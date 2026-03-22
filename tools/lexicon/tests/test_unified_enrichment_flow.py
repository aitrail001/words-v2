from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.batch_ingest import ingest_batch_outputs
from tools.lexicon.batch_prepare import build_batch_request_rows
from tools.lexicon.enrich import WordJobOutcome, enrich_snapshot
from tools.lexicon.jsonl_io import write_jsonl
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample


def _lexeme_row(*, lemma: str = "run", lexeme_id: str = "lx_run", rank: int = 5) -> dict[str, object]:
    return {
        "snapshot_id": "snap-1",
        "lexeme_id": lexeme_id,
        "lemma": lemma,
        "language": "en",
        "wordfreq_rank": rank,
        "is_wordnet_backed": False,
        "source_refs": ["wordfreq"],
        "created_at": "2026-03-22T00:00:00Z",
        "entry_id": lexeme_id,
        "normalized_form": lemma,
        "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
    }


def _compiled_like_record(*, lexeme: LexemeRecord, definition: str = "to move quickly on foot") -> EnrichmentRecord:
    return EnrichmentRecord(
        snapshot_id=lexeme.snapshot_id,
        enrichment_id=f"en_{lexeme.lexeme_id}_1_v1",
        sense_id=f"sn_{lexeme.lexeme_id}_1",
        lexeme_id=lexeme.lexeme_id,
        sense_order=1,
        part_of_speech="verb",
        sense_kind="standard_meaning",
        decision="keep_standard",
        base_word=None,
        definition=definition,
        examples=[SenseExample(sentence=f"I {lexeme.lemma} every morning.", difficulty="A1")],
        cefr_level="A1",
        primary_domain="general",
        secondary_domains=[],
        register="neutral",
        synonyms=["jog"],
        antonyms=["walk"],
        collocations=[f"{lexeme.lemma} fast"],
        grammar_patterns=[f"{lexeme.lemma} + adverb"],
        usage_note="Common everyday verb.",
        forms={
            "plural_forms": [],
            "verb_forms": {
                "base": lexeme.lemma,
                "third_person_singular": f"{lexeme.lemma}s",
                "past": "ran" if lexeme.lemma == "run" else f"{lexeme.lemma}ed",
                "past_participle": "run" if lexeme.lemma == "run" else f"{lexeme.lemma}ed",
                "gerund": "running" if lexeme.lemma == "run" else f"{lexeme.lemma}ing",
            },
            "comparative": None,
            "superlative": None,
            "derivations": [],
        },
        confusable_words=[],
        model_name="gpt-5.4",
        prompt_version="v1",
        generation_run_id="run-1",
        confidence=0.92,
        review_status="draft",
        generated_at="2026-03-22T00:00:00Z",
        translations={
            "zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": ["zh:example"]},
            "es": {"definition": "es:def", "usage_note": "es:note", "examples": ["es:example"]},
            "ar": {"definition": "ar:def", "usage_note": "ar:note", "examples": ["ar:example"]},
            "pt-BR": {"definition": "pt:def", "usage_note": "pt:note", "examples": ["pt:example"]},
            "ja": {"definition": "ja:def", "usage_note": "ja:note", "examples": ["ja:example"]},
        },
    )


class RealtimeUnifiedFlowTests(unittest.TestCase):
    def test_per_word_realtime_writes_words_enriched_directly_from_lexemes_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            write_jsonl(snapshot_dir / "lexemes.jsonl", [_lexeme_row()])

            def provider(*, lexeme, senses, settings, generated_at, generation_run_id, prompt_version):
                self.assertEqual(senses, [])
                return WordJobOutcome(
                    records=[_compiled_like_record(lexeme=lexeme)],
                    decision="keep_standard",
                    base_word=None,
                    discard_reason=None,
                )

            result = enrich_snapshot(
                snapshot_dir,
                word_provider=provider,
                mode="per_word",
                generated_at="2026-03-22T00:00:00Z",
                generation_run_id="run-1",
                prompt_version="v1",
            )

            self.assertEqual(len(result), 1)
            compiled_path = snapshot_dir / "words.enriched.jsonl"
            self.assertTrue(compiled_path.exists())
            self.assertFalse((snapshot_dir / "enrichments.jsonl").exists())
            payload = [json.loads(line) for line in compiled_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["entry_id"], "lx_run")
            self.assertEqual(payload[0]["word"], "run")
            self.assertEqual(payload[0]["senses"][0]["definition"], "to move quickly on foot")


