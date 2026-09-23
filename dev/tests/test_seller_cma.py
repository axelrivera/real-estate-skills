"""Tests for plugins/transactions/skills/seller-cma/scripts.

The fixture is the prototype's approved 517 Hickorywood report. Two inputs changed on purpose, so
the nets differ from the prototype's printed figures by exactly $355 per option:
  - brokerage: the prototype's 5% placeholder is now the market default 2.5% listing + 2.5% buyer's
    agent (same 5% total, now labeled placeholder per line);
  - title company fees: the prototype's flat $1,500 "settlement, lien search, recording" is now the
    Florida layer's itemized seller title fees, $700 + $250 + $125 + $70 = $1,145.
Buyer payments and the per-$10,000 effect match the prototype exactly.
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "plugins", "transactions", "skills", "seller-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, seller_render, deck, handoff, profiles = load(
    "seller-cma", "compute", "render", "deck", "_shared.handoff", "_shared.profiles")

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "hickorywood.json")
PROTOTYPE_NETS = [422719, 421781, 424905]  # 517-Hickorywood-Seller-CMA.pdf, page 6
TITLE_FEE_CHANGE = 1500 - 1145


def report():
    with open(FIXTURE) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    R["deck"] = os.path.join(ROOT, R["deck"])
    return R


def run(R, market_path=None):
    market, homes = compute.load_inputs(R, market_path)
    return compute.compute(R, market, homes), homes


def row(C, key):
    return next(r for r in C["net"]["rows"] if r["key"] == key)


def texas(R):
    R["subject"].update(state="TX", county="Travis", city="Austin")
    R.pop("export")
    R["buyer_payment"].pop("district")
    R["buyer_payment"].update(school_mills=9.5, total_mills=19.0)
    return R


class MatchesPrototype(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.C, _ = run(report())

    def test_nets(self):
        self.assertEqual([round(x["net"]) for x in self.C["strategies"]], [n + TITLE_FEE_CHANGE for n in PROTOTYPE_NETS])
        self.assertEqual(self.C["recommended_net_display"], "$422,136")

    def test_net_lines(self):
        self.assertEqual(row(self.C, "listing_fee")["amounts"], [-11575, -11550, -11500])
        self.assertEqual(row(self.C, "buyer_broker_fee")["amounts"], [-11575, -11550, -11500])
        self.assertEqual([round(a) for a in row(self.C, "transfer_tax")["amounts"]], [-3241, -3234, -3220])
        self.assertEqual(row(self.C, "owner_title")["amounts"], [-2390, -2385, -2375])
        self.assertEqual(row(self.C, "title_fees")["amounts"], [-1145] * 3)
        self.assertEqual(row(self.C, "credit")["amounts"], [-10000, -10000, -5000])
        self.assertIn("placeholder", row(self.C, "listing_fee")["label"])
        self.assertEqual(row(self.C, "transfer_tax")["label"], "Documentary stamp tax on the deed (0.70%)")
        self.assertFalse(self.C["preliminary"])

    def test_buyer_payments(self):
        self.assertEqual([round(x["payment"]) for x in self.C["strategies"]], [4148, 4067, 3985])
        self.assertEqual([round(x["down"]) for x in self.C["strategies"]], [23995, 23495, 22995])
        self.assertEqual(self.C["payments"]["per_10k_display"], "$80")
        self.assertEqual(self.C["payments"]["down_per_10k_display"], "$500")

    def test_no_warnings_but_assumptions(self):
        self.assertEqual(self.C["warnings"], [])
        self.assertTrue(any("Brokerage" in a for a in self.C["assumptions"]))


class Handoff(unittest.TestCase):
    def test_seller_handoff(self):
        C, _ = run(report())
        h = handoff.parse_text("reply\n" + C["handoff_block"])
        self.assertEqual(h["side"], "seller")
        self.assertEqual(h["source"], "seller-cma")
        self.assertEqual(h["recommended_list_price"], 469900)
        self.assertIsNone(h["offer_plan"])
        self.assertEqual((h["value"]["low"], h["value"]["high"], h["value"]["median_adjusted"]), (455000, 480000, 469800))
        self.assertEqual(h["market_profile"], {"state": "FL", "mls": "Stellar"})
        self.assertEqual(h["market"]["active_count"], 14)  # the subject's own active listing is left out
        self.assertEqual(len(h["comps"]), 5)

    def test_compute_cli_writes_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(handoff.load(result["handoff_file"])["side"], "seller")


class Costs(unittest.TestCase):
    def test_agent_terms_replace_placeholders(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 3, "buyer_broker_fee_pct": 2}
        C, _ = run(R)
        self.assertEqual(row(C, "listing_fee")["label"], "Listing brokerage (3%)")
        self.assertEqual(row(C, "listing_fee")["amounts"][0], -13890)
        self.assertEqual(row(C, "buyer_broker_fee")["amounts"][0], -9260)
        self.assertFalse(any("Brokerage" in a for a in C["assumptions"]))
        self.assertFalse(any("placeholder" in n for n in C["net"]["notes"]))

    def test_no_buyer_agent_fee(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 2.5, "buyer_broker_fee_pct": 0}
        C, _ = run(R)
        self.assertFalse(any(r["key"] == "buyer_broker_fee" for r in C["net"]["rows"]))

    def test_fraction_is_rejected(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 0.025}
        with self.assertRaises(compute.ReportError):
            run(R)

    def test_payoff_hoa_and_other(self):
        R = report()
        R["costs"] = {"mortgage_payoff": 210000, "hoa": True, "other": [{"label": "Survey", "amount": 450}]}
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"])
        self.assertEqual(row(C, "estoppel")["amounts"][0], -299)
        self.assertEqual(row(C, "other")["label"], "Survey")
        self.assertEqual(row(C, "total")["label"], "Estimated cash at closing")
        base = PROTOTYPE_NETS[0] + TITLE_FEE_CHANGE
        self.assertEqual(round(C["strategies"][0]["net"]), base - 299 - 450 - 210000)


class Warnings(unittest.TestCase):
    def test_recommended_outside_range(self):
        R = report()
        R["recommendation"]["list_price"] = 489900
        C, _ = run(R)
        self.assertTrue(any("outside the supported range" in w for w in C["warnings"]))
        self.assertTrue(any("doesn't match" in w for w in C["warnings"]))

    def test_expected_sale_above_range(self):
        R = report()
        R["pricing"]["strategies"][0]["expected_sale"] = 485000
        C, _ = run(R)
        self.assertTrue(any("above the supported range" in w for w in C["warnings"]))

    def test_missing_field(self):
        R = report()
        del R["recommendation"]["low"]
        with self.assertRaises(compute.ReportError):
            run(R)


class OtherMarkets(unittest.TestCase):
    def test_texas_is_preliminary_without_florida_numbers(self):
        C, _ = run(texas(report()))
        self.assertTrue(C["preliminary"])
        keys = {r["key"] for r in C["net"]["rows"]}
        self.assertEqual(keys, {"sale", "credit", "total"})  # no brokerage, stamps, title or fees borrowed from Florida
        for missing in ("listing fee", "deed transfer tax", "title company fees"):
            self.assertIn(missing, C["net"]["missing"])
        self.assertTrue(any(w.startswith("Preliminary") for w in C["warnings"]))
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 19.0 / 1000 / 12)  # no homestead in Texas

    def test_texas_with_agent_terms_still_preliminary(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 3, "buyer_broker_fee_pct": 2.5}
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertNotIn("listing fee", C["net"]["missing"])

    def test_texas_without_tax_rate_has_no_payments(self):
        R = texas(report())
        R["buyer_payment"].pop("total_mills")
        C, _ = run(R)
        self.assertIsNone(C["payments"])
        self.assertTrue(any("No millage" in w for w in C["warnings"]))

    def test_preliminary_shows_in_pdf_html(self):
        R = texas(report())
        C, homes = run(R)
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertIn("side prelim", doc)
        self.assertIn("no local figure for listing fee", doc)
        self.assertNotIn("Documentary stamp", doc)


AGENT = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
         "email": None, "website": None, "brand": {"seller_primary": "#0B6E4F"}}


class Brand(unittest.TestCase):
    def test_pdf_colors_side_and_agent_fields(self):
        R = report()
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn('<span class="side">Seller</span>', doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("License", doc)
        self.assertIn("--subject:#1F3A5F", doc)  # the subject is the palette's 'both' color, never the brand
        self.assertNotIn("side prelim", doc)

    def test_default_seller_orange(self):
        R = report()
        C, homes = run(R)
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertIn("--brand:#C2410C", doc)

    def test_deck_data_colors_and_agent(self):
        R = report()
        C, homes = run(R)
        L =compute.cma.Labels(compute.ASSETS)
        D = deck.deck_data(R, C, homes, AGENT, L, "footer")
        self.assertEqual(D["colors"]["brand"], "0B6E4F")
        self.assertEqual(D["colors"]["party_both"], "1F3A5F")
        self.assertEqual(D["colors"]["on_brand"], "FFFFFF")
        self.assertEqual(D["agent"]["lines"], ["Sunshine Realty"])  # no "License undefined"
        self.assertEqual(D["strategies"][1]["net_display"], "$422,136")
        self.assertIn("$80", D["content"]["payment_takeaway"])  # {per_10k} filled from compute.py
        self.assertEqual(D["competition"][0][1], "$400,000")  # price from the report's competition table

    def test_builder_has_no_hard_coded_colors(self):
        with open(os.path.join(SKILL, "scripts", "build_deck.js")) as f:
            js = f.read()
        self.assertEqual(re.findall(r"['\"]#?[0-9A-Fa-f]{6}['\"]", js), [])


class DeckContent(unittest.TestCase):
    def test_missing_field(self):
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        del R["deck"]["launch_plan"]
        with self.assertRaises(deck.DeckError):
            deck.load_content(R)

    def test_competition_must_be_in_report(self):
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        R["deck"]["competition"][0][0] = "1 Nowhere Ln"
        C, homes = run(R)
        with self.assertRaises(deck.DeckError):
            deck.deck_data(R, C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer")


def node_ready():
    """True when node can load pptxgenjs, react-icons and sharp (NODE_PATH, the global folder, or dev/node_modules)."""
    local = os.path.abspath(os.path.join(ROOT, "dev", "node_modules"))
    if os.path.isdir(local) and local not in os.environ.get("NODE_PATH", ""):
        os.environ["NODE_PATH"] = os.pathsep.join(p for p in (os.environ.get("NODE_PATH"), local) if p)
    node = shutil.which("node")
    if not node:
        return False
    r = subprocess.run([node, "-e", "require('pptxgenjs');require('react-icons/fa');require('sharp');require('react-dom/server')"],
                       capture_output=True, env=deck.node_env(), timeout=60)
    return r.returncode == 0


class Files(unittest.TestCase):
    def test_full_pdf(self):
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(R, "pdf", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(handoff.load(paths[1])["side"], "seller")

    def test_full_pptx(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here "
                          "(set NODE_PATH to dev/node_modules after `make setup`).")
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(R, "pptx", tmp, {"agent": AGENT, "market": None, "sample": True})
            with zipfile.ZipFile(paths[0]) as z:
                slides = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                self.assertEqual(len(slides), 15)
                charts = [z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
                scatter = next(c for c in charts if "<c:scatterChart>" in c)
                self.assertIn('<c:symbol val="triangle"/>', scatter)
                self.assertIn('<c:symbol val="diamond"/>', scatter)
                self.assertIn('val="1F3A5F"', scatter)
                self.assertIn('val="0B6E4F"', scatter)
                text = "".join(z.read(n).decode() for n in slides)
                self.assertIn("Sunshine Realty", text)
                self.assertNotIn("undefined", text)
                self.assertNotIn("C2410C", text)  # the default orange never leaks into a branded deck

    def test_preliminary_pptx_without_export(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here.")
        R = texas(report())
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(R, "pptx", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            with zipfile.ZipFile(paths[0]) as z:
                slides = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                self.assertEqual(len(slides), 14)  # no scatter without an MLS export
                self.assertIn("PRELIMINARY", z.read("ppt/slides/slide1.xml").decode())
                text = "".join(z.read(n).decode() for n in slides)
                self.assertNotIn("Documentary", text)
                self.assertNotIn("placeholder", text)


if __name__ == "__main__":
    unittest.main()
