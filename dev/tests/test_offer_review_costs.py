"""The seller's net: Florida costs and their overrides, other states' estimates, the title box, brokerage when the
listing broker pays the buyer's broker, HOA charges, property tax and the tax bill, rent-back, and the one Seller's
Target per listing."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render, oe = load("seller-offer-review", "review", "render", "_shared.offer_engine")
cf = oe.cf

FIXTURES = os.path.join(os.path.dirname(__file__), "..", "fixtures", "seller-offer-review")

BASE = {"analysis_date": "2026-09-23",
        "listing": {"address": "1 Test St, Longwood, FL 32750", "state": "FL", "county": "Seminole", "list_price": 400000,
                    "cma_low": 390000, "cma_high": 410000, "annual_tax": 5000, "hoa_monthly": 0, "flood_disclosure": True},
        "seller": {"payoff": 200000, "listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.025}}

def page(R, agent=None, sample=False, mode="auto", offer_id=None):
    """The report's HTML, from the one document model (review.result)."""
    return render.build_html(review.result(R, mode, offer_id), agent or {}, sample)



def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def hand(**k):
    o = {"id": "A", "contract_form": "as_is", "price": 400000, "financing": "conventional", "down_pct": 0.2, "deposit": 10000,
         "seller_concessions": 0, "inspection_days": 10, "loan_approval_days": 30, "closing_date": "2026-11-06",
         "title_by": "seller"}
    o.update(k)
    return o


def run(*offers, listing=None, seller=None):
    d = copy.deepcopy(BASE)
    d["offers"] = list(offers)
    d["listing"].update(listing or {})
    d["seller"].update(seller or {})
    return oe.analyze(d)


def first(*offers, **kw):
    return run(*offers, **kw)["offers"][0]


def case05(a=None, b=None, listing=None):
    """Two offers on 2604 Sable Palm Way (A closes Nov 2, B Oct 28), the listing broker paying the buyer's broker."""
    d = fixture("listing-pays-buyer-broker.json")
    d["offers"][0].update(a or {})
    d["offers"][1].update(b or {})
    d["listing"].update(listing or {})
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def line(sheet, key):
    return next((v for k, _, v in sheet["lines"] if k == key), 0)


def label(sheet, key):
    return next((lab for k, lab, v in sheet["lines"] if k == key and v), None)


def fields(R):
    return {a["field"]: a for a in R["assumptions"] if "field" in a}


