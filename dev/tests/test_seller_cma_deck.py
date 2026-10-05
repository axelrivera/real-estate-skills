"""seller-cma listing presentation: deck content validation, the deck data built from compute.py's output, brand
colors, and one PPTX build (node, with the PDF copy when LibreOffice is installed)."""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, os.path.dirname(__file__))
from test_seller_cma import (ROOT, SKILL, AGENT, compute, deck, report, report_with_deck,  # noqa: E402
                             run, seller_render, tanager, texas)

DECK = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "deck", "hickorywood-deck.json")


def data(R, agent=AGENT):
    C, homes = run(R)
    return deck.deck_data(R, C, homes, agent, compute.labels(R), "footer"), C


def no_export_deck():
    R = texas(report_with_deck())
    R["deck"]["market_stats"] = [["Median Adjusted Value", "$450K", "chart"], ["Sales with Seller Credits", "2 of 3"]]
    R["deck"].pop("scatter_takeaway", None)
    return R


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


class Colors(unittest.TestCase):
    def test_roles_hold_contrast_for_any_brand(self):
        design = deck.design
        for primary in (None, "#F2C94C", "#FFE600", "#111827", "#9CA3AF", "#6B21A8", "#0B6E4F"):
            K = design.pptx_colors(design.theme({"primary": primary} if primary else None, "seller"))
            roles = deck.contrast_roles(K)
            if primary is None:
                self.assertEqual(roles["comp"], K["brand"])  # comps in the brand, as on the PDF
            K.update(roles)
            c = lambda a, b: design.contrast("#" + K[a], "#" + K[b])
            self.assertGreaterEqual(c("mark", "bg"), 3.0, primary)
            self.assertGreaterEqual(c("brand_ink", "bg"), 4.5, primary)
            self.assertGreaterEqual(c("brand_strong", "brand_callout"), 6.0, primary)
            self.assertGreaterEqual(c("on_dark", "brand_deep"), 7.0, primary)
            self.assertGreaterEqual(c("on_ink", "brand_ink"), 4.5, primary)
            self.assertGreaterEqual(design.distance("#" + K["mark"], "#" + K["text"]), 0.12, primary)  # comps vs subject
        D, _ = data(report())
        self.assertEqual((D["colors"]["brand"], D["colors"]["on_brand"]), ("0B6E4F", "FFFFFF"))
        self.assertEqual(D["agent"]["lines"], ["Sunshine Realty"])  # no "License undefined"
        self.assertIn("$80", D["content"]["payment_takeaway"])  # {per_10k} filled from compute.py

    def test_builder_has_no_hard_coded_colors(self):
        with open(os.path.join(SKILL, "scripts", "build_deck.js")) as f:
            self.assertEqual(re.findall(r"['\"]#?[0-9A-Fa-f]{6}['\"]", f.read()), [])


