import json
import os
import socket
import sys
import subprocess
import tempfile
import unittest
import uuid
from contextlib import contextmanager
import time
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any, Optional
from unittest.mock import MagicMock, patch
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from tools.lexicon.import_db import (
    ImportSummary,
    _ensure_backend_path,
    _load_existing_examples,
    _load_existing_relations,
    _rebuild_learner_catalog_projection,
    import_compiled_rows,
    run_import_file,
)


class _FakeClause:
    def __init__(self, text: str):
        self.text = text

    def __str__(self) -> str:
        return self.text


class _FakeOrderClause(_FakeClause):
    pass


class _FakeColumn:
    def __init__(self, table_name: str, column_name: str):
        self.table_name = table_name
        self.column_name = column_name

    def __eq__(self, other: object) -> _FakeClause:  # type: ignore[override]
        return _FakeClause(f"{self.table_name}.{self.column_name} = {other}")

    def in_(self, values: object) -> _FakeClause:
        return _FakeClause(f"{self.table_name}.{self.column_name} IN {values}")

    def asc(self) -> _FakeOrderClause:
        return _FakeOrderClause(f"{self.table_name}.{self.column_name} ASC")


class _FakeSelectStatement:
    def __init__(self, model: type):
        self.model = model
        self.whereclause = _FakeClause("")

    def where(self, *clauses: _FakeClause):
        self.whereclause = _FakeClause(" AND ".join(str(clause) for clause in clauses))
        return self

    def order_by(self, *_clauses: _FakeOrderClause):
        return self


def _install_fake_sqlalchemy_module() -> None:
    module = ModuleType("sqlalchemy")
    module.select = lambda model: _FakeSelectStatement(model)
    sys.modules["sqlalchemy"] = module


def _load_real_models():
    _ensure_backend_path()
    from app.core.database import Base
    from app.models.learner_catalog_entry import LearnerCatalogEntry
    from app.models.meaning_metadata import MeaningMetadata
    from app.models.meaning import Meaning
    from app.models.meaning_example import MeaningExample
    from app.models.phrase_entry import PhraseEntry
    from app.models.phrase_sense import PhraseSense
    from app.models.phrase_sense_example import PhraseSenseExample
    from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization
    from app.models.phrase_sense_localization import PhraseSenseLocalization
    from app.models.reference_entry import ReferenceEntry
    from app.models.reference_localization import ReferenceLocalization
    from app.models.translation import Translation
    from app.models.translation_example import TranslationExample
    from app.models.word import Word
    from app.models.word_confusable import WordConfusable
    from app.models.word_form import WordForm
    from app.models.word_part_of_speech import WordPartOfSpeech
    from app.models.word_relation import WordRelation
    from app.models.lexicon_enrichment_job import LexiconEnrichmentJob
    from app.models.lexicon_enrichment_run import LexiconEnrichmentRun

    return {
        "Base": Base,
        "LearnerCatalogEntry": LearnerCatalogEntry,
        "Word": Word,
        "Meaning": Meaning,
        "MeaningMetadata": MeaningMetadata,
        "MeaningExample": MeaningExample,
        "Translation": Translation,
        "TranslationExample": TranslationExample,
        "WordRelation": WordRelation,
        "WordConfusable": WordConfusable,
        "WordForm": WordForm,
        "WordPartOfSpeech": WordPartOfSpeech,
        "LexiconEnrichmentJob": LexiconEnrichmentJob,
        "LexiconEnrichmentRun": LexiconEnrichmentRun,
        "PhraseEntry": PhraseEntry,
        "PhraseSense": PhraseSense,
        "PhraseSenseLocalization": PhraseSenseLocalization,
        "PhraseSenseExample": PhraseSenseExample,
        "PhraseSenseExampleLocalization": PhraseSenseExampleLocalization,
        "ReferenceEntry": ReferenceEntry,
        "ReferenceLocalization": ReferenceLocalization,
    }


@contextmanager
def _temporary_postgres_lexicon_connection():
    container_name = None
    database_url = ""
    if os.environ.get("LEXICON_TEST_USE_EXISTING_POSTGRES") == "1":
        database_url = os.environ.get(
            "LEXICON_TEST_POSTGRES_URL",
            os.environ.get(
                "DATABASE_URL_SYNC",
                os.environ.get("DATABASE_URL", "postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev"),
            ),
        )

    engine = None
    if database_url:
        engine = create_engine(database_url, future=True)
        try:
            connection = engine.connect()
        except OperationalError:
            engine.dispose()
            engine = None
            database_url = ""
        else:
            transaction = connection.begin()
            try:
                connection.execute(text("DROP SCHEMA IF EXISTS lexicon CASCADE"))
                connection.execute(text("CREATE SCHEMA lexicon"))
                yield connection
            finally:
                transaction.rollback()
                connection.close()
                engine.dispose()
            return

    container_name, database_url = _start_temporary_postgres_container()
    engine = create_engine(database_url, future=True)
    connection = engine.connect()

    transaction = connection.begin()
    try:
        connection.execute(text("DROP SCHEMA IF EXISTS lexicon CASCADE"))
        connection.execute(text("CREATE SCHEMA lexicon"))
        yield connection
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
        if container_name is not None:
            subprocess.run(["docker", "rm", "-f", container_name], check=False, capture_output=True)


def _start_temporary_postgres_container():
    port = _find_free_port()
    container_name = f"words-v2-test-postgres-{uuid.uuid4().hex[:8]}"
    database_url = f"postgresql://vocabapp:devpassword@127.0.0.1:{port}/vocabapp_dev"
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--rm",
            "--name",
            container_name,
            "-e",
            "POSTGRES_USER=vocabapp",
            "-e",
            "POSTGRES_PASSWORD=devpassword",
            "-e",
            "POSTGRES_DB=vocabapp_dev",
            "-p",
            f"{port}:5432",
            "postgres:18-alpine",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    try:
        _wait_for_postgres(database_url)
    except Exception:
        subprocess.run(["docker", "rm", "-f", container_name], check=False, capture_output=True)
        raise
    return container_name, database_url


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_postgres(database_url: str) -> None:
    deadline = time.time() + 60
    last_error: Exception | None = None
    while time.time() < deadline:
        engine = create_engine(database_url, future=True)
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            engine.dispose()
            return
        except OperationalError as exc:
            last_error = exc
            engine.dispose()
            time.sleep(0.5)
    raise RuntimeError("temporary postgres container did not become ready") from last_error


def _create_real_lexicon_tables(connection, models) -> None:
    for name in [
        "PhraseEntry",
        "PhraseSense",
        "PhraseSenseLocalization",
        "PhraseSenseExample",
        "PhraseSenseExampleLocalization",
    ]:
        models[name].__table__.create(connection, checkfirst=True)


def _create_real_word_lexicon_tables(connection, models) -> None:
    models["Base"].metadata.create_all(
        connection,
        tables=[
            models["Word"].__table__,
            models["Meaning"].__table__,
            models["MeaningMetadata"].__table__,
            models["MeaningExample"].__table__,
            models["Translation"].__table__,
            models["TranslationExample"].__table__,
            models["WordRelation"].__table__,
            models["WordConfusable"].__table__,
            models["WordForm"].__table__,
            models["WordPartOfSpeech"].__table__,
            models["LexiconEnrichmentJob"].__table__,
            models["LexiconEnrichmentRun"].__table__,
        ],
        checkfirst=True,
    )


class SqlMeaningExample:
    __tablename__ = "meaning_examples"
    __table__ = object()
    meaning_id = _FakeColumn("meaning_examples", "meaning_id")
    source = _FakeColumn("meaning_examples", "source")
    order_index = _FakeColumn("meaning_examples", "order_index")


class SqlWordRelation:
    __tablename__ = "word_relations"
    __table__ = object()
    meaning_id = _FakeColumn("word_relations", "meaning_id")
    relation_type = _FakeColumn("word_relations", "relation_type")
    related_word = _FakeColumn("word_relations", "related_word")
    source = _FakeColumn("word_relations", "source")


class FakeLearnerCatalogEntry:
    __table__ = object()

    def __init__(
        self,
        *,
        entry_type: str,
        entry_id: uuid.UUID,
        display_text: str,
        normalized_form: str,
        browse_rank: int,
        bucket_start: int,
        cefr_level: str | None,
        primary_part_of_speech: str | None,
        phrase_kind: str | None,
        is_ranked: bool,
    ) -> None:
        self.entry_type = entry_type
        self.entry_id = entry_id
        self.display_text = display_text
        self.normalized_form = normalized_form
        self.browse_rank = browse_rank
        self.bucket_start = bucket_start
        self.cefr_level = cefr_level
        self.primary_part_of_speech = primary_part_of_speech
        self.phrase_kind = phrase_kind
        self.is_ranked = is_ranked


@dataclass
class FakeWord:
    word: str
    language: str = "en"
    phonetics: object = None
    phonetic: object = None
    frequency_rank: object = None
    cefr_level: object = None
    learner_part_of_speech: object = None
    confusable_words: object = None
    learner_generated_at: object = None
    word_forms: object = None
    form_entries: object = field(default_factory=list)
    part_of_speech_entries: object = field(default_factory=list)
    source_type: object = None
    source_reference: object = None
    phonetic_source: object = None
    phonetic_confidence: object = None
    phonetic_enrichment_run_id: object = None
    meanings: object = field(default_factory=list)
    relations: object = field(default_factory=list)
    enrichment_jobs: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeProjectionWordPartOfSpeech:
    value: str
    order_index: int = 0


@dataclass
class FakePhraseEntry:
    id: uuid.UUID
    phrase_text: str
    normalized_form: str
    phrase_kind: str | None = None
    cefr_level: str | None = None


class _FakeProjectionSession:
    def __init__(self, words: list[FakeWord], phrases: list[FakePhraseEntry]) -> None:
        self.words = words
        self.phrases = phrases
        self.added: list[FakeLearnerCatalogEntry] = []
        self.deleted = 0

    def query(self, model):
        session = self

        class _FakeQuery:
            def delete(self, synchronize_session: bool = False):
                session.deleted += 1
                return 0

        return _FakeQuery()

    def add_all(self, rows):
        self.added.extend(list(rows))


def test_rebuild_learner_catalog_projection_replaces_rows_with_ranked_words_and_phrases():
    ranked_word = FakeWord(
        word="alpha",
        frequency_rank=1,
        cefr_level="A1",
        part_of_speech_entries=[FakeProjectionWordPartOfSpeech(value="noun", order_index=0)],
    )
    ranked_word.id = uuid.uuid4()
    unranked_word = FakeWord(
        word="zeta",
        frequency_rank=None,
        cefr_level="B1",
        part_of_speech_entries=[FakeProjectionWordPartOfSpeech(value="verb", order_index=0)],
    )
    unranked_word.id = uuid.uuid4()
    phrase = FakePhraseEntry(
        id=uuid.uuid4(),
        phrase_text="bank on",
        normalized_form="bank on",
        phrase_kind="phrasal_verb",
        cefr_level="B2",
    )
    session = _FakeProjectionSession([ranked_word, unranked_word], [phrase])

    _rebuild_learner_catalog_projection(
        session,
        learner_catalog_entry_model=FakeLearnerCatalogEntry,
    )

    assert session.deleted == 1
    assert [(row.entry_type, row.display_text, row.browse_rank) for row in session.added] == [
        ("word", "alpha", 1),
        ("word", "zeta", 2),
        ("phrase", "bank on", 3),
    ]
    assert [row.bucket_start for row in session.added] == [1, 1, 1]
    assert session.added[0].primary_part_of_speech == "noun"
    assert session.added[1].primary_part_of_speech == "verb"
    assert session.added[2].phrase_kind == "phrasal_verb"


