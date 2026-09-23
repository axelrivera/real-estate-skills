"""Tests for plugins/transactions/skills/buyer-offer-strategy/scripts."""
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
        self.assertEqual(got, {
            "recommended": (365000, 64, 23550, 2450, 3150, 61.3, "Competitive"),
            "stronger": (365000, 68, 25550, 450, 3150, 65.3, "Competitive"),
            "lower_cost": (364000, 66, 19980, 6020, 3142, 55.8, "At risk"),
        })
        t = r["terms"]["recommended"]
        self.assertEqual((t["seller_concessions"], t["deposit"], t["appraisal_gap"]), (2000, 11000, 0))
        self.assertNotIn("escalation", t)  # FHA 3.5% never escalates
        self.assertEqual(r["limits"]["stronger"], ["reserve $450 below $2,000 floor"])

    def test_seller_net_with_prototype_costs(self):
        d = fixture("fha-competitive.json")
        d["listing_side"]["listing_fee_pct"] = 0.03
        d["property"]["costs"] = {"title_fees": 645}
        r = strategy.analyze(d)
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 333052)
        self.assertEqual(r["target"], 335052)

    def test_market_defaults(self):
        r = analyze("fha-competitive.json")
        self.assertEqual(r["O"]["recommended"]["ns"]["net_adj"], 334377)  # 2.5% listing fee, $1,145 title fees
        self.assertEqual(r["B"]["buyer"]["closing_cost_pct"], 0.035)     # Florida 3% + 0.5% prepaids


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

    def test_required(self):
        with self.assertRaises(strategy.oe.OfferError):
            strategy.analyze({"property": {"address": "x"}})


class HandoffAndOtherStates(unittest.TestCase):
    def test_handoff_fills_value_market_and_subject(self):
        r = analyze("texas-cma-escalation.json")
        B = r["B"]
        self.assertEqual((B["value"]["cma_low"], B["value"]["cma_high"], B["value"]["mid"]), (598000, 632000, 615000))
        self.assertEqual(B["value"]["point"], 618500)  # median adjusted comp anchors the price
        self.assertEqual((B["market"]["sale_to_list"], B["market"]["median_dom"]), (0.992, 11))
        self.assertEqual((B["property"]["list_price"], B["property"]["state"]), (610000, "TX"))
        self.assertEqual(B["competition"]["heat"], "hot")
        self.assertEqual(r["terms"]["recommended"]["escalation"], {"increment": 1000, "cap": 634000})
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
        self.assertEqual([x["rider"] for x in w["riders"]], ["FHA/VA Financing", "Homeowners' / Flood Insurance (if in your form set)"])
        self.assertEqual(w["rows"][6]["entry"], "**$11,000** within 3 days of Effective Date")


class Pdf(unittest.TestCase):
    def test_options_html_is_buyer_side(self):
        r = analyze("fha-competitive.json")
        doc = buyer_render.options_html(r, {"name": "Jane Doe", "brokerage": "Sunshine Realty"}, sample=True)
        self.assertIn("--brand:#1A74AD", doc)  # buyer blue by default (the prototype used orange)
        self.assertNotIn("--brand:#C2410C", doc)
        self.assertIn("Buyer side", doc)
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
        self.assertEqual(w["price"], "$364,000")
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


if __name__ == "__main__":
    unittest.main()
