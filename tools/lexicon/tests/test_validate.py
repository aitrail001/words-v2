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


    def test_validate_snapshot_files_flags_unresolved_ambiguous_form_leaking_into_lexemes(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            leaked_lexeme = LexemeRecord(
                snapshot_id="snap-1",
                lexeme_id="lx_ringed",
                lemma="ringed",
                language="en",
                wordfreq_rank=1000,
                is_wordnet_backed=False,
                source_refs=["wordfreq"],
                created_at="2026-03-12T00:00:00Z",
            )
            leaked_sense = SenseRecord(
                snapshot_id="snap-1",
                sense_id="sn_lx_ringed_1",
                lexeme_id="lx_ringed",
                wn_synset_id=None,
                part_of_speech="noun",
                canonical_gloss="fallback",
                selection_reason="fallback learner sense",
                sense_order=1,
                is_high_polysemy=False,
                created_at="2026-03-12T00:00:00Z",
            )
            (root / "lexemes.jsonl").write_text(json.dumps(leaked_lexeme.to_dict()) + "\n", encoding="utf-8")
            (root / "senses.jsonl").write_text(json.dumps(leaked_sense.to_dict()) + "\n", encoding="utf-8")
            (root / "canonical_variants.jsonl").write_text(json.dumps({
                "snapshot_id": "snap-1",
                "entry_id": "lx_ringed",
                "surface_form": "ringed",
                "canonical_form": "ringed",
                "decision": "unknown_needs_llm",
                "decision_reason": "deterministic signals found candidate forms but no strong canonical winner",
                "confidence": 0.45,
                "variant_type": "ambiguous",
                "created_at": "2026-03-12T00:00:00Z",
                "linked_canonical_form": None,
                "is_separately_learner_worthy": True,
                "candidate_forms": ["ring"],
                "ambiguity_reason": "candidate set exists but deterministic score stayed below the collapse threshold",
                "needs_llm_adjudication": True,
            }) + "\n", encoding="utf-8")
            (root / "ambiguous_forms.jsonl").write_text(json.dumps({
                "surface_form": "ringed",
                "deterministic_decision": "unknown_needs_llm",
                "canonical_form": "ringed",
                "linked_canonical_form": None,
                "candidate_forms": ["ring"],
                "decision_reason": "deterministic signals found candidate forms but no strong canonical winner",
                "confidence": 0.45,
                "wordfreq_rank": 1000,
                "sense_labels": ["ring"],
                "ambiguity_reason": "candidate set exists but deterministic score stayed below the collapse threshold",
            }) + "\n", encoding="utf-8")

            errors = validate_snapshot_files(root)

            self.assertIn("unresolved ambiguous form ringed should not appear in lexemes.jsonl before adjudication", errors)


class ValidateCompiledRecordTests(unittest.TestCase):
    def test_validate_compiled_record_flags_missing_required_top_level_fields(self) -> None:
        errors = validate_compiled_record(
            {
                "schema_version": "1.0.0",
                "word": "run",
                "part_of_speech": ["verb"],
            }
        )

        self.assertIn("missing required field: entry_id", errors)
        self.assertIn("missing required field: entry_type", errors)
        self.assertIn("missing required field: normalized_form", errors)
        self.assertIn("missing required field: source_provenance", errors)
        self.assertIn("missing required field: cefr_level", errors)
        self.assertIn("missing required field: senses", errors)

    def test_validate_compiled_record_accepts_full_shape(self) -> None:
        record = CompiledWordRecord(
            schema_version="1.1.0",
            entry_id="lx_run",
            entry_type="word",
            normalized_form="run",
            source_provenance=[{"source": "wordfreq"}],
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

    def test_validate_compiled_record_accepts_phrase_shape(self) -> None:
        errors = validate_compiled_record(
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
                "senses": [],
                "confusable_words": [],
                "generated_at": "2026-03-20T00:00:00Z",
                "phrase_kind": "phrasal_verb",
                "display_form": "take off",
            }
        )

        self.assertEqual(errors, [])

    def test_validate_compiled_record_accepts_reference_shape(self) -> None:
        errors = validate_compiled_record(
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
            }
        )

        self.assertEqual(errors, [])



if __name__ == "__main__":
    unittest.main()


    def test_validate_compiled_record_rejects_too_many_senses_for_frequency_band(self) -> None:
        record = {
            "schema_version": "1.1.0",
            "entry_id": "lx_rare",
            "entry_type": "word",
            "normalized_form": "rareword",
            "source_provenance": [{"source": "wordfreq"}],
            "word": "rareword",
            "part_of_speech": ["noun"],
            "cefr_level": "B2",
            "frequency_rank": 12000,
            "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            "senses": [
                {"sense_id": f"sn_{idx}", "pos": "noun", "primary_domain": "general", "secondary_domains": [], "register": "neutral", "definition": "x", "examples": [{"sentence": "x", "difficulty": "A1"}], "synonyms": [], "antonyms": [], "collocations": [], "grammar_patterns": [], "usage_note": ""}
                for idx in range(5)
            ],
            "confusable_words": [],
            "generated_at": "2026-03-07T00:00:00Z",
        }

        errors = validate_compiled_record(record)

        self.assertIn("senses exceeds allowed limit 4 for frequency_rank 12000", errors)
