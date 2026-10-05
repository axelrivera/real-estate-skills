"""Tests for skills/buyer-offer-strategy/scripts/strategy.py: pricing, limits, options, escalation, appraisal gap,
dates, taxes, insurance, the market read and the assumptions asked. The worksheet, templates and PDFs are in
test_buyer_offer_worksheet.py. Facts of the unmodified fixtures are pinned by golden (dev/golden/buyer-offer-strategy/)."""
import copy
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

strategy, buyer_render = load("buyer-offer-strategy", "strategy", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy")
EVALS = os.path.join(ROOT, "dev", "evals", "buyer-offer-strategy", "files")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def run(d):
    return strategy.analyze(d, cma=strategy.load_cma(d))


def analyze(name):
    return run(fixture(name))


def fields(r, impact=None):
    return [a["field"] for a in r["missing"] if impact is None or a["impact"] == impact]


def to_confirm_fields(r):
    """The quick answer's questions, as the fields they ask about."""
    by_why = {a["why"]: a["field"] for a in r["missing"]}
    return [by_why.get(w) for w in strategy.result(r)["to_confirm"]]


def gatlin(**buyer):
    """A list-price-only buyer: an address, a list price and the buyer's cash."""
    return {"analysis_date": "2026-09-26", "property": {"address": "2716 Gatlin Ave, Orlando, FL", "list_price": 429000},
            "buyer": {"cash_available": 38000, **buyer}}


def roofed(d, year=2011):
    """The same input with a roof that age: the insurance and condition criterion scores lower without a quote in hand."""
    d["property"]["roof_year"] = year
    return d


def cypress():
    """An FHA buyer whose payment limit caps the price below the value range, against 2-3 competing offers."""
    d = {"analysis_date": "2026-09-26",
         "property": {"address": "1532 Cypress Bend Dr, Casselberry, FL 32707", "list_price": 365000},
         "competition": {"level": 2, "note": "Listing agent: 2 other offers coming", "deadline": "Friday 5 PM"},
         "buyer": {"financing": "fha", "down_pct": 0.035, "approval": "du_approved", "lender_called": True,
                   "cash_available": 26000, "reserve_floor": 2000, "max_price": 375000, "max_payment": 3200},
         "costs": {"rate": 7.03, "rate_source": "Freddie Mac weekly 30-year average, week of Sep 24, 2026"}}
    return strategy.analyze(d, cma=strategy.load_cma(d, os.path.join(EVALS, "1532-Cypress-Bend-Dr.cma.json")))


def reach(**buyer):
    """One competing offer, a buyer CMA's range, a 2010 roof and HOA dues (one-competing-reach.json)."""
    d = fixture("one-competing-reach.json")
    d["buyer"].update(buyer)
    return d


GAP = {"analysis_date": "2026-09-23",
       "property": {"address": "100 Test Rd, Sanford, FL 32771", "county": "Seminole", "list_price": 400000,
                    "year_built": 2012},
       "value": {"cma_low": 380000, "cma_high": 398000},
       "competition": {"level": 3, "deadline": "2026-09-25 17:00"},
       "buyer": {"financing": "conventional", "down_pct": 0.2, "cash_available": 140000, "max_price": 420000,
                 "reserve_floor": 5000},
       "worksheet": {"contract_form": "as_is"}}


class Pricing(unittest.TestCase):
    @staticmethod
    def only_offer(**buyer):
        return {"analysis_date": "2026-09-23",
                "property": {"address": "1 Main St, Orlando, FL", "state": "FL", "county": "Orange", "list_price": 400000},
                "value": {"cma_low": 420000, "cma_high": 440000}, "competition": {"level": 0},
                "buyer": {"financing": "conventional", "down_pct": 0.2, "cash_available": 150000, **buyer}}

    def test_seller_net_with_given_costs(self):
        """A 3% listing fee and $645 title fees: the net at the value midpoint, with the early-payment discount in the
        proration and closing counted from the expected acceptance (Mon Sep 28)."""
        d = fixture("fha-competitive.json")
        d["listing_side"]["listing_fee_pct"] = 0.03
        d["property"]["costs"] = {"title_fees": 645}
        r = run(d)
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 331744)
        self.assertEqual(r["target"], 335610)

    def test_fha_closing_costs_tax_the_financed_premium(self):
        """Florida 3% (2.5% plus 0.5% prepaids) plus note stamps and intangible tax on the loan, which for FHA includes
        the financed upfront premium."""
        r = analyze("fha-competitive.json")
        loan = 365000 * 0.965 * 1.0175
        self.assertEqual(strategy.closing_costs(r["B"], 365000),
                         round(365000 * 0.03 + round(loan * 0.0035) + round(loan * 0.002)))

    def test_only_offer_never_above_list(self):
        self.assertEqual(run(self.only_offer())["terms"]["recommended"]["price"], 400000)

    def test_lower_cost_starts_from_the_agents_price(self):
        for price in (632000, 612000):
            d = fixture("texas-cma-escalation.json")
            d["overrides"] = {"price": price}
            r = run(d)
            self.assertEqual(r["terms"]["recommended"]["price"], price)  # the agent's choice stands
            lc = r["terms"].get("lower_cost")
            if price == 632000:
                self.assertEqual(lc["price"], 615000)
                self.assertLess(r["cash"]["lower_cost"]["worst"], r["cash"]["recommended"]["worst"])
            elif lc:  # below the rules' own price, softening never raises it
                self.assertLessEqual(lc["price"], price)

    def test_jumbo_and_fha_limits(self):
        d = self.only_offer(down_pct=0.05)
        d["property"].update(list_price=950000)
        d["value"] = {"cma_low": 930000, "cma_high": 980000}
        self.assertIn("loan_limit", [a["field"] for a in run(d)["assumptions"]])
        d = self.only_offer(financing="fha", down_pct=0.035)
        d["property"].update(list_price=700000)
        d["value"] = {"cma_low": 690000, "cma_high": 720000}
        why = next(a["why"] for a in run(d)["assumptions"] if a["field"] == "loan_limit")
        self.assertIn("$541,287", why)  # the 2026 FHA floor

    def test_small_concession_ask_rounds_up_or_drops(self):
        """An ask under the minimum rounds up to it when the cash needs it, and drops to $0 when every limit holds; no
        option ever asks for less than the minimum."""
        r = run(reach())
        B, costs = r["B"], r["costs"]
        t = dict(r["terms"]["recommended"], seller_concessions=0)
        self.assertFalse(strategy.within_limits(B, costs, dict(t, price=445000)))  # $0 would break the reserve here
        self.assertEqual(strategy.meaningful_ask(B, costs, dict(t, price=445000), 500), strategy.MIN_CONCESSION_ASK)
        r = run(reach(cash_available=60000))
        B, costs = r["B"], r["costs"]
        t = dict(r["terms"]["recommended"], seller_concessions=0)
        self.assertTrue(strategy.within_limits(B, costs, t))
        self.assertEqual(strategy.meaningful_ask(B, costs, t, 500), 0)
        self.assertEqual(strategy.meaningful_ask(B, costs, t, 2500), 2500)  # above the minimum: as is
        for cash in (41000, 41900, 42000, 43000, 45000):
            r = run(reach(cash_available=cash))
            for k, t in r["terms"].items():
                c = t.get("seller_concessions", 0)
                self.assertTrue(c == 0 or c >= strategy.MIN_CONCESSION_ASK, (cash, k, c))


