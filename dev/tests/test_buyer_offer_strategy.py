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
        self.assertIsNone(r["terms"]["recommended"]["insurance_quote"])  # OFR-216: no quote, and none said to be planned
        self.assertIn("insurance quote", strategy.summary(r)["next_step"])
        B["buyer"]["insurance_quote"] = "planned"
        r = strategy.analyze(B)
        self.assertIsNone(r["promoted"])
        self.assertEqual(r["terms"]["recommended"]["insurance_quote"], "planned")

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

    def test_page_one_fits_every_fixture(self):
        # OFR-317: with one option, the exposure labels squeezed to a word per line and page 1 overflowed
        for name in sorted(os.listdir(FIXTURES)):
            err = io.StringIO()
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
                buyer_render.main([os.path.join(FIXTURES, name), "--out", tmp, "--format", "options"])
            self.assertNotIn("overflows", err.getvalue(), name)


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
        words = strategy.cf.term_words(strategy.cf.OTHER)  # OFR-234: generic words, never FR/BAR's
        self.assertIn(words["inspection_label"], fields)
        self.assertNotIn("Inspection Period", fields)
        self.assertIn("Initial Deposit", fields)
        self.assertNotIn("Option Fee", fields)
        self.assertEqual(next(r for r in w["rows"] if r["field"] == "Initial Deposit")["note"], "Due date per the contract")
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn(words["appraisal_addendum"], riders)
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