class FloridaCosts(unittest.TestCase):
    def test_itemized_title_fees_and_stated_brokerage(self):
        d = fixture("minimal-single.json")
        d["seller"] = {"listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.02}
        R = oe.analyze(d)
        o = R["offers"][0]
        self.assertEqual(line(o["ns"], "listing"), -9550)  # 2.5% of 382,000
        self.assertEqual(line(o["ns"], "bb"), -7640)  # the seller's 2% offer, as the agent stated it
        self.assertNotIn("Assumed", label(o["ns"], "bb"))  # a fee the agent stated isn't assumed
        self.assertEqual(fields(R)["buyer_broker_pct"]["impact"], "low")
        self.assertEqual(line(o["ns"], "settle"), -1145)  # 700 + 250 + 125 + 70
        self.assertEqual(line(o["ns"], "transfer"), -2674)  # 0.70%
        self.assertTrue(label(o["ns"], "transfer").startswith("Documentary Stamp Tax"))  # the market's own name
        self.assertEqual(R["listing"]["state"], "FL")  # read from the address

    def test_deal_quote_and_county_override(self):
        d = fixture("minimal-single.json")
        d["listing"]["costs"] = {"title_fees": 900}
        self.assertEqual(line(oe.analyze(d)["offers"][0]["ns"], "settle"), -900)
        d = fixture("minimal-single.json")
        d["listing"].update(address="1 Main St, Miami, FL 33130", county="Miami-Dade")
        o = oe.analyze(d)["offers"][0]
        self.assertEqual(line(o["ns"], "title"), 0)  # the buyer pays the owner's policy there
        self.assertEqual(line(o["ns"], "transfer"), -round(382000 * 0.006))

    def test_title_fee_note_matches_the_net_sheet(self):
        for name in ("four-offers.json", "counter-chain-standard.json", "expired-aga.json"):
            R = review.analyze(fixture(name))
            note = next(n for n in R["listing"]["cost_notes"] if n.startswith("Title company fees"))
            for o in R["active"] + R["incomplete"]:
                self.assertIn(review.money(-line(o["ns"], "settle")), note, name)


class OtherStates(unittest.TestCase):
    def test_national_estimates_not_florida(self):
        R = oe.analyze(fixture("texas-single.json"))
        self.assertFalse(any("transfer tax" in n for n in oe.preliminary_inputs(R)))  # an estimate, not a blocker
        self.assertNotIn("Florida", json.dumps(R["assumptions"]) + json.dumps(R["listing"]["cost_notes"]))

    def test_listing_costs_replace_the_estimates(self):
        data = fixture("texas-single.json")
        data["listing"].setdefault("costs", {}).update(
            {"transfer_tax_rate": 0, "title_estimate_pct": 0.0055, "title_fees": {"escrow_fee": 650},
             "inspection_credit_reserve_pct": 0.005})
        R = oe.analyze(data)
        o = R["offers"][0]
        self.assertEqual((line(o["ns"], "transfer"), line(o["ns"], "title"), line(o["ns"], "settle")),
                         (0, -round(598000 * 0.0055), -650))
        self.assertEqual(o["repair_reserve"], 3000)
        self.assertFalse({"title_estimate_pct", "title_fees", "inspection_credit_reserve_pct"} & set(fields(R)))

    def test_other_contract_keeps_the_agents_reserve(self):
        o = first(hand(contract_form="Texas TREC 20-18", inspection_walkaway=True),
                  listing={"costs": {"inspection_credit_reserve_pct": 0.01}})
        self.assertEqual((o["contract_label"], o["repair_reserve"]), ("Texas TREC 20-18", 4000))


class TitleBox(unittest.TestCase):
    def test_box_decides_the_sellers_searches(self):
        self.assertEqual(cf.title_box(cf.AS_IS, {"title_by": "buyer_regional"}), "iii")
        self.assertEqual(cf.seller_title_searches(cf.AS_IS, {"title_by": "buyer_regional"})["title_search"], 200)
        for title_by, listing, settle in (("seller", None, -1145),
                                          ("buyer", None, -770),  # (ii): no title or lien search for the seller
                                          ("buyer_regional", None, -1095),  # (iii): the title search capped at $200
                                          ("seller", {"address": "1 Test St, Naples, FL 34102", "county": "Collier"}, -1145),
                                          ("seller", {"address": "1 Test St, Miami, FL 33133", "county": "Miami-Dade"}, -1145)):
            with self.subTest(title_by=title_by, county=(listing or {}).get("county")):
                self.assertEqual(line(first(hand(title_by=title_by), listing=listing)["ns"], "settle"), settle)
        o = first(hand(title_by="buyer"))  # the target uses the offer's own title terms
        self.assertEqual(line(o["target"], "title"), 0)
        self.assertEqual(line(o["target"], "settle"), line(o["ns"], "settle"))

    def test_box_sets_who_pays_the_owners_policy(self):
        """Para. 9(c): the box decides, even in Collier; the agent's own number wins."""
        d = fixture("counter-chain-standard.json")
        d["offers"][0]["title_by"] = "buyer"
        self.assertEqual(line(oe.analyze(d)["offers"][0]["ns"], "title"), 0)
        d["offers"][0]["title_by"] = "seller"
        d["listing"]["costs"] = {"title_payer": "buyer"}
        self.assertEqual(line(oe.analyze(d)["offers"][0]["ns"], "title"), 0)


class ListingBrokerPays(unittest.TestCase):
    """The listing broker pays the buyer's broker out of the listing fee: no buyer-broker line, the fee unchanged."""

    def test_assumed_fee_is_the_market_total(self):
        R = run(hand(buyer_broker_pct=0.03, buyer_broker_paid_by="listing_broker"), seller={"listing_fee_pct": None})
        self.assertEqual(line(R["offers"][0]["ns"], "listing"), -20000)  # 5% total, not 2.5% + the 3% ask
        self.assertIn("5%", fields(R)["listing_fee_pct"]["why"])
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        R = review.analyze(data)
        o = R["offers"][0]
        self.assertEqual(line(o["target"], "bb"), 0)  # one total line in every column, the Seller's Target too
        self.assertAlmostEqual(line(o["target"], "listing") / 504000, line(o["ns"], "listing") / 489000, places=4)
        self.assertNotIn("Buyer-Broker Comp.", [r[0] for r in review.term_rows(o, R)])
        self.assertEqual(fields(R)["buyer_broker_paid_by"]["impact"], "med")

    def test_given_listing_fee(self):
        d = fixture("expired-aga.json")
        d["seller"]["listing_fee_pct"] = 0.05  # the listing agreement's total fee
        d["offers"][0]["buyer_broker_pct"] = 0.025
        base = oe.analyze(d)["offers"][0]["ns"]
        d["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        paid = oe.analyze(d)["offers"][0]["ns"]
        self.assertEqual((line(base, "bb"), line(paid, "bb")), (-12225, 0))
        self.assertEqual(line(paid, "listing"), line(base, "listing"))
        self.assertEqual(paid["net"] - base["net"], 12225)
        d["seller"].pop("listing_fee_pct")  # assumed fee: the market's total covers both sides either way
        d["offers"][0].pop("buyer_broker_paid_by")
        before = oe.analyze(d)["offers"][0]["ns"]["net"]
        d["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        self.assertEqual(oe.analyze(d)["offers"][0]["ns"]["net"], before)
        d = fixture("counter-chain-standard.json")
        d["offers"][0].pop("buyer_broker_pct", None)
        d["offers"][0].pop("buyer_broker_amount", None)
        d["offers"][0]["buyer_broker_paid_by"] = "listing_broker"
        self.assertNotIn("buyer_broker_pct", fields(oe.analyze(d)))  # nothing to assume about its share

    def test_listing_fee_includes_the_buyers_agent_when_stated(self):
        data = fixture("texas-single.json")
        data["seller"]["listing_fee_includes_buyer_broker"] = False
        self.assertNotIn("listing_fee_includes_buyer_broker", [a["field"] for a in review.analyze(data)["missing"]])


class SellersTarget(unittest.TestCase):
    """One Seller's Target per listing, on the recommended offer's closing date."""

    def test_one_target(self):
        R = review.analyze(fixture("four-offers.json"))  # title terms may differ by offer; the closing never does
        self.assertEqual({o["target"]["close"] for o in R["offers"]}, {R["target_close"]})
        self.assertIs(R["target"], R["ranked"][0]["target"])
        R = review.analyze(fixture("listing-pays-buyer-broker.json"))
        self.assertIn(oe.money(R["target"]["net_adj"]), page(R, {}, mode="single", offer_id="A"))
        tile = next(k for k in review.single_view(R, offer(R, "A"))["kpis"] if k["label"] == "Seller's Target Net")
        self.assertEqual(tile["value"], review.money(offer(R, "A")["target"]["net_adj"]))

    def test_listing_fee_terms(self):
        """An assumed fee keeps one target; the buyer-broker line stays unless every offer has the listing broker pay."""
        d = case05()
        d["seller"].pop("listing_fee_pct")
        R = review.analyze(d)
        self.assertEqual(R["target"]["net_adj"], offer(R, "A")["target"]["net_adj"])
        d = case05(b={"buyer_broker_paid_by": None, "buyer_broker_pct": 0.025})
        d["seller"]["listing_fee_pct"] = 0.025
        self.assertLess(line(review.analyze(d)["target"], "bb"), 0)


class Hoa(unittest.TestCase):
    def test_estoppel_charge(self):
        def estoppel(d):
            return label(review.analyze(d)["offers"][0]["ns"], "estoppel")
        data = fixture("texas-single.json")
        data["listing"].pop("hoa_monthly")
        self.assertIsNone(estoppel(data))  # an unknown HOA isn't charged "in case"
        data["listing"]["property_type"] = "condo"  # a condo has an association: charged, as an estimate
        self.assertEqual(estoppel(data), "HOA Documents")
        self.assertTrue(review.analyze(data)["offers"][0]["ns"]["estoppel_estimate"])
        self.assertEqual(estoppel(fixture("expired-aga.json")), "HOA Estoppel Letter")  # Florida's built-in fee
        self.assertEqual(label(first(hand(), listing={"hoa_monthly": 120})["ns"], "estoppel"), "HOA Estoppel Letter")
        data = fixture("minimal-single.json")
        data["listing"]["hoa_monthly"] = 0
        self.assertNotIn("hoa_monthly", fields(review.analyze(data)))

    def test_conflicting_hoa_dues(self):
        R = review.analyze(case05())  # the packages disagree: $95 a quarter or a month
        for o in R["active"]:
            self.assertNotIn("hoa_conflict", [f.get("topic") for f in review.deal_flags(o)])  # never a top risk
        self.assertIn("HOA to Confirm", json.dumps(review.fact_row(R), ensure_ascii=False))
        self.assertNotIn("HOA $95", json.dumps(review.fact_row(R), ensure_ascii=False))  # the figure isn't stated
        R = review.analyze(case05(listing={"hoa_conflict": None}))
        self.assertFalse(any(f.get("topic") == "hoa_conflict" for o in R["active"] for f in o["flags"]))
        self.assertIn("HOA $95/mo", json.dumps(review.fact_row(R), ensure_ascii=False))


class PropertyTax(unittest.TestCase):
    def test_annual_tax_from_rate_or_millage(self):
        data = fixture("texas-single.json")
        data["listing"].pop("annual_tax")
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], round(610000 * 0.011))  # national estimate
        data["listing"]["tax_rate"] = 0.02
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], 12200)
        data["listing"].pop("tax_rate")
        data["listing"]["total_mills"] = 20.464
        self.assertEqual(review.analyze(data)["listing"]["annual_tax"], round(610000 * 20.464 / 1000))
        data["listing"]["total_mills"] = 0.020464  # a fraction, not mills
        with self.assertRaises(oe.OfferError):
            review.analyze(data)
        self.assertEqual(fields(run(hand(), listing={"annual_tax": None}))["annual_tax"]["impact"], "med")

    def test_tax_bill_assumed_unpaid_only_after_bills_go_out(self):
        data = fixture("expired-aga.json")  # closes Nov 2
        self.assertIn("current_tax_bill_paid", {a["field"] for a in review.listed_assumptions(review.analyze(data))})
        data["listing"]["current_tax_bill_paid"] = False  # known unpaid: nothing assumed
        self.assertFalse(review.analyze(data)["offers"][0]["ns"]["tax_bill_assumed"])
        data = fixture("expired-aga.json")
        data["offers"][0]["closing_date"] = "2026-10-30"  # before this year's bills go out
        self.assertFalse(review.analyze(data)["offers"][0]["ns"]["tax_bill_assumed"])

    def test_tax_bill_assumption_is_per_offer(self):
        R = review.analyze(case05(listing={"highest_and_best_due": None}))  # A closes Nov 2, B Oct 28
        self.assertEqual(next(x for x in R["missing"] if x["field"] == "current_tax_bill_paid")["offers"], ["A"])

        def listed(oid):
            return [x["field"] for x in review.listed_assumptions(R, False, oid)]
        self.assertIn("current_tax_bill_paid", listed("A"))
        self.assertNotIn("current_tax_bill_paid", listed("B"))
        self.assertIn("current_tax_bill_paid", [x["field"] for x in review.listed_assumptions(R, True)])


class RentBack(unittest.TestCase):
    def test_free_rent_back_is_a_line_not_an_assumption(self):
        R = run(hand(riders=["U"], rent_back_days=14, rent_back_monthly=0))
        self.assertNotIn("rent_back", fields(R))
        self.assertIn("rentback", [k for k, _, _ in R["offers"][0]["ns"]["lines"]])


if __name__ == "__main__":
    unittest.main()
