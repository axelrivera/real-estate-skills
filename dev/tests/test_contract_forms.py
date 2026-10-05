"""Contract form routing: FAR/BAR AS IS and Standard rules never mix (shared/contract_forms.py and its users)."""
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
        for v, want in (("AS IS", "as_is"), ("ASIS-7", "as_is"), ("Standard", "standard"), ("CRSP", "other"),
                        ("CRSP-17", "other"), ("Residential Contract for Sale and Purchase", "standard"),
                        ("Vacant Land Contract", "other"), ("", None)):
            self.assertEqual(cf.normalize(v), want, v)
        for v, want in (("FAR/BAR AS IS", "as_is"), ("farbar standard", "standard"), ("FAR/BAR Standard Contract", "standard"),
                        ("FR/BAR AS IS", "as_is"), ("FRBAR Standard", "standard"), ("FR/BAR Standard Contract", "standard")):  # legacy
            self.assertEqual(cf.normalize(v), want, v)
        with self.assertRaises(cf.FormError):
            cf.normalize("FR/BAR contract")  # legacy name, form not named
        self.assertTrue(cf.farbar_market(["FAR/BAR AS IS"]) and cf.farbar_market(["FR/BAR AS IS"]))  # legacy market file
        self.assertFalse(cf.farbar_market(["CRSP-17"]))

    def test_walkaway(self):
        self.assertTrue(cf.inspection_walkaway("as_is"))
        self.assertFalse(cf.inspection_walkaway("standard", {"inspection_walkaway": True}))  # the form decides
        self.assertIsNone(cf.inspection_walkaway("other"))  # another contract must say; the caller asks or assumes
        self.assertTrue(cf.inspection_walkaway("other", {"inspection_walkaway": True}))
        self.assertFalse(cf.inspection_walkaway("other", {"inspection_walkaway": False}))

    def test_rider_codes(self):
        names = ["K", "Rider L", "CR-7 AA", "E. FHA/VA Financing", "Homeowners'/Flood Ins", "Appraisal Gap Addendum",
                 "PACE Disclosure", "Qualifying Improvements Disclosure", "Sellers Agreement with Respect to Buyers Broker "
                 "Compensation", "Credit Related to Buyers Broker Compensation", "Private road maintenance", "Condominium"]
        self.assertEqual(cf.rider_codes(names), (["K", "L", "AA", "E", "H", "EE", "GG", "FF", "A"],
                                                 ["Appraisal Gap Addendum", "Private road maintenance"]))
        self.assertEqual(len(cf.RIDERS), 33)
        # hyphenated and possessive-less names map; "Condominium Association" is Rider A, not B
        names = ["Short-Sale Rider", "Shortsale", "Seller Attorney Approval", "Buyers Attorney Approval",
                 "Pre-Closing Occupancy", "Kick-Out Clause", "Lead-Based Paint", "Interest-Bearing Account",
                 "Seller’s Agreement with Respect to Buyer’s Broker Compensation"]
        self.assertEqual(cf.rider_codes(names)[0], ["G", "Y", "Z", "T", "X", "P", "J", "GG"])
        self.assertEqual(cf.rider_code("Condominium Association"), "A")
        self.assertEqual(cf.rider_code("Condo Association Rider"), "A")
        self.assertEqual(cf.rider_code("Homeowners' Association/Community Disclosure"), "B")

    def test_inspection_riders_on_standard(self):
        """Rider K turns the Standard form into AS IS math; Rider L adds a walk-away and keeps the repairs."""
        for form, riders, want in (("standard", [], (False, True, None)), ("standard", ["As Is Rider"], (True, False, "K")),
                                   ("standard", ["Right to Inspect/ Cancel"], (True, True, "L")), ("as_is", [], (True, False, None))):
            t = cf.terms(form, {"riders": riders})
            self.assertEqual((t["walkaway"], t["repairs_owed"], t["inspection_rider"]), want, (form, riders))

    def test_reserved_riders_on_as_is(self):
        for r in ("I", "K", "L"):
            with self.assertRaisesRegex(cf.FormError, "RESERVED"):
                cf.terms("as_is", {"riders": [r]})
        with self.assertRaisesRegex(cf.FormError, "which one governs"):
            cf.terms("standard", {"riders": ["K", "L"]})

    def test_revision_note(self):
        self.assertIsNone(cf.revision_note("as_is", "FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26"))
        self.assertIsNone(cf.revision_note("standard", "FloridaRealtors/FloridaBar – 7x Rev. 2/26"))
        self.assertIsNone(cf.revision_note("other", "TREC 20-19"))
        self.assertIsNone(cf.revision_note("as_is", None))
        self.assertIsNotNone(cf.revision_note("as_is", "ASIS-8 Rev. 1/27"))
        self.assertIsNotNone(cf.revision_note("standard", "FloridaRealtors/FloridaBar-7x Rev. 10/24"))
        # a revision that didn't come from the footer is worded differently from one read off it
        self.assertNotEqual(cf.revision_note("as_is", "Rev. 6/24", False), cf.revision_note("as_is", "Rev. 6/24"))
        self.assertEqual(cf.support(["as_is"], [("as_is", "Rev. 6/24", False)])["chat_notes"],
                         [cf.revision_note("as_is", "Rev. 6/24", False)])
        # OFR-314: an offer still being written gets the buyer-side line, never "the signed contract"
        self.assertEqual(cf.support([cf.OTHER], drafting=True)["chat_notes"], [cf.BEST_EFFORT_OFFER_NOTE])
        self.assertEqual(cf.support([cf.OTHER])["chat_notes"], [cf.BEST_EFFORT_NOTE])
        self.assertEqual(cf.support(["as_is"], drafting=True)["chat_notes"], [])

    def test_repair_limits(self):
        self.assertEqual(cf.repair_limits(400000), {"general": 6000, "wdo": 6000, "permit": 6000})
        self.assertEqual(cf.repair_limits(400000, {"repair_limits": {"general": 0.02, "wdo": 2500}}),
                         {"general": 8000, "wdo": 2500, "permit": 6000})
        with self.assertRaises(cf.FormError):
            cf.repair_limits(400000, {"repair_limits": {"general": "lots"}})

    def test_term_words(self):  # OFR-234: FAR/BAR's names on FAR/BAR only; generic words on anything else
        for form in cf.FARBAR:
            self.assertEqual(cf.term_words(form)["inspection_label"], "Inspection Period")
            self.assertIsNone(cf.term_words(form)["appraisal_addendum"])
        for form in (cf.OTHER, None):
            w = cf.term_words(form)
            self.assertNotEqual(w["inspection_label"], "Inspection Period")
            self.assertTrue(w["appraisal_addendum"])