class Audit20260929Second(unittest.TestCase):
    """Second-pass fixes from the 2026-09-29 audit (eval iteration 3): OFR-201 to OFR-213."""

    def fields(self, r):
        return {(a["scope"], a["field"]): a for a in r["assumptions"]}

    def test_one_tax_rate_for_payment_and_proration(self):  # OFR-201
        d = fixture("texas-cma-escalation.json")
        d["costs"] = {"rate": 6.4, "insurance_annual": 3900, "tax_rate": 0.0198}
        r = analyze_data(d)
        self.assertEqual(r["R"]["listing"]["annual_tax"], round(610000 * 0.0198))  # not the national 1.1%
        self.assertIn(("property", "annual_tax"), self.fields(r))
        self.assertNotIn(("listing", "annual_tax"), self.fields(r))
        # a seller's bill that was given still wins
        d["cma"]["subject"]["annual_tax"] = 9000
        self.assertEqual(analyze_data(d)["R"]["listing"]["annual_tax"], 9000)

    def test_iso_deadline_is_formatted(self):  # OFR-202
        self.assertEqual(strategy.deadline_label("2026-10-02 18:00"), "Fri Oct 2 · 6 PM")
        self.assertEqual(strategy.deadline_label("2026-10-02 17:30"), "Fri Oct 2 · 5:30 PM")
        self.assertEqual(strategy.deadline_label("2026-10-03 17:00", long=True), "October 3, 2026, 5:00 PM")
        self.assertEqual(strategy.deadline_label("Fri Oct 2 · 6 PM"), "Fri Oct 2 · 6 PM")
        d = fixture("fha-competitive.json")
        d["competition"]["deadline"] = "2026-09-25 17:00"
        s = strategy.summary(strategy.analyze(d))
        self.assertEqual(s["submit_by"], "Fri Sep 25 · 5 PM")
        self.assertNotIn("2026-09-25", s["next_step"])

    def test_chat_note_prints_once_per_run(self):  # OFR-203
        d = fixture("texas-cma-escalation.json")  # another contract: one best-effort line for chat
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buyer.json")
            with open(path, "w") as f:
                json.dump(d, f)
            err = io.StringIO()
            real = buyer_render.render.html_to_pdf
            buyer_render.render.html_to_pdf = lambda *a, **k: 0
            try:
                with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                    buyer_render.main([path, "--format", "all", "--out", tmp])
            finally:
                buyer_render.render.html_to_pdf = real
        self.assertEqual(err.getvalue().count("chat only, never on the report"), 1)

    def test_no_escalation_names_the_max_and_the_gap(self):  # OFR-205
        d = fixture("texas-cma-escalation.json")
        A = strategy.oe.Assume()
        B, costs = strategy.prepare(strategy.apply_cma(d, strategy.load_cma(d)), A)
        t, why = strategy.build_offer(B, costs)
        self.assertNotIn("escalation", t)  # the value-range top is the CMA's walk-away
        self.assertIn("$640,000", why["escalation"])  # the buyer's max
        self.assertIn("$8,000", why["escalation"])  # what a price at the max would put above the range

    def test_missing_options_say_why(self):  # OFR-205, OFR-208
        r = analyze("fha-competitive.json")
        self.assertNotIn("stronger", r["terms"])
        s = strategy.summary(r)
        self.assertEqual([a["key"] for a in s["absent"]], ["stronger"])
        self.assertEqual(s["options_title"], "Your Options")
        self.assertTrue(s["next_step"].startswith("Pick an option"))
        d = fixture("fha-competitive.json")
        d["buyer"]["max_payment"] = 3100  # a lower payment cap: the softer offer would be Unlikely, one option left
        r = strategy.analyze(d)
        s = strategy.summary(r)
        self.assertEqual(list(r["terms"]), ["recommended"])
        self.assertEqual({a["key"] for a in s["absent"]}, {"stronger", "lower_cost"})
        self.assertEqual(s["options_title"], "Your Offer")
        self.assertNotIn("Pick an option", s["next_step"])

    def test_worksheet_nits(self):  # OFR-206, OFR-209
        r = analyze("fha-competitive.json")
        W = strategy.worksheet(r)
        items = {x["group"] + ":" + x["item"]: x["status"] for x in W["package"]}
        self.assertEqual(items["Do Not Include:Personal letter, photos or buyer background"], "Never")
        self.assertIn("Buyer Docs:Proof of funds for deposit and closing costs", items)  # no gap, so no gap in the line
        rider_e = next(x for x in W["riders"] if "(E)" in x["rider"])
        self.assertIn("Para. 2", rider_e["inputs"])
        self.assertIn("[", rider_e["inputs"])  # the cap has no default: a red blank
        self.assertEqual(buyer_render.sentence("buyer has insurance quote"), "Buyer has insurance quote")

    def test_deposit_risk_before_the_fha_escape_clause(self):  # OFR-210
        r = analyze("fha-competitive.json")
        o, t = r["O"]["recommended"], r["terms"]["recommended"]
        first, until = strategy.deposit_risk(o)
        self.assertEqual((first - r["B"]["effective_date"]).days, max(t["inspection_days"], t["loan_approval_days"]))
        self.assertEqual(until, o["firm_date"])  # the escape clause runs to closing, for a low appraisal only
        rows = dict(strategy.summary(r)["exposure"])
        self.assertTrue(rows["Low-Appraisal Protection"].startswith("To closing"))

    def test_handoff_mls_is_read(self):  # OFR-211
        d = fixture("minimal.json")
        d["cma"] = {"handoff": "cma", "version": 1, "side": "buyer", "as_of": "2026-09-22",
                    "subject": {"address": d["property"]["address"], "list_price": d["property"]["list_price"]},
                    "value": {"low": 420000, "high": 440000, "midpoint": 430000}, "comps": [],
                    "market_profile": {"state": "FL", "mls": "Stellar"}}
        r = analyze_data(d)
        self.assertNotIn("mls_assumed", r["costs"].market.note_codes)
        self.assertEqual(r["B"]["property"]["mls"], "Stellar")

    def test_no_cma_keeps_list_and_asks_the_gap(self):  # OFR-212
        r = analyze("minimal.json")
        t = r["terms"]["recommended"]
        self.assertEqual(t["price"], r["B"]["property"]["list_price"])
        self.assertNotIn("At value", r["why"]["price"])
        self.assertIn("ask the buyer", r["why"]["appraisal_gap"])
        # the quick answer's one question: the inferred competition read first, then the rest by impact
        to_confirm = strategy.result(r)["to_confirm"]
        self.assertTrue(to_confirm[0].startswith("Competition unknown"))
        self.assertTrue(to_confirm[1].startswith("No value range"))

    def test_county_from_the_city(self):  # OFR-213
        r = analyze("minimal.json")  # "…, Orlando, FL 32806" with no county
        self.assertEqual(r["B"]["property"]["county"], "Orange")
        self.assertEqual(r["B"]["costs"]["total_mills"], 18.1386)  # Orlando spans two districts: the higher one
        self.assertIn(("property", "county"), self.fields(r))
        d = fixture("minimal.json")
        d["property"]["address"] = "10 Test St, Miami, FL 33130"  # no built-in district: the fallback says why
        r = analyze_data(d)
        self.assertIsNone(r["B"]["property"].get("county"))
        self.assertIn("county", self.fields(r)[("costs", "property_tax")]["why"])


