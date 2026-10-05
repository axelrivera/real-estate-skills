"""Tests for skills/seller-cma/scripts.

The fixture is the prototype's approved 517 Hickorywood report. Two inputs changed on purpose, so
the nets differ from the prototype's printed figures by exactly $355 per option:
  - brokerage: the prototype's 5% placeholder is now the market default 2.5% listing + 2.5% buyer's
    agent (same 5% total, now labeled placeholder per line);
  - title company fees: the prototype's flat $1,500 "settlement, lien search, recording" is now the
    Florida layer's itemized seller title fees, $700 + $250 + $125 + $70 = $1,145.
Buyer payments and the per-$10,000 effect match the prototype exactly. Those nets, payments and net lines on the
unmodified fixture are pinned by golden (dev/golden/seller-cma/hickorywood.json).
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import unittest
import zipfile

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "skills", "seller-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, seller_render, deck, handoff, profiles, stats_mod = load(
    "seller-cma", "compute", "render", "deck", "_shared.handoff", "_shared.profiles", "stats")

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


class Handoff(unittest.TestCase):
    def test_seller_handoff(self):
        """Every handoff value is pinned by golden; the schema check isn't."""
        C, _ = run(report())
        handoff.validate(C["handoff"])

    def test_compute_cli_writes_handoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(handoff.load(result["handoff_file"])["side"], "seller")
            self.assertTrue(result["handoff_file"].endswith(".seller.cma.json"))


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


class Reprice(unittest.TestCase):
    """CMA-108: a home listed right now is a question first; the agent's own listing is priced as a reprice."""

    STATS = os.path.join(SKILL, "scripts", "stats.py")

    def stats(self, rows):
        import contextlib
        import csv
        import io
        with open(os.path.join(ROOT, "dev", "samples", "mls-export.csv"), newline="") as f:
            data = list(csv.reader(f))
        head, body = data[0], data[1:]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.csv")
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([head] + [r for r in body if r[3] != "517 LARKWOOD AVE"] + rows)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                stats_mod.main([path, "--address", "517 LARKWOOD AVE", "--sqft", "1849", "--state", "FL",
                                "--county", "Seminole"])
        return json.loads(out.getvalue())

    def row(self, status):
        return ["0.00", "X7000001", status, "517 LARKWOOD AVE", "FERNWOOD PARK UNIT 2", "1849", "$474,900", "", "",
                "$484,900", "", "4", "2", "1972", "Private", "36", "", "0.22", "", ""]

    def test_listed_now_says_confirm_first(self):
        for status in ("ACT", "PND"):
            r = self.stats([self.row(status)])
            self.assertTrue(r["listed_now"], status)
            note = next(n for n in r["market_notes"] if "listed right now" in n)
            self.assertIn("$474,900, 36 days on market", note)
            self.assertEqual(r["listed_now_action"], "ask")
            self.assertNotIn("relist", r)
            self.assertFalse(any("new listing" in n for n in r["market_notes"]))

    def test_past_rows_are_history(self):
        sold = self.row("SLD")
        sold[7:9] = ["$289,000", "06/14/2019"]
        r = self.stats([sold])
        self.assertFalse(r["listed_now"])
        self.assertTrue(any("not a current one" in n for n in r["market_notes"]))
        self.assertFalse(self.stats([])["listed_now"])

    def test_sample_export_is_not_a_current_listing(self):
        """EVAL-9: the committed sample's subject row is a past sale, so a real run wouldn't stop and ask."""
        import contextlib
        import io
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            stats_mod.main([os.path.join(ROOT, "dev", "samples", "mls-export.csv"), "--address", "517 LARKWOOD AVE",
                            "--sqft", "1849", "--state", "FL", "--county", "Seminole"])
        self.assertFalse(json.loads(out.getvalue())["listed_now"])

    def reprice(self):
        R = report()
        stay = {"label": "Stay at $489,900", "list_price": 489900, "expected_sale": 462000, "time": "60–120 days",
                "seller_credit": 10000, "note": "Has sat 74 days at this price"}
        R["pricing"]["strategies"].insert(0, stay)
        R["pricing"]["recommended_index"] = 2
        R["reprice"] = {"current_price": 489900, "days_on_market": 74}
        return R

    def test_reprice_needs_the_stay_option(self):
        R = self.reprice()
        R["pricing"]["strategies"].pop(0)
        R["pricing"]["recommended_index"] = 1
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        self.assertIn("Stay at Current Price", str(e.exception))
        R = self.reprice()
        R["reprice"].pop("days_on_market")
        with self.assertRaises(compute.ReportError):
            run(R)

    def test_reprice_output_and_wording(self):
        R = self.reprice()
        C, homes = run(R)
        self.assertLessEqual({"current_price": 489900, "current_price_display": "$489,900", "days_on_market": 74,
                              "stay_index": 0}.items(), C["reprice"].items())
        self.assertEqual(C["first_steps_heading"], "Before We Reprice")
        self.assertEqual(len(C["strategies"]), 4)
        self.assertTrue(C["strategies"][2]["recommended"])
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertIn("Before We Reprice", doc)
        self.assertNotIn("Before We List", doc)
        R["pricing"]["strategies"][3]["expected_sale"] = 461000  # the competing-offer option (last) may sell above list
        run(R)
        C, _ = run(report())
        self.assertIsNone(C["reprice"])
        self.assertEqual(C["first_steps_heading"], "Before We List")


class Warnings(unittest.TestCase):
    def test_recommended_outside_range(self):
        R = report()
        R["recommendation"]["list_price"] = 489900
        C, _ = run(R)
        self.assertEqual(C["warning_keys"], ["list_outside_range", "list_mismatch"])
        self.assertEqual(len(C["warnings"]), 2)

    def test_expected_sale_above_range(self):
        R = report()
        R["pricing"]["strategies"][2]["expected_sale"] = 485000  # the competing-offer option may sell above list
        C, _ = run(R)
        self.assertEqual(C["warning_keys"], ["expected_above_range"])

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
        self.assertTrue(any(a.startswith("Brokerage is at the default rates") for a in C["assumptions"]))  # asked in chat
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 19.0 / 1000 / 12)  # no homestead in Texas

    def test_out_of_state_terms(self):
        """CMA-109: outside Florida the HOA line has a generic name, and no transfer tax lookup where there is none."""
        R = texas(report())
        R["costs"]["hoa"] = True
        C, _ = run(R)
        self.assertEqual(row(C, "estoppel")["label"], "HOA Documents")  # the estimate is named in the notes, once
        self.assertIn("HOA documents fee", next(n for n in C["net"]["notes"] if n.startswith("Estimates, not local figures")))
        estimates = next(a for a in C["assumptions"] if a.startswith("National estimates"))
        self.assertNotIn("transfer tax", estimates)
        R = texas(report())
        R["subject"].update(state="GA", county="Fulton", city="Atlanta")  # a state that taxes deeds: look it up
        C, _ = run(R)
        self.assertIn("Look up the state's transfer tax", next(a for a in C["assumptions"] if a.startswith("National estimates")))
        R = report()
        R["costs"]["hoa"] = True
        C, _ = run(R)
        self.assertEqual(row(C, "estoppel")["label"], "HOA Estoppel Letter")  # Florida's own term

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
        self.assertIn("tax_estimated", C["warning_keys"])
    def test_estimates_show_in_pdf_html(self):
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025}
        C, homes = run(R)
        doc, _ = seller_render.build_html(R, C, homes, profiles.load_agent(None))
        self.assertNotIn("tag prelim", doc)
        self.assertNotIn("Transfer Tax", doc)  # Texas has no state transfer tax
        self.assertNotIn("(Estimate)", doc)  # local-costs.md: no line says Estimate; the notes name the estimates
        self.assertIn("Owner's Title Insurance", doc)
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
        self.assertEqual(D["colors"]["on_brand"], "FFFFFF")
        self.assertEqual(D["agent"]["lines"], ["Sunshine Realty"])  # no "License undefined"
        self.assertIn("$80", D["content"]["payment_takeaway"])  # {per_10k} filled from compute.py

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
        for item in ("mortgage payoff", "tax proration", "repairs"):
            self.assertIn(item, D["net_note"])
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-11-20", mortgage_payoff=210000)
        D, C = self.data(R)
        self.assertTrue(C["net"]["has_tax"])
        self.assertNotIn("tax proration", D["net_note"])  # the proration is a row in the table: never "not included"
        self.assertNotIn("mortgage payoff", D["net_note"])
        self.assertIn("repairs", D["net_note"])

    def test_strategy_title_follows_the_count(self):
        R = self.deck_R()
        D, _ = self.data(R)
        L = compute.cma.Labels(compute.ASSETS)
        self.assertEqual(D["labels"]["deck_strat_title"], L(f"deck_strat_title_{len(R['pricing']['strategies'])}"))

    def test_expected_sub_follows_the_market(self):
        R = self.deck_R()
        D, _ = self.data(R)
        L = compute.cma.Labels(compute.ASSETS)
        self.assertEqual(D["labels"]["deck_expected_sub"], L("deck_expected_sub"))
        ri = R["pricing"]["recommended_index"]
        R["pricing"]["strategies"][ri]["expected_sale"] = R["recommendation"]["list_price"]  # a seller's market: sells at list
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_expected_sub"], L("deck_expected_sub_at"))

    def test_comps_basis(self):
        R = self.deck_R()
        R["deck"].pop("comps_basis", None)
        D, _ = self.data(R)
        L = compute.cma.Labels(compute.ASSETS)
        self.assertEqual(D["labels"]["deck_step_comps"], L("deck_step_comps"))  # never "pool" by default
        R["deck"]["comps_basis"] = "size, floor, view and building"
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_step_comps"], L("deck_step_comps_basis", basis="size, floor, view and building"))

    def test_no_adjustments_note(self):
        R = self.deck_R()
        for c in R["comps"]["cards"]:
            c["adjustments"], c["seller_concessions"] = [], 0
        R["comps"].pop("time_adjustment")
        D, _ = self.data(R)
        self.assertEqual(D["labels"]["deck_method_note"], compute.cma.Labels(compute.ASSETS)("deck_method_note_none"))

    def test_no_mortgage_is_cash_at_closing(self):
        R = self.deck_R()
        R["costs"]["mortgage_payoff"] = 0
        D, C = self.data(R)
        self.assertTrue(C["net"]["cash_at_closing"] and C["net"]["no_mortgage"])
        L = compute.labels(R)  # CMA-317: after holding costs the subtitle names that net, never "cash at closing"
        self.assertTrue(D["net_sub"].startswith(L("deck_cash_free_holding_sub" if C["net_basis"] == "after_holding"
                                                  else "deck_cash_free_sub")))
        self.assertFalse([r for r in C["net"]["rows"] if r["key"] == "payoff"])

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
    return bool(deck.find_office())


