"""Tests for dev/manual_kit/build.py's smoke checks (the kit itself is built by make manual-kit)."""
import importlib.util
import os
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
spec = importlib.util.spec_from_file_location("manual_kit", os.path.join(ROOT, "dev", "manual_kit", "build.py"))
kit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kit)


class Checks(unittest.TestCase):
    def test_every_check_has_a_place(self):
        for case, checks in kit.CHECKS.items():
            self.assertTrue(checks, case)
            for text, where in checks:
                self.assertIn(where, kit.WHERE, text)

    def test_a_short_pass(self):
        """About ten yes/no checks: one pass per release in about twenty minutes."""
        texts = {text for checks in kit.CHECKS.values() for text, _ in checks}
        self.assertLessEqual(len(texts), 14)

    def test_black_box(self):
        """No check asks the tester for a data file or anything the skill makes along the way."""
        for case, checks in kit.CHECKS.items():
            for text, _ in checks:
                for word in ("JSON", "json", "data file", "deal file", "handoff", "script"):
                    self.assertNotIn(word, text, f"{case}: {text}")

    def test_platform_checks_only(self):
        """Content, numbers and layout are covered by golden, the generated tests and the evals, never by hand."""
        for case, checks in kit.CHECKS.items():
            for text, _ in checks:
                for word in ("match", "band", "same numbers", "layout", "overflow"):
                    self.assertNotIn(word, text.lower(), f"{case}: {text}")

    def test_claude_ai_pass(self):
        """The claude.ai pass runs cases 1, 2 and 6, so each has a check there."""
        for case in ("01-agent-profile", "02-seller-cma", "06-contract-timeline-fha"):
            self.assertTrue(any(where in ("both", "ai") for _, where in kit.CHECKS[case]), case)

    def test_results_table(self):
        md = kit.results_md()
        self.assertIn("| Case | Check | Cowork | claude.ai | Notes |", md)
        rows = [line for line in md.splitlines() if line.startswith("| 0")]
        self.assertEqual(len(rows), sum(len(c) for c in kit.CHECKS.values()))


if __name__ == "__main__":
    unittest.main()