def analyze_data(d):
    return strategy.analyze(d, cma=strategy.load_cma(d))


class Audit20260929Third(unittest.TestCase):
    """Eval iteration 4 findings (OFR-214 onward)."""

    GATLIN = {"analysis_date": "2026-09-26", "property": {"address": "2716 Gatlin Ave, Orlando, FL", "list_price": 429000},
              "buyer": {"cash_available": 38000}}

    def test_pushback_names_the_limit_it_breaks(self):  # OFR-214
        r = analyze("fha-competitive.json")
        B, t = r["B"], r["terms"]["recommended"]
        row = next(p for p in strategy.pushback(r) if p["term"] == "Price")
        self.assertEqual(row["breaks"], [])
        B["buyer"]["max_payment"] = strategy.monthly_payment(B, r["costs"], t["price"])  # the ask is now over the cap
        row = next(p for p in strategy.pushback(r) if p["term"] == "Price")
        self.assertEqual(row["breaks"], ["max_payment"])
        self.assertIn(row["yours"], row["response"])
        keys = [k for k, _ in strategy.limits_broken(B, r["costs"], dict(t, price=B["buyer"]["max_price"] + 1000,
                                                                          appraisal_gap=10 ** 6))]
        self.assertEqual(keys, ["max_price", "max_payment", "cash"])

    def test_closing_cost_label_matches_the_math(self):  # OFR-215
        r = analyze("fha-competitive.json")
        self.assertTrue(r["B"]["loan_taxes"])
        self.assertTrue(strategy.closing_cost_basis(r["B"]).endswith("plus loan taxes"))
        a = next(x for x in r["assumptions"] if x["field"] == "closing_cost_pct")
        self.assertIn(strategy.closing_cost_basis(r["B"]), a["why"])
        self.assertNotIn("loan taxes", strategy.closing_cost_basis(analyze("cash.json")["B"]))

    def test_insurance_scorecard_from_facts(self):  # OFR-216
        r = strategy.analyze(copy.deepcopy(self.GATLIN))
        why = r["O"]["recommended"]["score"]["why"]["property"]
        self.assertIn("no insurance quote yet", why)
        self.assertNotIn("planned", why)

    def test_insurance_premium_is_a_quote_in_hand(self):  # OFR-217
        d = copy.deepcopy(self.GATLIN)
        d["costs"] = {"insurance_annual": 3900}
        r = strategy.analyze(d)
        self.assertIs(r["terms"]["recommended"]["insurance_quote"], True)
        self.assertNotIn("insurance", strategy.summary(r)["next_step"])
        riders = [x["rider"] for x in strategy.worksheet(r)["riders"]]
        self.assertFalse(any("(H)" in x for x in riders))
        d["buyer"]["insurance_quote"] = False  # an estimate the agent marks as not a quote stays a to-do
        self.assertIsNone(strategy.analyze(d)["terms"]["recommended"]["insurance_quote"])

    def test_stronger_with_no_gain_is_dropped(self):  # OFR-218
        r = analyze("texas-cma-escalation.json")
        self.assertTrue(r.get("stronger_dropped"))
        self.assertNotIn("stronger", r["terms"])
        self.assertIn("stronger", r["absent"])
        r = strategy.analyze(copy.deepcopy(self.GATLIN))  # a higher score keeps it, worded as deposit at risk
        self.assertIn("stronger", r["terms"])
        self.assertGreater(r["O"]["stronger"]["score"]["total"], r["O"]["recommended"]["score"]["total"])
        what = next(o["what"] for o in strategy.summary(r)["options"] if o["key"] == "stronger")
        self.assertNotIn("for more cash", what)

    def test_closing_and_deposit_dates_follow_business_days(self):  # OFR-219
        r = strategy.analyze(copy.deepcopy(self.GATLIN))
        eff = r["B"]["effective_date"]
        for k, t in r["terms"].items():
            self.assertTrue(strategy.dates.is_business_day(eff + strategy.timedelta(days=t["closing_days"])), k)
        self.assertNotEqual(eff + strategy.timedelta(days=r["terms"]["lower_cost"]["closing_days"]),
                            strategy.date(2026, 11, 11))  # Veterans Day
        r = analyze("minimal.json")  # FR/BAR: a period ending on a weekend rolls to the next business day
        d, note = strategy.risk_after(r["O"]["recommended"], r["costs"])
        self.assertTrue(strategy.dates.is_business_day(d))
        self.assertIsNotNone(note)
        r = analyze("texas-cma-escalation.json")  # no built-in rule: the date stays, with a note to check
        d, note = strategy.risk_after(r["O"]["recommended"], r["costs"])
        self.assertFalse(strategy.dates.is_business_day(d))
        self.assertIsNotNone(note)

    def test_override_past_the_reserve_names_the_limit(self):  # OFR-221
        d = fixture("texas-cma-escalation.json")
        d["overrides"] = {"appraisal_gap": 20000}
        s = strategy.summary(analyze_data(d))
        self.assertTrue(s["breaks_limits"])
        self.assertNotIn("inside your limits", s["why"])
        self.assertEqual(strategy.summary(analyze("texas-cma-escalation.json"))["breaks_limits"], [])

    def test_other_contract_questions_come_first(self):  # OFR-222
        d = fixture("texas-cma-escalation.json")
        del d["worksheet"]["contract_name"]
        r = analyze_data(d)
        order = {a["why"]: a["field"] for a in r["missing"]}
        firsts = [order[w] for w in strategy.result(r)["to_confirm"][:2]]
        self.assertEqual(firsts[0], "contract_name")
        d["cma"]["offer_plan"]["walk_away"] = 640000  # OFR-240: the escalation question comes with an escalation
        d["overrides"] = {"inspection_days": 10}  # keeps the rule-built (escalating) offer from being softened
        r = analyze_data(d)
        self.assertTrue(r["terms"]["recommended"].get("escalation"))
        order = {a["why"]: a["field"] for a in r["missing"]}
        firsts = [order[w] for w in strategy.result(r)["to_confirm"][:2]]
        self.assertEqual(firsts, ["contract_name", "escalation_accepted"])
        self.assertNotIn("contract_name", [a["field"] for a in analyze("fha-competitive.json")["missing"]])

    def test_next_step_is_a_sentence(self):  # OFR-225
        s = strategy.summary(strategy.analyze(copy.deepcopy(self.GATLIN)))
        self.assertTrue(s["next_step"][0].isupper())
        self.assertEqual(s["next_step"].lower().count("get "), 1)

    def test_market_read_names_its_signals(self):  # OFR-226, OFR-229
        heat, basis = strategy.market_heat({"dom": 9}, {"median_dom": 34, "sale_to_list": 0.981})
        self.assertEqual(heat, "hot")
        self.assertTrue(basis.startswith("on days on market"))  # the deciding signal first
        self.assertIn("secondary: sale-to-list", basis)  # the other one, worded as secondary
        self.assertEqual(strategy.market_heat({}, {}), ("normal", "no market data"))
        self.assertEqual(strategy.market_heat({"price_cuts": 1, "dom": 3}, {"median_dom": 30})[0], "soft")



