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
    """The prototype's cost assumptions: 3% listing fee (when not given) and a flat $645 title settlement."""
    d = copy.deepcopy(data)
    d["listing"]["costs"] = {"title_fees": 645}
    d.setdefault("seller", {}).setdefault("listing_fee_pct", 0.03)
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
            "B": (145677, 142677, 148476, 86, 82, "ACCEPT"),
            "C": (134560, 131560, 153320, 100, 98, "BACKUP"),
            "A": (142901, 130105, 145813, 54, 66, "DECLINE"),
            "D": (154293, 134126, 146150, 42, 62, "DECLINE"),
        })
        self.assertEqual([o["id"] for o in R["ranked"]], ["B", "C", "A", "D"])
        self.assertEqual(R["mode"], "multi")

    def test_minimal_single(self):
        R = oe.analyze(prototype_costs(fixture("minimal-single.json")))
        o = R["offers"][0]
        self.assertEqual((o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"]), (348407, 345907, 352139))
        self.assertEqual((o["score"]["total"], o["action"]), (66, "COUNTER"))
        self.assertEqual([r[0] for r in o["counter_rows"]], ["Price", "Inspection Period"])
        self.assertEqual(R["seller"]["holding_monthly"], 1050)

    def test_two_offers_accept(self):
        R = oe.analyze(prototype_costs(fixture("two-offers-accept.json")))
        b = by_id(R)["B"]
        self.assertEqual((b["ns"]["net_adj"], b["ns_down"]["net_adj"], b["ns_counter"]["net_adj"]), (169691, 166191, 171567))
        self.assertEqual((b["score"]["total"], b["counter_score"], b["action"]), (88, 84, "ACCEPT"))
        self.assertEqual(by_id(R)["C"]["action"], "DECLINE")


class FloridaMarketDefaults(unittest.TestCase):
    def test_brokerage_and_itemized_title_fees(self):
        R = oe.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "listing"), -9550)       # 2.5% of 382,000
        self.assertEqual(line(o["ns"], "settle"), -1145)        # 700 + 250 + 125 + 70
        self.assertEqual(line(o["ns"], "transfer"), -2674)      # 0.70%
        self.assertEqual(o["ns"]["net_adj"], 349817)
        fee = next(a for a in R["assumptions"] if a["field"] == "listing_fee_pct")
        self.assertEqual((fee["impact"], fee["value"]), ("high", 0.025))
        self.assertIn("Florida default", fee["why"])
        self.assertEqual(R["listing"]["state"], "FL")  # read from the address

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
    def test_nothing_filled_from_florida(self):
        R = oe.analyze(fixture("texas-single.json"))
        o = R["offers"][0]
        for key in ("transfer", "title", "settle"):
            self.assertEqual(line(o["ns"], key), 0, key)
        self.assertEqual(o["repair_reserve"], 0)
        fields = {a["field"]: a["impact"] for a in R["assumptions"]}
        self.assertEqual(fields["deed transfer tax"], "high")
        self.assertIn("title company fees", fields)
        self.assertIn("inspection_credit_reserve_pct", fields)
        self.assertTrue(any("transfer tax" in n for n in oe.preliminary_inputs(R)))
        text = json.dumps(R["assumptions"]) + json.dumps(R["listing"]["cost_notes"])
        self.assertNotIn("Florida", text)
        self.assertEqual(o["contract_form"], "other")  # no FR/BAR form (or its math) outside Florida
        self.assertTrue(o["inspection_walkaway"])

    def test_market_profile_fills_the_gaps(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tx.md")
            with open(path, "w") as f:
                f.write("---\nprofile: market\nstate: TX\nclosing_costs:\n  deed_transfer_tax_rate: 0\n"
                        "  owner_title: {payer: seller, estimate_pct: 0.0055}\n  seller_title_fees: {escrow_fee: 650}\n"
                        "contract:\n  inspection_credit_reserve_pct: 0.005\n---\n")
            R = oe.analyze(fixture("texas-single.json"), market=path)
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "title"), -round(598000 * 0.0055))
        self.assertEqual(line(o["ns"], "settle"), -650)
        self.assertEqual(o["repair_reserve"], 3000)
        self.assertIn("your market profile", " ".join(R["listing"]["cost_notes"]))


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

    def test_fallback_counter_for_low_down_buyer(self):
        R = oe.analyze(fixture("four-offers.json"))
        a = by_id(R)["A"]  # FHA 3.5%, over the value range, no gap
        self.assertIn("fallback_terms", a)
        self.assertEqual(a["fallback_terms"]["appraisal_gap"], 0)

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
        self.assertEqual(o["ns"]["net_adj"], 349817)
        label = next(lab for k, lab, _ in o["ns"]["lines"] if k == "transfer")
        self.assertTrue(label.startswith("Documentary Stamp Tax"))


if __name__ == "__main__":
    unittest.main()
