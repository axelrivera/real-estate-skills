"""Tests for shared/offer_engine.py (used by seller-offer-review and buyer-offer-strategy)."""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
from shared import finance, handoff, offer_engine as oe, profiles  # noqa: E402

FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def prototype_costs(data):
    """The prototype's cost assumptions: 3% listing fee and 2.5% buyer-broker pay offered (when not given) and a flat
    $645 title settlement. Nothing about brokerage is built in any more (CORE-5), so the test states it."""
    d = copy.deepcopy(data)
    d["listing"]["costs"] = {"title_fees": 645}
    d.setdefault("seller", {}).setdefault("listing_fee_pct", 0.03)
    d["seller"].setdefault("offered_buyer_broker_pct", 0.025)
    return d


def line(sheet, key):
    return next(v for k, _, v in sheet["lines"] if k == key)


def by_id(R):
    return {o["id"]: o for o in R["offers"]}


class MatchesPrototype(unittest.TestCase):
    """Given the prototype's own cost assumptions, every number matches its sample reports."""

    def test_four_offers(self):
        R = oe.analyze(prototype_costs(fixture("four-offers.json")))
        got = {o["id"]: (o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"], o["score"]["total"],
                         o["counter_score"], o["action"]) for o in R["ranked"]}
        self.assertEqual(got, {
            # The prototype countered B; this seller wants certainty, so a strong offer isn't risked for a 0.7% gain.
            "B": (145851, 142851, 148650, 86, 82, "ACCEPT"),
            "C": (134729, 131729, 153489, 100, 98, "BACKUP"),
            # Audit 2026-09-23: the downside is measured from the CMA high (OFR-4), and A's FHA appraisal protection runs
            # to closing, so its counter asks for no gap coverage it couldn't enforce (OFR-3, OFR-17).
            # The tax proration allows Florida's 4% early-payment discount (FR/BAR Standard K; OFR-14).
            "A": (143084, 136352, 145996, 55, 63, "DECLINE"),
            "D": (154485, 140349, 146337, 42, 62, "DECLINE"),
        })
        self.assertEqual([o["id"] for o in R["ranked"]], ["B", "C", "A", "D"])
        self.assertEqual(R["mode"], "multi")

    def test_minimal_single(self):
        R = oe.analyze(prototype_costs(fixture("minimal-single.json")))
        o = R["offers"][0]
        # Audit: 4% early-payment discount in the proration (OFR-14) and no tax in holding costs (OFR-13)
        self.assertEqual((o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"]), (349279, 346779, 353011))
        self.assertEqual((o["score"]["total"], o["action"]), (63, "COUNTER"))  # FHA: appraisal protected to closing
        self.assertEqual([r[0] for r in o["counter_rows"]], ["Price", "Inspection Period"])
        self.assertEqual(R["seller"]["holding_monthly"], 500)  # HOA and loan interest; tax is in the proration (OFR-13)

    def test_two_offers_accept(self):
        R = oe.analyze(prototype_costs(fixture("two-offers-accept.json")))
        b = by_id(R)["B"]
        self.assertEqual((b["ns"]["net_adj"], b["ns_down"]["net_adj"], b["ns_counter"]["net_adj"]), (170598, 167098, 172474))
        self.assertEqual((b["score"]["total"], b["counter_score"], b["action"]), (88, 84, "ACCEPT"))
        self.assertEqual(by_id(R)["C"]["action"], "DECLINE")


class FloridaMarketDefaults(unittest.TestCase):
    def test_brokerage_assumed_at_five_percent_total(self):
        """No terms given: 2.5% listing and 2.5% buyer's agent, labeled assumed, not a Preliminary blocker."""
        R = oe.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "listing"), -round(o["price"] * 0.025))
        self.assertEqual(line(o["ns"], "bb"), -round(o["price"] * 0.025))
        fee = next(a for a in R["assumptions"] if a["field"] == "listing_fee_pct")
        self.assertEqual((fee["impact"], fee["value"]), ("med", 0.025))
        self.assertNotIn("listing fee", oe.preliminary_inputs(R))

    def test_itemized_title_fees_and_stated_brokerage(self):
        d = fixture("minimal-single.json")
        d["seller"] = {"listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.02}
        o = oe.analyze(d)["offers"][0]
        self.assertEqual(line(o["ns"], "listing"), -9550)       # 2.5% of 382,000
        self.assertEqual(line(o["ns"], "bb"), -7640)            # the seller's 2% offer, assumed for this offer
        self.assertIn("Assumed", next(lab for k, lab, _ in o["ns"]["lines"] if k == "bb"))
        self.assertEqual(line(o["ns"], "settle"), -1145)        # 700 + 250 + 125 + 70
        self.assertEqual(line(o["ns"], "transfer"), -2674)      # 0.70%
        self.assertEqual(oe.analyze(d)["listing"]["state"], "FL")  # read from the address

    def test_deal_quote_and_county_override(self):
        d = fixture("minimal-single.json")
        d["listing"]["costs"] = {"title_fees": 900}
        o = oe.analyze(d)["offers"][0]
        self.assertEqual(line(o["ns"], "settle"), -900)
        d = fixture("minimal-single.json")
        d["listing"].update(address="1 Main St, Miami, FL 33130", county="Miami-Dade")
        o = oe.analyze(d)["offers"][0]
        self.assertEqual(line(o["ns"], "title"), 0)             # buyer pays the owner's policy there
        self.assertEqual(line(o["ns"], "transfer"), -round(382000 * 0.006))

    def test_unknown_state_assumes_florida_and_says_so(self):
        d = fixture("minimal-single.json")
        d["listing"]["address"] = "1207 Palmetto Way"
        R = oe.analyze(d)
        a = next(a for a in R["assumptions"] if a["field"] == "state")
        self.assertEqual(a["impact"], "high")
        self.assertIn("property state", oe.preliminary_inputs(R))


class OtherStates(unittest.TestCase):
    def test_national_estimates_not_florida(self):
        R = oe.analyze(fixture("texas-single.json"))
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "transfer"), -round(598000 * 0.004))  # national estimate, not Florida's 0.7%
        self.assertEqual(line(o["ns"], "title"), -round(598000 * 0.005))
        self.assertEqual(line(o["ns"], "settle"), -1200)
        self.assertEqual(o["repair_reserve"], 0)
        fields = {a["field"]: a["impact"] for a in R["assumptions"]}
        self.assertEqual(fields["transfer_tax_rate"], "med")  # labeled Estimate, not a Preliminary blocker
        self.assertIn("title_fees", fields)
        self.assertIn("inspection_credit_reserve_pct", fields)
        self.assertFalse(any("transfer tax" in n for n in oe.preliminary_inputs(R)))
        text = json.dumps(R["assumptions"]) + json.dumps(R["listing"]["cost_notes"])
        self.assertNotIn("Florida", text)
        self.assertEqual(o["contract_form"], "other")  # no FR/BAR form (or its math) outside Florida
        self.assertTrue(o["inspection_walkaway"])

    def test_listing_costs_replace_the_estimates(self):
        """The skill's looked-up transfer tax and a title quote go in the listing's costs and win."""
        data = fixture("texas-single.json")
        data["listing"].setdefault("costs", {}).update(
            {"transfer_tax_rate": 0, "title_estimate_pct": 0.0055, "title_fees": {"escrow_fee": 650},
             "inspection_credit_reserve_pct": 0.005})
        R = oe.analyze(data)
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "transfer"), 0)
        self.assertEqual(line(o["ns"], "title"), -round(598000 * 0.0055))
        self.assertEqual(line(o["ns"], "settle"), -650)
        self.assertEqual(o["repair_reserve"], 3000)
        self.assertIn("this listing", " ".join(R["listing"]["cost_notes"]))
        self.assertFalse(any("national estimate" in a["why"] and a["field"] != "listing_fee_pct" and "broker" not in a["field"]
                             for a in R["assumptions"]))