class Limits(unittest.TestCase):
    def test_input_errors(self):
        d = fixture("fha-competitive.json")
        d["buyer"]["down_pct"] = 3.5  # a percent, not a fraction
        rate = {"analysis_date": "2026-09-23", "property": {"address": "1 Main St, Orlando, FL", "list_price": 400000},
                "buyer": {"cash_available": 40000}, "costs": {"rate": 0.064}}  # a fraction, not a percent
        for bad in (d, rate, {"property": {"address": "x"}}):
            with self.subTest(bad=bad.get("buyer")), self.assertRaises(strategy.oe.OfferError):
                strategy.analyze(bad)

    def test_not_enough_cash_is_one_limit(self):
        r = analyze("fha-competitive.json")  # inside the floor: a thin-cushion caution, no limit
        self.assertTrue(r["reserve_tight"])
        self.assertEqual(r["constraints"], [])
        d = fixture("fha-competitive.json")
        d["buyer"]["cash_available"] = 9000
        r = run(d)
        self.assertLess(r["cash"]["recommended"]["reserve"], 0)
        self.assertEqual(len(r["constraints"]), 1)  # the shortfall, said once
        self.assertNotIn("stronger", r["O"])

    def test_pushback_names_the_limit_it_breaks(self):
        r = analyze("fha-competitive.json")
        B, t = r["B"], r["terms"]["recommended"]
        self.assertEqual(next(p for p in strategy.pushback(r) if p["term"] == "Price")["breaks"], [])
        B["buyer"]["max_payment"] = strategy.monthly_payment(B, r["costs"], t["price"])  # the ask is now over the cap
        row = next(p for p in strategy.pushback(r) if p["term"] == "Price")
        self.assertEqual(row["breaks"], ["max_payment"])
        keys = [k for k, _ in strategy.limits_broken(B, r["costs"], dict(t, price=B["buyer"]["max_price"] + 1000,
                                                                          appraisal_gap=10 ** 6))]
        self.assertEqual(keys, ["max_price", "max_payment", "cash"])
        d = fixture("texas-cma-escalation.json")  # an override past the reserve is named
        d["overrides"] = {"appraisal_gap": 20000}
        self.assertTrue(strategy.summary(run(d))["breaks_limits"])
        self.assertEqual(strategy.summary(analyze("texas-cma-escalation.json"))["breaks_limits"], [])

    def test_thin_cushion_names_a_roomier_offer(self):
        """The cheapest offer that reaches the band keeps under $1,000 over the floor: a caution (not a limit) with the
        same-outlook offer that keeps more cash, its monthly cost and the cash it keeps; the files keep the cheapest."""
        r = run(reach(cash_available=41900))
        self.assertIn("tight_reserve", [x["key"] for x in r["reply_lines"]])
        roomy, alt = r["reached"]["roomy"], r["reserve_alt"]
        self.assertGreater(strategy.buyer_cash(r["B"], roomy)["reserve"], r["cash"]["recommended"]["reserve"] + 1000)
        self.assertEqual(alt["price"], roomy["price"])
        self.assertEqual(alt["payment_more"], strategy.monthly_payment(r["B"], r["costs"], alt["price"])
                         - strategy.monthly_payment(r["B"], r["costs"], r["terms"]["recommended"]["price"]))
        self.assertGreater(alt["payment_more"], 0)
        self.assertEqual(alt["cash_kept"], strategy.buyer_cash(r["B"], roomy)["reserve"] - r["cash"]["recommended"]["reserve"])
        self.assertIn(strategy.money(alt["cash_kept"]), r["reserve_tight"])
        self.assertIn(strategy.money(alt["payment_more"]), r["reserve_tight"])
        self.assertLess(r["terms"]["recommended"]["price"], alt["price"])
        s = strategy.summary(r)
        self.assertNotIn(r["reserve_tight"], s["constraints"])
        self.assertEqual(s["cautions"], [r["reserve_tight"]])
        self.assertIsNone(analyze("cash.json")["reserve_tight"])  # plenty of cushion: no line

    def test_payment_cap_names_its_assumed_inputs(self):
        d = fixture("fha-competitive.json")
        d["costs"].pop("rate"), d["costs"].pop("insurance_annual")
        r = run(d)
        self.assertEqual(len(r["B"]["payment_assumed"]), 2)
        self.assertEqual(r["terms"]["recommended"]["price_by"], "payment")
        for words in r["B"]["payment_assumed"]:
            self.assertIn(words, strategy.why_text(r["why"]["price"]))  # the payment limit sets the price, with what it assumed
        d = fixture("fha-competitive.json")
        self.assertEqual(len(run(d)["B"]["payment_assumed"]), 1)  # the insurance estimate
        d["buyer"]["insurance_quote"] = True  # a quote in hand and a given rate: nothing assumed
        self.assertEqual(run(d)["B"]["payment_assumed"], [])
        r = cypress()  # capped below the range: the limit line names the payment that would reach it
        pay = strategy.monthly_payment(r["B"], r["costs"], r["B"]["value"]["cma_low"])
        self.assertIn(strategy.money(pay), r["constraints"][0])


