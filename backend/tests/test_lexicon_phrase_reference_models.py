import os
import socket
import subprocess
import time
from datetime import datetime, timezone
from contextlib import contextmanager
from importlib import util
import uuid
from pathlib import Path

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, DateTime, MetaData, String, Table, UniqueConstraint, create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.models.phrase_entry import PhraseEntry
from app.models.phrase_sense import PhraseSense
from app.models.phrase_sense_example import PhraseSenseExample
from app.models.phrase_sense_example_localization import PhraseSenseExampleLocalization
from app.models.phrase_sense_localization import PhraseSenseLocalization
from app.models.reference_entry import ReferenceEntry
from app.models.reference_localization import ReferenceLocalization
from app.models.schema_names import LEXICON_SCHEMA


def _load_phrase_migration():
    migration_path = Path(__file__).resolve().parents[1] / "alembic" / "versions" / "019_normalize_phrase_learner_fields.py"
    spec = util.spec_from_file_location("migration_019_normalize_phrase_learner_fields", migration_path)
    assert spec is not None and spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _database_url_sync() -> str:
    if os.environ.get("LEXICON_TEST_USE_EXISTING_POSTGRES") == "1":
        return os.environ.get(
            "LEXICON_TEST_POSTGRES_URL",
            os.environ.get(
                "DATABASE_URL_SYNC",
                os.environ.get("DATABASE_URL", "postgresql://vocabapp:devpassword@localhost:5432/vocabapp_dev"),
            ),
        )
    return ""


def _reset_lexicon_schema(connection) -> None:
    connection.execute(text("DROP SCHEMA IF EXISTS lexicon CASCADE"))
    connection.execute(text("CREATE SCHEMA lexicon"))


def _create_phrase_entries_source_table(connection) -> Table:
    phrase_entries = Table(
        "phrase_entries",
        MetaData(),
        Column("id", UUID(as_uuid=True), primary_key=True),
        Column("compiled_payload", JSONB, nullable=True),
        Column("generated_at", DateTime(timezone=True), nullable=True),
        Column("created_at", DateTime(timezone=True), nullable=True),
        Column("source_type", String(length=50), nullable=True),
        schema="lexicon",
    )
    phrase_entries.create(connection)
    return phrase_entries


@contextmanager
def _temporary_postgres_lexicon_connection():
    database_url = _database_url_sync()
    engine = None
    container_name = None
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
                _reset_lexicon_schema(connection)
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
        _reset_lexicon_schema(connection)
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


class _BackfillResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _RecordingConnection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _BackfillResult(self.rows)


class TestPhraseEntryModel:
    def test_defaults_and_fields(self) -> None:
        entry = PhraseEntry(
            phrase_text="take off",
            normalized_form="take off",
            phrase_kind="phrasal_verb",
            compiled_payload={"entry_type": "phrase", "entry_id": "ph_take_off"},
            seed_metadata={"raw_reviewed_as": "phrasal verb"},
            confidence_score=0.91,
        )
        assert entry.phrase_text == "take off"
        assert entry.normalized_form == "take off"
        assert entry.phrase_kind == "phrasal_verb"
        assert entry.compiled_payload["entry_id"] == "ph_take_off"
        assert entry.seed_metadata["raw_reviewed_as"] == "phrasal verb"
        assert entry.confidence_score == 0.91
        assert entry.language == "en"
        assert entry.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseEntry.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseEntry.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_entry_normalized_language"
            and {column.name for column in constraint.columns} == {"normalized_form", "language"}
            for constraint in constraints
        )