class Handoff(unittest.TestCase):
    def test_cma_range_and_midpoint(self):
        h = handoff.build(side="seller", as_of="2026-09-20", subject={"address": "1207 Palmetto Way, Winter Springs, FL 32708",
                          "beds": 3, "sqft": 1650}, value={"low": 380000, "high": 398000, "midpoint": 390000}, comps=[])
        R = oe.analyze(fixture("minimal-single.json"), cma=h)
        L = R["listing"]
        self.assertTrue(L["cma_provided"])
        self.assertEqual((L["cma_low"], L["cma_high"], L["cma_mid"], L["beds"]), (380000, 398000, 390000, 3))
        self.assertNotIn("cma_low / cma_high", [a["field"] for a in R["assumptions"]])

    def test_listing_file_wins_over_handoff(self):
        d = fixture("two-offers-accept.json")
        h = handoff.build(side="seller", as_of="2026-09-20", subject={}, value={"low": 1, "high": 2, "midpoint": 1.5}, comps=[])
        self.assertEqual(oe.analyze(d, cma=h)["listing"]["cma_low"], 500000)


class Rules(unittest.TestCase):
    def test_agent_overrides(self):
        d = fixture("minimal-single.json")
        d["offers"][0]["scores"] = {"agent": {"score": 5, "why": "Closed 3 deals with them"}}
        d["offers"][0]["recommendation"] = "accept"
        o = oe.analyze(d)["offers"][0]
        self.assertEqual((o["score"]["scores"]["agent"], o["score"]["src"]["agent"]), (5, "agent"))
        self.assertEqual(o["action"], "ACCEPT")

    def test_counter_never_asks_fha_va_for_gap_money(self):
        """OFR-3, OFR-17: an FHA/VA gap clause doesn't bind the buyer; a price over the range is countered to its top."""
        fha = by_id(oe.analyze(fixture("four-offers.json")))["A"]
        self.assertFalse(any(r[0] == "Appraisal Gap Coverage" for r in fha["counter_rows"]))
        self.assertEqual(fha["counter_terms"]["price"], 428000)

    def test_percent_written_as_whole_number_is_refused(self):
        data = fixture("minimal-single.json")
        data["seller"] = {**(data.get("seller") or {}), "listing_fee_pct": 3}
        with self.assertRaisesRegex(oe.OfferError, "seller.listing_fee_pct is 3: write it as a fraction, 0.03"):
            oe.analyze(data)

    def test_state_from_address_without_zip(self):
        self.assertEqual(oe.state_of({"address": "1207 Palmetto Way, Winter Springs, FL"}), "FL")
        self.assertEqual(oe.state_of({"address": "8104 Shoal Creek Blvd, Austin, TX 78757"}), "TX")
        self.assertIsNone(oe.state_of({"address": "12 Main St"}))

    def test_no_transfer_tax_reads_as_none(self):
        class M:
            state, notes = "TX", []

            def get(self, path, default=None):
                return {"closing_costs.deed_transfer_tax_rate": 0}.get(path, default)

            def source(self, path):
                return "profile"
        notes = oe.cost_notes(oe.Costs(M()), {"title_customary_payer": None})
        self.assertTrue(notes[0].startswith("No deed transfer tax"))

    def test_required_inputs(self):
        with self.assertRaises(oe.OfferError):
            oe.analyze({"listing": {}, "offers": [{"price": 1}]})
        with self.assertRaises(oe.OfferError):
            oe.analyze({"listing": {"list_price": 300000}, "offers": [{"id": "A"}]})

    def test_net_sheet_uses_finance_lines(self):
        """The engine reads finance.seller_net's keyed lines and keeps the market's own name for the transfer tax."""
        o = oe.analyze(fixture("minimal-single.json"))["offers"][0]
        label = next(lab for k, lab, _ in o["ns"]["lines"] if k == "transfer")
        self.assertTrue(label.startswith("Documentary Stamp Tax"))



