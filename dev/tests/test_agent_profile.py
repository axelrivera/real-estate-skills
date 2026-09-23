"""Tests for plugins/core/skills/agent-profile/scripts (run against the synced _shared copy)."""
import contextlib
import io
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "core", "skills", "agent-profile", "scripts")
sys.path.insert(0, os.path.abspath(SCRIPTS))
import extract_colors as ec  # noqa: E402
import read_profile  # noqa: E402
import render as agent_render  # noqa: E402
from _shared import profiles  # noqa: E402
from PIL import Image  # noqa: E402

FULL = {
    "name": "Jane Doe", "team": "The Doe Group", "brokerage": "Sunshine Realty", "license": "SL1234567",
    "phone": "(407) 555-0100", "email": "jane@example.com", "website": "https://example.com",
    "brand": {"buyer_primary": "#1f3a5f", "seller_primary": "#D4AF37"},
    "voice": "Warm and direct.", "disclaimers": "Information deemed reliable but not guaranteed.",
}


def image(tmp, blocks, size=(100, 100), mode="RGB"):
    """blocks: [(color, fraction of width)] painted left to right."""
    im = Image.new(mode, size, (255, 255, 255, 0) if mode == "RGBA" else "white")
    x = 0
    for color, frac in blocks:
        w = int(size[0] * frac)
        im.paste(color, (x, 0, x + w, size[1]))
        x += w
    path = os.path.join(tmp, "img.png")
    im.save(path)
    return path


class Images(unittest.TestCase):
    def test_single_brand_color_on_white(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((31, 58, 95), 0.3)]))
        self.assertEqual(r["colors"][0]["name"], "Navy")
        self.assertNotIn("split", r["suggestion"])

    def test_two_strong_colors_offer_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((31, 58, 95), 0.4), ((212, 175, 55), 0.3)]))
        self.assertEqual([c["name"] for c in r["colors"][:2]], ["Navy", "Gold"])
        self.assertIn("split", r["suggestion"])
        self.assertTrue(any("Gold is too light" in n for n in r["notes"]))

    def test_small_accent_does_not_offer_split(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((31, 58, 95), 0.6), ((198, 40, 40), 0.05)]))
        self.assertNotIn("split", r["suggestion"])

    def test_black_and_white_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((17, 17, 17), 0.5)]))
        self.assertEqual(r["colors"], [])
        self.assertEqual([c["name"] for c in r["suggestion"]["alternatives"]], ["Charcoal", "Navy"])

    def test_transparent_background_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((140, 29, 64, 255), 0.2)], mode="RGBA"))
        self.assertEqual(r["colors"][0]["name"], "Burgundy")
        self.assertAlmostEqual(r["colors"][0]["share"], 1.0, places=2)


class Websites(unittest.TestCase):
    HTML = """<html><head>
      <meta name="theme-color" content="#1F3A5F">
      <link rel="stylesheet" href="/site.css"><link rel="stylesheet" href="https://fonts.example.net/f.css">
      <style>body{color:#333;background:#fff} a{color:#1F3A5F}</style></head>
      <body style="border-color: rgb(212, 175, 55)"></body></html>"""
    CSS = ":root{--brand-accent:#D4AF37;--gray:#777} .btn{background:#d4af37} .x{color:#C62828}"

    def fetch(self, url):
        self.fetched.append(url)
        return self.CSS

    def setUp(self):
        self.fetched = []

    def test_theme_color_first_and_same_site_css_only(self):
        r = ec.from_html(self.HTML, "https://jane.example.com/", fetch=self.fetch)
        self.assertEqual(self.fetched, ["https://jane.example.com/site.css"])
        self.assertEqual(r["colors"][0]["name"], "Navy")
        self.assertEqual(r["colors"][0]["evidence"], "site theme color")
        self.assertEqual(r["colors"][1]["name"], "Gold")
        self.assertIn("--brand-accent", r["colors"][1]["evidence"])

    def test_page_without_colors(self):
        r = ec.from_html("<html><style>body{color:#000;background:#fff}</style></html>", "https://x.com")
        self.assertEqual(r["colors"], [])
        self.assertTrue(r["notes"])

    def test_unreachable_site_asks_for_image(self):
        r = ec.from_url("https://nonexistent.invalid")
        self.assertEqual(r["colors"], [])
        self.assertIn("image", r["notes"][0])


class Render(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(io.StringIO()) as err:
            path = agent_render.build(FULL, "md", tmp)[0]
            self.assertEqual(os.path.basename(path), "agent-profile.md")
            back = read_profile.read(path)
        self.assertIn("Gold is too light", err.getvalue())
        self.assertEqual(back["missing_required"], [])
        self.assertEqual(back["data"]["brand"], {"buyer_primary": "#1F3A5F", "seller_primary": "#D4AF37"})
        self.assertEqual(back["colors"]["buyer_primary"]["name"], "Navy")
        for key in ("name", "team", "brokerage", "license", "phone", "email", "website", "voice", "disclaimers"):
            self.assertEqual(back["data"][key], FULL[key], key)

    def test_minimal_profile_has_no_empty_fields(self):
        text = agent_render.to_markdown({"name": "Sam", "brokerage": "Coastal", "team": " ", "brand": {}})
        data, sections = profiles.parse(text)
        self.assertEqual(set(data), {"profile", "schema", "name", "brokerage"})
        self.assertNotIn("brand colors", sections)

    def test_quotes_and_special_characters_survive(self):
        tricky = {"name": 'Ana "AJ" Peña: Broker', "brokerage": "#1 Realty, LLC", "phone": "+1 (787) 555-0100"}
        data, _ = profiles.parse(agent_render.to_markdown(tricky))
        for k, v in tricky.items():
            self.assertEqual(data[k], v)

    def test_required_fields_and_bad_colors(self):
        with self.assertRaises(ValueError):
            agent_render.to_markdown({"name": "Sam"})
        with self.assertRaises(ValueError):
            agent_render.to_markdown({"name": "Sam", "brokerage": "B", "brand": {"primary": "navy"}})

    def test_single_color_summary(self):
        _, sections = profiles.parse(agent_render.to_markdown({"name": "S", "brokerage": "B", "brand": {"primary": "#1F3A5F"}}))
        self.assertEqual(sections["brand colors"], "Navy for all reports.")


if __name__ == "__main__":
    unittest.main()