class Audit20260930(unittest.TestCase):
    """Eval iteration 5 findings (OFR-227 to OFR-237)."""
    GAP = fixture("fha-competitive.json")

    def test_lender_timeline_is_its_own_field(self):  # OFR-227
        d = copy.deepcopy(self.GAP)  # lender_called: the financing is confirmed, the date isn't
        w = strategy.worksheet(strategy.analyze(d))
        close = next(x for x in w["rows"] if x["field"] == "Closing Date")
        box = next(p for p in w["package"] if p["item"].startswith("Lender confirms"))
        self.assertEqual(box["status"], "Pending")
        self.assertNotIn("lender confirmed this closing date", close["note"])
        d["buyer"]["lender_confirmed_timeline"] = True
        w = strategy.worksheet(strategy.analyze(d))
        close = next(x for x in w["rows"] if x["field"] == "Closing Date")
        box = next(p for p in w["package"] if p["item"].startswith("Lender confirms"))
        self.assertEqual(box["status"], "Yes")  # the note and the box agree
        self.assertIn("lender confirmed this closing date", close["note"])

    def test_payment_cap_names_its_assumed_inputs(self):  # OFR-228
        d = copy.deepcopy(self.GAP)
        d["costs"].pop("rate"), d["costs"].pop("insurance_annual")
        r = strategy.analyze(d)
        self.assertIn("payment", r["why"]["price"])  # the payment limit sets the price here
        self.assertEqual(len(r["B"]["payment_assumed"]), 2)
        for words in r["B"]["payment_assumed"]:
            self.assertIn(words, r["why"]["price"])
        self.assertEqual(strategy.analyze(copy.deepcopy(self.GAP))["B"]["payment_assumed"], [])

    def test_no_stronger_quotes_the_printed_deposit(self):  # OFR-231
        r = analyze("fha-competitive.json")
        t = dict(r["terms"]["recommended"], deposit=11000, price=358000)
        self.assertIn(strategy.term_val("deposit", t, r["B"]), strategy.no_stronger_reason(r["B"], t))

    def test_other_contract_terms_are_generic(self):  # OFR-234
        d = fixture("texas-cma-escalation.json")
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        words = strategy.cf.term_words(strategy.cf.OTHER)
        self.assertEqual(r["B"]["words"], words)
        res = strategy.result(r)
        labels = [t["term"] for t in res["summary"]["terms"]] + [x["term"] for x in res["side_by_side"]]
        self.assertIn(words["inspection_label"], labels)
        self.assertNotIn("Inspection Period", labels + [p["term"] for p in res["pushback"]])
        self.assertIn(words["deposit_refund"], r["why"]["deposit"])
        fl = analyze("fha-competitive.json")
        self.assertEqual(fl["B"]["words"], strategy.cf.term_words(strategy.cf.AS_IS))
        self.assertIsNone(fl["B"]["words"]["appraisal_addendum"])

    def test_given_tax_rate_notes_homestead(self):  # OFR-237
        d = fixture("texas-cma-escalation.json")
        d["costs"] = {"rate": 6.4, "insurance_annual": 3900, "tax_rate": 0.0198}
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        a = [x for x in r["assumptions"] if x["field"] == "homestead"]
        self.assertEqual([x["value"] for x in a], ["as given"])

    def test_preliminary_names_the_assumed_max(self):  # OFR-233
        r = strategy.analyze({"analysis_date": "2026-09-26", "property": {"address": "2716 Gatlin Ave, Orlando, FL",
                                                                          "list_price": 429000}, "buyer": {"cash_available": 38000}})
        self.assertIn("max_price", [a["field"] for a in r["missing"] if a["impact"] == "high"])
        self.assertIn("max price (assumed $429,000", strategy.preliminary(r))

    def test_scorecard_flows_after_the_net_sheet(self):  # OFR-230
        r = analyze("fha-competitive.json")
        html = buyer_render.details(r, strategy.result(r))
        self.assertEqual(html.count('class="pb"'), 1)  # one break before the detail pages, none forced inside them