@dataclass
class FakeMeaning:
    word_id: uuid.UUID
    definition: str
    part_of_speech: object = None
    example_sentence: object = None
    wn_synset_id: object = None
    primary_domain: object = None
    secondary_domains: object = None
    register_label: object = None
    grammar_patterns: object = None
    usage_note: object = None
    metadata_entries: object = field(default_factory=list)
    translations: object = field(default_factory=list)
    word: object = None
    learner_generated_at: object = None
    order_index: int = 0
    source: object = None
    source_reference: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaningExample:
    meaning_id: uuid.UUID
    sentence: str
    difficulty: object = None
    order_index: int = 0
    source: object = None
    confidence: object = None
    enrichment_run_id: object = None
    meaning: object = None
    enrichment_run: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeTranslation:
    meaning_id: uuid.UUID
    language: str
    translation: str
    usage_note: object = None
    examples: object = None
    meaning: object = None
    example_entries: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeTranslationExample:
    translation_id: uuid.UUID
    text: str
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeMeaningMetadata:
    meaning_id: uuid.UUID
    metadata_kind: str
    value: str
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWordRelation:
    word_id: uuid.UUID
    meaning_id: Optional[uuid.UUID]
    relation_type: str
    related_word: str
    related_word_id: object = None
    source: object = None
    confidence: object = None
    enrichment_run_id: object = None
    word: object = None
    meaning: object = None
    enrichment_run: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeLexiconEnrichmentJob:
    word_id: uuid.UUID
    phase: str = "phase1"
    status: str = "pending"
    priority: int = 100
    attempt_count: int = 0
    max_attempts: int = 3
    started_at: object = None
    completed_at: object = None
    word: object = None
    runs: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeLexiconEnrichmentRun:
    enrichment_job_id: uuid.UUID
    generator_provider: object = None
    generator_model: object = None
    prompt_version: object = None
    prompt_hash: object = None
    verdict: object = None
    confidence: object = None
    created_at: object = None
    enrichment_job: object = None
    meaning_examples: object = field(default_factory=list)
    word_relations: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWordConfusable:
    word_id: uuid.UUID
    confusable_word: str
    note: object = None
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWordForm:
    word_id: uuid.UUID
    form_kind: str
    value: str
    form_slot: object = None
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeWordPartOfSpeech:
    word_id: uuid.UUID
    value: str
    order_index: int = 0
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakePhraseEntry:
    phrase_text: str
    normalized_form: str
    phrase_kind: str
    language: str = "en"
    cefr_level: object = None
    register_label: object = None
    brief_usage_note: object = None
    compiled_payload: object = None
    seed_metadata: object = None
    confidence_score: object = None
    generated_at: object = None
    source_type: object = None
    source_reference: object = None
    created_at: object = None
    phrase_senses: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakePhraseSenseLocalization:
    phrase_sense_id: uuid.UUID
    locale: str
    localized_definition: object = None
    localized_usage_note: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakePhraseSenseExampleLocalization:
    phrase_sense_example_id: uuid.UUID
    locale: str
    translation: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakePhraseSenseExample:
    phrase_sense_id: uuid.UUID
    sentence: str
    difficulty: object = None
    order_index: int = 0
    source: object = None
    localizations: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakePhraseSense:
    phrase_entry_id: uuid.UUID
    definition: str
    usage_note: object = None
    part_of_speech: object = None
    register: object = None
    primary_domain: object = None
    secondary_domains: object = field(default_factory=list)
    grammar_patterns: object = field(default_factory=list)
    synonyms: object = field(default_factory=list)
    antonyms: object = field(default_factory=list)
    collocations: object = field(default_factory=list)
    order_index: int = 0
    localizations: object = field(default_factory=list)
    examples: object = field(default_factory=list)
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeReferenceEntry:
    reference_type: str
    display_form: str
    normalized_form: str
    translation_mode: str
    brief_description: str
    pronunciation: str
    learner_tip: object = None
    language: str = "en"
    source_type: object = None
    source_reference: object = None
    created_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


@dataclass
class FakeReferenceLocalization:
    reference_entry_id: uuid.UUID
    locale: str
    display_form: str
    brief_description: object = None
    translation_mode: object = None
    created_at: object = None
    id: uuid.UUID = field(default_factory=uuid.uuid4)


class _ScalarResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _Scalars:
    def __init__(self, values):
        self._values = values

    def all(self):
        return self._values


class _ListResult:
    def __init__(self, values):
        self._values = values

    def scalars(self):
        return _Scalars(self._values)


