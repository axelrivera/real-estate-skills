"""Fixes from the owner's manual smoke test of seller-offer-review (case 5, OFR-319 to OFR-326).

Two offers on one listing, as in the kit: A (an AGA-1 offer whose time for acceptance ends first) and B (an
escalation offer, ranked first and countered). The tests assert keys and structure, not sentences.
"""
import copy
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render, oe = load("seller-offer-review", "review", "render", "_shared.offer_engine")

OFFER = {"status": "active", "contract_form": "as_is", "financing": "conventional", "approval": "preapproval",
         "deposit": 20000, "seller_concessions": 0, "title_by": "seller", "inspection_days": 10, "loan_approval_days": 30,
         "riders": ["B", "GG"], "buyer_broker_paid_by": "listing_broker", "buyer_broker_form": "GG",
         "lender": "Harborline Home Lending"}
BASE = {
    "analysis_date": "2026-09-22",
    "listing": {"address": "2604 Sable Palm Way, Jupiter, FL 33458", "state": "FL", "county": "Palm Beach",
                "list_price": 504000, "year_built": 2016, "property_type": "single_family", "flood_disclosure": True,
                "hoa_monthly": 95},
    "seller": {"name": "Logan Prescott"},
    "offers": [
        dict(OFFER, id="A", expires="2026-09-23 17:00", buyer_agent="Kendall Castellanos",
             buyer_brokerage="Sunward Homes Realty", price=489000, down_pct=0.2, loan_amount=391200,
             balance_to_close=77800, closing_date="2026-11-02", addenda=["Appraisal Gap Addendum (AGA-1)"],
             appraisal_form="aga", appraisal_gap=15000, approval_max_price=489000, approval_max_loan=391200),
        dict(OFFER, id="B", expires="2026-09-24 17:00", buyer_agent="Emery Ostrander",
             buyer_brokerage="Tidewater Key Realty", price=494000, down_pct=0.1, loan_amount=444600,
             balance_to_close=29400, closing_date="2026-10-28", addenda=["Escalation Addendum to Contract (EAC-1)"],
             escalation={"cap": 506000, "increment": 2000, "proof": True}, approval_max_price=494000,
             approval_max_loan=444600),
    ],
}


def data(listing=None, **offers):
    d = copy.deepcopy(BASE)
    d["listing"].update(listing or {})
    for o in d["offers"]:
        o.update(offers.get(o["id"]) or {})
    return d


def multi(d):
    R = review.analyze(d)
    return R, review.result(R, "multi")


def offer(R, k):
    return next(o for o in R["offers"] if o["id"] == k)


class BackupLapses(unittest.TestCase):  # OFR-319
    def test_backup_that_ends_before_the_counter_is_flagged_and_planned(self):
        R, out = multi(data())
        s = out["summary"]
        self.assertEqual([r["offer"] for r in s["ranked"]][0], offer(R, "B")["label"])
        a = next(x for x in out["offers"] if x["id"] == "A")
        self.assertIn("backup_lapses", a["flag_keys"])
        self.assertIn("backup_lapses", s["plan_keys"])
        also = {x["key"]: x for x in s["respond_by_also"]}
        self.assertEqual(also["backup_lapses"]["when"], "Wed Sep 23, 5:00 PM")  # the Respond By box's short form
        self.assertIsNotNone(offer(R, "A").get("lapses_before"))
        self.assertIn("Will the buyer extend", " ".join(render.questions(offer(R, "A"), R)))

    def test_backup_that_outlasts_the_counter_is_not(self):
        R, out = multi(data(A={"expires": "2026-09-28 17:00"}))
        self.assertNotIn("backup_lapses", next(x for x in out["offers"] if x["id"] == "A")["flag_keys"])
        self.assertNotIn("backup_lapses", out["summary"]["plan_keys"])
        self.assertEqual(out["summary"]["respond_by_also"], [])