class TestPhraseSenseModel:
    def test_defaults_and_fields(self) -> None:
        phrase_entry_id = uuid.uuid4()
        sense = PhraseSense(
            phrase_entry_id=phrase_entry_id,
            definition="to depart by plane",
            usage_note="Used for travel.",
            part_of_speech="phrasal_verb",
            register="neutral",
            primary_domain="general",
            secondary_domains=["travel"],
            grammar_patterns=["take off + adverb"],
            synonyms=["depart"],
            antonyms=["land"],
            collocations=["take off quickly"],
            order_index=1,
        )
        assert sense.phrase_entry_id == phrase_entry_id
        assert sense.definition == "to depart by plane"
        assert sense.usage_note == "Used for travel."
        assert sense.part_of_speech == "phrasal_verb"
        assert sense.register == "neutral"
        assert sense.primary_domain == "general"
        assert sense.secondary_domains == ["travel"]
        assert sense.grammar_patterns == ["take off + adverb"]
        assert sense.synonyms == ["depart"]
        assert sense.antonyms == ["land"]
        assert sense.collocations == ["take off quickly"]
        assert sense.order_index == 1
        assert sense.localizations == []

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseSense.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseSense.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_sense_entry_order"
            and {column.name for column in constraint.columns} == {"phrase_entry_id", "order_index"}
            for constraint in constraints
        )


class TestPhraseSenseLocalizationModel:
    def test_defaults_and_fields(self) -> None:
        phrase_sense_id = uuid.uuid4()
        localization = PhraseSenseLocalization(
            phrase_sense_id=phrase_sense_id,
            locale="es",
            localized_definition="salir en avión",
            localized_usage_note="Se usa para viajes.",
        )
        assert localization.phrase_sense_id == phrase_sense_id
        assert localization.locale == "es"
        assert localization.localized_definition == "salir en avión"
        assert localization.localized_usage_note == "Se usa para viajes."
        assert localization.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseSenseLocalization.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseSenseLocalization.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_sense_localization_sense_locale"
            and {column.name for column in constraint.columns} == {"phrase_sense_id", "locale"}
            for constraint in constraints
        )


class TestPhraseSenseExampleModel:
    def test_defaults_and_fields(self) -> None:
        phrase_sense_id = uuid.uuid4()
        example = PhraseSenseExample(
            phrase_sense_id=phrase_sense_id,
            sentence="The plane takes off at dawn.",
            order_index=2,
            source="lexicon_snapshot",
        )
        assert example.phrase_sense_id == phrase_sense_id
        assert example.sentence == "The plane takes off at dawn."
        assert example.order_index == 2
        assert example.source == "lexicon_snapshot"
        assert example.localizations == []

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseSenseExample.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseSenseExample.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_sense_example_sense_sentence"
            and {column.name for column in constraint.columns} == {"phrase_sense_id", "sentence"}
            for constraint in constraints
        )


class TestPhraseSenseExampleLocalizationModel:
    def test_defaults_and_fields(self) -> None:
        phrase_sense_example_id = uuid.uuid4()
        localization = PhraseSenseExampleLocalization(
            phrase_sense_example_id=phrase_sense_example_id,
            locale="ja",
            translation="飛行機が離陸した。",
        )
        assert localization.phrase_sense_example_id == phrase_sense_example_id
        assert localization.locale == "ja"
        assert localization.translation == "飛行機が離陸した。"
        assert localization.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in PhraseSenseExampleLocalization.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert PhraseSenseExampleLocalization.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_phrase_sense_example_localization_example_locale"
            and {column.name for column in constraint.columns} == {"phrase_sense_example_id", "locale"}
            for constraint in constraints
        )


