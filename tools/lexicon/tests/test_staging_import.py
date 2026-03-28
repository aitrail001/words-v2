from unittest.mock import MagicMock, patch

from tools.lexicon.import_db import ImportSummary
from tools.lexicon.staging_import import merge_staged_word_rows, run_staging_import_file
from tools.lexicon.tests.test_import_db import (
    FakeLearnerCatalogEntry,
    FakeMeaning,
    FakeMeaningExample,
    FakeMeaningMetadata,
    FakePhraseEntry,
    FakePhraseSense,
    FakePhraseSenseExample,
    FakePhraseSenseExampleLocalization,
    FakePhraseSenseLocalization,
    FakeTranslation,
    FakeTranslationExample,
    FakeWord,
    FakeWordConfusable,
    FakeWordForm,
    FakeWordPartOfSpeech,
    FakeWordRelation,
    FakeLexiconEnrichmentJob,
    FakeLexiconEnrichmentRun,
)


class TestStagingImport:
    def test_merge_staged_word_rows_uses_set_based_word_stage_before_importing_senses(self) -> None:
        rows = [
            {
                "entry_type": "word",
                "word": "alpha",
                "language": "en",
                "frequency_rank": 1,
                "cefr_level": "A1",
                "generated_at": "2026-03-28T00:00:00Z",
                "part_of_speech": ["noun"],
                "forms": {"plural_forms": ["alphas"], "verb_forms": {}, "derivations": []},
                "confusable_words": [{"word": "alfa", "note": "spelling"}],
                "senses": [
                    {
                        "sense_id": "sense-1",
                        "definition": "the first letter",
                        "pos": "noun",
                        "examples": [{"sentence": "Alpha leads the list.", "difficulty": "A1"}],
                        "translations": {
                            "es": {
                                "definition": "alfa",
                                "usage_note": "primera letra",
                                "examples": ["Alfa encabeza la lista."],
                            }
                        },
                        "synonyms": ["beginning"],
                        "confidence": 0.91,
                        "generated_at": "2026-03-28T00:00:00Z",
                        "generation_run_id": "run-1",
                        "model_name": "gpt-5-nano",
                        "prompt_version": "v1",
                    }
                ],
            }
        ]

        with patch(
            "tools.lexicon.staging_import.import_compiled_rows",
            return_value=ImportSummary(),
            create=True,
        ) as mocked_import:
            summary = merge_staged_word_rows(
                MagicMock(),
                rows,
                source_type="repo_fixture",
                source_reference="fixture-1",
                language="en",
            )

        assert summary == ImportSummary()
        mocked_import.assert_called_once()
        assert mocked_import.call_args.args[1] == rows

    def test_run_staging_import_file_merges_words_and_falls_back_for_phrases(self) -> None:
        fake_session = MagicMock()
        fake_engine = MagicMock()

        class _FakeSessionContext:
            def __init__(self, _engine):
                self._engine = _engine

            def __enter__(self):
                return fake_session

            def __exit__(self, exc_type, exc, tb):
                return False

        staged_rows = [
            {"entry_type": "word", "word": "alpha", "language": "en", "senses": []},
            {"entry_type": "phrase", "word": "bank on", "language": "en", "senses": [{"definition": "to rely on"}]},
        ]

        with patch("tools.lexicon.staging_import._copy_rows_into_temp_stage", return_value=staged_rows), \
             patch("tools.lexicon.staging_import.merge_staged_word_rows", return_value=ImportSummary(created_words=1), create=True) as mocked_merge, \
             patch("tools.lexicon.staging_import.import_compiled_rows", return_value=ImportSummary(created_phrases=1), create=True) as mocked_import, \
             patch("tools.lexicon.staging_import._rebuild_learner_catalog_projection", create=True) as mocked_rebuild, \
             patch(
                 "tools.lexicon.staging_import._default_models",
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
                 create=True,
             ), \
             patch("tools.lexicon.staging_import._default_phrase_models", return_value=(FakePhraseEntry, FakePhraseSense, FakePhraseSenseLocalization, FakePhraseSenseExample, FakePhraseSenseExampleLocalization), create=True), \
             patch("sqlalchemy.engine.create.create_engine", return_value=fake_engine), \
             patch("sqlalchemy.orm.Session", _FakeSessionContext), \
             patch("sqlalchemy.orm.session.Session", _FakeSessionContext), \
             patch("app.core.config.get_settings", return_value=type("Settings", (), {"database_url_sync": "postgresql://example/test"})()):
            summary = run_staging_import_file(
                "/tmp/fake.jsonl",
                source_type="repo_fixture",
                source_reference="fake-fixture",
            )

        assert summary["created_words"] == 1
        assert summary["created_phrases"] == 1
        mocked_merge.assert_called_once()
        assert mocked_merge.call_args.args[1] == [staged_rows[0]]
        mocked_import.assert_called_once()
        assert mocked_import.call_args.args[1] == [staged_rows[1]]
        mocked_rebuild.assert_called_once()
