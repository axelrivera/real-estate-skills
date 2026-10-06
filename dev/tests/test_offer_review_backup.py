"""Backup offers and highest and best: a backup that lapses before the counter, the backup's own terms, a call for
highest and best (none, pending, passed) and the wait-for-final-offers plan.

Case: two offers on 2604 Sable Palm Way (listing-pays-buyer-broker.json): A (AGA-1, its time for acceptance ends Wed
Sep 23 5:00 PM, the backup) and B (escalation, ranked first and countered, expires Thu Sep 24 5:00 PM), with highest
and best due Wed Sep 23 12:00 PM.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render = load("seller-offer-review", "review", "render")

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")
BACKUP_LABEL = "Backup: Ask to Extend"


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def case05(a=None, b=None, listing=None):
    d = fixture("listing-pays-buyer-broker.json")
    d["offers"][0].update(a or {})
    d["offers"][1].update(b or {})
    d["listing"].update(listing or {})
    return d


NO_CALL = {"highest_and_best_due": None}
PASSED = {"highest_and_best_due": "2026-09-21 12:00"}


def box_order(v):
    """The Respond By box's deadlines in printed order, as datetimes (the review's year is 2026)."""
    from datetime import datetime
    whens = [v["respond_by"]] + [x["when"] for x in v["respond_by_also"]]
    return [datetime.strptime(f"{w} 2026", "%a %b %d, %I:%M %p %Y") for w in whens]


def page(R, oid):
    """A single review's HTML, from the one document model (review.result)."""
    return render.build_html(review.result(R, "single", oid), {})


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def views(d):
    """(R, multi view, single view of A, single view of B)."""
    R = review.analyze(d)
    return R, review.multi_view(R), review.single_view(R, offer(R, "A")), review.single_view(R, offer(R, "B"))


def options(v):
    return [o["option"] for o in v["options"]]


class BackupLapses(unittest.TestCase):
    def test_backup_that_ends_before_the_counter_is_flagged_and_planned(self):
        R, m, a, b = views(case05(listing=NO_CALL))
        self.assertEqual(m["ranked"][0]["offer"], offer(R, "B")["label"])
        self.assertIn("backup_lapses", [f.get("topic") for f in offer(R, "A")["flags"]])
        self.assertIsNotNone(offer(R, "A").get("lapses_before"))
        self.assertIn("backup_lapses", m["plan_keys"])
        also = {x["key"]: x for x in m["respond_by_also"]}
        self.assertEqual(also["backup_lapses"]["when"], "Wed Sep 23, 5:00 PM")
        labels = {x["what"] for v in (m, b) for x in v["respond_by_also"] if x["key"] == "backup_lapses"}
        self.assertEqual(labels | {a["respond_by_offer"]}, {BACKUP_LABEL})  # one label for the backup's deadline

    def test_backup_that_outlasts_the_counter_is_not(self):
        R, m, _, _ = views(case05(a={"expires": "2026-09-28 17:00"}, listing=NO_CALL))
        self.assertNotIn("backup_lapses", [f.get("topic") for f in offer(R, "A")["flags"]])
        self.assertNotIn("backup_lapses", m["plan_keys"])
        self.assertEqual(m["respond_by_also"], [])

    def test_backup_keeps_its_own_price(self):
        R = review.analyze(fixture("four-offers.json"))
        backup = next(o for o in R["ranked"] if o["action"] == "BACKUP")
        row = next(r for r in review.multi_view(R)["ranked"] if r["key"] == backup["key"])
        self.assertNotEqual(backup["counter_terms"]["price"], backup["price"])  # a counter would ask for more
        self.assertNotIn("$", row["terms"])  # held as written: no counter price on its row


class HighestAndBest(unittest.TestCase):
    def test_no_call_out_offers_one(self):
        self.assertIn("Call for Highest & Best", options(views(case05(listing=NO_CALL))[1]))

    def test_passed_call_is_the_normal_plan(self):
        R, m, _, b = views(case05(listing=PASSED))
        self.assertNotIn("Call for Highest & Best", options(m))
        self.assertIn("highest_and_best_done", m["plan_keys"])
        self.assertNotIn("highest_and_best", [x["key"] for x in m["respond_by_also"]])
        self.assertEqual((m["headline"], b["headline"], m["wait"]), ("COUNTER", "COUNTER", None))
        self.assertEqual(m["ranked"][0]["action"], "Counter")
        self.assertTrue(m["options"][0]["recommended"])
        self.assertIn("OUR COUNTER", page(R, "B"))


class WaitForFinalOffers(unittest.TestCase):
    """Highest and best pending: wait for the final offers, then decide; the counter is the fallback."""

    @classmethod
    def setUpClass(cls):
        cls.R, cls.m, cls.a, cls.b = views(case05())

    def test_comparison_plan_is_to_wait(self):
        m = self.m
        self.assertEqual((m["headline"], m["title"]), (review.WAIT_HEADLINE, review.WAIT_TITLE))
        self.assertEqual(m["wait"]["due"], "Wed Sep 23, 12:00 PM")
        self.assertIn("$504,000", m["wait"]["fallback"])
        self.assertEqual(m["ranked"][0]["action"], "Wait")
        self.assertIn("highest_and_best_pending", m["plan_keys"])
        self.assertEqual((m["options"][0]["option"], m["options"][0]["recommended"]), ("Wait for Final Offers", True))
        self.assertEqual([o["recommended"] for o in m["options"][1:]], [False] * (len(m["options"]) - 1))
        self.assertNotIn("Call for Highest & Best", options(m))

    def test_respond_by_is_the_call(self):
        m = self.m
        self.assertEqual((m["respond_by"], m["respond_by_offer"]), ("Wed Sep 23, 12:00 PM", "Highest & Best Due"))
        self.assertEqual({(x["when"], x["what"]) for x in m["respond_by_also"]},
                         {("Thu Sep 24, 5:00 PM", "Ostrander Offer Expires"), ("Wed Sep 23, 5:00 PM", BACKUP_LABEL)})

    def test_respond_by_box_reads_in_time_order(self):
        # iteration 14 eval 8: every report's box, the comparison and each single review, earliest first
        for v in (self.m, self.a, self.b):
            self.assertEqual(box_order(v), sorted(box_order(v)), v["offer"])

    def test_single_review_of_the_lead_offer(self):
        b = self.b
        self.assertEqual((b["headline"], b["respond_by_offer"]), (review.WAIT_HEADLINE, "Highest & Best Due"))
        self.assertEqual(b["options"][0]["option"], "Wait for Final Offers")
        self.assertFalse(next(o for o in b["options"] if o["option"] == "Counter")["recommended"])
        self.assertEqual(b["counter"]["rows"][0]["counter"], "$504,000")  # the fallback's terms are all there
        html = page(self.R, "B")
        self.assertIn("FALLBACK COUNTER", html)
        self.assertNotIn("OUR COUNTER", html)

    def test_backup_review_keeps_its_plan(self):
        self.assertEqual((self.a["headline"], self.a["wait"]), ("HOLD AS BACKUP", None))
        # its own deadline stays in the box under the comparison's label; the earlier call for final offers leads
        self.assertIn(BACKUP_LABEL, [self.a["respond_by_offer"]] + [x["what"] for x in self.a["respond_by_also"]])


if __name__ == "__main__":
    unittest.main()