class TestPhraseLearnerMigrationBackfill:
    def test_backfill_rows_are_derived_from_compiled_payload(self) -> None:
        migration = _load_phrase_migration()
        phrase_row = {
            "id": uuid.uuid4(),
            "compiled_payload": {
                "senses": [
                    {
                        "definition": "leave the ground",
                        "usage_note": "Common for planes.",
                        "part_of_speech": "verb",
                        "register": "neutral",
                        "primary_domain": "general",
                        "secondary_domains": ["general", "transport"],
                        "grammar_patterns": ["subject + take off"],
                        "synonyms": ["depart", "set off"],
                        "antonyms": ["land"],
                        "collocations": ["take off quickly"],
                        "examples": [
                            {"sentence": "The plane took off.", "difficulty": "A1"},
                            {"sentence": "We took off early.", "difficulty": "A2"},
                        ],
                        "translations": {
                            "ar": {
                                "definition": "يقلع",
                                "usage_note": "استخدام شائع",
                                "examples": ["أقلعت الطائرة.", "أقلعنا مبكرًا."],
                            },
                            "es": {
                                "definition": "despegar",
                                "usage_note": "uso común",
                                "examples": ["El avión despegó.", "Despegamos temprano."],
                            },
                            "ja": {
                                "definition": "離陸する",
                                "usage_note": "よくある用法",
                                "examples": ["飛行機が離陸した。", "私たちは早く離陸した。"],
                            },
                            "pt-BR": {
                                "definition": "decolar",
                                "usage_note": "uso comum",
                                "examples": ["O avião decolou.", "Decolamos cedo."],
                            },
                            "zh-Hans": {
                                "definition": "起飞",
                                "usage_note": "常见用法",
                                "examples": ["飞机起飞了。", "我们很早起飞了。"],
                            },
                        },
                    },
                ]
            },
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "source_type": "lexicon_snapshot",
        }

        sense_rows, sense_localization_rows, example_rows, example_localization_rows = migration._build_phrase_backfill_rows(phrase_row)

        assert [row["order_index"] for row in sense_rows] == [0]
        assert sense_rows[0]["definition"] == "leave the ground"
        assert sense_rows[0]["usage_note"] == "Common for planes."
        assert sense_rows[0]["part_of_speech"] == "verb"
        assert sense_rows[0]["register"] == "neutral"
        assert sense_rows[0]["primary_domain"] == "general"
        assert sense_rows[0]["secondary_domains"] == ["general", "transport"]
        assert sense_rows[0]["grammar_patterns"] == ["subject + take off"]
        assert sense_rows[0]["synonyms"] == ["depart", "set off"]
        assert sense_rows[0]["antonyms"] == ["land"]
        assert sense_rows[0]["collocations"] == ["take off quickly"]
        assert {row["locale"] for row in sense_localization_rows} == {"ar", "es", "ja", "pt-BR", "zh-Hans"}
        sense_localization_map = {row["locale"]: row for row in sense_localization_rows}
        assert sense_localization_map["zh-Hans"]["localized_definition"] == "起飞"
        assert sense_localization_map["ja"]["localized_usage_note"] == "よくある用法"
        assert [row["sentence"] for row in example_rows] == ["The plane took off.", "We took off early."]
        assert len(example_localization_rows) == 10
        example_localizations_by_locale = {}
        for row in example_localization_rows:
            example_localizations_by_locale.setdefault(row["phrase_sense_example_id"], {})[row["locale"]] = row["translation"]
        assert all(set(locale_map.keys()) == {"ar", "es", "ja", "pt-BR", "zh-Hans"} for locale_map in example_localizations_by_locale.values())
        assert any(locale_map["zh-Hans"] == "飞机起飞了。" for locale_map in example_localizations_by_locale.values())

    def test_backfill_phrase_rows_uses_schema_qualified_source_table(self) -> None:
        migration = _load_phrase_migration()
        connection = _RecordingConnection([])

        sense_rows, sense_localization_rows, example_rows, example_localization_rows = migration.backfill_phrase_rows(connection)

        assert sense_rows == []
        assert sense_localization_rows == []
        assert example_rows == []
        assert example_localization_rows == []
        from_clause = connection.statements[0].get_final_froms()[0]
        assert from_clause.schema == "lexicon"
        assert from_clause.name == "phrase_entries"

    def test_backfill_insert_tables_are_schema_qualified(self) -> None:
        migration = _load_phrase_migration()

        assert migration.phrase_senses_insert_table().schema == "lexicon"
        assert migration.phrase_sense_localizations_insert_table().schema == "lexicon"
        assert migration.phrase_sense_examples_insert_table().schema == "lexicon"
        assert migration.phrase_sense_example_localizations_insert_table().schema == "lexicon"

    def test_backfill_rows_skip_malformed_senses_and_examples(self) -> None:
        migration = _load_phrase_migration()
        phrase_row = {
            "id": uuid.uuid4(),
            "compiled_payload": {
                "senses": [
                    {
                        "definition": "   ",
                        "usage_note": "ignored",
                        "examples": [{"sentence": "missing definition is skipped"}],
                        "translations": {"zh-Hans": {"definition": "忽略", "usage_note": "忽略", "examples": ["忽略"]}},
                    },
                    {
                        "definition": "keep this",
                        "usage_note": "Used when valid.",
                        "examples": [
                            {"sentence": "   ", "difficulty": "A1"},
                            {"sentence": "Valid example.", "difficulty": "A2"},
                        ],
                        "translations": {"zh-Hans": {"definition": "保留", "usage_note": "有效", "examples": ["", "有效例句。"]}},
                    },
                ]
            },
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "source_type": "lexicon_snapshot",
        }

        sense_rows, sense_localization_rows, example_rows, example_localization_rows = migration._build_phrase_backfill_rows(phrase_row)

        assert len(sense_rows) == 1
        assert sense_rows[0]["definition"] == "keep this"
        assert len(sense_localization_rows) == 1
        assert len(example_rows) == 1
        assert len(example_localization_rows) == 1
        assert example_rows[0]["sentence"] == "Valid example."
        assert example_localization_rows[0]["translation"] == "有效例句。"

    def test_backfill_rows_dedupe_duplicate_example_sentences_and_keep_richer_locales(self) -> None:
        migration = _load_phrase_migration()
        phrase_row = {
            "id": uuid.uuid4(),
            "compiled_payload": {
                "senses": [
                    {
                        "definition": "keep this",
                        "usage_note": "Used when valid.",
                        "examples": [
                            {"sentence": "Repeat me.", "difficulty": "A1"},
                            {"sentence": "Repeat me.", "difficulty": "A2"},
                        ],
                        "translations": {
                            "zh-Hans": {"definition": "保留", "usage_note": "有效", "examples": ["重复我。", "重复我。再次"]},
                            "es": {"definition": "conservar", "usage_note": "uso válido", "examples": ["", "Repíteme otra vez."]},
                            "ja": {"definition": "保持する", "usage_note": "有効", "examples": ["", "もう一度繰り返して。"]},
                            "ar": {"definition": "الاحتفاظ", "usage_note": "مفيد", "examples": ["", "كررني مرة أخرى."]},
                            "pt-BR": {"definition": "manter", "usage_note": "válido", "examples": ["", "Repita-me de novo."]},
                        },
                    }
                ]
            },
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "source_type": "lexicon_snapshot",
        }

        sense_rows, sense_localization_rows, example_rows, example_localization_rows = migration._build_phrase_backfill_rows(phrase_row)

        assert len(sense_rows) == 1
        assert len(sense_localization_rows) == 5
        assert len(example_rows) == 1
        assert example_rows[0]["sentence"] == "Repeat me."
        assert example_rows[0]["difficulty"] == "A2"
        assert len(example_localization_rows) == 5
        locale_map = {row["locale"]: row["translation"] for row in example_localization_rows}
        assert locale_map == {
            "ar": "كررني مرة أخرى.",
            "es": "Repíteme otra vez.",
            "ja": "もう一度繰り返して。",
            "pt-BR": "Repita-me de novo.",
            "zh-Hans": "重复我。再次",
        }

    def test_backfill_rows_dedupe_duplicate_example_sentences_within_a_sense(self) -> None:
        migration = _load_phrase_migration()
        phrase_row = {
            "id": uuid.uuid4(),
            "compiled_payload": {
                "senses": [
                    {
                        "definition": "keep this",
                        "examples": [
                            {"sentence": "Repeat me.", "difficulty": "A1"},
                            {"sentence": "Repeat me.", "difficulty": "A2"},
                            {"sentence": "Repeat me. ", "difficulty": "B1"},
                            {"sentence": "Unique sentence.", "difficulty": "B2"},
                        ],
                        "translations": {
                            "zh-Hans": {
                                "definition": "保留",
                                "examples": ["重复我。", "重复我。", "重复我。", "独特句子。"],
                            }
                        },
                    }
                ]
            },
            "created_at": datetime(2026, 3, 20, tzinfo=timezone.utc),
            "source_type": "lexicon_snapshot",
        }

        sense_rows, sense_localization_rows, example_rows, example_localization_rows = migration._build_phrase_backfill_rows(phrase_row)

        assert len(sense_rows) == 1
        assert len(sense_localization_rows) == 1
        assert [row["sentence"] for row in example_rows] == ["Repeat me.", "Unique sentence."]
        assert [row["order_index"] for row in example_rows] == [0, 1]
        assert [row["translation"] for row in example_localization_rows] == ["重复我。", "独特句子。"]

    def test_upgrade_backfills_real_phrase_tables_on_postgres(self) -> None:
        migration = _load_phrase_migration()
        phrase_row = {
            "id": uuid.uuid4(),
            "compiled_payload": {
                "senses": [
                    {
                        "definition": "leave the ground",
                        "usage_note": "Common for planes.",
                        "part_of_speech": "verb",
                        "register": "neutral",
                        "primary_domain": "general",
                        "secondary_domains": ["general", "transport"],
                        "grammar_patterns": ["subject + take off"],
                        "synonyms": ["depart", "set off"],
                        "antonyms": ["land"],
                        "collocations": ["take off quickly"],
                        "examples": [
                            {"sentence": "The plane took off.", "difficulty": "A1"},
                        ],
                        "translations": {
                            "es": {
                                "definition": "despegar",
                                "usage_note": "uso común",
                                "examples": ["El avión despegó."],
                            },
                            "zh-Hans": {
                                "definition": "起飞",
                                "usage_note": "常见用法",
                                "examples": ["飞机起飞了。"],
                            },
                        },
                    }
                ]
            },
            "generated_at": datetime.now(timezone.utc),
            "created_at": datetime.now(timezone.utc),
            "source_type": "lexicon_snapshot",
        }

        with _temporary_postgres_lexicon_connection() as connection:
            source_table = _create_phrase_entries_source_table(connection)
            connection.execute(source_table.insert().values(phrase_row))

            migration.op = Operations(MigrationContext.configure(connection))
            migration.upgrade()

            assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_senses")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_localizations")).scalar_one() == 2
            assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_examples")).scalar_one() == 1
            assert connection.execute(text("SELECT count(*) FROM lexicon.phrase_sense_example_localizations")).scalar_one() == 2