class Options(unittest.TestCase):
    def test_stronger_is_recommended_when_it_lifts_the_outlook_inside_limits(self):
        """Only a quote in hand is scored, so the buyer here has one (a 2014 roof: Stronger's deposit crosses into Strong)."""
        r = run(roofed(gatlin(insurance_quote=True), 2014))
        lvl = r["B"]["competition"]["level"]
        self.assertEqual(r["promoted"], "stronger")
        self.assertEqual(r["bands"]["recommended"][lvl][0], "strong")
        self.assertEqual(r["R"]["listing"]["state"], "FL")  # read from "Orlando, FL" without a ZIP
        r = run(roofed(gatlin(), 2014))  # no quote: not promoted, but kept as an option when it scores higher
        self.assertTrue(strategy.stronger_fits(r))
        self.assertIn("stronger", r["terms"])
        self.assertGreater(r["O"]["stronger"]["score"]["total"], r["O"]["recommended"]["score"]["total"])

    def test_stronger_names_only_what_it_raised(self):
        self.assertEqual(strategy.raised({"deposit": 12000, "appraisal_gap": 0}, {"deposit": 8000, "appraisal_gap": 0}),
                         ["raised_deposit"])
        why = strategy.promote_why({}, {}, "stronger", {"price": 400000, "deposit": 12000, "appraisal_gap": 0},
                                   {"deposit": 8000, "appraisal_gap": 0})
        self.assertNotIn("appraisal_gap", why)
        r = analyze("fha-competitive.json")  # the no-stronger reason quotes the deposit as printed
        t = dict(r["terms"]["recommended"], deposit=11000, price=358000)
        self.assertIn(strategy.term_val("deposit", t, r["B"]), strategy.no_stronger_reason(r["B"], t))

    def test_missing_options_are_named(self):
        s = strategy.summary(analyze("fha-competitive.json"))
        self.assertEqual([a["key"] for a in s["absent"]], ["stronger"])
        self.assertEqual(s["options_title"], "Your Options")
        d = fixture("fha-competitive.json")
        d["buyer"]["max_payment"] = 3100  # a lower payment cap: the softer offer would be Unlikely, one option left
        r = run(d)
        s = strategy.summary(r)
        self.assertEqual(list(r["terms"]), ["recommended"])
        self.assertEqual({a["key"] for a in s["absent"]}, {"stronger", "lower_cost"})
        self.assertEqual(s["options_title"], "Your Offer")

    def test_stronger_net_option_is_inside_the_limits_and_shown_not_promoted(self):
        """A smaller concession ask that nets the seller more stays inside every limit and the CMA's walk-away; when
        it ranks higher it's an option the buyer can pick, never promoted over the recommended offer."""
        r = analyze("kestrel-v5.json")
        B, costs, rec = r["B"], r["costs"], r["terms"]["recommended"]
        st = strategy.stronger_net(B, costs, rec)
        self.assertTrue(strategy.within_limits(B, costs, st))
        self.assertLessEqual(st["price"], B["cma_offer_plan"]["walk_away"])
        self.assertGreater(st["price"] - st["seller_concessions"], rec["price"] - rec["seller_concessions"])
        d = fixture("kestrel-v5.json")
        d["overrides"] = {"price": 436000, "seller_concessions": 5000, "deposit": 13500}
        r = run(d)
        lvl = r["B"]["competition"]["level"]
        st = r["terms"]["stronger"]
        self.assertEqual((st["price"], st["seller_concessions"]), (440000, 1000))
        self.assertTrue(strategy.within_limits(r["B"], r["costs"], st))
        self.assertEqual((r["bands"]["stronger"][lvl][1], r["bands"]["recommended"][lvl][1]), ("At Risk", "Unlikely"))
        B = r["B"]
        B["overrides"] = {}
        variants, _, by_net = strategy.option_set(B, r["costs"], r["terms"]["recommended"])
        self.assertTrue(by_net)
        _, O = strategy.run_engine(B, r["costs"], variants)
        self.assertNotEqual(strategy.better_option(B, r["costs"], dict(variants), O, lvl, promote_stronger=False), "stronger")
        self.assertEqual(strategy.better_option(B, r["costs"], dict(variants), O, lvl), "stronger")

    def test_reaches_the_next_band_unless_overridden(self):
        """The rule's draft reads Unlikely against one competing offer; the search reaches At Risk inside every limit,
        at or below the range's top and the CMA's walk-away."""
        r = analyze("one-competing-reach.json")
        B = r["B"]
        rule, _ = strategy.build_offer(B, r["costs"])
        _, O = strategy.run_engine(B, r["costs"], [("recommended", rule)])
        self.assertEqual(strategy.band_of(strategy.ci(O["recommended"], O["recommended"]["target"]["net_adj"],
                                                      B["property"]["list_price"]), 1)[0], "unl")
        t = r["terms"]["recommended"]
        self.assertLessEqual(t["price"], min(B["value"]["cma_high"], B["cma_offer_plan"]["walk_away"]))
        self.assertGreaterEqual(r["cash"]["recommended"]["reserve"], B["buyer"]["reserve_floor"])
        d = fixture("one-competing-reach.json")  # no search with overrides or an offer already Competitive
        d["overrides"] = {"price": 438000}
        self.assertIsNone(run(d)["reached"])
        self.assertIsNone(analyze("condo-flood.json")["reached"])  # Competitive already: the rule's offer stands

    def test_lower_cost_reasons_fit_the_competition_level(self):
        r = analyze("one-competing-reach.json")
        B, costs = r["B"], r["costs"]
        rec, _ = strategy.build_offer(B, costs)
        t, why = strategy.lower_cost(B, costs, rec)
        B0 = copy.deepcopy(B)
        B0["competition"]["level"] = 0
        _, why0 = strategy.build_offer(B0, costs)
        promoted = strategy.promote_why({}, why, "lower_cost", t, rec)
        for k in ("price", "seller_concessions"):  # never the level-0 reason on a deal with one competing offer
            self.assertNotEqual(why[k], why0[k])
            self.assertNotEqual(promoted[k], why0[k])

    def test_unlikely_lower_cost_is_never_offered(self):
        r = cypress()
        self.assertIsNone(r["promoted"])
        self.assertEqual(r["bands"]["recommended"][2][1], "Unlikely")
        self.assertEqual(r["terms"]["recommended"]["seller_concessions"], 1000)  # $500 short, rounded up to the minimum
        self.assertNotIn("lower_cost", r["terms"])
        self.assertIn("lower_cost", r["absent"])


