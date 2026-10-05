"""seller-cma listing presentation: the deck wording's shape, the deck data picked from the document model, brand colors,
and one PPTX build (node, with the PDF copy when LibreOffice is installed)."""
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


def data(R, agent=AGENT):
    C, _ = run(R)
    return deck.deck_data(C, agent, "footer"), C


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
            c = lambda a, b: design.contrast("#" + K[a], "#" + K[b])  # noqa: E731
            self.assertGreaterEqual(c("mark", "bg"), 3.0, primary)
            self.assertGreaterEqual(c("brand_ink", "bg"), 4.5, primary)
            self.assertGreaterEqual(c("on_dark", "brand_deep"), 7.0, primary)
            self.assertGreaterEqual(c("on_ink", "brand_ink"), 4.5, primary)
        D, _ = data(report())
        self.assertEqual((D["colors"]["brand"], D["colors"]["on_brand"]), ("0B6E4F", "FFFFFF"))
        self.assertEqual(D["agent"]["lines"], ["Sunshine Realty"])  # no "License undefined"

    def test_builder_has_no_hard_coded_colors_or_formats(self):
        with open(os.path.join(SKILL, "scripts", "build_deck.js")) as f:
            js = f.read()
        self.assertEqual(re.findall(r"['\"]#?[0-9A-Fa-f]{6}['\"]", js), [])
        self.assertNotIn("Math.round(v / 1000)", js)  # tick labels come named from deck.py (fmt)
        self.assertNotIn('"K"', js)


class Content(unittest.TestCase):
    def test_shape(self):
        def one_driver(R):
            R["deck"]["value_drivers"] = R["deck"]["value_drivers"][:1]

        def unknown_icon(R):
            R["deck"]["value_drivers"][0] = R["deck"]["value_drivers"][0][:2] + ["hot tub"]

        def old_competition(R):
            R["deck"]["competition"][0] = [R["deck"]["competition"][0][0], "For sale", "Why"]

        def stranger(R):
            R["deck"]["competition"][0][0] = "1 Nowhere Ln"

        def timeline(R):
            R["deck"]["timeline"][0][0] = "Week Two"

        for change in (one_driver, unknown_icon, old_competition, stranger, timeline):
            with self.subTest(change.__name__):
                R = report_with_deck()
                change(R)
                with self.assertRaises(deck.DeckError):
                    data(R)
        R = report_with_deck()
        R["deck"]["document_items"] = []  # nothing needs paperwork: allowed, the box is left out
        data(R)
        R = report()
        R["deck"] = "/nonexistent/deck.json"
        with self.assertRaisesRegex(deck.DeckError, "can't be read"):
            data(R)

    def test_labels_follow_the_data(self):
        R = report_with_deck()
        R["deck"].pop("comps_basis", None)
        D, C = data(R)
        self.assertEqual(D["labels"]["deck_strat_title"], compute.t(f"deck_strat_title_{len(C['strategies'])}"))
        self.assertEqual(D["labels"]["deck_expected_sub"], compute.t("deck_expected_sub"))
        self.assertEqual(D["method"]["steps"][1][1], compute.t("deck_step_comps"))
        ri = R["pricing"]["recommended_index"]
        R["pricing"]["strategies"][ri]["expected_sale"] = R["recommendation"]["list_price"]  # sells at list
        R["deck"]["comps_basis"] = "size, floor, view and building"
        D, _ = data(R)
        self.assertEqual(D["labels"]["deck_expected_sub"], compute.t("deck_expected_sub_at"))
        self.assertEqual(D["method"]["steps"][1][1], compute.t("deck_step_comps_basis", basis="size, floor, view and building"))
        R = report_with_deck()
        R["deck"]["value_drivers"][1] = R["deck"]["value_drivers"][1][:2]
        self.assertEqual(data(R)[0]["drivers"][1][2], "FaStar")  # neutral, never a pool the home may not have


