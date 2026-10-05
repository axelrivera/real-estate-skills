"""Tests for dev/manual_kit/build.py's checks (the kit itself is built by make manual-kit)."""
import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
spec = importlib.util.spec_from_file_location("manual_kit", os.path.join(ROOT, "dev", "manual_kit", "build.py"))
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class Checks(unittest.TestCase):
    def test_every_check_has_a_place_and_a_type(self):
        for case, checks in kit.CHECKS.items():
            for text, where, kind in checks:
                self.assertIn(where, ("both", "cowork", "ai"), text)
                self.assertIn(kind, kit.KINDS, text)

    def test_black_box(self):
        """No check asks the tester for a data file or anything the skill makes along the way."""
        for case, checks in kit.CHECKS.items():
            for text, _, _ in checks:
                for word in ("JSON", "json", "data file", "deal file", "handoff", "script"):
                    self.assertNotIn(word, text, f"{case}: {text}")

    def test_fixed_numbers_only_where_inputs_determine_them(self):
        """Judgment cases are checked by band or consistency; case 4 against the case 3 report, never expected.md."""
        for case, checks in kit.CHECKS.items():
            kinds = {kind for _, _, kind in checks}
            if case.startswith("04-"):
                self.assertNotIn("fixed", kinds)
                self.assertFalse(any("expected.md" in t for t, _, _ in checks))
                self.assertTrue(any("case 3" in t for t, _, k in checks if k == "consistency"))
            if case.startswith(("02-", "03-")):
                self.assertIn("band", kinds)
        self.assertEqual(kit.check_texts("06-contract-timeline-fha")[0], "Deadlines match expected.md (Fixed)")

    def test_results_table_has_the_type(self):
        md = kit.results_md()
        self.assertIn("| Case | Check | Type | Cowork | claude.ai | Notes |", md)
        self.assertIn("| Consistency |", md)


if __name__ == "__main__":
    unittest.main()