class Files(unittest.TestCase):
    def setUp(self):
        deck.PDF_TIMEOUT = 60  # a stalled LibreOffice fails the run in a minute, not three

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
                    pdf_pages = len(re.findall(rb"/Type\s*/Page[^s]", f.read()))
            with zipfile.ZipFile(paths[0]) as z:
                slides = [n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                if office_ready():
                    self.assertEqual(pdf_pages, len(slides))  # the PDF copy has every slide
                charts = [z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
                scatter = next(c for c in charts if "<c:scatterChart>" in c)
                self.assertIn('<c:size val="5"/>', scatter)  # other sales are small background dots
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
                charts = "".join(z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart"))
                self.assertNotIn("<c:scatterChart>", charts)  # no scatter without an MLS export
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
        self.assertEqual([sr["key"] for sr in D["series"]], ["sold", "active", "trend", "comp", "subject"])

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
        w = {"first_close": "2025-11-03", "last_close": "2026-02-20", "split_date": "2026-01-01"}  # across the new year
        self.assertEqual(deck.period_labels(w), ["November 2025–December 2025", "January 2026–February 2026"])

    def test_method_note_lists_the_adjustments_used(self):
        cards = [{"adjustments": [{"label": "Size", "amount": 1800}, {"label": "Larger Corner Lot", "amount": -5000}],
                  "seller_concessions": 0},
                 {"adjustments": [{"label": "Size", "amount": -900}], "seller_concessions": 5000}]
        self.assertEqual(deck.adjustment_words(cards), "size, lot and seller credits")

    def test_payoff_from_a_balance_is_an_estimate(self):
        R = report()
        R["costs"].update(mortgage_balance=200000, mortgage_rate=6)
        R["pricing"]["net_note"] = "Not included: any repairs agreed after inspection."  # says nothing about the payoff
        C, _ = run(R)
        self.assertEqual(row(C, "payoff")["amounts"][0], -(200000 + 1000))  # Results_v5: a month at 6%, no cushion
        self.assertEqual(row(C, "payoff")["label"], "Mortgage Payoff")  # no Estimate label: the note says so, once
        self.assertEqual(sum("estimated from the loan balance" in n for n in C["net"]["notes"]), 1)


class AuditMoneyLines(unittest.TestCase):
    """CORE-5, CMA-18 (a default commission is a default: no label anywhere), CMA-3 (proration), CORE-6 (surtax)."""

    def test_brokerage_default_when_not_given(self):
        """Owner rule: default commission rates are defaults, not assumptions: no Assumed label on the lines, the page
        1 tile, the net column headers or the deck; the reply still asks for the listing agreement's terms."""
        R = report()
        R["costs"] = {}
        C, homes = run(R)
        self.assertEqual(row(C, "listing_fee")["label"], "Listing Brokerage (2.5%)")
        self.assertEqual(row(C, "buyer_broker_fee")["label"], "Buyer's Agent Compensation (2.5%)")
        self.assertTrue(C["net"]["standard_terms"])
        self.assertFalse(C["net"]["incomplete"])  # the 5% default: the files build
        self.assertFalse(any("assumed" in n.lower() and "brokerage" in n.lower() for n in C["net"]["notes"]))
        self.assertIn("brokerage_assumed", C["assumption_keys"])  # the chat still asks
        doc = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)[0]
        self.assertNotIn("Assumed Brokerage", doc)
        self.assertNotIn("Brokerage Assumed", doc)
        self.assertNotIn("Assumed)", doc)
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.cma.Labels(compute.ASSETS), "footer")
        self.assertNotIn("assumed", D["net_sub"])  # the deck's net slide
    def test_tax_proration_and_surtax(self):
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-01")
        C, _ = run(R)
        tax = row(C, "tax_proration")
        self.assertEqual(C["net"]["closings"][1], "2026-12-01")  # the recommended option closes by the seller's goal
        self.assertEqual(tax["amounts"][1], -round(6000 * 0.96 * 334 / 365))
        R["costs"]["current_tax_bill_paid"] = True
        C, _ = run(R)
        self.assertEqual(row(C, "tax_proration")["amounts"][1], round(6000 * 0.96 * 31 / 365))
        R = report()
        R["costs"]["annual_tax"] = 6000  # Results_v4: no closing date: each option's time to contract sets it
        C = run(R)[0]
        self.assertNotIn("tax_no_closing_date", C["warning_keys"])
        self.assertEqual(C["net"]["closings"], ["2027-01-22", "2026-11-23", "2026-11-05"])
        R["pricing"]["strategies"] = [{**x, "time": ""} for x in R["pricing"]["strategies"]]  # nothing to date it by
        self.assertIn("tax_no_closing_date", run(R)[0]["warning_keys"])
        self.assertIn("Not included: this year's property tax proration", " ".join(run(report())[0]["net"]["notes"]))


class SecondPass(unittest.TestCase):
    """Second-pass audit fixes (CMA-251 to CMA-263)."""

    def reprice(self, current=479900):
        R = report()
        stay = {"label": "Stay at Current Price", "list_price": current, "expected_sale": 458000, "time": "2–4 months",
                "seller_credit": 10000, "note": "Has sat 60 days"}
        R["pricing"]["strategies"] = [stay] + R["pricing"]["strategies"][1:]  # no top-of-range option: cuts only
        R["reprice"] = {"current_price": current, "days_on_market": 60}
        return R

    def test_reprice_wording_is_a_new_price(self):
        """CMA-251: a reprice's page 1, verdict and deck say New List Price, never Recommended List Price."""
        R = self.reprice()
        C, homes = run(R)
        self.assertEqual(C["recommended_index"], 1)
        self.assertEqual(len(C["strategies"]), 3)
        L = compute.labels(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertEqual(L("sum_rec"), "NEW LIST PRICE")
        self.assertIn(L("sum_rec"), doc)
        self.assertNotIn("RECOMMENDED LIST PRICE", doc)
        self.assertNotIn("Recommended List Price", doc)
        R["pricing"]["strategies"][-1]["expected_sale"] = 461000  # the competing-offer option (last) may sell above list
        run(R)

    def test_reprice_never_raises_the_price_unless_asked(self):
        """CMA-251: Stay at Current Price plus cuts only; an increase needs reprice.allow_increase."""
        R = self.reprice(current=469900)  # the current price inside the range: a top-of-range option would be a raise
        R["pricing"]["strategies"] = [R["pricing"]["strategies"][0]] + report()["pricing"]["strategies"]
        R["pricing"]["recommended_index"] = 2
        R["pricing"]["strategies"][2]["list_price"] = 464900
        R["recommendation"]["list_price"] = 464900
        with self.assertRaisesRegex(compute.ReportError, "cuts only"):
            run(R)
        R["reprice"]["allow_increase"] = True
        run(R)

    def stats(self, rows, *extra, head_extra=()):
        import csv
        with open(os.path.join(ROOT, "dev", "samples", "mls-export.csv"), newline="") as f:
            data = list(csv.reader(f))
        head = data[0] + list(head_extra)
        body = [r + [""] * len(head_extra) for r in data[1:] if r[3] != "517 LARKWOOD AVE"]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.csv")
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([head] + body + rows)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                stats_mod.main([path, "--address", "517 LARKWOOD AVE", "--sqft", "1849", "--mls", "Stellar", *extra])
        return json.loads(out.getvalue())

    def subject_row(self, status, extra=()):
        return ["0.00", "X7000001", status, "517 LARKWOOD AVE", "FERNWOOD PARK UNIT 2", "1849", "$474,900", "", "",
                "$484,900", "", "4", "2", "1972", "Private", "36", "", "0.22", "", ""] + list(extra)

    def test_own_listing_confirms_then_reprices(self):
        """CMA-251: when the agent already said it's their listing, the note says confirm, then reprice."""
        r = self.stats([self.subject_row("ACT")], "--state", "FL", "--county", "Seminole", "--own-listing")
        self.assertEqual(r["listed_now_action"], "reprice")
        self.assertIn("confirm, then reprice", " ".join(r["market_notes"]))
        self.assertNotIn("stop and ask", " ".join(r["market_notes"]))
        r = self.stats([self.subject_row("ACT")], "--state", "FL", "--county", "Seminole")
        self.assertEqual(r["listed_now_action"], "ask")

    def test_location_from_the_export_row(self):
        """CMA-257: no county given: the export's own row for the home names it; without one, ask."""
        r = self.stats([self.subject_row("EXP", ("Altamonte Springs", "Seminole"))], head_extra=("City", "CountyOrParish"))
        self.assertEqual(r["subject_location"], {"city": "Altamonte Springs", "county": "Seminole"})
        r = self.stats([self.subject_row("EXP")])
        self.assertIsNone(r["subject_location"])
        self.assertIn("ask the agent for the city and county", " ".join(r["market_notes"]))

    def test_undated_failed_listing_is_flagged(self):
        """CMA-260: an expired listing with no dates in the export is named, with a note to ask when it ran."""
        r = self.stats([self.subject_row("EXP")], "--state", "FL", "--county", "Seminole")
        self.assertEqual(r["undated_history"], ["517 LARKWOOD AVE (expired at $474,900)"])
        self.assertEqual(self.stats([], "--state", "FL", "--county", "Seminole")["undated_history"], [])

    def test_december_closing_assumes_the_bill_unpaid(self):
        """CMA-254: one rule: the seller's share, the bill assumed unpaid (said in the notes), a credit back only when paid."""
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-15")
        C, _ = run(R)
        tax = row(C, "tax_proration")
        self.assertTrue(C["net"]["tax_assumed"])
        self.assertEqual(tax["label"], "Property Tax Proration (Jan 1 to Closing)")  # no Assumed label
        self.assertIn(compute.labels(R)("net_tax_assumed_note"), C["net"]["notes"])
        self.assertLess(tax["amounts"][1], 0)  # a cost to the seller
        self.assertTrue(any("current_tax_bill_paid" in a for a in C["assumptions"]))
        R["costs"]["current_tax_bill_paid"] = True
        C, _ = run(R)
        self.assertFalse(C["net"]["tax_assumed"])
        self.assertGreater(row(C, "tax_proration")["amounts"][1], 0)  # the buyer credits back Dec 15 to Dec 31
        R = report()
        R["costs"]["annual_tax"] = 6000  # before bills go out: no assumption
        for x in R["pricing"]["strategies"]:
            x["closing_date"] = "2026-09-15"
        self.assertFalse(run(R)[0]["net"]["tax_assumed"])

    def test_holding_note_states_the_loan_rate_and_tax(self):
        """CMA-255: the note names the interest rate and payoff, says when there's no loan, and never claims the tax
        is in a proration that was left out."""
        R = report()
        C, _ = run(R)
        L = compute.labels(R)
        note = next(n for n in C["net"]["notes"] if n.startswith("Holding costs"))
        self.assertIn(L("net_holding_loan_unknown"), note)
        self.assertIn(L("net_holding_tax_out"), note)
        self.assertNotIn(L("net_holding_tax_in"), note)
        R["costs"].update(mortgage_payoff=210000, annual_tax=6000, expected_closing_date="2026-12-15")
        note = next(n for n in run(R)[0]["net"]["notes"] if n.startswith("Holding costs"))
        self.assertIn(L("net_holding_loan_assumed", payoff="$210,000", rate="4.5"), note)
        self.assertIn(L("net_holding_tax_in"), note)
        R["costs"]["mortgage_rate"] = 6.25
        C, _ = run(R)
        self.assertIn(L("net_holding_loan_rate", payoff="$210,000", rate="6.25"),
                      next(n for n in C["net"]["notes"] if n.startswith("Holding")))

    def test_preliminary_reason_is_the_data(self):
        """CMA-258: the Preliminary line says why: the report's own reason, or the costs that are missing."""
        R = report()
        R["preliminary"] = "the tax bill and the roof date are still to be confirmed, so the figures may change."
        C, homes = run(R)
        self.assertEqual(C["preliminary_reason"],
                         "The tax bill and the roof date are still to be confirmed, so the figures may change.")
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(C["preliminary_reason"], doc)
        self.assertNotIn("closing costs for this market are still missing", doc)
        C, _ = run(report())
        self.assertEqual((C["preliminary"], C["preliminary_reason"]), (False, ""))

    def test_no_export_drops_mls_notes_and_fills_key_stats(self):
        """CMA-259, CMA-261: no export: no notes about which MLS, and page 1's empty stat tiles come from the comps."""
        R = texas(report())
        R["mls"] = "Unlock MLS"
        R["summary_page"].pop("key_stats")
        C, homes = run(R)
        self.assertFalse({"mls_not_built_in", "mls_assumed", "mls_not_given"} & set(C["market_note_keys"]))
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        L = compute.labels(R)
        self.assertIn(L("sum_stat_median", n=C["n_comps"]), doc)
        self.assertIn(L("sum_stat_comps"), doc)
        # CMA-279: with an export read by the MLS's own columns, the MLS isn't in doubt; a mapped export keeps the note
        self.assertNotIn("mls_assumed", run(report())[0]["market_note_keys"])
        R = report()
        R["export_columns"] = {"address": "Address", "status": "Status", "living_area": "Heated Area",
                               "close_price": "Close Price", "current_price": "Current Price", "close_date": "Close Date"}
        self.assertIn("mls_assumed", run(R)[0]["market_note_keys"])

    def test_no_export_deck_takes_one_value_market_cards(self):
        """CMA-261: without an export the deck's market cards can hold one value each (no invented earlier period)."""
        with open(os.path.join(ROOT, "dev", "fixtures", "seller-cma", "deck", "hickorywood-deck.json")) as f:
            content = json.load(f)
        content["market_stats"] = [["Median Adjusted Value", "$450K", "chart"], ["Sales with Seller Credits", "2 of 3"]]
        R = texas(report())
        R["deck"] = content
        self.assertEqual(deck.load_content(R)["market_stats"][1], ["Sales with Seller Credits", "2 of 3"])
        C, homes = run(R)
        D = deck.deck_data(R, C, homes, AGENT, compute.labels(R), "footer")
        self.assertTrue(D["market"]["one_period"])
        content["market_stats"].append(["Days to Contract", "40", "22"])
        with self.assertRaisesRegex(deck.DeckError, "mixes"):
            deck.load_content(R)

    def test_net_subtitle_ends_in_a_noun(self):
        """CMA-258 (template text): the assumed-brokerage subtitle no longer ends in "agreement's"."""
        R = report()
        R["costs"] = {}
        C, homes = run(R)
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        self.assertFalse(D["net_sub"].endswith("agreement's"))

    def test_no_profile_is_a_chat_check_only(self):
        """CMA-263: render names the missing name and brokerage for the chat; the PDF leaves them out."""
        self.assertIn("no profile", seller_render.profile_check(profiles.load_agent(None)))
        self.assertIsNone(seller_render.profile_check(AGENT))
        self.assertIn("profile incomplete", seller_render.profile_check({**AGENT, "brokerage": None}))
        R = report()
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, profiles.load_agent(None))
        self.assertNotIn("no profile", doc)

    def test_finds_libreoffice_off_path(self):
        """CMA-256: soffice not on PATH: the macOS app bundle and Linux install paths are tried."""
        with tempfile.TemporaryDirectory() as tmp:
            fake = os.path.join(tmp, "soffice")
            with open(fake, "w") as f:
                f.write("#!/bin/sh\n")
            os.chmod(fake, 0o755)
            which, paths = deck.shutil.which, deck.OFFICE_PATHS
            try:
                deck.shutil.which = lambda name: None
                deck.OFFICE_PATHS = ("/nonexistent/soffice", fake)
                self.assertEqual(deck.find_office(), fake)
                deck.OFFICE_PATHS = ("/nonexistent/soffice",)
                self.assertIsNone(deck.find_office())
            finally:
                deck.shutil.which, deck.OFFICE_PATHS = which, paths
        self.assertIn("/Applications/LibreOffice.app/Contents/MacOS/soffice", deck.OFFICE_PATHS)


class ChartLabels(unittest.TestCase):
    """CMA-252, CMA-253: chart labels stay off markers and each other; a chart that nearly fits shrinks."""

    def test_scatter_labels_avoid_each_other(self):
        R = report()
        _, homes = run(R)
        cma = compute.cma
        sc = {**R["scatter"], "subject_label": "Your Home", "subject_label_pos": "right"}
        # a callout at the subject's own price and nearly its size, asked for on the subject label's side
        near = next(h for h in homes if h["status"] == "SOLD" and h.get("living_area")
                    and 0 < h["living_area"] - 1849 < 120 and h["address"] != R["subject"]["mls_address"])
        near["close_price"] = R["recommendation"]["list_price"]
        sc["callouts"] = [{"address": near["address"], "label": "Twin Sale", "side": "left"}]
        svg, info = cma.scatter(homes, sc, 1849, R["recommendation"]["list_price"], R["subject"]["mls_address"],
                                (R["recommendation"]["low"], R["recommendation"]["high"]), compute.labels(R),
                                [cd["address"] for cd in R["comps"]["cards"]])
        self.assertEqual(info["crowded_labels"], [])
        texts = re.findall(r'<text x="([\d.]+)" y="([\d.]+)"(?: text-anchor="(\w+)")? class="(lbl[\w-]*)">([^<]+)</text>', svg)
        self.assertEqual({t[3] for t in texts}, {"lbl", "lbl-subj", "lbl-band"})
        boxes = []
        for x, y, anchor, cls, text in texts:
            size = 13 if cls == "lbl-subj" else 12
            w = cma._text_w(text, size, bold=cls != "lbl")
            x0 = float(x) - (w if anchor == "end" else w / 2 if anchor == "middle" else 0)
            boxes.append((x0, float(y) - size * 0.8, x0 + w, float(y) + size * 0.2))
        for i, a in enumerate(boxes):
            for b in boxes[i + 1:]:
                self.assertFalse(a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3], (a, b))

    def test_dot_label_moves_off_the_price_line(self):
        cards = [{"address": "1 A St", "adjusted": 448000}, {"address": "2 B St", "adjusted": 470000}]
        svg = compute.cma.dotplot(cards, 440000, 460000, 449900, "Recommended")
        self.assertRegex(svg, r'text-anchor="end" class="dp-val">\$448K')  # the line at $449,900 would strike it
        self.assertRegex(svg, r'<text x="[\d.]+" y="[\d.]+" class="dp-val">\$470K')

    def test_scatter_shrinks_rather_than_leave_a_gap(self):
        """CMA-252: a chart group that almost fits the rest of a page shrinks its chart instead of moving."""
        cma, render = compute.cma, seller_render.render
        svg = '<svg viewBox="0 0 760 470" class="scatter"><rect width="760" height="470"/></svg>'

        def layout(filler):
            doc = render.page(f'<div class="wrap"><div style="height:{filler}px"></div>'
                              f'<div class="kg"><h3>Chart</h3><div class="chart-box">{svg}</div>'
                              '<div style="height:260px"></div></div></div>', css=cma.css())

            def measure(pg):
                cma.paginate(pg)
                return pg.evaluate("() => { const g = document.querySelector('.kg');"
                                   "return {pb: g.classList.contains('pb'), w: g.querySelector('svg').style.width}; }")
            with tempfile.TemporaryDirectory() as tmp:
                return render.html_to_pdf(doc, os.path.join(tmp, "x.pdf"), margins=cma.PAGE_MARGINS, before_print=measure)
        near = layout(300)
        self.assertFalse(near["pb"])
        self.assertTrue(near["w"].endswith("px"))
        far = layout(640)  # a third of the page left: too little to shrink into, so it moves
        self.assertTrue(far["pb"])
        self.assertEqual(far["w"], "")


