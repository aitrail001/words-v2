import json
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from pathlib import Path

from tools.lexicon.config import LexiconSettings
from tools.lexicon.enrich import (
    NodeOpenAICompatibleResponsesClient,
    OpenAICompatibleResponsesClient,
    _generate_validated_word_payload_with_stats,
    _single_sense_response_schema,
    _validate_string_list_field,
    _word_enrichment_response_schema,
    build_enrichment_prompt,
    build_word_enrichment_prompt,
    build_enrichment_provider,
    build_openai_compatible_enrichment_provider,
    build_openai_compatible_word_enrichment_provider,
    _default_node_runner,
    build_openai_compatible_node_enrichment_provider,
    _parse_json_payload_text,
    enrich_snapshot,
    read_snapshot_inputs,
)
from tools.lexicon.errors import LexiconDependencyError
from tools.lexicon.models import EnrichmentRecord


def _test_translations(definition: str = "translated definition", usage_note: str = "translated usage note", examples: list[str] | None = None) -> dict[str, dict[str, object]]:
    example_rows = list(examples or ["translated example"])
    return {
        "zh-Hans": {"definition": f"zh:{definition}", "usage_note": f"zh:{usage_note}", "examples": [f"zh:{row}" for row in example_rows]},
        "es": {"definition": f"es:{definition}", "usage_note": f"es:{usage_note}", "examples": [f"es:{row}" for row in example_rows]},
        "ar": {"definition": f"ar:{definition}", "usage_note": f"ar:{usage_note}", "examples": [f"ar:{row}" for row in example_rows]},
        "pt-BR": {"definition": f"pt:{definition}", "usage_note": f"pt:{usage_note}", "examples": [f"pt:{row}" for row in example_rows]},
        "ja": {"definition": f"ja:{definition}", "usage_note": f"ja:{usage_note}", "examples": [f"ja:{row}" for row in example_rows]},
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

    def test_node_openai_compatible_client_falls_back_when_schema_request_hits_gateway_error(self) -> None:
        payloads = []

        def runner(payload):
            payloads.append(dict(payload))
            if payload.get("response_schema") is not None:
                raise RuntimeError("502 Bad gateway")
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
            runner=runner,
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
        self.assertEqual(len(payloads), 2)
        self.assertIn("response_schema", payloads[0])
        self.assertNotIn("response_schema", payloads[1])
        self.assertEqual(client.response_schema_fallback_count, 1)

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

            provider = build_openai_compatible_enrichment_provider(settings=settings, transport=transport)
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

            enrichments = [json.loads(line) for line in (snapshot_dir / "enrichments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            failures = [json.loads(line) for line in failures_path.read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual([row["sense_id"] for row in enrichments], ["sn_lx_alpha_1"])
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

            enrichments = [json.loads(line) for line in (snapshot_dir / "enrichments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(resumed_lemmas, ["beta"])
            self.assertEqual(sorted(row["sense_id"] for row in enrichments), ["sn_lx_alpha_1", "sn_lx_beta_1"])
            self.assertEqual(sorted(record.sense_id for record in records), ["sn_lx_alpha_1", "sn_lx_beta_1"])


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
            self.assertIn("at most 8 learner-friendly meanings", prompt.lower())
            self.assertIn("do not invent new sense ids", prompt.lower())
            self.assertIn("you may omit weak tail senses", prompt.lower())

    def test_build_word_enrichment_prompt_word_only_mode_omits_grounding_block(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            lexemes, senses = read_snapshot_inputs(snapshot_dir)
            run_lexeme = next(item for item in lexemes if item.lexeme_id == "lx_run")
            run_senses = [sense for sense in senses if sense.lexeme_id == "lx_run"]

            prompt = build_word_enrichment_prompt(lexeme=run_lexeme, senses=run_senses, prompt_mode="word_only")

            self.assertNotIn("grounding context", prompt.lower())
            self.assertIn("allowed sense ids for this word are:", prompt.lower())
            self.assertIn("sn_lx_run_1", prompt.lower())
            self.assertIn("sn_lx_run_2", prompt.lower())
            self.assertIn("do not invent new sense ids", prompt.lower())
            self.assertIn("english word 'run'", prompt.lower())
            self.assertIn("return only valid content for the required fields", prompt.lower())
            self.assertIn("at most 8 learner-friendly meanings", prompt.lower())
            self.assertNotIn("return json only with this schema:", prompt.lower())

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

    def test_enrich_snapshot_per_word_mode_writes_existing_enrichments_jsonl_shape(self) -> None:
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

            self.assertEqual([record.sense_id for record in records], ["sn_lx_play_1", "sn_lx_run_1", "sn_lx_run_2"])
            payload = [json.loads(line) for line in (snapshot_dir / "enrichments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(payload[0]["sense_id"], "sn_lx_play_1")
            self.assertEqual(payload[-1]["sense_id"], "sn_lx_run_2")

    def test_enrich_snapshot_per_word_mode_preserves_output_order_under_parallelism(self) -> None:
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

            self.assertEqual([record.sense_id for record in records], ["sn_lx_play_1", "sn_lx_run_1", "sn_lx_run_2"])

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
            self.assertIn("invalid if the senses array contains more than 8 items", prompt)
            self.assertIn("if more than 8 candidates seem useful, keep only the strongest 8", prompt)

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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
            records = provider(
                lexeme=run_lexeme,
                senses=run_senses,
                settings=settings,
                generated_at="2026-03-07T00:00:00Z",
                generation_run_id="run-123",
                prompt_version="v1",
            )

            self.assertEqual([record.sense_id for record in records], ["sn_lx_run_1"])

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
                return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"senses": rows})}]}]}

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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
                    return {"output": [{"type": "message", "content": [{"type": "output_text", "text": json.dumps({"senses": rows})}]}]}
                return {
                    "output": [{
                        "type": "message",
                        "content": [{
                            "type": "output_text",
                            "text": json.dumps({
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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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

            provider = build_openai_compatible_word_enrichment_provider(settings=settings, transport=transport)
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
            (snapshot_dir / "enrichments.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "enrichment_id": "en_dangling",
                    "sense_id": "sn_lx_run_1",
                    "definition": "dangling",
                    "examples": [{"sentence": "dangling", "difficulty": "A1"}],
                    "cefr_level": "A1",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "synonyms": [],
                    "antonyms": [],
                    "collocations": [],
                    "grammar_patterns": [],
                    "usage_note": "dangling",
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "confusable_words": [],
                    "model_name": "test-provider",
                    "prompt_version": "v1",
                    "generation_run_id": "dangling-run",
                    "confidence": 0.9,
                    "review_status": "draft",
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

            self.assertEqual(called_lemmas, ["play", "run"])
            self.assertEqual(sorted(record.sense_id for record in records), ["sn_lx_play_1", "sn_lx_run_1", "sn_lx_run_2"])
            payload = [json.loads(line) for line in (snapshot_dir / "enrichments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(sorted(row["sense_id"] for row in payload), ["sn_lx_play_1", "sn_lx_run_1", "sn_lx_run_2"])
            self.assertEqual(sum(1 for row in payload if row["sense_id"] == "sn_lx_run_1"), 1)

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

            payload = [json.loads(line) for line in (snapshot_dir / "enrichments.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            checkpoints = [json.loads(line) for line in checkpoint_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual([row["sense_id"] for row in payload], ["sn_lx_play_1"])
            self.assertEqual([row["lexeme_id"] for row in checkpoints], ["lx_play"])

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
            "senses": [
                {
                    "sense_id": sense_id,
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
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sense_id"], sense_id)
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

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["sense_id"], sense_id)
        self.assertEqual(client.calls, 2)
        self.assertEqual(int(stats["retry_count"]), 1)
