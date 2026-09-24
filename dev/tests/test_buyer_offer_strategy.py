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
    """The prototype's FHA sample (2–3 competing offers): same options, scores, cash and payments."""

    def test_options(self):
        r = analyze("fha-competitive.json")
        got = {k: (o["price"], o["score"]["total"], r["cash"][k]["worst"], r["cash"][k]["reserve"], r["payment"][k],
                   round(r["ci"][k], 1), r["bands"][k][2][1]) for k, o in r["O"].items()}
        # Audit 2026-09-23 (OFR-3, OFR-4, OFR-17): FHA appraisal protection runs to closing and a gap clause earns no
        # listing-side credit, so there's no "stronger" option built on gap money; scores move by a point or three.
        self.assertEqual(got, {
            # CORE-16: the loan taxes are itemized (0.55% of the FHA loan) and the lump share drops 0.5 points.
            # CORE-17: the 2026 indexed homestead exemption lowers the payment $1.
            # OFR-10: at 3.5% down with competition, the price stops at the value midpoint ($363,500, rounded down) and
            # the offer competes on terms; the lower price lifts the appraisal score two points.
            "recommended": (363000, 67, 23555, 2445, 3133, 61.6, "Competitive"),
            "lower_cost": (363000, 65, 19055, 6945, 3133, 53.5, "At Risk"),
        })
        t = r["terms"]["recommended"]
        self.assertEqual((t["seller_concessions"], t["deposit"], t["appraisal_gap"]), (2000, 11000, 0))
        self.assertNotIn("escalation", t)  # FHA 3.5% never escalates
        self.assertNotIn("stronger", r["O"])

    def test_seller_net_with_prototype_costs(self):
        d = fixture("fha-competitive.json")
        d["listing_side"]["listing_fee_pct"] = 0.03
        d["property"]["costs"] = {"title_fees": 645}
        r = strategy.analyze(d)
        # Audit: 4% early-payment discount in the proration (OFR-14), no tax in holding costs (OFR-13)
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 331804)  # OFR-10: $363,000, the value midpoint
        self.assertEqual(r["target"], 335670)

    def test_market_defaults(self):
        r = analyze("fha-competitive.json")
        # No built-in listing fee (CORE-5), $1,145 title fees; OFR-10: priced at the value midpoint, $2,000 below list
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 342194)
        self.assertTrue(any(a["field"] == "listing_fee_pct" for a in r["R"]["assumptions"]))
        # CORE-16: Florida 2.5% + 0.5% prepaids, with the loan's note stamps (0.35%) and intangible tax (0.2%) itemized
        self.assertEqual(r["B"]["buyer"]["closing_cost_pct"], 0.03)
        self.assertEqual([t["rate"] for t in r["B"]["loan_taxes"]], [0.0035, 0.002])
        loan = 365000 * 0.965 * 1.0175  # FHA: the upfront premium is financed, so it's taxed too
        self.assertEqual(strategy.closing_costs(r["B"], 365000), round(365000 * 0.03 + round(loan * 0.0035) + round(loan * 0.002)))


class MissingData(unittest.TestCase):
    def test_minimal_is_preliminary(self):
        r = analyze("minimal.json")
        fields = {a["field"]: a["impact"] for a in r["missing"]}
        self.assertEqual(fields["financing"], "high")
        self.assertEqual(fields["cma_low / cma_high"], "high")
        self.assertEqual(r["B"]["buyer"]["financing"], "conventional")
        self.assertEqual(r["B"]["buyer"]["down_pct"], 0.05)
        s = strategy.summary(r)
        self.assertIn("**Preliminary", s["preliminary"])
        self.assertIn("(assumed; confirm with lender)", s["financing"])

    def test_not_enough_cash_says_so(self):
        d = fixture("fha-competitive.json")
        d["buyer"]["cash_available"] = 9000
        r = strategy.analyze(d)
        self.assertTrue(r["constraints"][0].startswith("Not enough cash"))
        self.assertNotIn("stronger", r["O"])

    def test_cash_buyer(self):
        """OFR-1: a cash buyer's 100% down passes the fraction check; no lender wording."""
        r = analyze("cash.json")
        self.assertEqual(r["B"]["buyer"]["down_pct"], 1.0)
        rec = r["O"]["recommended"]
        self.assertFalse(rec["financed"])
        self.assertEqual(rec["loan_approval_days"], 0)
        self.assertEqual(strategy.summary(r)["financing"], "Cash")

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
        self.assertEqual(r["why"]["inspection_days"], "Room for a full inspection + 4-point (year built unknown)")

    def test_planned_insurance_quote_is_not_scored(self):
        """OFR-18: a quote the buyer plans to get is a to-do, not a point."""
        B = {"analysis_date": "2026-09-23", "property": {"address": "2716 Gatlin Ave, Orlando, FL", "list_price": 429000},
             "buyer": {"cash_available": 38000}}
        r = strategy.analyze(B)
        self.assertIsNone(r["promoted"])
        self.assertIn("insurance quote planned before submitting (scored once in hand)",
                      r["O"]["recommended"]["score"]["why"]["property"])
        self.assertIn("get the insurance quote", strategy.summary(r)["next_step"])

    def test_rate_written_as_fraction_is_refused(self):
        B = {"analysis_date": "2026-09-23", "property": {"address": "1 Main St, Orlando, FL", "list_price": 400000},
             "buyer": {"cash_available": 40000}, "costs": {"rate": 0.064}}
        with self.assertRaisesRegex(strategy.oe.OfferError, "percent"):
            strategy.analyze(B)