class Content(unittest.TestCase):
    def test_validation(self):
        def missing(R):
            del R["deck"]["launch_plan"]

        def one_driver(R):
            R["deck"]["value_drivers"] = R["deck"]["value_drivers"][:1]

        def unknown_icon(R):
            R["deck"]["value_drivers"][0] = R["deck"]["value_drivers"][0][:2] + ["hot tub"]

        def mixed_periods(R):
            R["deck"]["market_stats"] = [["Median Adjusted Value", "$450K", "chart"], ["Sales with Seller Credits", "2 of 3"],
                                         ["Days to Contract", "40", "22"]]

        for change in (missing, one_driver, unknown_icon, mixed_periods):
            with self.subTest(change.__name__):
                R = report_with_deck()
                change(R)
                with self.assertRaises(deck.DeckError):
                    deck.load_content(R)
        R = report_with_deck()
        R["deck"]["document_items"] = []  # nothing needs paperwork: allowed, the box is left out
        R["deck"]["launch_plan"] = R["deck"]["launch_plan"][:4]
        deck.load_content(R)
        R = report_with_deck()
        R["deck"]["competition"][0][0] = "1 Nowhere Ln"  # competition must be in the report
        with self.assertRaises(deck.DeckError):
            data(R)

    def test_labels_follow_the_data(self):
        R = report_with_deck()
        L = compute.labels(R)
        R["deck"].pop("comps_basis", None)
        D, _ = data(R)
        self.assertEqual(D["labels"]["deck_strat_title"], L(f"deck_strat_title_{len(R['pricing']['strategies'])}"))
        self.assertEqual(D["labels"]["deck_expected_sub"], L("deck_expected_sub"))
        self.assertEqual(D["labels"]["deck_step_comps"], L("deck_step_comps"))
        ri = R["pricing"]["recommended_index"]
        R["pricing"]["strategies"][ri]["expected_sale"] = R["recommendation"]["list_price"]  # sells at list
        R["deck"]["comps_basis"] = "size, floor, view and building"
        D, _ = data(R)
        self.assertEqual(D["labels"]["deck_expected_sub"], L("deck_expected_sub_at"))
        self.assertEqual(D["labels"]["deck_step_comps"], L("deck_step_comps_basis", basis="size, floor, view and building"))
        R = report_with_deck()
        for c in R["comps"]["cards"]:
            c["adjustments"], c["seller_concessions"] = [], 0
        R["comps"].pop("time_adjustment")
        self.assertEqual(data(R)[0]["labels"]["deck_method_note"], L("deck_method_note_none"))
        R = report_with_deck()
        R["deck"]["value_drivers"][1] = R["deck"]["value_drivers"][1][:2] + ["pool"]
        self.assertEqual(data(R)[0]["icons"]["value_drivers"][1], "FaSwimmingPool")  # named in the content
        R["deck"]["value_drivers"][1] = R["deck"]["value_drivers"][1][:2]
        self.assertEqual(data(R)[0]["icons"]["value_drivers"][1], "FaStar")  # neutral, never a pool the home may not have

    def test_period_labels_and_adjustment_words(self):
        w = {"first_close": "2026-04-03", "last_close": "2026-09-20", "split_date": "2026-07-01"}
        self.assertEqual(deck.period_labels(w), ["April–June", "July–September"])
        w["split_date"] = "2026-07-15"
        self.assertEqual(deck.period_labels(w), ["April–July 14", "July 15–September"])
        w = {"first_close": "2025-11-03", "last_close": "2026-02-20", "split_date": "2026-01-01"}  # across the new year
        self.assertEqual(deck.period_labels(w), ["November 2025–December 2025", "January 2026–February 2026"])
        mk = lambda labels, credit=0, kind=None: {"adjustments": [{"label": x, "amount": 5000, **({"kind": kind} if kind else {})}
                                                                 for x in labels], "seller_concessions": credit}
        cases = [
            ([mk(["Size", "Larger Corner Lot"]), mk(["Size"], 5000)], "size, lot and seller credits"),
            ([mk(["Original Hall Bath", "Older Roof", "Size"], 5000),
              mk(["Kitchen, Hall Bath and Floors", "Remodeled Primary Bath", "Market Since the Sale"], 5000)],
             "condition and updates, roof and systems, size, market changes since each sale and seller credits"),
            ([mk(["Hall Bath (Not in Its Listing)"]), mk(["Something Odd"], kind="pool")], "condition and updates and pool"),
        ]
        for cards, words in cases:
            self.assertEqual(deck.adjustment_words(cards), words)


class Data(unittest.TestCase):
    """Deck figures come from compute.py's output, on the same basis as the report."""

    def test_figures_from_compute(self):
        R = report_with_deck()
        for x in R["pricing"]["strategies"]:
            x.pop("expected_sale")
        R["listing_history"] = [{"status": "expired", "price": 229900, "original_price": 239900, "ended": "2017-03",
                                 "days_on_market": 184}]
        D, C = data(R)
        self.assertEqual(D["expected_sale"], C["recommendation"]["expected_sale"])
        self.assertEqual(D["history"], C["listing_history"][0]["text"])
        for figure in ("$229,900", "$239,900", "184"):
            self.assertIn(figure, D["history"])
        R = report_with_deck()
        R["costs"]["mortgage_payoff"] = 210000
        D, C = data(R)
        L = compute.labels(R)
        self.assertEqual(C["net_basis"], "after_holding")
        bars = [x["net"] for x in D["strategies"]]
        self.assertEqual(max(bars) - min(bars), round(C["net_spread"]))
        self.assertEqual(D["net_spread_display"], C["net_spread_display"])
        self.assertTrue(D["net_sub"].startswith(L("deck_cash_holding_sub")))  # the after-holding net, never cash at closing
        R["costs"]["mortgage_payoff"] = 0
        D, C = data(R)
        self.assertTrue(D["net_sub"].startswith(L("deck_cash_free_holding_sub")))
        R = tanager()
        D, C = data(R)
        lines = {c["address"]: c["line"] for c in D["comps"]}
        strongest = R["comps"]["cards"][C["strongest_comp"]]["address"]
        L = compute.labels(R)
        self.assertTrue(lines[strongest].startswith(L("deck_strongest")))
        self.assertEqual(sum(line.startswith(L("deck_strongest")) for line in lines.values()), 1)

    def test_scatter_matches_the_report(self):
        R = report_with_deck()
        D, C = data(R)
        _, homes = run(R)
        comps = [cd["address"] for cd in R["comps"]["cards"]]
        pts, _, _ = compute.cma.scatter_points(homes, R["scatter"], R["subject"]["sqft"], R["subject"].get("mls_address"), comps)
        sc = D["scatter"]
        self.assertEqual({k: len(v) for k, v in sc["points"].items()}, {k: len(v) for k, v in pts.items()})
        self.assertEqual(len(pts["comp"]), len(comps))  # every comp card is on the chart, matched by address
        self.assertEqual([s["key"] for s in sc["series"]], ["sold", "active", "trend", "comp", "subject"])
        ys = [p[1] for s in sc["series"] for p in s["points"]] + sc["band"]
        self.assertLessEqual(sc["y_max"] - max(ys), sc["y_step"] + 10000)
        self.assertLessEqual(min(ys) - sc["y_min"], sc["y_step"] + 10000)
        self.assertEqual(sc["band"], [R["recommendation"]["low"], R["recommendation"]["high"]])

    def test_without_an_export(self):
        """No scatter, one-value market cards, and the method starts at the comps."""
        R = no_export_deck()
        self.assertEqual(deck.load_content(R)["market_stats"][1], ["Sales with Seller Credits", "2 of 3"])
        D, _ = data(R)
        self.assertIsNone(D["scatter"])
        self.assertTrue(D["market"]["one_period"])
        self.assertIsNone(D["method"]["n_sold"])
        self.assertIsNotNone(data(report_with_deck())[0]["method"]["n_sold"])


