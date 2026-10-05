"""Seller net sheet fixes from manual round 5 (case 9), replayed from the kit's inputs."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

compute, render, shared_render = load("seller-net-sheet", "compute", "render", "_shared.render")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-net-sheet")


def case9():
    with open(os.path.join(FIXTURES, "florida-credit-manual-v5.json")) as f:
        return json.load(f)


class TypicalCharges(unittest.TestCase):
    """Built-in statewide fees are the state's typical charges, never the county's."""

    def test_florida_fees_name_the_state(self):
        C = compute.run(case9())
        text = " ".join(C["notes"] + C["assumptions"] + C["chat_notes"])
        self.assertIn("typical Florida charges", text)
        self.assertNotIn("Seminole charges", text)
        self.assertNotIn("typical local charges", text)

    def test_no_state_stays_local(self):
        d = case9()
        d["property"] = {"address": "1 Sample St"}
        C = compute.run(d)
        self.assertNotIn("typical Florida", " ".join(C["notes"] + C["assumptions"]))


class BalancePayoff(unittest.TestCase):
    """A stated payoff is used as given; a balance gets a month's interest at the loan's rate, else 4.5%."""

    def payoff(self, costs):
        d = case9()
        d["costs"] = {k: v for k, v in d["costs"].items() if k != "mortgage_payoff"} | costs
        C = compute.run(d)
        return -next(r for r in C["rows"] if r.get("key") == "payoff" or "Mortgage Payoff" in r["label"])["amounts"][0]

    def test_stated_payoff_as_given(self):
        self.assertEqual(self.payoff({"mortgage_payoff": 188000}), 188000)

    def test_balance_default_rate(self):
        self.assertEqual(self.payoff({"mortgage_balance": 188000}), round(188000 * (1 + 4.5 / 1200)))

    def test_balance_loan_rate(self):
        self.assertEqual(self.payoff({"mortgage_balance": 188000, "mortgage_rate": 6}), round(188000 * 1.005))


class ChartLabels(unittest.TestCase):
    """The chart's price labels fit on one line ("At $425,000 with $6,000 Credit" wrapped in round 5)."""

    def test_labels_one_line(self):
        C = compute.run(case9())
        self.assertIn("At $425,000 with $6,000 Credit", [c["label"] for c in C["columns"]])  # the labels case 9 wrote
        doc = render.build_html(C, {})
        seen = {}

        def measure(pg):
            seen["heights"] = pg.evaluate("() => [...document.querySelectorAll('.bars .lbl')].map(e => e.getBoundingClientRect().height)")
            return render.fit_one_page(pg)

        with tempfile.TemporaryDirectory() as tmp:
            height, no_chart, clipped = shared_render.html_to_pdf(doc, os.path.join(tmp, "x.pdf"), before_print=measure)
        self.assertFalse(no_chart)
        self.assertEqual(clipped, [])
        hs = seen["heights"]
        self.assertEqual(len(hs), 3)
        self.assertLess(max(hs) - min(hs), 2, hs)  # every label one line high, the long one included

    def test_group_labels_are_title_case_in_source(self):
        """BROKERAGE and the other group rows are uppercase only in CSS; the source is Title Case (style-check reads it)."""
        C = compute.run(case9())
        groups = [r["label"] for r in C["rows"] if r["kind"] == "group"]
        self.assertTrue(groups)
        for g in groups:
            self.assertNotEqual(g, g.upper(), g)
        with open(os.path.join(ROOT, "dev", "style_check.py")) as f:
            self.assertIn('"group"', f.read())


if __name__ == "__main__":
    unittest.main()
