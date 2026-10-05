"""shared/offer_engine.py (used by seller-offer-review and buyer-offer-strategy): nets against the prototype, the
property's state, input checks, the CMA handoff, scoring, appraisal and contract rules, deadlines and assumptions.
Costs, counters and escalation have their own files (test_offer_review_costs/counter/escalation.py)."""
import copy
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.dirname(__file__))
from shared import contract_forms as cf, handoff, offer_engine as oe  # noqa: E402
from skill_import import load  # noqa: E402

review, render = load("seller-offer-review", "review", "render")

FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")

BASE = {"analysis_date": "2026-09-23",
        "listing": {"address": "1 Test St, Longwood, FL 32750", "state": "FL", "county": "Seminole", "list_price": 400000,
                    "cma_low": 390000, "cma_high": 410000, "annual_tax": 5000, "hoa_monthly": 0, "flood_disclosure": True},
        "seller": {"payoff": 200000, "listing_fee_pct": 0.025, "offered_buyer_broker_pct": 0.025}}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def hand(**k):
    """A hand-built FAR/BAR AS IS offer on BASE."""
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


def one(data):
    return oe.analyze(data)["offers"][0]


def prototype_costs(data):
    """The prototype's cost assumptions: 3% listing fee and 2.5% buyer-broker pay offered (when not given) and a flat
    $645 title settlement. Nothing about brokerage is built in, so the test states it."""
    d = copy.deepcopy(data)
    d["listing"]["costs"] = {"title_fees": 645}
    d.setdefault("seller", {}).setdefault("listing_fee_pct", 0.03)
    d["seller"].setdefault("offered_buyer_broker_pct", 0.025)
    return d


def line(sheet, key):
    return next((v for k, _, v in sheet["lines"] if k == key), 0)


def by_id(R):
    return {o["id"]: o for o in R["offers"]}


def fields(R):
    return {a["field"]: a for a in R["assumptions"] if "field" in a}


def topics(o, sev=None):
    return [f.get("topic") for f in o["flags"] if sev is None or f["sev"] == sev]


def sevs(o, topic):
    return [f["sev"] for f in o["flags"] if f.get("topic") == topic]


