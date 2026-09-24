"""Tests for plugins/core/skills/agent-profile/scripts (run against the synced _shared copy)."""
import os
import sys
import tempfile
import unittest

SCRIPTS = os.path.join(os.path.dirname(__file__), "..", "..", "plugins", "core", "skills", "agent-profile", "scripts")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

check_profile, ec, profiles = load("agent-profile", "check_profile", "extract_colors", "_shared.profiles")
from PIL import Image  # noqa: E402

TEMPLATE = os.path.join(SCRIPTS, "..", "assets", "agent-profile-template.md")
PLACEHOLDERS = {
    "full name": "name", "team name": "team", "brokerage": "brokerage", "license number": "license",
    "phone": "phone", "email": "email", "website": "website",
    "how the agent writes": "voice", "disclaimers for documents": "disclaimers",
}


def fill(values, brand=None):
    """Fill the template the way SKILL.md step 4 describes: drop lines and sections not given."""
    with open(TEMPLATE) as f:
        lines = f.read().splitlines()
    out, skip_section = [], False
    for line in lines:
        raw = line
        if line.startswith("## "):
            section = line[3:].lower()
            skip_section = (section == "brand colors" and not brand) or \
                           (section in ("voice", "disclaimers") and section not in values)
        if skip_section:
            continue
        if line.startswith("brand:") and not brand:
            continue
        key = line.strip().split(":")[0]
        if key in ("primary", "buyer_primary", "seller_primary"):
            if not brand or key not in brand:
                continue
            line = f'  {key}: "{brand[key]}"'
        elif "{{color name}} for all reports" in line:
            line = "Color for all reports."
        for ph, field in PLACEHOLDERS.items():
            if "{{" + ph + "}}" in line:
                if field not in values:
                    line = None
                    break
                line = line.replace("{{" + ph + "}}", values[field].replace('"', '\\"') if ":" in line else values[field])
        if line is None and "{{team name}} · {{brokerage}}" in raw and "brokerage" in values:
            line = values["brokerage"]  # SKILL.md step 4: without a team, just the brokerage
        if line is not None and "{{" in line and line.lstrip().startswith(("- {state", "brokerage_")):
            line = None  # CORE-15's optional license and brokerage lines, left out when not given
        if line is not None and line.startswith("licenses:"):
            line = None
        if line is not None:
            out.append(line)
    return "\n".join(out) + "\n"


def write_profile(tmp, text):
    path = os.path.join(tmp, "agent-profile.md")
    with open(path, "w") as f:
        f.write(text)
    return path


