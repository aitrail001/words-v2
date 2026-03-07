import tempfile
import json
import unittest
from pathlib import Path

from tools.lexicon.compile_export import compile_snapshot, compile_words
from tools.lexicon.models import EnrichmentRecord, LexemeRecord, SenseExample, SenseRecord


class CompileWordsTests(unittest.TestCase):
    def test_compile_words_groups_normalized_records_into_compiled_rows(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        senses = [
            SenseRecord(
                snapshot_id="snap-1",
                sense_id="sn_lx_run_2",
                lexeme_id="lx_run",
                wn_synset_id="run.n.01",
                part_of_speech="noun",
                canonical_gloss="a period of running",
                selection_reason="common exercise sense",
                sense_order=2,
                is_high_polysemy=False,
                created_at="2026-03-07T00:00:00Z",
            ),
            SenseRecord(
                snapshot_id="snap-1",
                sense_id="sn_lx_run_1",
                lexeme_id="lx_run",
                wn_synset_id="run.v.01",
                part_of_speech="verb",
                canonical_gloss="move fast by using your legs",
                selection_reason="core learner sense",
                sense_order=1,
                is_high_polysemy=False,
                created_at="2026-03-07T00:00:00Z",
            ),
        ]
        enrichments = [
            EnrichmentRecord(
                snapshot_id="snap-1",
                enrichment_id="en_sn_lx_run_2_v1",
                sense_id="sn_lx_run_2",
                definition="a period of running for exercise",
                examples=[SenseExample(sentence="She went for a run.", difficulty="A1")],
                cefr_level="A1",
                primary_domain="sports_fitness",
                secondary_domains=[],
                register="neutral",
                synonyms=["jog"],
                antonyms=[],
                collocations=["go for a run"],
                grammar_patterns=["go for a run"],
                usage_note="Common exercise expression.",
                forms={
                    "plural_forms": ["runs"],
                    "verb_forms": {},
                    "comparative": None,
                    "superlative": None,
                    "derivations": [],
                },
                confusable_words=[],
                model_name="gpt-5.4",
                prompt_version="v1",
                generation_run_id="run-1",
                confidence=0.8,
                review_status="approved",
                generated_at="2026-03-07T00:00:00Z",
            ),
            EnrichmentRecord(
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
                generation_run_id="run-1",
                confidence=0.9,
                review_status="approved",
                generated_at="2026-03-07T00:00:00Z",
            ),
        ]

        compiled = compile_words(lexemes=[lexeme], senses=senses, enrichments=enrichments)

        self.assertEqual(len(compiled), 1)
        row = compiled[0].to_dict()
        self.assertEqual(row["word"], "run")
        self.assertEqual(row["part_of_speech"], ["verb", "noun"])
        self.assertEqual([sense["sense_id"] for sense in row["senses"]], ["sn_lx_run_1", "sn_lx_run_2"])
        self.assertEqual(row["confusable_words"], [{"word": "ran", "note": "Past tense form."}])
        self.assertEqual(row["frequency_rank"], 5)

    def test_compile_words_skips_lexemes_without_enrichments(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        senses = [
            SenseRecord(
                snapshot_id="snap-1",
                sense_id="sn_lx_run_1",
                lexeme_id="lx_run",
                wn_synset_id="run.v.01",
                part_of_speech="verb",
                canonical_gloss="move fast by using your legs",
                selection_reason="core learner sense",
                sense_order=1,
                is_high_polysemy=False,
                created_at="2026-03-07T00:00:00Z",
            ),
        ]

        compiled = compile_words(lexemes=[lexeme], senses=senses, enrichments=[])

        self.assertEqual(compiled, [])



    def test_compile_snapshot_reads_jsonl_and_writes_export(self) -> None:
        lexeme = LexemeRecord(
            snapshot_id="snap-1",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )
        sense = SenseRecord(
            snapshot_id="snap-1",
            sense_id="sn_lx_run_1",
            lexeme_id="lx_run",
            wn_synset_id="run.v.01",
            part_of_speech="verb",
            canonical_gloss="move fast by using your legs",
            selection_reason="core learner sense",
            sense_order=1,
            is_high_polysemy=False,
            created_at="2026-03-07T00:00:00Z",
        )
        enrichment = EnrichmentRecord(
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
            review_status="approved",
            generated_at="2026-03-07T00:00:00Z",
        )
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            (root / "lexemes.jsonl").write_text(json.dumps(lexeme.to_dict()) + "\n", encoding="utf-8")
            (root / "senses.jsonl").write_text(json.dumps(sense.to_dict()) + "\n", encoding="utf-8")
            (root / "enrichments.jsonl").write_text(json.dumps(enrichment.to_dict()) + "\n", encoding="utf-8")

            out_path = root / "words.enriched.jsonl"
            compiled = compile_snapshot(root, out_path)

            self.assertEqual(len(compiled), 1)
            self.assertTrue(out_path.exists())
            payload = json.loads(out_path.read_text(encoding="utf-8").strip())
            self.assertEqual(payload["word"], "run")
            self.assertEqual(payload["senses"][0]["definition"], "to move quickly on foot")


if __name__ == "__main__":
    unittest.main()