class AppraisalForm(unittest.TestCase):
    """Rider F vs. the Appraisal Gap Addendum (AGA-1): each offer is scored on its own form's window."""

    def test_detection_and_windows(self):
        self.assertEqual(cf.appraisal_form("as_is", {"riders": ["Appraisal Gap Addendum (AGA-1)"]}), "aga")
        self.assertEqual(cf.appraisal_form("standard", {"appraisal_form": "AGA-1"}), "aga")
        self.assertEqual(cf.appraisal_form("as_is", {"riders": ["F"]}), "F")
        self.assertEqual(cf.appraisal_form("as_is", {"riders": ["FHA/VA Financing"]}), "E")
        self.assertIsNone(cf.appraisal_form("other", {"riders": ["Appraisal Gap Addendum"]}))
        self.assertEqual(cf.appraisal_window("aga", 60), 36)  # 30 + 3 + 3
        self.assertEqual(cf.appraisal_window("aga", 60, {"aga_valuation_days": 20, "aga_renegotiate_days": 5}), 28)
        self.assertEqual(cf.appraisal_window("F", 60), 53)  # 10 days before closing + 3

    def two(self, close_days=60):
        d = fixture("seller-offer-review", "two-offers-accept.json")
        base = dict(d["offers"][0], financing="conventional", down_pct=0.2, appraisal_gap=10000, closing_days=close_days,
                    contract_form="as_is")
        base.pop("closing_date", None)
        base.pop("appraisal_contingency", None)
        d["offers"] = [dict(base, id="A", appraisal_form="aga"), dict(base, id="B", riders=["F"])]
        R = oe.analyze(d)
        return R, {o["id"]: o for o in R["offers"]}

    def test_aga_window_against_rider_f(self):
        """AGA-1 ends the appraisal risk sooner than Rider F on a long close; on a short one it makes little difference."""
        R, o = self.two(60)
        self.assertEqual((o["A"]["appraisal_days"], o["B"]["appraisal_days"]), (36, 53))
        self.assertLess(o["A"]["risk_days"], o["B"]["risk_days"])
        self.assertGreaterEqual(o["A"]["score"]["total"], o["B"]["score"]["total"])
        self.assertEqual(R["ranked"][0]["id"], "A")  # same price and gap: the shorter window ranks first
        _, o = self.two(40)
        self.assertEqual((o["A"]["appraisal_days"], o["B"]["appraisal_days"]), (36, 33))

    def test_cash_offer_with_aga_carries_appraisal_risk(self):
        _, o = offer("as_is", financing="cash", down_pct=1, appraisal_form="aga", appraisal_gap=5000)
        self.assertTrue(o["appraisal_risk"])
        self.assertEqual((o["appraisal_days"], o["gap_cover"]), (36, 5000))

    def test_aga_with_rider_f_or_fha_is_flagged(self):
        _, o = offer("as_is", riders=["F", "Appraisal Gap Addendum"], appraisal_gap=5000, financing="conventional", down_pct=0.2)
        self.assertIn("aga_with_rider_F", [f["topic"] for f in o["flags"]])
        _, o = offer("as_is", riders=["E", "AGA-1"], appraisal_gap=5000, financing="fha", down_pct=0.035)
        self.assertIn("aga_loan_type", [f["topic"] for f in o["flags"]])


