import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrich import (
    OpenAICompatibleResponsesClient,
    build_enrichment_prompt,
    build_enrichment_provider,
    build_openai_compatible_enrichment_provider,
    _default_node_runner,
    build_openai_compatible_node_enrichment_provider,
    enrich_snapshot,
    read_snapshot_inputs,
)
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.models import EnrichmentRecord


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

    def test_read_snapshot_inputs_loads_linked_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            lexemes, senses = read_snapshot_inputs(snapshot_dir)

            self.assertEqual(len(lexemes), 1)
            self.assertEqual(len(senses), 1)
            self.assertEqual(lexemes[0].lemma, "run")
            self.assertEqual(senses[0].sense_id, "sn_lx_run_1")

    def test_enrich_snapshot_writes_enrichments_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)

            def provider(*, lexeme, sense, settings, generated_at, generation_run_id, prompt_version):
                return EnrichmentRecord(
                    snapshot_id=sense.snapshot_id,
                    enrichment_id="en_sn_lx_run_1_v1",
                    sense_id=sense.sense_id,
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
                )

            records = enrich_snapshot(
                snapshot_dir,
                provider=provider,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual(len(records), 1)
            enrichment_path = snapshot_dir / "enrichments.jsonl"
            self.assertTrue(enrichment_path.exists())
            payload = [json.loads(line) for line in enrichment_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(payload[0]["sense_id"], "sn_lx_run_1")
            self.assertEqual(payload[0]["model_name"], "test-provider")

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

        payload = client.generate_json("hello")

        self.assertEqual(captured["url"], "https://example.test/v1/responses")
        self.assertEqual(captured["headers"]["Authorization"], "Bearer secret-key")
        self.assertEqual(captured["payload"]["model"], "gpt-test")
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

        client.generate_json("hello")

        self.assertEqual(captured["payload"]["reasoning"], {"effort": "low"})

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
                                        }
                                    ),
                                }
                            ],
                        }
                    ]
                }

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
            with self.assertRaisesRegex(RuntimeError, "examples"):
                provider(
                    lexeme=lexeme,
                    sense=sense,
                    settings=settings,
                    generated_at="2026-03-07T00:00:00Z",
                    generation_run_id="run-123",
                    prompt_version="v1",
                )

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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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
            provider = build_enrichment_provider(settings=settings, provider_mode="auto", transport=lambda *_: {})

        self.assertIs(provider, sentinel_provider)
        mocked_builder.assert_called_once()

    def test_default_node_runner_times_out_cleanly(self) -> None:
        with patch('tools.lexicon.enrich.shutil.which', return_value='node'), \
             patch('tools.lexicon.enrich.Path.exists', return_value=True), \
             patch('tools.lexicon.enrich.subprocess.run', side_effect=subprocess.TimeoutExpired(cmd=['node'], timeout=60)):
            with self.assertRaisesRegex(RuntimeError, 'timed out after 60 seconds'):
                _default_node_runner({'prompt': 'hello'})


if __name__ == "__main__":
    unittest.main()
