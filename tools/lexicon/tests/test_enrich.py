import json
import io
import subprocess
import tempfile
import time
import unittest
from contextlib import redirect_stderr
from unittest.mock import patch
from pathlib import Path

from tools.lexicon.config import LexiconSettings
from tools.lexicon.jsonl_io import append_jsonl, read_jsonl, write_jsonl
from tools.lexicon.enrich import (
    NodeOpenAICompatibleResponsesClient,
    OpenAICompatibleResponsesClient,
    merge_staged_enrichment_rows,
    run_core_enrichment,
    split_legacy_enrich_artifact,
    split_compiled_row_for_staging,
    _generate_validated_phrase_payload_with_stats,
    _generate_validated_word_payload_with_stats,
    _single_sense_response_schema,
    build_openai_compatible_phrase_enrichment_provider,
    _validate_openai_compatible_word_payload,
    _validate_string_list_field,
    _word_enrichment_response_schema,
    learner_meaning_cap,
    build_enrichment_prompt,
    build_phrase_enrichment_prompt,
    build_phrase_enrichment_provider,
    build_word_enrichment_prompt,
    build_enrichment_provider,
    build_openai_compatible_enrichment_provider,
    build_openai_compatible_node_phrase_enrichment_provider,
    build_openai_compatible_word_enrichment_provider,
    build_placeholder_word_enrichment_provider,
    _default_node_runner,
    build_openai_compatible_node_enrichment_provider,
    _parse_json_payload_text,
    WordJobOutcome,
    enrich_snapshot,
    read_snapshot_inputs,
    run_enrichment,
    run_translation_enrichment,
)
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.models import EnrichmentRecord, LexemeRecord
from tools.lexicon.runtime_logging import RuntimeLogConfig, RuntimeLogger
from tools.lexicon.schemas.phrase_enrichment_schema import normalize_phrase_enrichment_payload


class _FakeResponsesAPI:
    def __init__(self, handler):
        self._handler = handler

    def create(self, **payload):
        return self._handler(payload)


class _FakeOpenAIClient:
    def __init__(self, handler):
        self.responses = _FakeResponsesAPI(handler)


def _client_from_transport(transport):
    return _FakeOpenAIClient(lambda payload: transport("https://example.test/v1/responses", payload, {"Authorization": "Bearer secret-key", "Content-Type": "application/json"}))


def _test_translations(definition: str = "translated definition", usage_note: str = "translated usage note", examples: list[str] | None = None) -> dict[str, dict[str, object]]:
    example_rows = list(examples or ["translated example"])
    return {
        "zh-Hans": {"definition": f"zh:{definition}", "usage_note": f"zh:{usage_note}", "examples": [f"zh:{row}" for row in example_rows]},
        "es": {"definition": f"es:{definition}", "usage_note": f"es:{usage_note}", "examples": [f"es:{row}" for row in example_rows]},
        "ar": {"definition": f"ar:{definition}", "usage_note": f"ar:{usage_note}", "examples": [f"ar:{row}" for row in example_rows]},
        "pt-BR": {"definition": f"pt:{definition}", "usage_note": f"pt:{usage_note}", "examples": [f"pt:{row}" for row in example_rows]},
        "ja": {"definition": f"ja:{definition}", "usage_note": f"ja:{usage_note}", "examples": [f"ja:{row}" for row in example_rows]},
    }


def _test_phonetics(us: str = "/rʌn/", uk: str = "/rʌn/", au: str = "/rɐn/") -> dict[str, dict[str, object]]:
    return {
        "us": {"ipa": us, "confidence": 0.99},
        "uk": {"ipa": uk, "confidence": 0.98},
        "au": {"ipa": au, "confidence": 0.97},
    }


