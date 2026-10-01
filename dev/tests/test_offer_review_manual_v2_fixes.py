"""Fixes from the owner's second manual run of seller-offer-review (case 5, OFR-339 to OFR-345).

The same two offers as test_offer_review_manual_fixes.py: A (AGA-1, its time for acceptance ends first, closes Nov 2)
and B (escalation, ranked first and countered, closes Oct 28), both with the listing broker paying the buyer's broker.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402
from test_offer_review_manual_fixes import data, multi, offer  # noqa: E402

review, render = load("seller-offer-review", "review", "render")


def line(ns, key):
    return next((v for k, _, v in ns["lines"] if k == key), 0)


class ReportTarget(unittest.TestCase):  # OFR-339
    def test_given_listing_fee_target_matches_the_single_reviews(self):
        d = data()
        d["seller"]["listing_fee_pct"] = 0.05
        R = review.analyze(d)
        self.assertEqual(line(R["target"], "bb"), 0)
        a = offer(R, "A")  # the latest closing, the report target's date
        self.assertEqual(R["target"]["net_adj"], a["target"]["net_adj"])
        for o in R["active"]:  # both offers sit below the target, as every single review says
            self.assertLess(o["ns"]["net_adj"], R["target"]["net_adj"])

    def test_assumed_listing_fee_target_unchanged(self):
        R = review.analyze(data())
        self.assertEqual(R["target"]["net_adj"], offer(R, "A")["target"]["net_adj"])

    def test_buyer_broker_line_stays_when_not_every_offer_has_the_listing_broker_pay(self):
        d = data(B={"buyer_broker_paid_by": None, "buyer_broker_pct": 0.025})
        d["seller"]["listing_fee_pct"] = 0.025
        R = review.analyze(d)
        self.assertLess(line(R["target"], "bb"), 0)


class BackupLapsesWithHighestAndBest(unittest.TestCase):  # OFR-342
    def flag(self, d):
        R = review.analyze(d)
        return next(f for f in offer(R, "A")["flags"] if f.get("topic") == "backup_lapses")

    def test_pending_highest_and_best_drops_answer_first(self):
        f = self.flag(data({"highest_and_best_due": "2026-09-23 12:00"}))
        self.assertNotIn("answer this offer first", f["fix"])

    def test_without_highest_and_best_both_paths_stay(self):
        self.assertIn("answer this offer first", self.flag(data())["fix"])


class HoaConflict(unittest.TestCase):  # OFR-343
    def test_every_offer_flagged_and_chip_not_stating_the_figure(self):
        R = review.analyze(data({"hoa_conflict": "$95 per quarter in one package, $95 per month in the other"}))
        for o in R["active"]:
            self.assertIn("hoa_conflict", [f.get("topic") for f in o["flags"]])
            self.assertNotIn("hoa_conflict", [f.get("topic") for f in review.deal_flags(o)])  # never a top risk
        chips = render.snapshot(R)
        self.assertIn("HOA to Confirm", chips)
        self.assertNotIn("HOA $95", chips)

    def test_no_conflict_no_flag(self):
        R = review.analyze(data())
        self.assertFalse(any(f.get("topic") == "hoa_conflict" for o in R["active"] for f in o["flags"]))
        self.assertIn("HOA $95/mo", render.snapshot(R))


class TaxBillAssumptionPerOffer(unittest.TestCase):  # OFR-344
    def test_only_on_reviews_of_offers_closing_in_november(self):
        R = review.analyze(data())
        a = next(x for x in R["missing"] if x["field"] == "current_tax_bill_paid")
        self.assertEqual(a["offers"], ["A"])
        fields = lambda oid: [x["field"] for x in review.listed_assumptions(R, False, oid)]  # noqa: E731
        self.assertIn("current_tax_bill_paid", fields("A"))
        self.assertNotIn("current_tax_bill_paid", fields("B"))
        self.assertIn("current_tax_bill_paid", [x["field"] for x in review.listed_assumptions(R, True)])


class TopOfferNextStepOrder(unittest.TestCase):  # OFR-344
    def test_extension_ask_comes_before_the_counter(self):
        R = review.analyze(data())
        nxt = review.single_view(R, offer(R, "B"))["next_step"]
        self.assertIn("extend past", nxt)
        self.assertLess(nxt.index("extend past"), nxt.index("send the counter"))


if __name__ == "__main__":
    unittest.main()