class MatchesPrototype(unittest.TestCase):
    """Given the prototype's own cost assumptions, every net, score and action matches its sample reports."""

    def test_four_offers(self):
        R = oe.analyze(prototype_costs(fixture("four-offers.json")))
        got = {o["id"]: (o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"], o["score"]["total"],
                         o["counter_score"], o["action"]) for o in R["ranked"]}
        self.assertEqual(got, {
            "B": (145851, 142851, 148650, 86, 82, "ACCEPT"),  # the seller wants certainty: no counter for a 0.7% gain
            "C": (134729, 131729, 153489, 100, 98, "BACKUP"),
            # downside from the CMA high; FHA appraisal protection runs to closing, so no gap coverage is asked; the
            # proration allows Florida's 4% early-payment discount; the buyer designates the Closing Agent (9(c)(ii))
            "A": (145319, 138567, 148211, 55, 63, "DECLINE"),
            "D": (154485, 140349, 146337, 45, 65, "DECLINE"),  # a kick-out clause (Rider X): contingency 2, not 1
        })
        self.assertEqual([o["id"] for o in R["ranked"]], ["B", "C", "A", "D"])
        self.assertEqual(R["mode"], "multi")

    def test_minimal_single(self):
        R = oe.analyze(prototype_costs(fixture("minimal-single.json")))
        o = R["offers"][0]
        self.assertEqual((o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"]), (349578, 347078, 353310))
        self.assertEqual((o["score"]["total"], o["action"]), (63, "COUNTER"))
        self.assertEqual([r[0] for r in o["counter_rows"]], ["Price", "Time for Acceptance"])
        self.assertEqual(R["seller"]["holding_monthly"], 500)  # HOA and loan interest; tax is in the proration

    def test_two_offers_accept(self):
        R = oe.analyze(prototype_costs(fixture("two-offers-accept.json")))
        b = by_id(R)["B"]
        self.assertEqual((b["ns"]["net_adj"], b["ns_down"]["net_adj"], b["ns_counter"]["net_adj"]), (170598, 167098, 172474))
        self.assertEqual((b["score"]["total"], b["counter_score"], b["action"]), (88, 84, "ACCEPT"))
        self.assertEqual(by_id(R)["C"]["action"], "DECLINE")


class State(unittest.TestCase):
    def test_state_from_the_address_or_the_form(self):
        """No state in the address: a FAR/BAR form means Florida (assumed, Florida costs); no form, no state and
        national estimates, asked as a high-impact input."""
        data = fixture("minimal-single.json")
        data["listing"]["address"] = "1207 Palmetto Way"
        data["offers"][0]["contract_form"] = "standard"
        R = oe.analyze(data)
        self.assertEqual((R["listing"]["state"], fields(R)["state"]["value"]), ("FL", "FL"))
        self.assertTrue(R["costs"].state_assumed)
        self.assertTrue(line(R["offers"][0]["ns"], "transfer"))
        self.assertFalse(R["market_notes"])  # no "don't assume Florida" note next to Florida costs
        data["offers"][0].pop("contract_form")
        R = oe.analyze(data)
        self.assertIsNone(R["listing"]["state"])
        self.assertEqual((fields(R)["state"]["value"], fields(R)["state"]["impact"]), (None, "high"))
        self.assertFalse(R["costs"].state_assumed)
        self.assertEqual(R["costs"].source("closing_costs.deed_transfer_tax_rate"), "estimate")
        self.assertIn("property state", oe.preliminary_inputs(R))

    def test_state_from_address_without_zip(self):
        self.assertEqual(oe.state_of({"address": "1207 Palmetto Way, Winter Springs, FL"}), "FL")
        self.assertEqual(oe.state_of({"address": "8104 Shoal Creek Blvd, Austin, TX 78757"}), "TX")
        self.assertIsNone(oe.state_of({"address": "12 Main St"}))


class Inputs(unittest.TestCase):
    def test_bad_inputs_stop(self):
        for data in ({"listing": {}, "offers": [{"price": 1}]}, {"listing": {"list_price": 300000}, "offers": [{"id": "A"}]}):
            with self.assertRaises(oe.OfferError):
                oe.analyze(data)
        data = fixture("minimal-single.json")
        data["seller"] = {**(data.get("seller") or {}), "listing_fee_pct": 3}  # a percent written as a whole number
        with self.assertRaisesRegex(oe.OfferError, r"listing_fee_pct.*0\.03"):
            oe.analyze(data)
        with self.assertRaises(oe.OfferError):
            run(hand(), listing={"costs": {"transfer_tax_rate": 0.7}})
        with self.assertRaises(cf.FormError):
            cf.repair_limits(400000, {"repair_limits": {"general": 1.5}})
        self.assertEqual(cf.repair_limits(400000, {"repair_limits": {"general": 6000}})["general"], 6000)


class Handoff(unittest.TestCase):
    def cma(self, side="seller", **subject):
        return handoff.build(side, "2026-09-20", {"address": "1 Test St", **subject},
                             {"low": 390000, "high": 410000, "midpoint": 400000}, [])

    def test_cma_range_and_midpoint(self):
        h = handoff.build(side="seller", as_of="2026-09-20", subject={"address": "1207 Palmetto Way, Winter Springs, FL 32708",
                          "beds": 3, "sqft": 1650}, value={"low": 380000, "high": 398000, "midpoint": 390000}, comps=[])
        R = oe.analyze(fixture("minimal-single.json"), cma=h)
        L = R["listing"]
        self.assertTrue(L["cma_provided"])
        self.assertEqual((L["cma_low"], L["cma_high"], L["cma_mid"], L["beds"]), (380000, 398000, 390000, 3))
        self.assertNotIn("cma_low / cma_high", fields(R))

    def test_listing_file_wins_and_nulls_are_filled(self):
        d = fixture("two-offers-accept.json")
        h = handoff.build(side="seller", as_of="2026-09-20", subject={}, value={"low": 1, "high": 2, "midpoint": 1.5}, comps=[])
        self.assertEqual(oe.analyze(d, cma=h)["listing"]["cma_low"], 500000)
        d["listing"]["cma_low"] = None
        h = {"kind": "cma", "version": 1, "side": "buyer", "source": "buyer-cma",
             "value": {"low": 495000, "high": 520000, "midpoint": 507500}}
        L = oe.analyze(d, cma=h)["listing"]
        self.assertEqual((L["cma_low"], L["cma_high"]), (495000, 525000))  # an explicit null is filled; the file's own wins

    def test_another_propertys_cma_is_flagged(self):
        d = copy.deepcopy(BASE)
        d["offers"] = [hand()]
        self.assertEqual(fields(oe.analyze(d, cma=self.cma(address="99 Other Ave")))["cma_address"]["impact"], "high")
        self.assertNotIn("cma_address", fields(oe.analyze(d, cma=self.cma(address="1 Test Street, Longwood, FL"))))

    def test_optional_subject_facts(self):
        self.assertEqual(handoff.flood_code("X (lower risk)"), "X")
        self.assertIsNone(handoff.flood_code("To confirm (likely X)"))
        facts = handoff.subject_facts(annual_tax=4600, total_mills=18.18, homestead=True, flood_zone="To confirm",
                                      roof_year="2015", hoa_monthly=None)
        self.assertEqual(facts, {"annual_tax": 4600, "total_mills": 18.18, "homestead": True})
        with self.assertRaises(handoff.HandoffError):
            self.cma(flood_zone="TO")
        d = copy.deepcopy(BASE)
        d["listing"].pop("annual_tax")
        d["offers"] = [hand()]
        R = oe.analyze(d, cma=self.cma(annual_tax=4321, roof_year=2004))
        self.assertEqual((R["listing"]["annual_tax"], R["listing"]["roof_year"]), (4321, 2004))


class Scoring(unittest.TestCase):
    def test_agent_overrides(self):
        d = fixture("minimal-single.json")
        d["offers"][0]["scores"] = {"agent": {"score": 5, "why": "Closed 3 deals with them"}}
        d["offers"][0]["recommendation"] = "accept"
        o = one(d)
        self.assertEqual((o["score"]["scores"]["agent"], o["score"]["src"]["agent"], o["action"]), (5, "agent", "ACCEPT"))

    def test_seller_side_limits(self):
        d = fixture("two-offers-accept.json")
        d["offers"][0].update(financing="conventional", down_pct=0.05, seller_concessions=25600)  # 5%; the cap is 3%
        self.assertEqual(sevs(by_id(oe.analyze(d))["B"], "concessions_cap"), ["High"])
        d = fixture("two-offers-accept.json")
        d["offers"][0]["insurance_quote"] = "planned"  # a planned quote isn't scored
        planned = by_id(oe.analyze(d))["B"]["score"]["scores"]["property"]
        d["offers"][0]["insurance_quote"] = True
        self.assertEqual(by_id(oe.analyze(d))["B"]["score"]["scores"]["property"] - planned, 1)

    def test_deposit_rating_agrees_with_the_norm(self):
        """1.0% against a 1% norm is good, so it's neither scored nor countered as weak."""
        T = oe.analyze(fixture("texas-single.json"))
        o = T["offers"][0]
        self.assertEqual(oe.deposit_status(o, T["listing"]), "good")
        self.assertNotIn("Escrow Deposit", [r[0] for r in o["counter_rows"]])
        R = review.analyze(fixture("texas-single.json"))
        row = next(r for r in review.term_rows(R["offers"][0], R) if r[0] == "Escrow Deposit")
        self.assertEqual(row[3], "good")  # the terms table rates it the same


class Appraisal(unittest.TestCase):
    def test_appraisal_form_rules(self):
        o = first(hand(financing="cash", riders=["F"], price=415000))  # cash with Rider F carries appraisal risk
        self.assertTrue(o["appraisal_risk"])
        self.assertEqual(o["appraisal_days"], cf.appraisal_window("F", o["close_days"]))
        o = first(hand(financing="usda", down_pct=0, appraisal_form="aga", appraisal_gap=5000, price=415000))
        self.assertNotEqual(o["appraisal_form"], "aga")  # a USDA gap on AGA-1 is intent only
        self.assertEqual(o["gap_cover"], 0)
        self.assertIn("aga_loan_type", topics(o))
        self.assertTrue(cf.aga_named({"addenda": ["Appraisal Gap Addendum (AGA-1)"]}))
        self.assertEqual(cf.appraisal_form(cf.AS_IS, {"appraisal_form": "aga"}, "fha"), None)
        self.assertEqual(cf.appraisal_form(cf.AS_IS, {"appraisal_form": "aga"}, "cash"), "aga")
        with open(os.path.join(ROOT, "shared", "offer_engine.py")) as f:
            self.assertNotIn("AGA(-1)?", f.read())  # the name pattern is written once, in contract_forms

    def test_aga_window_against_closing(self):
        o = first(hand(appraisal_form="aga", appraisal_gap=5000, closing_date="2026-10-23", price=415000))
        self.assertEqual((o["appraisal_days"], o["aga_window_full"]), (o["close_days"], 36))  # stops at closing
        self.assertIn("aga_window_past_closing", topics(o))
        self.assertEqual(cf.aga_valuation_days(21), 15)
        data = fixture("expired-aga.json")
        data["offers"][0]["closing_date"] = "2026-11-20"  # 55 days: the window ends well before closing
        self.assertFalse({"aga_window_at_closing", "aga_window_past_closing"} & set(topics(one(data))))

    def test_rider_windows(self):
        self.assertEqual(cf.appraisal_window("F", 5), cf.RIDER_F_NOTICE_DAYS)
        for days in (5, 0):
            self.assertEqual(cf.rider_windows(cf.AS_IS, {"riders": ["H"]}, days)[0], [("H", 0, "insurance rider")])
        o = first(hand(riders=["F"], closing_date="2026-12-18", price=415000), seller={"deadline": "2026-11-20"})
        self.assertEqual(str(o["counter_terms"]["close"]), "2026-11-20")
        self.assertEqual(o["risk_days"], 86 - 10 + 3)  # Dec 18: Rider F's blank date, 10 days before closing, + 3
        self.assertEqual(o["counter_risk_days"], 58 - 10 + 3)  # recounted from the counter's Nov 20 closing

    def test_standard_without_rider_f(self):
        """Para. 8(b)(2): the Standard contract appraises within loan approval; no rider flag for a stated period."""
        d = fixture("counter-chain-standard.json")
        d["offers"][0]["appraisal_contingency"] = 30
        self.assertNotIn("rider_F", topics(one(d)))

    def test_downside_price(self):
        data = fixture("escalation.json")
        b = data["offers"][1]
        b.update(price=420000, appraisal_contingency=False, appraisal_gap=0)
        o = by_id(oe.analyze(data))["B"]
        self.assertTrue(o["appraisal_waived"])
        self.assertEqual(o["downside_price"], 410000)  # a financed waiver without documented funds: the CMA high
        self.assertLess(o["score"]["scores"]["appraisal"], 5)
        b["gap_funds"] = 10000
        self.assertEqual(by_id(oe.analyze(data))["B"]["downside_price"], 420000)
        data = fixture("escalation.json")  # $405k nets more than $400k inside a $390k-$410k range and ranks above it
        data["offers"] = [dict(data["offers"][1], id="A", price=400000), dict(data["offers"][1], id="B")]
        R = oe.analyze(data)
        self.assertEqual([o["id"] for o in R["ranked"]], ["B", "A"])
        self.assertEqual(by_id(R)["B"]["downside_price"], 405000)


class Forms(unittest.TestCase):
    def test_form_names_and_footers(self):
        for text, want in (("FAR/BAR Standard Contract", cf.STANDARD), ("FAR/BAR ASIS-7x", cf.AS_IS),
                           ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26", cf.AS_IS),
                           ("FloridaRealtors/FloridaBar – 7x Rev. 2/26", cf.STANDARD),
                           ("FAR/BAR Standard with the As Is Rider (K)", cf.STANDARD), ("TREC 20-18", cf.OTHER)):
            self.assertEqual(cf.normalize(text), want, text)
        with self.assertRaises(cf.FormError):
            cf.normalize("FAR/BAR contract")

    def test_inspection_blank_is_the_forms_15_days(self):
        self.assertEqual(first({k: v for k, v in hand().items() if k != "inspection_days"})["inspection_days"], 15)
        other = {k: v for k, v in hand(contract_form="TREC 20-18", inspection_walkaway=True).items() if k != "inspection_days"}
        self.assertEqual(first(other)["inspection_days"], 10)

    def test_rider_k_watch_items_are_a_low_flag(self):
        d = fixture("minimal-single.json")
        d["offers"][0].update(financing="conventional", down_pct=0.2, contract_form="standard", riders=["K"])
        self.assertEqual(sevs(one(d), "rider_K_terms"), ["Low"])


class ContractChecks(unittest.TestCase):
    def test_preapproval_expiry(self):
        R = run(hand(approval_expires="30 days from letter"))  # free text: an assumption, not a flag
        self.assertIn("approval_expires", fields(R))
        self.assertFalse(sevs(R["offers"][0], "approval_expires"))
        d = fixture("expired-aga.json")
        d["offers"][0]["approval_expires"] = "2026-10-01"  # before closing
        self.assertEqual(sevs(one(d), "approval_expires"), ["Med"])
        d["offers"][0]["approval_expires"] = "2027-01-31"
        self.assertFalse(sevs(one(d), "approval_expires"))

    def test_proof_of_funds(self):
        self.assertFalse(sevs(first(hand(financing="cash", proof_of_funds=400000, appraisal_gap=5000)), "proof_of_funds"))
        d = fixture("expired-aga.json")
        o = d["offers"][0]
        o["proof_of_funds"] = o["price"] - o["loan_amount"] + o["appraisal_gap"] - 1  # a dollar short of the cash needed
        self.assertEqual(sevs(one(d), "proof_of_funds"), ["High"])
        o["proof_of_funds"] += 1
        self.assertFalse(sevs(one(d), "proof_of_funds"))

    def test_missing_title_box_is_an_assumption(self):
        R = run({k: v for k, v in hand().items() if k != "title_by"})
        self.assertEqual(fields(R)["title_by"]["impact"], "med")
        self.assertNotIn("title_by", fields(run(hand())))

    def test_offer_ending_today_isnt_lapsed(self):
        d = fixture("expired-aga.json")
        d["offers"][0]["expires"] = "2026-09-26 17:00"  # the same day: not provably passed, but it ends today
        o = one(d)
        self.assertEqual((sevs(o, "expired"), o["action"]), (["High"], "COUNTER"))

    def test_agent_issues_and_engine_flags(self):
        gg = [f for f in one(fixture("expired-aga.json"))["flags"] if f["topic"] == "rider_GG"]
        self.assertTrue(gg[0]["agent_topics"])  # the agent's Low issue, raised to the engine's level, keeps its topic
        d = fixture("counter-chain-standard.json")
        d["offers"][0].pop("prior_counters")
        d["offers"][0]["contract_issues"] = [{"sev": "High", "issue": "Counter 2 drops the 10-day inspection period.",
                                              "fix": "Restate it."}]
        self.assertEqual(sevs(one(d), "inspection_period"), ["High"])  # the agent's only
        d = fixture("counter-chain-standard.json")  # advice to restate a loan term isn't a dropped term
        d["offers"][0]["contract_issues"] = [{"sev": "Med", "issue": "Para. 2(c) keeps the Loan Amount in dollars.",
                                              "fix": "Confirm the cash, or restate Para. 2(c) and 2(e) in the next counter."}]
        flags = one(d)["flags"]
        self.assertEqual([f["sev"] for f in flags if f.get("topic") == "counter_chain"], ["High"])
        self.assertEqual([f["sev"] for f in flags if f["issue"].startswith("Para. 2(c)")], ["Med"])

    def test_condo_and_flood(self):
        R = oe.analyze(fixture("broward-condo.json"))
        req = [x.get("request") for x in by_id(R)["A"]["flags"] if x["topic"] == "condo_project_approval"]
        self.assertTrue(req and req[0])  # FHA on a condo: asked of the buyer's agent
        d = fixture("broward-condo.json")
        d["listing"]["flood_disclosure"] = True
        self.assertNotIn("flood_disclosure", topics(by_id(oe.analyze(d))["A"]))
        text = json.dumps([o["flags"] for o in oe.analyze(fixture("texas-single.json"))["offers"]])
        self.assertFalse([s for s in ("689.302", "718.503") if s in text])  # no Florida statutes elsewhere


class Deadlines(unittest.TestCase):
    def test_target_closes_on_a_business_day(self):
        R = oe.analyze(fixture("four-offers.json"))
        self.assertEqual(R["target_close"], R["ranked"][0]["close"])  # one target closing: the recommended offer's
        # with nothing ranked, the latest closing capped at the seller's deadline, a business day (Sun Nov 15 -> Fri Nov 13)
        self.assertEqual(oe.report_target_close([], R["active"], R["listing"], R["seller"]).isoformat(), "2026-11-13")

    def test_no_contingency_outlives_closing(self):
        d = fixture("minimal-single.json")
        d["analysis_date"] = "2026-09-26"  # FHA to a Saturday closing
        d["offers"][0]["loan_approval_days"] = 45
        o = one(d)
        self.assertEqual((o["risk_days"], o["close_days"]), (35, 35))
        self.assertEqual(oe.rolled(o["firm_date"], {"contract.weekend_holiday_rollover": "next_business_day"},
                                   o["close"])[0], o["close"])
        d["offers"][0].pop("loan_approval_days")
        c = review.result(review.analyze(d))["summary"]["certainty"]
        self.assertTrue(c["walk_away_until"].startswith("Sat Oct 31"), c["walk_away_until"])

    def test_walk_away_rolls_off_a_weekend(self):
        R = review.analyze(fixture("expired-aga.json"))  # AGA-1 window (36 days) ends Sun Nov 1
        o = R["offers"][0]
        self.assertEqual(review.firm_day(o, R["costs"]), (oe.date(2026, 11, 2), oe.date(2026, 11, 1)))
        c = review.result(R)["summary"]["certainty"]
        self.assertTrue(c["walk_away_until"].startswith("Mon Nov 2"))
        self.assertIn("Oct 26", c["walk_away_note"])  # the other windows end at 30 days
        tx = review.analyze(fixture("texas-single.json"))  # no rollover rule for another state's contract
        self.assertEqual(oe.rolled(oe.date(2026, 11, 1), tx["costs"]), (oe.date(2026, 11, 1), None))
        R = run(hand(contract_form="standard", riders=["K"]))  # Rider K: Sat Oct 3 rolls to Mon Oct 5
        self.assertEqual(R["offers"][0]["walkaway_days"], 10)
        self.assertIn("Oct 5", review.walk_away(R["offers"][0], R["costs"])[1])


class Assumptions(unittest.TestCase):
    def test_same_assumption_on_several_offers_is_listed_once(self):
        o1 = {k: v for k, v in hand().items() if k != "contract_form"}
        R = run(o1, dict(o1, id="B", price=402000), dict(o1, id="C", price=398000))
        forms = [a for a in R["assumptions"] if a.get("field") == "contract_form"]
        self.assertEqual(len(forms), 1)
        self.assertEqual(oe.scopes(forms[0]), ["offer A", "offer B", "offer C"])
        self.assertIn("contract form", oe.preliminary_inputs(R, "C"))


if __name__ == "__main__":
    unittest.main()
