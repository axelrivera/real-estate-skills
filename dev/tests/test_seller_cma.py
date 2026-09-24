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
    R["costs"] = {}  # no agent terms: nothing is borrowed from Florida
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
        self.assertEqual(row(self.C, "listing_fee")["label"], "Listing Brokerage (2.5%)")  # the listing agreement's terms
        self.assertEqual(row(self.C, "transfer_tax")["label"], "Documentary Stamp Tax on the Deed (0.70%)")
        self.assertFalse(self.C["preliminary"])

    def test_buyer_payments(self):
        # CORE-17: the 2026 indexed homestead ($26,411 off non-school levies) lowers tax about $17/yr
        self.assertEqual([round(x["payment"]) for x in self.C["strategies"]], [4147, 4065, 3984])
        self.assertEqual([round(x["down"]) for x in self.C["strategies"]], [23995, 23495, 22995])
        self.assertEqual(self.C["payments"]["per_10k_display"], "$80")
        self.assertEqual(self.C["payments"]["down_per_10k_display"], "$500")

    def test_no_warnings_but_assumptions(self):
        self.assertEqual(self.C["warnings"], [])
        self.assertTrue(any("Title company fees" in a for a in self.C["assumptions"]))
        self.assertFalse(any("Brokerage" in a for a in self.C["assumptions"]))  # the agreement's terms are in costs


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
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.02}
        C, _ = run(R)
        self.assertEqual(row(C, "listing_fee")["label"], "Listing Brokerage (3%)")
        self.assertEqual(row(C, "listing_fee")["amounts"][0], -13890)
        self.assertEqual(row(C, "buyer_broker_fee")["amounts"][0], -9260)
        self.assertFalse(any("Brokerage" in a for a in C["assumptions"]))
        self.assertFalse(any("placeholder" in n for n in C["net"]["notes"]))

    def test_no_buyer_agent_fee(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 0.025, "buyer_broker_fee_pct": 0}
        C, _ = run(R)
        self.assertFalse(any(r["key"] == "buyer_broker_fee" for r in C["net"]["rows"]))

    def test_title_company_quote_replaces_built_in_fees(self):
        R = report()
        R["costs"] = {"title_fees": {"settlement_fee": 850, "title_search": 200}}
        C, _ = run(R)
        self.assertEqual(row(C, "title_fees")["amounts"][0], -1050)
        self.assertFalse(any("Title company fees are the built-in" in a for a in C["assumptions"]))

    def test_percent_is_rejected(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 2.5}  # *_pct fields are fractions everywhere (0.025)
        with self.assertRaises(compute.ReportError):
            run(R)

    def test_credit_rows_by_key(self):
        """CMA-1: a credit in only some options keeps its row, in either order, and totals still add up."""
        for credits in ((0, 10000, 0), (10000, 0, 0), (0, 0, 5000)):
            R = report()
            for x, c in zip(R["pricing"]["strategies"], credits):
                x["seller_credit"] = c
            C, _ = run(R)
            self.assertEqual(row(C, "credit")["amounts"], [-c for c in credits])
            for i, total in enumerate(C["net"]["totals"]):
                self.assertAlmostEqual(sum(r["amounts"][i] for r in C["net"]["rows"]
                                           if r["key"] not in ("total", "holding", "after_holding")), total, places=2)
                self.assertEqual(C["net"]["after_holding"][i], total - C["net"]["holding"][i])

    def test_payoff_hoa_and_other(self):
        R = report()
        R["costs"].update({"mortgage_payoff": 210000, "hoa": True, "other": [{"label": "Survey", "amount": 450}]})
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"])
        self.assertEqual(row(C, "estoppel")["amounts"][0], -299)
        self.assertEqual(row(C, "other")["label"], "Survey")
        self.assertEqual(row(C, "total")["label"], "Estimated Cash at Closing")
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
        R["pricing"]["strategies"][2]["expected_sale"] = 485000  # the competing-offer option may sell above list
        C, _ = run(R)
        self.assertTrue(any("above the supported range" in w for w in C["warnings"]))

    def test_expected_sale_above_list_outside_competing_option(self):
        """CMA-20: only the competing-offer option can expect to sell above its list price."""
        R = report()
        R["pricing"]["strategies"][0]["expected_sale"] = 485000
        with self.assertRaisesRegex(compute.ReportError, r"strategies\[0\]"):
            run(R)

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
        for missing in ("listing brokerage fee", "transfer tax (or confirmation there is none)", "title company fees"):
            self.assertIn(missing, C["net"]["missing"])
        self.assertTrue(C["net"]["incomplete"])  # no commission: render.py refuses rather than overstate the net
        self.assertTrue(any(w.startswith("Preliminary") for w in C["warnings"]))
        self.assertTrue(any(w.startswith("No brokerage terms") for w in C["warnings"]))
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 19.0 / 1000 / 12)  # no homestead in Texas

    def test_texas_with_agent_terms_still_preliminary(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025}
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertNotIn("listing brokerage fee", C["net"]["missing"])
        self.assertFalse(C["net"]["incomplete"])

    def test_texas_without_tax_rate_has_no_payments(self):
        R = texas(report())
        R["buyer_payment"].pop("total_mills")
        C, _ = run(R)
        self.assertIsNone(C["payments"])
        self.assertTrue(any("No millage" in w for w in C["warnings"]))

    def test_preliminary_shows_in_pdf_html(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025}
        C, homes = run(R)
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertIn("tag prelim", doc)
        self.assertIn("no local figure for transfer tax (or confirmation there is none)", doc)
        self.assertNotIn("Documentary Stamp", doc)