class BuyerPriority(unittest.TestCase):
    """buyer_priority picks the recommended option; competition.level and buyer_priority take only their choices."""

    def with_priority(self, name, priority, roof=None):
        d = fixture(name)
        d["buyer_priority"] = priority
        return run(roofed(d, roof) if roof else d)

    def test_missing_is_balanced_with_no_assumption(self):
        r = analyze("minimal.json")
        self.assertEqual(r["buyer_priority"], "balanced")
        self.assertNotIn("buyer_priority", fields(r))
        self.assertEqual(r["terms"]["recommended"], self.with_priority("minimal.json", "balanced")["terms"]["recommended"])

    def test_win_takes_the_higher_score_inside_the_limits(self):
        bal, win = analyze("condo-flood.json"), self.with_priority("condo-flood.json", "win")
        self.assertIsNone(bal["promoted"])
        self.assertEqual(win["promoted"], "stronger")
        self.assertGreater(win["O"]["recommended"]["score"]["total"], bal["O"]["recommended"]["score"]["total"])
        self.assertFalse(win["promoted_lifts"])  # same outlook, a higher score
        self.assertEqual(strategy.result(win)["summary"]["priority"]["key"], "win")

    def test_protect_cash_takes_less_cash_unless_at_risk(self):
        # a newer roof keeps the fuller offer in the Strong band, so protecting cash gives something up
        bal = self.with_priority("stress-long-names.json", "balanced", roof=2016)
        pc = self.with_priority("stress-long-names.json", "protect_cash", roof=2016)
        self.assertIsNone(bal["promoted"])
        self.assertEqual((pc["promoted"], pc["framing"]), ("lower_cost", "cash_first"))
        lvl = pc["B"]["competition"]["level"]
        self.assertGreaterEqual(strategy.BAND_RANK[pc["bands"]["recommended"][lvl][0]], strategy.BAND_RANK["comp"])
        self.assertLess(pc["cash"]["recommended"]["worst"], bal["cash"]["recommended"]["worst"])

    def test_overrides_turn_the_choice_off(self):
        for p in strategy.BUYER_PRIORITIES:
            d = fixture("minimal.json")
            d.update(buyer_priority=p, overrides={"inspection_days": 10})
            self.assertIsNone(run(d)["promoted"], p)

    def test_unknown_categories_stop_naming_every_choice(self):
        for field, change, allowed in (("competition.level", {"competition": {"level": 5}}, ("0", "1", "2", "3")),
                                       ("competition.level", {"competition": {"level": "2"}}, ("0", "1", "2", "3")),
                                       ("buyer_priority", {"buyer_priority": "aggressive"}, strategy.BUYER_PRIORITIES)):
            with self.subTest(field=field, change=change):
                d = fixture("minimal.json")
                d.update(change)
                with self.assertRaises(strategy.oe.OfferError) as e:
                    run(d)
                msg = str(e.exception)
                self.assertIn(field + ":", msg)
                for a in allowed:
                    self.assertIn(a, msg)


class Escalation(unittest.TestCase):
    def setUp(self):
        d = fixture("texas-cma-escalation.json")
        d["cma"]["offer_plan"]["walk_away"] = 650000
        d["overrides"] = {"price": 632000}
        self.r = run(d)

    def test_cap_is_funded_and_written_in_the_letters(self):
        """The cap stays at or below the walk-away, its gap is measured from the range's top, the cash at the cap keeps
        the reserve, and the worksheet's letters cover the cap."""
        e = self.r["terms"]["recommended"]["escalation"]
        self.assertLessEqual(e["cap"], 650000)
        self.assertEqual(e["gap_at_cap"], e["cap"] - 632000)
        self.assertEqual(self.r["cash_at_cap"]["gap"], e["gap_at_cap"])
        self.assertGreaterEqual(self.r["cash_at_cap"]["reserve"], 15000)
        self.assertIn(strategy.money(e["cap"]), json.dumps(strategy.worksheet(self.r)))

    def test_gap_written_at_the_cap_and_variants_are_one_buyer(self):
        """An escalating offer above the range writes its gap at the cap on AGA-1. Scoring two variants together
        doesn't change either one's score or escalate one against the other."""
        r = run(copy.deepcopy(GAP))
        rec = r["terms"]["recommended"]
        self.assertEqual(rec["appraisal_gap"], rec["escalation"]["gap_at_cap"])
        self.assertEqual(r["O"]["recommended"]["appraisal_form"], "aga")
        _, alone = strategy.run_engine(r["B"], r["costs"], [("recommended", rec)])
        _, both = strategy.run_engine(r["B"], r["costs"], [("recommended", rec), ("stronger", dict(rec, price=rec["price"] + 5000))])
        self.assertEqual(both["recommended"]["score"]["total"], alone["recommended"]["score"]["total"])
        self.assertFalse(both["recommended"]["escalated"])

    def test_no_escalation_names_the_max_and_the_gap(self):
        d = fixture("texas-cma-escalation.json")
        B, costs = strategy.prepare(strategy.apply_cma(d, strategy.load_cma(d)), strategy.oe.Assume())
        t, why = strategy.build_offer(B, costs)
        self.assertNotIn("escalation", t)  # the value-range top is the CMA's walk-away
        self.assertEqual((why["escalation"]["key"], why["escalation"]["max"]), ("why_esc_walk", "$640,000"))  # the buyer's max
        self.assertIn("$8,000", strategy.why_text(why["escalation"]))  # what a price at the max would put above the range


class AppraisalGap(unittest.TestCase):
    def test_pushback_row_only_above_the_range(self):
        r = analyze("one-competing-reach.json")
        self.assertLessEqual(r["terms"]["recommended"]["price"], r["B"]["value"]["cma_high"])
        self.assertNotIn("Appraisal Gap Coverage", [p["term"] for p in strategy.result(r)["pushback"]])
        r["B"]["value"]["cma_high"] = r["terms"]["recommended"]["price"] - 5000  # the offer now sits above the range
        self.assertIn("Appraisal Gap Coverage", [p["term"] for p in strategy.pushback(r)])

    def test_no_cma_keeps_list_and_asks_competition_and_range_first(self):
        r = analyze("minimal.json")
        self.assertEqual(r["terms"]["recommended"]["price"], r["B"]["property"]["list_price"])
        self.assertEqual(to_confirm_fields(r)[:2], ["level", "cma_low / cma_high"])

    def test_protection_windows(self):
        """Rider F's window ends before the deposit is at risk: no protection to closing, but the cell names a date.
        FHA's escape clause runs to closing (low appraisal only), after the deposit is at risk."""
        r = analyze("one-competing-reach.json")
        o = r["O"]["recommended"]
        self.assertIsNone(strategy.appraisal_until(o, r["B"], r["costs"]))
        self.assertNotIn(strategy.appraisal_protection(o, r["B"], r["costs"]), ("", "—", None))
        r = analyze("fha-competitive.json")
        o, t = r["O"]["recommended"], r["terms"]["recommended"]
        first, until = strategy.deposit_risk(o)
        self.assertEqual((first - r["B"]["effective_date"]).days, max(t["inspection_days"], t["loan_approval_days"]))
        self.assertEqual(until, o["firm_date"])  # the escape clause runs to closing, for a low appraisal only

    def test_downside_label_names_only_what_applies(self):
        self.assertNotIn("Appraisal", strategy.downside_label(cypress()["O"]))  # below the range: inspection only
        above = {"recommended": {"price": 380000, "downside_price": 372000, "repair_reserve": 2500}}
        self.assertIn("Appraisal", strategy.downside_label(above))
        self.assertIn("Inspection", strategy.downside_label(above))
        above["recommended"]["repair_reserve"] = 0
        self.assertNotIn("Inspection", strategy.downside_label(above))


