import json
import tempfile
import unittest
from pathlib import Path

from tools.lexicon.config import LexiconSettings
from tools.lexicon.rerank import build_rerank_prompt, run_rerank, validate_rerank_selection


class RerankTests(unittest.TestCase):
    def _write_snapshot(self, snapshot_dir: Path) -> None:
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
                    "canonical_gloss": "a score in baseball made by a runner touching all four bases safely",
                    "selection_reason": "common learner sense",
                    "sense_order": 2,
                    "is_high_polysemy": False,
                    "created_at": "2026-03-08T00:00:00Z",
                }),
            ]) + "\n",
            encoding="utf-8",
        )

    def _extract_candidates_from_prompt(self, prompt: str) -> list[dict[str, object]]:
        marker = "Candidates: "
        if marker not in prompt:
            self.fail("rerank prompt did not include candidates marker")
        tail = prompt.split(marker, 1)[1]
        candidates_json = tail.split("\n", 1)[0]
        parsed = json.loads(candidates_json)
        self.assertIsInstance(parsed, list)
        return parsed

    def test_build_rerank_prompt_mentions_candidates_and_selection_limit(self) -> None:
        prompt = build_rerank_prompt(
            lemma="run",
            target_count=2,
            candidates=[
                {"wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "lemma_count": 12},
                {"wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "lemma_count": 4},
            ],
        )

        self.assertIn("run.v.01", prompt)
        self.assertIn("run.n.01", prompt)
        self.assertIn("exactly 2", prompt.lower())

    def test_validate_rerank_selection_rejects_unknown_ids(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_rerank_selection(
                {"selected_wn_synset_ids": ["run.v.99"]},
                candidate_ids={"run.v.01", "run.n.01"},
                target_count=1,
            )

    def test_validate_rerank_selection_rejects_duplicates(self) -> None:
        with self.assertRaises(RuntimeError):
            validate_rerank_selection(
                {"selected_wn_synset_ids": ["run.v.01", "run.v.01"]},
                candidate_ids={"run.v.01", "run.n.01"},
                target_count=2,
            )

    def test_run_rerank_writes_jsonl_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            def transport(url, payload, headers):
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"selected_wn_synset_ids": ["run.v.01", "run.n.01"]}),
                                }
                            ],
                        }
                    ]
                }

            result = run_rerank(
                snapshot_dir,
                settings=settings,
                provider_mode="openai_compatible",
                candidate_limit=3,
                sense_provider=lambda lemma: [
                    {"query_lemma": "run", "wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "canonical_label": "run", "lemma_count": 12},
                    {"query_lemma": "run", "wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "canonical_label": "run", "lemma_count": 4},
                    {"query_lemma": "run", "wn_synset_id": "run.v.02", "part_of_speech": "verb", "canonical_gloss": "direct or control", "canonical_label": "run", "lemma_count": 2},
                ],
                transport=transport,
            )

            self.assertEqual(len(result.rows), 1)
            payload = [json.loads(line) for line in result.output_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(payload[0]["selected_wn_synset_ids"], ["run.v.01", "run.n.01"])

    def test_run_rerank_rejects_invented_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })

            def transport(url, payload, headers):
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"selected_wn_synset_ids": ["run.v.01", "invented.v.01"]}),
                                }
                            ],
                        }
                    ]
                }

            with self.assertRaises(RuntimeError):
                run_rerank(
                    snapshot_dir,
                    settings=settings,
                    provider_mode="openai_compatible",
                    candidate_limit=3,
                    sense_provider=lambda lemma: [
                        {"query_lemma": "run", "wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "canonical_label": "run", "lemma_count": 12},
                        {"query_lemma": "run", "wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "canonical_label": "run", "lemma_count": 4},
                    ],
                    transport=transport,
                )

    def test_run_rerank_selected_only_uses_snapshot_selected_senses_as_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })
            captured_candidate_ids: list[str] = []

            def transport(url, payload, headers):
                prompt = payload["input"]
                candidates = self._extract_candidates_from_prompt(prompt)
                captured_candidate_ids[:] = [
                    str(candidate["wn_synset_id"])
                    for candidate in candidates
                ]
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"selected_wn_synset_ids": ["run.v.01", "run.n.01"]}),
                                }
                            ],
                        }
                    ]
                }

            result = run_rerank(
                snapshot_dir,
                settings=settings,
                provider_mode="openai_compatible",
                candidate_limit=8,
                candidate_source="selected_only",
                sense_provider=lambda lemma: [
                    {"query_lemma": "run", "wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "canonical_label": "run", "lemma_count": 12},
                    {"query_lemma": "run", "wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "canonical_label": "run", "lemma_count": 4},
                    {"query_lemma": "run", "wn_synset_id": "run.v.02", "part_of_speech": "verb", "canonical_gloss": "direct or control", "canonical_label": "run", "lemma_count": 2},
                ],
                transport=transport,
            )

            self.assertEqual(captured_candidate_ids, ["run.v.01", "run.n.01"])
            self.assertEqual(result.rows[0]["candidate_wn_synset_ids"], ["run.v.01", "run.n.01"])

    def test_run_rerank_candidates_mode_includes_selected_plus_extra_candidates(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })
            captured_candidate_ids: list[str] = []

            def transport(url, payload, headers):
                prompt = payload["input"]
                candidates = self._extract_candidates_from_prompt(prompt)
                captured_candidate_ids[:] = [
                    str(candidate["wn_synset_id"])
                    for candidate in candidates
                ]
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"selected_wn_synset_ids": ["run.v.01", "run.n.01"]}),
                                }
                            ],
                        }
                    ]
                }

            result = run_rerank(
                snapshot_dir,
                settings=settings,
                provider_mode="openai_compatible",
                candidate_limit=8,
                candidate_source="candidates",
                sense_provider=lambda lemma: [
                    {"query_lemma": "run", "wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "canonical_label": "run", "lemma_count": 12},
                    {"query_lemma": "run", "wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "canonical_label": "run", "lemma_count": 4},
                    {"query_lemma": "run", "wn_synset_id": "run.v.02", "part_of_speech": "verb", "canonical_gloss": "operate or function", "canonical_label": "run", "lemma_count": 10},
                    {"query_lemma": "run", "wn_synset_id": "run.n.03", "part_of_speech": "noun", "canonical_gloss": "a period of success", "canonical_label": "run", "lemma_count": 9},
                ],
                transport=transport,
            )

            selected_ids = {"run.v.01", "run.n.01"}
            self.assertTrue(selected_ids.issubset(set(captured_candidate_ids)))
            self.assertGreater(len(captured_candidate_ids), len(selected_ids))
            self.assertTrue(any(candidate_id not in selected_ids for candidate_id in captured_candidate_ids))
            self.assertEqual(result.rows[0]["selected_wn_synset_ids"], ["run.v.01", "run.n.01"])

    def test_run_rerank_full_wordnet_mode_uses_ranked_wordnet_candidate_pool(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            snapshot_dir = Path(tmpdir)
            self._write_snapshot(snapshot_dir)
            settings = LexiconSettings.from_env({
                "LEXICON_LLM_BASE_URL": "https://example.test/v1",
                "LEXICON_LLM_MODEL": "gpt-test",
                "LEXICON_LLM_API_KEY": "secret-key",
            })
            captured_candidate_ids: list[str] = []

            def transport(url, payload, headers):
                prompt = payload["input"]
                candidates = self._extract_candidates_from_prompt(prompt)
                captured_candidate_ids[:] = [
                    str(candidate["wn_synset_id"])
                    for candidate in candidates
                ]
                return {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps({"selected_wn_synset_ids": captured_candidate_ids[:2]}),
                                }
                            ],
                        }
                    ]
                }

            result = run_rerank(
                snapshot_dir,
                settings=settings,
                provider_mode="openai_compatible",
                candidate_limit=3,
                candidate_source="full_wordnet",
                sense_provider=lambda lemma: [
                    {"query_lemma": "run", "wn_synset_id": "run.v.99", "part_of_speech": "verb", "canonical_gloss": "manage or operate", "canonical_label": "run", "lemma_count": 20},
                    {"query_lemma": "run", "wn_synset_id": "run.v.01", "part_of_speech": "verb", "canonical_gloss": "move fast by using your legs", "canonical_label": "run", "lemma_count": 12},
                    {"query_lemma": "run", "wn_synset_id": "run.n.01", "part_of_speech": "noun", "canonical_gloss": "a score in baseball", "canonical_label": "run", "lemma_count": 4},
                    {"query_lemma": "run", "wn_synset_id": "run.n.03", "part_of_speech": "noun", "canonical_gloss": "a period of success", "canonical_label": "run", "lemma_count": 9},
                ],
                transport=transport,
            )

            self.assertEqual(len(captured_candidate_ids), 4)
            self.assertIn("run.v.99", captured_candidate_ids)
            self.assertTrue(any(candidate_id not in {"run.v.01", "run.n.01"} for candidate_id in captured_candidate_ids))
            self.assertEqual(len(result.rows[0]["selected_wn_synset_ids"]), 2)


if __name__ == "__main__":
    unittest.main()