class Audit20260930Iter6(unittest.TestCase):
    """Eval iteration 6 findings (OFR-239 to OFR-244)."""
    TX = fixture("texas-cma-escalation.json")
    GAP = fixture("fha-competitive.json")

    def test_reply_lines_outside_the_cap(self):  # OFR-239
        r = analyze_data(copy.deepcopy(self.TX))  # highest and best, one flat number
        res = strategy.result(r)
        self.assertEqual([x["key"] for x in res["reply_lines"]], ["flat_number", "contract_terms", "inspection_period"])
        self.assertIn(strategy.money(r["terms"]["recommended"]["price"]), res["reply_lines"][0]["text"])
        d = copy.deepcopy(self.TX)
        d["competition"]["note"] = "Listing agent: 6 offers in"
        self.assertEqual([x["key"] for x in strategy.result(analyze_data(d))["reply_lines"]],
                         ["contract_terms", "inspection_period"])  # OFR-315: the period is still a default
        d["competition"]["highest_and_best"] = True  # the field wins over the note
        self.assertIn("flat_number", [x["key"] for x in strategy.analyze(d, cma=strategy.load_cma(d))["reply_lines"]])
        d = copy.deepcopy(self.TX)
        d["cma"]["offer_plan"]["walk_away"], d["overrides"] = 640000, {"inspection_days": 10}  # escalating: no flat number
        self.assertTrue(analyze_data(d)["terms"]["recommended"].get("escalation"))
        self.assertEqual([x["key"] for x in analyze_data(d)["reply_lines"]], ["contract_terms"])
        self.assertEqual(analyze("fha-competitive.json")["reply_lines"], [])  # FR/BAR, no highest and best

    def test_no_escalation_question_without_escalation(self):  # OFR-240
        r = analyze_data(copy.deepcopy(self.TX))
        self.assertFalse(r["terms"]["recommended"].get("escalation"))
        self.assertNotIn("escalation_accepted", [a["field"] for a in r["missing"]])

    def test_looked_up_rate_is_labeled(self):  # OFR-241
        d = copy.deepcopy(self.GAP)
        d["costs"]["rate"], d["costs"]["rate_source"] = 7.0, "Freddie Mac weekly 30-year average, week of Sep 24, 2026"
        r = strategy.analyze(d)
        self.assertIn("payment", r["why"]["price"])  # the payment limit sets the price
        self.assertIn("week of Sep 24", r["why"]["price"])
        a = {x["field"]: x for x in r["missing"]}
        self.assertEqual(a["rate_source"]["impact"], "med")  # looked up, not assumed: not Preliminary on its own
        self.assertNotIn("rate", a)
        d["costs"].pop("rate"), d["costs"].pop("rate_source"), d["costs"].pop("insurance_annual")
        a = {x["field"]: x for x in strategy.analyze(d)["missing"]}
        self.assertEqual(a["rate"]["value"], strategy.DEFAULT_RATE)  # the offline fallback, high when it sets the price
        self.assertEqual(a["rate"]["impact"], "high")
        self.assertIn("Assumed", a["rate"]["why"])

    def test_handoff_days_on_market_are_aged(self):  # OFR-242
        d = copy.deepcopy(self.TX)
        del d["property"]["dom"]
        d["cma"]["subject"]["dom"] = 4
        d["analysis_date"] = "2026-09-26"  # handoff as of 9/22
        r = analyze_data(d)
        self.assertEqual(r["B"]["property"]["dom"], 8)
        self.assertEqual({a["field"]: a["value"] for a in r["missing"]}["dom"], 8)
        self.assertNotIn("dom", [a["field"] for a in analyze_data(copy.deepcopy(self.TX))["missing"]])  # given in the file

    def test_estimated_seller_tax_is_labeled(self):  # OFR-243
        d = copy.deepcopy(self.GAP)
        del d["property"]["annual_tax"]
        r = strategy.analyze(d)
        tax = [ln[1] for ln in r["O"]["recommended"]["ns"]["lines"] if ln[0] == "tax"]
        self.assertTrue(tax and tax[0].endswith("Estimate)"))
        self.assertIn("annual_tax", [a["field"] for a in r["missing"]])
        tax = [ln[1] for ln in analyze("fha-competitive.json")["O"]["recommended"]["ns"]["lines"] if ln[0] == "tax"]
        self.assertNotIn("Estimate", tax[0])  # the seller's bill was given

    def test_weekday_deadline(self):  # OFR-244
        sat = strategy.date(2026, 9, 26)
        self.assertEqual(strategy.weekday_date("Friday 5pm", sat), (strategy.date(2026, 10, 2), (17, 0)))
        self.assertEqual(strategy.weekday_date("Mon 17:30", sat), (strategy.date(2026, 9, 28), (17, 30)))
        self.assertIsNone(strategy.weekday_date("Fri Sep 25 · 5 PM", sat))  # a full date is used as given
        d = copy.deepcopy(self.GAP)
        d["analysis_date"], d["competition"]["deadline"] = "2026-09-26", "Friday 5pm"
        r = strategy.analyze(d)
        self.assertEqual(r["B"]["competition"]["deadline"], "2026-10-02 17:00")
        self.assertEqual(r["B"]["effective_date"], strategy.date(2026, 10, 3))
        a = {x["field"]: x for x in r["missing"]}
        self.assertEqual(a["deadline"]["value"], "2026-10-02 17:00")
        first = strategy.result(r)["to_confirm"][0]
        self.assertEqual(first, a["deadline"]["why"])  # asked first: it may already have passed
        d["analysis_date"] = "2026-09-29"  # Tuesday: Friday is 3 days out, no question
        self.assertNotIn("deadline", [x["field"] for x in strategy.analyze(d)["missing"]])