class Dates(unittest.TestCase):
    def test_dates_count_from_the_expected_acceptance(self):
        """The day after Wed Sep 23 has the Fri Sep 25 deadline; acceptance is the next business day, Mon Sep 28, and a
        35-day close is 35 days after it. A given acceptance date wins; a weekday day after stays."""
        r = run(copy.deepcopy(GAP))
        self.assertEqual(str(r["B"]["effective_date"]), "2026-09-28")
        self.assertEqual(r["O"]["recommended"]["close_days"], r["terms"]["recommended"]["closing_days"])
        rows = {x["field"]: x["entry"] for x in strategy.worksheet(r)["rows"]}
        self.assertIn("September 28, 2026", rows["Time for Acceptance"])
        d = copy.deepcopy(GAP)
        d["expected_effective_date"] = "2026-10-01"
        self.assertEqual(str(run(d)["B"]["effective_date"]), "2026-10-01")
        d = fixture("kestrel-v5.json")
        d["analysis_date"] = "2026-09-29"
        self.assertEqual(run(d)["B"]["effective_date"], strategy.date(2026, 9, 30))
        self.assertEqual(strategy.deadline_date("Fri Sep 25 · 5 PM", strategy._d("2026-09-23")), strategy._d("2026-09-25"))

    def test_deadline_formats(self):
        today = strategy.date(2026, 9, 26)
        for given in ("2026-10-02 18:00", "Fri Oct 2 · 6 PM", "Oct 2 6pm"):
            self.assertEqual(strategy.deadline_iso(given, today), "2026-10-02 18:00", given)
        self.assertEqual(strategy.deadline_text("2026-10-03 17:00", today, "long"), "October 3, 2026, 5:00 PM")
        self.assertEqual(strategy.deadline_text("when the seller decides", today), "when the seller decides")
        d = fixture("fha-competitive.json")
        d["competition"]["deadline"] = "2026-09-25 17:00"
        self.assertEqual(strategy.summary(run(d))["submit_by"], strategy.fmt.when("2026-09-25 17:00", "deadline"))
        sat = strategy.date(2026, 9, 26)  # a weekday deadline is the next such day
        self.assertEqual(strategy.weekday_date("Friday 5pm", sat), (strategy.date(2026, 10, 2), (17, 0)))
        self.assertEqual(strategy.weekday_date("Mon 17:30", sat), (strategy.date(2026, 9, 28), (17, 30)))
        self.assertIsNone(strategy.weekday_date("Fri Sep 25 · 5 PM", sat))  # a full date is used as given
        d = fixture("fha-competitive.json")
        d["analysis_date"], d["competition"]["deadline"] = "2026-09-26", "Friday 5pm"
        r = run(d)
        self.assertEqual(r["B"]["competition"]["deadline"], "2026-10-02 17:00")
        self.assertEqual(r["B"]["effective_date"], strategy.date(2026, 10, 5))  # Saturday moves to Monday
        self.assertEqual(to_confirm_fields(r)[0], "deadline")  # asked first: it may already have passed
        d["analysis_date"] = "2026-09-29"  # Tuesday: Friday is 3 days out, no question
        self.assertNotIn("deadline", fields(run(d)))

    def test_closing_and_deposit_dates_follow_business_days(self):
        r = run(gatlin())
        eff = r["B"]["effective_date"]
        for k, t in r["terms"].items():
            self.assertTrue(strategy.dates.is_business_day(eff + strategy.timedelta(days=t["closing_days"])), k)
        self.assertNotEqual(eff + strategy.timedelta(days=r["terms"]["lower_cost"]["closing_days"]),
                            strategy.date(2026, 11, 11))  # Veterans Day
        r = analyze("minimal.json")  # FAR/BAR: a period ending on a weekend rolls to the next business day
        d, note = strategy.risk_after(r["O"]["recommended"], r["costs"])
        self.assertTrue(strategy.dates.is_business_day(d))
        self.assertIsNotNone(note)
        d = fixture("texas-cma-escalation.json")  # no built-in rule: the date stays, with a note to check
        d["expected_effective_date"] = "2026-09-26"
        r = run(d)
        d, note = strategy.risk_after(r["O"]["recommended"], r["costs"])
        self.assertFalse(strategy.dates.is_business_day(d))
        self.assertIsNotNone(note)
        r = analyze("texas-cma-escalation.json")  # the other contract's deposit-risk date is asked to confirm, once
        self.assertEqual(r["O"]["recommended"]["contract_form"], strategy.cf.OTHER)
        self.assertIn("deposit_risk", fields(r))
        fl = analyze("fha-competitive.json")
        self.assertIsNone(strategy.cf.term_words(fl["O"]["recommended"]["contract_form"])["deposit_risk_confirm"])