AGENT = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
         "email": None, "website": None, "brand": {"seller_primary": "#0B6E4F"}}


class Brand(unittest.TestCase):
    def test_pdf_colors_side_and_agent_fields(self):
        R = report()
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Seller Summary", doc)  # the side shows in the page-1 label; no separate pill
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("License", doc)
        self.assertIn("--party-both:#1F3A5F", doc)  # the subject is the palette's 'both' color, never the brand
        self.assertIn("--subject:var(--party-both)", doc)
        self.assertNotIn("tag prelim", doc)

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
        with tempfile.TemporaryDirectory() as tmp:  # never the working directory: a failed build must leave nothing behind
            with self.assertRaises(compute.ReportError):  # no brokerage terms: no files
                seller_render.build(R, "pptx", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            self.assertEqual(os.listdir(tmp), [])
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025}
        if isinstance(R["deck"], str):
            with open(R["deck"]) as f:
                R["deck"] = json.load(f)
        R["deck"].pop("scatter_takeaway", None)  # no export, no scatter slide: not required
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



class Flood(unittest.TestCase):
    """CMA-6: the buyer payment shown to the seller counts a flood quote and otherwise says to get one."""

    def test_flood_line(self):
        C, _ = run(report())
        self.assertIsNone(C["payments"]["flood"]["annual"])
        self.assertIn("Get a quote", C["payments"]["flood"]["note"])
        R = report()
        R["buyer_payment"]["flood_insurance_annual"] = 1200
        Q, _ = run(R)
        for a, b in zip(C["payments"]["rows"], Q["payments"]["rows"]):
            self.assertAlmostEqual(b["payment"] - a["payment"], 100)

    def test_no_citizens_rule_outside_florida(self):
        C, _ = run(texas(report()))
        self.assertNotIn("Citizens", C["payments"]["flood"]["note"])


class HoldingCosts(unittest.TestCase):
    """CMA-7: slower options pay more to hold the home, and options are compared after that."""

    def test_net_after_holding(self):
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, _ = run(R)
        hold = C["net"]["holding"]
        self.assertTrue(hold[0] > hold[1] > hold[2] > 0)  # 45–90 days, 3–6 weeks, 1–3 weeks to contract
        self.assertEqual([x["net_after_holding"] for x in C["strategies"]],
                         [t - h for t, h in zip(C["net"]["totals"], hold)])
        after = C["net"]["after_holding"]
        self.assertEqual(C["net_spread"], max(after) - min(after))
        self.assertTrue(any("month to close" in n for n in C["net"]["notes"]))

    def test_months_from_time_text(self):
        f = compute.finance
        self.assertEqual((f.months_in("45–90 days"), f.months_in("3–6 weeks"), f.months_in("2 months")), (2.22, 1.03, 2.0))
        self.assertIsNone(f.months_in("soon"))

    def test_handoff_file_has_the_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            self.assertTrue(json.loads(out.getvalue())["handoff_file"].endswith(".seller.cma.json"))

if __name__ == "__main__":
    unittest.main()


class AuditMoneyLines(unittest.TestCase):
    """CORE-5, CMA-18 (standard terms marked everywhere), CMA-3 (proration), CORE-6 (surtax)."""

    def test_standard_terms_from_the_market_profile_are_marked(self):
        R = report()
        R["costs"] = {}
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "market.md")
            with open(path, "w") as f:
                f.write("---\nprofile: market\nstate: FL\nbrokerage:\n  listing_fee_pct: 0.03\n  buyer_broker_fee_pct: 0.02\n---\n")
            C, homes = run(R, path)
        self.assertEqual(row(C, "listing_fee")["label"], "Listing Brokerage (3%, Standard Terms)")
        self.assertTrue(C["net"]["standard_terms"])
        self.assertIn("Commissions are negotiable and not set by law.", C["net"]["notes"])
        doc = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)[0]
        self.assertIn("Standard Brokerage Terms", doc)  # page 1 net tile
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer")
        self.assertIn("standard brokerage terms", D["net_sub"])  # the deck's net slide

    def test_no_terms_anywhere_blocks_the_files(self):
        R = report()
        R["costs"] = {}
        C, _ = run(R)
        self.assertTrue(C["net"]["incomplete"])  # Florida too: nothing built in (CORE-5)

    def test_tax_proration_and_surtax(self):
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-01")
        C, _ = run(R)
        tax = row(C, "tax_proration")
        self.assertEqual(tax["amounts"][0], -round(6000 * 0.96 * 334 / 365))
        R["costs"]["current_tax_bill_paid"] = True
        C, _ = run(R)
        self.assertEqual(row(C, "tax_proration")["amounts"][0], round(6000 * 0.96 * 31 / 365))
        R = report()
        R["costs"]["annual_tax"] = 6000
        self.assertTrue(any("expected_closing_date" in w for w in run(R)[0]["warnings"]))
        self.assertIn("Not included: this year's property tax proration", " ".join(run(report())[0]["net"]["notes"]))

