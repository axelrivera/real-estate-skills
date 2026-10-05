"""Tests for dev/style_check.py's text rules: headings, word dashes, estimate marks in labels."""
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

    def test_estimate_marks_in_labels(self):
        """Owner rule: Assumed / Estimate marks never sit in a header, a row label, a tile or a fact chip; notes may
        say them, and a label that names the figure ("Estimated Net") is fine."""
        bad = ('<table><thead><tr><th>Estimated Net*<br><span class="th-sub">5% Brokerage Assumed</span></th>'
               '<th>Conventional, 5% Down, Assumed</th></tr></thead><tbody>'
               '<tr><td>Listing Brokerage (2.5%, Assumed)</td><td class="n">$9,612</td></tr>'
               "<tr><td>Owner's Title Insurance (Estimate)</td><td>$2,100</td></tr>"
               '<tr><td>Homeowners Insurance (Estimate: Get a Quote)</td><td>$300</td></tr>'
               '<tr><td>Approval</td><td>Pre-approval letter (assumed)</td></tr>'
               '<tr><td>Inspection Period</td><td>7 days (AS IS, form assumed)</td></tr>'
               '<tr><td>Holding Costs Until Closing (Est.)</td><td>$1,200</td></tr></tbody></table>'
               '<div class="sp-stat"><b>$425,888</b><span>Estimated Net at $479,900 (Assumed Brokerage)</span></div>'
               '<div class="divrow factrow"><div><span>Condo (Assumed)</span></div></div>')
        found = [t for _, t in sc.estimate_label_errors(bad)]
        for text in ("Listing Brokerage (2.5%, Assumed)", "Owner's Title Insurance (Estimate)",
                     "Homeowners Insurance (Estimate: Get a Quote)", "Pre-approval letter (assumed)",
                     "7 days (AS IS, form assumed)", "Holding Costs Until Closing (Est.)", "Condo (Assumed)",
                     "Conventional, 5% Down, Assumed", "Estimated Net at $479,900 (Assumed Brokerage)"):
            self.assertIn(text, found)
        self.assertTrue(any("Brokerage Assumed" in t for t in found))
        good = ('<table><thead><tr><th>Estimated Net*</th><th>Est. Monthly Payment</th></tr></thead><tbody>'
                '<tr><td>Listing Brokerage (2.5%)</td><td>$9,612</td></tr>'
                '<tr><td>Med</td><td>Down payment not provided: assumed 0% for VA</td></tr></tbody></table>'
                '<p class="note">Assumed: this year\'s tax bill is still unpaid at closing. Estimates, not local figures: '
                'transfer tax 1%.</p><div class="sp-stat"><b>$425,888</b><span>Estimated Net at $479,900</span></div>')
        self.assertEqual(sc.estimate_label_errors(good), [])


if __name__ == "__main__":
    unittest.main()
