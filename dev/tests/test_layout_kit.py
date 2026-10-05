"""shared/layout.py: the component kit's markup (generated inputs), a demo page printed with the bundled font (nothing
clipped or over the page edge), and the one page-fit pipeline (page 1 fit steps, read-back, tail steps). The printed
tests need Chromium and pdftotext; skipped without them."""
import contextlib
import io
import os
import random
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from shared import cma, design, fmt, layout, notes, render  # noqa: E402


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


NEEDS = unittest.skipUnless(bool(shutil.which("pdftotext")) and have_chromium(), "needs Chromium and pdftotext")
THEME = design.css_vars(design.theme(None, "seller"))
WORDS = ("Estimated Net Before Mortgage Payoff", "Listing Brokerage", "Owner's Title Policy (Promulgated Rate)",
         "Whispering Cypress Hammock Boulevard", "Seller-Paid Closing Costs / Concessions", "Mortgage Payoff",
         "Price", "HOA Documents", "Deed Transfer Tax")


def demo(rng, prices=3, n_tiles=4):
    """A page of kit pieces: header, fact row, tiles, a table with long headers, a chart with its legend, notes."""
    N = notes.Notes()
    N.add("commission", "Commission is assumed at 5% total, split between the two brokerages.", "assumption")
    N.add("title", "The owner's title premium is estimated from the published rate table.", "estimate")
    N.add("commission", "A second commission note never prints.", "assumption")
    vals = [rng.randint(250_000, 2_400_000) for _ in range(prices)]
    cols = [layout.Col("item", "Item", min="11em")] + [
        layout.Col(i, f"At {fmt.money(v)} ({rng.choice(WORDS)})", align="num") for i, v in enumerate(vals)]
    rows, ledgers = [], []
    for v in vals:
        from shared import finance
        led = finance.Ledger()
        led.add("price", "Sale Price", v)
        for w in WORDS[1:6]:
            led.cost(w, w, v * rng.uniform(0.001, 0.03))
        ledgers.append(led)
    for j, ln in enumerate(ledgers[0]):
        rows.append({"item": ln["label"], **{i: fmt.money(L.lines[j]["amount"]) for i, L in enumerate(ledgers)}})
    total = {"item": "Estimated Net", **{i: fmt.money(L.total()) for i, L in enumerate(ledgers)}}
    chart = layout.Chart()
    svg = [f'<svg viewBox="0 0 {40 + 90 * prices} 80" width="{40 + 90 * prices}" height="80">']
    for i, v in enumerate(vals):
        chart.mark("price", "Prices Compared", "bar")
        svg.append(f'<rect x="{20 + i * 90}" y="20" width="60" height="50" style="fill:var(--brand)"/>')
    svg.append("</svg>")
    chart.mark("trend", "Trend", "dash", count=0)  # declared, never drawn: not in the legend
    tiles = [(rng.choice(WORDS), fmt.k(v, 1)) for v in vals[:n_tiles]]
    body = (layout.header("Seller Net Sheet", "1438 Whispering Cypress Hammock Blvd, Orlando, FL",
                          ["Prepared for Alexandria Montgomery-Fitzgerald", "By Jordan Lee, Example Realty"],
                          tag="Seller", sample=True) +
            layout.fact_row(["3 Beds", "2 Baths", "1,850 Sq Ft", "Built 1998", "Closing " + fmt.date_short("2026-11-20")]) +
            layout.tiles(tiles, n=n_tiles) +
            "<h2>Itemized Estimate</h2>" + layout.table(cols, rows, total=total) +
            layout.chart_frame("".join(svg), chart.legend(), title="Where the Sale Price Goes",
                               takeaway="The middle price nets the most after costs.") +
            layout.notes_block(N))
    return render.page(body, title="Kit Demo", theme_css=THEME, body_class="font-bundled"), N, chart