class CondoAndFlood(unittest.TestCase):
    """CMA-5 (condo rider, FHA/VA project approval, rescission) and CMA-6 (seller flood disclosure, s. 689.302)."""

    def flags(self, R, oid):
        return [x["issue"] for x in by_id(R)[oid]["flags"]]

    def test_broward_condo(self):
        R = oe.analyze(fixture("broward-condo.json"))
        a, b = self.flags(R, "A"), self.flags(R, "B")
        self.assertIn("The property is a condo but no condo rider is attached.", a)
        self.assertIn("FHA loan on a condo: the project must be FHA-approved.", a)
        self.assertFalse(any("no condo rider" in x for x in b))  # B attached the rider
        self.assertFalse(any("-approved" in x for x in b))
        for issues in (a, b):
            self.assertTrue(any(x.startswith("Condo: the buyer may cancel within 7 days") for x in issues))
            self.assertTrue(any("flood disclosure (s. 689.302)" in x for x in issues))
        req = [x.get("request") for x in by_id(R)["A"]["flags"] if "FHA-approved" in x["issue"]]
        self.assertTrue(req and "FHA approval" in req[0])

    def test_disclosure_given(self):
        d = fixture("broward-condo.json")
        d["listing"]["flood_disclosure"] = True
        R = oe.analyze(d)
        self.assertFalse(any("flood disclosure" in x for x in self.flags(R, "A")))

    def test_not_florida(self):
        R = oe.analyze(fixture("texas-single.json"))
        text = json.dumps([o["flags"] for o in R["offers"]])
        self.assertNotIn("689.302", text)
        self.assertNotIn("718.503", text)


class AuditSellerSideLimits(unittest.TestCase):
    """OFR-12 (concessions over the program cap), OFR-18 (a planned quote isn't scored)."""

    def test_concessions_over_the_cap(self):
        d = fixture("two-offers-accept.json")
        o = d["offers"][0]
        o.update(financing="conventional", down_pct=0.05, seller_concessions=25600)  # 5% of $512,000; the cap is 3%
        R = oe.analyze(d)
        flags = [x["issue"] for x in by_id(R)["B"]["flags"]]
        self.assertTrue(any("exceed the Conventional limit of 3% at 5% down" in x for x in flags), flags)

    def test_planned_quote_not_scored(self):
        d = fixture("two-offers-accept.json")
        d["offers"][0]["insurance_quote"] = "planned"
        planned = by_id(oe.analyze(d))["B"]["score"]["scores"]["property"]
        d["offers"][0]["insurance_quote"] = True
        in_hand = by_id(oe.analyze(d))["B"]["score"]["scores"]["property"]
        self.assertEqual(in_hand - planned, 1)