class Taxes(unittest.TestCase):
    def test_millage_and_county_from_the_address(self):
        d = fixture("fha-competitive.json")
        d["costs"].pop("total_mills"), d["costs"].pop("school_mills"), d["costs"].pop("homestead")
        r = run(d)
        self.assertEqual(r["B"]["costs"]["total_mills"], 18.1808)  # Casselberry, from the address
        self.assertTrue({"total_mills", "homestead"} <= {a["field"] for a in r["assumptions"]})
        r = analyze("minimal.json")  # "..., Orlando, FL 32806" with no county
        self.assertEqual(r["B"]["property"]["county"], "Orange")
        self.assertEqual(r["B"]["costs"]["total_mills"], 18.1386)  # Orlando spans two districts: the higher one
        d = fixture("minimal.json")
        d["property"]["address"] = "10 Test St, Miami, FL 33130"  # no built-in district
        r = run(d)
        self.assertIsNone(r["B"]["property"].get("county"))
        self.assertIn("property_tax", [a["field"] for a in r["assumptions"] if a["scope"] == "costs"])

    def test_one_tax_rate_for_payment_and_proration(self):
        d = fixture("texas-cma-escalation.json")
        d["costs"] = {"rate": 6.4, "insurance_annual": 3900, "tax_rate": 0.0198}
        r = run(d)
        self.assertEqual(r["R"]["listing"]["annual_tax"], round(610000 * 0.0198))  # not the national 1.1%
        scoped = {(a["scope"], a["field"]): a for a in r["assumptions"]}
        self.assertIn(("property", "annual_tax"), scoped)
        self.assertNotIn(("listing", "annual_tax"), scoped)
        self.assertEqual([x["value"] for x in r["assumptions"] if x["field"] == "homestead"], ["as given"])
        d["cma"]["subject"]["annual_tax"] = 9000  # a seller's bill that was given still wins
        self.assertEqual(run(d)["R"]["listing"]["annual_tax"], 9000)

    def test_handoff_millage_and_a_cma_for_another_home(self):
        d = fixture("texas-cma-escalation.json")
        d["costs"].pop("total_mills")
        d["cma"]["subject"].update(total_mills=21.4, school_mills=9.1, homestead=True)
        self.assertEqual(run(d)["B"]["costs"]["total_mills"], 21.4)
        d = fixture("texas-cma-escalation.json")
        d["property"]["address"] = "12 Other Ln, Austin, TX 78757"
        d["cma"]["side"] = "seller"
        r = run(d)
        self.assertTrue({"cma_side", "cma_address"} <= set(fields(r, "high")))
        self.assertNotIn("cma_side", strategy.preliminary(r, r["missing"]))  # named in words, never a raw field name

    def test_estimated_seller_tax_is_an_assumption_not_a_label(self):
        d = fixture("fha-competitive.json")
        del d["property"]["annual_tax"]
        r = run(d)
        tax = [ln[1] for ln in r["O"]["recommended"]["ns"]["lines"] if ln[0] == "tax"]
        self.assertEqual(tax, ["Property Tax Proration (Jan 1 to Closing)"])
        self.assertIn("annual_tax", fields(r))

    def test_tax_bill_question_once_the_bills_are_out(self):
        """Before Nov 1 nobody can have paid this year's bill: a low-impact note; after, a medium question."""
        for date, impact in (("2026-09-26", "low"), ("2026-11-20", "med")):
            d = reach()
            d["costs"].pop("insurance_annual")
            d["buyer"].pop("insurance_quote")
            d["analysis_date"] = date
            a = next(x for x in run(d)["missing"] if x["field"] == "current_tax_bill_paid")
            self.assertEqual(a["impact"], impact, date)


class Insurance(unittest.TestCase):
    def test_estimate_from_the_year_built(self):
        """No premium: the shared estimate (age factor, Florida floor) at the price, recorded as an assumption."""
        for year, annual in ((1972, 4000), (2015, 3500)):
            r = run({"analysis_date": "2026-09-23", "buyer": {"cash_available": 40000},
                     "property": {"address": "1 Main St, Orlando, FL", "list_price": 300000, "year_built": year}})
            self.assertEqual(r["B"]["costs"]["insurance_annual"], annual, year)
            self.assertIn("insurance_annual", [a["field"] for a in r["assumptions"]])

    def test_quote_in_hand(self):
        """Only a quote in hand is scored: a planned quote is a to-do; a given premium is a quote unless marked
        otherwise, and then stays an assumption."""
        r = run(roofed(gatlin()))
        self.assertIsNone(r["promoted"])
        self.assertIsNone(r["terms"]["recommended"]["insurance_quote"])
        r = run(roofed(gatlin(insurance_quote="planned")))
        self.assertIsNone(r["promoted"])
        self.assertEqual(r["terms"]["recommended"]["insurance_quote"], "planned")
        d = gatlin()
        d["analysis_date"] = "2026-09-26"
        d["costs"] = {"insurance_annual": 3900}
        r = run(d)
        self.assertIs(r["terms"]["recommended"]["insurance_quote"], True)
        self.assertFalse(any("(H)" in x["rider"] for x in strategy.worksheet(r)["riders"]))
        d["buyer"]["insurance_quote"] = False  # an estimate the agent marks as not a quote stays a to-do
        self.assertIsNone(run(d)["terms"]["recommended"]["insurance_quote"])
        r = analyze("one-competing-reach.json")  # typed in with insurance_quote false: still an assumption
        self.assertIn("insurance_annual", fields(r))
        self.assertFalse(strategy.quote_in_hand(r["B"]["buyer"]))
        d = fixture("one-competing-reach.json")
        del d["buyer"]["insurance_quote"]
        self.assertNotIn("insurance_annual", fields(run(d)))

    def test_flood_and_cdd_in_the_payment(self):
        r = analyze("condo-flood.json")
        d = fixture("condo-flood.json")
        d["costs"].pop("flood_insurance_annual")
        d["property"].pop("cdd_annual")
        bare = run(d)
        for k in r["payment"]:
            self.assertEqual(r["payment"][k] - bare["payment"][k], 250)  # $1,800/yr flood + $1,200/yr CDD
        impact = {a["field"]: a["impact"] for a in bare["assumptions"]}
        self.assertEqual((impact["flood_insurance_annual"], impact["cdd_annual"]), ("med", "med"))  # zone AE
        self.assertNotIn("flood_insurance_annual", {a["field"] for a in r["assumptions"]})
        self.assertEqual(strategy.side_by_side(bare)[-1]["term"], strategy.L_["sbs_payment_no_flood"])
        self.assertEqual(strategy.side_by_side(r)[-1]["term"], strategy.L_["sbs_payment"])