class Office(unittest.TestCase):
    def test_finds_libreoffice_off_path(self):
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


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not node_ready():
            raise unittest.SkipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here "
                                    "(set NODE_PATH to dev/node_modules after `make setup`).")
        deck.PDF_TIMEOUT = 60  # a stalled LibreOffice fails the run in a minute, not three

    def test_full_pptx(self):
        """The branded deck: one brand hue, the subject black, print-light tables, a PDF copy with every slide."""
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                paths = seller_render.build(report(), "pptx", tmp, {"agent": AGENT, "market": None, "sample": True})
            self.assertNotIn("doesn't fit", err.getvalue())  # the sample content fits every box
            office = bool(deck.find_office())
            if office:
                self.assertEqual(len(paths), 2)
                self.assertTrue(paths[1].endswith("-Listing-Presentation.pdf"))
                with open(paths[1], "rb") as f:
                    pdf_pages = len(re.findall(rb"/Type\s*/Page[^s]", f.read()))
            with zipfile.ZipFile(paths[0]) as z:
                slides = sorted((n for n in z.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                                key=lambda n: int(re.search(r"\d+", n).group()))
                if office:
                    self.assertEqual(pdf_pages, len(slides))
                charts = [z.read(n).decode() for n in z.namelist() if n.startswith("ppt/charts/chart") and n.endswith(".xml")]
                text = "".join(z.read(n).decode() for n in slides)
                tables = [z.read(n).decode() for n in slides[-2:]]
        scatter = next(c for c in charts if "<c:scatterChart>" in c)
        self.assertIn('<c:size val="5"/>', scatter)  # other sales are small background dots
        self.assertIn('<c:symbol val="diamond"/>', scatter)
        self.assertIn('val="1A1A1A"', scatter)  # the subject home is black, not a second hue
        self.assertIn('val="0B6E4F"', scatter)
        self.assertNotIn("<c:legend>", scatter)  # the legend is drawn as shapes matching the markers
        self.assertIn("Sunshine Realty", text)
        self.assertNotIn("undefined", text)
        everything = text + "".join(charts)
        for hue in ("C2410C", "1F3A5F", "E4E7EC", "D2D8DF", "A3ADB6", "B8C2CC", "5A6672"):
            self.assertNotIn(hue, everything)  # no default orange, navy or slate: one brand color only
        for xml in tables:  # no filled header and no banded rows: every cell is white (the rules aside)
            cells = [re.sub(r"<a:ln[LRTB]\b.*?</a:ln[LRTB]>", "", c, flags=re.S) for c in re.findall(r"<a:tcPr.*?</a:tcPr>", xml, re.S)]
            self.assertTrue(cells)
            self.assertLessEqual({f for c in cells for f in re.findall(r'<a:srgbClr val="(\w+)"', c)}, {"FFFFFF"})

    def test_text_fit_checks_say_how_much_fits(self):
        R = tanager()
        R["deck"]["subtitle"] = ("Listing Presentation · Casselberry, Tanager Ridge · Three Bedrooms, an Updated Kitchen, "
                                 "a Two-Car Garage and a Newer Roof")
        D, _ = data(R)
        with tempfile.TemporaryDirectory() as tmp:
            checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))  # still built
            self.assertTrue(os.path.exists(os.path.join(tmp, "deck.pptx")))
        sub = [c for c in checks if "deck.subtitle" in c]
        self.assertEqual(len(sub), 1)
        fit, has = map(int, re.findall(r"\d+", sub[0].split("deck.subtitle", 1)[1])[:2])
        self.assertEqual(has, len(R["deck"]["subtitle"]))
        self.assertLess(fit, has)
        R["deck"]["subtitle"] = R["deck"]["subtitle"][:fit].rsplit(" ", 1)[0]  # cut to the stated limit: it fits
        D, _ = data(R)
        with tempfile.TemporaryDirectory() as tmp:
            checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))
        self.assertFalse([c for c in checks if "deck.subtitle" in c])


if __name__ == "__main__":
    unittest.main()
