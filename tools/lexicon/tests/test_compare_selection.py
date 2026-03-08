import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.compare_selection import compare_selection_artifacts


class CompareSelectionTests(unittest.TestCase):
    def test_compare_selection_reports_changed_ids_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir) / "snapshot"
            snapshot_dir.mkdir()
            (snapshot_dir / "lexemes.jsonl").write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "language": "en",
                    "wordfreq_rank": 5,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordnet", "wordfreq"],
                    "created_at": "2026-03-08T00:00:00Z",
                }) + "\n",
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
                        "created_at": "2026-03-08T00:00:00Z",
                    }),
                    json.dumps({
                        "snapshot_id": "snap-1",
                        "sense_id": "sn_lx_run_2",
                        "lexeme_id": "lx_run",
                        "wn_synset_id": "run.n.01",
                        "part_of_speech": "noun",
                        "canonical_gloss": "a score in baseball",
                        "selection_reason": "common learner sense",
                        "sense_order": 2,
                        "is_high_polysemy": False,
                        "created_at": "2026-03-08T00:00:00Z",
                    }),
                ]) + "\n",
                encoding="utf-8",
            )
            rerank_path = snapshot_dir / "sense_reranks.jsonl"
            rerank_path.write_text(
                json.dumps({
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_run",
                    "lemma": "run",
                    "candidate_wn_synset_ids": ["run.v.01", "run.n.01", "run.v.02"],
                    "selected_wn_synset_ids": ["run.n.01", "run.v.01"],
                    "model_name": "gpt-5.4",
                    "prompt_version": "rerank-v1",
                    "generation_run_id": "rerank-1",
                    "generated_at": "2026-03-08T00:00:00Z",
                }) + "\n",
                encoding="utf-8",
            )

            payload = compare_selection_artifacts(snapshot_dir, rerank_path)

            self.assertEqual(payload["compared_lexeme_count"], 1)
            self.assertEqual(payload["changed_lexeme_count"], 1)
            self.assertEqual(payload["changes"][0]["deterministic_wn_synset_ids"], ["run.v.01", "run.n.01"])
            self.assertEqual(payload["changes"][0]["reranked_wn_synset_ids"], ["run.n.01", "run.v.01"])


if __name__ == "__main__":
    unittest.main()