FULL = {
    "name": "Jane Doe", "team": "The Doe Group", "brokerage": "Sunshine Realty", "license": "SL1234567",
    "phone": "(407) 555-0100", "email": "jane@example.com", "website": "https://example.com",
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
        self.assertTrue(any("Navy for all reports is also a good choice" in n for n in r["notes"]))

    def test_exact_logo_colors_not_bucket_centers(self):
        """Report the logo's real colors (#1F3A5F, #D4AF37), not the rounded bucket centers."""
        with tempfile.TemporaryDirectory() as tmp:
            r = ec.from_image(image(tmp, [((31, 58, 95), 0.4), ((29, 60, 92), 0.05), ((212, 175, 55), 0.3)]))
        self.assertEqual([c["hex"] for c in r["colors"][:2]], ["#1F3A5F", "#D4AF37"])

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
      <link rel="stylesheet" href="/site.css"><link rel="stylesheet" href="https://fonts.googleapis.com/css?family=X">
      <link rel="stylesheet" href="https://www.jane.example.com/theme.css"><link rel="stylesheet" href="https://cdn.builder.net/b.css">
      <style>body{color:#333;background:#fff} a{color:#1F3A5F}</style></head>
      <body style="border-color: rgb(212, 175, 55)"></body></html>"""
    CSS = ":root{--brand-accent:#D4AF37;--gray:#777} .btn{background:#d4af37} .x{color:#C62828}"

    def fetch(self, url):
        self.fetched.append(url)
        return self.CSS if url.endswith("/site.css") else ".noop{color:#777}"

    def setUp(self):
        self.fetched = []

    def test_theme_color_first_and_site_css(self):
        """CORE-20: www. and the bare domain are one site, and a CDN or site builder's CSS is read; font CSS isn't."""
        r = ec.from_html(self.HTML, "https://jane.example.com/", fetch=self.fetch)
        self.assertEqual(self.fetched, ["https://jane.example.com/site.css", "https://www.jane.example.com/theme.css",
                                        "https://cdn.builder.net/b.css"])
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


class Template(unittest.TestCase):
    def test_full_profile_passes_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile(tmp, fill(FULL, {"buyer_primary": "#1F3A5F", "seller_primary": "#D4AF37"}))
            r = check_profile.check(path)
            agent = profiles.load_agent(path)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["colors"]["buyer"]["name"], "Navy")
        self.assertEqual(r["colors"]["seller"]["name"], "Gold")
        self.assertTrue(any("Gold is too light" in w for w in r["warnings"]))
        for key, value in FULL.items():
            self.assertEqual(agent[key], value, key)

    def test_minimal_profile_passes_check(self):
        with tempfile.TemporaryDirectory() as tmp:
            text = fill({"name": "Sam", "brokerage": "Coastal Homes"})
            r = check_profile.check(write_profile(tmp, text))
        self.assertIn("\nCoastal Homes\n", text)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["fields"], ["name", "brokerage"])
        self.assertTrue(r["colors"]["buyer"]["default"])

    def test_quotes_survive(self):
        values = {"name": 'Ana "AJ" Peña', "brokerage": "#1 Realty, LLC"}
        with tempfile.TemporaryDirectory() as tmp:
            agent = profiles.load_agent(write_profile(tmp, fill(values)))
        self.assertEqual((agent["name"], agent["brokerage"]), (values["name"], values["brokerage"]))


class Check(unittest.TestCase):
    def check_text(self, text):
        with tempfile.TemporaryDirectory() as tmp:
            return check_profile.check(write_profile(tmp, text))

    def test_leftover_placeholders(self):
        with open(TEMPLATE) as f:
            r = self.check_text(f.read())
        self.assertFalse(r["ok"])
        self.assertTrue(any("placeholders" in p for p in r["problems"]))

    def test_missing_brokerage_and_bad_color(self):
        r = self.check_text('---\nprofile: agent\nname: "Sam"\nbrand: {primary: "navy"}\n---\n')
        self.assertFalse(r["ok"])
        self.assertIn("Missing brokerage.", r["problems"])
        self.assertTrue(any("navy" in p for p in r["problems"]))

    def test_unreadable_file(self):
        r = self.check_text("no settings block")
        self.assertFalse(r["ok"])



class AuditProfileFields(unittest.TestCase):
    """CORE-14 (numbers in quotes), CORE-15 (licenses and brokerage details), CORE-20 (SVG, unreadable files)."""

    def test_unquoted_number_is_a_problem(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile(tmp, "---\nprofile: agent\nname: Jane Doe\nbrokerage: Sample Realty\nlicense: 0123456\n---\n")
            r = check_profile.check(path)
        self.assertFalse(r["ok"])
        self.assertTrue(any("license is written as a number" in x for x in r["problems"]))

    def test_licenses_and_brokerage_block(self):
        text = ("---\nprofile: agent\nname: Jane Doe\nbrokerage:\n  name: Sample Realty LLC\n  license: \"CQ1234\"\n"
                "  address: 1 Main St, Orlando, FL\n  phone: \"407-555-0100\"\nlicenses:\n"
                "  - {state: FL, type: sales associate, number: \"SL123\"}\n  - {state: NY, type: salesperson, number: \"10401\"}\n---\n")
        with tempfile.TemporaryDirectory() as tmp:
            agent = profiles.load_agent(write_profile(tmp, text))
        self.assertEqual(agent["brokerage"], "Sample Realty LLC")
        self.assertEqual(agent["license"], "FL sales associate SL123; NY salesperson 10401")
        from _shared import render  # the skill's synced copy
        lines = render.notice_lines(agent)
        self.assertIn("Sample Realty LLC, Lic. CQ1234, 1 Main St, Orlando, FL, 407-555-0100.", lines)

    def test_svg_logo(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "logo.svg")
            with open(path, "w") as fh:
                fh.write('<svg><rect fill="#1F3A5F"/><path fill="#1F3A5F"/><circle stroke="#D4AF37"/><g fill="#fff"/></svg>')
            r = ec.from_image(path)
        self.assertEqual([c["name"] for c in r["colors"]][:2], ["Navy", "Gold"])

    def test_unreadable_file_says_so(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "card.heic")
            with open(path, "wb") as fh:
                fh.write(b"not an image")
            r = ec.from_image(path)
        self.assertFalse(r["ok"])
        self.assertIn("PNG or JPG", r["notes"][0])


class AuditSmallFixes(unittest.TestCase):
    def test_agents_own_color_name(self):
        """CORE-27: warnings use the agent's word for the color."""
        with tempfile.TemporaryDirectory() as tmp:
            path = write_profile(tmp, '---\nprofile: agent\nname: Jane Doe\nbrokerage: Sample Realty\nbrand:\n'
                                      '  primary: "#D4AF37"  # Gold\n---\n')
            r = check_profile.check(path)
        self.assertEqual(r["colors"]["buyer"]["name"], "Gold")
        self.assertTrue(r["warnings"][0].startswith("Gold is too light"))

    def test_missing_logo_file(self):
        """CORE-26: a missing file is reported as a missing file, not a website."""
        import contextlib
        import io
        import json as _json
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ec.main(["no-such-logo.png"])
        r = _json.loads(out.getvalue())
        self.assertFalse(r["ok"])
        self.assertIn("File not found", r["notes"][0])

if __name__ == "__main__":
    unittest.main()