class BatchUnifiedFlowTests(unittest.TestCase):
    def test_batch_ingest_materializes_words_and_regenerate_queue_from_shared_word_contract(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            lexeme_rows = [_lexeme_row(lemma="run", lexeme_id="lx_run"), _lexeme_row(lemma="bank", lexeme_id="lx_bank", rank=20)]
            request_rows = build_batch_request_rows(
                snapshot_id="snap-1",
                model="gpt-5.4-mini",
                prompt_version="v1",
                rows=lexeme_rows,
            )
            write_jsonl(snapshot_dir / "batch_requests.jsonl", request_rows)

            accepted_payload = {
                "decision": "keep_standard",
                "discard_reason": None,
                "base_word": None,
                "phonetics": {
                    "us": {"ipa": "/rʌn/", "confidence": 0.99},
                    "uk": {"ipa": "/rʌn/", "confidence": 0.98},
                    "au": {"ipa": "/rɐn/", "confidence": 0.97},
                },
                "senses": [
                    {
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
                        "forms": {
                            "plural_forms": [],
                            "verb_forms": {
                                "base": "run",
                                "third_person_singular": "runs",
                                "past": "ran",
                                "past_participle": "run",
                                "gerund": "running",
                            },
                            "comparative": None,
                            "superlative": None,
                            "derivations": [],
                        },
                        "confusable_words": [],
                        "confidence": 0.91,
                        "translations": {
                            "zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": ["zh:example"]},
                            "es": {"definition": "es:def", "usage_note": "es:note", "examples": ["es:example"]},
                            "ar": {"definition": "ar:def", "usage_note": "ar:note", "examples": ["ar:example"]},
                            "pt-BR": {"definition": "pt:def", "usage_note": "pt:note", "examples": ["pt:example"]},
                            "ja": {"definition": "ja:def", "usage_note": "ja:note", "examples": ["ja:example"]},
                        },
                    }
                ],
            }
            invalid_payload = {
                "decision": "keep_standard",
                "discard_reason": None,
                "base_word": None,
                "phonetics": {
                    "us": {"ipa": "/bæŋk/", "confidence": 0.95},
                    "uk": {"ipa": "/bæŋk/", "confidence": 0.94},
                    "au": {"ipa": "/bæŋk/", "confidence": 0.93},
                },
                "senses": [
                    {
                        "part_of_speech": "noun",
                        "sense_kind": "standard_meaning",
                        "definition": "a financial institution",
                        "examples": [],
                        "cefr_level": "A2",
                        "primary_domain": "finance",
                        "secondary_domains": [],
                        "register": "neutral",
                        "synonyms": [],
                        "antonyms": [],
                        "collocations": ["bank account"],
                        "grammar_patterns": [],
                        "usage_note": "Common finance noun.",
                        "forms": {
                            "plural_forms": ["banks"],
                            "verb_forms": {},
                            "comparative": None,
                            "superlative": None,
                            "derivations": [],
                        },
                        "confusable_words": [],
                        "confidence": 0.5,
                        "translations": {
                            "zh-Hans": {"definition": "zh:def", "usage_note": "zh:note", "examples": []},
                            "es": {"definition": "es:def", "usage_note": "es:note", "examples": []},
                            "ar": {"definition": "ar:def", "usage_note": "ar:note", "examples": []},
                            "pt-BR": {"definition": "pt:def", "usage_note": "pt:note", "examples": []},
                            "ja": {"definition": "ja:def", "usage_note": "ja:note", "examples": []},
                        },
                    }
                ],
            }

            batch_output_path = snapshot_dir / "batch_output.jsonl"
            write_jsonl(
                batch_output_path,
                [
                    {
                        "custom_id": request_rows[0]["custom_id"],
                        "response": {
                            "body": {
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [{"type": "output_text", "text": json.dumps(accepted_payload)}],
                                    }
                                ]
                            }
                        },
                    },
                    {
                        "custom_id": request_rows[1]["custom_id"],
                        "response": {
                            "body": {
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [{"type": "output_text", "text": json.dumps(invalid_payload)}],
                                    }
                                ]
                            }
                        },
                    },
                ],
            )

            result_rows = ingest_batch_outputs(
                snapshot_dir=snapshot_dir,
                output_path=snapshot_dir / "batch_results.jsonl",
                request_path=snapshot_dir / "batch_requests.jsonl",
                batch_output_path=batch_output_path,
                ingested_at="2026-03-22T00:00:00Z",
                failure_output_path=snapshot_dir / "enrich.failures.jsonl",
            )

            compiled_rows = [json.loads(line) for line in (snapshot_dir / "words.enriched.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
            regenerate_rows = [json.loads(line) for line in (snapshot_dir / "words.regenerate.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]

            self.assertEqual(len(result_rows), 2)
            self.assertEqual(compiled_rows[0]["entry_id"], "lx_run")
            self.assertEqual(compiled_rows[0]["word"], "run")
            self.assertEqual(regenerate_rows[0]["entry_id"], "lx_bank")
            self.assertIn("examples", regenerate_rows[0]["failure_reason"])


if __name__ == "__main__":
    unittest.main()