class Audit20260930Iter7(unittest.TestCase):
    """Eval iteration 7 on a contract that isn't FR/BAR (OFR-314 to OFR-316)."""

    def setUp(self):
        d = fixture("texas-cma-escalation.json")
        self.d = d
        self.r = strategy.analyze(copy.deepcopy(d), cma=strategy.load_cma(d))

    def test_best_effort_line_fits_an_offer_being_written(self):  # OFR-314
        out = strategy.result(self.r)
        self.assertEqual(out["chat_notes"], [strategy.cf.BEST_EFFORT_OFFER_NOTE])
        self.assertNotIn(strategy.cf.BEST_EFFORT_NOTE, out["chat_notes"])

    def test_option_period_is_a_default_to_confirm(self):  # OFR-315
        keys = [x["key"] for x in self.r["reply_lines"]]
        self.assertIn("inspection_period", keys)
        self.assertIn("inspection_days", [a["field"] for a in self.r["missing"]])
        d = copy.deepcopy(self.d)
        d["overrides"] = {"inspection_days": 4}  # the agent set it: no longer a default
        r = strategy.analyze(d, cma=strategy.load_cma(d))
        self.assertNotIn("inspection_period", [x["key"] for x in r["reply_lines"]])
        self.assertNotIn("inspection_days", [a["field"] for a in r["missing"]])
        fl = analyze("fha-competitive.json")  # FR/BAR: the form's own period, nothing to confirm
        self.assertNotIn("inspection_period", [x["key"] for x in fl["reply_lines"]])

    def test_deposit_risk_date_marked_to_confirm(self):  # OFR-316
        o = self.r["O"]["recommended"]
        self.assertEqual(o["contract_form"], strategy.cf.OTHER)
        _, note = strategy.risk_after(o, self.r["costs"])
        self.assertIn(strategy.cf.term_words(strategy.cf.OTHER)["deposit_risk_confirm"], note)
        self.assertIn("deposit_risk", [a["field"] for a in self.r["missing"]])
        fl = analyze("fha-competitive.json")
        _, note = strategy.risk_after(fl["O"]["recommended"], fl["costs"])
        self.assertIsNone(strategy.cf.term_words(fl["O"]["recommended"]["contract_form"])["deposit_risk_confirm"])
        self.assertNotIn("confirm when your contract", note or "")


if __name__ == "__main__":
    unittest.main()
