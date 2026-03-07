import unittest

from tools.lexicon.ids import build_snapshot_id, make_concept_id, make_enrichment_id, make_lexeme_id, make_sense_id


class IdentifierTests(unittest.TestCase):
    def test_build_snapshot_id_is_deterministic(self) -> None:
        snapshot_id = build_snapshot_id(date_stamp="20260307", source_label="wordnet-wordfreq")

        self.assertEqual(snapshot_id, "lexicon-20260307-wordnet-wordfreq")

    def test_record_ids_keep_bootstrap_shapes_for_existing_integer_usage(self) -> None:
        self.assertEqual(make_lexeme_id("run"), "lx_run")
        self.assertEqual(make_sense_id("lx_run", 2), "sn_lx_run_2")
        self.assertEqual(make_enrichment_id("sn_lx_run_2", "v1"), "en_sn_lx_run_2_v1")

    def test_concept_ids_are_readable_and_collision_resistant(self) -> None:
        dot_variant = make_concept_id("run.v.01")
        underscore_variant = make_concept_id("run_v_01")

        self.assertTrue(dot_variant.startswith("cp_run_v_01_"))
        self.assertTrue(underscore_variant.startswith("cp_run_v_01_"))
        self.assertNotEqual(dot_variant, underscore_variant)

    def test_string_based_sense_ids_can_use_stable_canonical_refs(self) -> None:
        first = make_sense_id("lx_run", "run.v.01")
        second = make_sense_id("lx_run", "run.v.01")
        different = make_sense_id("lx_run", "run_v_01")

        self.assertEqual(first, second)
        self.assertTrue(first.startswith("sn_lx_run_run_v_01_"))
        self.assertNotEqual(first, different)


if __name__ == "__main__":
    unittest.main()