class AuditReviewBenchmarks(unittest.TestCase):
    """OFR-15 (market offer norms, the same in review and counter), OFR-24 (handoff side and nulls)."""

    def test_norms_from_market_or_national(self):
        R = oe.analyze(fixture("two-offers-accept.json"))
        self.assertEqual(R["listing"]["norms"], {"deposit_pct": 0.03, "concessions_pct": 0.015, "inspection_days": 7,
                                                 "loan_approval_days": 21})
        T = oe.analyze(fixture("texas-single.json"))
        self.assertEqual(T["listing"]["norms_source"], "national")
        self.assertTrue(any(a["field"] == "offer_norms" for a in T["assumptions"]))
        o = T["offers"][0]
        weak_deposit = o["deposit"] is not None and o["deposit"] / o["price"] < T["listing"]["norms"]["deposit_pct"]
        self.assertEqual(weak_deposit, any(r[0] == "Escrow Deposit" for r in o["counter_rows"]))

    def test_handoff_side_and_nulls(self):
        d = fixture("two-offers-accept.json")
        d["listing"]["cma_low"] = None
        h = {"kind": "cma", "version": 1, "side": "buyer", "source": "buyer-cma",
             "value": {"low": 495000, "high": 520000, "midpoint": 507500}}
        R = oe.analyze(d, cma=h)
        self.assertEqual(R["listing"]["cma_low"], 495000)  # an explicit null is filled
        self.assertEqual(R["listing"]["cma_high"], 525000)  # the file's own value wins
        self.assertTrue(any("from the buyer side" in a["why"] for a in R["assumptions"]))

if __name__ == "__main__":
    unittest.main()


class AuditAppraisalAndEscalation(unittest.TestCase):
    """Audit 2026-09-23: OFR-2, OFR-3, OFR-4, OFR-17."""

    def test_escalation_ranks_on_effective_price(self):
        """OFR-2: A ($400k, +$1k to $425k) reaches $406k over B's flat $405k and ranks first."""
        R = oe.analyze(fixture("escalation.json"))
        a, b = by_id(R)["A"], by_id(R)["B"]
        self.assertEqual((a["price_base"], a["price"], a["escalated"]), (400000, 406000, True))
        self.assertEqual(a["escalation_note"], "Escalates to $406,000 from $400,000 (cap $425,000)")
        self.assertEqual(R["ranked"][0]["id"], "A")
        self.assertGreater(a["ns"]["net_adj"], b["ns"]["net_adj"])

    def test_escalation_terms_are_checked(self):
        data = fixture("escalation.json")
        data["offers"][0]["escalation"] = {"increment": 1000}
        issues = [f["issue"] for f in by_id(oe.analyze(data))["A"]["flags"]]
        self.assertTrue(any("no cap" in i for i in issues))
        self.assertTrue(any("doesn't say how a competing offer is proven" in i for i in issues))

    def test_fha_waiver_is_ignored(self):
        """OFR-3, OFR-17: an FHA appraisal waiver and gap clause don't bind the buyer."""
        R = oe.analyze(fixture("escalation.json"))
        c = by_id(R)["C"]
        self.assertTrue(c["appraisal_protected"])
        self.assertEqual((c["gap_cover"], c["appraisal_days"]), (0, c["close_days"]))
        self.assertNotEqual(c["score"]["why"]["appraisal"], "No appraisal contingency")
        self.assertTrue(any("intent only" in f["issue"] for f in c["flags"]))
        self.assertTrue(any(a["field"] == "appraisal_contingency" for a in R["assumptions"]))

    def test_financed_waiver_counts_only_documented_funds(self):
        data = fixture("escalation.json")
        b = data["offers"][1]
        b.update(price=420000, appraisal_contingency=False, appraisal_gap=0)
        o = by_id(oe.analyze(data))["B"]
        self.assertTrue(o["appraisal_waived"])
        self.assertEqual(o["downside_price"], 410000)  # no documented funds: covered only to the CMA high
        self.assertLess(o["score"]["scores"]["appraisal"], 5)
        b["gap_funds"] = 10000
        self.assertEqual(by_id(oe.analyze(data))["B"]["downside_price"], 420000)

    def test_price_above_midpoint_isnt_penalized(self):
        """OFR-4: $405k nets more than $400k inside a $390k-$410k range and ranks above it."""
        data = fixture("escalation.json")
        data["offers"] = [dict(data["offers"][1], id="A", price=400000), dict(data["offers"][1], id="B")]
        R = oe.analyze(data)
        self.assertEqual([o["id"] for o in R["ranked"]], ["B", "A"])
        self.assertEqual(by_id(R)["B"]["downside_price"], 405000)
