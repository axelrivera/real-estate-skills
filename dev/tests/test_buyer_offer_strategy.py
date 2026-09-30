"""Tests for skills/buyer-offer-strategy/scripts."""
import contextlib
import copy
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

strategy, buyer_render = load("buyer-offer-strategy", "strategy", "render")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def analyze(name, **kw):
    d = fixture(name)
    return strategy.analyze(d, cma=strategy.load_cma(d), **kw)


class MatchesPrototype(unittest.TestCase):
    """The prototype's FHA sample (2–3 competing offers). Its options, scores, cash, payments and bands on the
    unmodified fixture are pinned by golden (dev/golden/buyer-offer-strategy/fha-competitive.json)."""

    def test_seller_net_with_prototype_costs(self):
        d = fixture("fha-competitive.json")
        d["listing_side"]["listing_fee_pct"] = 0.03
        d["property"]["costs"] = {"title_fees": 645}
        r = strategy.analyze(d)
        # Audit: 4% early-payment discount in the proration (OFR-14), no tax in holding costs (OFR-13)
        # OFR-10: $363,000, the value midpoint. OFR-123: closing counts from Sep 26 (the day after the Sep 25 deadline),
        # so the tax proration runs three days longer than when it counted from the analysis date
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 331714)
        self.assertEqual(r["target"], 335580)  # the same closing, so the same three days of proration

    def test_market_defaults(self):
        r = analyze("fha-competitive.json")
        # No built-in listing fee (CORE-5), $1,145 title fees; OFR-10: priced at the value midpoint, $2,000 below list
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 333029)  # 2.5% listing fee assumed (5% total); OFR-123
        self.assertTrue(any(a["field"] == "listing_fee_pct" for a in r["R"]["assumptions"]))
        # CORE-16: Florida 2.5% + 0.5% prepaids, with the loan's note stamps (0.35%) and intangible tax (0.2%) itemized
        self.assertEqual(r["B"]["buyer"]["closing_cost_pct"], 0.03)
        self.assertEqual([t["rate"] for t in r["B"]["loan_taxes"]], [0.0035, 0.002])
        loan = 365000 * 0.965 * 1.0175  # FHA: the upfront premium is financed, so it's taxed too
        self.assertEqual(strategy.closing_costs(r["B"], 365000), round(365000 * 0.03 + round(loan * 0.0035) + round(loan * 0.002)))


class MissingData(unittest.TestCase):
    def test_minimal_is_preliminary(self):
        """The missing fields, financing and down payment on minimal.json are pinned by golden; the summary isn't."""
        s = strategy.summary(analyze("minimal.json"))
        self.assertTrue(s["preliminary"])
        self.assertIn("assumed", s["financing"])

    def test_not_enough_cash_says_so(self):
        d = fixture("fha-competitive.json")
        d["buyer"]["cash_available"] = 9000
        self.assertEqual(strategy.analyze(fixture("fha-competitive.json"))["constraints"], [])
        r = strategy.analyze(d)
        self.assertLess(r["cash"]["recommended"]["reserve"], 0)
        self.assertEqual(len(r["constraints"]), 1)  # the shortfall, said once
        self.assertNotIn("stronger", r["O"])

    def test_cash_buyer(self):
        """OFR-1: a cash buyer's 100% down passes the fraction check (golden runs cash.json, so a regression fails it);
        the summary and its terms read as cash, with no lender wording, which golden doesn't run."""
        s = strategy.summary(analyze("cash.json"))
        self.assertEqual(s["financing"], "Cash")

    def test_percent_down_still_refused(self):
        d = fixture("fha-competitive.json")
        d["buyer"]["down_pct"] = 3.5
        with self.assertRaises(strategy.oe.OfferError):
            strategy.analyze(d)

    def test_required(self):
        with self.assertRaises(strategy.oe.OfferError):
            strategy.analyze({"property": {"address": "x"}})