class Markup(unittest.TestCase):
    def test_tiles_always_fill_n_slots(self):
        rng = random.Random(1)
        for _ in range(200):
            n = rng.randint(1, 6)
            items = [(f"Label {i}", f"${i}") for i in range(rng.randint(0, n))]
            out = layout.tiles(items, n=n)
            self.assertEqual(len(re.findall(r'class="kit-tile[ "]', out)), n)
            self.assertIn(f"repeat({n},", out)
        with self.assertRaises(ValueError):
            layout.tiles([("a", "1")] * 3, n=2)
        out = layout.tiles([("A", "$1", None, "price short"), ("B", "$2")], n=3)  # a kind of tile, by class
        self.assertEqual(re.findall(r'class="(kit-tile(?:\s[^"]*)?)"', out), ["kit-tile price short", "kit-tile", "kit-tile kit-empty"])

    def test_table_cells_escaped_and_aligned(self):
        rng = random.Random(2)
        for _ in range(200):
            k = rng.randint(1, 5)
            cols = [layout.Col(i, f"<H{i}>", align=rng.choice(["num", "text"])) for i in range(k)]
            rows = [[f"<v{r}{c}>" for c in range(k)] for r in range(rng.randint(0, 8))]
            out = layout.table(cols, rows, total=["t"] * k if rng.random() < 0.5 else None)
            self.assertNotRegex(out, r"<v\d|<H\d")
            self.assertEqual(out.count("<th "), k)
            nums = sum(c.align == "num" for c in cols)
            self.assertEqual(out.count('<td class="n kit-nw"'), nums * (len(rows) + ("total" in out)))
        self.assertIn("<b>x</b>", layout.table([layout.Col(0, "A")], [[layout.Raw("<b>x</b>")]]))

    def test_legend_names_only_drawn_series(self):
        rng = random.Random(3)
        for _ in range(300):
            ch, drawn = layout.Chart(), []
            for key in rng.sample(["sold", "active", "comp", "trend", "subject"], rng.randint(0, 5)):
                count = rng.choice([0, 0, 1, 3])
                ch.mark(key, key.title(), rng.choice(list(layout.SWATCHES)), count=count)
                if count and key not in drawn:
                    drawn.append(key)
            self.assertEqual(re.findall(r'data-series="(\w+)"', ch.legend()), drawn)
            self.assertEqual(ch.legend() == "", not drawn)

    def test_notes_block_prints_each_note_once(self):
        N = notes.Notes()
        N.add("a", "Assumed one.", "assumption")
        N.add("b", "Chat only.", "chat_only")
        N.add("a", "Assumed again.", "assumption")
        out = layout.notes_block(N)
        self.assertEqual(out.count("<li>"), 1)
        self.assertNotIn("Chat only", out)
        self.assertEqual(layout.notes_block(notes.Notes()), "")

    def test_moved_pagination_code_is_shared(self):
        for name in ("page_fill", "page_checks", "group_blocks", "PAGINATE_JS", "HALF_EMPTY", "LONE_TAIL"):
            self.assertIs(getattr(cma, name), getattr(layout, name))

    def test_fit_steps_and_page_size(self):
        self.assertEqual(layout.Fit().page_limit(), layout.PAGE1_LIMIT)
        self.assertEqual(layout.Fit(landscape=True).page_limit(), layout.PAGE1_LIMIT_WIDE)
        self.assertEqual(layout.Fit(limit=700).page_limit(), 700)
        with self.assertRaises(ValueError):
            layout.Fit(tail=("() => 1",))


def tall_doc(lines, extra_css="", tail_lines=0):
    """Page 1 of `lines` paragraphs, then a .pb detail section; .compact halves the spacing."""
    body = "".join(f"<p class='l'>Line {i} of page one</p>" for i in range(lines))
    body += "<div class='pb'><h2 class='dh'>Detailed Analysis</h2>" + \
            "".join(f"<p class='d'>Detail {i}</p>" for i in range(tail_lines)) + "</div>"
    css = ".l{margin:0;height:30px} body.compact .l{height:15px} .pb{break-before:page} .d{margin:0;height:40px}" \
          " body.dense .d{height:20px}" + extra_css
    return render.page(body, css=css, theme_css=THEME, body_class="font-bundled")