class RiderWindowsAndPay(unittest.TestCase):
    """Rider cancel windows count toward "days until firm"; a kick-out raises a sale contingency; FF uses the cap."""

    def test_insurance_rider_window_counts(self):
        _, plain = offer("as_is", inspection_days=7, loan_approval_days=21, appraisal_contingency=21, closing_days=45)
        _, ins = offer("as_is", inspection_days=7, loan_approval_days=21, appraisal_contingency=21, closing_days=45, riders=["H"])
        self.assertEqual(ins["risk_days"], min(30, ins["close_days"] - 10))  # the earlier of 30 days or 10 before closing
        self.assertGreater(ins["risk_days"], plain["risk_days"])
        self.assertLessEqual(ins["score"]["total"], plain["score"]["total"])

    def test_rider_windows(self):
        """Rider cancel windows from contract_forms; a rider without its date is a recorded assumption."""
        w, missing = cf.rider_windows("standard", {"riders": ["I", "M", "GG", "Z", "R"]}, 45)
        self.assertEqual({c: d for c, d, _ in w}, {"I": 20, "M": 15, "GG": 6})
        self.assertEqual(missing, ["Z", "R"])
        self.assertEqual(cf.rider_windows("as_is", {"riders": ["Z"], "attorney_days": 5})[0], [("Z", 5, "buyer's attorney approval")])
        self.assertEqual(cf.rider_windows("other", {"riders": ["H"]}), ([], []))
        R, _ = offer("as_is", riders=["Z"])
        self.assertTrue(any(a["field"] == "rider_Z" for a in R["assumptions"]))

    def test_kickout_raises_a_sale_contingency(self):
        _, bare = offer("as_is", sale_contingency_days=30)
        _, kick = offer("as_is", sale_contingency_days=30, riders=["V", "X"])
        self.assertEqual((bare["score"]["scores"]["contingency"], kick["score"]["scores"]["contingency"]), (1, 2))

    def test_ff_credit_counts_toward_the_cap(self):
        # FHA cap 6% of $400,000 = $24,000: $16,000 of concessions fits alone, not with a $10,000 credit
        kw = dict(financing="fha", down_pct=0.035, seller_concessions=16000, buyer_broker_pct=0.025, price=400000)
        _, gg = offer("as_is", riders=["E", "GG"], **kw)
        _, ff = offer("as_is", riders=["E", "FF"], **kw)
        self.assertNotIn("concessions_cap", [f["topic"] for f in gg["flags"]])
        self.assertIn("concessions_cap", [f["topic"] for f in ff["flags"]])  # the credit is what puts it over