class EvalFindings(unittest.TestCase):
    def test_stronger_is_recommended_when_it_lifts_the_outlook_inside_limits(self):
        # OFR-18: only a quote in hand is scored, so the buyer here has one
        B = {"analysis_date": "2026-09-23", "property": {"address": "2716 Gatlin Ave, Orlando, FL", "list_price": 429000},
             "buyer": {"cash_available": 38000, "insurance_quote": True}}
        r = strategy.analyze(B)
        lvl = r["B"]["competition"]["level"]
        self.assertEqual(r["promoted"], "stronger")
        self.assertEqual(r["bands"]["recommended"][lvl][0], "strong")
        self.assertEqual(r["R"]["listing"]["state"], "FL")  # read from "Orlando, FL" without a ZIP
        self.assertIn("4-point", r["why"]["inspection_days"])

    def test_planned_insurance_quote_is_not_scored(self):
        """OFR-18: a quote the buyer plans to get is a to-do, not a point."""
        B = {"analysis_date": "2026-09-23", "property": {"address": "2716 Gatlin Ave, Orlando, FL", "list_price": 429000},
             "buyer": {"cash_available": 38000}}
        r = strategy.analyze(B)
        self.assertIsNone(r["promoted"])
        self.assertEqual(r["terms"]["recommended"]["insurance_quote"], "planned")
        self.assertIn("insurance quote", strategy.summary(r)["next_step"])

    def test_rate_written_as_fraction_is_refused(self):
        B = {"analysis_date": "2026-09-23", "property": {"address": "1 Main St, Orlando, FL", "list_price": 400000},
             "buyer": {"cash_available": 40000}, "costs": {"rate": 0.064}}
        with self.assertRaisesRegex(strategy.oe.OfferError, "percent"):
            strategy.analyze(B)