@NEEDS
class Printed(unittest.TestCase):
    def test_demo_prints_clean_with_the_bundled_font(self):
        rng = random.Random(4)
        for prices, n_tiles in ((3, 4), (4, 3), (1, 2)):
            doc, N, chart = demo(rng, prices, n_tiles)

            def inspect(pg):
                return pg.evaluate("""(clip) => ({
                  clipped: (new Function('return ' + clip))()(),
                  over: document.documentElement.scrollWidth - window.innerWidth,
                  font: getComputedStyle(document.querySelector('td')).fontFamily,
                  numWrapped: [...document.querySelectorAll('td.n')].filter(td => {
                    const r = document.createRange(); r.selectNodeContents(td);
                    return r.getClientRects().length > 1; }).length,
                  slotWidths: [...document.querySelectorAll('.kit-tile')].map(t => Math.round(t.getBoundingClientRect().width)),
                  legend: [...document.querySelectorAll('.kit-legend [data-series]')].map(s => s.dataset.series),
                  notes: [...document.querySelectorAll('.kit-notes li')].map(li => li.textContent),
                })""", render.FIND_CLIPPED)

            err = io.StringIO()
            with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
                path = os.path.join(tmp, "demo.pdf")
                info = render.html_to_pdf(doc, path, before_print=inspect)
                with open(path, "rb") as f:
                    pdf = f.read()
                pages = layout.page_fill(path, 0.3, 0.4)
            self.assertNotIn("clipped", err.getvalue())
            self.assertEqual(info["clipped"], [])
            self.assertLessEqual(info["over"], 1)
            self.assertTrue(info["font"].startswith('"Report Sans"'), info["font"])
            self.assertEqual(info["numWrapped"], 0)  # figures never break across lines, even under long headers
            first = info["slotWidths"][0]
            self.assertEqual(len(info["slotWidths"]), n_tiles)
            self.assertTrue(all(abs(w - first) <= 1 for w in info["slotWidths"]))
            self.assertEqual(info["legend"], chart.drawn())
            self.assertEqual(info["notes"], N.pdf())
            self.assertIn(b"Inter", pdf)  # the bundled face is the one embedded
            self.assertEqual(len(pages), 1)

    def test_page_one_fit_steps(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "fit.pdf")
            fit = layout.Fit(steps=("compact",))
            info = layout.print_pdf(tall_doc(45, tail_lines=3), path, fit)
            self.assertEqual(info["steps"], ["compact"])
            self.assertLessEqual(info["top"], info["limit"])
            self.assertNotIn("spill", info["problems"])
            self.assertTrue(info["pages"][1][1].startswith("Detailed Analysis"))
            # a page that already fits takes no step
            info = layout.print_pdf(tall_doc(10, tail_lines=3), path, fit)
            self.assertEqual(info["steps"], [])

    def test_overflow_names_the_tallest_block(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "over.pdf")
            fit = layout.Fit(steps=("compact",), blocks=((".l", "the first line"),))
            info = layout.print_pdf(tall_doc(90, tail_lines=1), path, fit)
            self.assertGreater(info["top"], info["limit"])
            self.assertEqual(info["blocks"][0][1], "the first line")
            self.assertTrue(info["checks"])

    def test_tail_step_kept_only_when_it_saves_a_page(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "tail.pdf")
            fit = layout.Fit(tail=("dense",), tail_below=0.5)
            # page 2 full of details and a few on page 3: the denser details pull page 3 back
            info = layout.print_pdf(tall_doc(10, tail_lines=26), path, fit)
            self.assertEqual(info["tail"], ["dense"])
            self.assertEqual(len(info["pages"]), 2)
            # nothing to save: the tail step isn't tried
            info = layout.print_pdf(tall_doc(10, tail_lines=10), path, fit)
            self.assertEqual(info["tail"], [])

    def test_one_page_document(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "one.pdf")
            body = "".join(f"<p class='l'>Row {i}</p>" for i in range(40))
            doc = render.page(body, css=".l{margin:0;height:30px} body.compact .l{height:20px}", theme_css=THEME)
            info = layout.print_pdf(doc, path, layout.Fit(one_page=True, steps=("compact",)))
            self.assertEqual(info["steps"], ["compact"])
            self.assertEqual(len(info["pages"]), 1)


    def test_paginated_report_keeps_groups_whole(self):
        rng = random.Random(5)
        blocks = []
        for i in range(14):
            blocks += [f"<h2>Section {i}</h2>", "<p>An intro line for the table below.</p>",
                       layout.table([layout.Col(0, "Item"), layout.Col(1, "Amount", align="num")],
                                    [[f"Row {r}", fmt.money(rng.randint(1, 900_000))] for r in range(rng.randint(2, 9))])]
        doc = render.page('<div class="wrap">' + layout.group_blocks(blocks) + "</div>", theme_css=THEME,
                          body_class="font-bundled")
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "pages.pdf")
            info = layout.print_pdf(doc, path, layout.Fit(end=None, paginate=True))
            self.assertIn("paginate", info)
            self.assertGreater(len(info["pages"]), 1)
            self.assertNotIn("spill", info["problems"])
            # no section heading is left at the foot of a page without its table
            for fill, first in info["pages"][1:]:
                self.assertFalse(first.startswith("Row "), first)


if __name__ == "__main__":
    unittest.main()