class ThirdPass(unittest.TestCase):
    """Eval iteration 4 fixes (CMA-264 to CMA-276)."""

    def test_net_slide_bars_and_spread_share_one_basis(self):
        """CMA-264: the net chart's bars and the spread tile compare the same nets (after holding costs), and say so."""
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, homes = run(R)
        self.assertEqual(C["net_basis"], "after_holding")
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        bars = [x["net"] for x in D["strategies"]]
        self.assertEqual(max(bars) - min(bars), round(C["net_spread"]))
        self.assertEqual(D["net_spread_display"], C["net_spread_display"])
        self.assertIn("after holding costs", D["net_sub"])

    def test_placeholders_fill_every_field(self):
        """CMA-265: {median_adjusted} fills beyond page 1; an unknown {name} warns; an even count's median is rounded."""
        R = report()
        R["comps"]["summary_paragraph"] = "The adjusted values center on about {median_adjusted}."
        C, homes = run(R)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(f"center on about {C['median_adjusted_display']}.", doc)
        self.assertNotIn("{median_adjusted}", doc)
        R["means"] = ["A sale at {typo_price} would appraise."]
        C, _ = run(R)
        self.assertEqual(C["warning_keys"].count("unfilled_placeholder"), 1)
        self.assertIn("$.means[0]", C["warnings"][C["warning_keys"].index("unfilled_placeholder")])
        R = report()
        R["comps"]["cards"] = R["comps"]["cards"][:4]
        C, _ = run(R)
        self.assertEqual(C["median_adjusted_display"], compute.money(C["median_adjusted"], 100))

    def test_holding_note_names_only_counted_costs(self):
        """CMA-266: no HOA dues, no HOA in the holding note."""
        R = report()
        note = lambda C: next(n for n in C["net"]["notes"] if n.startswith("Holding costs"))
        self.assertNotIn("HOA", note(run(R)[0]))
        R["costs"]["hoa_monthly"] = 120
        self.assertIn("HOA", note(run(R)[0]))

    def test_scatter_label_checks(self):
        """CMA-267: a label still covering a marker is a Check; a label moved off its asked side is information."""
        checks, notes = seller_render.scatter_checks(
            {"labels_overlapping": ["749 Cedar Ln W"], "crowded_labels": [],
             "labels_moved": [("749 Cedar Ln W", "below", "right"), ("Your Home", "right", "left")]})
        self.assertEqual(len(checks), 1)
        self.assertIn("749 Cedar Ln W", checks[0])
        self.assertEqual(len(notes), 1)
        self.assertNotIn("749 Cedar", notes[0])  # already named in the check
        self.assertEqual(seller_render.scatter_checks({"labels_overlapping": [], "labels_moved": []}), ([], []))

    def test_scatter_callout_side_is_passed(self):
        """CMA-267: a callout's side reaches the label placer: any move is reported from the side asked for."""
        R = report()
        _, homes = run(R)
        sc = {**R["scatter"], "subject_label": "Your Home"}
        args = (1849, R["recommendation"]["list_price"], R["subject"]["mls_address"],
                (R["recommendation"]["low"], R["recommendation"]["high"]), compute.labels(R),
                [cd["address"] for cd in R["comps"]["cards"]])
        for side in ("left", "right", "above", "below"):
            sc["callouts"] = [{**R["scatter"]["callouts"][0], "side": side}]
            _, info = compute.cma.scatter(homes, sc, *args)
            label = sc["callouts"][0]["label"]
            self.assertTrue(all(m[1] == side for m in info["labels_moved"] if m[0] == label))

    def test_stellar_export_without_mls(self):
        """CMA-268: a Stellar export with no --mls (no county, so none assumed) says to pass --mls Stellar."""
        export = os.path.join(ROOT, "dev", "evals", "seller-cma", "files", "export-spring-oaks.csv")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            self.assertEqual(stats_mod.main([export, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--state", "FL"]), 1)
        self.assertIn("--mls Stellar", json.loads(out.getvalue())["problems"][0])
        self.assertEqual(stats_mod.builtin_layout(export), "Stellar")

    def test_florida_without_county_warns(self):
        """CMA-268: Florida costs depend on the county (title payer), so a missing county is a warning."""
        R = report()
        self.assertNotIn("no_county", run(R)[0]["warning_keys"])
        R["subject"].pop("county")
        R["mls"] = "Stellar"
        self.assertIn("no_county", run(R)[0]["warning_keys"])
        self.assertNotIn("no_county", run(texas(report()))[0]["warning_keys"])

    def test_payoff_and_holding_rate_are_assumptions(self):
        """CMA-269: the seller's payoff estimate and the assumed holding interest rate are listed in assumptions."""
        R = report()
        self.assertFalse([a for a in run(R)[0]["assumptions"] if "payoff" in a])
        R["costs"]["mortgage_payoff"] = 210000
        A = run(R)[0]["assumptions"]
        self.assertTrue(any("the seller's estimate" in a for a in A))
        self.assertTrue(any("assumed 4.5%" in a for a in A))
        R["costs"]["mortgage_rate"] = 6.25
        self.assertFalse(any("assumed 4.5%" in a for a in run(R)[0]["assumptions"]))

    def test_no_homestead_is_labeled(self):
        """CMA-270: outside Florida no exemption is applied, and the payment note says so."""
        R = texas(report())
        R["buyer_payment"].pop("note")  # the note script writes (a report's own note says it itself)
        C, homes = run(R)
        self.assertFalse(C["payments"]["homestead_applied"])
        self.assertTrue(any("no homestead exemption" in a for a in C["assumptions"]))
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(compute.labels(R)("pay_no_homestead_built_in"), doc)
        self.assertTrue(run(report())[0]["payments"]["homestead_applied"])

    def test_no_export_method_slide_counts_once(self):
        """CMA-271: without an export the method slide starts at the comps (no separate 'sales reviewed' step)."""
        with open(os.path.join(ROOT, "dev", "fixtures", "seller-cma", "deck", "hickorywood-deck.json")) as f:
            content = json.load(f)
        content["market_stats"] = [["Median Adjusted Value", "$450K", "chart"], ["Sales with Seller Credits", "2 of 3"]]
        R = texas(report())
        R["deck"] = content
        C, homes = run(R)
        self.assertIsNone(deck.deck_data(R, C, homes, AGENT, compute.labels(R), "footer")["method"]["n_sold"])
        R = report()
        C, homes = run(R)
        self.assertIsNotNone(deck.deck_data(R, C, homes, AGENT, compute.labels(R), "footer")["method"]["n_sold"])

    def test_rounded_differences_for_the_reply(self):
        """CMA-272: rounded differences come from compute; CMA-318: to $100 under $10,000, so "about" agrees with the
        exact figure beside it."""
        self.assertEqual(compute.about(6796), "about $6,800")
        self.assertEqual(compute.about(-3976), "about $4,000")
        self.assertEqual(compute.about(2240), "about $2,200")
        self.assertEqual(compute.about(3678), "about $3,700")  # the smoke test's spread read "about $3,500"
        self.assertEqual(compute.about(12345), "about $12,500")
        self.assertEqual(compute.about(61400), "about $61,000")
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, _ = run(R)
        self.assertEqual(C["strategies"][C["recommended_index"]]["net_vs_recommended_about"], "")
        for x in C["strategies"]:
            if not x["recommended"] and abs(x["net_vs_recommended"]) >= 250:
                self.assertIn(compute.about(x["net_vs_recommended"]), x["net_vs_recommended_about"])
        self.assertEqual(C["net_spread_about"], compute.about(C["net_spread"]))

    def test_page_one_stay_row_is_labeled(self):
        """CMA-273: page 1's options table reads 'Stay at $479,900' for a reprice's first option."""
        R = SecondPass.reprice(None)
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(compute.labels(R)("sum_stay", price="$479,900"), doc.split('<div class="pb">')[0])

    def test_page_checks(self):
        """CMA-274, CMA-276: a page under half full before a moved block, and a last page with a few lines, are Checks."""
        full = (0.9, "x")
        self.assertEqual(seller_render.page_checks([full, full, full]), [])
        checks = seller_render.page_checks([full, (0.34, "a"), (0.9, "Where Your Home Fits"), (0.1, "Sales data")])
        self.assertEqual(len(checks), 2)
        self.assertIn("Page 2 is only 34% full", checks[0])
        self.assertIn("Where Your Home Fits", checks[0])
        self.assertIn("last page (page 4)", checks[1])

    def test_page_fill_reads_the_pdf(self):
        """CMA-274: page fill and first lines come from the printed PDF."""
        render = seller_render.render
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext isn't installed here")
        doc = render.page('<div style="height:300px">Top line</div><div style="break-before:page">Second page</div>')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.pdf")
            render.html_to_pdf(doc, path, margins=compute.cma.PAGE_MARGINS)
            pages = seller_render.page_fill(path)
        self.assertEqual([p[1] for p in pages], ["Top line", "Second page"])
        self.assertLess(pages[1][0], 0.1)

    def test_notices_stay_with_the_method(self):
        """CMA-276: the closing notices are kept together with How This Was Prepared, never alone on a page."""
        R = report()
        C, homes = run(R)
        doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        tail = doc[doc.rindex('<div class="kg sec">'):]
        self.assertIn(L("h_method"), tail)
        self.assertIn('<div class="notices">', tail)
        self.assertIn("<footer>", tail)


EVAL_EXPORT = os.path.join(ROOT, "dev", "evals", "seller-cma", "files", "export-spring-oaks.csv")  # the home expired at $474,900


class FourthPass(unittest.TestCase):
    """Eval iteration 5 fixes (CMA-277 to CMA-286)."""

    def test_relist_caps_the_options(self):
        """CMA-277: after the home's own listing ended unsold, no option lists above that price without a reason."""
        R = report()
        R["relist"] = {"failed_price": 474900, "status": "expired", "days_on_market": 92}
        with self.assertRaisesRegex(compute.ReportError, "relist.reason_above"):
            run(R)  # the fixture's top-of-range option is $479,900
        R["relist"]["reason_above"] = "The kitchen and baths were redone after that listing ended."
        self.assertEqual(run(R)[0]["relist"]["failed_price"], 474900)
        R = report()
        R["relist"] = {"failed_price": 474900}
        R["pricing"]["strategies"][0]["list_price"] = 474900  # capped at the failed price
        C, _ = run(R)
        self.assertEqual((C["relist"]["source"], C["placeholders"]["failed_price"]), ("report", "$474,900"))

    def test_relist_found_in_the_export(self):
        """CMA-277: without `relist`, compute.py finds the home's expired listing in the export; stats.py prints it."""
        R = report()
        R["export"] = EVAL_EXPORT
        with self.assertRaises(compute.ReportError):
            run(R)
        R["pricing"]["strategies"][0]["list_price"] = 474900
        C, _ = run(R)
        self.assertEqual((C["relist"]["failed_price"], C["relist"]["status"], C["relist"]["source"]), (474900, "expired", "export"))
        self.assertIsNone(run(report())[0]["relist"])  # the fixture's export has the home active, not failed
        with contextlib.redirect_stdout(io.StringIO()) as out:
            stats_mod.main([EVAL_EXPORT, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar",
                            "--state", "FL", "--county", "Seminole"])
        r = json.loads(out.getvalue())
        self.assertEqual((r["relist"]["failed_price"], r["relist"]["status"], r["mls"]), (474900, "expired", "Stellar"))
        self.assertNotIn("relist", SecondPass.stats(None, [SecondPass.subject_row(None, "ACT")], "--own-listing"))

    def test_reprice_is_not_a_relist(self):
        """CMA-277: a reprice has its own rule (Stay plus cuts), so an earlier failed listing isn't checked again."""
        R = SecondPass.reprice(None, current=474900)
        R["relist"] = {"failed_price": 469900}
        self.assertIsNone(run(R)[0]["relist"])

    def test_new_placeholders(self):
        """CMA-278: the rounded spread, the adjusted span, a reprice's current price and a relist's failed price."""
        R = report()
        R["comps"]["summary_paragraph"] = ("They run from {adjusted_min} to {adjusted_max}; the options are within "
                                           "{net_spread_about}.")
        C, homes = run(R)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(f"They run from {compute.money(C['adjusted_min'])} to {compute.money(C['adjusted_max'])}; the options "
                      f"are within {C['net_spread_about']}.", doc)
        R["means"] = ["It has sat at {current_price}.", "It expired at {failed_price}."]
        self.assertEqual(run(R)[0]["warning_keys"].count("unfilled_placeholder"), 2)  # neither a reprice nor a relist
        R = SecondPass.reprice(None)
        R["means"] = ["It has sat at {current_price}."]
        C, _ = run(R)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        self.assertEqual(C["placeholders"]["current_price"], "$479,900")

    def test_higher_option_netting_more_warns(self):
        """CMA-280: the top-of-range option, or a reprice's Stay, netting more than the recommended one is a warning."""
        self.assertFalse({"top_nets_more", "stay_nets_more"} & set(run(report())[0]["warning_keys"]))
        R = report()
        R["pricing"]["strategies"][0]["expected_sale"] = 470000
        self.assertIn("top_nets_more", run(R)[0]["warning_keys"])
        R = SecondPass.reprice(None)
        R["pricing"]["strategies"][0]["expected_sale"] = 475000
        R["pricing"]["strategies"][0]["time"] = "1–2 months"
        self.assertIn("stay_nets_more", run(R)[0]["warning_keys"])

    def test_stay_expected_sale_rule(self):
        """CMA-280: Stay's expected sale by one rule (current price × the ratio of sales that sat as long, or the median
        adjusted value if lower, plus its credit); a higher one warns."""
        R = SecondPass.reprice(None)
        C, _ = run(R)
        rp = C["reprice"]
        credit = R["pricing"]["strategies"][0]["seller_credit"]
        expected = min(479900 * rp["stay_ratio"], C["median_adjusted"]) + credit
        self.assertAlmostEqual(rp["stay_expected_sale"], expected, delta=600)
        self.assertGreaterEqual(rp["stay_ratio_sales"], 3)
        R["pricing"]["strategies"][0]["expected_sale"] = rp["stay_expected_sale"] + 5000
        self.assertIn("stay_expected_high", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"][0]["expected_sale"] = rp["stay_expected_sale"]
        self.assertNotIn("stay_expected_high", run(R)[0]["warning_keys"])
        R = texas(SecondPass.reprice(None))  # no export: nothing to derive it from
        self.assertNotIn("stay_expected_sale", run(R)[0]["reprice"])

    def test_template_net_matches_the_comparison(self):
        """CMA-281: the chat template's Est. Net column is on the same basis (after holding) as the comparison line."""
        with open(os.path.join(SKILL, "assets", "seller-cma-template.md")) as f:
            template = f.read()
        self.assertIn("net_after_holding_display", template)
        self.assertNotRegex(template, r"expected_sale_display, net_display")
        C, _ = run(report())
        self.assertEqual([x["net_after_holding"] - C["strategies"][C["recommended_index"]]["net_after_holding"]
                          for x in C["strategies"]], [x["net_vs_recommended"] for x in C["strategies"]])

    def test_no_state_with_a_state_mls(self):
        """CMA-282: no state, a Stellar export: national estimates, Preliminary, and what Florida would change."""
        R = report()
        for k in ("state", "county"):
            R["subject"].pop(k)
        R["mls"] = "Stellar"
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertEqual(C["state_hint"]["state"], "FL")
        self.assertIn("state_unknown", C["assumption_keys"])
        self.assertIn("0.70%", C["state_hint"]["transfer_tax_label"])
        self.assertNotEqual(C["state_hint"]["transfer_tax_label"], C["state_hint"]["estimate_label"])
        C, _ = run(report())
        self.assertIsNone(C["state_hint"])
        self.assertNotIn("state_unknown", C["assumption_keys"])

    def test_texas_default_homestead_takes_nothing_off(self):
        """CMA-283: buyer_payment.homestead left at its default (true) never applies Florida's exemption to Texas."""
        R = texas(report())
        R["buyer_payment"].pop("homestead", None)
        default = run(R)[0]["payments"]
        R["buyer_payment"]["homestead"] = False
        self.assertEqual([r["payment"] for r in default["rows"]], [r["payment"] for r in run(R)[0]["payments"]["rows"]])
        self.assertFalse(default["homestead_applied"])
        R = report()  # Florida: the exemption lowers the payment
        home = run(R)[0]["payments"]["rows"]
        R["buyer_payment"]["homestead"] = False
        self.assertGreater(run(R)[0]["payments"]["rows"][0]["payment"], home[0]["payment"])

    def test_value_driver_dollars_come_from_adjustments(self):
        """CMA-284: a value driver's dollar figure must be one of the report's comp adjustments."""
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        self.assertNotIn("driver_amount", run(R)[0]["warning_keys"])
        R["deck"]["value_drivers"][1][1] = "Worth about $25,000 against similar homes without one."
        self.assertEqual(run(R)[0]["warning_keys"].count("driver_amount"), 1)
        R["deck"]["value_drivers"][1][1] = "Worth $30,000 to $45,000 against the partly updated sales."
        self.assertNotIn("driver_amount", run(R)[0]["warning_keys"])

    def test_render_checks(self):
        """CMA-285: 'still left, a line lower' for a label that only moved a line; the comp table apart from its cards
        and a method-only last page are Checks (the last only when a modest cut brings it back)."""
        _, notes = seller_render.scatter_checks({"labels_moved": [("Your Home", "left", "left, a line lower"),
                                                                  ("749 Cedar Ln W", "below", "right")]})
        self.assertIn("Your Home (still left, a line lower)", notes[0])
        self.assertIn("749 Cedar Ln W (below to right)", notes[0])
        self.assertNotIn("left to left", notes[0])
        L = compute.labels(report())
        head = " ".join(L(k) for k in ("th_sale", "th_sold_for", "th_seller_paid", "th_adjusted"))
        pages = [(0.9, "Seller Summary"), (0.8, "The Home"), (0.97, head), (0.77, "Before We List"), (0.37, L("h_method"))]
        checks = seller_render.page_checks(pages, L)
        self.assertEqual(len(checks), 2)
        self.assertIn("page 3", checks[0])
        self.assertIn("page 5", checks[1])
        pages[3] = (0.93, "Before We List")  # a full page before it: no cut would bring the method back
        self.assertEqual(len(seller_render.page_checks(pages, L)), 1)
        self.assertEqual(seller_render.page_checks(pages), cma_page_checks(pages))

    def test_reprice_asks_for_the_listing_agreement(self):
        """CMA-286: a reprice without brokerage terms assumes 5% and asks for the listing agreement's commission."""
        R = SecondPass.reprice(None)
        R["costs"] = {}  # no terms given
        C, _ = run(R)
        self.assertIn("brokerage_listing_agreement", C["assumption_keys"])
        self.assertNotIn("brokerage_assumed", C["assumption_keys"])
        R = report()
        R["costs"] = {}
        self.assertIn("brokerage_assumed", run(R)[0]["assumption_keys"])
        R = SecondPass.reprice(None)  # the fixture's own terms
        self.assertFalse({"brokerage_listing_agreement", "brokerage_assumed"} & set(run(R)[0]["assumption_keys"]))
        self.assertEqual(len(C["assumptions"]), len(C["assumption_keys"]))


EVAL_ACTIVE = os.path.join(ROOT, "dev", "evals", "seller-cma", "files", "export-spring-oaks-active.csv")  # listed at $474,900


class FifthPass(unittest.TestCase):
    """Eval iteration 6 fixes (CMA-287 to CMA-292)."""

    def test_reprice_price_history(self):
        """CMA-287: stats.py prints the reprice with the original price; compute.py carries it (from report.json or the
        export) into the price history, the {original_price} placeholder and the Bottom Line."""
        with contextlib.redirect_stdout(io.StringIO()) as out:
            stats_mod.main([EVAL_ACTIVE, "--address", "517 HICKORYWOOD AVE", "--sqft", "1849", "--mls", "Stellar",
                            "--state", "FL", "--county", "Seminole", "--own-listing"])
        r = json.loads(out.getvalue())
        self.assertEqual(r["reprice"], {"current_price": 474900, "days_on_market": 36, "original_price": 484900})
        R = SecondPass.reprice(None, current=474900)
        R["export"] = EVAL_ACTIVE
        R["reprice"]["days_on_market"] = 36  # no original_price: found in the export's own row
        R["means"] = ["It started at {original_price}."]
        C, homes = run(R)
        self.assertEqual((C["reprice"]["original_price"], C["placeholders"]["original_price"]), (484900, "$484,900"))
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        self.assertIn("$484,900", C["reprice"]["price_history"])
        self.assertIn("$474,900", C["reprice"]["price_history"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(C["reprice"]["price_history"], doc)
        R = SecondPass.reprice(None, current=474900)
        R.pop("export")
        R["reprice"]["original_price"] = 484900  # given, with no export
        self.assertEqual(run(R)[0]["reprice"]["original_price"], 484900)
        R["reprice"]["original_price"] = 474900  # no cut: no history of one
        C, _ = run(R)
        self.assertIsNone(C["reprice"]["original_price"])
        self.assertNotIn("original_price", C["placeholders"])

    def test_relist_price_history(self):
        """CMA-287: a relist's original price comes from the export when report.json's relist leaves it out."""
        R = report()
        R["export"] = EVAL_EXPORT
        R["relist"] = {"failed_price": 474900, "status": "expired", "days_on_market": 92}
        R["pricing"]["strategies"][0]["list_price"] = 474900
        C, _ = run(R)
        self.assertEqual((C["relist"]["original_price"], C["placeholders"]["original_price"]), (484900, "$484,900"))
        self.assertIn("92", C["relist"]["price_history"])

    def test_top_option_near_the_recommendation(self):
        """CMA-288: a relist cap that leaves the top option within 1% of the recommended price warns; two options don't."""
        R = report()
        R["relist"] = {"failed_price": 474900}
        R["pricing"]["strategies"][0]["list_price"] = 472900
        self.assertIn("top_near_recommended", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"][0]["list_price"] = 474900  # just over 1% above $469,900
        self.assertNotIn("top_near_recommended", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"].pop(0)
        R["pricing"]["recommended_index"] = 0
        C, _ = run(R)
        self.assertNotIn("top_near_recommended", C["warning_keys"])
        self.assertEqual(len(C["strategies"]), 2)

    def test_adjusted_values_round_to_100(self):
        """CMA-289: adjusted values show to $100 in the placeholders, table and cards; the math stays exact."""
        R = report()  # 621 Little Wekiva Rd has a $13,071 seller credit; a round size adjustment leaves $436,229
        R["comps"]["cards"][4]["adjustments"][1]["amount"] = -1200
        R["comps"]["summary_paragraph"] = "From {adjusted_min} to {adjusted_max}, median {median_adjusted}."
        C, homes = run(R)
        exact = [c["adjusted"] for c in R["comps"]["cards"]]
        self.assertTrue(any(v % 100 for v in exact))
        self.assertEqual(C["adjusted_min"], min(exact))
        for v in [C["placeholders"][k] for k in ("adjusted_min", "adjusted_max", "median_adjusted")] + [
                r["adjusted_display"] for r in C["comps_table"]]:
            self.assertTrue(v.endswith("00"), v)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        for v in exact:
            if v % 100:
                self.assertNotIn(compute.money(v), doc)
                self.assertIn(compute.money(v, 100), doc)

    def test_bottom_option_netting_more_warns(self):
        """CMA-290: the competing-offer option netting more than the recommended one warns, unless pricing.note says
        its net rests on competing offers (competing_offer_upside)."""
        R = report()
        self.assertNotIn("bottom_nets_more", run(R)[0]["warning_keys"])  # the fixture's note says so
        R["pricing"].pop("competing_offer_upside")
        self.assertIn("bottom_nets_more", run(R)[0]["warning_keys"])
        R["pricing"]["strategies"][2].update(expected_sale=452000, seller_credit=10000)
        self.assertNotIn("bottom_nets_more", run(R)[0]["warning_keys"])

    def test_stay_rule_wording_and_rate_citation(self):
        """CMA-290, CMA-291, CMA-292: method.md says the Stay figure already includes the credit and covers a cut inside
        one search bracket; the rate is cited from Freddie Mac's PMMS page."""
        with open(os.path.join(SKILL, "references", "method.md")) as f:
            method = f.read()
        self.assertIn("with the credit already in it", method)
        self.assertNotIn("plus Stay's seller credit", method)
        self.assertIn("A cut inside the same search bracket", method)
        with open(os.path.join(SKILL, "SKILL.md")) as f:
            self.assertIn("freddiemac.com/pmms", f.read())


class SixthPass(unittest.TestCase):
    """Eval iteration 7 fixes (CMA-298 to CMA-301)."""

    def test_pdf_nets_match_the_reply_basis(self):
        """CMA-298: page 1, the pricing table and the tile show the nets the reply's differences compare (after holding)."""
        R = SecondPass.reprice(None)
        C, homes = run(R)
        self.assertEqual(C["net_basis"], "after_holding")
        ri = C["recommended_index"]
        self.assertEqual(C["recommended_net_display"], C["strategies"][ri]["net_after_holding_display"])
        self.assertEqual(C["placeholders"]["recommended_net"], C["strategies"][ri]["net_after_holding_display"])
        doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        for x in C["strategies"]:
            self.assertNotEqual(x["net_display"], x["net_after_holding_display"])
            self.assertEqual(doc.count(f'<td class="n">{x["net_after_holding_display"]}</td>'), 3)  # page 1, pricing, net sheet's last row
            self.assertEqual(doc.count(f'<td class="n">{x["net_display"]}</td>'), 1)  # the net sheet's total only
        self.assertIn(L("sum_options_note_holding"), doc)
        self.assertIn(L("pricing_note_holding"), doc)
        self.assertIn(L("sum_net_tile_holding", price=C["recommendation"]["list_price_display"]), doc)
        nets = [x["net_after_holding"] for x in C["strategies"]]
        self.assertEqual([x["net_vs_recommended"] for x in C["strategies"]], [v - nets[ri] for v in nets])

    def test_callout_off_the_chart_is_a_check(self):
        """CMA-299: a callout whose home isn't plotted (pending, or not in the export) is named, never dropped silently."""
        R = report()
        C, homes = run(R)
        comps = {" ".join(cd["address"].upper().split()) for cd in R["comps"]["cards"]}
        pend = next(h for h in homes if h["status"] == "SOLD" and h.get("living_area")
                    and " ".join(h["address"].upper().split()) not in comps)
        pend["status"] = "PENDING"
        R["scatter"]["callouts"] = R["scatter"]["callouts"][:1] + [
            {"address": pend["address"], "label": "Pending Sale", "side": "right"},
            {"address": "1 NOWHERE LN", "label": "Missing", "side": "left"}]
        seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertEqual(C["render_check_keys"].count("callout_not_plotted"), 2)
        self.assertEqual(len(C["render_checks"]), len(C["render_check_keys"]))
        dropped = [c for c, k in zip(C["render_checks"], C["render_check_keys"]) if k == "callout_not_plotted"]
        self.assertIn("Pending Sale", dropped[0])
        self.assertIn("pending", dropped[0])
        self.assertIn("not found in the export", dropped[1])
        _, info = compute.cma.scatter(homes, {**R["scatter"], "subject_label": "Your Home"}, 1849,
                                      R["recommendation"]["list_price"], R["subject"]["mls_address"],
                                      (R["recommendation"]["low"], R["recommendation"]["high"]), compute.labels(R))
        self.assertEqual([d[2] for d in info["callouts_dropped"]], ["pending", "not_in_export"])
        R = report()  # the fixture's own callouts are all plotted
        C, homes = run(R)
        seller_render.build_html(R, C, homes, AGENT)
        self.assertNotIn("callout_not_plotted", C.get("render_check_keys", []))

    def test_stay_expected_sale_is_filled_by_the_rule(self):
        """CMA-300: a reprice's Stay without expected_sale gets the rule's figure on the first run, no warning."""
        R = SecondPass.reprice(None)
        rule = run(copy.deepcopy(R))[0]["reprice"]["stay_expected_sale"]
        R["pricing"]["strategies"][0].pop("expected_sale")
        C, _ = run(R)
        self.assertEqual(C["strategies"][0]["expected_sale"], rule)
        self.assertTrue(C["reprice"]["stay_expected_filled"])
        self.assertNotIn("stay_expected_high", C["warning_keys"])
        R = texas(SecondPass.reprice(None))  # no export: nothing to fill it from
        R["pricing"]["strategies"][0].pop("expected_sale")
        with self.assertRaises(compute.ReportError):
            run(R)
        R = report()  # Results_v4: any option may leave it out; the rule fills it
        R["pricing"]["strategies"][0].pop("expected_sale")
        self.assertEqual(run(R)[0]["strategies"][0]["expected_sale_source"], "rule")

    def test_method_time_adjustment_base_and_no_tildes(self):
        """CMA-301: the time adjustment's base is the sale price minus seller-paid costs; no "~" in the references."""
        with open(os.path.join(SKILL, "references", "method.md")) as f:
            self.assertIn("on its price net of seller-paid costs", f.read())  # Results_v5: the script applies it
        for folder in ("references", "assets"):
            for name in os.listdir(os.path.join(SKILL, folder)):
                with open(os.path.join(SKILL, folder, name), encoding="utf-8") as f:
                    self.assertNotIn("~", f.read(), name)


def cma_page_checks(pages):
    return seller_render.cma.page_checks(pages, "the needs list, the launch steps or the method")


if __name__ == "__main__":
    unittest.main()


class SeventhPass(unittest.TestCase):
    """CMA-303: a live listing that isn't the agent's is the agent's choice (failed or history); failed listings older
    than 12 months set no cap in the scripts either."""

    def test_live_listing_as_failed(self):
        r = SecondPass.stats(None, [SecondPass.subject_row(None, "PND")], "--state", "FL", "--county", "Seminole",
                             "--listed-as", "failed")
        self.assertEqual(r["listed_now_action"], "relist")
        self.assertEqual((r["relist"]["failed_price"], r["relist"]["status"], r["relist"]["original_price"]),
                         (474900, "pending", 484900))
        self.assertNotIn("reprice", r)

    def test_live_listing_as_history(self):
        r = SecondPass.stats(None, [SecondPass.subject_row(None, "ACT")], "--state", "FL", "--county", "Seminole",
                             "--listed-as", "history")
        self.assertEqual(r["listed_now_action"], "history")
        self.assertNotIn("relist", r)
        self.assertNotIn("reprice", r)

    def test_one_choice_only(self):
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            SecondPass.stats(None, [SecondPass.subject_row(None, "ACT")], "--own-listing", "--listed-as", "failed")

    def test_old_failed_listing_sets_no_cap(self):
        old = SecondPass.subject_row(None, "EXP")
        old[8] = "09/30/2017"
        r = SecondPass.stats(None, [old], "--state", "FL", "--county", "Seminole", "--as-of", "2026-09-26")
        self.assertNotIn("relist", r)
        recent = SecondPass.subject_row(None, "EXP")
        recent[8] = "03/15/2026"
        r = SecondPass.stats(None, [recent], "--state", "FL", "--county", "Seminole", "--as-of", "2026-09-26")
        self.assertEqual(r["relist"]["failed_price"], 474900)

    def test_ended_within(self):
        from datetime import date
        self.assertTrue(compute.mls.ended_within({"close_date": date(2026, 1, 5)}, date(2026, 9, 26)))
        self.assertFalse(compute.mls.ended_within({"close_date": date(2017, 9, 30)}, date(2026, 9, 26)))
        self.assertTrue(compute.mls.ended_within({}, date(2026, 9, 26)))  # undated counts

    def test_live_failed_price_history_wording(self):
        L = compute.labels(report())
        text = compute.price_history(L, relist={"failed_price": 474900, "status": "pending", "days_on_market": 36,
                                                "original_price": 484900})
        self.assertIn("went under contract after 36 days, but the sale didn't close", text)
        self.assertNotIn("hasn't sold", text)
        text = compute.price_history(L, relist={"failed_price": 474900, "status": "active"})
        self.assertEqual(text, "The listing at $474,900 didn't sell.")


class EighthPass(unittest.TestCase):
    """Owner's manual smoke test, 842 Tanager Ridge Dr (CMA-317 to CMA-324)."""

    def test_after_holding_net_is_never_called_cash_at_closing(self):
        """CMA-317: the tile, the option tables' headers and the deck's net subtitle show the after-holding net, so
        they name it as the net sheet's "Net After Holding Costs" row does, never "cash at closing" (its own row)."""
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, homes = run(R)
        self.assertEqual((C["net_basis"], C["net"]["cash_at_closing"]), ("after_holding", True))
        doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(L("sum_cash_tile_holding", price=C["recommendation"]["list_price_display"]), doc)
        self.assertNotIn("Cash at Closing at", doc)
        self.assertNotIn(L("th_est_cash"), doc)
        self.assertNotIn(L("th_cash"), doc)
        self.assertEqual([r["key"] for r in C["net"]["rows"]][-3:], ["total", "holding", "after_holding"])
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, L, "footer")
        self.assertTrue(D["net_sub"].startswith(L("deck_cash_holding_sub")))
        self.assertNotIn("cash at closing", D["net_sub"].lower())

    def test_spread_about_agrees_with_the_exact_spread(self):
        """CMA-318: {net_spread_about} is within $50 of {net_spread} under $10,000."""
        C, _ = run(report())
        spread = C["net_spread"]
        self.assertLess(spread, 10000)
        about = int(C["net_spread_about"].replace("about $", "").replace(",", ""))
        self.assertLessEqual(abs(about - spread), 50)

    def test_competing_offer_caveat_on_page_one(self):
        """CMA-319: the competing-offer option netting more than the recommended one gets its caveat on page 1."""
        R = report()
        C, homes = run(R)
        nets = [x["net_after_holding"] for x in C["strategies"]]
        self.assertGreater(nets[2], nets[C["recommended_index"]])  # the fixture's competing-offer option nets more
        self.assertEqual(C["competing_offer_caveat"], 2)
        doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        caveat = L("sum_options_note_competing", price=C["strategies"][2]["list_price_display"])
        self.assertIn(caveat, doc[:doc.index(L("h_home"))])  # page 1
        R["pricing"]["strategies"][2].update(expected_sale=452000, seller_credit=10000)  # now it nets less
        C, homes = run(R)
        self.assertIsNone(C["competing_offer_caveat"])
        doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertNotIn(caveat, doc)

    def test_months_supply_placeholder(self):
        """CMA-320: months of supply comes from stats.py through {months_supply}; a typed figure stops the render
        (Results_v4: like any typed stat)."""
        R = report()
        C, homes = run(R)
        self.assertEqual(C["placeholders"]["months_supply"], compute.months_text(C["handoff"]["market"]["months_supply"]))
        self.assertNotIn("months_supply_typed", C["warning_keys"])
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(f'about {C["placeholders"]["months_supply"]} of supply', doc)
        R["market"]["bullets"][2] = "Only five homes are for sale nearby, about a month and a half of supply."
        with self.assertRaisesRegex(compute.ReportError, r"market\.bullets\[2\]: states months of supply.*→ write \{months_supply\}"):
            run(R)
        R["market"]["bullets"][2] = "Buyers have plenty of inventory to choose from."  # no figure: nothing typed
        run(R)
        self.assertEqual((compute.months_text(1.3), compute.months_text(1.0)), ("1.3 months", "1 month"))

    def test_method_note_adjustments_are_short_and_once_each(self):
        """CMA-321: "original hall bath, older roof, size, kitchen, hall bath and floors, remodeled primary bath" named
        the hall bath twice."""
        mk = lambda *labels: {"adjustments": [{"label": x, "amount": 5000} for x in labels], "seller_concessions": 5000}
        cards = [mk("Original Hall Bath", "Older Roof", "Size"),
                 mk("Kitchen, Hall Bath and Floors", "Remodeled Primary Bath", "Market Since the Sale")]
        self.assertEqual(deck.adjustment_words(cards),
                         "condition and updates, roof and systems, size, market changes since each sale and seller credits")

    def test_higher_price_never_expects_a_lower_sale(self):
        """CMA-323: $399,900 expected to sell for less than $394,900 warns."""
        R = report()
        self.assertNotIn("expected_sale_order", run(R)[0]["warning_keys"])
        top, rec = R["pricing"]["strategies"][0], R["pricing"]["strategies"][1]
        top["expected_sale"] = rec["expected_sale"] - 1000
        self.assertIn("expected_sale_order", run(R)[0]["warning_keys"])

    def test_data_date_written_out(self):
        """CMA-325: the chat template's data date reads "September 26, 2026", not the ISO form; the agent's stated date
        sets as_of and prepared_date."""
        R = report()
        R["as_of"] = "2026-09-26"
        C, _ = run(R)
        self.assertEqual(C["data_source"]["as_of_display"], "September 26, 2026")
        with open(os.path.join(SKILL, "assets", "seller-cma-template.md")) as f:
            self.assertIn("{{data_source.as_of_display}}", f.read())
        with open(os.path.join(SKILL, "SKILL.md")) as f:
            self.assertIn("When the agent states today's date", f.read())


def resolve(C, path):
    """A template path ("summary_page.first_steps") in compute.py's output, or KeyError."""
    v = C
    for part in path.split("."):
        v = v[part]
    return v


class ChatTemplate(unittest.TestCase):
    """The chat template follows page 1 of the PDF, from compute.py's output alone (CMA-332 to CMA-342)."""

    def template(self):
        with open(os.path.join(SKILL, "assets", "seller-cma-template.md")) as f:
            return f.read()

    def test_every_template_path_is_in_compute_output(self):
        """CMA-332, CMA-333: the template reads the filled prose (recommendation_paragraph, summary_page) and every
        other path from compute.py's output, never report.json's unfilled copies."""
        text = self.template()
        self.assertNotIn("recommendation.paragraph", text)
        C, _ = run(report())
        paths = ["subject.address", "preliminary_reason", "recommendation.list_price_display", "recommendation.range_display",
                 "recommendation.expected_sale", "summary_page.headline", "recommendation_paragraph", "summary_page.why",
                 "expected_sale_basis.note",
                 "median_adjusted_display", "comps_table", "options_summary.net_header",
                 "net.incomplete", "options_summary.note", "payments.per_10k_display", "net.notes", "net_spread_about",
                 "payments.basis_note", "payments.flood.annual", "payments.flood.required", "first_steps_heading",
                 "summary_page.first_steps", "summary_page.next_step", "data_source.as_of_display"]
        for p in paths:
            self.assertIn(p, text)
            resolve(C, p)
        for p in ("recommendation_paragraph", "summary_page"):
            self.assertNotRegex(json.dumps(resolve(C, p)), r"\{(median_adjusted|list_price|low|high|per_10k)\}")
        self.assertTrue(all(len(step) == 2 for step in C["summary_page"]["first_steps"]))  # CMA-334: [heading, detail]
        self.assertIn("{{summary_page.first_steps[0][0]}}", text)

    def test_comps_table_has_the_seller_paid_column(self):
        """CMA-339: the chat comps table carries the report's Seller Paid column."""
        R = report()
        C, _ = run(R)
        paid = [compute.money(c["seller_concessions"]) for c in R["comps"]["cards"]]
        self.assertEqual(sorted(r["seller_paid_display"] for r in C["comps_table"]), sorted(paid))
        L = compute.labels(R)
        self.assertIn(f'| {L("th_sale")} | {L("th_sold_for")} | {L("th_seller_paid")} | {L("th_adjusted")} |', self.template())

    def test_options_summary_matches_page_one(self):
        """CMA-336: the net column's header and footnote come from compute.py, in page 1's own words, by basis."""
        L = compute.labels(report())
        cases = [({}, "sum_options_note_holding"), ({"mortgage_payoff": 0}, "sum_options_note_free_holding"),
                 ({"mortgage_payoff": 210000}, "sum_options_note_cash_holding")]
        for costs, note in cases:
            R = report()
            R["costs"].update(costs)
            C, homes = run(R)
            opts = C["options_summary"]
            self.assertEqual(opts["net_header"], L("th_est_net"))  # after holding costs the column is a net (CMA-317)
            self.assertTrue(opts["note"].startswith(L(note)), opts["note"])
            self.assertIn(L("sum_options_note_competing", price=C["strategies"][2]["list_price_display"]), opts["note"])
            doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
            self.assertIn(opts["note"], doc)
        C["net_basis"] = "net"  # no holding costs, with a payoff: the column is the net sheet's cash at closing
        self.assertEqual(compute.options_summary(C, L)["net_header"], L("th_est_cash"))
        self.assertTrue(compute.options_summary(C, L)["note"].startswith(L("sum_options_note_cash")))

    def test_payment_basis_line(self):
        """CMA-338: the buyer-payment basis is compute.py's, the same words the report prints before its flood note."""
        R = report()
        R["buyer_payment"].pop("note", None)
        C, homes = run(R)
        pay = C["payments"]
        L = compute.labels(R)
        self.assertTrue(pay["basis_note"].startswith(L("prog_" + pay["loan_type"]) + " loan"), pay["basis_note"])
        self.assertIn(pay["tax_basis"], pay["basis_note"])
        self.assertNotIn(pay["flood"]["note"], pay["basis_note"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(pay["basis_note"] + " " + pay["flood"]["note"], doc)

    def test_template_follows_page_one(self):
        """CMA-335, CMA-337, CMA-340, CMA-341, CMA-342: the Stay row, no brokerage label (a default), the estimates line, the
        headline and the title."""
        text = self.template()
        self.assertIn("reprice.stay_index", text)
        self.assertIn('"Stay at " + list_price_display', text)
        self.assertNotIn("Assumed Brokerage", text)  # local-costs.md: a default commission gets no label
        self.assertIn("Payment, tax and cost figures are estimates only, not lending or tax advice", text)
        self.assertIn("{{summary_page.headline", text)
        self.assertTrue(text.startswith("## {{subject.address}}: Seller Summary"))
        R = report()
        R["costs"] = {}
        self.assertTrue(run(R)[0]["net"]["standard_terms"])



class ResultsV4(unittest.TestCase):
    """Results_v4 case 02: script-owned values, typed data that stops the render, and the layout fixes."""

    def no_typed(self):
        R = report()
        for x in R["pricing"]["strategies"]:
            x.pop("expected_sale")
        return R

    def test_expected_sale_rule(self):
        """List x the recent sale-to-final-list ratio plus the option's credit, to $500, never below the range; the top
        option expects the recommended one's sale; page 1 and slide 2 say "About ..." from the recommended option,
        never typed."""
        R = self.no_typed()
        C, homes = run(R)
        ratio = C["expected_sale_basis"]["ratio"]
        top, rec, low = C["strategies"]
        floor = R["recommendation"]["low"]
        for x, cap in ((rec, rec["list_price"]), (low, R["recommendation"]["high"])):  # the last is the competing option
            rule = round((x["list_price"] * ratio + x["seller_credit"]) / 500) * 500
            self.assertEqual(x["expected_sale"], min(max(rule, floor), cap))
            self.assertEqual(x["expected_sale_source"], "rule")
        self.assertEqual(top["expected_sale"], rec["expected_sale"])  # a higher price buys time, not a higher sale
        self.assertEqual(C["recommendation"]["expected_sale"], "About " + rec["expected_sale_display"])
        self.assertIn(f"{ratio * 100:.1f}%", C["expected_sale_basis"]["method"])
        again, _ = run(R)  # the same data, run again (render.py runs compute once per format): the same figures
        self.assertEqual([x["expected_sale"] for x in again["strategies"]], [x["expected_sale"] for x in C["strategies"]])
        R["summary_page"]["expected_sale"] = "Upper $380,000s to about $390,000"  # a typed phrase is never shown
        C, _ = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertNotIn("Upper $380,000s", doc)
        self.assertIn("About " + rec["expected_sale_display"], doc)
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        self.assertEqual(D["expected_sale"], "About " + rec["expected_sale_display"])

    def test_expected_sale_caps_and_agent_figure(self):
        R = texas(self.no_typed())
        R["market"]["sale_to_list"] = 1.05  # a hot market's ratio: still never above list (but the last) or the range
        C, _ = run(R)
        self.assertEqual(C["expected_sale_basis"]["source"], "report")
        high = R["recommendation"]["high"]
        for i, x in enumerate(C["strategies"]):
            self.assertLessEqual(x["expected_sale"], high)
            if i < 2:
                self.assertLessEqual(x["expected_sale"], x["list_price"])
        self.assertIn("never above the list price", C["expected_sale_basis"]["method"])
        R = report()  # a typed figure is the agent's own, and the report says so
        R["pricing"]["strategies"][2].pop("expected_sale")
        C, _ = run(R)
        self.assertEqual([x["expected_sale_source"] for x in C["strategies"]], ["agent", "agent", "rule"])
        self.assertIn("$479,900 and $469,900 options' expected sales are our own estimates", C["expected_sale_basis"]["note"])

    def test_no_ratio_is_assumed(self):
        C, _ = run(texas(self.no_typed()))
        self.assertEqual(C["expected_sale_basis"]["source"], "assumed")
        self.assertIn("expected_sale_ratio", C["assumption_keys"])

    def test_typed_stats_stop_with_every_problem(self):
        R = report()
        R["summary_page"]["key_stats"][1][0] = "95.2%"
        R["market"]["rows"][2][2] = "30"
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        msg = str(e.exception)
        self.assertIn("2 things to fix", msg)
        self.assertIn('summary_page.key_stats[1][0]: "95.2%"', msg)
        self.assertIn("→ write {sale_to_list_recent}", msg)
        self.assertIn('market.rows[2][2]: "30"', msg)
        self.assertIn("{days_recent}", msg)

    def test_market_table_and_stats_come_from_the_export(self):
        R = report()
        R["market"].pop("rows"), R["market"].pop("columns"), R["summary_page"].pop("key_stats")
        C, homes = run(R)
        n = C["market_numbers"]
        self.assertEqual(C["market_table"]["columns"], ["", "April–June", "July–September"])
        self.assertIn(["Typical Sale vs. Original Asking Price", n["sale_to_list_early"], n["sale_to_list_recent"]],
                      C["market_table"]["rows"])
        self.assertEqual(C["key_stats"][1][0], n["sale_to_list_recent"])
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        R["deck"].pop("market_stats")
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        self.assertEqual(D["content"]["market_stats"][0][1:3], [n["sale_to_list_early"], n["sale_to_list_recent"]])

    def test_split_month_is_the_periods(self):
        R = report()
        R["market"]["intro"] = "Homes sold since August took longer to sell than in the spring."
        with self.assertRaisesRegex(compute.ReportError, r'market\.intro: says "since August".*if this sentence compares '
                                    r'the two periods, write "since \{split_month\}".*if it means another date'):
            run(R)
        R["market"]["intro"] = "Homes sold since {split_month} took longer to sell than in the spring."
        # iteration 12: a time adjustment's own cutoff is not the market split, in the method note or anywhere else
        R["comps"]["time_adjustment"]["cutoff"] = "2026-08-01"
        R["comps"]["method_note"] = "About 1% per quarter off sales from before August, since prices softened."
        R["comps"]["intro"] = "Sales from before August are adjusted down for the softer market."
        run(R)
        R["summary_page"]["why"][0] = "The home has sat since January without an offer."  # not a period boundary
        self.assertEqual(run(R)[0]["placeholders"]["split_month"], "July")

    def test_launch_plan_steps_come_from_the_report(self):
        R = report()
        with open(R["deck"]) as f:
            R["deck"] = json.load(f)
        R["deck"]["launch_plan"].append(["Professional Staging", "A stager furnishes every room", "staging"])
        with self.assertRaisesRegex(compute.ReportError, r'deck\.launch_plan\[\d\]: "Professional Staging" isn\'t one of'):
            run(R)
        R["deck"]["launch_plan"].pop()
        run(R)

    def test_adjustment_kinds(self):
        R = report()
        R["comps"]["cards"][0]["adjustments"][0]["kind"] = "vibes"
        with self.assertRaisesRegex(compute.ReportError, r"comps\.cards\[0\]\.adjustments\[0\]\.kind: 'vibes'"):
            run(R)
        cards = [{"adjustments": [{"label": "Hall Bath (Not in Its Listing)", "amount": 10000},
                                  {"label": "Something Odd", "amount": 2000, "kind": "pool"}], "seller_concessions": 0}]
        self.assertEqual(deck.adjustment_words(cards), "condition and updates and pool")

    def test_range_warnings_run_here_too(self):
        R = report()
        R["recommendation"].update(low=400000, high=520000)
        keys = run(R)[0]["warning_keys"]
        self.assertIn("range_wide", keys)
        self.assertIn("range_one_comp", keys)

    def test_listing_history_on_page_one_and_the_deck(self):
        R = report()
        R["listing_history"] = [{"status": "expired", "price": 229900, "original_price": 239900, "ended": "2017-03",
                                 "days_on_market": 184}]
        C, homes = run(R)
        text = "Expired in March 2017 after 184 days at $229,900, first listed at $239,900."
        self.assertEqual([e["text"] for e in C["listing_history"]], [text])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn(text, doc.split('class="pb"')[0])  # page 1
        self.assertEqual(deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")["history"], text)
        R["listing_history"] = [{"status": "sold", "price": 1}]
        with self.assertRaisesRegex(compute.ReportError, r"listing_history\[0\]"):
            run(R)

    def test_each_option_prorates_to_its_own_closing(self):
        """Dec 18 for every option, though the slowest closes in January: now each closing follows its time."""
        from datetime import date
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-18")
        C, _ = run(R)
        self.assertEqual(C["net"]["closings"], ["2027-01-22", "2026-12-18", "2026-12-18"])
        tax = row(C, "tax_proration")["amounts"]
        jan = (date(2027, 1, 22) - date(2027, 1, 1)).days
        self.assertEqual(tax[0], -(round(6000 * 0.96) + round(6000 * 0.96 * jan / 365)))  # this year's bill, then 2027's
        self.assertEqual(tax[1], -round(6000 * 0.96 * (date(2026, 12, 18) - date(2026, 1, 1)).days / 365))
        notes = " ".join(C["net"]["notes"])
        self.assertIn("closes in 2027", notes)
        self.assertIn("own expected closing", notes)

    def test_default_brokerage_never_labeled_beside_a_net(self):
        """Owner rule (supersedes Results_v4's '5% Brokerage Assumed'): no Assumed label under a net column's header,
        on the page 1 tile or in the options footnote; the brokerage lines show the rates."""
        R = report()
        R["costs"] = {}
        C, homes = run(R)
        self.assertNotIn("net_header_sub", C["options_summary"])
        self.assertNotIn("assumed", C["options_summary"]["note"].lower().replace("assumes competing", ""))
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertNotIn("Brokerage Assumed", doc)
        self.assertNotIn("th-sub", doc)
        self.assertIn("Listing Brokerage (2.5%)", doc)

    def test_report_carries_equal_housing_and_runs_on(self):
        R = report()
        C, homes = run(R)
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertIn("Equal Housing Opportunity.", doc)
        self.assertIn('class="kg sec runon"', doc)  # the method may run on to a last page

    def test_crowded_callouts_are_left_off(self):
        checks, _ = seller_render.scatter_checks({"labels_dropped": ["882 Siskin Way (For Sale)", "Your Home"]}, "Your Home")
        self.assertEqual(len(checks), 1)
        self.assertIn("882 Siskin Way (For Sale)", checks[0])
        self.assertNotIn("Your Home", checks[0])

    def test_deck_scatter_fits_its_data(self):
        R = report()
        C, homes = run(R)
        sc = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")["scatter"]
        ys = [p[1] for s in sc["series"] for p in s["points"]] + sc["band"]
        self.assertLessEqual(sc["y_max"] - max(ys), sc["y_step"] + 10000)
        self.assertLessEqual(min(ys) - sc["y_min"], sc["y_step"] + 10000)
        self.assertEqual(sc["band"], [R["recommendation"]["low"], R["recommendation"]["high"]])

    def test_deck_tables_are_print_light(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here.")
        R = report()
        C, homes = run(R)
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deck.pptx")
            with contextlib.redirect_stderr(io.StringIO()):
                deck.build_pptx(D, path)
            with zipfile.ZipFile(path) as z:
                names = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                               key=lambda n: int(re.search(r"\d+", n).group()))
                tables = [z.read(n).decode() for n in names[-2:]]
                chart = next(z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart")
                             and b"<c:scatterChart>" in z.read(n))
        for xml in tables:  # no filled header and no banded rows: every cell is white (the rules aside)
            cells = [re.sub(r"<a:ln[LRTB]\b.*?</a:ln[LRTB]>", "", c, flags=re.S) for c in re.findall(r"<a:tcPr.*?</a:tcPr>", xml, re.S)]
            fills = {f for c in cells for f in re.findall(r'<a:srgbClr val="(\w+)"', c)}
            self.assertTrue(cells)
            self.assertLessEqual(fills, {D["colors"]["bg"]})
        self.assertNotIn("<c:legend>", chart)  # the legend is drawn as shapes matching the markers
        for slate in ("A3ADB6", "B8C2CC", "5A6672"):  # the old slate grays: a second, blue hue
            self.assertNotIn(slate, chart)


TANAGER = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "tanager", "report.json")


def tanager():
    """Iteration 12, seller-cma eval-9: 842 Tanager Ridge Dr, five comps clustered at $384,000 to $395,100 adjusted, an
    export whose sold rows echo the sale price as the current price (a Matrix export), the agent's first range of
    $375,000 to $400,000, launch headings that are the report's steps, and a method note with a time-adjustment
    cutoff ("before August") that isn't the July market split."""
    with open(TANAGER) as f:
        R = json.load(f)
    R["export"] = os.path.join(os.path.dirname(TANAGER), R["export"])
    return R


class Iteration12(unittest.TestCase):
    def test_expected_sale_is_never_below_the_range(self):
        """The rule's figure for a list price inside the range never lands under it: the comps are already net of
        credits, so page 1's expected sale reads inside its range."""
        R = tanager()
        C, homes = run(R)
        rec = C["strategies"][1]
        self.assertEqual(rec["expected_sale"], 384500)  # 389,900 x 97% + 6,500, inside $380,000 to $400,000
        self.assertEqual(C["strategies"][0]["expected_sale"], 384500)  # the top option expects the recommended one's
        self.assertEqual(C["strategies"][2]["expected_sale"], 380000)  # 372,500 by the rule, floored at the range
        self.assertNotIn("expected_below_range", C["assumption_keys"])
        self.assertIn("never below the bottom of the supported range", C["expected_sale_basis"]["method"])
        for x in C["strategies"]:
            self.assertGreaterEqual(x["expected_sale"], R["recommendation"]["low"])
        doc, _ = seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        page1 = doc[doc.index('class="onepage"'):]
        self.assertIn("$380,000 – $400,000", page1)
        self.assertIn("About $384,500", page1)
        R = tanager()  # a range narrower than the rule's figure: the expected sale is its bottom, still not above list
        R["recommendation"].update(low=385000, high=390000)
        C, _ = run(R)
        self.assertEqual([x["expected_sale"] for x in C["strategies"]], [385000, 385000, 385000])

    def test_sale_to_final_list_from_an_export_that_carries_it(self):
        """An export whose sold rows carry the final list price (RESO ListPrice) gives the ratio against it, not
        against the original price; one that echoes the sale price falls back to 97% assumed and says why."""
        R = tanager()
        C, _ = run(R)
        self.assertEqual(C["expected_sale_basis"]["source"], "assumed")
        self.assertIn("no final list price", " ".join(C["assumptions"]))
        market, homes = compute.load_inputs(tanager())
        final = {"790 TANAGER RIDGE DR": 389900, "1012 GROSBEAK CT": 369900, "402 LINNET CIR": 379900}
        for h in homes:
            if h["status"] == "SOLD" and h["address"] in final:
                h["current_price"] = final[h["address"]]
        self.assertTrue(compute.mls.carries_final_list([h for h in homes if h["status"] == "SOLD"]))
        recent = [h for h in homes if h["status"] == "SOLD" and str(h["close_date"]) >= "2026-07-01"]
        want = round(statistics.median((h["close_price"] - (h["seller_paid"] or 0)) / h["current_price"] for h in recent), 4)
        C = compute.compute(tanager(), market, homes)
        self.assertEqual((C["expected_sale_basis"]["source"], C["expected_sale_basis"]["ratio"]), ("export", want))
        self.assertGreater(want, C["handoff"]["market"]["sale_to_original_list_recent"])  # earlier cuts don't count
        self.assertIn("final asking price", C["expected_sale_basis"]["method"])

    def test_range_rule_allows_a_normal_width(self):
        """Clustered comps never force a range narrower than the method's normal width: each end may reach half the
        target width from the median, rounded outward to $5,000; every warning names a range that passes.
        Results_v5: the width is capped at about 6% of the median ($23,210 here, so $20,000 with $5,000 ends) and
        floored at half of that."""
        values = [384000, 385200, 386825, 387500, 395100]
        fl = {"cma.range_width_pct": 0.06}
        self.assertEqual(compute.cma.range_bounds(values, fl), (375000, 400000, 20000))
        self.assertEqual(compute.cma.range_warnings({"low": 380000, "high": 400000}, values, fl), [])
        self.assertEqual(compute.cma.range_warnings({"low": 380000, "high": 395000}, values, fl), [])
        out = dict(compute.cma.range_warnings({"low": 385000, "high": 390000}, values, fl))
        self.assertEqual(list(out), ["range_narrow"])
        self.assertIn("for example $375,000 – $395,000", out["range_narrow"])
        out = compute.cma.range_warnings({"low": 365000, "high": 410000}, values, fl)
        self.assertEqual([k for k, _ in out], ["range_wide", "range_one_comp", "range_one_comp"])
        for _, text in out:
            self.assertIn("both ends sit inside $375,000 – $400,000 and it's $15,000 to $20,000 wide", text)
        self.assertEqual(dict(compute.cma.range_warnings({"low": 375000, "high": 400000}, values, fl)).keys(),
                         {"range_wide"})  # $25,000 is past the cap
        spread = [431000, 452000, 466000, 478800, 496000]  # comps that disagree: the second-highest still caps the top
        self.assertEqual(compute.cma.range_bounds(spread, fl)[1], 480000)
        self.assertEqual(compute.cma.range_bounds(values, None), (375000, 400000, 20000))  # 6% where none is built in
        self.assertEqual(compute.cma.range_width(440000)["target"], 25000)  # $26,400 cap: $25,000 at $440,000

    def test_time_adjustment_month_is_not_the_split(self):
        R = tanager()
        R["comps"]["time_adjustment"]["cutoff"] = "2026-08-01"
        R["comps"]["method_note"] = R["comps"]["method_note"].replace("{time_cutoff}", "August")
        run(R)  # no stop: the time adjustment's cutoff isn't the July market split
        R["market"]["intro"] = "Homes sold since August took about a month to sell."
        with self.assertRaisesRegex(compute.ReportError, r"market\.intro: says \"since August\""):
            run(R)

    def test_launch_headings_must_be_step_names(self):
        R = tanager()
        plan = R["deck"]["launch_plan"]
        plan[3][0], plan[4][0] = "Seller-Credit Budget", "3-Week Review"  # what the eval wrote: passed before
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        msg = str(e.exception)
        self.assertIn('deck.launch_plan[3]: "Seller-Credit Budget" isn\'t one of', msg)
        self.assertIn('deck.launch_plan[4]: "3-Week Review" isn\'t one of', msg)
        self.assertIn('"Decide on a seller-credit budget now"', msg)  # the names that pass, once each
        self.assertEqual(msg.count('"Gather Kitchen Records"') + msg.count('"Gather the kitchen records"'), 2)  # 2 stops
        plan[3][0], plan[4][0] = "Decide On A Seller Credit Budget", "agree on the review point!"  # trivial differences
        run(R)
        self.assertTrue(compute.same_step("Gather Kitchen Records", "Gather the kitchen records."))
        self.assertFalse(compute.same_step("Kitchen Records", "Gather the kitchen records."))

    def test_text_fit_checks_say_how_much_fits(self):
        if not node_ready():
            self.skipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here.")
        R = tanager()
        R["deck"]["subtitle"] = ("Listing Presentation · Casselberry, Tanager Ridge · Three Bedrooms, an Updated Kitchen, "
                                 "a Two-Car Garage and a Newer Roof")
        C, homes = run(R)
        D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
        with tempfile.TemporaryDirectory() as tmp:
            checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))
            sub = next(c for c in checks if "deck.subtitle" in c)
            m = re.search(r"at most about (\d+) characters fit and it has (\d+); shorten it to \1 characters or fewer", sub)
            self.assertTrue(m, sub)
            self.assertEqual(int(m.group(2)), len(R["deck"]["subtitle"]))
            R["deck"]["subtitle"] = R["deck"]["subtitle"][:int(m.group(1))].rsplit(" ", 1)[0]  # cut to the limit: fits
            D = deck.deck_data(copy.deepcopy(R), C, homes, AGENT, compute.labels(R), "footer")
            checks = deck.build_pptx(D, os.path.join(tmp, "deck2.pptx"))
        self.assertFalse([c for c in checks if "deck.subtitle" in c])