class SellerEngine(unittest.TestCase):
    def test_as_is_uses_the_inspection_credit_only(self):
        _, o = offer("as_is")
        self.assertTrue(o["inspection_walkaway"])
        self.assertEqual(o["risk_days"], max(o["inspection_days"], o["loan_approval_days"], o["appraisal_days"]))
        self.assertIn("repair", [k for k, _, _ in o["ns_down"]["lines"]])
        self.assertNotIn("repair_limits", o)

    def test_standard_uses_the_repair_limits_only(self):
        _, o = offer("standard")
        self.assertFalse(o["inspection_walkaway"])
        self.assertEqual(o["repair_limits"]["general"], round(0.015 * o["price"]))
        self.assertEqual({k: v for k, _, v in o["ns_down"]["lines"]}["repair"], -round(0.015 * o["price"]))
        self.assertEqual(o["risk_days"], max(o["inspection_days"] + 15, o["loan_approval_days"], o["appraisal_days"]))

    def test_same_offer_differs_only_by_form_rules(self):
        _, a = offer("as_is", inspection_days=10)
        _, s = offer("standard", inspection_days=10)
        self.assertEqual(a["ns"]["net"], s["ns"]["net"])  # as offered: same price and terms
        self.assertNotEqual(a["ns_down"]["net"], s["ns_down"]["net"])  # downside: each form's own repair rule

    def test_inspection_riders_on_standard(self):
        """Rider K runs AS IS math on the Standard form; Rider L walks away and still owes the repairs."""
        _, o = offer("standard", riders=["K"])
        self.assertTrue(o["inspection_walkaway"])
        self.assertFalse(o["repairs_owed"])
        self.assertNotIn("repair_limits", o)
        self.assertEqual(o["risk_days"], max(o["inspection_days"], o["loan_approval_days"], o["appraisal_days"]))
        _, as_is = offer("as_is")
        self.assertEqual({k: v for k, _, v in o["ns_down"]["lines"]}["repair"],
                         {k: v for k, _, v in as_is["ns_down"]["lines"]}["repair"])  # AS IS's repair credit, not the limits
        _, o = offer("standard", riders=["L"])
        self.assertTrue(o["inspection_walkaway"])
        self.assertTrue(o["repairs_owed"])
        self.assertEqual(o["risk_days"], max(o["inspection_days"] + 15, o["loan_approval_days"], o["appraisal_days"]))

    def test_reserved_rider_on_as_is_stops_the_review(self):
        with self.assertRaisesRegex(oe.OfferError, "RESERVED"):
            offer("as_is", riders=["K"])

    def test_rider_money_lines(self):
        _, o = offer("as_is", riders=["U", "C"], rent_back_days=15, rent_back_monthly=3000, seller_financing=50000)
        lines = {k: v for k, _, v in o["ns"]["lines"]}
        self.assertEqual(lines["rentback"], -1500)
        self.assertEqual(lines["note"], -50000)
        self.assertEqual([k for k, _, _ in o["ns"]["lines"]], [k for k, _, _ in o["ns_down"]["lines"]])

    def test_rider_f_default_runs_to_closing_minus_seven(self):
        _, o = offer("as_is", riders=["Appraisal Contingency"], appraisal_contingency=None)
        self.assertEqual(o["appraisal_days"], o["close_days"] - 7)

    def test_rider_flags(self):
        _, o = offer("as_is", riders=["G", "Z", "V", "GG"], sale_contingency_days=30)
        text = " ".join(f["issue"] for f in o["flags"])
        for code in ("G", "Z", "V", "GG"):  # each rider is flagged by its letter
            self.assertRegex(text, rf"Rider {code}\b")

    def test_other_contract_in_florida(self):
        """Another contract in Florida: an unstated walk-away is a high-impact assumption, and no AS IS repair reserve."""
        R, o = offer("Builder Purchase Agreement")
        self.assertTrue(o["inspection_walkaway"])
        self.assertTrue(any(a["field"] == "inspection_walkaway" and a["impact"] == "high" for a in R["assumptions"]))
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
        self.assertIn("Standard", strategy.worksheet(r)["form_name"])

    def test_gap_option_is_scored_on_aga(self):
        d = fixture("buyer-offer-strategy", "fha-competitive.json")
        d["buyer"].update(financing="conventional", down_pct=0.2)
        d["overrides"] = {"appraisal_gap": 10000}
        r = strategy.analyze(d)
        o = r["O"]["recommended"]
        self.assertEqual(o["appraisal_form"], "aga")
        # OFR-106: the valuation blank is filled so AGA-1's periods end with the 21-day loan approval (15 + 3 + 3)
        self.assertEqual(o["appraisal_days"], 21)
        self.assertEqual(o["aga_valuation_days"], 15)

    def test_needs_sale_is_scored_with_a_kickout(self):
        d = fixture("buyer-offer-strategy", "fha-competitive.json")
        d["buyer"]["needs_sale"] = True
        r = strategy.analyze(d)
        o = r["O"]["recommended"]
        self.assertEqual((o["sale_contingency_days"], o["kickout"]), (21, True))
        self.assertEqual(o["score"]["scores"]["contingency"], 2)
        self.assertTrue(any(a["field"] == "sale_contingency_days" for a in r["missing"]))

    def test_ff_route_leaves_less_room_for_concessions(self):
        d = fixture("buyer-offer-strategy", "fha-competitive.json")
        gg = strategy.analyze(copy.deepcopy(d))
        d.setdefault("worksheet", {})["buyer_broker_form"] = "FF"
        ff = strategy.analyze(d)
        price = ff["terms"]["recommended"]["price"]
        self.assertLess(strategy.concession_cap(ff["B"], price), strategy.concession_cap(gg["B"], price))
        riders = [x["rider"] for x in strategy.worksheet(ff)["riders"]]
        self.assertIn("Credit Related to Buyer's Broker Compensation Rider (FF)", riders)

    def test_default_is_as_is_and_says_so(self):
        r = strategy.analyze(fixture("buyer-offer-strategy", "fha-competitive.json"))
        self.assertTrue(all(o["contract_form"] == "as_is" for o in r["O"].values()))
        self.assertTrue(any(a["field"] == "contract_form" for a in r["missing"]))
        self.assertNotIn("Standard", strategy.worksheet(r)["form_name"])


class Timeline(unittest.TestCase):
    def test_farbar_needs_its_form(self):
        deal = fixture("contract-timeline", "buyer-fha.json")
        del deal["contract"]["contract_form"]
        with self.assertRaisesRegex(timeline.DealError, "as_is or standard"):
            timeline.analyze(deal)

    def test_legacy_form_family_still_reads(self):
        deal = fixture("contract-timeline", "buyer-fha.json")
        want = timeline.analyze(copy.deepcopy(deal))["rows"]
        deal["contract"]["form_family"] = "frbar"  # legacy deal file from 0.12
        self.assertEqual(timeline.analyze(deal)["rows"], want)

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