class MarketRead(unittest.TestCase):
    def test_market_heat_and_area_read(self):
        cases = [
            (({"dom": 9}, {"median_dom": 34, "sale_to_list": 0.981}), "hot"),
            (({}, {}), "normal"),
            (({"price_cuts": 1, "dom": 3}, {"median_dom": 30}), "soft"),
            (({"price_cuts": 1}, {"months_supply": 1.4}), "normal"),  # a cut in a tight market isn't soft
            (({"price_cuts": 1}, {"months_supply": 4.2}), "soft"),
            (({"price_cuts": 1}, {}), "soft"),  # supply unknown: the cut still reads soft
            (({"price_cuts": 1, "dom": 78}, {"months_supply": 1.4, "median_dom": 23}), "stale"),  # this listing, not the market
            (({"price_cuts": 1, "dom": 78}, {"months_supply": 4.2, "median_dom": 23}), "soft"),
            (({"price_cuts": 2, "dom": 78}, {"months_supply": 1.4, "median_dom": 23}), "stale"),
        ]
        for (P, M), heat in cases:
            with self.subTest(P=P, M=M):
                self.assertEqual(strategy.market_heat(P, M)[0], heat)
        self.assertEqual(strategy.area_read({"months_supply": 4.2}), "balanced")
        self.assertEqual(strategy.area_read({"months_supply": 7.5}), "soft")
        self.assertEqual(strategy.area_read({"sale_to_list": 0.995}), "hot")
        self.assertIsNone(strategy.area_read({}))
        self.assertEqual(strategy.market_read({"property": {}, "market": {}}), ("—", None))

    def test_handoff_days_and_cuts_read_the_listing_apart_from_the_market(self):
        d = fixture("one-competing-reach.json")
        for k in ("dom", "price_cuts"):
            d["cma"]["subject"][k] = d["property"].pop(k)
        r = run(d)
        P = r["B"]["property"]
        self.assertEqual((P["dom"], P["price_cuts"]), (78, 2))
        self.assertEqual(r["B"]["competition"]["heat"], "stale")
        self.assertEqual(strategy.market_read(r["B"])[0], "Tight market, stale listing")
        cells = {c["label"]: c["value"] for c in strategy.snapshot(r["B"])["cells"]}
        self.assertEqual((cells["Days on Market"], cells["Median Days on Market"]), ("78", "23"))  # 23.0 prints whole
        d = fixture("kestrel-v5.json")  # inferred competition on a stale listing: still no competing offers
        d["competition"] = {}
        self.assertEqual(run(d)["B"]["competition"]["level"], 0)

    def test_handoff_market_facts(self):
        """Days on market aged from the handoff's date, the seller-paid stats, and the MLS."""
        d = fixture("texas-cma-escalation.json")
        del d["property"]["dom"]
        d["cma"]["subject"]["dom"] = 4
        d["analysis_date"] = "2026-09-26"  # handoff as of 9/22
        d["cma"]["market"].update({"share_with_seller_paid_costs_recent": 0.44, "median_seller_paid_recent": 6500})
        r = run(d)
        self.assertEqual(r["B"]["property"]["dom"], 8)
        self.assertEqual({a["field"]: a["value"] for a in r["missing"]}["dom"], 8)
        M = r["B"]["market"]
        self.assertEqual((M["share_with_seller_costs"], M["typical_seller_paid"]), (0.44, 6500))
        d = fixture("minimal.json")
        d["cma"] = {"handoff": "cma", "version": 1, "side": "buyer", "as_of": "2026-09-22",
                    "subject": {"address": d["property"]["address"], "list_price": d["property"]["list_price"]},
                    "value": {"low": 420000, "high": 440000, "midpoint": 430000}, "comps": [],
                    "market_profile": {"state": "FL", "mls": "Stellar"}}
        r = run(d)
        self.assertNotIn("mls_assumed", r["costs"].market.note_codes)
        self.assertEqual(r["B"]["property"]["mls"], "Stellar")


class Assumptions(unittest.TestCase):
    """What's assumed, its impact, and the order the questions are asked."""

    def test_preliminary_summary_and_assumed_max(self):
        r = analyze("minimal.json")
        s = strategy.result(r)["summary"]
        self.assertTrue(s["preliminary"])
        self.assertIn("financing", fields(r))
        self.assertNotIn("assumed", s["financing"])  # the loan type assumption is in the assumptions, once
        self.assertEqual(strategy.summary(analyze("cash.json"))["financing"], "Cash")
        r = run(gatlin())  # the assumed max is high impact and quoted
        self.assertIn("max_price", fields(r, "high"))
        self.assertIn(strategy.money(429000), strategy.preliminary(r, r["missing"]))  # the assumed max, so the reply never infers it

    def test_contract_form_is_high_impact_and_lender_box_pending(self):
        d = copy.deepcopy(GAP)
        d["worksheet"].pop("contract_form")
        d["buyer"]["lender_called"] = True
        r = run(d)
        self.assertEqual(next(a for a in r["assumptions"] if a["field"] == "contract_form")["impact"], "high")
        box = next(p for p in strategy.worksheet(r)["package"] if p["item"].startswith("Lender confirms"))
        self.assertEqual(box["status"], "Pending")

    def test_other_contract_questions_come_first(self):
        d = fixture("texas-cma-escalation.json")
        del d["worksheet"]["contract_name"]
        self.assertEqual(to_confirm_fields(run(d))[0], "contract_name")
        d["cma"]["offer_plan"]["walk_away"] = 640000  # the escalation question comes with an escalation
        d["overrides"] = {"inspection_days": 10}  # keeps the rule-built (escalating) offer from being softened
        r = run(d)
        self.assertTrue(r["terms"]["recommended"].get("escalation"))
        self.assertEqual(to_confirm_fields(r)[:2], ["contract_name", "escalation_accepted"])
        self.assertNotIn("contract_name", fields(analyze("fha-competitive.json")))

    def test_rate_and_payment_inputs(self):
        """A looked-up average that sets the price through the payment limit is high impact; a lender quote isn't
        asked; with no rate, the offline fallback is used and asked."""
        d = fixture("fha-competitive.json")
        d["costs"]["rate"], d["costs"]["rate_source"] = 7.0, "Freddie Mac weekly 30-year average, week of Sep 24, 2026"
        a = {x["field"]: x for x in run(d)["missing"]}
        self.assertEqual(a["rate_source"]["impact"], "high")
        self.assertNotIn("rate", a)
        d["costs"].pop("rate"), d["costs"].pop("rate_source"), d["costs"].pop("insurance_annual")
        a = {x["field"]: x for x in run(d)["missing"]}
        self.assertEqual((a["rate"]["value"], a["rate"]["impact"]), (strategy.DEFAULT_RATE, "high"))
        self.assertNotIn("rate_source", fields(analyze("one-competing-reach.json")))  # a lender quote
        d = fixture("one-competing-reach.json")
        d["costs"]["rate_source"] = "Freddie Mac weekly 30-year average, week of Sep 24, 2026"
        self.assertIn("rate_source", fields(run(d)))
        r = cypress()  # the payment inputs that set the price are high and asked right after the deadline
        a = {x["field"]: x for x in r["missing"]}
        self.assertEqual((a["rate_source"]["impact"], a["insurance_annual"]["impact"]), ("high", "high"))
        self.assertEqual(to_confirm_fields(r)[:3], ["deadline", "rate_source", "insurance_annual"])

    def test_nothing_assumed_no_line(self):
        r = copy.copy(analyze("kestrel-v5.json"))
        self.assertTrue(strategy.assumed_line(r))
        r["missing"] = []
        self.assertIsNone(strategy.assumed_line(r))


