"""Contract form routing: FR/BAR AS IS and Standard rules never mix (shared/contract_forms.py and its users)."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import contract_forms as cf  # noqa: E402
from skill_import import load  # noqa: E402

review, = load("seller-offer-review", "review")
strategy, = load("buyer-offer-strategy", "strategy")
timeline, = load("contract-timeline", "timeline")
oe = review.oe

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def fixture(skill, name):
    with open(os.path.join(ROOT, "dev", "fixtures", skill, name)) as f:
        return json.load(f)


def offer(form, **extra):
    d = fixture("seller-offer-review", "two-offers-accept.json")
    o = d["offers"][0]
    if form is None:
        o.pop("contract_form", None)
    else:
        o["contract_form"] = form
    o.update(extra)
    d["offers"] = [o]
    R = oe.analyze(d)
    return R, R["offers"][0]


class Module(unittest.TestCase):
    def test_normalize(self):
        for v, want in (("AS IS", "as_is"), ("ASIS-7", "as_is"), ("Standard", "standard"), ("CRSP", "standard"),
                        ("Residential Contract for Sale and Purchase", "standard"), ("TREC 20-19", "other"), ("", None)):
            self.assertEqual(cf.normalize(v), want, v)

    def test_walkaway(self):
        self.assertTrue(cf.inspection_walkaway("as_is"))
        self.assertFalse(cf.inspection_walkaway("standard", {"inspection_walkaway": True}))  # the form decides
        self.assertTrue(cf.inspection_walkaway("other"))  # an option or due-diligence period
        self.assertFalse(cf.inspection_walkaway("other", {"inspection_walkaway": False}))

    def test_repair_limits(self):
        self.assertEqual(cf.repair_limits(400000), {"general": 6000, "wdo": 6000, "permit": 6000})
        self.assertEqual(cf.repair_limits(400000, {"repair_limits": {"general": 0.02, "wdo": 2500}}),
                         {"general": 8000, "wdo": 2500, "permit": 6000})
        with self.assertRaises(cf.FormError):
            cf.repair_limits(400000, {"repair_limits": {"general": "lots"}})


class SellerEngine(unittest.TestCase):
    def test_as_is_uses_the_inspection_credit_only(self):
        _, o = offer("as_is")
        self.assertTrue(o["inspection_walkaway"])
        self.assertEqual(o["risk_days"], max(o["inspection_days"], o["loan_approval_days"], o["appraisal_days"]))
        line = dict((k, (lbl, v)) for k, lbl, v in o["ns_down"]["lines"])["repair"]
        self.assertEqual(line[0], "Post-Inspection Repair Credit (Est.)")
        self.assertNotIn("repair_limits", o)
        self.assertFalse(any("Standard contract" in f["issue"] for f in o["flags"]))

    def test_standard_uses_the_repair_limits_only(self):
        _, o = offer("standard")
        self.assertFalse(o["inspection_walkaway"])
        self.assertEqual(o["repair_limits"]["general"], round(0.015 * o["price"]))
        line = dict((k, (lbl, v)) for k, lbl, v in o["ns_down"]["lines"])["repair"]
        self.assertEqual(line, ("Repairs up to the General Repair Limit (Standard)", -oe.rnd(0.015 * o["price"], 500)))
        self.assertEqual(o["risk_days"], max(o["inspection_days"] + 15, o["loan_approval_days"], o["appraisal_days"]))
        self.assertIn("no walk-away", o["score"]["why"]["contingency"])
        self.assertTrue(any("Standard contract" in f["issue"] for f in o["flags"]))

    def test_same_offer_differs_only_by_form_rules(self):
        _, a = offer("as_is", inspection_days=10)
        _, s = offer("standard", inspection_days=10)
        self.assertEqual(a["ns"]["net"], s["ns"]["net"])  # as offered: same price and terms
        self.assertNotEqual(a["ns_down"]["net"], s["ns_down"]["net"])  # downside: each form's own repair rule

    def test_other_contract_in_florida_gets_no_as_is_reserve(self):
        _, o = offer("Builder Purchase Agreement")
        self.assertEqual(o["contract_form"], "other")
        self.assertEqual(o["repair_reserve"], 0)

    def test_missing_form_in_florida_is_a_high_assumption(self):
        R, o = offer(None)
        self.assertEqual(o["contract_form"], "as_is")
        self.assertTrue(any(a["field"] == "contract_form" and a["impact"] == "high" for a in R["assumptions"]))


class BuyerStrategy(unittest.TestCase):
    def test_worksheet_form_is_the_scored_form(self):
        """The Standard form on the worksheet means Standard math in the options, never AS IS."""
        d = fixture("buyer-offer-strategy", "fha-competitive.json")
        d["worksheet"]["contract_form"] = "standard"
        r = strategy.analyze(d)
        self.assertTrue(all(o["contract_form"] == "standard" for o in r["O"].values()))
        self.assertTrue(all(not o["inspection_walkaway"] for o in r["O"].values()))
        w = strategy.worksheet(r)
        text = json.dumps(w)
        self.assertIn("Repair Limits", text)
        self.assertNotIn("Buyer may cancel for any reason", text)

    def test_default_is_as_is_and_says_so(self):
        r = strategy.analyze(fixture("buyer-offer-strategy", "fha-competitive.json"))
        self.assertTrue(all(o["contract_form"] == "as_is" for o in r["O"].values()))
        self.assertTrue(any(a["field"] == "contract_form" for a in r["missing"]))
        self.assertNotIn("Repair Limits", json.dumps(strategy.worksheet(r)))


class Timeline(unittest.TestCase):
    def test_frbar_needs_its_form(self):
        deal = fixture("contract-timeline", "buyer-fha.json")
        del deal["contract"]["contract_form"]
        with self.assertRaisesRegex(timeline.DealError, "as_is or standard"):
            timeline.analyze(deal)

    def test_rows_follow_the_form(self):
        deal = fixture("contract-timeline", "buyer-fha.json")
        as_is = {r["key"] for r in timeline.analyze(copy.deepcopy(deal))["rows"] + timeline.analyze(copy.deepcopy(deal))["pending"]}
        deal["contract"]["contract_form"] = "Standard"
        r = timeline.analyze(deal)
        std = {x["key"] for x in r["rows"] + r["pending"]}
        self.assertEqual(std - as_is, {"repair_estimates", "repair_election"})
        self.assertFalse(next(x for x in r["rows"] if x["key"] == "inspection")["contingency"])


if __name__ == "__main__":
    unittest.main()
