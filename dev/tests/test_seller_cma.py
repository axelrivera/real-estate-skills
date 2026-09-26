"""Tests for skills/seller-cma/scripts.

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
SKILL = os.path.join(ROOT, "skills", "seller-cma")
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


def run(R):
    market, homes = compute.load_inputs(R)
    return compute.compute(R, market, homes), homes


def row(C, key):
    return next(r for r in C["net"]["rows"] if r["key"] == key)


def texas(R):
    R["costs"] = {}  # no terms given: national estimates, never Florida's numbers
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
        h = handoff.validate(C["handoff"])
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
    def test_texas_uses_labeled_estimates_not_florida_numbers(self):
        C, _ = run(texas(report()))
        self.assertFalse(C["preliminary"])
        keys = {r["key"] for r in C["net"]["rows"]}
        self.assertEqual(keys, {"sale", "listing_fee", "buyer_broker_fee", "owner_title", "title_fees",
                                "credit", "total", "holding", "after_holding"})  # no transfer tax in Texas, never Florida's stamps
        self.assertEqual(C["net"]["missing"], [])
        self.assertFalse(C["net"]["incomplete"])
        self.assertTrue(any(a.startswith("National estimates") for a in C["assumptions"]))
        self.assertTrue(any(a.startswith("Brokerage is assumed") for a in C["assumptions"]))
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 19.0 / 1000 / 12)  # no homestead in Texas

    def test_texas_deal_numbers_replace_the_estimates(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025, "transfer_tax_rate": 0,
                      "title_fees": {"escrow_fee": 650}}
        C, _ = run(R)
        keys = {r["key"] for r in C["net"]["rows"]}
        self.assertNotIn("transfer_tax", keys)  # Texas has none: the looked-up 0 wins
        self.assertEqual(row(C, "listing_fee")["label"], "Listing Brokerage (3%)")
        self.assertEqual(row(C, "title_fees")["amounts"][0], -650)
        self.assertFalse(C["net"]["standard_terms"])
    def test_texas_without_tax_rate_estimates_payments(self):
        R = texas(report())
        R["buyer_payment"].pop("total_mills")
        C, _ = run(R)
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 0.011 / 12)  # national estimate
        self.assertTrue(any("Buyer taxes are estimated" in w for w in C["warnings"]))
    def test_estimates_show_in_pdf_html(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025}
        C, homes = run(R)
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertNotIn("tag prelim", doc)
        self.assertNotIn("Transfer Tax", doc)  # Texas has no state transfer tax
        self.assertIn("Owner's Title Insurance (Estimate)", doc)
        self.assertIn("Estimates, not local figures", doc)
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
        self.assertIn("--subject:var(--text)", doc)  # the subject home is black: one brand hue, no second color
        self.assertNotIn("var(--party", doc)  # no party color outside party coding
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

    def test_deck_roles_hold_contrast_for_any_brand(self):
        design = deck.design
        for primary in (None, "#F2C94C", "#FFE600", "#111827", "#9CA3AF", "#6B21A8", "#0B6E4F"):
            K = design.pptx_colors(design.theme({"primary": primary} if primary else None, "seller"))
            K.update(deck.contrast_roles(K))
            c = lambda a, b: design.contrast("#" + K[a], "#" + K[b])
            self.assertGreaterEqual(c("mark", "bg"), 3.0, primary)          # chart marks on white
            self.assertGreaterEqual(c("brand_ink", "bg"), 4.5, primary)     # brand text, fills behind white text
            self.assertGreaterEqual(c("brand_strong", "brand_callout"), 6.0, primary)  # small brand text on cards
            self.assertGreaterEqual(c("on_dark", "brand_deep"), 7.0, primary)  # text and circles on the dark slides
            self.assertGreaterEqual(c("on_ink", "brand_ink"), 4.5, primary)
            self.assertGreaterEqual(design.distance("#" + K["mark"], "#" + K["text"]), 0.12, primary)  # comps vs subject

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

    def deck_R(self):
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        return R

    def data(self, R):
        C, homes = run(R)
        return deck.deck_data(R, C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer"), C

    def test_net_note_lists_only_what_is_left_out(self):
        R = self.deck_R()
        D, C = self.data(R)
        self.assertFalse(C["net"]["has_tax"])
        self.assertIn("mortgage payoff, tax proration and repairs", D["net_note"])
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-11-20", mortgage_payoff=210000)
        D, C = self.data(R)
        self.assertTrue(C["net"]["has_tax"])
        self.assertNotIn("tax proration", D["net_note"])  # the proration is a row in the table: never "not included"
        self.assertNotIn("mortgage payoff", D["net_note"])
        self.assertIn("Not included: repairs;", D["net_note"])

    def test_strategy_title_follows_the_count(self):
        R = self.deck_R()
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_strat_title"], "Three Ways to Price It")

    def test_expected_sub_follows_the_market(self):
        R = self.deck_R()
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_expected_sub"], "After the negotiating that is normal now")
        ri = R["pricing"]["recommended_index"]
        R["pricing"]["strategies"][ri]["expected_sale"] = R["recommendation"]["list_price"]  # a seller's market: sells at list
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_expected_sub"], "With competing offers likely at this price")

    def test_comps_basis(self):
        R = self.deck_R()
        R["deck"].pop("comps_basis", None)
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_step_comps"], "closest matches to your home")  # never "pool" by default
        R["deck"]["comps_basis"] = "size, floor, view and building"
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_step_comps"], "closest matches in size, floor, view and building")

    def test_no_adjustments_note(self):
        R = self.deck_R()
        for c in R["comps"]["cards"]:
            c["adjustments"], c["seller_concessions"] = [], 0
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_method_note"], "The comps needed no adjustment.")

    def test_no_mortgage_is_cash_at_closing(self):
        R = self.deck_R()
        R["costs"]["mortgage_payoff"] = 0
        D, C = self.data(R)
        self.assertTrue(C["net"]["cash_at_closing"] and C["net"]["no_mortgage"])
        self.assertEqual(D["net_sub"], "Estimated cash at closing, with no mortgage to pay off")
        self.assertFalse([r for r in C["net"]["rows"] if r["key"] == "payoff"])
        self.assertEqual(row(C, "total")["label"], "Estimated Cash at Closing")

    def test_icons(self):
        R = self.deck_R()
        R["deck"]["value_drivers"][1] = R["deck"]["value_drivers"][1][:2] + ["pool"]
        D, _ = self.data(R)
        self.assertEqual(D["icons"]["value_drivers"][1], "FaSwimmingPool")  # named in the content
        R["deck"]["value_drivers"][1] = R["deck"]["value_drivers"][1][:2]
        D, _ = self.data(R)
        self.assertEqual(D["icons"]["value_drivers"][1], "FaStar")  # neutral, never a pool the home may not have
        R["deck"]["value_drivers"][0] = R["deck"]["value_drivers"][0][:2] + ["hot tub"]
        with self.assertRaises(deck.DeckError):
            deck.load_content(R)

    def test_counts_are_ranges(self):
        R = self.deck_R()
        R["deck"]["document_items"] = []  # nothing needs paperwork: allowed, the box is left out
        R["deck"]["launch_plan"] = R["deck"]["launch_plan"][:4]
        deck.load_content(R)
        R["deck"]["value_drivers"] = R["deck"]["value_drivers"][:1]
        with self.assertRaises(deck.DeckError):
            deck.load_content(R)

    def test_period_labels_across_new_year(self):
        w = {"first_close": "2025-11-03", "last_close": "2026-02-20", "split_date": "2026-01-01"}
        self.assertEqual(deck.period_labels(w), ["November 2025–December 2025", "January 2026–February 2026"])


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


def office_ready():
    return bool(shutil.which("soffice") or shutil.which("libreoffice"))


class Files(unittest.TestCase):
    def test_full_pdf(self):
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(R, "pdf", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(paths, [paths[0]])  # the PDF only: no JSON handed to the agent
            self.assertFalse([f for f in os.listdir(tmp) if f.endswith(".json")])

    def test_full_pptx(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here "
                          "(set NODE_PATH to dev/node_modules after `make setup`).")
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                paths = seller_render.build(R, "pptx", tmp, {"agent": AGENT, "market": None, "sample": True})
            self.assertNotIn("doesn't fit", err.getvalue())  # the sample wording fits every box
            if office_ready():  # a PDF copy of the slides next to the PPTX
                self.assertEqual(len(paths), 2)
                self.assertTrue(paths[1].endswith("-Listing-Presentation.pdf"))
                with open(paths[1], "rb") as f:
                    self.assertEqual(len(re.findall(rb"/Type\s*/Page[^s]", f.read())), 15)
            with zipfile.ZipFile(paths[0]) as z:
                slides = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                self.assertEqual(len(slides), 15)
                charts = [z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
                scatter = next(c for c in charts if "<c:scatterChart>" in c)
                self.assertIn('<c:symbol val="square"/>', scatter)
                self.assertIn('<c:symbol val="diamond"/>', scatter)
                self.assertIn('val="1A1A1A"', scatter)  # the subject home is black, not a second hue
                self.assertIn('val="0B6E4F"', scatter)
                text = "".join(z.read(n).decode() for n in slides)
                self.assertIn("Sunshine Realty", text)
                self.assertNotIn("undefined", text)
                self.assertNotIn("C2410C", text)  # the default orange never leaks into a branded deck
                everything = text + "".join(charts)
                for hue in ("1F3A5F", "E4E7EC", "D2D8DF"):  # the navy 'both' color and its tints: one brand color only
                    self.assertNotIn(hue, everything)

    def test_long_wording_is_flagged(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here.")
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        R["deck"]["market_stats"][3][0] = "Average 30-Year Fixed Mortgage Rate This Quarter"
        C, homes = run(R)
        D = deck.deck_data(R, C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer")
        with tempfile.TemporaryDirectory() as tmp:
            checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))  # still built
            self.assertTrue(os.path.exists(os.path.join(tmp, "deck.pptx")))
        self.assertEqual(len(checks), 1)
        self.assertIn("slide 7", checks[0])
        self.assertIn("deck.market_stats label", checks[0])

    def test_texas_pptx_without_export(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here.")
        R = texas(report())
        if isinstance(R["deck"], str):
            with open(R["deck"]) as f:
                R["deck"] = json.load(f)
        R["deck"].pop("scatter_takeaway", None)  # no export, no scatter slide: not required
        with tempfile.TemporaryDirectory() as tmp:  # never the working directory
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(R, "pptx", tmp, {"agent": profiles.load_agent(None), "sample": True})
            with zipfile.ZipFile(paths[0]) as z:
                slides = sorted(n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n))
                self.assertEqual(len(slides), 14)  # no scatter without an MLS export
                self.assertNotIn("PRELIMINARY", z.read("ppt/slides/slide1.xml").decode())  # estimates are labeled, not blocking
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


class AuditLowCma(unittest.TestCase):
    """CMA-24 (one point set for PDF and deck), CMA-25 (period labels), CMA-26 (method note), CMA-29 (payoff)."""

    def test_deck_and_pdf_use_the_same_points(self):
        R = report()
        C, homes = run(R)
        L = compute.cma.Labels(compute.ASSETS)
        D = deck.scatter_data(homes, R, C, L)
        comps = [cd["address"] for cd in R["comps"]["cards"]]
        pts, _, _ = compute.cma.scatter_points(homes, R["scatter"], R["subject"]["sqft"], R["subject"].get("mls_address"), comps)
        self.assertEqual({k: len(v) for k, v in D["points"].items()}, {k: len(v) for k, v in pts.items()})
        self.assertEqual(len(pts["comp"]), len(comps))  # every comp card is on the chart, matched by address
        self.assertEqual([sr["key"] for sr in D["series"]], ["comp", "sold", "active", "trend", "subject"])

    def test_legend_lists_only_what_is_drawn(self):
        L = compute.cma.Labels(compute.ASSETS)
        legend = compute.cma.scatter_legend(L, "Your Home", {"comp": 3, "sold": 0, "active": 2, "trend": 1})
        self.assertIn(L("lg_comp"), legend)
        self.assertNotIn(L("lg_sold"), legend)
        self.assertIn(L("lg_active"), legend)

    def test_period_labels(self):
        w = {"first_close": "2026-04-03", "last_close": "2026-09-20", "split_date": "2026-07-01"}
        self.assertEqual(deck.period_labels(w), ["April–June", "July–September"])
        w["split_date"] = "2026-07-15"
        self.assertEqual(deck.period_labels(w), ["April–July 14", "July 15–September"])

    def test_method_note_lists_the_adjustments_used(self):
        cards = [{"adjustments": [{"label": "Size", "amount": 1800}, {"label": "Larger Corner Lot", "amount": -5000}],
                  "seller_concessions": 0},
                 {"adjustments": [{"label": "Size", "amount": -900}], "seller_concessions": 5000}]
        self.assertEqual(deck.adjustment_words(cards), "size, larger corner lot and seller credits")

    def test_payoff_from_a_balance_is_an_estimate(self):
        R = report()
        R["costs"].update(mortgage_balance=200000, mortgage_rate=6)
        C, _ = run(R)
        self.assertEqual(row(C, "payoff")["amounts"][0], -(200000 + 1000 + 500))
        self.assertEqual(row(C, "payoff")["label"], "Mortgage Payoff (Estimate from Balance)")

if __name__ == "__main__":
    unittest.main()


class AuditMoneyLines(unittest.TestCase):
    """CORE-5, CMA-18 (standard terms marked everywhere), CMA-3 (proration), CORE-6 (surtax)."""

    def test_brokerage_assumed_when_not_given(self):
        R = report()
        R["costs"] = {}
        C, homes = run(R)
        self.assertEqual(row(C, "listing_fee")["label"], "Listing Brokerage (2.5%, Assumed)")
        self.assertEqual(row(C, "buyer_broker_fee")["label"], "Buyer's Agent Compensation (2.5%, Assumed)")
        self.assertTrue(C["net"]["standard_terms"])
        self.assertFalse(C["net"]["incomplete"])  # 5% total assumed: the files build
        self.assertIn("Brokerage is assumed at 5% in total until the listing agreement sets it.", C["net"]["notes"])
        doc = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)[0]
        self.assertIn("Assumed Brokerage", doc)  # page 1 net tile
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer")
        self.assertIn("brokerage assumed", D["net_sub"])  # the deck's net slide
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

