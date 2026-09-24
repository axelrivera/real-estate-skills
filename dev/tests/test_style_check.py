"""Tests for dev/style_check.py's text rules (DOC-6, DOC-12)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import style_check as sc  # noqa: E402


class Rules(unittest.TestCase):
    def test_headings(self):
        self.assertEqual(sc.heading_errors("Gather the Inputs"), [])
        self.assertEqual(sc.heading_errors("3. Write report.json"), [])  # file names keep their spelling
        self.assertEqual(sc.heading_errors("Slides and `deck` Wording"), [])
        self.assertEqual(sc.heading_errors("offers[]"), [])  # a field key
        self.assertTrue(sc.heading_errors("Gather the inputs"))

    def test_word_dashes(self):
        self.assertTrue(sc.WORD_DASH.search("the net -- after costs"))
        self.assertTrue(sc.WORD_DASH.search("the net – after costs"))
        self.assertIsNone(sc.WORD_DASH.search("$455,000 – $480,000"))  # a number range is fine
        self.assertIsNone(sc.WORD_DASH.search("run it with --out DIR"))


if __name__ == "__main__":
    unittest.main()
