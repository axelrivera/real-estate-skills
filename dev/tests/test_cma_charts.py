"""shared/cma.py charts: label placement on the scatter and the dot plot, label halos, axis ticks, and the chart that
shrinks rather than leave a gap. The one place for chart label rules."""
import os
import re
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.dirname(__file__))
from test_seller_cma import compute, report, run, seller_render  # noqa: E402

cma, fmt, kit = compute.cma, compute.fmt, seller_render.layout


def scatter_args(R):
    C, _ = run(R)
    return (R["subject"]["sqft"], C["recommendation"]["list_price"], R["subject"]["mls_address"],
            (C["recommendation"]["low"], C["recommendation"]["high"]), compute.labeler(),
            [cd["address"] for cd in R["comps"]["cards"]])


class ScatterLabels(unittest.TestCase):
    def test_labels_avoid_each_other(self):
        R = report()
        _, homes = run(R)
        sc = {**R["scatter"], "subject_label": "Your Home", "subject_label_pos": "right"}
        # a callout at the subject's own price and nearly its size, asked for on the subject label's side
        near = next(h for h in homes if h["status"] == "SOLD" and h.get("living_area")
                    and 0 < h["living_area"] - 1849 < 120 and h["address"] != R["subject"]["mls_address"])
        near["close_price"] = run(R)[0]["recommendation"]["list_price"]
        sc["callouts"] = [{"address": near["address"], "label": "Twin Sale", "side": "left"}]
        svg, info = cma.scatter(homes, sc, *scatter_args(R))
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

    def test_callout_side_is_passed(self):
        """Any move is reported from the side the callout asked for."""
        R = report()
        _, homes = run(R)
        sc = {**R["scatter"], "subject_label": "Your Home"}
        for side in ("left", "right", "above", "below"):
            sc["callouts"] = [{**R["scatter"]["callouts"][0], "label": "A Callout", "side": side}]
            _, info = cma.scatter(homes, sc, *scatter_args(R))
            label = sc["callouts"][0]["label"]
            self.assertTrue(all(m[1] == side for m in info["labels_moved"] if m[0] == label))


class Halo(unittest.TestCase):
    """Labels read in every PDF viewer: a background-colored copy under each label, never a paint-order outline."""

    def test_halo_copy_and_width(self):
        svg = cma._halo('<text x="1" y="2" class="lbl-band">Supported Range $375K–$395K</text>')
        self.assertEqual(svg.count("Supported Range"), 2)
        self.assertTrue(svg.startswith('<text x="1" y="2" aria-hidden="true" class="halo lbl-band">'))
        self.assertTrue(svg.endswith('class="lbl-band">Supported Range $375K–$395K</text>'))
        for path in ("shared/cma.css", "shared/report.css", "skills/contract-timeline/assets/timeline.css"):
            with open(os.path.join(ROOT, path), encoding="utf-8") as f:
                self.assertNotIn("paint-order", f.read(), path)
        self.assertGreater(cma._text_w("Supported Range $375K–$395K", 12, bold=True), 27 * 12 * 0.6)


class DotPlot(unittest.TestCase):
    def test_marks_labels_and_ticks(self):
        cards = [{"address": f"{i} Oak St", "adjusted": v} for i, v in enumerate((455000, 462000, 470000))]
        svg = cma.dotplot(cards, 455000, 480000, 474900, "Asking $474,900", (468000, "Offer $468,000"))
        self.assertEqual(svg.count('class="dp-dot"'), 3)
        # two close markers label on opposite sides
        anchors = dict((cls, a) for a, cls in re.findall(r'text-anchor="(\w+)" class="dp-(mark|second)-lbl"', svg))
        self.assertEqual(set(anchors), {"mark", "second"})
        self.assertNotEqual(anchors["mark"], anchors["second"])
        self.assertEqual((fmt.k(455000), fmt.k(1250000), fmt.k(2000000)), ("$455K", "$1.25M", "$2M"))
        cards = [{"address": f"{i} Bay Dr", "adjusted": v} for i, v in enumerate((1210000, 1390000, 1480000, 1620000, 1790000))]
        svg = cma.dotplot(cards, 1400000, 1600000, 1550000, "Asking")
        self.assertLessEqual(len(svg.split('class="dp-tick">')[1:]), 8)
        self.assertIn("$1.5M", svg)

    def test_value_label_moves_off_the_price_line(self):
        cards = [{"address": "1 A St", "adjusted": 448000}, {"address": "2 B St", "adjusted": 470000}]
        svg = cma.dotplot(cards, 440000, 460000, 449900, "Recommended")
        self.assertRegex(svg, r'text-anchor="end" class="dp-val">\$448K')  # the line at $449,900 would strike it
        self.assertRegex(svg, r'<text x="[\d.]+" y="[\d.]+" class="dp-val">\$470K')


class ChartFit(unittest.TestCase):
    def test_scatter_shrinks_rather_than_leave_a_gap(self):
        """A chart group that almost fits the rest of a page shrinks its chart instead of moving."""
        render = seller_render.render
        svg = '<svg viewBox="0 0 760 470" class="scatter"><rect width="760" height="470"/></svg>'

        def layout(filler):
            doc = render.page(f'<div class="wrap"><div style="height:{filler}px"></div>'
                              f'<div class="kg"><h3>Chart</h3><div class="chart-box">{svg}</div>'
                              '<div style="height:260px"></div></div></div>', css=cma.css())

            def measure(pg):
                pg.set_viewport_size({"width": 730, "height": 1000})
                pg.evaluate(kit.PAGINATE_JS, [960, []])
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


if __name__ == "__main__":
    unittest.main()
