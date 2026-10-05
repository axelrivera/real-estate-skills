"""Contract timeline fixes from manual round 5 (cases 6 to 8), replayed from the kit's inputs."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

timeline, timeline_render = load("contract-timeline", "timeline", "render")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        deal = json.load(f)
    deal.setdefault("report_date", "2026-09-26")
    return deal


def rows(t):
    return {r["key"]: r for r in t["rows"] + t["pending"]}


def short_sale_case7():
    """Case 7: the short sale package, deposit and Rider GG's agreement done Sep 23, occupancy not recorded."""
    d = fixture("short-sale.json")
    d["completed"] = {"deposit": "2026-09-23", "compensation_agreement": "2026-09-23"}
    return d


class OtherContractLegend(unittest.TestCase):
    """Case 8 (Ohio): the star legend states no FAR/BAR consequence for another contract."""

    def setUp(self):
        self.t = timeline.analyze(fixture("ohio-manual-v5.json"))

    def test_legend_has_no_deposit_consequence(self):
        self.assertNotIn("deposit", self.t["critical_legend"])
        html = timeline_render.build_html(self.t, {}, True)
        self.assertNotIn("put the deposit at risk", html)
        self.assertIn("a deadline the contract makes time-sensitive", html)

    def test_farbar_keeps_its_legend(self):
        t = timeline.analyze(fixture("buyer-fha.json"))
        self.assertIn("put the deposit at risk", t["critical_legend"])
        self.assertIn("put the deposit at risk", timeline_render.build_html(t, {}, True))

    def test_page_one_table_is_key_dates(self):
        html = timeline_render.build_html(self.t, {}, True)
        self.assertIn("<h2>Key Dates <span", html)
        self.assertNotIn("All Key Dates", html)


class PartyWords(unittest.TestCase):
    """Case 8: a party named inside a sentence of the deal file's text reads "the buyer" / "the seller"."""

    def test_rows_from_the_deal_file(self):
        r = rows(timeline.analyze(fixture("ohio-manual-v5.json")))
        self.assertEqual(r["earnest_money"]["if_missed"], "Seller may terminate the agreement by written notice to the buyer")
        self.assertTrue(r["financing"]["action"].startswith("Deliver the written loan commitment to the seller,"))
        self.assertEqual(r["title_commitment"]["action"],
                         "Olentangy Crossing Title Agency provides the title commitment to the buyer")

    def test_names_that_run_on_and_sentence_starts_are_kept(self):
        self.assertEqual(timeline.party_words("Deliver the Seller's Disclosure to the Buyer"),
                         "Deliver the Seller's Disclosure to the buyer")
        self.assertEqual(timeline.party_words("Buyer accepts the property"), "Buyer accepts the property")
        self.assertEqual(timeline.party_words("Buyer in default; Seller may cancel"), "Buyer in default; the seller may cancel")
        self.assertEqual(timeline.party_words("Notify the Buyer's lender"), "Notify the buyer's lender")


class RuleText(unittest.TestCase):
    """Case 6 (FHA): each rule and weekend note reads one way, once."""

    def setUp(self):
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = ["FHA/VA Financing", "Homeowners'/Flood Insurance"]
        self.r = rows(timeline.analyze(d))

    def test_trid_count_named_once(self):
        cd = next(r for r in self.r.values() if "Closing Disclosure" in r["label"])
        text = cd["rule"] + " " + (cd["note"] or "")
        self.assertEqual(text.count("TRID business days"), 1)
        self.assertIn("Saturdays count", cd["rule"])

    def test_one_weekend_phrasing(self):
        notes = [r["note"] for r in self.r.values() if r.get("note") and "extended" in r["note"]]
        self.assertTrue(notes)
        for n in notes:
            self.assertIn("falls on", n)
            self.assertNotIn("ends on", n)
        survey = self.r["survey"]["note"]  # counted back from closing: same words as one counted forward
        loan = self.r["loan_approval"]["note"]
        self.assertEqual(survey, "falls on a Sunday: extended to the end of Mon Oct 26")
        self.assertEqual(loan, survey)


class ShortSaleNotes(unittest.TestCase):
    """Case 7: only questions whose answer changes a date; the Rider U 6(b) note while occupancy isn't recorded."""

    def test_gg_reading_not_asked_once_the_agreement_is_signed(self):
        t = timeline.analyze(short_sale_case7())
        self.assertNotIn("short_sale_gg", t["note_keys"])
        open_gg = fixture("short-sale.json")
        self.assertIn("short_sale_gg", timeline.analyze(open_gg)["note_keys"])

    def test_rider_u_6b_note_without_occupancy(self):
        t = timeline.analyze(short_sale_case7())
        self.assertIn("rider_u_6b", t["note_keys"])
        d = short_sale_case7()
        d["contract"]["occupancy"] = "tenant"
        self.assertIn("rider_u_6b", timeline.analyze(d)["note_keys"])

    def test_compensation_agreement_is_both(self):
        r = rows(timeline.analyze(short_sale_case7()))
        self.assertEqual(r["compensation_agreement"]["party"], "Both")


class CalendarLenderLine(unittest.TestCase):
    """Case 6: the reply says which lender targets the calendar leaves out, unless --lender-dates adds them."""

    def test_line_names_the_left_out_targets(self):
        t = timeline.analyze(fixture("buyer-fha.json"))
        left = timeline_render.calendar_lender_rows(t)
        self.assertTrue(left)
        line = timeline_render.lender_calendar_note(left)
        self.assertIn("Homeowner's Insurance Bound (Fri Oct 23)", line)
        self.assertNotIn("(Lender Target)", line)
        self.assertEqual(timeline_render.calendar_lender_rows(t, lender_dates=True), [])

    def test_ics_run_prints_it(self):
        deal = fixture("buyer-fha.json")
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            timeline_render.build(copy.deepcopy(deal), "ics", tmp, {"agent": {}, "formats": ["ics"]})
        self.assertIn("The calendar leaves out the lender's targets", err.getvalue())
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            timeline_render.build(copy.deepcopy(deal), "ics", tmp, {"agent": {}, "formats": ["ics"], "lender_dates": True})
        self.assertNotIn("leaves out the lender's targets", err.getvalue())


if __name__ == "__main__":
    unittest.main()