class HandoffAndOtherStates(unittest.TestCase):
    def test_handoff_seller_paid_stats_fill_the_market_table(self):
        # A buyer CMA's handoff names these share_with_seller_paid_costs_recent and median_seller_paid_recent (raw numbers).
        d = fixture("texas-cma-escalation.json")
        d["cma"]["market"].update({"share_with_seller_paid_costs_recent": 0.44, "median_seller_paid_recent": 6500})
        B = strategy.analyze(d, cma=strategy.load_cma(d))["B"]
        self.assertEqual((B["market"]["share_with_seller_costs"], B["market"]["typical_seller_paid"]), ("44%", "$6,500"))

    def test_handoff_file_via_cli(self):
        d = fixture("texas-cma-escalation.json")
        h = d.pop("cma")
        with tempfile.TemporaryDirectory() as tmp:
            bp, hp = os.path.join(tmp, "buyer.json"), os.path.join(tmp, "8104-Shoal-Creek-Blvd.cma.json")
            with open(bp, "w") as f:
                json.dump(d, f)
            with open(hp, "w") as f:
                json.dump(h, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = strategy.main([bp, "--cma", hp])
        res = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(res["value_range"], "$598,000–$632,000")
        self.assertEqual(res["market"]["median_adjusted"], "$618,500")

    def test_texas_worksheet_has_no_florida_forms(self):
        r = analyze("texas-cma-escalation.json")
        w = strategy.worksheet(r)
        text = json.dumps(w)
        for florida in ("FR/BAR", "Form Simplicity", "4-point", "Florida"):
            self.assertNotIn(florida, text)
        self.assertEqual(w["form_name"], "Sample Residential Purchase Agreement")
        self.assertTrue(all(row["para"] == "" for row in w["rows"]))
        self.assertIn("national estimate", json.dumps(r["missing"]))  # closing costs, not Florida's

    def test_florida_worksheet(self):
        w = strategy.worksheet(analyze("fha-competitive.json"))
        self.assertTrue(w["frbar"])
        self.assertEqual([x["rider"] for x in w["riders"]], ["FHA/VA Financing Rider (E)", "Homeowner's/Flood Insurance Rider (H)",
                                                         "Seller's Agreement with Respect to Buyer's Broker Compensation Rider (GG)"])
        deposit = next(r for r in w["rows"] if r["field"] == "Initial Deposit")
        self.assertIn("$11,000", deposit["entry"])
        self.assertIn("Inspection Period", [r["field"] for r in w["rows"]])  # Florida keeps its inspection period


class Pdf(unittest.TestCase):
    def test_options_html_is_buyer_side(self):
        r = analyze("fha-competitive.json")
        doc = buyer_render.options_html(r, {"name": "Jane Doe", "brokerage": "Sunshine Realty"}, sample=True)
        self.assertIn("--brand:#1A74AD", doc)  # buyer blue by default (the prototype used orange)
        self.assertNotIn("--brand:#C2410C", doc)
        self.assertIn("Buyer Side", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)

    def test_worksheet_never_shows_the_buyers_limits(self):
        r = analyze("fha-competitive.json")
        doc, _ = buyer_render.worksheet_html(r, {}, sample=False)
        for secret in ("$375,000", "$26,000", "$3,200"):
            self.assertNotIn(secret, doc)
        self.assertIn('<span class="fill">[from listing / tax record]</span>', doc)

    def test_option_choice(self):
        r = analyze("fha-competitive.json")
        _, w = buyer_render.worksheet_html(r, {}, sample=False, variant="lower_cost")
        self.assertEqual(w["price"], "$363,000")  # OFR-8: never above the recommended price (OFR-10: the midpoint)
        with self.assertRaises(strategy.oe.OfferError):
            strategy.worksheet(analyze("fha-competitive.json"), "nope")

    def test_renders_both_pdfs(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = buyer_render.main([os.path.join(FIXTURES, "fha-competitive.json"), "--out", tmp, "--format", "all"])
            self.assertEqual([os.path.basename(p) for p in paths],
                             ["1532-Cypress-Bend-Dr-Offer-Options.pdf", "1532-Cypress-Bend-Dr-Offer-Package.pdf"])
            for p in paths:
                with open(p, "rb") as f:
                    self.assertEqual(f.read(4), b"%PDF")


class FloodCddCondo(unittest.TestCase):
    """OFR-26, CMA-6, CMA-5: flood insurance and CDD are payment lines; condos get their documents and checks."""

    def test_flood_and_cdd_in_payment(self):
        r = analyze("condo-flood.json")
        d = fixture("condo-flood.json")
        d["costs"].pop("flood_insurance_annual")
        d["property"].pop("cdd_annual")
        bare = strategy.analyze(d, cma=strategy.load_cma(d))
        for k in r["payment"]:
            self.assertEqual(r["payment"][k] - bare["payment"][k], 250)  # $1,800/yr flood + $1,200/yr CDD
        fields = {a["field"]: a["impact"] for a in bare["assumptions"]}
        self.assertEqual(fields["flood_insurance_annual"], "med")  # zone AE: the lender requires it
        self.assertEqual(fields["cdd_annual"], "med")
        self.assertNotIn("flood_insurance_annual", {a["field"] for a in r["assumptions"]})

    def test_payment_label_without_quote(self):
        d = fixture("condo-flood.json")
        d["costs"].pop("flood_insurance_annual")
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        html = buyer_render.details(r, strategy.result(r))
        self.assertIn("Est. Monthly Payment (Before Flood Insurance)", html)

    def test_condo_documents_and_flood_disclosure(self):
        res = strategy.result(analyze("condo-flood.json"))
        text = json.dumps(res)
        self.assertIn("milestone inspection summary and SIRS", text)
        self.assertIn("s. 689.302", text)


class AuditPricing(unittest.TestCase):
    """OFR-7, OFR-8, OFR-11, OFR-30."""

    def only_offer(self, **buyer):
        return {"analysis_date": "2026-09-23",
                "property": {"address": "1 Main St, Orlando, FL", "state": "FL", "county": "Orange", "list_price": 400000},
                "value": {"cma_low": 420000, "cma_high": 440000}, "competition": {"level": 0},
                "buyer": {"financing": "conventional", "down_pct": 0.2, "cash_available": 150000, **buyer}}

    def test_only_offer_never_above_list(self):
        r = strategy.analyze(self.only_offer())
        self.assertEqual(r["terms"]["recommended"]["price"], 400000)

    def test_lower_cost_starts_from_the_agents_price(self):
        for price in (632000, 612000):
            d = fixture("texas-cma-escalation.json")
            d["overrides"] = {"price": price}
            r = strategy.analyze(d, cma=strategy.load_cma(d))
            self.assertEqual(r["terms"]["recommended"]["price"], price)  # the agent's choice stands (no OFR-9 swap)
            lc = r["terms"].get("lower_cost")
            if price == 632000:
                self.assertEqual(lc["price"], 615000)
                self.assertLess(r["cash"]["lower_cost"]["worst"], r["cash"]["recommended"]["worst"])
            elif lc:  # below the rules' own price, softening never raises it
                self.assertLessEqual(lc["price"], price)

    def test_option_that_saves_nothing_is_dropped(self):
        for name in ("fha-competitive.json", "texas-cma-escalation.json", "cash.json"):
            r = analyze(name)
            if "lower_cost" in r["terms"]:
                self.assertLess(r["cash"]["lower_cost"]["worst"], r["cash"]["recommended"]["worst"], name)

    def test_jumbo_and_fha_limits(self):
        d = self.only_offer(down_pct=0.05)
        d["property"].update(list_price=950000)
        d["value"] = {"cma_low": 930000, "cma_high": 980000}
        r = strategy.analyze(d)
        self.assertIn("loan_limit", [a["field"] for a in r["assumptions"]])
        self.assertIn("check the loan limit", r["limits"]["recommended"])
        d = self.only_offer(financing="fha", down_pct=0.035)
        d["property"].update(list_price=700000)
        d["value"] = {"cma_low": 690000, "cma_high": 720000}
        r = strategy.analyze(d)
        why = next(a["why"] for a in r["assumptions"] if a["field"] == "loan_limit")
        self.assertIn("$541,287", why)  # the 2026 FHA floor


class FrbarGap(unittest.TestCase):
    def test_conventional_gap_uses_aga_not_rider_f(self):
        """AGA-1 is for conventional or cash offers and isn't used with the Appraisal Contingency Rider (F)."""
        d = fixture("fha-competitive.json")
        d["buyer"].update(financing="conventional", down_pct=0.2)
        d["overrides"] = {"appraisal_gap": 10000}
        w = strategy.worksheet(strategy.analyze(d))
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn("Appraisal Gap Addendum (AGA-1)", riders)
        self.assertNotIn("Appraisal Contingency Rider (F)", riders)
        self.assertNotIn("Appraisal Gap", [c["title"] for c in w["clauses"]])


class OtherContractWorksheet(unittest.TestCase):
    """Only FR/BAR is built in: any other contract gets the generic entries by name, never another state's form rules."""

    def test_other_contract_rows_and_riders_are_generic(self):
        d = fixture("texas-cma-escalation.json")
        w = strategy.worksheet(strategy.analyze(d, cma=strategy.load_cma(d)))
        fields = [r["field"] for r in w["rows"]]
        self.assertIn("Inspection Period", fields)
        self.assertIn("Initial Deposit", fields)
        self.assertNotIn("Option Fee", fields)
        self.assertEqual(next(r for r in w["rows"] if r["field"] == "Initial Deposit")["note"], "Due date per the contract")
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn("Appraisal Contingency Addendum", riders)
        self.assertFalse(any("TREC" in x or "Third Party" in x for x in riders))

    def test_best_effort_line_is_chat_only(self):
        d = fixture("texas-cma-escalation.json")
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        out = strategy.result(r)
        self.assertEqual(out["support"], "best_effort")
        self.assertNotIn("fully supported", json.dumps(out["worksheet"]))

    def test_fha_on_other_contract(self):
        d = fixture("texas-cma-escalation.json")
        d["buyer"].update(financing="fha", down_pct=0.035)
        w = strategy.worksheet(strategy.analyze(d, cma=strategy.load_cma(d)))
        self.assertIn("FHA/VA Financing Addendum", [r["rider"] for r in w["riders"]])


class InsuranceEstimate(unittest.TestCase):
    def test_older_home_estimate_and_floor(self):
        """CORE-29: the estimate scales with age, has Florida's floor, and says to get a quote."""
        B = {"analysis_date": "2026-09-23", "property": {"address": "1 Main St, Orlando, FL", "list_price": 300000, "year_built": 1972},
             "buyer": {"cash_available": 40000}}
        r = strategy.analyze(B)
        self.assertEqual(r["B"]["costs"]["insurance_annual"], 4000)  # 0.9% x $300,000 x 1.5 = $4,050, to the $100
        B["property"]["year_built"] = 2015
        r = strategy.analyze(B)
        self.assertEqual(r["B"]["costs"]["insurance_annual"], 3500)  # $2,700 is under the Florida floor
        why = next(a["why"] for a in r["assumptions"] if a["field"] == "insurance_annual")
        self.assertIn("get a quote", why)


class AuditEscalationCap(unittest.TestCase):
    """Audit 2026-09-23: OFR-5 (cap vs. walk-away and the appraisal line), OFR-27 (letters at the cap)."""

    def setUp(self):
        d = fixture("texas-cma-escalation.json")
        d["cma"]["offer_plan"]["walk_away"] = 650000
        d["overrides"] = {"price": 632000}  # the agent chose the fuller offer, so OFR-9 doesn't swap in a cheaper one
        self.r = strategy.analyze(d, cma=strategy.load_cma(d))

    def test_cap_is_funded_from_the_same_risk_line(self):
        e = self.r["terms"]["recommended"]["escalation"]
        self.assertLessEqual(e["cap"], 650000)
        self.assertEqual(e["gap_at_cap"], e["cap"] - 632000)  # above the CMA high, the listing side's risk line
        cc = self.r["cash_at_cap"]
        self.assertEqual(cc["gap"], e["gap_at_cap"])
        self.assertGreaterEqual(cc["reserve"], 15000)
        self.assertIn("above the value range", self.r["why"]["escalation"])
        self.assertNotIn("appraisal can support", self.r["why"]["escalation"])

    def test_letters_cover_the_cap(self):
        text = json.dumps(strategy.worksheet(self.r))
        self.assertIn("$637,000", text)
        self.assertIn("escalation cap", text)
        self.assertIn("(at the escalation cap)", text)


class AuditBuyerBrokerShortfall(unittest.TestCase):
    def test_shortfall_in_cash_to_close(self):
        """CMA-4: a 3% agreement with the seller paying 2.5% leaves 0.5% for the buyer, counted in the limits."""
        d = fixture("fha-competitive.json")
        d["buyer"]["buyer_broker_agreement_pct"] = 0.03
        r = strategy.analyze(d)
        c = r["cash"]["recommended"]
        self.assertEqual(c["bb_short"], 1815)  # 0.5% of $363,000 (OFR-10 prices at the value midpoint)
        self.assertEqual(c["to_close"], c["down"] + c["cc"] + c["conc"] + 1815)
        doc = buyer_render.options_html(r, {"name": None, "brokerage": None, "brand": {}}, False)
        self.assertIn("Broker Fee (Not Paid by Seller)", doc)
        self.assertFalse(any(a["field"] == "buyer_broker_agreement_pct" for a in r["missing"]))


class Audit20260929(unittest.TestCase):
    """Fixes from the 2026-09-29 audit (docs/audits/2026-09-29.md)."""

    GAP = {"analysis_date": "2026-09-23",
           "property": {"address": "100 Test Rd, Sanford, FL 32771", "county": "Seminole", "list_price": 400000,
                        "year_built": 2012},
           "value": {"cma_low": 380000, "cma_high": 398000},
           "competition": {"level": 3, "deadline": "2026-09-25 17:00"},
           "buyer": {"financing": "conventional", "down_pct": 0.2, "cash_available": 140000, "max_price": 420000,
                     "reserve_floor": 5000},
           "worksheet": {"contract_form": "as_is"}}

    def test_variants_are_one_buyer(self):  # OFR-101
        r = strategy.analyze(copy.deepcopy(self.GAP))
        rec = r["terms"]["recommended"]
        self.assertIn("escalation", rec)
        _, alone = strategy.run_engine(r["B"], r["costs"], [("recommended", rec)])
        _, both = strategy.run_engine(r["B"], r["costs"], [("recommended", rec), ("stronger", dict(rec, price=rec["price"] + 5000))])
        self.assertEqual(both["recommended"]["score"]["total"], alone["recommended"]["score"]["total"])
        self.assertFalse(both["recommended"]["escalated"])

    def test_escalation_gap_is_written_at_the_cap(self):  # OFR-105
        r = strategy.analyze(copy.deepcopy(self.GAP))
        rec = r["terms"]["recommended"]
        self.assertEqual(rec["appraisal_gap"], rec["escalation"]["gap_at_cap"])
        self.assertEqual(r["O"]["recommended"]["appraisal_form"], "aga")
        self.assertNotIn("rises with the price", json.dumps(strategy.worksheet(r)))

    def test_dates_count_from_the_expected_acceptance(self):  # OFR-123
        r = strategy.analyze(copy.deepcopy(self.GAP))
        self.assertEqual(str(r["B"]["effective_date"]), "2026-09-26")
        o, t = r["O"]["recommended"], r["terms"]["recommended"]
        self.assertEqual(o["close_days"], t["closing_days"])  # a 35-day close is 35 days after acceptance
        rows = {x["field"]: x["entry"] for x in strategy.worksheet(r)["rows"]}
        self.assertIn("September 26, 2026", rows["Time for Acceptance"])
        d = copy.deepcopy(self.GAP)
        d["expected_effective_date"] = "2026-10-01"
        self.assertEqual(str(strategy.analyze(d)["B"]["effective_date"]), "2026-10-01")
        self.assertEqual(strategy.deadline_date("Fri Sep 25 · 5 PM", strategy._d("2026-09-23")), strategy._d("2026-09-25"))

    def test_city_millage_and_homestead(self):  # OFR-124
        d = fixture("fha-competitive.json")
        d["costs"].pop("total_mills"), d["costs"].pop("school_mills"), d["costs"].pop("homestead")
        r = strategy.analyze(d)
        self.assertEqual(r["B"]["costs"]["total_mills"], 18.1808)  # Casselberry, from the address
        fields = {a["field"] for a in r["assumptions"]}
        self.assertTrue({"total_mills", "homestead"} <= fields)

    def test_plain_words_and_the_agents_boxes(self):  # OFR-126, ENG-12
        d = copy.deepcopy(self.GAP)
        d["worksheet"].pop("contract_form")
        d["buyer"]["lender_called"] = True
        r = strategy.analyze(d)
        form = next(a for a in r["assumptions"] if a["field"] == "contract_form")
        self.assertEqual(form["impact"], "high")
        self.assertFalse([a for a in r["assumptions"] if "re-run" in a["why"] or "worksheet." in a["why"]])
        box = next(p for p in strategy.worksheet(r)["package"] if p["item"].startswith("Lender confirms"))
        self.assertEqual(box["status"], "Pending")

    def test_usda_gap_isnt_written_on_aga(self):  # ENG-10, OFR-104
        d = copy.deepcopy(self.GAP)
        d["buyer"].update(financing="usda", down_pct=0)
        d["overrides"] = {"price": 400000, "appraisal_gap": 5000}
        r = strategy.analyze(d)
        self.assertNotEqual(r["O"]["recommended"]["appraisal_form"], "aga")
        w = strategy.worksheet(r)
        self.assertFalse([x for x in w["riders"] if "AGA-1" in x["rider"]])
        self.assertIn("Appraisal Gap", [c["title"] for c in w["clauses"]])

    def test_stronger_names_only_what_it_raised(self):  # CMA-103
        self.assertEqual(strategy.raised({"deposit": 12000, "appraisal_gap": 0}, {"deposit": 8000, "appraisal_gap": 0}), "deposit")
        why = strategy.promote_why({}, {}, "stronger", {"price": 400000, "deposit": 12000, "appraisal_gap": 0},
                                   {"deposit": 8000, "appraisal_gap": 0})
        self.assertNotIn("appraisal_gap", why)

    def test_handoff_tax_and_address(self):  # CMA-111, CMA-102, CMA-101
        d = fixture("texas-cma-escalation.json")
        d["costs"].pop("total_mills")
        d["cma"]["subject"].update(total_mills=21.4, school_mills=9.1, homestead=True)
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertEqual(r["B"]["costs"]["total_mills"], 21.4)
        d = fixture("texas-cma-escalation.json")
        d["property"]["address"] = "12 Other Ln, Austin, TX 78757"
        d["cma"]["side"] = "seller"
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        text = strategy.preliminary(r)
        self.assertIn("a CMA for this property", text)
        self.assertIn("a buyer-side CMA", text)
        self.assertNotIn("cma side", text)


if __name__ == "__main__":
    unittest.main()