class HighestAndBest(unittest.TestCase):  # OFR-320
    def options(self, out):
        return [o["option"] for o in out["summary"]["options"]]

    def test_no_call_out_offers_one(self):
        _, out = multi(data())
        self.assertIn("Call for Highest & Best", self.options(out))

    def test_pending_call_is_shown_and_not_offered_again(self):
        _, out = multi(data({"highest_and_best_due": "2026-09-23 12:00"}))
        s = out["summary"]
        self.assertNotIn("Call for Highest & Best", self.options(out))
        self.assertIn("highest_and_best_pending", s["plan_keys"])
        self.assertEqual(s["respond_by_also"][0]["key"], "highest_and_best")
        self.assertEqual(s["respond_by_also"][0]["when"], "Wed Sep 23, 12:00 PM")

    def test_passed_call_is_not_a_deadline(self):
        _, out = multi(data({"highest_and_best_due": "2026-09-21 12:00"}))
        s = out["summary"]
        self.assertNotIn("Call for Highest & Best", self.options(out))
        self.assertIn("highest_and_best_done", s["plan_keys"])
        self.assertNotIn("highest_and_best", [x["key"] for x in s["respond_by_also"]])


class PackageDocuments(unittest.TestCase):  # OFR-321
    def test_named_loan_officer_isnt_asked_for(self):
        R = review.analyze(data())
        without = render.questions(offer(R, "B"), R)
        R = review.analyze(data(B={"loan_officer": "Riley Galloway"}))
        named = render.questions(offer(R, "B"), R)
        self.assertEqual(len(without) - len(named), 1)
        self.assertNotIn("Who is the loan officer, so we can verify the approval directly?", named)

    def test_verified_funds_arent_asked_for(self):
        R = review.analyze(data())
        without = render.lender_questions(offer(R, "A"), R)
        R = review.analyze(data(A={"proof_of_funds": 156000}))  # covers the down payment, the counter and the gap
        self.assertTrue(render.funds_shown(offer(R, "A"), 15000))
        self.assertEqual(len(without) - len(render.lender_questions(offer(R, "A"), R)), 1)

    def test_short_funds_are_still_asked_for(self):
        R = review.analyze(data(A={"proof_of_funds": 90000}))
        self.assertFalse(render.funds_shown(offer(R, "A"), 15000))


class CounterTimeForAcceptance(unittest.TestCase):  # OFR-322
    def test_never_the_offers_own_deadline(self):
        R = review.analyze(data())
        b = offer(R, "B")  # expires Thu Sep 24 5:00 PM, the same as the rule's two days
        self.assertEqual(str(oe.acceptance_due(b, R["listing"])), "2026-09-25")
        row = next(r for r in b["counter_rows"] if r[0] == "Time for Acceptance")
        self.assertNotIn("Sep 24", row[2])

    def test_other_deadlines_keep_the_rule(self):
        R = review.analyze(data())
        self.assertEqual(str(oe.acceptance_due(offer(R, "A"), R["listing"])), "2026-09-24")


class Layout(unittest.TestCase):
    def test_snapshot_chips_are_title_case(self):  # OFR-323
        R = review.analyze(data())
        snap = render.snapshot(R)
        self.assertIn("CMA Not Provided", snap)
        self.assertIn("Payoff Not Provided", snap)
        self.assertNotIn("not provided", snap)

    def test_comparison_headings_and_short_options(self):  # OFR-324
        R = review.analyze(data())
        doc, mode, _ = render.build_html(R, {}, mode="multi")
        self.assertEqual(mode, "multi")
        self.assertEqual(doc.count("Key Terms"), 1)
        v = review.multi_view(review.analyze(data()))
        self.assertEqual(v["options"][0]["short"], "Counter B, Hold A as Backup")

    def test_single_review_tables_flow(self):  # OFR-326
        R = review.analyze(data())
        doc, mode, _ = render.build_html(R, {}, mode="single", offer_id="A")
        self.assertEqual(mode, "single")
        self.assertNotIn('<h2 class="pb">', doc)
        self.assertEqual(doc.count('class="tbl split"'), 3)


if __name__ == "__main__":
    unittest.main()