class Data(unittest.TestCase):
    """Every figure on a slide is the model's, on the same basis as the report."""

    def test_figures_from_the_model(self):
        R = report_with_deck()
        R["listing_history"] = [{"status": "expired", "price": 229900, "original_price": 239900, "ended": "2017-03",
                                 "days_on_market": 184}]
        R["costs"]["mortgage_payoff"] = 210000
        D, C = data(R)
        self.assertEqual(D["rec"]["history"], C["history_line"])
        self.assertEqual(D["rec"]["expected_display"], C["recommendation"]["expected_sale_display"])
        self.assertEqual([x["net"] for x in D["strategies"]], C["net"]["after_holding"])
        self.assertEqual([x["net_display"] for x in D["strategies"]], [x["net_after_holding_display"] for x in C["strategies"]])
        self.assertEqual(D["net_rows"], [[r["label"]] + r["display"] for r in C["net"]["rows"]])
        self.assertEqual(D["comps_rows"], C["comps"]["table"] + [C["comps"]["subject_row"]])
        self.assertIn(C["payments"]["per_10k_display"], D["pay"]["per_10k_line"])
        self.assertEqual(D["timeline"][[t[1] for t in D["timeline"]].index(
            compute.t("tl_go_live", price=C["recommendation"]["list_price_display"]))][0], C["launch"]["short"])
        D, C = data(tanager())
        lines = {c["address"]: c["line"] for c in D["comps"]}
        strongest = C["comps"]["strongest"]["address"]
        self.assertTrue(lines[strongest].startswith(compute.t("deck_strongest")))
        self.assertEqual(sum(line.startswith(compute.t("deck_strongest")) for line in lines.values()), 1)
        self.assertTrue(D["cover"]["subtitle"].startswith(compute.t("deck_subtitle_plain")))

    def test_scatter_series_and_legend_from_the_report_points(self):
        D, C = data(report_with_deck())
        homes = C["_points"][0]
        sc = D["scatter"]
        drawn = {s["key"]: len(s["points"]) for s in sc["series"]}
        for kind in ("sold", "active", "comp"):
            self.assertEqual(drawn.get(kind, 0), len(homes[kind]))
        self.assertTrue(all(s["points"] for s in sc["series"]))  # the legend names only series with marks
        for s in sc["series"]:
            m = s["marker"]
            if s["key"] != "trend":
                self.assertNotEqual(m["fill"], D["colors"]["bg"])  # a filled marker every renderer draws
        self.assertEqual(sc["band"], [C["recommendation"]["low"], C["recommendation"]["high"]])
        self.assertEqual([t[1] for t in sc["y_ticks"]], [compute.fmt.k(t[0]) for t in sc["y_ticks"]])

    def test_without_an_export(self):
        """No scatter, one-value market cards from the comps, and the method starts at the comps."""
        R = texas(report_with_deck())
        R["deck"].pop("scatter_takeaway", None)
        D, _ = data(R)
        self.assertIsNone(D["scatter"])
        self.assertTrue(D["market"]["one_period"])
        self.assertTrue(all(len(m) == 3 for m in D["market"]["cards"]))  # label, value, icon
        self.assertEqual(len(D["method"]["steps"]), 3)
        self.assertEqual(len(data(report_with_deck())[0]["method"]["steps"]), 4)


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


class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not node_ready():
            raise unittest.SkipTest("Node with pptxgenjs, react-icons and sharp isn't resolvable here "
                                    "(set NODE_PATH to dev/node_modules after `make setup`).")
        deck.PDF_TIMEOUT = 60

    def test_full_pptx(self):
        """The branded deck: one brand hue, the subject black, filled markers, no value axis on the nets, print-light
        tables, a PDF copy with every slide."""
        C, _ = run(report())
        with tempfile.TemporaryDirectory() as tmp:
            err = io.StringIO()
            with contextlib.redirect_stderr(err):
                paths = seller_render.build(C, "pptx", tmp, {"agent": AGENT, "sample": True})
            self.assertNotIn("doesn't fit", err.getvalue())
            self.assertNotIn("reaches the footer", err.getvalue())
            office = bool(deck.find_office())
            if office:
                self.assertEqual(len(paths), 2)
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
        self.assertIn('<c:symbol val="diamond"/>', scatter)
        self.assertIn('<c:symbol val="square"/>', scatter)  # for-sale homes: a filled square, drawn in every viewer
        self.assertIn('val="1A1A1A"', scatter)  # the subject home is black, not a second hue
        self.assertNotIn("<c:legend>", scatter)
        bars = next(c for c in charts if "<c:barChart>" in c)
        self.assertRegex(bars, r'<c:valAx>.*<c:delete val="1"/>')  # no "$0K" axis: the bars carry their values
        self.assertIn("Sunshine Realty", text)
        self.assertNotIn("undefined", text)
        for xml in tables:  # no filled header and no banded rows
            cells = [re.sub(r"<a:ln[LRTB]\b.*?</a:ln[LRTB]>", "", c, flags=re.S) for c in re.findall(r"<a:tcPr.*?</a:tcPr>", xml, re.S)]
            self.assertTrue(cells)
            self.assertLessEqual({f for c in cells for f in re.findall(r'<a:srgbClr val="(\w+)"', c)}, {"FFFFFF"})

    def test_text_fit_checks_say_how_much_fits(self):
        R = tanager()
        R["deck"]["tagline"] = ("Three bedrooms, an updated kitchen, a two-car garage, a newer roof and a quiet street "
                                "close to the lakes and the trail, with room to grow")
        D, _ = data(R)
        with tempfile.TemporaryDirectory() as tmp:
            checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))
            self.assertTrue(os.path.exists(os.path.join(tmp, "deck.pptx")))
        sub = [c for c in checks if "deck.tagline" in c]
        self.assertEqual(len(sub), 1)
        fit, has = map(int, re.findall(r"\d+", sub[0].split("deck.tagline", 1)[1])[:2])
        self.assertEqual(has, len(R["deck"]["tagline"]))
        R["deck"]["tagline"] = R["deck"]["tagline"][:fit].rsplit(" ", 1)[0]
        D, _ = data(R)
        with tempfile.TemporaryDirectory() as tmp:
            self.assertFalse([c for c in deck.build_pptx(D, os.path.join(tmp, "deck.pptx")) if "deck.tagline" in c])


if __name__ == "__main__":
    unittest.main()