class HandoffAndOtherStates(unittest.TestCase):
    def test_handoff_fills_value_market_and_subject(self):
        r = analyze("texas-cma-escalation.json")
        B = r["B"]
        self.assertEqual((B["value"]["cma_low"], B["value"]["cma_high"], B["value"]["mid"]), (598000, 632000, 615000))
        self.assertEqual(B["value"]["point"], 618500)  # median adjusted comp anchors the price
        self.assertEqual((B["market"]["sale_to_list"], B["market"]["median_dom"]), (0.992, 11))
        self.assertEqual((B["property"]["list_price"], B["property"]["state"]), (610000, "TX"))
        self.assertEqual(B["competition"]["heat"], "hot")
        # OFR-9: $615,000 reaches the same Strong outlook as the $632,000 offer, so it's recommended and the fuller offer
        # stays as the stronger alternative. OFR-5: that one is already at the CMA's walk-away, so it doesn't escalate.
        self.assertEqual(r["promoted"], "lower_cost")
        self.assertEqual((r["terms"]["recommended"]["price"], r["terms"]["stronger"]["price"]), (615000, 632000))
        self.assertEqual(r["bands"]["recommended"][3][0], r["bands"]["stronger"][3][0])
        self.assertNotIn("escalation", r["terms"]["stronger"])
        self.assertNotIn("cma_low / cma_high", [a["field"] for a in r["missing"]])

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
        self.assertEqual(w["form_name"], "TREC One to Four Family Residential Contract (Resale)")
        self.assertTrue(all(row["para"] == "" for row in w["rows"]))
        self.assertIn("national planning estimate", json.dumps(r["missing"]))  # closing costs, not Florida's

    def test_florida_worksheet(self):
        w = strategy.worksheet(analyze("fha-competitive.json"))
        self.assertTrue(w["frbar"])
        self.assertEqual([x["rider"] for x in w["riders"]], ["FHA/VA Financing", "Homeowners' / Flood Insurance (If in Your Form Set)"])
        self.assertEqual(w["rows"][6]["entry"], "**$11,000** within 3 days of Effective Date")


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
        self.assertIn("value range starts above it", r["why"]["price"])

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
        self.assertTrue(any("jumbo" in a["why"] for a in r["assumptions"]))
        self.assertIn("check the loan limit", r["limits"]["recommended"])
        d = self.only_offer(financing="fha", down_pct=0.035)
        d["property"].update(list_price=700000)
        d["value"] = {"cma_low": 690000, "cma_high": 720000}
        r = strategy.analyze(d)
        self.assertTrue(any("FHA floor ($541,287)" in a["why"] for a in r["assumptions"]))


class TrecWorksheet(unittest.TestCase):
    """OFR-19 (TREC 20-19 and 49-1, verified): option fee and period, the financing addendum and 49-1."""

    def test_trec_rows_and_riders(self):
        d = fixture("texas-cma-escalation.json")
        d.setdefault("worksheet", {})["option_fee"] = 300
        w = strategy.worksheet(strategy.analyze(d, cma=strategy.load_cma(d)))
        fields = [r["field"] for r in w["rows"]]
        self.assertIn("Option Fee", fields)
        self.assertIn("Option Period", fields)
        self.assertNotIn("Inspection Period", fields)
        self.assertIn("Earnest Money", fields)
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn("Third Party Financing Addendum", riders)
        self.assertIn("Addendum Concerning Right to Terminate Due to Lender's Appraisal (TREC 49-1)", riders)

    def test_fha_on_trec_has_no_49_1(self):
        d = fixture("texas-cma-escalation.json")
        d["buyer"].update(financing="fha", down_pct=0.035)
        w = strategy.worksheet(strategy.analyze(d, cma=strategy.load_cma(d)))
        riders = [r["rider"] for r in w["riders"]]
        self.assertFalse(any("49-1" in x for x in riders))
        self.assertIn("Third Party Financing Addendum (FHA/VA Section)", riders)

    def test_florida_keeps_its_inspection_period(self):
        w = strategy.worksheet(analyze("fha-competitive.json"))
        self.assertIn("Inspection Period", [r["field"] for r in w["rows"]])


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

if __name__ == "__main__":
    unittest.main()


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
        self.assertIn("Letter at up to $637,000, the escalation cap", text)
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