class EnrichSnapshotTests(unittest.TestCase):
    def _write_snapshot(self, snapshot_dir: Path) -> None:
        (snapshot_dir / "lexemes.jsonl").write_text(
            json.dumps(
                {
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "language": "en",
                    "wordfreq_rank": 5,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-07T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (snapshot_dir / "senses.jsonl").write_text(
            json.dumps(
                {
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_run_1",
                    "lexeme_id": "lx_run",
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "selection_reason": "common learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }
            )
            + "\n",
            encoding="utf-8",
        )

    def _write_resume_modes_snapshot(self, snapshot_dir: Path) -> None:
        (snapshot_dir / "lexemes.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_alpha",
                            "lemma": "alpha",
                            "language": "en",
                            "wordfreq_rank": 1,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_run",
                            "lemma": "run",
                            "language": "en",
                            "wordfreq_rank": 2,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_play",
                            "lemma": "play",
                            "language": "en",
                            "wordfreq_rank": 3,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (snapshot_dir / "senses.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_alpha_1",
                            "lexeme_id": "lx_alpha",
                            "wn_synset_id": "alpha.n.01",
                            "part_of_speech": "noun",
                            "canonical_gloss": "alpha sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_run_1",
                            "lexeme_id": "lx_run",
                            "wn_synset_id": "run.v.01",
                            "part_of_speech": "verb",
                            "canonical_gloss": "run sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_play_1",
                            "lexeme_id": "lx_play",
                            "wn_synset_id": "play.v.01",
                            "part_of_speech": "verb",
                            "canonical_gloss": "play sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def test_read_snapshot_inputs_loads_linked_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            lexemes, senses = read_snapshot_inputs(snapshot_dir)

            self.assertEqual(len(lexemes), 1)
            self.assertEqual(len(senses), 1)
            self.assertEqual(lexemes[0].lemma, "run")
            self.assertEqual(senses[0].sense_id, "sn_lx_run_1")

    def test_read_snapshot_inputs_loads_phrase_rows_from_phrases_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text("", encoding="utf-8")
            (snapshot_dir / "phrases.jsonl").write_text(
                json.dumps(
                    {
                        "snapshot_id": "snap-1",
                        "entry_id": "ph_take_off",
                        "entry_type": "phrase",
                        "normalized_form": "take off",
                        "display_form": "Take off",
                        "phrase_kind": "phrasal_verb",
                        "language": "en",
                        "source_provenance": [{"source": "phrase_seed"}],
                        "seed_metadata": {"raw_reviewed_as": "phrasal verb"},
                        "created_at": "2026-03-23T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            lexemes, senses = read_snapshot_inputs(snapshot_dir)

            self.assertEqual(len(lexemes), 1)
            self.assertEqual(senses, [])
            self.assertEqual(lexemes[0].entry_type, "phrase")
            self.assertEqual(lexemes[0].phrase_kind, "phrasal_verb")
            self.assertEqual(lexemes[0].display_form, "Take off")

    def test_run_core_enrichment_writes_core_rows_without_translations(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            result = run_core_enrichment(
                snapshot_dir,
                provider_mode="placeholder",
                max_concurrency=1,
            )

            self.assertEqual(result.core_row_count, 1)
            core_rows = [json.loads(line) for line in result.output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(core_rows), 1)
            self.assertEqual(core_rows[0]["entry_id"], "lx_run")
            self.assertNotIn("translations", core_rows[0]["senses"][0])

    def test_run_core_enrichment_uses_core_stage_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            captured: dict[str, object] = {}
            core_settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-5.4",
                    "LEXICON_LLM_API_KEY": "secret",
                }
            )
            translation_settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-5.4-mini",
                    "LEXICON_LLM_API_KEY": "secret",
                }
            )

            def fake_from_env(env=None, *, stage=None):
                if stage == "core":
                    return core_settings
                if stage == "translations":
                    return translation_settings
                return translation_settings

            def fake_enrich_snapshot(
                snapshot_dir: Path,
                *,
                output_path: Path | None = None,
                settings: LexiconSettings | None = None,
                **_: object,
            ) -> list[EnrichmentRecord]:
                captured["model"] = settings.llm_model if settings else None
                assert output_path is not None
                output_path.write_text(
                    json.dumps(
                        {
                            "schema_version": "1.1.0",
                            "entry_id": "lx_run",
                            "entry_type": "word",
                            "normalized_form": "run",
                            "source_provenance": [{"source": "wordnet"}],
                            "entity_category": "general",
                            "word": "run",
                            "part_of_speech": ["verb"],
                            "cefr_level": "B1",
                            "frequency_rank": 5,
                            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                            "senses": [
                                {
                                    "sense_id": "sn_lx_run_1",
                                    "wn_synset_id": "run.v.01",
                                    "pos": "verb",
                                    "sense_kind": "standard_meaning",
                                    "decision": "keep_standard",
                                    "base_word": None,
                                    "primary_domain": "general",
                                    "secondary_domains": [],
                                    "register": "neutral",
                                    "definition": "move fast by using your legs",
                                    "examples": [{"sentence": "I run every day.", "difficulty": "B1"}],
                                    "synonyms": [],
                                    "antonyms": [],
                                    "collocations": [],
                                    "grammar_patterns": [],
                                    "usage_note": "Common learner note.",
                                    "enrichment_id": "enr_1",
                                    "generation_run_id": "run-1",
                                    "model_name": "gpt-5.4",
                                    "prompt_version": "v1",
                                    "confidence": 0.9,
                                    "generated_at": "2026-04-08T00:00:00Z",
                                    "translations": {},
                                }
                            ],
                            "confusable_words": [],
                            "generated_at": "2026-04-08T00:00:00Z",
                            "phonetics": _test_phonetics(),
                        }
                    )
                    + "\n",
                    encoding="utf-8",
                )
                return []

            with patch("tools.lexicon.enrich.LexiconSettings.from_env", side_effect=fake_from_env):
                with patch("tools.lexicon.enrich.enrich_snapshot", side_effect=fake_enrich_snapshot):
                    result = run_core_enrichment(snapshot_dir, provider_mode="auto", max_concurrency=1)

            self.assertEqual(result.core_row_count, 1)
            self.assertEqual(captured["model"], "gpt-5.4")

    def test_run_core_enrichment_preserves_existing_compiled_rows_when_appending_new_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            core_path = snapshot_dir / "words.enriched.core.jsonl"
            core_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "schema_version": "1.1.0",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "normalized_form": "alpha",
                                "source_provenance": [{"source": "wordnet"}],
                                "entity_category": "general",
                                "word": "alpha",
                                "part_of_speech": ["noun"],
                                "cefr_level": "A1",
                                "frequency_rank": 1,
                                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                "senses": [
                                    {
                                        "sense_id": "sn_lx_alpha_1",
                                        "wn_synset_id": "alpha.n.01",
                                        "pos": "noun",
                                        "sense_kind": "standard_meaning",
                                        "decision": "keep_standard",
                                        "base_word": None,
                                        "primary_domain": "general",
                                        "secondary_domains": [],
                                        "register": "neutral",
                                        "definition": "existing alpha",
                                        "examples": [{"sentence": "alpha existing", "difficulty": "A1"}],
                                        "synonyms": [],
                                        "antonyms": [],
                                        "collocations": [],
                                        "grammar_patterns": [],
                                        "usage_note": "existing alpha note",
                                        "enrichment_id": "en_alpha_existing",
                                        "generation_run_id": "existing-run",
                                        "model_name": "test-model",
                                        "prompt_version": "v1",
                                        "confidence": 0.9,
                                        "generated_at": "2026-04-08T00:00:00Z",
                                    }
                                ],
                                "confusable_words": [],
                                "generated_at": "2026-04-08T00:00:00Z",
                                "phonetics": _test_phonetics(),
                            }
                        )
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            def fake_enrich_snapshot(
                snapshot_dir: Path,
                *,
                output_path: Path | None = None,
                **_: object,
            ) -> list[EnrichmentRecord]:
                assert output_path is not None
                append_jsonl(output_path, [{
                    "schema_version": "1.1.0",
                    "entry_id": "lx_beta",
                    "entry_type": "word",
                    "normalized_form": "beta",
                    "source_provenance": [{"source": "wordnet"}],
                    "entity_category": "general",
                    "word": "beta",
                    "part_of_speech": ["noun"],
                    "cefr_level": "A1",
                    "frequency_rank": 2,
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "senses": [
                        {
                            "sense_id": "sn_lx_beta_1",
                            "wn_synset_id": "beta.n.01",
                            "pos": "noun",
                            "sense_kind": "standard_meaning",
                            "decision": "keep_standard",
                            "base_word": None,
                            "primary_domain": "general",
                            "secondary_domains": [],
                            "register": "neutral",
                            "definition": "new beta",
                            "examples": [{"sentence": "beta new", "difficulty": "A1"}],
                            "synonyms": [],
                            "antonyms": [],
                            "collocations": [],
                            "grammar_patterns": [],
                            "usage_note": "new beta note",
                            "enrichment_id": "en_beta_new",
                            "generation_run_id": "run-1",
                            "model_name": "gpt-5.4",
                            "prompt_version": "v1",
                            "confidence": 0.9,
                            "generated_at": "2026-04-08T00:00:00Z",
                            "translations": {},
                        }
                    ],
                    "confusable_words": [],
                    "generated_at": "2026-04-08T00:00:00Z",
                    "phonetics": _test_phonetics(),
                }])
                return []

            with patch("tools.lexicon.enrich.enrich_snapshot", side_effect=fake_enrich_snapshot):
                run_core_enrichment(snapshot_dir, max_concurrency=1)

            core_rows = read_jsonl(core_path)
            self.assertEqual([row["entry_id"] for row in core_rows], ["lx_alpha", "lx_beta"])
            self.assertEqual(core_rows[0]["senses"][0]["definition"], "existing alpha")
            self.assertEqual(core_rows[1]["senses"][0]["definition"], "new beta")

    def test_run_core_enrichment_resume_skips_existing_compiled_core_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            core_path = snapshot_dir / "words.enriched.core.jsonl"
            core_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "schema_version": "1.1.0",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "normalized_form": "alpha",
                                "source_provenance": [{"source": "wordnet"}],
                                "entity_category": "general",
                                "word": "alpha",
                                "part_of_speech": ["noun"],
                                "cefr_level": "A1",
                                "frequency_rank": 1,
                                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                "senses": [
                                    {
                                        "sense_id": "sn_lx_alpha_1",
                                        "wn_synset_id": "alpha.n.01",
                                        "pos": "noun",
                                        "sense_kind": "standard_meaning",
                                        "decision": "keep_standard",
                                        "base_word": None,
                                        "primary_domain": "general",
                                        "secondary_domains": [],
                                        "register": "neutral",
                                        "definition": "stale alpha",
                                        "examples": [{"sentence": "alpha stale", "difficulty": "A1"}],
                                        "synonyms": [],
                                        "antonyms": [],
                                        "collocations": [],
                                        "grammar_patterns": [],
                                        "usage_note": "stale alpha note",
                                        "enrichment_id": "en_alpha_stale",
                                        "generation_run_id": "existing-run",
                                        "model_name": "test-model",
                                        "prompt_version": "v1",
                                        "confidence": 0.8,
                                        "generated_at": "2026-04-08T00:00:00Z",
                                    }
                                ],
                                "confusable_words": [],
                                "generated_at": "2026-04-08T00:00:00Z",
                                "phonetics": _test_phonetics(),
                            }
                        ),
                        json.dumps(
                            {
                                "schema_version": "1.1.0",
                                "entry_id": "lx_play",
                                "entry_type": "word",
                                "normalized_form": "play",
                                "source_provenance": [{"source": "wordnet"}],
                                "entity_category": "general",
                                "word": "play",
                                "part_of_speech": ["verb"],
                                "cefr_level": "A1",
                                "frequency_rank": 3,
                                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                "senses": [
                                    {
                                        "sense_id": "sn_lx_play_1",
                                        "wn_synset_id": "play.v.01",
                                        "pos": "verb",
                                        "sense_kind": "standard_meaning",
                                        "decision": "keep_standard",
                                        "base_word": None,
                                        "primary_domain": "general",
                                        "secondary_domains": [],
                                        "register": "neutral",
                                        "definition": "existing play",
                                        "examples": [{"sentence": "play existing", "difficulty": "A1"}],
                                        "synonyms": [],
                                        "antonyms": [],
                                        "collocations": [],
                                        "grammar_patterns": [],
                                        "usage_note": "existing play note",
                                        "enrichment_id": "en_play_existing",
                                        "generation_run_id": "existing-run",
                                        "model_name": "test-model",
                                        "prompt_version": "v1",
                                        "confidence": 0.9,
                                        "generated_at": "2026-04-08T00:00:00Z",
                                    }
                                ],
                                "confusable_words": [],
                                "generated_at": "2026-04-08T00:00:00Z",
                                "phonetics": _test_phonetics(),
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            resumed_lemmas: list[str] = []

            def fake_enrich_snapshot(
                snapshot_dir: Path,
                *,
                resume: bool = False,
                **_: object,
            ) -> list[EnrichmentRecord]:
                self.assertTrue(resume)
                lexemes, _ = read_snapshot_inputs(snapshot_dir)
                completed_lexeme_ids = {row["lexeme_id"] for row in read_jsonl(snapshot_dir / "enrich.core.checkpoint.jsonl")}
                for lexeme in sorted(lexemes, key=lambda item: (item.wordfreq_rank, item.lemma)):
                    if lexeme.lexeme_id in completed_lexeme_ids:
                        continue
                    resumed_lemmas.append(lexeme.lemma)
                return []

            with patch("tools.lexicon.enrich.enrich_snapshot", side_effect=fake_enrich_snapshot):
                run_core_enrichment(snapshot_dir, max_concurrency=1, resume=True)

            self.assertEqual(resumed_lemmas, ["run"])
            checkpoint_rows = read_jsonl(snapshot_dir / "enrich.core.checkpoint.jsonl")
            self.assertEqual([row["lexeme_id"] for row in checkpoint_rows], ["lx_alpha", "lx_play"])

    def test_run_core_enrichment_rejects_distinct_runtime_output_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            with self.assertRaises(RuntimeError):
                run_core_enrichment(
                    snapshot_dir,
                    output_path=snapshot_dir / "words.enriched.core.jsonl",
                    runtime_output_path=snapshot_dir / "words.enriched.core.runtime.jsonl",
                    max_concurrency=1,
                )

    def test_run_translation_enrichment_writes_translation_ledger_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            core_path = snapshot_dir / "words.enriched.core.jsonl"
            core_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "normalized_form": "run",
                        "source_provenance": [{"source": "wordnet"}],
                        "entity_category": "general",
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "B1",
                        "frequency_rank": 5,
                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        "senses": [
                            {
                                "sense_id": "sn_lx_run_1",
                                "wn_synset_id": "run.v.01",
                                "pos": "verb",
                                "sense_kind": "standard_meaning",
                                "decision": "keep_standard",
                                "base_word": None,
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "definition": "move fast by using your legs",
                                "examples": [{"sentence": "I run every day.", "difficulty": "B1"}],
                                "synonyms": [],
                                "antonyms": [],
                                "collocations": [],
                                "grammar_patterns": [],
                                "usage_note": "Common learner note.",
                                "enrichment_id": "enr_1",
                                "generation_run_id": "run-1",
                                "model_name": "test-model",
                                "prompt_version": "v1",
                                "confidence": 0.9,
                                "generated_at": "2026-04-08T00:00:00Z",
                            }
                        ],
                        "confusable_words": [],
                        "generated_at": "2026-04-08T00:00:00Z",
                        "phonetics": _test_phonetics(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            def translation_provider(**_: object) -> dict[str, dict[str, object]]:
                return _test_translations(
                    definition="move quickly",
                    usage_note="translation note",
                    examples=["I run every day."],
                )

            result = run_translation_enrichment(
                snapshot_dir,
                core_input_path=core_path,
                translation_provider=translation_provider,
            )

            self.assertEqual(result.translation_row_count, 5)
            rows = [json.loads(line) for line in result.output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(rows), 5)
            self.assertEqual({row["locale"] for row in rows}, {"zh-Hans", "es", "ar", "pt-BR", "ja"})

    def test_run_translation_enrichment_uses_translation_stage_settings(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            core_path = snapshot_dir / "words.enriched.core.jsonl"
            core_path.write_text(
                json.dumps(
                    {
                        "schema_version": "1.1.0",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "normalized_form": "run",
                        "source_provenance": [{"source": "wordnet"}],
                        "entity_category": "general",
                        "word": "run",
                        "part_of_speech": ["verb"],
                        "cefr_level": "B1",
                        "frequency_rank": 5,
                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        "senses": [
                            {
                                "sense_id": "sn_lx_run_1",
                                "wn_synset_id": "run.v.01",
                                "pos": "verb",
                                "sense_kind": "standard_meaning",
                                "decision": "keep_standard",
                                "base_word": None,
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "definition": "move fast by using your legs",
                                "examples": [{"sentence": "I run every day.", "difficulty": "B1"}],
                                "synonyms": [],
                                "antonyms": [],
                                "collocations": [],
                                "grammar_patterns": [],
                                "usage_note": "Common learner note.",
                                "enrichment_id": "enr_1",
                                "generation_run_id": "run-1",
                                "model_name": "test-model",
                                "prompt_version": "v1",
                                "confidence": 0.9,
                                "generated_at": "2026-04-08T00:00:00Z",
                            }
                        ],
                        "confusable_words": [],
                        "generated_at": "2026-04-08T00:00:00Z",
                        "phonetics": _test_phonetics(),
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            captured: dict[str, object] = {}
            core_settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-5.4",
                    "LEXICON_LLM_API_KEY": "secret",
                }
            )
            translation_settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-5.4-mini",
                    "LEXICON_LLM_API_KEY": "secret",
                }
            )

            def fake_from_env(env=None, *, stage=None):
                if stage == "core":
                    return core_settings
                if stage == "translations":
                    return translation_settings
                return core_settings

            def fake_build_translation_provider(
                *,
                settings: LexiconSettings,
                **_: object,
            ):
                captured["model"] = settings.llm_model

                def provider(**__: object) -> dict[str, dict[str, object]]:
                    return _test_translations(
                        definition="move quickly",
                        usage_note="translation note",
                        examples=["I run every day."],
                    )

                return provider

            with patch("tools.lexicon.enrich.LexiconSettings.from_env", side_effect=fake_from_env):
                with patch("tools.lexicon.enrich.build_translation_provider", side_effect=fake_build_translation_provider):
                    result = run_translation_enrichment(
                        snapshot_dir,
                        core_input_path=core_path,
                        provider_mode="auto",
                    )

            self.assertEqual(result.translation_row_count, 5)
            self.assertEqual(captured["model"], "gpt-5.4-mini")

    def test_build_phrase_enrichment_prompt_mentions_phrase_context(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_take_off",
            lemma="take off",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_take_off",
            entry_type="phrase",
            normalized_form="take off",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="phrasal_verb",
            display_form="Take off",
            seed_metadata={"raw_reviewed_as": "phrasal verb"},
        )

        prompt = build_phrase_enrichment_prompt(lexeme=lexeme)

        self.assertIn("Take off", prompt)
        self.assertIn("phrasal_verb", prompt)
        self.assertIn("phrase", prompt.lower())

    def test_phrase_provider_respects_validation_retry_limit_override(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-5.4-mini",
                "LEXICON_LLM_API_KEY": "secret",
            }
        )
        call_count = 0

        def transport(url, payload, headers):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "phrase_kind": "idiom",
                                            "confidence": 0.87,
                                            "senses": [
                                                {
                                                    "definition": "to wish someone good luck",
                                                    "part_of_speech": "phrase",
                                                    "examples": [{"sentence": "Break a leg!", "difficulty": "B1"}],
                                                    "grammar_patterns": ["say + phrase"],
                                                    "usage_note": "Used before a performance.",
                                                    "translations": {
                                                        locale: {
                                                            "definition": f"{locale}: definition",
                                                            "usage_note": "",
                                                            "examples": ["translated example"],
                                                        }
                                                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                                                    },
                                                }
                                            ],
                                        }
                                    ),
                                }
                            ],
                        }
                    ]
                }
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "phrase_kind": "idiom",
                                        "confidence": 0.87,
                                        "senses": [
                                            {
                                                "definition": "to wish someone good luck",
                                                "part_of_speech": "phrase",
                                                "examples": [{"sentence": "Break a leg!", "difficulty": "B1"}],
                                                "grammar_patterns": ["say + phrase"],
                                                "usage_note": "Used before a performance.",
                                                "translations": _test_translations("Break a leg."),
                                            }
                                        ],
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

        provider = build_openai_compatible_phrase_enrichment_provider(
            settings=settings,
            client=_client_from_transport(transport),
            validation_retries=0,
        )
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )

        with self.assertRaisesRegex(RuntimeError, "missing_translated_usage_note_with_source_note_present"):
            provider(
                lexeme=lexeme,
                senses=[],
                settings=settings,
                generated_at="2026-03-23T00:00:00Z",
                generation_run_id="run-1",
                prompt_version="v1",
            )

        self.assertEqual(call_count, 1)

    def test_openai_compatible_phrase_provider_uses_phrase_schema(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-5.4-mini",
                "LEXICON_LLM_API_KEY": "secret",
            }
        )
        captured: dict[str, object] = {}

        def handler(payload):
            captured["input"] = payload["input"]
            captured["schema"] = payload["text"]["format"]["name"]
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "phrase_kind": "idiom",
                                        "confidence": 0.87,
                                        "senses": [
                                            {
                                                "definition": "to wish someone good luck",
                                                "part_of_speech": "phrase",
                                                "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                                                "grammar_patterns": ["say + phrase"],
                                                "usage_note": "Used before a performance.",
                                                "translations": _test_translations("They told me to break a leg."),
                                            }
                                        ],
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

        provider = build_openai_compatible_phrase_enrichment_provider(
            settings=settings,
            client=_FakeOpenAIClient(handler),
        )
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )

        outcome = provider(
            lexeme=lexeme,
            senses=[],
            settings=settings,
            generated_at="2026-03-23T00:00:00Z",
            generation_run_id="run-1",
            prompt_version="v1",
        )

        self.assertEqual(captured["schema"], "lexicon_enrichment_phrase")
        self.assertIn("Break a leg", str(captured["input"]))
        self.assertEqual(outcome.records[0].definition, "to wish someone good luck")
        self.assertEqual(outcome.records[0].part_of_speech, "phrase")

    def test_placeholder_word_provider_emits_grouped_phonetics(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            settings = LexiconSettings.from_env({})
            provider = build_placeholder_word_enrichment_provider(settings=settings)

            outcome = provider(
                lexeme=lexemes[0],
                senses=senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-1",
                prompt_version="v1",
            )

            self.assertEqual(outcome[0].phonetics["us"]["ipa"], "/run/")
            self.assertEqual(outcome[0].phonetics["uk"]["ipa"], "/run/")
            self.assertEqual(outcome[0].phonetics["au"]["ipa"], "/run/")

    def test_placeholder_word_provider_supports_lexeme_only_snapshots(self) -> None:
        settings = LexiconSettings.from_env({})
        provider = build_placeholder_word_enrichment_provider(settings=settings)
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=False,
            source_refs=["wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        outcome = provider(
            lexeme=lexeme,
            senses=[],
            settings=settings,
            generated_at="2026-03-07T00:00:00Z",
            generation_run_id="run-1",
            prompt_version="v1",
        )

        self.assertEqual(outcome.decision, "keep_standard")
        self.assertEqual(len(outcome.records), 1)
        self.assertEqual(outcome.records[0].definition, "placeholder learner definition for run")
        self.assertEqual(outcome.records[0].phonetics["us"]["ipa"], "/run/")

    def test_enrich_snapshot_writes_words_enriched_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del settings
                sense = senses[0]
                return WordJobOutcome(records=[EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id="en_sn_lx_run_1_v1",
                    sense_id=sense.sense_id,
                    lexeme_id=lexeme.lexeme_id,
                    sense_order=sense.sense_order,
                    part_of_speech=sense.part_of_speech,
                    sense_kind="standard_meaning",
                    decision="keep_standard",
                    base_word=None,
                    definition=f"to {sense.canonical_gloss}",
                    examples=[{"sentence": f"I {lexeme.lemma} every morning.", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=["jog"],
                    antonyms=["walk"],
                    collocations=["run fast"],
                    grammar_patterns=["run + adverb"],
                    usage_note="Common everyday verb.",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[{"word": "ran", "note": "Past tense form."}],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(
                        f"to {sense.canonical_gloss}",
                        "Common everyday verb.",
                        [f"I {lexeme.lemma} every morning."],
                    ),
                )], decision="keep_standard")

            records = enrich_snapshot(
                snapshot_dir,
                word_provider=word_provider,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(len(records), 1)
            enrichment_path = snapshot_dir / "words.enriched.jsonl"
            self.assertTrue(enrichment_path.exists())
            payload = [json.loads(line) for line in enrichment_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(payload[0]["entry_id"], "lx_run")
            self.assertEqual(payload[0]["senses"][0]["sense_id"], "sn_lx_run_1")
            self.assertEqual(payload[0]["senses"][0]["model_name"], "test-provider")

    def test_build_enrichment_prompt_includes_lexeme_sense_and_rank_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]

            prompt = build_enrichment_prompt(lexeme=lexeme, sense=sense)

            self.assertIn("run", prompt)
            self.assertIn("move fast by using your legs", prompt)
            self.assertIn("word frequency rank: 5", prompt.lower())
            self.assertIn("json", prompt.lower())

    def test_build_word_enrichment_prompt_uses_word_level_decision_contract_without_sense_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, senses = read_snapshot_inputs(snapshot_dir)

            prompt = build_word_enrichment_prompt(lexeme=lexeme[0], senses=senses, prompt_mode="word_only")

            self.assertIn("discard", prompt)
            self.assertIn("keep_standard", prompt)
            self.assertIn("keep_derived_special", prompt)
            self.assertNotIn("Allowed sense IDs", prompt)
            self.assertNotIn("sense_id", prompt)
            self.assertNotIn("WordNet-grounded", prompt)

    def test_learner_meaning_cap_compresses_the_highest_frequency_band(self) -> None:
        self.assertEqual(learner_meaning_cap(25), 5)
        self.assertEqual(learner_meaning_cap(250), 5)
        self.assertEqual(learner_meaning_cap(251), 6)
        self.assertEqual(learner_meaning_cap(5000), 8)
        self.assertEqual(learner_meaning_cap(10001), 4)

    def test_build_word_enrichment_prompt_adds_compression_guidance_for_common_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            common_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "to",
                "lexeme_id": "lx_to",
                "entry_id": "lx_to",
                "normalized_form": "to",
                "wordfreq_rank": 2,
            })

            prompt = build_word_enrichment_prompt(lexeme=common_lexeme, senses=senses, prompt_mode="word_only").lower()

            self.assertIn("select at most 5 learner-friendly meanings in total", prompt)
            self.assertIn("for very common grammar or function words", prompt)
            self.assertIn("merge closely related micro-uses", prompt)
            self.assertIn("do not split tiny contextual variants into separate senses", prompt)

    def test_build_word_enrichment_prompt_preserves_closed_class_grammar_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            possessive_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "our",
                "lexeme_id": "lx_our",
                "entry_id": "lx_our",
                "normalized_form": "our",
                "wordfreq_rank": 70,
            })

            prompt = build_word_enrichment_prompt(lexeme=possessive_lexeme, senses=senses, prompt_mode="word_only").lower()

            self.assertIn("do not discard common closed-class grammar words", prompt)
            self.assertIn("pronouns, determiners, and possessives", prompt)
            self.assertIn("plain auxiliary verb inflections such as", prompt)
            self.assertIn("is, are, and has", prompt)

    def test_build_word_enrichment_prompt_discards_plain_contractions_and_prefers_derived_special_links(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            said_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "said",
                "lexeme_id": "lx_said",
                "entry_id": "lx_said",
                "normalized_form": "said",
                "wordfreq_rank": 95,
            })

            prompt = build_word_enrichment_prompt(lexeme=said_lexeme, senses=senses, prompt_mode="word_only").lower()

            self.assertIn("plain contractions such as", prompt)
            self.assertIn("\"it's\" or \"i'm\"", prompt)
            self.assertIn("prefer keep_derived_special", prompt)
            self.assertIn("smaller subset of special, shifted, or lexicalized uses", prompt)

    def test_validate_openai_compatible_word_payload_accepts_derived_special_without_sense_ids(self) -> None:
        lexeme = type("Lexeme", (), {
            "lemma": "meeting",
            "wordfreq_rank": 80,
            "entity_category": "general",
            "is_variant_with_distinct_meanings": False,
            "variant_base_form": None,
            "variant_relationship": None,
            "variant_prompt_note": None,
        })()
        response = {
            "decision": "keep_derived_special",
            "base_word": "meet",
            "discard_reason": None,
            "phonetics": {
                "us": {"ipa": "/ˈmiːtɪŋ/", "confidence": 0.98},
                "uk": {"ipa": "/ˈmiːtɪŋ/", "confidence": 0.97},
                "au": {"ipa": "/ˈmiːtɪŋ/", "confidence": 0.96},
            },
            "senses": [
                {
                    "sense_kind": "base_form_reference",
                    "part_of_speech": "noun",
                    "definition": "the noun meeting is also a form related to meet",
                    "examples": [{"sentence": "We scheduled a meeting for Friday.", "difficulty": "A1"}],
                    "cefr_level": "A1",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": ["schedule a meeting"],
                    "grammar_patterns": ["a meeting"],
                    "usage_note": "Use this only as a brief link to the base word.",
                    "forms": {"plural_forms": ["meetings"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "confusable_words": [],
                    "confidence": 0.8,
                    "translations": _test_translations(),
                },
                {
                    "sense_kind": "special_meaning",
                    "part_of_speech": "noun",
                    "definition": "an event where people gather to talk or decide something",
                    "examples": [{"sentence": "The team meeting starts at noon.", "difficulty": "A1"}],
                    "cefr_level": "A1",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "synonyms": ["session"],
                    "antonyms": [],
                    "collocations": ["team meeting"],
                    "grammar_patterns": ["hold a meeting"],
                    "usage_note": "This is the standalone noun meaning learners should study.",
                    "forms": {"plural_forms": ["meetings"], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "confusable_words": [],
                    "confidence": 0.93,
                    "translations": _test_translations(),
                },
            ],
        }

        payload = _validate_openai_compatible_word_payload(response, lexeme=lexeme, senses=[])

        self.assertEqual(payload["decision"], "keep_derived_special")
        self.assertEqual(payload["base_word"], "meet")
        self.assertEqual(payload["phonetics"]["au"]["ipa"], "/ˈmiːtɪŋ/")
        self.assertEqual([sense["sense_kind"] for sense in payload["senses"]], ["base_form_reference", "special_meaning"])

    def test_openai_compatible_client_uses_endpoint_and_authorization_header(self) -> None:
        captured = {}

        def transport(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "definition": "to move quickly on foot",
                                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                        "cefr_level": "A1",
                                        "primary_domain": "general",
                                        "secondary_domains": [],
                                        "register": "neutral",
                                        "synonyms": ["jog"],
                                        "antonyms": ["walk"],
                                        "collocations": ["run fast"],
                                        "grammar_patterns": ["run + adverb"],
                                        "usage_note": "Common everyday verb.",
                                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                                        "confidence": 0.93,
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

        client = OpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            transport=transport,
        )

        payload = client.generate_json(
            "hello",
            response_schema={
                "name": "test_schema",
                "schema": {
                    "type": "object",
                    "properties": {"definition": {"type": "string"}},
                    "required": ["definition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        self.assertEqual(captured["url"], "https://example.test/v1/responses")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-key")
        self.assertEqual(captured["payload"]["model"], "gpt-test")
        self.assertEqual(captured["payload"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(payload["definition"], "to move quickly on foot")

    def test_openai_compatible_client_includes_reasoning_effort_when_configured(self) -> None:
        captured = {}

        def transport(url, payload, headers):
            captured["url"] = url
            captured["payload"] = payload
            captured["headers"] = headers
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps(
                                    {
                                        "definition": "to move quickly on foot",
                                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                        "cefr_level": "A1",
                                        "primary_domain": "general",
                                        "secondary_domains": [],
                                        "register": "neutral",
                                        "synonyms": ["jog"],
                                        "antonyms": ["walk"],
                                        "collocations": ["run fast"],
                                        "grammar_patterns": ["run + adverb"],
                                        "usage_note": "Common everyday verb.",
                                        "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                        "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                                        "confidence": 0.93,
                                    }
                                ),
                            }
                        ],
                    }
                ]
            }

        client = OpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            reasoning_effort="low",
            transport=transport,
        )

        client.generate_json(
            "hello",
            response_schema={
                "name": "test_schema",
                "schema": {
                    "type": "object",
                    "properties": {"definition": {"type": "string"}},
                    "required": ["definition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        self.assertEqual(captured["payload"]["reasoning"], {"effort": "low"})

    def test_node_openai_compatible_client_forwards_reasoning_none_and_json_schema(self) -> None:
        captured = {}

        def runner(payload):
            captured.update(payload)
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"definition": "ok"}),
                            }
                        ],
                    }
                ]
            }

        client = NodeOpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            reasoning_effort="none",
            runner=runner,
        )

        client.generate_json(
            "hello",
            response_schema={
                "name": "test_schema",
                "schema": {
                    "type": "object",
                    "properties": {"definition": {"type": "string"}},
                    "required": ["definition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        self.assertEqual(captured["reasoning_effort"], "none")
        self.assertEqual(captured["response_schema"]["name"], "test_schema")
        self.assertTrue(captured["response_schema"]["strict"])

    def test_node_openai_compatible_client_raises_when_schema_request_fails(self) -> None:
        def runner(payload):
            raise RuntimeError("502 Bad gateway")

        client = NodeOpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            runner=runner,
        )

        with self.assertRaisesRegex(RuntimeError, "502 Bad gateway"):
            client.generate_json(
                "hello",
                response_schema={
                    "name": "test_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"definition": {"type": "string"}},
                        "required": ["definition"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            )

    def test_openai_compatible_client_uses_sdk_client_when_provided(self) -> None:
        captured = {}

        def handler(payload):
            captured["payload"] = payload
            return {
                "output": [
                    {
                        "type": "message",
                        "content": [
                            {
                                "type": "output_text",
                                "text": json.dumps({"definition": "ok"}),
                            }
                        ],
                    }
                ]
            }

        client = OpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            client=_FakeOpenAIClient(handler),
            reasoning_effort="low",
        )

        payload = client.generate_json(
            "hello",
            response_schema={
                "name": "test_schema",
                "schema": {
                    "type": "object",
                    "properties": {"definition": {"type": "string"}},
                    "required": ["definition"],
                    "additionalProperties": False,
                },
                "strict": True,
            },
        )

        self.assertEqual(payload["definition"], "ok")
        self.assertEqual(captured["payload"]["text"]["format"]["type"], "json_schema")
        self.assertEqual(captured["payload"]["reasoning"], {"effort": "low"})

    def test_openai_compatible_client_raises_when_schema_request_fails(self) -> None:
        def handler(payload):
            raise RuntimeError("schema enforcement failed")

        client = OpenAICompatibleResponsesClient(
            endpoint="https://example.test/v1",
            api_key="secret-key",
            model="gpt-test",
            client=_FakeOpenAIClient(handler),
        )

        with self.assertRaisesRegex(RuntimeError, "schema enforcement failed"):
            client.generate_json(
                "hello",
                response_schema={
                    "name": "test_schema",
                    "schema": {
                        "type": "object",
                        "properties": {"definition": {"type": "string"}},
                        "required": ["definition"],
                        "additionalProperties": False,
                    },
                    "strict": True,
                },
            )

    def test_word_enrichment_response_schema_uses_anyof_for_nullable_fields(self) -> None:
        schema = _word_enrichment_response_schema()["schema"]
        item_schema = schema["properties"]["senses"]["items"]
        forms_schema = item_schema["properties"]["forms"]

        self.assertEqual(set(item_schema["required"]), set(item_schema["properties"]))

        single_schema = _single_sense_response_schema()["schema"]
        self.assertEqual(set(single_schema["required"]), set(single_schema["properties"]))

        self.assertIn("anyOf", forms_schema)
        self.assertNotIn("type", forms_schema)

        object_branch = next(branch for branch in forms_schema["anyOf"] if branch.get("type") == "object")
        self.assertEqual(
            object_branch["required"],
            ["plural_forms", "verb_forms", "comparative", "superlative", "derivations"],
        )
        verb_forms = object_branch["properties"]["verb_forms"]
        self.assertEqual(
            verb_forms["required"],
            ["base", "third_person_singular", "past", "past_participle", "gerund"],
        )
        self.assertFalse(verb_forms["additionalProperties"])
        self.assertIn("anyOf", object_branch["properties"]["comparative"])
        self.assertIn("anyOf", item_schema["properties"]["usage_note"])

    def test_real_provider_requires_endpoint_model_and_api_key(self) -> None:
        settings = LexiconSettings.from_env({"LEXICON_LLM_MODEL": "gpt-test"})

        with self.assertRaises(LexiconDependencyError):
            build_openai_compatible_enrichment_provider(settings=settings)

    def test_real_provider_maps_openai_compatible_json_to_enrichment_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_PROVIDER": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "definition": "to move quickly on foot",
                                            "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                            "cefr_level": "A1",
                                            "primary_domain": "general",
                                            "secondary_domains": [],
                                            "register": "neutral",
                                            "synonyms": ["jog"],
                                            "antonyms": ["walk"],
                                            "collocations": ["run fast"],
                                            "grammar_patterns": ["run + adverb"],
                                            "usage_note": "Common everyday verb.",
                                            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                            "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                                            "confidence": 0.91,
                                            "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                        }
                                    ),
                                }
                            ],
                        }
                    ]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            record = provider(
                lexeme=lexeme,
                sense=sense,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(record.definition, "to move quickly on foot")
            self.assertEqual(record.examples[0].sentence, "I run every morning.")
            self.assertEqual(record.model_name, "gpt-test")
            self.assertEqual(record.confidence, 0.91)

    def test_real_provider_honors_retry_budgets_for_single_sense_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            call_count = 0

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    return {
                        "output": [{
                            "type": "message",
                            "content": [{
                                "type": "output_text",
                                "text": json.dumps({
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "confidence": 0.91,
                                })
                            }]
                        }]
                    }
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "definition": "to move quickly on foot",
                                "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                "cefr_level": "A1",
                                "primary_domain": "general",
                                "secondary_domains": [],
                                "register": "neutral",
                                "synonyms": [],
                                "antonyms": [],
                                "collocations": [],
                                "grammar_patterns": [],
                                "usage_note": "Common everyday verb.",
                                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                "confusable_words": [],
                                "confidence": 0.91,
                                "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                transient_retries=0,
                validation_retries=1,
            )
            records = provider(
                lexeme=read_snapshot_inputs(snapshot_dir)[0][0],
                sense=read_snapshot_inputs(snapshot_dir)[1][0],
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(call_count, 2)
            self.assertEqual(records.sense_id, "sn_lx_run_1")

    def test_enrich_snapshot_per_word_forwards_retry_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )
            def fake_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del settings
                sense = senses[0]
                return WordJobOutcome(records=[EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id="en_sn_lx_run_1_v1",
                    sense_id=sense.sense_id,
                    definition="definition",
                    examples=[{"sentence": "I run every morning.", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note="note",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    translations=_test_translations(),
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                )], decision="keep_standard")

            with patch("tools.lexicon.enrich.build_word_enrichment_provider", return_value=fake_provider) as mocked_builder:
                enrich_snapshot(
                    snapshot_dir,
                    provider_mode="openai_compatible",
                    settings=settings,
                    transient_retries=4,
                    validation_retries=2,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                )

            self.assertEqual(mocked_builder.call_args.kwargs["transient_retries"], 4)
            self.assertEqual(mocked_builder.call_args.kwargs["validation_retries"], 2)

    def test_real_provider_rejects_missing_definition(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "definition"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_examples_without_sentence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"difficulty": "A1"}], "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "examples"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_parse_json_payload_text_salvages_code_fenced_object(self) -> None:
        payload = _parse_json_payload_text("```json\n{\"ok\": true}\n```")

        self.assertEqual(payload, {"ok": True})

    def test_real_provider_accepts_numeric_string_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "confidence": "0.9", "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."])})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            record = provider(
                lexeme=lexeme,
                sense=sense,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(record.confidence, 0.9)

    def test_real_provider_rejects_non_numeric_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "confidence": "high"})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "confidence"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_invalid_cefr_level(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "cefr_level": "beginner", "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "cefr_level"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_invalid_register(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "register": "casualish", "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "register"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_non_list_synonyms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "synonyms": "jog", "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "synonyms"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_malformed_forms(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "forms": {"plural_forms": "runs"}, "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "forms"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_provider_rejects_malformed_confusable_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                    "LEXICON_LLM_MODEL": "gpt-test",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )

            def transport(url, payload, headers):
                return {
                    "output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"definition": "to move quickly on foot", "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}], "confusable_words": [{"note": "Past tense form."}], "confidence": 0.9})}]}]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, client=_client_from_transport(transport))
            with self.assertRaisesRegex(RuntimeError, "confusable_words"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_node_provider_maps_openai_sdk_style_response_to_enrichment_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexeme, sense = read_snapshot_inputs(snapshot_dir)[0][0], read_snapshot_inputs(snapshot_dir)[1][0]
            settings = LexiconSettings.from_env(
                {
                    "LEXICON_LLM_BASE_URL": "https://api.nwai.cc",
                    "LEXICON_LLM_MODEL": "gpt-5.1",
                    "LEXICON_LLM_API_KEY": "secret-key",
                }
            )
            captured = {}

            def runner(payload):
                captured.update(payload)
                return {
                    "output_text": json.dumps(
                        {
                            "definition": "to move quickly on foot",
                            "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                            "cefr_level": "A1",
                            "primary_domain": "general",
                            "secondary_domains": [],
                            "register": "neutral",
                            "synonyms": ["jog"],
                            "antonyms": ["walk"],
                            "collocations": ["run fast"],
                            "grammar_patterns": ["run + adverb"],
                            "usage_note": "Common everyday verb.",
                            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                            "confusable_words": [{"word": "ran", "note": "Past tense form."}],
                            "confidence": 0.91,
                            "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                        }
                    )
                }

            provider = build_openai_compatible_node_enrichment_provider(settings=settings, runner=runner)
            record = provider(
                lexeme=lexeme,
                sense=sense,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(captured["base_url"], "https://api.nwai.cc")
            self.assertEqual(captured["api_key"], "secret-key")
            self.assertEqual(captured["model"], "gpt-5.1")
            self.assertIn("run", captured["prompt"])
            self.assertIn("learners", captured["system_prompt"].lower())
            self.assertEqual(record.definition, "to move quickly on foot")
            self.assertEqual(record.confidence, 0.91)

    def test_node_phrase_provider_maps_openai_sdk_style_response_to_phrase_outcome(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.nwai.cc",
                "LEXICON_LLM_MODEL": "gpt-5.1",
                "LEXICON_LLM_API_KEY": "secret-key",
            }
        )
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        captured = {}

        def runner(payload):
            captured.update(payload)
            return {
                "output_text": json.dumps(
                    {
                        "phrase_kind": "idiom",
                        "confidence": 0.91,
                        "senses": [
                            {
                                "definition": "used to wish someone good luck before a performance",
                                "part_of_speech": "phrase",
                                "examples": [{"sentence": "They told her to break a leg before the audition.", "difficulty": "B1"}],
                                "grammar_patterns": ["say + phrase"],
                                "usage_note": "Common before performances and public appearances.",
                                "translations": _test_translations(
                                    "used to wish someone good luck before a performance",
                                    "Common before performances and public appearances.",
                                    ["They told her to break a leg before the audition."],
                                ),
                            }
                        ],
                    }
                )
            }

        provider = build_openai_compatible_node_phrase_enrichment_provider(settings=settings, runner=runner)
        outcome = provider(
            lexeme=lexeme,
            senses=[],
            settings=settings,
            generated_at="2026-03-07T00:00:00Z",
            generation_run_id="run-123",
            prompt_version="v1",
        )

        self.assertEqual(captured["base_url"], "https://api.nwai.cc")
        self.assertEqual(captured["api_key"], "secret-key")
        self.assertEqual(captured["model"], "gpt-5.1")
        self.assertIn("Break a leg", captured["prompt"])
        self.assertEqual(outcome.decision, "keep_standard")
        self.assertEqual(len(outcome.records), 1)
        self.assertEqual(outcome.records[0].definition, "used to wish someone good luck before a performance")

    def test_auto_provider_uses_node_transport_when_configured(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.nwai.cc",
                "LEXICON_LLM_MODEL": "gpt-5.1",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_TRANSPORT": "node",
            }
        )

        sentinel_provider = object()
        with patch('tools.lexicon.enrich.build_openai_compatible_node_enrichment_provider', return_value=sentinel_provider) as mocked_builder:
            provider = build_enrichment_provider(settings=settings, provider_mode="auto")

        self.assertIs(provider, sentinel_provider)
        mocked_builder.assert_called_once()

    def test_auto_phrase_provider_uses_node_transport_when_configured(self) -> None:
        settings = LexiconSettings.from_env(
            {
                "LEXICON_LLM_BASE_URL": "https://api.nwai.cc",
                "LEXICON_LLM_MODEL": "gpt-5.1",
                "LEXICON_LLM_API_KEY": "secret-key",
                "LEXICON_LLM_TRANSPORT": "node",
            }
        )

        sentinel_provider = object()
        with patch('tools.lexicon.enrich.build_openai_compatible_node_phrase_enrichment_provider', return_value=sentinel_provider) as mocked_builder:
            provider = build_phrase_enrichment_provider(settings=settings, provider_mode="auto")

        self.assertIs(provider, sentinel_provider)
        mocked_builder.assert_called_once()

    def test_default_node_runner_times_out_cleanly(self) -> None:
        with patch('tools.lexicon.enrich.shutil.which', return_value='node'), \
             patch('tools.lexicon.enrich.Path.exists', return_value=True), \
             patch('tools.lexicon.enrich.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['node'], timeout=60)):
            with self.assertRaisesRegex(RuntimeError, 'timed out after 60 seconds'):
                _default_node_runner({'prompt': 'hello'})

    def test_default_node_runner_uses_payload_timeout_seconds(self) -> None:
        with patch('tools.lexicon.enrich.shutil.which', return_value='node'), \
             patch('tools.lexicon.enrich.Path.exists', return_value=True), \
             patch('tools.lexicon.enrich.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['node'], timeout=90)) as mocked_run:
            with self.assertRaisesRegex(RuntimeError, 'timed out after 90 seconds'):
                _default_node_runner({'prompt': 'hello'}, timeout_seconds=90)

        self.assertEqual(mocked_run.call_args.kwargs['timeout'], 90)

    def test_parse_json_payload_text_salvages_markdown_fenced_output(self) -> None:
        payload = _parse_json_payload_text(
            "Here is the JSON\n```json\n{\"ok\": true}\n```"
        )

        self.assertEqual(payload, {'ok': True})

    def test_parse_json_payload_text_wraps_malformed_extracted_json(self) -> None:
        with self.assertRaisesRegex(RuntimeError, 'JSON object not found in model output'):
            _parse_json_payload_text('prefix {"broken" 1} suffix')

    def test_enrich_snapshot_per_word_writes_partial_output_and_checkpoint_before_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "beta":
                    raise RuntimeError("gateway timeout")
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            with self.assertRaisesRegex(RuntimeError, "beta: gateway timeout"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    max_failures=1,
                )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual([row["entry_id"] for row in compiled_rows], ["lx_alpha"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints if row["status"] == "completed"], ["lx_alpha"])
            self.assertEqual([row["lexeme_id"] for row in failures], ["lx_beta"])

    def test_enrich_snapshot_per_word_resume_skips_completed_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            resumed_lemmas = []

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def first_word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "beta":
                    raise RuntimeError("gateway timeout")
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            with self.assertRaisesRegex(RuntimeError, "beta: gateway timeout"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=first_word_provider,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    max_failures=1,
                )

            def resumed_word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                resumed_lemmas.append(lexeme.lemma)
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=resumed_word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
            )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(resumed_lemmas, ["beta"])
            self.assertEqual(sorted(row["entry_id"] for row in compiled_rows), ["lx_alpha", "lx_beta"])
            self.assertEqual(sorted(record["entry_id"] for record in records), ["lx_alpha", "lx_beta"])

    def test_enrich_snapshot_per_word_stops_after_max_new_completed_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_gamma",
                        "lemma": "gamma",
                        "language": "en",
                        "wordfreq_rank": 30,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_gamma_1",
                        "lexeme_id": "lx_gamma",
                        "wn_synset_id": "gamma.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "gamma sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            seen_lemmas: list[str] = []

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                seen_lemmas.append(lexeme.lemma)
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                max_new_completed_lexemes=2,
            )

            checkpoints = [json.loads(line) for line in (snapshot_dir / "enrich.checkpoint.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(seen_lemmas, ["alpha", "beta"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_alpha", "lx_beta"])
            self.assertEqual(sorted(record["entry_id"] for record in records), ["lx_alpha", "lx_beta"])

    def test_enrich_snapshot_per_word_flushes_success_immediately_after_prior_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_gamma",
                        "lemma": "gamma",
                        "language": "en",
                        "wordfreq_rank": 30,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_gamma_1",
                        "lexeme_id": "lx_gamma",
                        "wn_synset_id": "gamma.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "gamma sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            processed_lemmas: list[str] = []

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del settings
                processed_lemmas.append(lexeme.lemma)
                if lexeme.lemma == "alpha":
                    raise RuntimeError("gateway timeout")
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            with self.assertRaisesRegex(RuntimeError, "alpha: gateway timeout"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    max_new_completed_lexemes=1,
                )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            decisions = [json.loads(line) for line in (snapshot_dir / "enrich.decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(processed_lemmas, ["alpha", "beta"])
            self.assertEqual([row["entry_id"] for row in compiled_rows], ["lx_beta"])
            self.assertEqual([row["lexeme_id"] for row in decisions], ["lx_beta"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_beta"])
            self.assertEqual([row["lexeme_id"] for row in failures], ["lx_alpha"])

    def test_enrich_snapshot_per_word_persists_discard_decisions_without_enrichment_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_is",
                    "lemma": "is",
                    "language": "en",
                    "wordfreq_rank": 12,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_is_1",
                    "lexeme_id": "lx_is",
                    "wn_synset_id": "be.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "exist or be",
                    "selection_reason": "common learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                self.assertEqual(lexeme.lemma, "is")
                return []

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
            )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in (snapshot_dir / "enrich.checkpoint.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            decisions = [json.loads(line) for line in (snapshot_dir / "enrich.decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(records, [])
            self.assertEqual(compiled_rows, [])
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(checkpoints[0]["lexeme_id"], "lx_is")
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["lexeme_id"], "lx_is")
            self.assertEqual(decisions[0]["lemma"], "is")
            self.assertEqual(decisions[0]["decision"], "discard")
            self.assertEqual(decisions[0]["accepted_sense_count"], 0)

    def test_enrich_snapshot_per_word_resume_skips_completed_discarded_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_is",
                    "lemma": "is",
                    "language": "en",
                    "wordfreq_rank": 12,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_is_1",
                    "lexeme_id": "lx_is",
                    "wn_synset_id": "be.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "exist or be",
                    "selection_reason": "common learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            resumed_lemmas: list[str] = []

            def first_word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                return []

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=first_word_provider,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
            )

            def resumed_word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                resumed_lemmas.append(lexeme.lemma)
                return []

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=resumed_word_provider,
                resume=True,
            )

            decisions = [json.loads(line) for line in (snapshot_dir / "enrich.decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(records, [])
            self.assertEqual(resumed_lemmas, [])
            self.assertEqual(len(decisions), 1)
            self.assertEqual(decisions[0]["decision"], "discard")

    def test_enrich_snapshot_per_word_resume_stops_after_max_new_completed_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_gamma",
                        "lemma": "gamma",
                        "language": "en",
                        "wordfreq_rank": 30,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_gamma_1",
                        "lexeme_id": "lx_gamma",
                        "wn_synset_id": "gamma.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "gamma sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                json.dumps({
                    "lexeme_id": "lx_alpha",
                    "lemma": "alpha",
                    "status": "completed",
                    "generation_run_id": "old-run",
                    "completed_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "words.enriched.jsonl").write_text(
                json.dumps({
                    "schema_version": "1.1.0",
                    "entry_id": "lx_alpha",
                    "entry_type": "word",
                    "normalized_form": "alpha",
                    "source_provenance": [{"source": "wordfreq"}],
                    "entity_category": "general",
                    "word": "alpha",
                    "part_of_speech": ["noun"],
                    "cefr_level": "A1",
                    "frequency_rank": 10,
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "senses": [{
                        "sense_id": "sn_lx_alpha_1",
                        "wn_synset_id": None,
                        "pos": "noun",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "definition for alpha",
                        "examples": [{"sentence": "alpha example", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "note for alpha",
                        "enrichment_id": "en_sn_lx_alpha_1",
                        "generation_run_id": "old-run",
                        "model_name": "test-provider",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-03-07T00:00:00Z",
                        "translations": _test_translations("definition for alpha", "note for alpha", ["alpha example"]),
                    }],
                    "confusable_words": [],
                    "generated_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            failures_path.write_text("", encoding="utf-8")
            seen_lemmas: list[str] = []

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                seen_lemmas.append(lexeme.lemma)
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
                max_new_completed_lexemes=1,
            )

            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(seen_lemmas, ["beta"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_alpha", "lx_beta"])
            self.assertEqual(sorted(record["entry_id"] for record in records), ["lx_alpha", "lx_beta"])


if __name__ == "__main__":
    unittest.main()


class EnrichPerWordModeTests(unittest.TestCase):
    def _write_snapshot(self, snapshot_dir: Path) -> None:
        (snapshot_dir / "lexemes.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "language": "en",
                    "wordfreq_rank": 5,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-07T00:00:00Z",
                }),
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_play",
                    "lemma": "play",
                    "language": "en",
                    "wordfreq_rank": 8,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-07T00:00:00Z",
                }),
            ]) + "\n",
            encoding="utf-8",
        )
        (snapshot_dir / "senses.jsonl").write_text(
            "\n".join([
                json.dumps({
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_run_1",
                    "lexeme_id": "lx_run",
                    "wn_synset_id": "run.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "move fast by using your legs",
                    "selection_reason": "common learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }),
                json.dumps({
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_run_2",
                    "lexeme_id": "lx_run",
                    "wn_synset_id": "run.n.01",
                    "part_of_speech": "noun",
                    "canonical_gloss": "a period of running",
                    "selection_reason": "common learner sense",
                    "sense_order": 2,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }),
                json.dumps({
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_play_1",
                    "lexeme_id": "lx_play",
                    "wn_synset_id": "play.v.01",
                    "part_of_speech": "verb",
                    "canonical_gloss": "engage in activity for enjoyment",
                    "selection_reason": "common learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-07T00:00:00Z",
                }),
            ]) + "\n",
            encoding="utf-8",
        )

    def _write_resume_modes_snapshot(self, snapshot_dir: Path) -> None:
        (snapshot_dir / "lexemes.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_alpha",
                            "lemma": "alpha",
                            "language": "en",
                            "wordfreq_rank": 1,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_run",
                            "lemma": "run",
                            "language": "en",
                            "wordfreq_rank": 2,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "lexeme_id": "lx_play",
                            "lemma": "play",
                            "language": "en",
                            "wordfreq_rank": 3,
                            "is_wordnet_backed": True,
                            "source_refs": ["wordnet", "wordfreq"],
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )
        (snapshot_dir / "senses.jsonl").write_text(
            "\n".join(
                [
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_alpha_1",
                            "lexeme_id": "lx_alpha",
                            "wn_synset_id": "alpha.n.01",
                            "part_of_speech": "noun",
                            "canonical_gloss": "alpha sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_run_1",
                            "lexeme_id": "lx_run",
                            "wn_synset_id": "run.v.01",
                            "part_of_speech": "verb",
                            "canonical_gloss": "run sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                    json.dumps(
                        {
                            "snapshot_id": "snap-1",
                            "sense_id": "sn_lx_play_1",
                            "lexeme_id": "lx_play",
                            "wn_synset_id": "play.v.01",
                            "part_of_speech": "verb",
                            "canonical_gloss": "play sense",
                            "selection_reason": "common learner sense",
                            "sense_order": 1,
                            "is_high_polysemy": False,
                            "created_at": "2026-03-07T00:00:00Z",
                        }
                    ),
                ]
            )
            + "\n",
            encoding="utf-8",
        )

    def _response(self, sense_id: str, definition: str) -> dict:
        return {
            "sense_id": sense_id,
            "definition": definition,
            "examples": [{"sentence": f"Example for {sense_id}", "difficulty": "A1"}],
            "cefr_level": "A1",
            "primary_domain": "general",
            "secondary_domains": [],
            "register": "neutral",
            "synonyms": [],
            "antonyms": [],
            "collocations": [],
            "grammar_patterns": [],
            "usage_note": "Helpful note.",
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "confusable_words": [],
            "confidence": 0.9,
        }

    def test_build_word_enrichment_prompt_uses_grounding_and_adaptive_meaning_cap(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=run_lexeme, senses=run_senses)

            self.assertIn("sn_lx_run_1", prompt)
            self.assertIn("sn_lx_run_2", prompt)
            self.assertIn("grounding context", prompt.lower())
            self.assertIn("at most 5 learner-friendly meanings", prompt.lower())
            self.assertIn("do not return internal meaning ids", prompt.lower())
            self.assertIn("keep_derived_special", prompt.lower())

    def test_build_word_enrichment_prompt_word_only_mode_omits_grounding_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=run_lexeme, senses=run_senses, prompt_mode="word_only")

            self.assertNotIn("grounding context", prompt.lower())
            self.assertNotIn("sn_lx_run_1", prompt.lower())
            self.assertNotIn("sn_lx_run_2", prompt.lower())
            self.assertIn("do not return internal meaning ids", prompt.lower())
            self.assertIn("english word 'run'", prompt.lower())
            self.assertIn("return only valid content for the required fields", prompt.lower())
            self.assertIn("at most 5 learner-friendly meanings", prompt.lower())
            self.assertIn("keep_standard", prompt.lower())

    def test_build_word_enrichment_prompt_front_loads_stable_rules_before_word_specific_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=run_lexeme, senses=run_senses, prompt_mode="word_only")
            stable_index = prompt.lower().find("select at most")
            dynamic_index = prompt.lower().find("english word 'run'")

            self.assertNotEqual(stable_index, -1)
            self.assertNotEqual(dynamic_index, -1)
            self.assertLess(stable_index, dynamic_index)

    def test_enrich_snapshot_per_word_mode_writes_compiled_words_jsonl_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                return [
                    EnrichmentRecord(
                        snapshot_id=sense.snapshot_id,
                        enrichment_id=f"en_{sense.sense_id}_v1",
                        sense_id=sense.sense_id,
                        definition=f"def:{sense.sense_id}",
                        examples=[{"sentence": f"{lexeme.lemma}:{sense.sense_id}", "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note="note",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                    for sense in senses
                ]

            records = enrich_snapshot(snapshot_dir, mode="per_word", word_provider=word_provider, max_concurrency=2, generated_at="2026-03-07T00:00:00Z", generation_run_id="run-123")

            self.assertEqual(sorted(record["entry_id"] for record in records), ["lx_play", "lx_run"])
            payload = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(sorted(row["entry_id"] for row in payload), ["lx_play", "lx_run"])

    def test_enrich_snapshot_per_word_mode_flushes_in_completion_order_under_parallelism(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "run":
                    time.sleep(0.05)
                return [
                    EnrichmentRecord(
                        snapshot_id=sense.snapshot_id,
                        enrichment_id=f"en_{sense.sense_id}_v1",
                        sense_id=sense.sense_id,
                        definition=f"def:{sense.sense_id}",
                        examples=[{"sentence": f"{lexeme.lemma}:{sense.sense_id}", "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note="note",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                    for sense in senses
                ]

            records = enrich_snapshot(snapshot_dir, mode="per_word", word_provider=word_provider, max_concurrency=2)
            payload = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual([record["entry_id"] for record in records], ["lx_play", "lx_run"])
            self.assertEqual([row["entry_id"] for row in payload], ["lx_play", "lx_run"])

    def test_enrich_snapshot_per_word_mode_reports_failed_lexeme(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "run":
                    raise RuntimeError("gateway timeout")
                return [
                    EnrichmentRecord(
                        snapshot_id=senses[0].snapshot_id,
                        enrichment_id="en_ok",
                        sense_id=senses[0].sense_id,
                        definition="ok",
                        examples=[{"sentence": "ok", "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note="ok",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                ]

            with self.assertRaisesRegex(RuntimeError, "run: gateway timeout"):
                enrich_snapshot(snapshot_dir, mode="per_word", word_provider=word_provider, max_concurrency=2)

    def test_build_word_enrichment_prompt_tightens_meaning_cap_for_lower_frequency_words(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            low_priority = run_lexeme.__class__(**{**run_lexeme.to_dict(), "wordfreq_rank": 12000})
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=low_priority, senses=run_senses)

            self.assertIn("at most 4 learner-friendly meanings", prompt.lower())

    def test_build_word_enrichment_prompt_repeats_hard_output_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=run_lexeme, senses=run_senses).lower()

            self.assertIn("json object only", prompt)
            self.assertIn("invalid if the senses array contains more than 5 items", prompt)
            self.assertIn("if more than 5 candidates seem useful, keep only the strongest 5", prompt)

    def test_build_word_enrichment_prompt_adds_variant_specific_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            variant_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "meeting",
                "lexeme_id": "lx_meeting",
                "entry_id": "lx_meeting",
                "normalized_form": "meeting",
                "is_variant_with_distinct_meanings": True,
                "variant_base_form": "meet",
                "variant_relationship": "lexicalized_form",
            })
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=variant_lexeme, senses=run_senses).lower()

            self.assertIn("another form of the base word 'meet'", prompt)
            self.assertIn("do not repeat the ordinary meanings already covered by the base word", prompt)
            self.assertIn("generate only the meanings that are distinct or special to 'meeting'", prompt)
            self.assertIn("include a short usage note that says it is another form of 'meet'", prompt)

    def test_build_word_enrichment_prompt_hardens_distinct_derived_variant_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            distinct_variant_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "building",
                "lexeme_id": "lx_building",
                "entry_id": "lx_building",
                "normalized_form": "building",
                "is_variant_with_distinct_meanings": True,
                "variant_base_form": "build",
                "variant_relationship": "distinct_derived_form",
                "variant_prompt_note": "Focus on the standalone noun meanings, not the ordinary act of build.",
                "variant_source": "dataset",
            })
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=distinct_variant_lexeme, senses=run_senses).lower()

            self.assertIn("related to the base word 'build'", prompt)
            self.assertIn("do not restate the ordinary inflectional or base-word meanings", prompt)
            self.assertIn("only the standalone meanings and uses that justify keeping 'building' as its own entry", prompt)
            self.assertIn("focus on the standalone noun meanings, not the ordinary act of build", prompt)

    def test_build_word_enrichment_prompt_adds_entity_category_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            place_lexeme = run_lexeme.__class__(**{
                **run_lexeme.to_dict(),
                "lemma": "kinshasa",
                "lexeme_id": "lx_kinshasa",
                "entry_id": "lx_kinshasa",
                "normalized_form": "kinshasa",
                "entity_category": "place",
            })
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=place_lexeme, senses=run_senses).lower()

            self.assertIn("categorized as 'place'", prompt)
            self.assertIn("specific named-entity or specialized-entity use", prompt)
            self.assertIn("do not broaden it into unrelated ordinary meanings", prompt)

    def test_real_word_provider_accepts_subset_of_grounded_senses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            def transport(url, payload, headers):
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "sense_id": "sn_lx_run_1",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "cefr_level": "A1",
                                    "primary_domain": "general",
                                    "secondary_domains": [],
                                    "register": "neutral",
                                    "synonyms": ["jog"],
                                    "antonyms": ["walk"],
                                    "collocations": ["run fast"],
                                    "grammar_patterns": ["run + adverb"],
                                    "usage_note": "Common everyday verb.",
                                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                    "confusable_words": [],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."])
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            records = provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])

    def test_real_word_provider_uses_word_only_prompt_mode_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            prompts: list[str] = []

            def transport(url, payload, headers):
                prompts.append(str(payload.get("input") or ""))
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "decision": "keep_standard",
                                "discard_reason": None,
                                "base_word": None,
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "part_of_speech": "verb",
                                    "sense_kind": "standard_meaning",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "cefr_level": "A1",
                                    "primary_domain": "general",
                                    "secondary_domains": [],
                                    "register": "neutral",
                                    "synonyms": ["jog"],
                                    "antonyms": ["walk"],
                                    "collocations": ["run fast"],
                                    "grammar_patterns": ["run + adverb"],
                                    "usage_note": "Common everyday verb.",
                                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                                    "confusable_words": [],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(len(prompts), 1)
            self.assertNotIn("grounding context", prompts[0].lower())
            self.assertNotIn("sn_lx_run_1", prompts[0].lower())

    def test_real_word_provider_rejects_too_many_selected_senses_for_frequency_band(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            low_priority = run_lexeme.__class__(**{**run_lexeme.to_dict(), "wordfreq_rank": 12000})
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            extra_senses = [run_senses[0].__class__(**{**run_senses[0].to_dict(), "sense_id": f"sn_lx_run_extra_{idx}", "sense_order": idx + 2}) for idx in range(4)]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            def transport(url, payload, headers):
                rows = []
                for sense in run_senses + extra_senses:
                    rows.append({
                        "sense_id": sense.sense_id,
                        "definition": "x",
                        "examples": [{"sentence": "x", "difficulty": "A1"}],
                        "confidence": 0.9,
                    })
                return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"phonetics": _test_phonetics(), "senses": rows})}]}]}

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            with self.assertRaisesRegex(RuntimeError, "at most 4 learner-friendly meanings"):
                provider(
                    lexeme=low_priority,
                    senses=run_senses + extra_senses,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

    def test_real_word_provider_retries_transient_timeouts_before_failing_word(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            call_count = 0

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                if call_count < 3:
                    raise RuntimeError("Node OpenAI-compatible transport timed out after 60 seconds")
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "sense_id": "sn_lx_run_1",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            records = provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(call_count, 3)
            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])

    def test_real_word_provider_repairs_twice_for_schema_only_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            call_count = 0
            prompts = []

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                prompts.append(payload["input"])
                if call_count == 1:
                    return {
                        "output": [{
                            "type": "message",
                            "content": [{
                                "type": "output_text",
                                "text": json.dumps({
                                    "phonetics": _test_phonetics(),
                                    "senses": [{
                                        "sense_id": "sn_lx_run_1",
                                        "definition": "to move quickly on foot",
                                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                        "confidence": 0.91,
                                        "translations": {
                                            "zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": ["zh:one"]},
                                            "es": {"definition": "es:def", "usage_note": "es:note", "examples": ["es:one"]},
                                            "ar": {"definition": "ar:def", "usage_note": "ar:note", "examples": ["ar:one"]},
                                            "ja": {"definition": "ja:def", "usage_note": "ja:note", "examples": ["ja:one"]}
                                        },
                                    }]
                                })
                            }]
                        }]
                    }
                if call_count == 2:
                    return {
                        "output": [{
                            "type": "message",
                            "content": [{
                                "type": "output_text",
                                "text": json.dumps({
                                    "phonetics": _test_phonetics(),
                                    "senses": [{
                                        "sense_id": "sn_lx_run_1",
                                        "definition": "to move quickly on foot",
                                        "examples": [
                                            {"sentence": "I run every morning.", "difficulty": "A1"},
                                            {"sentence": "She runs every day.", "difficulty": "A1"}
                                        ],
                                        "confidence": 0.91,
                                        "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["only one example"]),
                                    }]
                                })
                            }]
                        }]
                    }
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "sense_id": "sn_lx_run_1",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            records = provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(call_count, 3)
            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])
            self.assertIn("repair the previous learner-facing enrichment response", prompts[1].lower())
            self.assertIn("repair the previous learner-facing enrichment response", prompts[2].lower())

    def test_real_word_provider_repairs_once_when_model_returns_too_many_senses(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            low_priority = run_lexeme.__class__(**{**run_lexeme.to_dict(), "wordfreq_rank": 12000})
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            extra_senses = [run_senses[0].__class__(**{**run_senses[0].to_dict(), "sense_id": f"sn_lx_run_extra_{idx}", "sense_order": idx + 2}) for idx in range(4)]
            all_senses = run_senses + extra_senses
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            prompts = []
            call_count = 0

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                prompts.append(payload["input"])
                if call_count == 1:
                    rows = []
                    for sense in all_senses:
                        rows.append({
                            "sense_id": sense.sense_id,
                            "definition": "x",
                            "examples": [{"sentence": "x", "difficulty": "A1"}],
                            "confidence": 0.9,
                        })
                    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"phonetics": _test_phonetics(), "senses": rows})}]}]}
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "sense_id": "sn_lx_run_1",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            records = provider(
                lexeme=low_priority,
                senses=all_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])
            self.assertEqual(call_count, 2)
            self.assertIn("repair the previous learner-facing enrichment response", prompts[1].lower())
            self.assertIn("at most 4 learner-friendly meanings", prompts[1].lower())

    def test_real_word_provider_repairs_multiple_times_for_repairable_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            prompts = []
            call_count = 0

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                prompts.append(payload["input"])
                if call_count == 1:
                    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": "```json\n{\"senses\": [{\"sense_id\": \"sn_lx_run_1\", \"definition\": \"to move quickly on foot\"}]}\n```"}]}]}
                if call_count == 2:
                    return {
                        "output": [{
                            "type": "message",
                            "content": [{
                                "type": "output_text",
                                "text": json.dumps({
                                    "phonetics": _test_phonetics(),
                                    "senses": [{
                                        "sense_id": "sn_lx_run_1",
                                        "definition": "to move quickly on foot",
                                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                        "confidence": 0.91,
                                        "translations": {"zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": ["zh:one", "zh:two"]}},
                                    }]
                                })
                            }]
                        }]
                    }
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
                                "phonetics": _test_phonetics(),
                                "senses": [{
                                    "sense_id": "sn_lx_run_1",
                                    "definition": "to move quickly on foot",
                                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                                    "confidence": 0.91,
                                    "translations": _test_translations("to move quickly on foot", "Common everyday verb.", ["I run every morning."]),
                                }]
                            })
                        }]
                    }]
                }

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            records = provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])
            self.assertEqual(call_count, 3)
            self.assertIn("repair the previous learner-facing enrichment response", prompts[1].lower())
            self.assertIn("repair the previous learner-facing enrichment response", prompts[2].lower())

    def test_real_word_provider_does_not_retry_transport_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            call_count = 0

            def transport(url, payload, headers):
                nonlocal call_count
                call_count += 1
                raise RuntimeError("OpenAI-compatible endpoint request failed with status 403: blocked")

            provider = build_openai_compatible_word_enrichment_provider(
                settings=settings,
                client=_client_from_transport(transport),
                validation_retries=2,
            )
            with self.assertRaisesRegex(RuntimeError, "status 403"):
                provider(
                    lexeme=run_lexeme,
                    senses=run_senses,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

            self.assertEqual(call_count, 1)

    def test_enrich_snapshot_per_word_resume_reconciles_uncheckpointed_output_before_retry(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text("", encoding="utf-8")
            failures_path.write_text(
                json.dumps({
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "status": "failed",
                    "generation_run_id": "failed-run",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "words.enriched.jsonl").write_text(
                json.dumps({
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
                    "senses": [{
                        "sense_id": "sn_lx_run_1",
                        "wn_synset_id": None,
                        "pos": "verb",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "dangling",
                        "examples": [{"sentence": "dangling", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "dangling",
                        "enrichment_id": "en_dangling",
                        "generation_run_id": "dangling-run",
                        "model_name": "test-provider",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-03-07T00:00:00Z",
                        "translations": {},
                    }],
                    "confusable_words": [],
                    "generated_at": "2026-03-07T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                called_lemmas.append(lexeme.lemma)
                return [
                    EnrichmentRecord(
                        snapshot_id=sense.snapshot_id,
                        enrichment_id=f"en_{sense.sense_id}",
                        sense_id=sense.sense_id,
                        definition=f"definition for {lexeme.lemma}",
                        examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note=f"note for {lexeme.lemma}",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                    for sense in senses
                ]

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
            )

            self.assertEqual(called_lemmas, ["run", "play"])
            self.assertEqual(sorted(record["entry_id"] for record in records), ["lx_play", "lx_run"])
            payload = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(sorted(row["entry_id"] for row in payload), ["lx_play", "lx_run"])
            self.assertEqual(sum(1 for row in payload if row["entry_id"] == "lx_run"), 1)

    def test_enrich_snapshot_per_word_resume_retries_unresolved_failed_lexemes_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "status": "completed",
                        "generation_run_id": "completed-alpha",
                        "completed_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            failures_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "lexeme_id": "lx_alpha",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "lemma": "alpha",
                                "display_form": "alpha",
                                "normalized_form": "alpha",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-alpha",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                        json.dumps(
                            {
                                "lexeme_id": "lx_run",
                                "entry_id": "lx_run",
                                "entry_type": "word",
                                "lemma": "run",
                                "display_form": "run",
                                "normalized_form": "run",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-run",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                called_lemmas.append(lexeme.lemma)
                return []

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
            )

            self.assertEqual(called_lemmas, ["run", "play"])

    def test_enrich_snapshot_per_word_resume_does_not_load_failures_without_failure_mode_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "status": "completed",
                        "generation_run_id": "completed-alpha",
                        "completed_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            failures_path.write_text(
                json.dumps(
                    {
                        "lexeme_id": "lx_run",
                        "entry_id": "lx_run",
                        "entry_type": "word",
                        "lemma": "run",
                        "display_form": "run",
                        "normalized_form": "run",
                        "phrase_kind": None,
                        "status": "failed",
                        "generation_run_id": "failed-run",
                        "failed_at": "2026-03-07T00:00:00Z",
                        "error": "gateway timeout",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                called_lemmas.append(lexeme.lemma)
                return []

            with patch("tools.lexicon.enrich._load_failed_lexeme_ids", side_effect=AssertionError("should not load failures")):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    resume=True,
                )

            self.assertEqual(called_lemmas, ["run", "play"])

    def test_enrich_snapshot_per_word_resume_skip_failed_excludes_unresolved_failed_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "status": "completed",
                        "generation_run_id": "completed-alpha",
                        "completed_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            failures_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "lexeme_id": "lx_alpha",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "lemma": "alpha",
                                "display_form": "alpha",
                                "normalized_form": "alpha",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-alpha",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                        json.dumps(
                            {
                                "lexeme_id": "lx_run",
                                "entry_id": "lx_run",
                                "entry_type": "word",
                                "lemma": "run",
                                "display_form": "run",
                                "normalized_form": "run",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-run",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                called_lemmas.append(lexeme.lemma)
                return []

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
                skip_failed=True,
            )

            self.assertEqual(called_lemmas, ["play"])

    def test_enrich_snapshot_per_word_resume_retry_failed_only_schedules_only_unresolved_failed_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                json.dumps(
                    {
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "status": "completed",
                        "generation_run_id": "completed-alpha",
                        "completed_at": "2026-03-07T00:00:00Z",
                    }
                )
                + "\n",
                encoding="utf-8",
            )
            failures_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "lexeme_id": "lx_alpha",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "lemma": "alpha",
                                "display_form": "alpha",
                                "normalized_form": "alpha",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-alpha",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                        json.dumps(
                            {
                                "lexeme_id": "lx_run",
                                "entry_id": "lx_run",
                                "entry_type": "word",
                                "lemma": "run",
                                "display_form": "run",
                                "normalized_form": "run",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-run",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                called_lemmas.append(lexeme.lemma)
                return []

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
                retry_failed_only=True,
            )

            self.assertEqual(called_lemmas, ["run"])

    def test_enrich_snapshot_per_word_resume_retry_failed_only_dedupes_failure_history_and_preserves_rows(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_resume_modes_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            checkpoint_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "lexeme_id": "lx_alpha",
                                "lemma": "alpha",
                                "status": "completed",
                                "generation_run_id": "completed-alpha",
                                "completed_at": "2026-03-07T00:00:00Z",
                            }
                        )
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            failures_path.write_text(
                "\n".join(
                    [
                        json.dumps(
                            {
                                "lexeme_id": "lx_alpha",
                                "entry_id": "lx_alpha",
                                "entry_type": "word",
                                "lemma": "alpha",
                                "display_form": "alpha",
                                "normalized_form": "alpha",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-alpha",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                        json.dumps(
                            {
                                "lexeme_id": "lx_run",
                                "entry_id": "lx_run",
                                "entry_type": "word",
                                "lemma": "run",
                                "display_form": "run",
                                "normalized_form": "run",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-run-1",
                                "failed_at": "2026-03-07T00:00:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                        json.dumps(
                            {
                                "lexeme_id": "lx_run",
                                "entry_id": "lx_run",
                                "entry_type": "word",
                                "lemma": "run",
                                "display_form": "run",
                                "normalized_form": "run",
                                "phrase_kind": None,
                                "status": "failed",
                                "generation_run_id": "failed-run-2",
                                "failed_at": "2026-03-07T00:10:00Z",
                                "error": "gateway timeout",
                            }
                        ),
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            called_lemmas: list[str] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                called_lemmas.append(lexeme.lemma)
                return []

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
                retry_failed_only=True,
            )

            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(called_lemmas, ["run"])
            self.assertEqual([row["lexeme_id"] for row in failures], ["lx_alpha", "lx_run", "lx_run"])
            self.assertEqual([row["generation_run_id"] for row in failures], ["failed-alpha", "failed-run-1", "failed-run-2"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_alpha", "lx_run"])

    def test_enrich_snapshot_rejects_retry_failed_only_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)

            with self.assertRaises(ValueError):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=lambda **kwargs: [],
                    retry_failed_only=True,
                )

    def test_run_enrichment_rejects_retry_failed_only_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)

            with self.assertRaises(ValueError):
                run_enrichment(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=lambda **kwargs: [],
                    retry_failed_only=True,
                )

    def test_enrich_snapshot_rejects_skip_failed_without_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)

            with self.assertRaises(ValueError):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=lambda **kwargs: [],
                    skip_failed=True,
                )

    def test_enrich_snapshot_rejects_retry_failed_only_with_skip_failed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)

            with self.assertRaises(ValueError):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=lambda **kwargs: [],
                    resume=True,
                    retry_failed_only=True,
                    skip_failed=True,
                )

    def test_enrich_snapshot_per_word_failure_flushes_later_successes_before_raise(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "play":
                    return [
                        EnrichmentRecord(
                            snapshot_id=senses[0].snapshot_id,
                            enrichment_id="en_play",
                            sense_id=senses[0].sense_id,
                            definition="play ok",
                            examples=[{"sentence": "play ok", "difficulty": "A1"}],
                            cefr_level="A1",
                            primary_domain="general",
                            secondary_domains=[],
                            register="neutral",
                            synonyms=[],
                            antonyms=[],
                            collocations=[],
                            grammar_patterns=[],
                            usage_note="ok",
                            forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                            confusable_words=[],
                            model_name="test-provider",
                            prompt_version=prompt_version,
                            generation_run_id=generation_run_id,
                            confidence=0.9,
                            review_status="draft",
                            generated_at=generated_at,
                        )
                    ]
                time.sleep(0.05)
                raise RuntimeError("gateway timeout")

            with self.assertRaisesRegex(RuntimeError, "run: gateway timeout"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    max_concurrency=2,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    max_failures=1,
                    request_delay_seconds=0.0,
                )

            payload = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([row["entry_id"] for row in payload], ["lx_play"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_play"])

    def test_enrich_snapshot_per_word_resume_appends_failure_history_on_repeat_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            failures_path.write_text(
                json.dumps({
                    "lexeme_id": "lx_run",
                    "entry_id": "lx_run",
                    "entry_type": "word",
                    "lemma": "run",
                    "display_form": "run",
                    "normalized_form": "run",
                    "phrase_kind": None,
                    "status": "failed",
                    "generation_run_id": "failed-run-1",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }) + "\n",
                encoding="utf-8",
            )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, prompt_version
                if lexeme.lemma == "run":
                    raise RuntimeError(f"repeat failure for {generation_run_id}")
                return []

            with self.assertRaisesRegex(RuntimeError, "run: repeat failure"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    failures_output=failures_path,
                    resume=True,
                    max_failures=1,
                )

            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([row["lexeme_id"] for row in failures], ["lx_run", "lx_run"])
            self.assertEqual([row["generation_run_id"] for row in failures], ["failed-run-1", failures[1]["generation_run_id"]])

    def test_enrich_snapshot_per_word_resume_keeps_append_only_failure_history_after_later_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"
            failures_path.write_text(
                json.dumps({
                    "lexeme_id": "lx_run",
                    "entry_id": "lx_run",
                    "entry_type": "word",
                    "lemma": "run",
                    "display_form": "run",
                    "normalized_form": "run",
                    "phrase_kind": None,
                    "status": "failed",
                    "generation_run_id": "failed-run-1",
                    "failed_at": "2026-03-07T00:00:00Z",
                    "error": "gateway timeout",
                }) + "\n",
                encoding="utf-8",
            )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del settings
                return [
                    EnrichmentRecord(
                        snapshot_id=sense.snapshot_id,
                        enrichment_id=f"en_{sense.sense_id}",
                        sense_id=sense.sense_id,
                        definition=f"definition for {lexeme.lemma}",
                        examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note=f"note for {lexeme.lemma}",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                    for sense in senses
                ]

            records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
                max_new_completed_lexemes=1,
            )

            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            decisions = [json.loads(line) for line in (snapshot_dir / "enrich.decisions.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual([row["lexeme_id"] for row in failures], ["lx_run"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_run"])
            self.assertEqual([row["lexeme_id"] for row in decisions], ["lx_run"])
            self.assertEqual([row["entry_id"] for row in records], ["lx_run"])

            resumed_lemmas: list[str] = []

            def resumed_word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                del senses, settings, generated_at, generation_run_id, prompt_version
                resumed_lemmas.append(lexeme.lemma)
                return []

            resumed_records = enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=resumed_word_provider,
                checkpoint_path=checkpoint_path,
                failures_output=failures_path,
                resume=True,
            )

            self.assertEqual(resumed_lemmas, ["play"])
            self.assertEqual([row["entry_id"] for row in resumed_records], ["lx_run"])

    def test_enrich_snapshot_per_word_request_delay_paces_global_request_starts(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({"snapshot_id": "snap-1", "lexeme_id": "lx_alpha", "lemma": "alpha", "language": "en", "wordfreq_rank": 1, "is_wordnet_backed": True, "source_refs": ["wordnet", "wordfreq"], "created_at": "2026-03-07T00:00:00Z"}),
                    json.dumps({"snapshot_id": "snap-1", "lexeme_id": "lx_beta", "lemma": "beta", "language": "en", "wordfreq_rank": 2, "is_wordnet_backed": True, "source_refs": ["wordnet", "wordfreq"], "created_at": "2026-03-07T00:00:00Z"}),
                    json.dumps({"snapshot_id": "snap-1", "lexeme_id": "lx_gamma", "lemma": "gamma", "language": "en", "wordfreq_rank": 3, "is_wordnet_backed": True, "source_refs": ["wordnet", "wordfreq"], "created_at": "2026-03-07T00:00:00Z"}),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({"snapshot_id": "snap-1", "sense_id": "sn_lx_alpha_1", "lexeme_id": "lx_alpha", "wn_synset_id": "alpha.n.01", "part_of_speech": "noun", "canonical_gloss": "alpha", "selection_reason": "common learner sense", "sense_order": 1, "is_high_polysemy": False, "created_at": "2026-03-07T00:00:00Z"}),
                    json.dumps({"snapshot_id": "snap-1", "sense_id": "sn_lx_beta_1", "lexeme_id": "lx_beta", "wn_synset_id": "beta.n.01", "part_of_speech": "noun", "canonical_gloss": "beta", "selection_reason": "common learner sense", "sense_order": 1, "is_high_polysemy": False, "created_at": "2026-03-07T00:00:00Z"}),
                    json.dumps({"snapshot_id": "snap-1", "sense_id": "sn_lx_gamma_1", "lexeme_id": "lx_gamma", "wn_synset_id": "gamma.n.01", "part_of_speech": "noun", "canonical_gloss": "gamma", "selection_reason": "common learner sense", "sense_order": 1, "is_high_polysemy": False, "created_at": "2026-03-07T00:00:00Z"}),
                ]) + "\n",
                encoding="utf-8",
            )
            start_times: list[float] = []

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                start_times.append(time.monotonic())
                return [
                    EnrichmentRecord(
                        snapshot_id=senses[0].snapshot_id,
                        enrichment_id=f"en_{senses[0].sense_id}",
                        sense_id=senses[0].sense_id,
                        definition=lexeme.lemma,
                        examples=[{"sentence": lexeme.lemma, "difficulty": "A1"}],
                        cefr_level="A1",
                        primary_domain="general",
                        secondary_domains=[],
                        register="neutral",
                        synonyms=[],
                        antonyms=[],
                        collocations=[],
                        grammar_patterns=[],
                        usage_note="ok",
                        forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                        confusable_words=[],
                        model_name="test-provider",
                        prompt_version=prompt_version,
                        generation_run_id=generation_run_id,
                        confidence=0.9,
                        review_status="draft",
                        generated_at=generated_at,
                    )
                ]

            enrich_snapshot(
                snapshot_dir,
                mode="per_word",
                word_provider=word_provider,
                max_concurrency=3,
                request_delay_seconds=0.05,
            )

            self.assertEqual(len(start_times), 3)
            sorted_times = sorted(start_times)
            self.assertGreaterEqual(sorted_times[1] - sorted_times[0], 0.045)
            self.assertGreaterEqual(sorted_times[2] - sorted_times[1], 0.045)


class EnrichmentValidationHardeningTests(unittest.TestCase):
    def _write_snapshot(self, snapshot_dir: Path) -> None:
        EnrichPerWordModeTests()._write_snapshot(snapshot_dir)

    def _word_payload(self, sense_id: str) -> dict[str, object]:
        return {
            "decision": "keep_standard",
            "discard_reason": None,
            "base_word": None,
            "phonetics": _test_phonetics(),
            "senses": [
                {
                    "sense_id": sense_id,
                    "part_of_speech": "verb",
                    "sense_kind": "standard_meaning",
                    "definition": "move quickly on foot",
                    "examples": [{"sentence": "I run every day.", "difficulty": "A1"}],
                    "cefr_level": "A1",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": [],
                    "grammar_patterns": [],
                    "usage_note": "Common verb.",
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "confusable_words": [],
                    "translations": _test_translations(definition="move quickly", usage_note="common verb"),
                    "confidence": 0.9,
                }
            ]
        }

    def _build_lexeme_and_senses(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            return lexemes[0], senses

    def test_validate_string_list_field_drops_blank_items(self) -> None:
        self.assertEqual(
            _validate_string_list_field([" opposite ", "", "   ", "reverse"], field="antonyms"),
            ["opposite", "reverse"],
        )

    def test_run_enrichment_forwards_retry_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            with patch("tools.lexicon.enrich.enrich_snapshot", return_value=[]) as mocked_enrich:
                run_enrichment(
                    snapshot_dir,
                    transient_retries=7,
                    validation_retries=3,
                )

        self.assertEqual(mocked_enrich.call_args.kwargs["transient_retries"], 7)
        self.assertEqual(mocked_enrich.call_args.kwargs["validation_retries"], 3)

    def test_run_enrichment_forwards_log_controls(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            log_file = snapshot_dir / "runtime.log"
            with patch("tools.lexicon.enrich.enrich_snapshot", return_value=[]) as mocked_enrich:
                run_enrichment(
                    snapshot_dir,
                    log_level="debug",
                    log_file=log_file,
                )

        self.assertEqual(mocked_enrich.call_args.kwargs["log_level"], "debug")
        self.assertEqual(mocked_enrich.call_args.kwargs["log_file"], log_file)

    def test_generate_validated_word_payload_retries_after_validation_failure(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        invalid_one = self._word_payload(sense_id)
        invalid_one["senses"][0]["antonyms"] = [123]
        invalid_two = self._word_payload(sense_id)
        invalid_two["senses"][0]["synonyms"] = [None, "sprint"]
        valid = self._word_payload(sense_id)

        class StubClient:
            def __init__(self, responses):
                self._responses = list(responses)

            def generate_json(self, prompt: str):
                return self._responses.pop(0)

        rows, stats = _generate_validated_word_payload_with_stats(
            client=StubClient([invalid_one, invalid_two, valid]),
            lexeme=lexeme,
            senses=senses,
            prompt_mode="word_only",
            max_validation_retries=2,
        )

        self.assertEqual(rows["decision"], "keep_standard")
        self.assertEqual(len(rows["senses"]), 1)
        self.assertEqual(rows["senses"][0]["sense_id"], sense_id)
        self.assertGreaterEqual(int(stats["repair_count"]), 2)

    def test_generate_validated_word_payload_still_fails_after_bounded_validation_retries(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        invalid = self._word_payload(sense_id)
        invalid["senses"][0]["antonyms"] = [123]

        class StubClient:
            def generate_json(self, prompt: str):
                return invalid

        with self.assertRaises(RuntimeError):
            _generate_validated_word_payload_with_stats(
                client=StubClient(),
                lexeme=lexeme,
                senses=senses,
                prompt_mode="word_only",
            )

    def test_generate_validated_word_payload_escalates_reasoning_effort_for_validation_retry(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        invalid = self._word_payload(sense_id)
        invalid["senses"][0]["antonyms"] = [123]
        valid = self._word_payload(sense_id)

        class StubClient:
            def __init__(self):
                self.reasoning_effort = "none"
                self.calls: list[str] = []

            def generate_json(self, prompt: str):
                del prompt
                self.calls.append(str(self.reasoning_effort))
                return invalid if len(self.calls) == 1 else valid

        client = StubClient()
        rows, stats = _generate_validated_word_payload_with_stats(
            client=client,
            lexeme=lexeme,
            senses=senses,
            prompt_mode="word_only",
            max_validation_retries=1,
        )

        self.assertEqual(rows["decision"], "keep_standard")
        self.assertEqual(int(stats["repair_count"]), 1)
        self.assertEqual(client.calls, ["none", "low"])

    def test_generate_validated_word_payload_emits_validation_outcome_events(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        invalid = self._word_payload(sense_id)
        invalid["senses"][0]["antonyms"] = [123]
        valid = self._word_payload(sense_id)

        class StubClient:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt: str):
                del prompt
                self.calls += 1
                return invalid if self.calls == 1 else valid

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = RuntimeLogger(RuntimeLogConfig(level="debug", log_file=log_file), stream=io.StringIO())
            _generate_validated_word_payload_with_stats(
                client=StubClient(),
                lexeme=lexeme,
                senses=senses,
                prompt_mode="word_only",
                max_validation_retries=1,
                runtime_logger=logger,
            )

            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            validation_events = [row for row in log_rows if row["event"] == "validation-outcome"]
            self.assertEqual(len(validation_events), 1)
            self.assertEqual(validation_events[0]["fields"]["outcome"], "repaired")
            self.assertEqual(validation_events[0]["fields"]["retry_count"], 1)
            self.assertNotIn("sense_id", validation_events[0]["fields"])

    def test_generate_validated_word_payload_emits_failed_validation_outcome(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        invalid = self._word_payload(sense_id)
        invalid["senses"][0]["antonyms"] = [123]

        class StubClient:
            def generate_json(self, prompt: str):
                del prompt
                return invalid

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = RuntimeLogger(RuntimeLogConfig(level="debug", log_file=log_file), stream=io.StringIO())
            with self.assertRaises(RuntimeError):
                _generate_validated_word_payload_with_stats(
                    client=StubClient(),
                    lexeme=lexeme,
                    senses=senses,
                    prompt_mode="word_only",
                    max_validation_retries=0,
                    runtime_logger=logger,
                )

            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            validation_events = [row for row in log_rows if row["event"] == "validation-outcome"]
            self.assertEqual(len(validation_events), 1)
            self.assertEqual(validation_events[0]["fields"]["outcome"], "failed")
            self.assertEqual(validation_events[0]["fields"]["retry_count"], 0)
            self.assertNotIn("sense_id", validation_events[0]["fields"])

    def test_phrase_translation_usage_note_can_be_blank_when_source_note_is_absent(self) -> None:
        payload = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "say something to encourage success",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "Good luck!", "difficulty": "A1"}],
                    "grammar_patterns": [],
                    "usage_note": None,
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }

        normalized = normalize_phrase_enrichment_payload(payload)

        self.assertEqual(normalized["senses"][0]["usage_note"], None)
        self.assertEqual(
            normalized["senses"][0]["translations"]["ar"]["usage_note"],
            "",
        )

    def test_phrase_translation_usage_note_blank_is_retryable_when_source_note_exists(self) -> None:
        payload = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "say something to encourage success",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "Good luck!", "difficulty": "A1"}],
                    "grammar_patterns": [],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }

        with self.assertRaisesRegex(RuntimeError, "missing_translated_usage_note_with_source_note_present"):
            normalize_phrase_enrichment_payload(payload)

    def test_generate_validated_phrase_payload_emits_retry_runtime_event(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }
        valid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": _test_translations("They told me to break a leg."),
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt: str, response_schema=None):
                del prompt, response_schema
                self.calls += 1
                return invalid if self.calls == 1 else valid

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = RuntimeLogger(RuntimeLogConfig(level="debug", log_file=log_file), stream=io.StringIO())
            rows, stats = _generate_validated_phrase_payload_with_stats(
                client=StubClient(),
                lexeme=lexeme,
                max_validation_retries=1,
                runtime_logger=logger,
            )

            self.assertEqual(rows["phrase_kind"], "idiom")
            self.assertEqual(int(stats["validation_retry_count"]), 1)
            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            retry_events = [row for row in log_rows if row["event"] == "retry-scheduled"]
            self.assertEqual(len(retry_events), 1)
            self.assertEqual(retry_events[0]["fields"]["retry_reason"], "missing_translated_usage_note_with_source_note_present")
            self.assertEqual(retry_events[0]["fields"]["retries_remaining"], 0)
            self.assertNotIn("They told me to break a leg.", log_file.read_text(encoding="utf-8"))
            self.assertNotIn("translated example", log_file.read_text(encoding="utf-8"))

    def test_generate_validated_phrase_payload_retries_after_retryable_validation_failure(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }
        valid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": _test_translations("They told me to break a leg."),
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.calls = 0
                self.prompts: list[str] = []

            def generate_json(self, prompt: str, response_schema=None):
                del response_schema
                self.calls += 1
                self.prompts.append(prompt)
                return invalid if self.calls == 1 else valid

        client = StubClient()
        rows, stats = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            max_validation_retries=1,
        )

        self.assertEqual(rows["phrase_kind"], "idiom")
        self.assertEqual(client.calls, 2)
        self.assertEqual(int(stats["validation_retry_count"]), 1)
        self.assertIn("repair the previous learner-facing enrichment response", client.prompts[1].lower())

    def test_generate_validated_phrase_payload_escalates_reasoning_effort_for_validation_retry(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }
        valid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": _test_translations("They told me to break a leg."),
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.reasoning_effort = "none"
                self.calls: list[str] = []

            def generate_json(self, prompt: str, response_schema=None):
                del prompt, response_schema
                self.calls.append(str(self.reasoning_effort))
                return invalid if len(self.calls) == 1 else valid

        client = StubClient()
        rows, stats = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            max_validation_retries=1,
        )

        self.assertEqual(rows["phrase_kind"], "idiom")
        self.assertEqual(int(stats["validation_retry_count"]), 1)
        self.assertEqual(client.calls, ["none", "low"])

    def test_generate_validated_phrase_payload_repairs_general_validation_failures(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        **_test_translations("They told me to break a leg."),
                        "es": {
                            "definition": "es:def",
                            "usage_note": "frequ\x00eancia",
                            "examples": ["es:They told me to break a leg."],
                        },
                    },
                }
            ],
        }
        valid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": _test_translations("They told me to break a leg."),
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.calls = 0
                self.prompts: list[str] = []

            def generate_json(self, prompt: str, response_schema=None):
                del response_schema
                self.calls += 1
                self.prompts.append(prompt)
                return invalid if self.calls == 1 else valid

        client = StubClient()
        rows, stats = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            max_validation_retries=1,
        )

        self.assertEqual(rows["phrase_kind"], "idiom")
        self.assertEqual(client.calls, 2)
        self.assertEqual(int(stats["validation_retry_count"]), 1)
        self.assertIn("repair the previous learner-facing enrichment response", client.prompts[1].lower())

    def test_generate_validated_phrase_payload_fails_after_bounded_validation_retries(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        locale: {
                            "definition": f"{locale}: definition",
                            "usage_note": "",
                            "examples": ["translated example"],
                        }
                        for locale in ("zh-Hans", "es", "ar", "pt-BR", "ja")
                    },
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt: str, response_schema=None):
                del prompt, response_schema
                self.calls += 1
                return invalid

        client = StubClient()
        with self.assertRaisesRegex(RuntimeError, "missing_translated_usage_note_with_source_note_present"):
            _generate_validated_phrase_payload_with_stats(
                client=client,
                lexeme=lexeme,
                max_validation_retries=1,
            )
        self.assertEqual(client.calls, 2)

    def test_generate_validated_phrase_payload_accepts_core_mode_without_translations(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        core_only = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.response_schemas: list[dict[str, object] | None] = []

            def generate_json(self, prompt: str, response_schema=None):
                del prompt
                self.response_schemas.append(response_schema)
                return core_only

        client = StubClient()
        rows, stats = _generate_validated_phrase_payload_with_stats(
            client=client,
            lexeme=lexeme,
            include_translations=False,
        )

        self.assertEqual(rows["phrase_kind"], "idiom")
        self.assertEqual(rows["senses"][0]["translations"], {})
        self.assertEqual(int(stats["validation_retry_count"]), 0)
        self.assertNotIn("translations", client.response_schemas[0]["schema"]["properties"]["senses"]["items"]["required"])

    def test_generate_validated_phrase_payload_emits_validation_outcome_events(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="ph_break_a_leg",
            lemma="break a leg",
            language="en",
            wordfreq_rank=0,
            is_wordnet_backed=False,
            source_refs=["phrase_seed"],
            created_at="2026-03-23T00:00:00Z",
            entry_id="ph_break_a_leg",
            entry_type="phrase",
            normalized_form="break a leg",
            source_provenance=[{"source": "phrase_seed"}],
            phrase_kind="idiom",
            display_form="Break a leg",
            seed_metadata={"raw_reviewed_as": "idiom"},
        )
        invalid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": {
                        **_test_translations("They told me to break a leg."),
                        "es": {
                            "definition": "es:def",
                            "usage_note": "frequ\x00eancia",
                            "examples": ["es:They told me to break a leg."],
                        },
                    },
                }
            ],
        }
        valid = {
            "phrase_kind": "idiom",
            "confidence": 0.9,
            "senses": [
                {
                    "definition": "to wish someone good luck",
                    "part_of_speech": "phrase",
                    "examples": [{"sentence": "They told me to break a leg.", "difficulty": "B1"}],
                    "grammar_patterns": ["say + phrase"],
                    "usage_note": "Used before a performance.",
                    "translations": _test_translations("They told me to break a leg."),
                }
            ],
        }

        class StubClient:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt: str, response_schema=None):
                del prompt, response_schema
                self.calls += 1
                return invalid if self.calls == 1 else valid

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / "runtime.log"
            logger = RuntimeLogger(RuntimeLogConfig(level="debug", log_file=log_file), stream=io.StringIO())
            _generate_validated_phrase_payload_with_stats(
                client=StubClient(),
                lexeme=lexeme,
                max_validation_retries=1,
                runtime_logger=logger,
            )

            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            validation_events = [row for row in log_rows if row["event"] == "validation-outcome"]
            self.assertEqual(len(validation_events), 1)
            self.assertEqual(validation_events[0]["fields"]["outcome"], "repaired")
            self.assertEqual(validation_events[0]["fields"]["retry_count"], 1)

    def test_enrich_snapshot_emits_lexeme_progress_events_without_payload_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            (snapshot_dir / "lexemes.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_alpha",
                        "lemma": "alpha",
                        "language": "en",
                        "wordfreq_rank": 10,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "lexeme_id": "lx_beta",
                        "lemma": "beta",
                        "language": "en",
                        "wordfreq_rank": 20,
                        "is_wordnet_backed": True,
                        "source_refs": ["wordnet", "wordfreq"],
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            (snapshot_dir / "senses.jsonl").write_text(
                "\n".join([
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_alpha_1",
                        "lexeme_id": "lx_alpha",
                        "wn_synset_id": "alpha.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "alpha sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_beta_1",
                        "lexeme_id": "lx_beta",
                        "wn_synset_id": "beta.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "beta sense",
                        "selection_reason": "common learner sense",
                        "sense_order": 1,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-07T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            log_file = snapshot_dir / "runtime.log"
            checkpoint_path = snapshot_dir / "enrich.checkpoint.jsonl"
            failures_path = snapshot_dir / "enrich.failures.jsonl"

            def make_record(lexeme, sense, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id=f"en_{sense.sense_id}",
                    sense_id=sense.sense_id,
                    definition=f"definition for {lexeme.lemma}",
                    examples=[{"sentence": f"{lexeme.lemma} example", "difficulty": "A1"}],
                    cefr_level="A1",
                    primary_domain="general",
                    secondary_domains=[],
                    register="neutral",
                    synonyms=[],
                    antonyms=[],
                    collocations=[],
                    grammar_patterns=[],
                    usage_note=f"note for {lexeme.lemma}",
                    forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    confusable_words=[],
                    model_name="test-provider",
                    prompt_version=prompt_version,
                    generation_run_id=generation_run_id,
                    confidence=0.9,
                    review_status="draft",
                    generated_at=generated_at,
                    translations=_test_translations(f"definition for {lexeme.lemma}", f"note for {lexeme.lemma}", [f"{lexeme.lemma} example"]),
                )

            def word_provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                if lexeme.lemma == "beta":
                    raise RuntimeError("gateway timeout")
                return [make_record(lexeme, senses[0], generated_at, generation_run_id, prompt_version)]

            with self.assertRaisesRegex(RuntimeError, "beta: gateway timeout"):
                enrich_snapshot(
                    snapshot_dir,
                    mode="per_word",
                    word_provider=word_provider,
                    checkpoint_path=checkpoint_path,
                    failures_output=failures_path,
                    max_failures=1,
                    log_level="debug",
                    log_file=log_file,
                )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            log_rows = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines() if line.strip()]
            events = [row["event"] for row in log_rows]

            self.assertEqual([row["entry_id"] for row in compiled_rows], ["lx_alpha"])
            self.assertIn("lexeme-start", events)
            self.assertIn("lexeme-complete", events)
            self.assertIn("lexeme-failure", events)
            self.assertNotIn("definition for alpha", log_file.read_text(encoding="utf-8"))
            self.assertNotIn("definition for beta", log_file.read_text(encoding="utf-8"))

    def test_generate_validated_word_payload_retries_after_bad_gateway_failure(self) -> None:
        lexeme, senses = self._build_lexeme_and_senses()
        sense_id = senses[0].sense_id
        valid = self._word_payload(sense_id)

        class StubClient:
            def __init__(self):
                self.calls = 0

            def generate_json(self, prompt: str):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("502 Bad gateway")
                return valid

        client = StubClient()
        rows, stats = _generate_validated_word_payload_with_stats(
            client=client,
            lexeme=lexeme,
            senses=senses,
            prompt_mode="word_only",
        )

        self.assertEqual(rows["decision"], "keep_standard")
        self.assertEqual(len(rows["senses"]), 1)
        self.assertEqual(rows["senses"][0]["sense_id"], sense_id)
        self.assertEqual(client.calls, 2)
        self.assertEqual(int(stats["retry_count"]), 1)


class StagedEnrichmentArtifactTests(unittest.TestCase):
    def test_split_compiled_row_for_staging_roundtrips_through_merge(self) -> None:
        compiled_row = {
            "schema_version": "1.1.0",
            "entry_id": "lx_run",
            "entry_type": "word",
            "normalized_form": "run",
            "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
            "entity_category": "general",
            "word": "run",
            "part_of_speech": ["verb"],
            "cefr_level": "B1",
            "frequency_rank": 5,
            "forms": {
                "plural_forms": [],
                "verb_forms": {"base": "run", "third_person_singular": "runs", "past": "ran", "past_participle": "run", "gerund": "running"},
                "comparative": None,
                "superlative": None,
                "derivations": [],
            },
            "senses": [
                {
                    "sense_id": "sn_lx_run_1",
                    "wn_synset_id": "run.v.01",
                    "pos": "verb",
                    "sense_kind": "standard_meaning",
                    "decision": "keep_standard",
                    "base_word": None,
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "definition": "move quickly on foot",
                    "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": [],
                    "grammar_patterns": [],
                    "usage_note": "Common everyday verb.",
                    "enrichment_id": "en_sn_lx_run_1_v1",
                    "generation_run_id": "enrich-2026-04-08T02:00:00Z",
                    "model_name": "gpt-5.4",
                    "prompt_version": "v1",
                    "confidence": 0.9,
                    "generated_at": "2026-04-08T02:00:00Z",
                    "translations": _test_translations(
                        "move quickly on foot",
                        "Common everyday verb.",
                        ["I run every morning."],
                    ),
                }
            ],
            "confusable_words": [],
            "generated_at": "2026-04-08T02:00:00Z",
            "phonetics": _test_phonetics(),
        }

        core_row, translation_rows = split_compiled_row_for_staging(compiled_row)
        merged_rows = merge_staged_enrichment_rows([core_row], translation_rows)

        self.assertEqual(len(translation_rows), 5)
        self.assertNotIn("translations", core_row["senses"][0])
        self.assertEqual(merged_rows, [compiled_row])

    def test_split_legacy_enrich_artifact_can_synthesize_resume_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            compiled_input = tmp_path / "words.enriched.jsonl"
            compiled_row = {
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "lexeme_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "B1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run", "third_person_singular": "runs", "past": "ran", "past_participle": "run", "gerund": "running"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_1",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "generation_run_id": "enrich-2026-04-08T02:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-04-08T02:00:00Z",
                        "translations": _test_translations(
                            "move quickly on foot",
                            "Common everyday verb.",
                            ["I run every morning."],
                        ),
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-04-08T02:00:00Z",
                "phonetics": _test_phonetics(),
            }
            compiled_input.write_text(json.dumps(compiled_row) + "\n", encoding="utf-8")

            payload = split_legacy_enrich_artifact(
                compiled_input_path=compiled_input,
                core_output_path=tmp_path / "words.enriched.core.jsonl",
                translations_output_path=tmp_path / "words.translations.jsonl",
                core_checkpoint_path=tmp_path / "enrich.core.checkpoint.jsonl",
                core_decisions_path=tmp_path / "enrich.core.decisions.jsonl",
                core_failures_path=tmp_path / "enrich.core.failures.jsonl",
                translations_checkpoint_path=tmp_path / "enrich.translations.checkpoint.jsonl",
                translations_decisions_path=tmp_path / "enrich.translations.decisions.jsonl",
                translations_failures_path=tmp_path / "enrich.translations.failures.jsonl",
            )

            self.assertEqual(payload["core_row_count"], 1)
            self.assertEqual(payload["translation_row_count"], 5)
            self.assertEqual(payload["core_checkpoint_row_count"], 1)
            self.assertEqual(payload["core_decision_row_count"], 1)
            self.assertEqual(payload["translations_checkpoint_row_count"], 1)
            self.assertEqual(payload["translations_decision_row_count"], 1)

            core_checkpoint_rows = read_jsonl(tmp_path / "enrich.core.checkpoint.jsonl")
            self.assertEqual(core_checkpoint_rows[0]["lexeme_id"], "lx_run")
            self.assertEqual(core_checkpoint_rows[0]["status"], "completed")

            core_decision_rows = read_jsonl(tmp_path / "enrich.core.decisions.jsonl")
            self.assertEqual(core_decision_rows[0]["decision"], "keep_standard")
            self.assertEqual(core_decision_rows[0]["accepted_sense_count"], 1)

            translation_checkpoint_rows = read_jsonl(tmp_path / "enrich.translations.checkpoint.jsonl")
            self.assertEqual(translation_checkpoint_rows[0]["entry_id"], "lx_run")
            self.assertEqual(translation_checkpoint_rows[0]["sense_id"], "sn_lx_run_1")
            self.assertEqual(translation_checkpoint_rows[0]["status"], "completed")

            translation_decision_rows = read_jsonl(tmp_path / "enrich.translations.decisions.jsonl")
            self.assertEqual(translation_decision_rows[0]["locale_count"], 5)

            self.assertEqual(read_jsonl(tmp_path / "enrich.core.failures.jsonl"), [])
            self.assertEqual(read_jsonl(tmp_path / "enrich.translations.failures.jsonl"), [])

    def test_split_legacy_enrich_artifact_prefers_legacy_core_ledgers_and_keeps_discards(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            compiled_input = tmp_path / "words.enriched.jsonl"
            compiled_input.write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "B1",
                "frequency_rank": 5,
                "forms": {
                    "plural_forms": [],
                    "verb_forms": {"base": "run", "third_person_singular": "runs", "past": "ran", "past_participle": "run", "gerund": "running"},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                "senses": [
                    {
                        "sense_id": "sn_lx_run_1",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "generation_run_id": "enrich-2026-04-08T02:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-04-08T02:00:00Z",
                        "translations": _test_translations(
                            "move quickly on foot",
                            "Common everyday verb.",
                            ["I run every morning."],
                        ),
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-04-08T02:00:00Z",
                "phonetics": _test_phonetics(),
            }) + "\n", encoding="utf-8")
            write_jsonl(
                tmp_path / "enrich.checkpoint.jsonl",
                [
                    {
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                    },
                    {
                        "lexeme_id": "lx_runs",
                        "lemma": "runs",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:02Z",
                    },
                ],
            )
            write_jsonl(
                tmp_path / "enrich.decisions.jsonl",
                [
                    {
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                        "decision": "keep_standard",
                        "base_word": None,
                        "discard_reason": None,
                        "accepted_sense_count": 1,
                    },
                    {
                        "lexeme_id": "lx_runs",
                        "lemma": "runs",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:02Z",
                        "decision": "discard",
                        "base_word": None,
                        "discard_reason": "ordinary inflection",
                        "accepted_sense_count": 0,
                    },
                ],
            )

            split_legacy_enrich_artifact(
                compiled_input_path=compiled_input,
                core_output_path=tmp_path / "words.enriched.core.jsonl",
                translations_output_path=tmp_path / "words.translations.jsonl",
                core_checkpoint_path=tmp_path / "enrich.core.checkpoint.jsonl",
                core_decisions_path=tmp_path / "enrich.core.decisions.jsonl",
            )

            self.assertEqual(read_jsonl(tmp_path / "enrich.core.checkpoint.jsonl"), read_jsonl(tmp_path / "enrich.checkpoint.jsonl"))
            self.assertEqual(read_jsonl(tmp_path / "enrich.core.decisions.jsonl"), read_jsonl(tmp_path / "enrich.decisions.jsonl"))

    def test_split_legacy_enrich_artifact_requires_compiled_rows_to_exist_in_legacy_ledgers(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            compiled_input = tmp_path / "words.enriched.jsonl"
            compiled_input.write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "B1",
                "frequency_rank": 5,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [
                    {
                        "sense_id": "sn_lx_run_1",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "generation_run_id": "enrich-2026-04-08T02:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-04-08T02:00:00Z",
                        "translations": _test_translations(),
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-04-08T02:00:00Z",
                "phonetics": _test_phonetics(),
            }) + "\n", encoding="utf-8")
            write_jsonl(
                tmp_path / "enrich.checkpoint.jsonl",
                [
                    {
                        "lexeme_id": "lx_other",
                        "lemma": "other",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                    },
                ],
            )
            write_jsonl(
                tmp_path / "enrich.decisions.jsonl",
                [
                    {
                        "lexeme_id": "lx_other",
                        "lemma": "other",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                        "decision": "keep_standard",
                        "base_word": None,
                        "discard_reason": None,
                        "accepted_sense_count": 1,
                    },
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "Compiled rows missing from legacy enrich ledgers: lx_run"):
                split_legacy_enrich_artifact(
                    compiled_input_path=compiled_input,
                    core_output_path=tmp_path / "words.enriched.core.jsonl",
                    translations_output_path=tmp_path / "words.translations.jsonl",
                    core_checkpoint_path=tmp_path / "enrich.core.checkpoint.jsonl",
                    core_decisions_path=tmp_path / "enrich.core.decisions.jsonl",
                )

    def test_split_legacy_enrich_artifact_rejects_legacy_accepted_rows_missing_from_compiled_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir)
            compiled_input = tmp_path / "words.enriched.jsonl"
            compiled_input.write_text(json.dumps({
                "schema_version": "1.1.0",
                "entry_id": "lx_run",
                "entry_type": "word",
                "normalized_form": "run",
                "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
                "entity_category": "general",
                "word": "run",
                "part_of_speech": ["verb"],
                "cefr_level": "B1",
                "frequency_rank": 5,
                "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                "senses": [
                    {
                        "sense_id": "sn_lx_run_1",
                        "wn_synset_id": "run.v.01",
                        "pos": "verb",
                        "sense_kind": "standard_meaning",
                        "decision": "keep_standard",
                        "base_word": None,
                        "primary_domain": "general",
                        "secondary_domains": [],
                        "register": "neutral",
                        "definition": "move quickly on foot",
                        "examples": [{"sentence": "I run every morning.", "difficulty": "A1"}],
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": [],
                        "grammar_patterns": [],
                        "usage_note": "Common everyday verb.",
                        "enrichment_id": "en_sn_lx_run_1_v1",
                        "generation_run_id": "enrich-2026-04-08T02:00:00Z",
                        "model_name": "gpt-5.4",
                        "prompt_version": "v1",
                        "confidence": 0.9,
                        "generated_at": "2026-04-08T02:00:00Z",
                        "translations": _test_translations(),
                    }
                ],
                "confusable_words": [],
                "generated_at": "2026-04-08T02:00:00Z",
                "phonetics": _test_phonetics(),
            }) + "\n", encoding="utf-8")
            write_jsonl(
                tmp_path / "enrich.checkpoint.jsonl",
                [
                    {
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                    },
                    {
                        "lexeme_id": "lx_jump",
                        "lemma": "jump",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:02Z",
                    },
                ],
            )
            write_jsonl(
                tmp_path / "enrich.decisions.jsonl",
                [
                    {
                        "lexeme_id": "lx_run",
                        "lemma": "run",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:01Z",
                        "decision": "keep_standard",
                        "base_word": None,
                        "discard_reason": None,
                        "accepted_sense_count": 1,
                    },
                    {
                        "lexeme_id": "lx_jump",
                        "lemma": "jump",
                        "status": "completed",
                        "generation_run_id": "legacy-run",
                        "completed_at": "2026-04-08T02:00:02Z",
                        "decision": "keep_standard",
                        "base_word": None,
                        "discard_reason": None,
                        "accepted_sense_count": 1,
                    },
                ],
            )

            with self.assertRaisesRegex(RuntimeError, "Legacy accepted decisions missing from compiled enrich artifact: lx_jump"):
                split_legacy_enrich_artifact(
                    compiled_input_path=compiled_input,
                    core_output_path=tmp_path / "words.enriched.core.jsonl",
                    translations_output_path=tmp_path / "words.translations.jsonl",
                    core_checkpoint_path=tmp_path / "enrich.core.checkpoint.jsonl",
                    core_decisions_path=tmp_path / "enrich.core.decisions.jsonl",
                )
