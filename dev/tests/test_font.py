"""The bundled font: open license, small, inlined into every page, copied into every rendering skill, and its metrics
match what Chromium draws (generated strings)."""
import filecmp
import os
import random
import re
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from shared import design, layout, render  # noqa: E402

FONTS = os.path.join(ROOT, "shared", "fonts")
FILES = ("Inter-Regular.woff2", "Inter-Bold.woff2")


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


NEEDS = unittest.skipUnless(have_chromium(), "needs Chromium (make setup)")


class Files(unittest.TestCase):
    def test_license_and_size(self):
        with open(os.path.join(FONTS, "LICENSE.txt"), encoding="utf-8") as f:
            self.assertIn("SIL Open Font License", f.read())
        for name in FILES:
            size = os.path.getsize(os.path.join(FONTS, name))
            self.assertLess(size, 40_000, name)  # a Latin subset, not the full font

    def test_metrics_cover_what_reports_print(self):
        m = layout.metrics()
        needed = [chr(c) for c in range(0x20, 0x7F)] + list("–—−·×→≈≤≥…’“”•éñáíóúüÉÑ")
        for weight in ("regular", "bold"):
            missing = [ch for ch in needed if ch not in m[weight]]
            self.assertEqual(missing, [], weight)
            self.assertEqual(sorted(m["tnum"][weight]), list("0123456789"))

    def test_text_width_properties(self):
        rng = random.Random(1)
        chars = [chr(c) for c in range(0x21, 0x7F)]
        for _ in range(500):
            a = "".join(rng.choice(chars) for _ in range(rng.randint(1, 30)))
            b = "".join(rng.choice(chars) for _ in range(rng.randint(1, 30)))
            size = rng.choice([7, 8.6, 9, 12, 26])
            self.assertAlmostEqual(layout.text_width(a + b, size), layout.text_width(a, size) + layout.text_width(b, size))
            self.assertAlmostEqual(layout.text_width(a, 2 * size), 2 * layout.text_width(a, size))
            self.assertGreaterEqual(layout.text_width(a, size, bold=True), 0.97 * layout.text_width(a, size))
            for line in layout.wrap_lines(a + " " + b, 40, size):
                self.assertTrue(layout.text_width(line, size) <= 40 or " " not in line)


class Inlined(unittest.TestCase):
    def test_page_carries_the_font(self):
        doc = render.page("<p>x</p>", theme_css=design.css_vars(design.theme(None, "seller")))
        self.assertNotRegex(doc, r"url\(['\"]?fonts/")
        self.assertEqual(doc.count("data:font/woff2;base64,"), len(FILES))

    def test_every_rendering_skill_ships_the_same_files(self):
        skills = [os.path.join(ROOT, "skills", s) for s in sorted(os.listdir(os.path.join(ROOT, "skills")))]
        rendering = [s for s in skills if os.path.exists(os.path.join(s, "scripts", "_shared", "render.py"))]
        self.assertTrue(rendering)
        for s in rendering:
            for name in (*FILES, "LICENSE.txt", "metrics.json"):
                copy = os.path.join(s, "scripts", "_shared", "fonts", name)
                self.assertTrue(os.path.exists(copy), copy)
                self.assertTrue(filecmp.cmp(os.path.join(FONTS, name), copy, shallow=False), copy)


@NEEDS
class AgainstChromium(unittest.TestCase):
    def test_metrics_are_current(self):
        r = subprocess.run([sys.executable, os.path.join(ROOT, "dev", "font_metrics.py"), "--check"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_text_width_matches_the_drawn_width(self):
        from playwright.sync_api import sync_playwright
        rng = random.Random(2)
        words = ["$474,900", "Listing Brokerage", "Owner's Title Policy", "Sep 24", "−$12,788", "3.25%", "Whispering",
                 "Cypress", "Hammock", "Boulevard", "1,850 Sq Ft", "AS IS", "→", "Mortgage Payoff", "Q"]
        samples = [(" ".join(rng.choice(words) for _ in range(rng.randint(1, 6))), rng.choice([False, True]),
                    rng.choice([7, 8.6, 11, 15])) for _ in range(60)]
        doc = render.page("<div id='box'></div>", theme_css=design.css_vars(design.theme(None, "buyer")),
                          body_class="font-bundled")
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                pg = browser.new_page()
                pg.set_content(doc, wait_until="load")
                pg.evaluate(render.LOAD_FONTS)
                drawn = pg.evaluate("""(samples) => samples.map(([t, bold, size]) => {
                  const s = document.createElement('span');
                  s.style.cssText = `font-size:${size}px;font-weight:${bold ? 700 : 400};white-space:pre;font-kerning:none`;
                  s.textContent = t; document.getElementById('box').appendChild(s);
                  const w = s.getBoundingClientRect().width; s.remove(); return w; })""", samples)
                family = pg.evaluate("() => getComputedStyle(document.body).fontFamily")
                loaded = pg.evaluate("() => [...document.fonts].filter(f => f.family.includes('Report Sans'))"
                                     ".map(f => f.status)")
            finally:
                browser.close()
        self.assertTrue(family.startswith('"Report Sans"'), family)
        self.assertEqual(loaded, ["loaded", "loaded"])
        for (text, bold, size), w in zip(samples, drawn):
            est = layout.text_width(text, size, bold)
            self.assertAlmostEqual(est, w, delta=max(0.5, 0.01 * w), msg=text)


if __name__ == "__main__":
    unittest.main()
