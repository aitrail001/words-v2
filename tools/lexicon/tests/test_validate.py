import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.models import CompiledWordRecord, EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord
from tools.lexicon.validate import validate_compiled_record, validate_snapshot, validate_snapshot_files


class ValidateSnapshotTests(unittest.TestCase):
    def setUp(self) -> None:
        self.lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        self.sense = SenseRecord(
            snapshot_id="snap-1",
            sense_id="sn_lx_run_1",
            lexeme_id="lx_run",
            wn_synset_id="run.v.01",
            part_of_speech="verb",
            canonical_gloss="move fast by using your legs",
            selection_reason="common learner sense",
            sense_order=1,
            is_high_polysemy=False,
            created_at="2026-03-07T00:00:00Z",
        )
        self.enrichment = EnrichmentRecord(
            snapshot_id="snap-1",
            enrichment_id="en_sn_lx_run_1_v1",
            sense_id="sn_lx_run_1",
            definition="to move quickly on foot",
            examples=[SenseExample(sentence="I run every morning.", difficulty="A1")],
            cefr_level="A1",
            primary_domain="general",
            secondary_domains=[],
            register="neutral",
            synonyms=["jog"],
            antonyms=["walk"],
            collocations=["run fast"],
            grammar_patterns=["run + adverb"],
            usage_note="Common everyday verb.",
            forms={
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
                "derivations": ["runner"],
            },
            confusable_words=[{"word": "ran", "note": "Past tense form."}],
            model_name="gpt-5.4",
            prompt_version="v1",
            generation_run_id="run-123",
            confidence=0.9,
            review_status="draft",
            generated_at="2026-03-07T00:00:00Z",
        )

    def test_validate_snapshot_accepts_linked_records(self) -> None:
        errors = validate_snapshot(
            lexemes=[self.lexeme],
            senses=[self.sense],
            enrichments=[self.enrichment],
        )

        self.assertEqual(errors, [])

    def test_validate_snapshot_flags_missing_parent_links(self) -> None:
        orphan_sense = SenseRecord(
            snapshot_id="snap-1",
            sense_id="sn_missing_1",
            lexeme_id="lx_missing",
            wn_synset_id=None,
            part_of_speech="noun",
            canonical_gloss="missing parent",
            selection_reason="fallback",
            sense_order=1,
            is_high_polysemy=False,
            created_at="2026-03-07T00:00:00Z",
        )

        errors = validate_snapshot(lexemes=[self.lexeme], senses=[orphan_sense], enrichments=[])

        self.assertIn("sense sn_missing_1 links missing lexeme lx_missing", errors)

    def test_validate_snapshot_flags_duplicate_senses_per_lexeme(self) -> None:
        duplicate = SenseRecord(
            snapshot_id="snap-1",
            sense_id="sn_lx_run_2",
            lexeme_id="lx_run",
            wn_synset_id="run.v.99",
            part_of_speech="verb",
            canonical_gloss="move fast by using your legs",
            selection_reason="duplicate",
            sense_order=2,
            is_high_polysemy=False,
            created_at="2026-03-07T00:00:00Z",
        )

        errors = validate_snapshot(
            lexemes=[self.lexeme],
            senses=[self.sense, duplicate],
            enrichments=[self.enrichment],
        )

        self.assertIn("duplicate sense for lexeme lx_run: verb|move fast by using your legs", errors)

    def test_validate_snapshot_flags_missing_examples(self) -> None:
        no_example = EnrichmentRecord(
            snapshot_id="snap-1",
            enrichment_id="en_sn_lx_run_1_v2",
            sense_id="sn_lx_run_1",
            definition="to move quickly on foot",
            examples=[],
            cefr_level="A1",
            primary_domain="general",
            secondary_domains=[],
            register="neutral",
            synonyms=[],
            antonyms=[],
            collocations=[],
            grammar_patterns=[],
            usage_note="",
            forms={
                "plural_forms": [],
                "verb_forms": {},
                "comparative": None,
                "superlative": None,
                "derivations": [],
            },
            confusable_words=[],
            model_name="gpt-5.4",
            prompt_version="v1",
            generation_run_id="run-456",
            confidence=0.9,
            review_status="draft",
            generated_at="2026-03-07T00:00:00Z",
        )

        errors = validate_snapshot(
            lexemes=[self.lexeme],
            senses=[self.sense],
            enrichments=[no_example],
        )

        self.assertIn("enrichment en_sn_lx_run_1_v2 must include at least one example", errors)


    def test_validate_snapshot_files_reads_jsonl_inputs(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "lexemes.jsonl").write_text(json.dumps(self.lexeme.to_dict()) + "\n", encoding="utf-8")
            (root / "senses.jsonl").write_text(json.dumps(self.sense.to_dict()) + "\n", encoding="utf-8")
            (root / "enrichments.jsonl").write_text(json.dumps(self.enrichment.to_dict()) + "\n", encoding="utf-8")

            errors = validate_snapshot_files(root)

            self.assertEqual(errors, [])


class ValidateCompiledRecordTests(unittest.TestCase):
    def test_validate_compiled_record_flags_missing_required_top_level_fields(self) -> None:
        errors = validate_compiled_record(
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb"],
            }
        )

        self.assertIn("missing required field: cefr_level", errors)
        self.assertIn("missing required field: senses", errors)

    def test_validate_compiled_record_accepts_full_shape(self) -> None:
        record = CompiledWordRecord(
            schema_version="1.0.0",
            word="run",
            part_of_speech=["verb"],
            cefr_level="A1",
            frequency_rank=5,
            forms={
                "plural_forms": [],
                "verb_forms": {"base": "run"},
                "comparative": None,
                "superlative": None,
                "derivations": [],
            },
            senses=[
                {
                    "sense_id": "sn_lx_run_1",
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
            confusable_words=[],
            generated_at="2026-03-07T00:00:00Z",
        )

        self.assertEqual(validate_compiled_record(record), [])



if __name__ == "__main__":
    unittest.main()
