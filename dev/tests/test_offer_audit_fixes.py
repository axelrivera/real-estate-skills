"""Fixes from the 2026-09-29 audit in the offer engine, contract_forms and the CMA handoff (docs/audits/2026-09-29.md).

Each test names its finding. They assert structured keys (topics, fields, numbers), not sentences.
"""
import copy
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
from shared import contract_forms as cf, handoff, offer_engine as oe  # noqa: E402

BASE = {"analysis_date": "2026-09-23",
        "listing": {"address": "1 Test St, Longwood, FL 32750", "state": "FL", "county": "Seminole", "list_price": 400000,
                    "cma_low": 390000, "cma_high": 410000, "annual_tax": 5000, "hoa_monthly": 0, "flood_disclosure": True},
        "seller": {"payoff": 200000, "listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.025}}


def offer(**k):
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


def line(sheet, key):
    return next((v for k, _, v in sheet["lines"] if k == key), 0)


def fields(R):
    return {a["field"]: a for a in R["assumptions"]}


class Escalation(unittest.TestCase):
    def test_cap_below_price_never_lowers_it(self):  # ENG-1
        R = run(offer(price=405000, escalation={"increment": 2000, "cap": 402000, "proof": "copy"}), offer(id="B", price=404000))
        a = R["offers"][0]
        self.assertEqual((a["price_base"], a["price"], a["escalated"]), (405000, 405000, False))
        self.assertTrue(any("402,000" in i for _, i, _, _ in a["escalation_issues"]))

    def test_same_buyer_variants_dont_escalate_against_each_other(self):  # OFR-101
        esc = {"increment": 1000, "cap": 420000, "proof": "copy"}
        alone = first(offer(price=400000, escalation=esc, same_buyer="b"))
        both = run(offer(price=400000, escalation=esc, same_buyer="b"), offer(id="B", price=405000, same_buyer="b"))
        self.assertEqual(both["offers"][0]["price"], alone["price"])
        self.assertEqual(both["offers"][0]["score"]["total"], alone["score"]["total"])


class NegotiationHistory(unittest.TestCase):
    def test_seller_counter_above_list_is_the_ceiling(self):  # ENG-2
        o = first(offer(price=420000, prior_counters=[{"by": "seller", "price": 405000}]))
        self.assertEqual(o["counter_terms"]["price"], 405000)

    def test_meets_partway_up_to_the_seller_counter(self):  # OFR-107
        o = first(offer(price=402000, prior_counters=[{"by": "seller", "price": 408000}]))
        self.assertEqual(o["counter_terms"]["price"], 405000)

    def test_appraisal_branch_never_below_the_seller_counter(self):  # ENG-2
        o = first(offer(price=420000, prior_counters=[{"by": "seller", "price": 415000}]))
        self.assertEqual(o["counter_terms"]["price"], 415000)
        self.assertEqual(o["counter_terms"]["appraisal_gap"], 5000)

    def test_null_concessions_in_a_counter(self):  # ENG-4
        o = first(offer(seller_concessions=20000, prior_counters=[{"by": "seller", "price": 398000, "seller_concessions": None}]))
        self.assertIn("Seller Concessions", [r[0] for r in o["counter_rows"]])

    def test_closing_date_and_loan_approval_restated(self):  # OFR-108, ENG-16
        o = first(offer(closing_date="2026-11-13", loan_approval_days=30,
                        prior_counters=[{"by": "seller", "closing_date": "2026-11-06", "loan_approval_days": 21}]))
        self.assertIn("closing_date", [g[3] for g in oe.chain_gaps(o)])
        self.assertEqual(str(o["counter_terms"]["close"]), "2026-11-06")
        self.assertEqual(o["counter_terms"]["loan_approval_days"], 21)


class NoCma(unittest.TestCase):
    def test_over_list_keeps_its_price_and_asks_for_gap(self):  # OFR-110
        d = copy.deepcopy(BASE)
        d["listing"].pop("cma_low"), d["listing"].pop("cma_high")
        d["offers"] = [offer(price=410000)]
        o = oe.analyze(d)["offers"][0]
        self.assertEqual(o["counter_terms"]["price"], 410000)
        self.assertEqual(o["counter_terms"]["appraisal_gap"], 10000)
        self.assertNotIn("Price", [r[0] for r in o["counter_rows"]])


class Appraisal(unittest.TestCase):
    def test_cash_with_rider_f_carries_appraisal_risk(self):  # ENG-3
        o = first(offer(financing="cash", riders=["F"], price=415000))
        self.assertTrue(o["appraisal_risk"])
        self.assertEqual(o["appraisal_days"], cf.appraisal_window("F", o["close_days"]))

    def test_usda_gap_on_aga_is_intent_only(self):  # ENG-10
        o = first(offer(financing="usda", down_pct=0, appraisal_form="aga", appraisal_gap=5000, price=415000))
        self.assertNotEqual(o["appraisal_form"], "aga")
        self.assertEqual(o["gap_cover"], 0)
        self.assertIn("aga_loan_type", [f["topic"] for f in o["flags"]])

    def test_aga_rules_live_in_contract_forms(self):  # ENG-15
        self.assertTrue(cf.aga_named({"addenda": ["Appraisal Gap Addendum (AGA-1)"]}))
        self.assertEqual(cf.appraisal_form(cf.AS_IS, {"appraisal_form": "aga"}, "fha"), None)
        self.assertEqual(cf.appraisal_form(cf.AS_IS, {"appraisal_form": "aga"}, "cash"), "aga")
        with open(os.path.join(ROOT, "shared", "offer_engine.py")) as f:
            self.assertNotIn("AGA(-1)?", f.read())  # the name pattern is written once, in contract_forms

    def test_aga_window_stops_at_closing_and_is_flagged(self):  # OFR-106
        o = first(offer(appraisal_form="aga", appraisal_gap=5000, closing_date="2026-10-23", price=415000))
        self.assertEqual(o["appraisal_days"], o["close_days"])
        self.assertEqual(o["aga_window_full"], 36)
        self.assertIn("aga_window_past_closing", [f["topic"] for f in o["flags"]])
        self.assertEqual(cf.aga_valuation_days(21), 15)

    def test_rider_f_and_h_windows_on_a_short_close(self):  # ENG-13, ENG-14
        self.assertEqual(cf.appraisal_window("F", 5), cf.RIDER_F_NOTICE_DAYS)
        self.assertEqual(cf.rider_windows(cf.AS_IS, {"riders": ["H"]}, 5)[0], [("H", 0, "insurance rider")])
        self.assertEqual(cf.rider_windows(cf.AS_IS, {"riders": ["H"]}, 0)[0], [("H", 0, "insurance rider")])

    def test_counter_that_moves_closing_recounts_rider_f(self):  # ENG-14
        o = first(offer(riders=["F"], closing_date="2026-12-18", price=415000),
                  seller={"deadline": "2026-11-20"})
        self.assertEqual(str(o["counter_terms"]["close"]), "2026-11-20")
        self.assertEqual(o["risk_days"], 86 - 10 + 3)  # Dec 18: Rider F's blank date, 10 days before closing, + 3
        self.assertEqual(o["counter_risk_days"], 58 - 10 + 3)  # recounted from the counter's Nov 20 closing


class Forms(unittest.TestCase):
    def test_form_names_and_footers(self):  # ENG-8
        for text, want in (("FR/BAR Standard Contract", cf.STANDARD), ("FR/BAR ASIS-7x", cf.AS_IS),
                           ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26", cf.AS_IS),
                           ("FloridaRealtors/FloridaBar – 7x Rev. 2/26", cf.STANDARD),
                           ("FR/BAR Standard with the As Is Rider (K)", cf.STANDARD), ("TREC 20-18", cf.OTHER)):
            self.assertEqual(cf.normalize(text), want, text)
        with self.assertRaises(cf.FormError):
            cf.normalize("FR/BAR contract")

    def test_inspection_blank_is_the_forms_15_days(self):  # ENG-7
        R = run({k: v for k, v in offer().items() if k != "inspection_days"})
        self.assertEqual(R["offers"][0]["inspection_days"], 15)
        R = run({k: v for k, v in offer(contract_form="TREC 20-18", inspection_walkaway=True).items() if k != "inspection_days"})
        self.assertEqual(R["offers"][0]["inspection_days"], 10)

    def test_other_contract_keeps_its_name_and_the_agents_reserve(self):  # OFR-113
        o = first(offer(contract_form="Texas TREC 20-18", inspection_walkaway=True),
                  listing={"costs": {"inspection_credit_reserve_pct": 0.01}})
        self.assertEqual(o["contract_label"], "Texas TREC 20-18")
        self.assertEqual(o["repair_reserve"], 4000)

    def test_rate_units_are_checked(self):  # OFR-112
        with self.assertRaises(oe.OfferError):
            run(offer(), listing={"costs": {"transfer_tax_rate": 0.7}})
        with self.assertRaises(cf.FormError):
            cf.repair_limits(400000, {"repair_limits": {"general": 1.5}})
        self.assertEqual(cf.repair_limits(400000, {"repair_limits": {"general": 6000}})["general"], 6000)


class ContractChecks(unittest.TestCase):
    def test_free_text_preapproval_expiry(self):  # ENG-5
        R = run(offer(approval_expires="30 days from letter"))
        self.assertIn("approval_expires", fields(R))
        self.assertFalse([f for f in R["offers"][0]["flags"] if f.get("topic") == "approval_expires"])

    def test_proof_of_funds_on_cash_needs_no_gap(self):  # ENG-6
        o = first(offer(financing="cash", proof_of_funds=400000, appraisal_gap=5000))
        self.assertFalse([f for f in o["flags"] if f.get("topic") == "proof_of_funds"])

    def test_missing_title_box_is_an_assumption(self):  # ENG-9, OFR-111
        R = run({k: v for k, v in offer().items() if k != "title_by"})
        self.assertEqual(fields(R)["title_by"]["impact"], "med")
        self.assertNotIn("title_by", fields(run(offer())))

    def test_lapsed_counter_sets_a_time_for_acceptance(self):  # OFR-122
        o = first(offer(expires="2026-09-20 17:00", inspection_days=15))
        self.assertEqual(o["counter_rows"][-1][0], "Time for Acceptance")
        o = first(offer(price=395000))
        self.assertEqual(o["counter_rows"][-1][0], "Time for Acceptance")
        self.assertEqual(first(offer(inspection_days=7, deposit=40000))["counter_rows"], [])  # nothing to counter: no row

    def test_preapproval_request_at_the_countered_price(self):  # OFR-116
        o = first(offer(price=380000, approval_max_price=370000))
        req = [f["request"] for f in o["flags"] if f.get("topic") == "approval_cap"][0]
        self.assertIn(oe.money(o["counter_terms"]["price"]), req)


class TitleBox(unittest.TestCase):
    def test_box_decides_the_sellers_searches(self):  # OFR-102, ENG-17
        self.assertEqual(cf.title_box(cf.AS_IS, {"title_by": "buyer_regional"}), "iii")
        self.assertEqual(cf.seller_title_searches(cf.AS_IS, {"title_by": "buyer_regional"})["title_search"], 200)
        by_seller = first(offer())
        by_buyer = first(offer(title_by="buyer"))
        regional = first(offer(title_by="buyer_regional"))
        self.assertEqual(line(by_seller["ns"], "settle"), -1145)
        self.assertEqual(line(by_buyer["ns"], "settle"), -770)  # (ii): no title or lien search for the seller
        self.assertEqual(line(regional["ns"], "settle"), -1095)  # (iii): the title search capped at $200
        collier = first(offer(), listing={"address": "1 Test St, Naples, FL 34102", "county": "Collier"})
        self.assertEqual(line(collier["ns"], "settle"), -1145)  # (i) in a (ii) county: the searches are the seller's
        dade = first(offer(), listing={"address": "1 Test St, Miami, FL 33133", "county": "Miami-Dade"})
        self.assertEqual(line(dade["ns"], "settle"), -1145)  # no $200 cap under (i)

    def test_target_uses_the_offers_title_terms(self):  # OFR-103
        o = first(offer(title_by="buyer"))
        self.assertEqual(line(o["target"], "title"), 0)
        self.assertEqual(line(o["target"], "settle"), line(o["ns"], "settle"))


class Money(unittest.TestCase):
    def test_free_rent_back(self):  # OFR-118
        R = run(offer(riders=["U"], rent_back_days=14, rent_back_monthly=0))
        self.assertNotIn("rent_back", fields(R))
        self.assertIn("rentback", [k for k, _, _ in R["offers"][0]["ns"]["lines"]])

    def test_listing_broker_pays_from_the_market_total(self):  # OFR-116, OFR-127
        R = run(offer(buyer_broker_pct=0.03, buyer_broker_paid_by="listing_broker"), seller={"listing_fee_pct": None})
        self.assertEqual(line(R["offers"][0]["ns"], "listing"), -20000)  # 5% total, not 2.5% + the 3% ask
        self.assertIn("5%", fields(R)["listing_fee_pct"]["why"])

    def test_estoppel_line_uses_the_markets_name(self):  # CMA-109 follow-up
        def label(o):
            return next(lab for k, lab, _ in o["ns"]["lines"] if k == "estoppel")
        self.assertEqual(label(first(offer(), listing={"hoa_monthly": 120})), "HOA Estoppel Letter")
        tx = first(offer(contract_form="TREC 20-18", inspection_walkaway=True),
                   listing={"address": "1 Test St, Austin, TX 78757", "state": "TX", "county": "Travis", "hoa_monthly": 120})
        self.assertEqual(label(tx), "HOA Status Letter")

    def test_tax_estimate_is_medium_impact(self):  # OFR-128
        R = run(offer(), listing={"annual_tax": None})
        self.assertEqual(fields(R)["annual_tax"]["impact"], "med")


class Assumptions(unittest.TestCase):
    def test_same_assumption_on_several_offers_is_listed_once(self):  # OFR-119
        o1 = {k: v for k, v in offer().items() if k != "contract_form"}
        R = run(o1, dict(o1, id="B", price=402000), dict(o1, id="C", price=398000))
        forms = [a for a in R["assumptions"] if a["field"] == "contract_form"]
        self.assertEqual(len(forms), 1)
        self.assertEqual(oe.scopes(forms[0]), ["offer A", "offer B", "offer C"])
        self.assertIn("contract form", oe.preliminary_inputs(R, "C"))


class CmaHandoff(unittest.TestCase):
    def h(self, **subject):
        return handoff.build("seller", "2026-09-20", {"address": "1 Test St", **subject},
                             {"low": 390000, "high": 410000, "midpoint": 400000}, [])

    def test_other_side_note_has_plain_words(self):  # CMA-101
        d = copy.deepcopy(BASE)
        d["offers"] = [offer()]
        h = handoff.build("buyer", "2026-09-20", {"address": "1 Test St"}, {"low": 390000, "high": 410000, "midpoint": 400000}, [])
        need = oe.preliminary_inputs(oe.analyze(d, cma=h))
        self.assertIn("a CMA from the seller's side", need)
        self.assertFalse([n for n in need if "cma side" in n])

    def test_another_propertys_cma_is_flagged(self):  # CMA-102
        d = copy.deepcopy(BASE)
        d["offers"] = [offer()]
        R = oe.analyze(d, cma=self.h(address="99 Other Ave"))
        self.assertEqual(fields(R)["cma_address"]["impact"], "high")
        self.assertNotIn("cma_address", fields(oe.analyze(d, cma=self.h(address="1 Test Street, Longwood, FL"))))

    def test_optional_subject_facts(self):  # CMA-111
        self.assertEqual(handoff.flood_code("X (lower risk)"), "X")
        self.assertIsNone(handoff.flood_code("To confirm (likely X)"))
        facts = handoff.subject_facts(annual_tax=4600, total_mills=18.18, homestead=True, flood_zone="To confirm",
                                      roof_year="2015", hoa_monthly=None)
        self.assertEqual(facts, {"annual_tax": 4600, "total_mills": 18.18, "homestead": True})
        with self.assertRaises(handoff.HandoffError):
            self.h(flood_zone="TO")
        d = copy.deepcopy(BASE)
        d["listing"].pop("annual_tax")
        d["offers"] = [offer()]
        R = oe.analyze(d, cma=self.h(annual_tax=4321, roof_year=2004))
        self.assertEqual((R["listing"]["annual_tax"], R["listing"]["roof_year"]), (4321, 2004))


class WalkAway(unittest.TestCase):
    def test_any_reason_window_is_named(self):  # OFR-121
        sys.path.insert(0, os.path.dirname(__file__))
        from skill_import import load
        review, = load("seller-offer-review", "review")
        o = first(offer(contract_form="standard", riders=["K"]))
        until, note = review.walk_away(o)
        self.assertEqual(o["walkaway_days"], 10)
        self.assertIn("Oct 3", note)
        self.assertIn("As Is Rider (K)", note)


if __name__ == "__main__":
    unittest.main()