class TestReferenceEntryModel:
    def test_defaults_and_fields(self) -> None:
        entry = ReferenceEntry(
            reference_type="country",
            display_form="Australia",
            normalized_form="australia",
            translation_mode="localized",
            brief_description="A country in the Southern Hemisphere.",
            pronunciation="/ɔˈstreɪliə/",
        )
        assert entry.reference_type == "country"
        assert entry.display_form == "Australia"
        assert entry.normalized_form == "australia"
        assert entry.translation_mode == "localized"
        assert entry.language == "en"
        assert entry.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in ReferenceEntry.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert ReferenceEntry.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_reference_entry_normalized_language"
            and {column.name for column in constraint.columns} == {"normalized_form", "language"}
            for constraint in constraints
        )


class TestReferenceLocalizationModel:
    def test_defaults_and_relationship_keys(self) -> None:
        localization = ReferenceLocalization(
            reference_entry_id=uuid.uuid4(),
            locale="es",
            display_form="Australia",
        )
        assert localization.locale == "es"
        assert localization.display_form == "Australia"
        assert localization.created_at is not None

    def test_schema_and_unique_constraint(self) -> None:
        constraints = [
            constraint
            for constraint in ReferenceLocalization.__table__.constraints
            if isinstance(constraint, UniqueConstraint)
        ]
        assert ReferenceLocalization.__table__.schema == LEXICON_SCHEMA
        assert any(
            constraint.name == "uq_reference_localization_entry_locale"
            and {column.name for column in constraint.columns} == {"reference_entry_id", "locale"}
            for constraint in constraints
        )