class ReplyLines(unittest.TestCase):
    def test_reply_lines_outside_the_cap(self):
        tx = fixture("texas-cma-escalation.json")
        r = run(copy.deepcopy(tx))  # highest and best, one flat number
        res = strategy.result(r)
        self.assertEqual([x["key"] for x in res["reply_lines"]],
                         ["flat_number", "contract_terms", "inspection_period", "assumptions"])
        self.assertIn(strategy.money(r["terms"]["recommended"]["price"]), res["reply_lines"][0]["text"])
        d = copy.deepcopy(tx)
        d["competition"]["note"] = "Listing agent: 6 offers in"
        self.assertEqual([x["key"] for x in strategy.result(run(d))["reply_lines"]],
                         ["contract_terms", "inspection_period", "assumptions"])
        d["competition"]["highest_and_best"] = True  # the field wins over the note
        self.assertIn("flat_number", [x["key"] for x in run(d)["reply_lines"]])
        d = copy.deepcopy(tx)
        d["cma"]["offer_plan"]["walk_away"], d["overrides"] = 640000, {"inspection_days": 10}  # escalating: no flat number
        r = run(d)
        self.assertTrue(r["terms"]["recommended"].get("escalation"))
        self.assertEqual([x["key"] for x in r["reply_lines"] if x["key"] != "tight_reserve"], ["contract_terms"])
        self.assertEqual([x["key"] for x in analyze("fha-competitive.json")["reply_lines"]],
                         ["tight_reserve", "higher_price"])

    def test_higher_price_inside_the_limits(self):
        """Below Strong, the report says what the highest price inside the buyer's own limits would do: that price is
        above the recommended one, inside every limit with $1,000 more breaking one (or the max), `lifts` follows the
        band ranks, and the line reaches the chat once and the PDF once."""
        seen = 0
        for name in sorted(os.listdir(FIXTURES)):
            r = analyze(name)
            hp, rec, lvl = r["higher_price"], r["terms"]["recommended"], r["B"]["competition"]["level"]
            if r["bands"]["recommended"][lvl][0] == "strong" or r["overrides"] or rec.get("escalation"):
                self.assertIsNone(hp, name)
                continue
            if hp is None:
                continue
            seen += 1
            B, costs = r["B"], r["costs"]
            self.assertGreater(hp["price"], rec["price"], name)
            self.assertTrue(strategy.within_limits(B, costs, dict(rec, price=hp["price"])), name)
            self.assertTrue(hp["price"] + 1000 > B["buyer"]["max_price"]
                            or not strategy.within_limits(B, costs, dict(rec, price=hp["price"] + 1000)), name)
            self.assertEqual(hp["lifts"], strategy.BAND_RANK[hp["band_key"]]
                             > strategy.BAND_RANK[r["bands"]["recommended"][lvl][0]], name)
            self.assertEqual([x["key"] for x in r["reply_lines"]].count("higher_price"), 1)
            self.assertEqual(buyer_render.options_html(strategy.result(r), {}).count(buyer_render.esc(hp["text"])), 1)
        self.assertTrue(seen)

    def test_rate_line_when_the_cma_used_another_rate(self):
        """With a CMA handoff whose payment used another rate, a reply line says which rate each report used; the same
        rate, or no rate in the handoff, adds none."""
        d = fixture("one-competing-reach.json")
        h = strategy.load_cma(d)
        if h is None:
            self.skipTest("fixture has no CMA handoff")
        keys = lambda h_: [x["key"] for x in strategy.analyze(d, cma=h_)["reply_lines"]]  # noqa: E731
        rate = strategy.analyze(d, cma=h)["B"]["costs"]["rate"]
        for cma_rate, want in ((rate + 0.5, True), (rate, False), (None, False)):
            h2 = copy.deepcopy(h)
            h2["subject"].pop("rate", None)
            if cma_rate is not None:
                h2["subject"]["rate"] = cma_rate
            self.assertEqual("rate_differs" in keys(h2), want, cma_rate)

    def test_option_period_is_a_default_to_confirm(self):
        r = analyze("texas-cma-escalation.json")
        self.assertIn("inspection_period", [x["key"] for x in r["reply_lines"]])
        self.assertIn("inspection_days", fields(r))
        d = fixture("texas-cma-escalation.json")
        d["overrides"] = {"inspection_days": 4}  # the agent set it: no longer a default
        r = run(d)
        self.assertNotIn("inspection_period", [x["key"] for x in r["reply_lines"]])
        self.assertNotIn("inspection_days", fields(r))
        self.assertNotIn("inspection_period", [x["key"] for x in analyze("fha-competitive.json")["reply_lines"]])

    def test_seller_flexible_close_is_chat_only(self):
        d = reach()
        self.assertNotIn("seller_timeline", [x["key"] for x in run(d)["reply_lines"]])
        d["property"]["seller_flexible_close"] = True
        r = run(d)
        self.assertIn("seller_timeline", [x["key"] for x in r["reply_lines"]])
        self.assertNotIn("flexible", json.dumps(strategy.result(r)["summary"]))

    def test_best_effort_note_is_chat_only(self):
        out = strategy.result(analyze("texas-cma-escalation.json"))
        self.assertEqual(out["support"], "best_effort")
        self.assertEqual(out["chat_notes"], [strategy.cf.BEST_EFFORT_OFFER_NOTE])
        self.assertNotIn(strategy.cf.BEST_EFFORT_OFFER_NOTE, json.dumps(out["worksheet"]))


if __name__ == "__main__":
    unittest.main()