class ImportCompiledRowsTests(unittest.TestCase):
    def test_load_existing_examples_ignores_source_filter_for_sqlalchemy_models(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ListResult([])
        _install_fake_sqlalchemy_module()

        _load_existing_examples(session, SqlMeaningExample, uuid.uuid4(), "snapshot_refresh")

        statement = session.execute.call_args[0][0]
        where_clause = str(statement.whereclause)
        self.assertIn("meaning_examples.meaning_id", where_clause)
        self.assertNotIn("meaning_examples.source", where_clause)

    def test_load_existing_relations_ignores_source_filter_for_sqlalchemy_models(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ListResult([])
        _install_fake_sqlalchemy_module()

        _load_existing_relations(session, SqlWordRelation, uuid.uuid4(), "snapshot_refresh")

        statement = session.execute.call_args[0][0]
        where_clause = str(statement.whereclause)
        self.assertIn("word_relations.meaning_id", where_clause)
        self.assertIn("word_relations.relation_type", where_clause)
        self.assertNotIn("word_relations.source", where_clause)

    def test_import_creates_word_and_meanings_with_provenance(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb", "noun"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": ["runs"],
                    "verb_forms": {
                        "base": "run",
                        "third_person_singular": "runs",
                        "past": "ran",
                        "past_participle": "run",
                        "gerund": "running",
                    },
                    "comparative": None,
                    "superlative": None,
                    "derivations": ["runner"],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                    },
                    {
                        "sense_id": "sn_lx_run_run_n_01_ef567890",
                        "pos": "noun",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "an act of running",
                        "examples": [{"sentence": "She went for a run.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": [],
                        "collocations": ["go for a run"],
                        "grammar_patterns": ["go for a run"],
                        "usage_note": "Common exercise noun.",
                    },
                ],
                "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
        )

        self.assertEqual(summary, ImportSummary(created_words=1, updated_words=0, created_meanings=2, updated_meanings=0))
        self.assertEqual(len(added), 3)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        imported_meanings = [item for item in added if isinstance(item, FakeMeaning)]
        self.assertEqual(imported_word.word, "run")
        self.assertEqual(imported_word.cefr_level, "A1")
        self.assertEqual(imported_word.source_type, "lexicon_snapshot")
        self.assertEqual(imported_word.source_reference, "snapshot-20260307")
        self.assertEqual(imported_word.phonetics["au"]["ipa"], "/rɐn/")
        self.assertEqual(imported_word.phonetic, "/rʌn/")
        self.assertEqual(imported_word.phonetic_source, "lexicon_snapshot")
        self.assertEqual(imported_word.phonetic_confidence, 0.99)
        self.assertIsNotNone(imported_word.learner_generated_at)
        self.assertEqual(imported_meanings[0].source, "lexicon_snapshot")
        self.assertEqual(imported_meanings[0].primary_domain, "general")
        self.assertEqual(imported_meanings[0].register_label, "neutral")
        self.assertEqual(imported_meanings[0].usage_note, "Common everyday verb.")
        self.assertEqual(imported_meanings[0].source_reference, "snapshot-20260307:sn_lx_run_run_v_01_abcd1234")
        self.assertEqual(imported_meanings[1].order_index, 1)

    def test_import_replaces_normalized_word_confusable_rows(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(word="run")
        existing_word.confusable_entries = [
            FakeWordConfusable(
                word_id=existing_word.id,
                confusable_word="old",
                note="stale",
                order_index=0,
            )
        ]
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([]),
            _ScalarResult(None),
        ]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {},
                "senses": [],
                "confusable_words": [
                    {"word": "ran", "note": "Past tense form."},
                    {"word": "sprint", "note": "Related but different."},
                ],
            }
        ]

        import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            word_confusable_model=FakeWordConfusable,
        )

        self.assertEqual(
            [(item.confusable_word, item.note, item.order_index) for item in existing_word.confusable_entries],
            [
                ("ran", "Past tense form.", 0),
                ("sprint", "Related but different.", 1),
            ],
        )

    def test_import_fail_mode_raises_for_existing_word(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(word="run")
        session.execute.side_effect = [
            _ScalarResult(existing_word),
        ]

        with self.assertRaisesRegex(ValueError, "already exists"):
            import_compiled_rows(
                session,
                [
                    {
                        "schema_version": "1.0.0",
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "A1",
                        "frequency_rank": 5,
                        "forms": {},
                        "senses": [],
                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                    }
                ],
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260307",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                word_confusable_model=FakeWordConfusable,
                on_conflict="fail",
            )

    def test_import_skip_mode_leaves_existing_word_unchanged(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(word="run")
        existing_word.confusable_entries = [
            FakeWordConfusable(
                word_id=existing_word.id,
                confusable_word="old",
                note="stale",
                order_index=0,
            )
        ]
        session.execute.side_effect = [
            _ScalarResult(existing_word),
        ]

        summary = import_compiled_rows(
            session,
            [
                {
                    "schema_version": "1.0.0",
                    "word": "run",
                    "part_of_speech": ["verb"],
                    "cefr_level": "A1",
                    "frequency_rank": 5,
                    "forms": {},
                    "senses": [],
                    "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                }
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            word_confusable_model=FakeWordConfusable,
            on_conflict="skip",
        )

        self.assertEqual(summary.skipped_words, 1)
        self.assertEqual(
            [(item.confusable_word, item.note, item.order_index) for item in existing_word.confusable_entries],
            [("old", "stale", 0)],
        )

    def test_import_replaces_normalized_word_form_rows(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(
            word="run",
            word_forms={"verb_forms": {"base": "stale"}},
            form_entries=[
                FakeWordForm(word_id=uuid.uuid4(), form_kind="plural", value="stales", order_index=0),
            ],
        )
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([]),
            _ScalarResult(None),
        ]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        import_compiled_rows(
            session,
            [
                {
                    "schema_version": "1.0.0",
                    "word": "run",
                    "part_of_speech": ["verb"],
                    "cefr_level": "A1",
                    "frequency_rank": 5,
                    "forms": {
                        "plural_forms": ["runs"],
                        "verb_forms": {
                            "base": "run",
                            "past": "ran",
                            "gerund": "running",
                        },
                        "comparative": None,
                        "superlative": None,
                        "derivations": ["runner"],
                    },
                    "senses": [],
                    "confusable_words": [],
                }
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            word_form_model=FakeWordForm,
        )

        self.assertEqual(
            [(item.form_kind, item.form_slot, item.value, item.order_index) for item in existing_word.form_entries],
            [
                ("verb", "base", "run", 0),
                ("verb", "past", "ran", 1),
                ("verb", "gerund", "running", 2),
                ("plural", "", "runs", 0),
                ("derivation", "", "runner", 0),
            ],
        )
        self.assertEqual(existing_word.word_forms["verb_forms"]["base"], "stale")

    def test_import_replaces_normalized_word_part_of_speech_rows(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(
            word="run",
            learner_part_of_speech=["stale"],
            part_of_speech_entries=[
                FakeWordPartOfSpeech(word_id=uuid.uuid4(), value="stale", order_index=0),
            ],
        )
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([]),
        ]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        import_compiled_rows(
            session,
            [
                {
                    "schema_version": "1.0.0",
                    "word": "run",
                    "part_of_speech": ["verb", "noun"],
                    "cefr_level": "A1",
                    "frequency_rank": 5,
                    "forms": {},
                    "senses": [],
                    "confusable_words": [],
                }
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            word_part_of_speech_model=FakeWordPartOfSpeech,
        )

        self.assertEqual(
            [(item.value, item.order_index) for item in existing_word.part_of_speech_entries],
            [("verb", 0), ("noun", 1)],
        )
        self.assertEqual(existing_word.learner_part_of_speech, ["stale"])


    def test_import_applies_word_level_fields_even_without_senses(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "solo",
                "part_of_speech": ["adjective"],
                "cefr_level": "A2",
                "frequency_rank": 1234,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [],
                "confusable_words": [{"word": "single", "note": "Related but not identical."}],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_words, 1)
        self.assertEqual(summary.created_meanings, 0)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        self.assertEqual(imported_word.cefr_level, "A2")
        self.assertIsNotNone(imported_word.learner_generated_at)

    def test_import_honors_row_level_word_language_and_provenance(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "bonjour",
                "language": "fr",
                "source_type": "db_export",
                "source_reference": "fixture-fr",
                "frequency_rank": 11,
                "forms": {},
                "senses": [
                    {
                        "sense_id": "sense-fr-001",
                        "definition": "hello",
                        "pos": "interjection",
                    }
                ],
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="fallback_source",
            source_reference="fallback-ref",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
        )

        self.assertEqual(summary.created_words, 1)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        imported_meaning = next(item for item in added if isinstance(item, FakeMeaning))
        self.assertEqual(imported_word.language, "fr")
        self.assertEqual(imported_word.source_type, "db_export")
        self.assertEqual(imported_word.source_reference, "fixture-fr")
        self.assertEqual(imported_meaning.source, "db_export")
        self.assertEqual(imported_meaning.source_reference, "fixture-fr:sense-fr-001")

    def test_import_honors_row_level_phrase_provenance(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(None)]
        added = []
        session.add.side_effect = added.append

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "by and large",
                "display_form": "by and large",
                "normalized_form": "by and large",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "senses": [],
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="fallback_source",
            source_reference="fallback-ref",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
        )

        self.assertEqual(summary.created_phrases, 1)
        imported_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        self.assertEqual(imported_phrase.source_type, "db_export")
        self.assertEqual(imported_phrase.source_reference, "phrase-fixture")
        self.assertEqual(imported_phrase.language, "en")

    def test_import_preflight_reports_phrase_translation_usage_note_error_before_mutating_counts(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(None)]
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "by and large",
                "display_form": "by and large",
                "normalized_form": "by and large",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "senses": [
                    {
                        "sense_id": "phrase-1",
                        "definition": "generally",
                        "part_of_speech": "adverb",
                        "examples": [{"sentence": "By and large, the plan worked.", "difficulty": "B2"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "总的来说",
                                "usage_note": "",
                                "examples": ["总的来说，计划成功了。"],
                            }
                        },
                    }
                ],
            }
        ]

        with self.assertRaisesRegex(RuntimeError, "usage_note must be a non-empty string"):
            import_compiled_rows(
                session,
                rows,
                source_type="fallback_source",
                source_reference="fallback-ref",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                phrase_model=FakePhraseEntry,
                phrase_sense_model=FakePhraseSense,
                phrase_sense_localization_model=FakePhraseSenseLocalization,
                phrase_sense_example_model=FakePhraseSenseExample,
                phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
                on_conflict="upsert",
                error_mode="continue",
                dry_run=True,
            )

    def test_import_preserves_localized_usage_notes_and_example_translations(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),  # existing word lookup
            _ListResult([]),      # existing meanings
            _ListResult([]),      # existing examples
            _ListResult([]),      # existing translations
            _ListResult([]),      # existing relations
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "forms": {},
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "pos": "noun",
                        "examples": [{"sentence": "I do not have time today.", "difficulty": "A1"}],
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "usage_note": "Muito comum em contextos abstratos e práticos.",
                                "examples": ["Eu não tenho tempo hoje."],
                            }
                        },
                    }
                ],
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260324",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            translation_model=FakeTranslation,
            translation_example_model=FakeTranslationExample,
            word_relation_model=FakeWordRelation,
        )

        self.assertEqual(summary.created_translations, 1)
        imported_translation = next(item for item in added if isinstance(item, FakeTranslation))
        self.assertEqual(imported_translation.translation, "tempo")
        self.assertEqual(imported_translation.usage_note, "Muito comum em contextos abstratos e práticos.")
        self.assertEqual(
            [(item.text, item.order_index) for item in imported_translation.example_entries],
            [("Eu não tenho tempo hoje.", 0)],
        )

    def test_import_replaces_normalized_translation_example_rows(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(word="time")
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="the thing measured in minutes and hours",
            part_of_speech="noun",
            order_index=0,
        )
        existing_translation = FakeTranslation(
            meaning_id=existing_meaning.id,
            language="pt-BR",
            translation="tempo",
            example_entries=[
                FakeTranslationExample(
                    translation_id=uuid.uuid4(),
                    text="stale translated example",
                    order_index=0,
                )
            ],
        )
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
            _ListResult([]),
            _ListResult([existing_translation]),
            _ListResult([]),
        ]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        import_compiled_rows(
            session,
            [
                {
                    "schema_version": "1.1.0",
                    "entry_type": "word",
                    "word": "time",
                    "language": "en",
                    "forms": {},
                    "senses": [
                        {
                            "sense_id": "sense-001",
                            "definition": "the thing measured in minutes and hours",
                            "pos": "noun",
                            "examples": [{"sentence": "I do not have time today.", "difficulty": "A1"}],
                            "translations": {
                                "pt-BR": {
                                    "definition": "tempo",
                                    "usage_note": "Muito comum em contextos abstratos e práticos.",
                                    "examples": ["Eu não tenho tempo hoje."],
                                }
                            },
                        }
                    ],
                }
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260324",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            translation_model=FakeTranslation,
            translation_example_model=FakeTranslationExample,
            word_relation_model=FakeWordRelation,
        )

        self.assertEqual(
            [(item.text, item.order_index) for item in existing_translation.example_entries],
            [("Eu não tenho tempo hoje.", 0)],
        )

    def test_import_replaces_normalized_meaning_metadata_rows(self) -> None:
        session = MagicMock()
        existing_word = FakeWord(word="run")
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="to move quickly on foot",
            secondary_domains=["stale-domain"],
            grammar_patterns=["stale-pattern"],
            metadata_entries=[
                FakeMeaningMetadata(meaning_id=uuid.uuid4(), metadata_kind="secondary_domain", value="stale-domain", order_index=0),
                FakeMeaningMetadata(meaning_id=uuid.uuid4(), metadata_kind="grammar_pattern", value="stale-pattern", order_index=0),
            ],
        )
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
            _ListResult([]),
            _ListResult([]),
        ]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        import_compiled_rows(
            session,
            [
                {
                    "schema_version": "1.0.0",
                    "word": "run",
                    "part_of_speech": ["verb"],
                    "cefr_level": "A1",
                    "frequency_rank": 5,
                    "forms": {},
                    "senses": [
                        {
                            "sense_id": "sn_lx_run_run_v_01_abcd1234",
                            "pos": "verb",
                            "definition": "to move quickly on foot",
                            "primary_domain": "general",
                            "secondary_domains": ["general", "movement"],
                            "register": "neutral",
                            "grammar_patterns": ["run + adverb"],
                            "usage_note": "Common everyday verb.",
                            "examples": [],
                        }
                    ],
                    "confusable_words": [],
                }
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_metadata_model=FakeMeaningMetadata,
        )

        self.assertEqual(
            [(item.metadata_kind, item.value, item.order_index) for item in existing_meaning.metadata_entries],
            [
                ("secondary_domain", "general", 0),
                ("secondary_domain", "movement", 1),
                ("grammar_pattern", "run + adverb", 0),
            ],
        )

    def test_import_upsert_mode_reimports_existing_word_without_duplicate_normalized_children_on_real_sqlalchemy_models(self) -> None:
        models = _load_real_models()
        row = {
            "schema_version": "1.1.0",
            "entry_type": "word",
            "word": "aaron",
            "language": "en",
            "cefr_level": "A2",
            "frequency_rank": 4815,
            "part_of_speech": ["proper noun"],
            "forms": {"plural_forms": ["Aarons"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "confusable_words": [{"word": "Erin", "note": "another male given name; different name"}],
            "phonetics": {"us": {"ipa": "ˈerən", "confidence": 0.88}},
            "phonetic": "ˈerən",
            "phonetic_confidence": 0.88,
            "generated_at": "2026-03-24T02:57:14+00:00",
            "source_type": "snapshot_reviewed_approved",
            "source_reference": "words-40000-20260323-main-wordfreq-live-target30k",
            "senses": [
                {
                    "sense_id": "sn_lx_aaron_1",
                    "definition": "a male first name",
                    "pos": "proper noun",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "grammar_patterns": ["Aaron + be + noun", "meet + Aaron", "call + someone + Aaron"],
                    "usage_note": "Used as a common male given name in English and many other languages.",
                    "generated_at": "2026-03-24T02:57:14+00:00",
                    "examples": [
                        {"sentence": "Aaron is my cousin.", "difficulty": "A2"},
                        {"sentence": "I met Aaron at school.", "difficulty": "A2"},
                    ],
                    "translations": {
                        "zh-Hans": {
                            "definition": "男性名字：亚伦，阿伦",
                            "usage_note": "用作男性人名。",
                            "examples": ["亚伦是我表弟。", "我在学校见到了亚伦。"],
                        }
                    },
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": ["Aaron and I", "Aaron said", "my friend Aaron"],
                }
            ],
        }

        with _temporary_postgres_lexicon_connection() as connection:
            _create_real_word_lexicon_tables(connection, models)
            session = Session(bind=connection, expire_on_commit=False)
            try:
                import_kwargs = dict(
                    source_type="snapshot_reviewed_approved",
                    source_reference="words-40000-20260323-main-wordfreq-live-target30k",
                    language="en",
                    word_model=models["Word"],
                    meaning_model=models["Meaning"],
                    meaning_metadata_model=models["MeaningMetadata"],
                    meaning_example_model=models["MeaningExample"],
                    word_relation_model=models["WordRelation"],
                    lexicon_enrichment_job_model=models["LexiconEnrichmentJob"],
                    lexicon_enrichment_run_model=models["LexiconEnrichmentRun"],
                    translation_model=models["Translation"],
                    translation_example_model=models["TranslationExample"],
                    word_confusable_model=models["WordConfusable"],
                    word_form_model=models["WordForm"],
                    word_part_of_speech_model=models["WordPartOfSpeech"],
                    rebuild_learner_catalog=False,
                    on_conflict="upsert",
                )

                import_compiled_rows(session, [row], **import_kwargs)
                session.flush()

                import_compiled_rows(session, [row], **import_kwargs)
                session.flush()

                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.words")).scalar_one(), 1)
                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.word_confusables")).scalar_one(), 1)
                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.meaning_metadata WHERE metadata_kind = 'grammar_pattern'")).scalar_one(), 3)
                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.meaning_examples")).scalar_one(), 2)
                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.translation_examples")).scalar_one(), 2)
                self.assertEqual(connection.execute(text("SELECT count(*) FROM lexicon.word_relations")).scalar_one(), 3)
            finally:
                session.close()

    def test_import_updates_existing_word_and_meanings_without_duplication(self) -> None:
        existing_word = FakeWord(
            word="run",
            language="en",
            frequency_rank=50,
            source_type="older_source",
            source_reference="old-snapshot",
        )
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="old definition",
            part_of_speech="verb",
            example_sentence="Old example.",
            order_index=0,
            source="older_source",
            source_reference="old-snapshot:old-sense",
        )

        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
        ]
        added = []
        deleted = []
        session.add.side_effect = added.append
        session.delete.side_effect = deleted.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": ["runs"],
                    "verb_forms": {
                        "base": "run",
                        "third_person_singular": "runs",
                        "past": "ran",
                        "past_participle": "run",
                        "gerund": "running",
                    },
                    "comparative": None,
                    "superlative": None,
                    "derivations": ["runner"],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                    }
                ],
                "confusable_words": [],
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
        )

        self.assertEqual(summary, ImportSummary(created_words=0, updated_words=1, created_meanings=0, updated_meanings=1))
        self.assertEqual(existing_word.frequency_rank, 5)
        self.assertEqual(existing_word.cefr_level, "A1")
        self.assertIsNotNone(existing_word.learner_generated_at)
        self.assertEqual(existing_word.source_reference, "snapshot-20260307")
        self.assertEqual(existing_meaning.definition, "to move quickly on foot")
        self.assertEqual(existing_meaning.example_sentence, "I run every morning.")
        self.assertEqual(existing_meaning.primary_domain, "general")
        self.assertEqual(existing_meaning.register_label, "neutral")
        self.assertEqual(existing_meaning.usage_note, "Common everyday verb.")
        self.assertIsNotNone(existing_meaning.learner_generated_at)
        self.assertEqual(existing_meaning.source_reference, "snapshot-20260307:sn_lx_run_run_v_01_abcd1234")
        self.assertEqual(added, [])
        self.assertEqual(deleted, [])

    def test_import_creates_examples_relations_and_enrichment_provenance_when_models_are_provided(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
            _ScalarResult(None),
            _ListResult([]),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [
                            {"sentence": "I run every morning.", "difficulty": "A1"},
                            {"sentence": "They run together on Sundays.", "difficulty": "A2"},
                        ],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": ["run fast"],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_run_v_01_abcd1234_v1",
                        "generation_run_id": "run-123",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.91,
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                ],
                "confusable_words": [],
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_words, 1)
        self.assertEqual(summary.created_meanings, 1)
        self.assertEqual(summary.created_examples, 2)
        self.assertEqual(summary.created_relations, 3)
        self.assertEqual(summary.created_enrichment_jobs, 1)
        self.assertEqual(summary.created_enrichment_runs, 1)

        imported_job = next(item for item in added if isinstance(item, FakeLexiconEnrichmentJob))
        imported_run = next(item for item in added if isinstance(item, FakeLexiconEnrichmentRun))
        imported_examples = [item for item in added if isinstance(item, FakeMeaningExample)]
        imported_relations = [item for item in added if isinstance(item, FakeWordRelation)]

        self.assertEqual(imported_job.phase, "phase1")
        self.assertEqual(imported_job.status, "completed")
        self.assertEqual(imported_run.generator_model, "gpt-5.1")
        self.assertEqual(imported_run.prompt_version, "v1")
        self.assertEqual(imported_run.confidence, 0.91)
        imported_word = next(item for item in added if isinstance(item, FakeWord))
        imported_meaning = next(item for item in added if isinstance(item, FakeMeaning))
        self.assertEqual(imported_word.cefr_level, "A1")
        self.assertIsNotNone(imported_word.learner_generated_at)
        self.assertEqual(imported_meaning.wn_synset_id, "run.v.01")
        self.assertEqual(imported_meaning.primary_domain, "general")
        self.assertEqual(imported_meaning.register_label, "neutral")
        self.assertEqual(imported_meaning.usage_note, "Common everyday verb.")
        self.assertIsNotNone(imported_meaning.learner_generated_at)
        self.assertEqual([item.sentence for item in imported_examples], [
            "I run every morning.",
            "They run together on Sundays.",
        ])
        self.assertEqual([item.difficulty for item in imported_examples], ["A1", "A2"])
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in imported_relations],
            [("synonym", "jog"), ("antonym", "walk"), ("collocation", "run fast")],
        )
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_examples))
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_relations))
        self.assertEqual(imported_word.phonetics["uk"]["ipa"], "/rʌn/")
        self.assertEqual(imported_word.phonetic, "/rʌn/")
        self.assertEqual(imported_word.phonetic_confidence, 0.99)
        self.assertEqual(imported_word.phonetic_enrichment_run_id, imported_run.id)

    def test_import_collapses_same_generation_run_id_to_one_enrichment_run_per_word(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),
            _ListResult([]),
            _ScalarResult(None),
            _ScalarResult(None),
            _ListResult([]),
            _ListResult([]),
            _ListResult([]),
            _ListResult([]),
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "set",
                "part_of_speech": ["verb", "noun"],
                "cefr_level": "A1",
                "frequency_rank": 10,
                "forms": {
                    "plural_forms": ["sets"],
                    "verb_forms": {"base": "set", "third_person_singular": "sets", "past": "set", "past_participle": "set", "gerund": "setting"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_set_1",
                        "wn_synset_id": "set.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to put something in a place",
                        "examples": [{"sentence": "She set the cup on the table.", "difficulty": "A1"}],
                        "synonyms": ["place"],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": ["set + object + place"],
                        "usage_note": "Common verb sense.",
                        "enrichment_id": "en_sn_lx_set_1_v1",
                        "generation_run_id": "word-run-1",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.95,
                        "generated_at": "2026-03-12T00:00:00Z",
                    },
                    {
                        "sense_id": "sn_lx_set_2",
                        "wn_synset_id": "set.n.01",
                        "pos": "noun",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "a group of things that belong together",
                        "examples": [{"sentence": "This chess set is old.", "difficulty": "A1"}],
                        "synonyms": ["collection"],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common noun sense.",
                        "enrichment_id": "en_sn_lx_set_2_v1",
                        "generation_run_id": "word-run-1",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.94,
                        "generated_at": "2026-03-12T00:00:00Z",
                    },
                ],
                "confusable_words": [],
                "generated_at": "2026-03-12T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260312",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_enrichment_jobs, 1)
        self.assertEqual(summary.created_enrichment_runs, 1)
        imported_run = next(item for item in added if isinstance(item, FakeLexiconEnrichmentRun))
        imported_examples = [item for item in added if isinstance(item, FakeMeaningExample)]
        imported_relations = [item for item in added if isinstance(item, FakeWordRelation)]
        self.assertEqual(len([item for item in added if isinstance(item, FakeLexiconEnrichmentRun)]), 1)
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_examples))
        self.assertTrue(all(item.enrichment_run_id == imported_run.id for item in imported_relations))

    def test_import_compiled_rows_supports_phrase_and_reference_rows(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(None),  # phrase lookup
            _ScalarResult(None),  # reference lookup
            _ListResult([]),      # reference localizations lookup
        ]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [{
                    "sense_id": "phrase-1",
                    "definition": "leave the ground",
                    "part_of_speech": "verb",
                    "register": "neutral",
                    "primary_domain": "general",
                    "secondary_domains": ["general", "transport"],
                    "examples": [
                        {"sentence": "The plane took off.", "difficulty": "A1"},
                        {"sentence": "We took off early.", "difficulty": "A2"},
                    ],
                    "grammar_patterns": ["subject + take off"],
                    "usage_note": "Common for planes.",
                    "synonyms": ["depart", "set off"],
                    "antonyms": ["land"],
                    "collocations": ["take off quickly"],
                    "translations": {
                        "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。", "我们很早起飞了。"]},
                        "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó.", "Despegamos temprano."]},
                        "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة.", "أقلعنا مبكرًا."]},
                        "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou.", "Decolamos cedo."]},
                        "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。", "私たちは早く離陸した。"]},
                    },
                }],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
                "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
                "confidence": 0.91,
            },
            {
                "schema_version": "1.1.0",
                "entry_id": "rf_australia",
                "entry_type": "reference",
                "normalized_form": "australia",
                "source_provenance": [{"source": "reference_seed"}],
                "entity_category": "general",
                "word": "Australia",
                "part_of_speech": [],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "reference_type": "country",
                "display_form": "Australia",
                "translation_mode": "localized",
                "brief_description": "A country in the Southern Hemisphere.",
                "pronunciation": "/ɔˈstreɪliə/",
                "localized_display_form": {"es": "Australia"},
                "localized_brief_description": {"es": "País del hemisferio sur."},
                "learner_tip": "Stress is on STRAY.",
                "localizations": [{"locale": "es", "display_form": "Australia", "translation_mode": "localized"}],
            },
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
            reference_model=FakeReferenceEntry,
            reference_localization_model=FakeReferenceLocalization,
        )

        self.assertEqual(summary.created_phrases, 1)
        self.assertEqual(summary.created_reference_entries, 1)
        self.assertEqual(summary.created_reference_localizations, 1)
        self.assertEqual(any(isinstance(item, FakePhraseEntry) for item in added), True)
        self.assertEqual(any(isinstance(item, FakeReferenceEntry) for item in added), True)
        self.assertEqual(any(isinstance(item, FakeReferenceLocalization) for item in added), True)
        imported_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        imported_sense = next(item for item in added if isinstance(item, FakePhraseSense))
        imported_phrase.compiled_payload = None
        self.assertEqual(imported_phrase.seed_metadata["raw_reviewed_as"], "phrasal verb")
        self.assertEqual(imported_phrase.confidence_score, 0.91)
        self.assertEqual(imported_phrase.phrase_senses[0], imported_sense)
        self.assertEqual(imported_sense.definition, "leave the ground")
        self.assertEqual(imported_sense.usage_note, "Common for planes.")
        self.assertEqual([row.locale for row in imported_sense.localizations], ["ar", "es", "ja", "pt-BR", "zh-Hans"])
        self.assertEqual(next(row.localized_definition for row in imported_sense.localizations if row.locale == "ja"), "離陸する")
        self.assertEqual(
            [row.localized_usage_note for row in imported_sense.localizations if row.locale == "zh-Hans"],
            ["常见用法"],
        )
        self.assertEqual([row.sentence for row in imported_sense.examples], ["The plane took off.", "We took off early."])
        self.assertEqual(imported_sense.part_of_speech, "verb")
        self.assertEqual(imported_sense.register, "neutral")
        self.assertEqual(imported_sense.primary_domain, "general")
        self.assertEqual(imported_sense.secondary_domains, ["general", "transport"])
        self.assertEqual(imported_sense.grammar_patterns, ["subject + take off"])
        self.assertEqual(imported_sense.synonyms, ["depart", "set off"])
        self.assertEqual(imported_sense.antonyms, ["land"])
        self.assertEqual(imported_sense.collocations, ["take off quickly"])
        self.assertEqual(
            [row.translation for row in imported_sense.examples[0].localizations],
            ["أقلعت الطائرة.", "El avión despegó.", "飛行機が離陸した。", "O avião decolou.", "飞机起飞了。"],
        )
        self.assertEqual(
            [row.translation for row in imported_sense.examples[1].localizations],
            ["أقلعنا مبكرًا.", "Despegamos temprano.", "私たちは早く離陸した。", "Decolamos cedo.", "我们很早起飞了。"],
        )

    def test_import_compiled_rows_uses_effective_normalized_form_for_new_phrase_cache_keys(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ScalarResult(None)
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        summary = import_compiled_rows(
            session,
            [
                {
                    "entry_type": "phrase",
                    "word": "Take Off",
                    "display_form": "Take Off",
                    "senses": [],
                },
                {
                    "entry_type": "phrase",
                    "word": "By And Large",
                    "display_form": "By And Large",
                    "senses": [],
                },
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260329",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        phrases = [item for item in added if isinstance(item, FakePhraseEntry)]
        self.assertEqual(summary.created_phrases, 2)
        self.assertEqual(len(phrases), 2)
        self.assertEqual([phrase.normalized_form for phrase in phrases], ["take off", "by and large"])

    def test_import_compiled_rows_uses_effective_normalized_form_for_new_reference_cache_keys(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(None), _ScalarResult(None)]
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        summary = import_compiled_rows(
            session,
            [
                {
                    "entry_type": "reference",
                    "word": "Australia",
                    "display_form": "Australia",
                    "localizations": [],
                },
                {
                    "entry_type": "reference",
                    "word": "New Zealand",
                    "display_form": "New Zealand",
                    "localizations": [],
                },
            ],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260329",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            reference_model=FakeReferenceEntry,
            reference_localization_model=FakeReferenceLocalization,
        )

        references = [item for item in added if isinstance(item, FakeReferenceEntry)]
        self.assertEqual(summary.created_reference_entries, 2)
        self.assertEqual(len(references), 2)
        self.assertEqual([reference.normalized_form for reference in references], ["australia", "new zealand"])

    def test_import_compiled_rows_replaces_normalized_phrase_children_on_repeat_import_with_real_sqlalchemy_models(self) -> None:
        models = _load_real_models()

        first_row = {
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{
                "sense_id": "phrase-1",
                "definition": "leave the ground",
                "part_of_speech": "verb",
                "register": "neutral",
                "primary_domain": "general",
                "secondary_domains": ["general", "transport"],
                "examples": [
                    {"sentence": "The plane took off.", "difficulty": "A1"},
                    {"sentence": "We took off early.", "difficulty": "A2"},
                ],
                "grammar_patterns": ["subject + take off"],
                "usage_note": "Common for planes.",
                "synonyms": ["depart", "set off"],
                "antonyms": ["land"],
                "collocations": ["take off quickly"],
                "translations": {
                    "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。", "我们很早起飞了。"]},
                    "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó.", "Despegamos temprano."]},
                    "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة.", "أقلعنا مبكرًا."]},
                    "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou.", "Decolamos cedo."]},
                    "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。", "私たちは早く離陸した。"]},
                },
            }],
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "phrase_kind": "phrasal_verb",
            "display_form": "take off",
            "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
            "confidence": 0.91,
        }
        empty_row = {**first_row, "senses": []}

        with _temporary_postgres_lexicon_connection() as connection:
            _create_real_lexicon_tables(connection, models)
            session = Session(bind=connection, expire_on_commit=False)
            try:
                import_compiled_rows(
                    session,
                    [first_row],
                    source_type="lexicon_snapshot",
                    source_reference="snapshot-20260320",
                    language="en",
                    word_model=models["Word"],
                    meaning_model=models["Meaning"],
                    meaning_example_model=models["MeaningExample"],
                    word_relation_model=models["WordRelation"],
                    lexicon_enrichment_job_model=models["LexiconEnrichmentJob"],
                    lexicon_enrichment_run_model=models["LexiconEnrichmentRun"],
                    translation_model=models["Translation"],
                    phrase_model=models["PhraseEntry"],
                    phrase_sense_model=models["PhraseSense"],
                    phrase_sense_localization_model=models["PhraseSenseLocalization"],
                    phrase_sense_example_model=models["PhraseSenseExample"],
                    phrase_sense_example_localization_model=models["PhraseSenseExampleLocalization"],
                    reference_model=models["ReferenceEntry"],
                    reference_localization_model=models["ReferenceLocalization"],
                )
                session.flush()

                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_senses")).scalar_one() == 1
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_localizations")).scalar_one() == 5
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_examples")).scalar_one() == 2
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_example_localizations")).scalar_one() == 10

                import_compiled_rows(
                    session,
                    [empty_row],
                    source_type="lexicon_snapshot",
                    source_reference="snapshot-20260320",
                    language="en",
                    word_model=models["Word"],
                    meaning_model=models["Meaning"],
                    meaning_example_model=models["MeaningExample"],
                    word_relation_model=models["WordRelation"],
                    lexicon_enrichment_job_model=models["LexiconEnrichmentJob"],
                    lexicon_enrichment_run_model=models["LexiconEnrichmentRun"],
                    translation_model=models["Translation"],
                    phrase_model=models["PhraseEntry"],
                    phrase_sense_model=models["PhraseSense"],
                    phrase_sense_localization_model=models["PhraseSenseLocalization"],
                    phrase_sense_example_model=models["PhraseSenseExample"],
                    phrase_sense_example_localization_model=models["PhraseSenseExampleLocalization"],
                    reference_model=models["ReferenceEntry"],
                    reference_localization_model=models["ReferenceLocalization"],
                )
                session.flush()

                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_senses")).scalar_one() == 0
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_localizations")).scalar_one() == 0
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_examples")).scalar_one() == 0
                assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_example_localizations")).scalar_one() == 0
            finally:
                session.close()

    def test_import_compiled_rows_replaces_normalized_phrase_children_on_repeat_import(self) -> None:
        row = {
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [{
                    "sense_id": "phrase-1",
                    "definition": "leave the ground",
                    "part_of_speech": "verb",
                    "register": "neutral",
                    "primary_domain": "general",
                    "secondary_domains": ["general", "transport"],
                    "examples": [
                        {"sentence": "The plane took off.", "difficulty": "A1"},
                        {"sentence": "We took off early.", "difficulty": "A2"},
                    ],
                    "grammar_patterns": ["subject + take off"],
                    "usage_note": "Common for planes.",
                    "synonyms": ["depart", "set off"],
                    "antonyms": ["land"],
                    "collocations": ["take off quickly"],
                    "translations": {
                        "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。", "我们很早起飞了。"]},
                        "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó.", "Despegamos temprano."]},
                        "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة.", "أقلعنا مبكرًا."]},
                        "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou.", "Decolamos cedo."]},
                        "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。", "私たちは早く離陸した。"]},
                    },
                }],
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "phrase_kind": "phrasal_verb",
            "display_form": "take off",
            "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
            "confidence": 0.91,
        }
        added = []
        first_session = MagicMock()
        first_session.execute.return_value = _ScalarResult(None)
        first_session.add.side_effect = added.append
        first_session.flush.side_effect = lambda: None

        import_compiled_rows(
            first_session,
            [row],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        created_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        stale_sense = FakePhraseSense(
            phrase_entry_id=created_phrase.id,
            definition="stale definition",
            usage_note="stale",
            order_index=99,
            localizations=[FakePhraseSenseLocalization(phrase_sense_id=uuid.uuid4(), locale="fr", localized_definition="ancien")],
            examples=[FakePhraseSenseExample(
                phrase_sense_id=uuid.uuid4(),
                sentence="Stale sentence.",
                order_index=0,
                source="legacy",
                localizations=[FakePhraseSenseExampleLocalization(phrase_sense_example_id=uuid.uuid4(), locale="fr", translation="ancienne phrase")],
            )],
        )
        created_phrase.phrase_senses = [stale_sense]
        second_session = MagicMock()
        second_session.execute.return_value = _ScalarResult(created_phrase)
        second_session.add.side_effect = added.append
        second_session.flush.side_effect = lambda: None

        import_compiled_rows(
            second_session,
            [row],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        self.assertEqual(len(created_phrase.phrase_senses), 1)
        self.assertIsNot(created_phrase.phrase_senses[0], stale_sense)
        self.assertEqual(
            [row.locale for row in created_phrase.phrase_senses[0].localizations],
            ["ar", "es", "ja", "pt-BR", "zh-Hans"],
        )
        self.assertEqual(created_phrase.phrase_senses[0].part_of_speech, "verb")
        self.assertEqual(created_phrase.phrase_senses[0].register, "neutral")
        self.assertEqual(created_phrase.phrase_senses[0].primary_domain, "general")
        self.assertEqual(created_phrase.phrase_senses[0].secondary_domains, ["general", "transport"])
        self.assertEqual(created_phrase.phrase_senses[0].grammar_patterns, ["subject + take off"])
        self.assertEqual(created_phrase.phrase_senses[0].synonyms, ["depart", "set off"])
        self.assertEqual(created_phrase.phrase_senses[0].antonyms, ["land"])
        self.assertEqual(created_phrase.phrase_senses[0].collocations, ["take off quickly"])
        self.assertEqual(
            next(row.localized_definition for row in created_phrase.phrase_senses[0].localizations if row.locale == "zh-Hans"),
            "起飞",
        )
        self.assertEqual(
            [row.translation for row in created_phrase.phrase_senses[0].examples[0].localizations],
            ["أقلعت الطائرة.", "El avión despegó.", "飛行機が離陸した。", "O avião decolou.", "飞机起飞了。"],
        )

    def test_import_compiled_rows_clears_normalized_phrase_children_on_empty_senses_reimport(self) -> None:
        row = {
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{
                "sense_id": "phrase-1",
                "definition": "leave the ground",
                "part_of_speech": "verb",
                "examples": [
                    {"sentence": "The plane took off.", "difficulty": "A1"},
                ],
                "grammar_patterns": ["subject + take off"],
                "usage_note": "Common for planes.",
                "translations": {
                    "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。"]},
                    "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó."]},
                    "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة."]},
                    "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou."]},
                    "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。"]},
                },
            }],
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "phrase_kind": "phrasal_verb",
            "display_form": "take off",
            "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
            "confidence": 0.91,
        }
        added = []
        first_session = MagicMock()
        first_session.execute.return_value = _ScalarResult(None)
        first_session.add.side_effect = added.append
        first_session.flush.side_effect = lambda: None

        import_compiled_rows(
            first_session,
            [row],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        created_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        self.assertEqual(len(created_phrase.phrase_senses), 1)

        created_phrase.phrase_senses = [
            FakePhraseSense(
                phrase_entry_id=created_phrase.id,
                definition="stale definition",
                usage_note="stale",
                part_of_speech="noun",
                register="formal",
                primary_domain="general",
                secondary_domains=["general"],
                grammar_patterns=["stale pattern"],
                synonyms=["stale synonym"],
                antonyms=["stale antonym"],
                collocations=["stale collocation"],
                order_index=99,
                localizations=[FakePhraseSenseLocalization(phrase_sense_id=uuid.uuid4(), locale="fr", localized_definition="ancien")],
                examples=[FakePhraseSenseExample(
                    phrase_sense_id=uuid.uuid4(),
                    sentence="Stale sentence.",
                    order_index=0,
                    source="legacy",
                    localizations=[FakePhraseSenseExampleLocalization(phrase_sense_example_id=uuid.uuid4(), locale="fr", translation="ancienne phrase")],
                )],
            )
        ]

        second_session = MagicMock()
        second_session.execute.return_value = _ScalarResult(created_phrase)
        second_session.add.side_effect = added.append
        second_session.flush.side_effect = lambda: None

        import_compiled_rows(
            second_session,
            [{
                **row,
                "senses": [],
            }],
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        self.assertEqual(created_phrase.phrase_senses, [])

    def test_import_compiled_rows_prefers_richer_duplicate_phrase_examples(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ScalarResult(None)
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [{
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [{
                "sense_id": "phrase-1",
                "definition": "leave the ground",
                "part_of_speech": "verb",
                "examples": [
                    {"sentence": "The plane took off.", "difficulty": "A1"},
                    {"sentence": "The plane took off.", "difficulty": "A2"},
                ],
                "grammar_patterns": ["subject + take off"],
                "usage_note": "Common for planes.",
                "translations": {
                    "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。", "飞机已经起飞了。"]},
                    "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó.", "El avión despegó hace un momento."]},
                    "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة.", "أقلعت الطائرة قبل لحظات."]},
                    "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou.", "O avião decolou há pouco."]},
                    "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。", "飛行機はたった今離陸した。"]},
                },
            }],
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "phrase_kind": "phrasal_verb",
            "display_form": "take off",
            "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
            "confidence": 0.91,
        }]

        import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
        )

        imported_phrase = next(item for item in added if isinstance(item, FakePhraseEntry))
        imported_sense = imported_phrase.phrase_senses[0]
        imported_example = imported_sense.examples[0]
        self.assertEqual(imported_example.difficulty, "A2")
        self.assertEqual(
            [row.translation for row in imported_example.localizations],
            ["أقلعت الطائرة قبل لحظات.", "El avión despegó hace un momento.", "飛行機はたった今離陸した。", "O avião decolou há pouco.", "飞机已经起飞了。"],
        )

    def test_import_compiled_rows_avoids_individual_child_adds_for_new_mapped_phrase_graphs(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ScalarResult(None)
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        row = {
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "display_form": "take off",
            "phrase_kind": "phrasal_verb",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "senses": [{
                "sense_id": "phrase-1",
                "definition": "leave the ground",
                "part_of_speech": "verb",
                "examples": [{"sentence": "The plane took off.", "difficulty": "A1"}],
                "translations": {
                    "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。"]},
                    "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó."]},
                    "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة."]},
                    "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou."]},
                    "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した。"]},
                },
            }],
        }

        real_mapped_phrase_models = {
            FakePhraseEntry,
            FakePhraseSense,
            FakePhraseSenseLocalization,
            FakePhraseSenseExample,
            FakePhraseSenseExampleLocalization,
        }

        with patch(
            "tools.lexicon.import_db._is_real_mapped_model",
            side_effect=lambda model: model in real_mapped_phrase_models,
        ), patch("tools.lexicon.import_db._preload_existing_by_normalized_form", return_value={}), patch(
            "tools.lexicon.import_db._find_existing_by_normalized_form",
            return_value=None,
        ):
            import_compiled_rows(
                session,
                [row],
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260328",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                phrase_model=FakePhraseEntry,
                phrase_sense_model=FakePhraseSense,
                phrase_sense_localization_model=FakePhraseSenseLocalization,
                phrase_sense_example_model=FakePhraseSenseExample,
                phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
            )

        self.assertEqual([type(item) for item in added], [FakePhraseEntry])
        self.assertEqual(len(added[0].phrase_senses), 1)
        self.assertEqual(len(added[0].phrase_senses[0].examples), 1)
        self.assertEqual(len(added[0].phrase_senses[0].localizations), 5)
        self.assertEqual(len(added[0].phrase_senses[0].examples[0].localizations), 5)

    def test_import_skip_mode_skips_existing_phrase(self) -> None:
        existing_phrase = FakePhraseEntry(
            phrase_text="take off",
            normalized_form="take off",
            phrase_kind="phrasal_verb",
            language="en",
            source_type="snapshot_reviewed_approved",
            source_reference="snapshot-20260320",
        )
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(existing_phrase)]

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "display_form": "take off",
                "phrase_kind": "phrasal_verb",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "senses": [],
            }
        ]

        import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260320",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            phrase_model=FakePhraseEntry,
            phrase_sense_model=FakePhraseSense,
            phrase_sense_localization_model=FakePhraseSenseLocalization,
            phrase_sense_example_model=FakePhraseSenseExample,
            phrase_sense_example_localization_model=FakePhraseSenseExampleLocalization,
            conflict_mode="skip",
        )

    def test_import_upsert_mode_reimports_existing_phrase_without_duplicate_order_index_on_real_sqlalchemy_models(self) -> None:
        models = _load_real_models()
        phrase_row = {
            "schema_version": "1.1.0",
            "entry_id": "ph_take_off",
            "entry_type": "phrase",
            "normalized_form": "take off",
            "source_provenance": [{"source": "phrase_seed"}],
            "entity_category": "general",
            "word": "take off",
            "display_form": "take off",
            "phrase_kind": "phrasal_verb",
            "part_of_speech": ["phrasal_verb"],
            "cefr_level": "B1",
            "frequency_rank": 0,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "confusable_words": [],
            "generated_at": "2026-03-20T00:00:00Z",
            "senses": [{
                "sense_id": "phrase-1",
                "definition": "leave the ground",
                "part_of_speech": "verb",
                "examples": [{"sentence": "The plane took off.", "difficulty": "A1"}],
                "translations": {
                    "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。"]},
                    "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó."]},
                    "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة."]},
                    "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou."]},
                    "ja": {"definition": "離陸する", "usage_note": "よくある用法", "examples": ["飛行機が離陸した."]},
                },
            }],
        }

        with _temporary_postgres_lexicon_connection() as connection:
            _create_real_lexicon_tables(connection, models)
            session = Session(bind=connection, expire_on_commit=False)
            try:
                import_kwargs = dict(
                    source_type="snapshot_reviewed_approved",
                    source_reference="snapshot-20260320",
                    language="en",
                    phrase_model=models["PhraseEntry"],
                    phrase_sense_model=models["PhraseSense"],
                    phrase_sense_localization_model=models["PhraseSenseLocalization"],
                    phrase_sense_example_model=models["PhraseSenseExample"],
                    phrase_sense_example_localization_model=models["PhraseSenseExampleLocalization"],
                    rebuild_learner_catalog=False,
                    conflict_mode="upsert",
                )

                import_compiled_rows(session, [phrase_row], **import_kwargs)
                session.flush()

                import_compiled_rows(session, [phrase_row], **import_kwargs)
                session.flush()
                phrase = session.query(models["PhraseEntry"]).one()
                self.assertEqual(len(phrase.phrase_senses), 1)
            finally:
                session.close()

    def test_import_compiled_rows_rejects_phrase_rows_missing_translation_examples(self) -> None:
        session = MagicMock()
        session.execute.return_value = _ScalarResult(None)

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [{
                    "sense_id": "phrase-1",
                    "definition": "leave the ground",
                    "part_of_speech": "verb",
                    "examples": [{"sentence": "The plane took off.", "difficulty": "A1"}],
                    "grammar_patterns": ["subject + take off"],
                    "usage_note": "Common for planes.",
                    "translations": {
                        "zh-Hans": {"definition": "起飞", "usage_note": "常见用法", "examples": ["飞机起飞了。"]},
                        "es": {"definition": "despegar", "usage_note": "uso común", "examples": ["El avión despegó."]},
                        "ar": {"definition": "يقلع", "usage_note": "استخدام شائع", "examples": ["أقلعت الطائرة."]},
                        "pt-BR": {"definition": "decolar", "usage_note": "uso comum", "examples": ["O avião decolou."]},
                        "ja": {"definition": "離陸する", "usage_note": "よくある用法"},
                    },
                }],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
                "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
                "confidence": 0.91,
            },
        ]

        with self.assertRaisesRegex(RuntimeError, "translations\\.ja\\.examples must be a non-empty list"):
            import_compiled_rows(
                session,
                rows,
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260320",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                phrase_model=FakePhraseEntry,
            )

    def test_load_compiled_rows_reads_family_directory_and_dry_run_counts(self) -> None:
        from tools.lexicon.import_db import load_compiled_rows, summarize_compiled_rows, summarize_compiled_rows_from_path

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "words.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
            }) + "\n", encoding="utf-8")
            (root / "phrases.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "ph_take_off",
                "entry_type": "phrase",
                "normalized_form": "take off",
                "source_provenance": [{"source": "phrase_seed"}],
                "entity_category": "general",
                "word": "take off",
                "part_of_speech": ["phrasal_verb"],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
            }) + "\n", encoding="utf-8")
            (root / "references.enriched.jsonl").write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "rf_australia",
                "entry_type": "reference",
                "normalized_form": "australia",
                "source_provenance": [{"source": "reference_seed"}],
                "entity_category": "general",
                "word": "Australia",
                "part_of_speech": [],
                "cefr_level": "B1",
                "frequency_rank": 0,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "reference_type": "country",
                "display_form": "Australia",
                "translation_mode": "localized",
                "brief_description": "A country in the Southern Hemisphere.",
                "pronunciation": "/ɔˈstreɪliə/",
                "localized_display_form": {"es": "Australia"},
                "localized_brief_description": {"es": "País del hemisferio sur."},
                "learner_tip": "Stress is on STRAY.",
                "localizations": [{"locale": "es", "display_form": "Australia", "translation_mode": "localized"}],
            }) + "\n", encoding="utf-8")

            rows = load_compiled_rows(root)
            counts = summarize_compiled_rows(rows)
            streaming_counts = summarize_compiled_rows_from_path(root)

            self.assertEqual(counts["row_count"], 3)
            self.assertEqual(counts["word_count"], 1)
            self.assertEqual(counts["phrase_count"], 1)
            self.assertEqual(counts["reference_count"], 1)
            self.assertEqual(streaming_counts, counts)

    def test_import_skips_existing_child_loaders_for_brand_new_rows(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(None)]
        session.add.side_effect = lambda _: None
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "forms": {},
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "pos": "noun",
                        "examples": [{"sentence": "I do not have time today.", "difficulty": "A1"}],
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "examples": ["Eu não tenho tempo hoje."],
                            }
                        },
                        "synonyms": ["duration"],
                    }
                ],
            }
        ]

        with patch("tools.lexicon.import_db._load_existing_meanings") as mocked_meanings, \
             patch("tools.lexicon.import_db._find_existing_enrichment_job") as mocked_jobs, \
             patch("tools.lexicon.import_db._load_existing_examples") as mocked_examples, \
             patch("tools.lexicon.import_db._load_existing_translations") as mocked_translations, \
             patch("tools.lexicon.import_db._load_existing_relations") as mocked_relations:
            import_compiled_rows(
                session,
                rows,
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260324",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                meaning_example_model=FakeMeaningExample,
                translation_model=FakeTranslation,
                translation_example_model=FakeTranslationExample,
                word_relation_model=FakeWordRelation,
                lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
                lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
            )

        mocked_meanings.assert_not_called()
        mocked_jobs.assert_not_called()
        mocked_examples.assert_not_called()
        mocked_translations.assert_not_called()
        mocked_relations.assert_not_called()

    def test_import_compiled_rows_avoids_individual_child_adds_for_new_mapped_word_graphs(self) -> None:
        session = MagicMock()
        added = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "part_of_speech": ["noun"],
                "cefr_level": "A1",
                "frequency_rank": 10,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "confusable_words": [],
                "generated_at": "2026-03-24T00:00:00Z",
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "pos": "noun",
                        "examples": [{"sentence": "I do not have time today.", "difficulty": "A1"}],
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "examples": ["Eu não tenho tempo hoje."],
                            }
                        },
                        "synonyms": ["duration"],
                        "confidence": 0.8,
                        "generated_at": "2026-03-24T00:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                    }
                ],
            }
        ]

        real_mapped_word_models = {
            FakeWord,
            FakeMeaning,
            FakeMeaningMetadata,
            FakeMeaningExample,
            FakeTranslation,
            FakeTranslationExample,
            FakeWordRelation,
            FakeLexiconEnrichmentJob,
            FakeLexiconEnrichmentRun,
            FakeWordConfusable,
            FakeWordForm,
            FakeWordPartOfSpeech,
        }

        with patch(
            "tools.lexicon.import_db._is_real_mapped_model",
            side_effect=lambda model: model in real_mapped_word_models,
        ), patch("tools.lexicon.import_db._preload_existing_words", return_value={}), patch(
            "tools.lexicon.import_db._find_existing_word",
            return_value=None,
        ):
            import_compiled_rows(
                session,
                rows,
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260324",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                meaning_metadata_model=FakeMeaningMetadata,
                meaning_example_model=FakeMeaningExample,
                translation_model=FakeTranslation,
                translation_example_model=FakeTranslationExample,
                word_relation_model=FakeWordRelation,
                lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
                lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
                word_confusable_model=FakeWordConfusable,
                word_form_model=FakeWordForm,
                word_part_of_speech_model=FakeWordPartOfSpeech,
            )

        self.assertEqual([type(item) for item in added], [FakeWord, FakeMeaningExample])

    def test_import_compiled_rows_bulk_child_insert_for_new_mapped_word_graphs(self) -> None:
        session = MagicMock()
        added = []
        bulk_calls: list[tuple[type, list[dict[str, object]]]] = []
        session.add.side_effect = added.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "word",
                "word": "time",
                "language": "en",
                "part_of_speech": ["noun"],
                "cefr_level": "A1",
                "frequency_rank": 10,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "confusable_words": [],
                "generated_at": "2026-03-24T00:00:00Z",
                "senses": [
                    {
                        "sense_id": "sense-001",
                        "definition": "the thing measured in minutes and hours",
                        "pos": "noun",
                        "examples": [{"sentence": "I do not have time today.", "difficulty": "A1"}],
                        "translations": {
                            "pt-BR": {
                                "definition": "tempo",
                                "examples": ["Eu não tenho tempo hoje."],
                            }
                        },
                        "synonyms": ["duration"],
                        "confidence": 0.8,
                        "generated_at": "2026-03-24T00:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                    }
                ],
            }
        ]

        real_mapped_word_models = {
            FakeWord,
            FakeMeaning,
            FakeMeaningMetadata,
            FakeMeaningExample,
            FakeTranslation,
            FakeTranslationExample,
            FakeWordRelation,
            FakeLexiconEnrichmentJob,
            FakeLexiconEnrichmentRun,
            FakeWordConfusable,
            FakeWordForm,
            FakeWordPartOfSpeech,
        }

        def _record_bulk_insert(_session, model, rows):
            bulk_calls.append((model, list(rows)))

        with patch(
            "tools.lexicon.import_db._is_real_mapped_model",
            side_effect=lambda model: model in real_mapped_word_models,
        ), patch("tools.lexicon.import_db._preload_existing_words", return_value={}), patch(
            "tools.lexicon.import_db._find_existing_word",
            return_value=None,
        ), patch(
            "tools.lexicon.import_db._supports_bulk_insert_model",
            side_effect=lambda _session, model: model in {FakeMeaningExample, FakeTranslationExample, FakeWordRelation},
            create=True,
        ), patch(
            "tools.lexicon.import_db._bulk_insert_mapped_rows",
            side_effect=_record_bulk_insert,
        ):
            import_compiled_rows(
                session,
                rows,
                source_type="lexicon_snapshot",
                source_reference="snapshot-20260324",
                language="en",
                word_model=FakeWord,
                meaning_model=FakeMeaning,
                meaning_metadata_model=FakeMeaningMetadata,
                meaning_example_model=FakeMeaningExample,
                translation_model=FakeTranslation,
                translation_example_model=FakeTranslationExample,
                word_relation_model=FakeWordRelation,
                lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
                lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
                word_confusable_model=FakeWordConfusable,
                word_form_model=FakeWordForm,
                word_part_of_speech_model=FakeWordPartOfSpeech,
            )

        self.assertEqual([type(item) for item in added], [FakeWord])
        self.assertEqual(
            [(model, len(rows)) for model, rows in bulk_calls],
            [
                (FakeMeaningExample, 1),
                (FakeTranslationExample, 1),
                (FakeWordRelation, 1),
            ],
        )

    def test_run_import_file_streams_input_and_commits_per_chunk(self) -> None:
        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = iter(
            [
                {"entry_type": "word", "word": "alpha"},
                {"entry_type": "word", "word": "beta"},
                {"entry_type": "word", "word": "gamma"},
            ]
        )
        import_summaries = [
            ImportSummary(created_words=2),
            ImportSummary(created_words=1),
        ]
        progress_calls: list[tuple[str, int, int]] = []

        with patch("tools.lexicon.import_db.iter_compiled_rows", return_value=rows), \
             patch("tools.lexicon.import_db.count_compiled_rows", return_value=3), \
             patch("tools.lexicon.import_db.import_compiled_rows", side_effect=import_summaries) as mocked_import, \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                commit_every_rows=2,
                progress_callback=lambda **kwargs: progress_calls.append(
                    (str(kwargs["row"].get("word")), int(kwargs["completed_rows"]), int(kwargs["total_rows"]))
                ),
            )

        self.assertEqual(summary["created_words"], 3)
        self.assertEqual(fake_session.commit.call_count, 3)
        self.assertEqual([len(call.args[1]) for call in mocked_import.call_args_list], [2, 1])
        self.assertEqual([call.kwargs["source_reference"] for call in mocked_import.call_args_list], ["fake-fixture", "fake-fixture"])
        self.assertEqual(progress_calls, [])

    def test_run_import_file_rebuilds_learner_catalog_once_after_all_batches(self) -> None:
        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = iter(
            [
                {"entry_type": "word", "word": "alpha"},
                {"entry_type": "word", "word": "beta"},
                {"entry_type": "word", "word": "gamma"},
            ]
        )

        with patch("tools.lexicon.import_db.iter_compiled_rows", return_value=rows), \
             patch("tools.lexicon.import_db.count_compiled_rows", return_value=3), \
             patch(
                 "tools.lexicon.import_db.import_compiled_rows",
                 side_effect=[ImportSummary(created_words=2), ImportSummary(created_words=1)],
             ) as mocked_import, \
             patch("tools.lexicon.import_db._rebuild_learner_catalog_projection") as mocked_rebuild_projection, \
             patch(
                 "tools.lexicon.import_db._default_models",
                 return_value=(
                     FakeWord,
                     FakeMeaning,
                     FakeMeaningMetadata,
                     FakeMeaningExample,
                     FakeWordRelation,
                     FakeLexiconEnrichmentJob,
                     FakeLexiconEnrichmentRun,
                     FakeTranslation,
                     FakeTranslationExample,
                     FakeWordConfusable,
                     FakeWordForm,
                     FakeWordPartOfSpeech,
                     FakeLearnerCatalogEntry,
                 ),
             ), \
             patch("tools.lexicon.import_db._default_phrase_models", return_value=(FakePhraseEntry, FakePhraseSense, FakePhraseSenseLocalization, FakePhraseSenseExample, FakePhraseSenseExampleLocalization)), \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                commit_every_rows=2,
            )

        self.assertEqual([call.kwargs["rebuild_learner_catalog"] for call in mocked_import.call_args_list], [False, False])
        mocked_rebuild_projection.assert_called_once()
        self.assertEqual(fake_session.commit.call_count, 3)

    def test_run_import_file_skip_only_does_not_rebuild_learner_catalog(self) -> None:
        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = iter([{"entry_type": "word", "word": "alpha"}])

        with patch("tools.lexicon.import_db.iter_compiled_rows", return_value=rows), \
             patch("tools.lexicon.import_db.count_compiled_rows", return_value=1), \
             patch(
                 "tools.lexicon.import_db.import_compiled_rows",
                 return_value=ImportSummary(skipped_words=1),
             ), \
             patch("tools.lexicon.import_db._rebuild_learner_catalog_projection") as mocked_rebuild_projection, \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                on_conflict="skip",
            )

        self.assertEqual(summary["skipped_words"], 1)
        mocked_rebuild_projection.assert_not_called()
        self.assertEqual(fake_session.commit.call_count, 1)

    def test_run_import_file_continue_mode_falls_back_to_row_level_import(self) -> None:
        from sqlalchemy.exc import IntegrityError

        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = [
            {"entry_type": "word", "word": "alpha"},
            {"entry_type": "word", "word": "beta"},
            {"entry_type": "word", "word": "gamma"},
        ]

        def fake_import(_session, batch, **kwargs):
            if len(batch) > 1:
                raise IntegrityError("insert", {}, Exception("bad row in batch"))
            if str(batch[0].get("word")) == "beta":
                raise ValueError("beta is invalid")
            return ImportSummary(created_words=1)

        error_samples: list[dict[str, Any]] = []
        with patch("tools.lexicon.import_db.import_compiled_rows", side_effect=fake_import), \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                rows=rows,
                commit_every_rows=3,
                error_mode="continue",
                error_samples_sink=error_samples,
            )

        self.assertEqual(summary["created_words"], 2)
        self.assertEqual(summary["failed_rows"], 1)
        self.assertEqual(error_samples, [{"entry": "beta", "error": "beta is invalid"}])
        self.assertGreaterEqual(fake_session.rollback.call_count, 2)

    def test_run_import_file_continue_mode_reraises_non_row_level_errors(self) -> None:
        from sqlalchemy.exc import OperationalError

        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        rows = [{"entry_type": "word", "word": "alpha"}]

        with patch(
            "tools.lexicon.import_db.import_compiled_rows",
            side_effect=OperationalError("select 1", {}, Exception("db down")),
        ), \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            with self.assertRaises(OperationalError):
                run_import_file(
                    "/tmp/fake.jsonl",
                    source_type="repo_fixture",
                    source_reference="fake-fixture",
                    rows=rows,
                    error_mode="continue",
                )

    def test_run_import_file_dry_run_uses_preflight_without_write_path(self) -> None:
        rows = [
            {
                "schema_version": "1.1.0",
                "entry_id": "word:alpha",
                "entry_type": "word",
                "normalized_form": "alpha",
                "source_provenance": [{"source": "snapshot"}],
                "word": "alpha",
                "senses": [],
            }
        ]

        with patch("tools.lexicon.import_db.import_compiled_rows", side_effect=AssertionError("write path should not run")), \
             patch("sqlalchemy.engine.create.create_engine", return_value=MagicMock()), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                rows=rows,
                dry_run=True,
            )

        self.assertEqual(summary["row_count"], 1)
        self.assertEqual(summary["word_count"], 1)
        self.assertEqual(summary["failed_rows"], 0)
        self.assertTrue(summary["dry_run"])

    def test_run_import_file_dry_run_returns_preflight_errors_without_raising(self) -> None:
        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "fuss over",
                "display_form": "fuss over",
                "normalized_form": "fuss over",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "source_provenance": [{"source": "snapshot"}],
                "senses": [
                    {
                        "sense_id": "phrase-1",
                        "definition": "care too much",
                        "part_of_speech": "verb",
                        "examples": [{"sentence": "Do not fuss over small things.", "difficulty": "B2"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "为...过分操心",
                                "usage_note": "",
                                "examples": ["不要为小事过分操心。"],
                            }
                        },
                    }
                ],
            }
        ]

        error_samples: list[dict[str, Any]] = []
        with patch("tools.lexicon.import_db.import_compiled_rows", side_effect=AssertionError("write path should not run")), \
             patch("sqlalchemy.engine.create.create_engine", return_value=MagicMock()), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                rows=rows,
                dry_run=True,
                error_samples_sink=error_samples,
            )

        self.assertEqual(summary["failed_rows"], 1)
        self.assertTrue(summary["dry_run"])
        self.assertEqual(len(error_samples), 1)
        self.assertEqual(error_samples[0]["entry"], "fuss over")
        self.assertIn("usage_note must be a non-empty string", error_samples[0]["error"])

    def test_run_import_file_dry_run_counts_failed_rows_once_per_row(self) -> None:
        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "fuss over",
                "display_form": "fuss over",
                "normalized_form": "fuss over",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "source_provenance": [{"source": "snapshot"}],
                "senses": [
                    {
                        "sense_id": "phrase-1",
                        "definition": "care too much",
                        "part_of_speech": "verb",
                        "examples": [],
                        "translations": {
                            "zh-Hans": {
                                "definition": "为...过分操心",
                                "usage_note": "",
                                "examples": [],
                            }
                        },
                    }
                ],
            }
        ]

        with patch("tools.lexicon.import_db.import_compiled_rows", side_effect=AssertionError("write path should not run")), \
             patch("sqlalchemy.engine.create.create_engine", return_value=MagicMock()), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                rows=rows,
                dry_run=True,
            )

        self.assertEqual(summary["row_count"], 1)
        self.assertEqual(summary["failed_rows"], 1)

    def test_run_import_file_raises_preflight_error_before_write_path(self) -> None:
        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "fuss over",
                "display_form": "fuss over",
                "normalized_form": "fuss over",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "source_provenance": [{"source": "snapshot"}],
                "senses": [
                    {
                        "sense_id": "phrase-1",
                        "definition": "care too much",
                        "part_of_speech": "verb",
                        "examples": [{"sentence": "Do not fuss over small things.", "difficulty": "B2"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "为...过分操心",
                                "usage_note": "",
                                "examples": ["不要为小事过分操心。"],
                            }
                        },
                    }
                ],
            }
        ]

        with patch("tools.lexicon.import_db.import_compiled_rows", side_effect=AssertionError("write path should not run")), \
             patch("sqlalchemy.engine.create.create_engine", return_value=MagicMock()), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            with self.assertRaisesRegex(RuntimeError, "usage_note must be a non-empty string"):
                run_import_file(
                    "/tmp/fake.jsonl",
                    source_type="repo_fixture",
                    source_reference="fake-fixture",
                    rows=rows,
                )

    def test_run_import_file_reuses_single_preflight_scan_before_write_path(self) -> None:
        rows = [
            {
                "schema_version": "1.1.0",
                "entry_type": "phrase",
                "word": "fuss over",
                "display_form": "fuss over",
                "normalized_form": "fuss over",
                "language": "en",
                "source_type": "db_export",
                "source_reference": "phrase-fixture",
                "source_provenance": [{"source": "snapshot"}],
                "senses": [
                    {
                        "sense_id": "phrase-1",
                        "definition": "care too much",
                        "part_of_speech": "verb",
                        "examples": [{"sentence": "Do not fuss over small things.", "difficulty": "B2"}],
                        "translations": {
                            "zh-Hans": {
                                "definition": "为...过分操心",
                                "usage_note": "",
                                "examples": ["不要为小事过分操心。"],
                            }
                        },
                    }
                ],
            }
        ]

        with patch("tools.lexicon.import_db._preflight_validate_compiled_rows", wraps=sys.modules["tools.lexicon.import_db"]._preflight_validate_compiled_rows) as preflight_validate, \
             patch("tools.lexicon.import_db.import_compiled_rows", side_effect=AssertionError("write path should not run")), \
             patch("sqlalchemy.engine.create.create_engine", return_value=MagicMock()), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            with self.assertRaisesRegex(RuntimeError, "usage_note must be a non-empty string"):
                run_import_file(
                    "/tmp/fake.jsonl",
                    source_type="repo_fixture",
                    source_reference="fake-fixture",
                    rows=rows,
                )

        self.assertEqual(preflight_validate.call_count, 1)

    def test_run_import_file_reports_skip_progress_for_existing_word(self) -> None:
        session = MagicMock()
        existing_word = type("Word", (), {"word": "bank", "language": "en"})()
        progress_updates: list[tuple[str | None, int, int]] = []
        rows = [{"word": "bank", "senses": []}]

        with patch("tools.lexicon.import_db._find_existing_word", return_value=existing_word), \
             patch("tools.lexicon.import_db._preload_existing_words", return_value={("bank", "en"): existing_word}), \
             patch("tools.lexicon.import_db._default_models", return_value=(MagicMock(), MagicMock(), None, None, None, None, None, None, None, None, None, None, None)):
            summary = import_compiled_rows(
                session,
                rows,
                source_type="repo_fixture",
                source_reference="fixture",
                on_conflict="skip",
                progress_callback=lambda row, completed_rows, total_rows: progress_updates.append(
                    (row.get("_progress_label"), completed_rows, total_rows),
                ),
                rebuild_learner_catalog=False,
            )

        self.assertEqual(summary.skipped_words, 1)
        self.assertEqual(progress_updates, [("Skipping existing word: bank", 1, 1)])

    def test_run_import_file_staging_mode_delegates_to_staging_import(self) -> None:
        with patch("tools.lexicon.staging_import.run_staging_import_file", return_value={"created_words": 9}) as mocked_staging:
            summary = run_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
                import_mode="staging",
            )

        self.assertEqual(summary["created_words"], 9)
        mocked_staging.assert_called_once_with(
            "/tmp/fake.jsonl",
            source_type="repo_fixture",
            source_reference="fake-fixture",
            language="en",
            rows=None,
            commit_every_rows=250,
            progress_callback=None,
            on_conflict="upsert",
        )


    def test_import_reuses_job_and_run_and_replaces_examples_and_relations(self) -> None:
        existing_word = FakeWord(word="run", language="en", frequency_rank=50)
        existing_meaning = FakeMeaning(
            word_id=existing_word.id,
            definition="old definition",
            part_of_speech="verb",
            example_sentence="Old example.",
            order_index=0,
            source="lexicon_snapshot",
            source_reference="snapshot-20260307:sn_lx_run_run_v_01_abcd1234",
        )
        existing_job = FakeLexiconEnrichmentJob(word_id=existing_word.id, status="completed")
        existing_run = FakeLexiconEnrichmentRun(
            enrichment_job_id=existing_job.id,
            generator_provider="lexicon_snapshot",
            generator_model="gpt-5.1",
            prompt_version="v1",
            prompt_hash="ignored-in-fake-tests",
            verdict="imported",
            confidence=0.5,
        )
        old_example = FakeMeaningExample(
            meaning_id=existing_meaning.id,
            sentence="Old example.",
            order_index=0,
            source="lexicon_snapshot",
            confidence=0.5,
            enrichment_run_id=existing_run.id,
        )
        old_relation = FakeWordRelation(
            word_id=existing_word.id,
            meaning_id=existing_meaning.id,
            relation_type="synonym",
            related_word="sprint",
            source="lexicon_snapshot",
            confidence=0.5,
            enrichment_run_id=existing_run.id,
        )

        session = MagicMock()
        session.execute.side_effect = [
            _ScalarResult(existing_word),
            _ListResult([existing_meaning]),
            _ScalarResult(existing_job),
            _ScalarResult(existing_run),
            _ListResult([old_example]),
            _ListResult([old_relation]),
        ]
        added = []
        deleted = []
        session.add.side_effect = added.append
        session.delete.side_effect = deleted.append
        session.flush.side_effect = lambda: None

        rows = [
            {
                "schema_version": "1.1.0",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_run_v_01_abcd1234",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "to move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": ["jog"],
                        "antonyms": ["walk"],
                        "collocations": [],
                        "grammar_patterns": ["run + adverb"],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_run_v_01_abcd1234_v1",
                        "generation_run_id": "run-123",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.91,
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.updated_words, 1)
        self.assertEqual(summary.updated_meanings, 1)
        self.assertEqual(summary.reused_enrichment_jobs, 1)
        self.assertEqual(summary.reused_enrichment_runs, 1)
        self.assertEqual(summary.deleted_examples, 1)
        self.assertEqual(summary.deleted_relations, 1)
        self.assertEqual(summary.created_examples, 1)
        self.assertEqual(summary.created_relations, 2)
        self.assertEqual(existing_word.cefr_level, "A1")
        self.assertEqual(existing_meaning.wn_synset_id, "run.v.01")
        self.assertEqual(existing_meaning.primary_domain, "general")
        self.assertEqual(existing_meaning.register_label, "neutral")
        self.assertEqual(existing_meaning.usage_note, "Common everyday verb.")
        self.assertEqual(deleted, [old_example, old_relation])
        self.assertEqual(session.flush.call_count, 2)
        self.assertEqual(
            [(item.relation_type, item.related_word) for item in added if isinstance(item, FakeWordRelation)],
            [("synonym", "jog"), ("antonym", "walk")],
        )
        self.assertEqual([item.difficulty for item in added if isinstance(item, FakeMeaningExample)], ["A1"])

    def test_import_creates_new_enrichment_job_without_counting_it_as_reused(self) -> None:
        session = MagicMock()
        session.execute.side_effect = [_ScalarResult(None)]
        session.flush.side_effect = lambda: None
        rows = [
            {
                "schema_version": "1.1.0",
                "word": "fresh",
                "part_of_speech": ["adjective"],
                "cefr_level": "A1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_fresh_adj_01_abcd1234",
                        "wn_synset_id": "fresh.a.01",
                        "pos": "adjective",
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "new or recently made",
                        "examples": [],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": None,
                        "enrichment_id": "en_sn_lx_fresh_adj_01_abcd1234_v1",
                        "generation_run_id": "run-fresh-123",
                        "model_name": "gpt-5.1",
                        "prompt_version": "v1",
                        "confidence": 0.91,
                        "generated_at": "2026-03-07T00:00:00Z",
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-03-07T00:00:00Z",
            }
        ]

        summary = import_compiled_rows(
            session,
            rows,
            source_type="lexicon_snapshot",
            source_reference="snapshot-20260307",
            language="en",
            word_model=FakeWord,
            meaning_model=FakeMeaning,
            meaning_example_model=FakeMeaningExample,
            word_relation_model=FakeWordRelation,
            lexicon_enrichment_job_model=FakeLexiconEnrichmentJob,
            lexicon_enrichment_run_model=FakeLexiconEnrichmentRun,
        )

        self.assertEqual(summary.created_enrichment_jobs, 1)
        self.assertEqual(summary.reused_enrichment_jobs, 0)


if __name__ == "__main__":
    unittest.main()
