import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from tools.lexicon import cli


class CanonicalRegistryCliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str, str]:
        stdout = io.StringIO()
        stderr = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            try:
                code = cli.main(argv)
            except SystemExit as exc:
                code = int(exc.code)
        return code, stdout.getvalue(), stderr.getvalue()

    def _write_lines(self, path: Path, rows: list[dict]) -> None:
        path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")

    def test_lookup_entry_command_returns_canonical_mapping(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_lines(
                root / "canonical_entries.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "entry_id": "lx_thing",
                    "canonical_form": "thing",
                    "display_form": "thing",
                    "normalized_form": "thing",
                    "source_forms": ["things"],
                    "created_at": "2026-03-12T00:00:00Z",
                    "language": "en",
                    "entry_type": "word",
                    "linked_canonical_form": None,
                    "notes": None,
                }],
            )
            self._write_lines(
                root / "canonical_variants.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "entry_id": "lx_thing",
                    "surface_form": "things",
                    "canonical_form": "thing",
                    "decision": "collapse_to_canonical",
                    "decision_reason": "suffix normalization points to candidate",
                    "confidence": 0.9,
                    "variant_type": "inflectional",
                    "created_at": "2026-03-12T00:00:00Z",
                    "linked_canonical_form": None,
                    "is_separately_learner_worthy": False,
                }],
            )

            code, stdout, _ = self.run_cli(["lookup-entry", "--snapshot-dir", str(root), "things"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "lookup-entry")
            self.assertEqual(payload["canonical_form"], "thing")
            self.assertEqual(payload["decision"], "collapse_to_canonical")

    def test_status_entry_command_reports_db_status_when_enabled(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            self._write_lines(
                root / "canonical_entries.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "entry_id": "lx_left",
                    "canonical_form": "left",
                    "display_form": "left",
                    "normalized_form": "left",
                    "source_forms": ["left"],
                    "created_at": "2026-03-12T00:00:00Z",
                    "language": "en",
                    "entry_type": "word",
                    "linked_canonical_form": "leave",
                    "notes": None,
                }],
            )
            self._write_lines(
                root / "canonical_variants.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "entry_id": "lx_left",
                    "surface_form": "left",
                    "canonical_form": "left",
                    "decision": "keep_both_linked",
                    "decision_reason": "surface form is learner-worthy on its own and also maps to a related base form",
                    "confidence": 0.9,
                    "variant_type": "lexicalized",
                    "created_at": "2026-03-12T00:00:00Z",
                    "linked_canonical_form": "leave",
                    "is_separately_learner_worthy": True,
                }],
            )
            self._write_lines(
                root / "lexemes.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "lexeme_id": "lx_left",
                    "lemma": "left",
                    "language": "en",
                    "wordfreq_rank": 15,
                    "is_wordnet_backed": True,
                    "source_refs": ["wordfreq", "wordnet"],
                    "created_at": "2026-03-12T00:00:00Z",
                    "entry_id": "lx_left",
                    "entry_type": "word",
                    "normalized_form": "left",
                    "source_provenance": [{"source": "wordfreq", "role": "frequency_rank"}],
                }],
            )
            self._write_lines(
                root / "senses.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "sense_id": "sn_lx_left_1",
                    "lexeme_id": "lx_left",
                    "wn_synset_id": "left.a.01",
                    "part_of_speech": "adjective",
                    "canonical_gloss": "on the opposite side from right",
                    "selection_reason": "selected canonical learner sense",
                    "sense_order": 1,
                    "is_high_polysemy": True,
                    "created_at": "2026-03-12T00:00:00Z",
                }],
            )
            self._write_lines(
                root / "enrichments.jsonl",
                [{
                    "snapshot_id": "snap-1",
                    "enrichment_id": "en_left_1",
                    "sense_id": "sn_lx_left_1",
                    "definition": "on the side opposite the right side",
                    "examples": [{"sentence": "Turn left at the lights.", "difficulty": "A1"}],
                    "cefr_level": "A1",
                    "primary_domain": "general",
                    "secondary_domains": [],
                    "register": "neutral",
                    "synonyms": [],
                    "antonyms": ["right"],
                    "collocations": [],
                    "grammar_patterns": [],
                    "usage_note": "",
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "confusable_words": [],
                    "model_name": "gpt-5.1",
                    "prompt_version": "v1",
                    "generation_run_id": "run-left",
                    "confidence": 0.9,
                    "review_status": "draft",
                    "generated_at": "2026-03-12T00:00:00Z",
                }],
            )
            self._write_lines(
                root / "words.enriched.jsonl",
                [{
                    "schema_version": "1.1.0",
                    "entry_id": "lx_left",
                    "entry_type": "word",
                    "normalized_form": "left",
                    "source_provenance": [{"source": "wordfreq"}],
                    "word": "left",
                    "part_of_speech": ["adjective"],
                    "cefr_level": "A1",
                    "frequency_rank": 15,
                    "forms": {"plural_forms": [], "verb_forms": {}, "comparative": None, "superlative": None, "derivations": []},
                    "senses": [],
                    "confusable_words": [],
                    "generated_at": "2026-03-12T00:00:00Z",
                }],
            )

            with patch("tools.lexicon.cli._db_word_lookup", return_value={"word": "left", "language": "en"}):
                code, stdout, _ = self.run_cli(["status-entry", "--snapshot-dir", str(root), "--check-db", "left"])

            self.assertEqual(code, 0)
            payload = json.loads(stdout)
            self.assertEqual(payload["command"], "status-entry")
            self.assertTrue(payload["base_built"])
            self.assertTrue(payload["enriched"])
            self.assertTrue(payload["compiled"])
            self.assertTrue(payload["published"])


if __name__ == "__main__":
    unittest.main()
