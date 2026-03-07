import unittest

from tools.lexicon.models import CompiledWordRecord, ConceptRecord, EnrichmentRecord, ExpressionRecord, LexemeRecord, SenseExample, SenseRecord


class ModelSerializationTests(unittest.TestCase):
    def test_lexeme_record_serializes_expected_fields(self) -> None:
        record = LexemeRecord(
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            lexeme_id="lx_run",
            lemma="run",
            language="en",
            wordfreq_rank=5,
            is_wordnet_backed=True,
            source_refs=["wordnet", "wordfreq"],
            created_at="2026-03-07T00:00:00Z",
        )

        self.assertEqual(record.to_dict()["lemma"], "run")
        self.assertEqual(record.to_dict()["wordfreq_rank"], 5)

    def test_compiled_word_record_supports_full_learner_jsonl_shape(self) -> None:
        record = CompiledWordRecord(
            schema_version="1.0.0",
            word="run",
            part_of_speech=["verb", "noun"],
            cefr_level="A1",
            frequency_rank=5,
            forms={
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
            confusable_words=[{"word": "ran", "note": "Past tense, not a different lemma."}],
            generated_at="2026-03-07T00:00:00Z",
        )

        payload = record.to_dict()

        self.assertEqual(
            list(payload.keys()),
            [
                "schema_version",
                "word",
                "part_of_speech",
                "cefr_level",
                "frequency_rank",
                "forms",
                "senses",
                "confusable_words",
                "generated_at",
            ],
        )
        self.assertEqual(payload["senses"][0]["examples"][0]["sentence"], "I run every morning.")

    def test_supporting_records_serialize_with_links(self) -> None:
        sense = SenseRecord(
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            sense_id="sn_lx_run_1",
            lexeme_id="lx_run",
            wn_synset_id="run.v.01",
            part_of_speech="verb",
            canonical_gloss="move fast by using your legs",
            selection_reason="common learner sense",
            sense_order=1,
            is_high_polysemy=True,
            created_at="2026-03-07T00:00:00Z",
        )
        enrichment = EnrichmentRecord(
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
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
            forms={"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
            confusable_words=[{"word": "ran", "note": "Past tense form."}],
            model_name="gpt-5.4",
            prompt_version="v1",
            generation_run_id="run-123",
            confidence=0.9,
            review_status="draft",
            generated_at="2026-03-07T00:00:00Z",
        )
        concept = ConceptRecord(
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            concept_id="cp_run_v_01",
            wn_synset_id="run.v.01",
            canonical_label="run",
            part_of_speech="verb",
            gloss="move fast by using your legs",
            lemma_ids=["lx_run"],
            created_at="2026-03-07T00:00:00Z",
        )
        expression = ExpressionRecord(
            snapshot_id="lexicon-20260307-wordnet-wordfreq",
            expression_id="ex_run_out_of",
            expression_text="run out of",
            expression_type="phrasal_verb",
            linked_lexeme_ids=["lx_run"],
            linked_concept_ids=["cp_run_v_01"],
            base_definition="to use all of something so none remains",
            enrichment_ref="en_sn_lx_run_1_v1",
            source_type="custom",
            created_at="2026-03-07T00:00:00Z",
        )

        self.assertEqual(sense.to_dict()["lexeme_id"], "lx_run")
        self.assertEqual(enrichment.to_dict()["examples"][0]["difficulty"], "A1")
        self.assertEqual(concept.to_dict()["lemma_ids"], ["lx_run"])
        self.assertEqual(expression.to_dict()["linked_concept_ids"], ["cp_run_v_01"])


if __name__ == "__main__":
    unittest.main()
