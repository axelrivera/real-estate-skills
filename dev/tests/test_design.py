import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from shared import design as d  # noqa: E402


class ColorMath(unittest.TestCase):
    def test_parse_hex(self):
        self.assertEqual(d.parse_hex("#1a74ad"), "#1A74AD")
        self.assertEqual(d.parse_hex("1A74AD"), "#1A74AD")
        self.assertEqual(d.parse_hex("#abc"), "#AABBCC")
        for bad in ("navy", "#12345", "", None, 123):
            self.assertIsNone(d.parse_hex(bad))

    def test_oklch_round_trip(self):
        for hx in ("#1A74AD", "#C2410C", "#000000", "#FFFFFF", "#7F7F7F", "#00FF00"):
            self.assertLessEqual(d.distance(hx, d.from_oklch(*d.to_oklch(hx))), 0.005)

    def test_contrast_reference_values(self):
        self.assertAlmostEqual(d.contrast("#000000"), 21.0, places=1)
        self.assertAlmostEqual(d.contrast("#FFFFFF"), 1.0, places=2)

    def test_darken_to_reaches_target_and_keeps_hue_family(self):
        for hx in ("#F2C94C", "#7FDBFF", "#FFB6C1"):
            out = d.darken_to(hx, d.AA)
            self.assertGreaterEqual(d.contrast(out), d.AA)
            self.assertEqual(d.hue_name(out), d.hue_name(hx), hx)


class Defaults(unittest.TestCase):
    def test_default_sides(self):
        self.assertEqual(d.theme(None, "buyer")["brand"], "#1A74AD")
        self.assertEqual(d.theme(None, "seller")["brand"], "#C2410C")
        self.assertEqual(d.theme(None, "buyer")["source"], "default")

    def test_defaults_are_not_adjusted(self):
        for side in ("buyer", "seller"):
            t = d.theme(None, side)
            self.assertEqual(t["adjustments"], [], side)
            self.assertEqual(t["warnings"], [], side)
            self.assertEqual(t["brand_ink"], t["brand"], side)
            self.assertEqual(t["status"], d.STATUS, side)

    def test_default_party_colors(self):
        self.assertEqual(d.party_colors(None), {"buyer": "#1A74AD", "seller": "#C2410C", "both": "#1F3A5F"})

    def test_tints_close_to_prototype(self):
        t = d.theme(None, "buyer")
        for token, proto in (("brand_panel", "#F6F9FB"), ("brand_callout", "#EEF5FA"),
                             ("brand_soft", "#C9DDEB"), ("brand_accent", "#7FB0CF")):
            self.assertLess(d.distance(t[token], proto), 0.02, token)


class Resolution(unittest.TestCase):
    def test_order_side_then_primary_then_default(self):
        brand = {"primary": "#0B6E4F", "seller_primary": "#8C1D40"}
        self.assertEqual(d.resolve(brand, "seller")[:2], ("#8C1D40", "side"))
        self.assertEqual(d.resolve(brand, "buyer")[:2], ("#0B6E4F", "primary"))
        self.assertEqual(d.resolve({"buyer_primary": "#0B6E4F"}, "seller")[:2], ("#C2410C", "default"))

    def test_invalid_color_falls_back_with_warning(self):
        hx, source, warnings = d.resolve({"primary": "navy"}, "buyer")
        self.assertEqual((hx, source), ("#1A74AD", "default"))
        self.assertEqual(len(warnings), 1)

    def test_invalid_side_override_falls_through_to_primary(self):
        self.assertEqual(d.resolve({"buyer_primary": "x", "primary": "#0B6E4F"}, "buyer")[0], "#0B6E4F")

    def test_bad_side(self):
        with self.assertRaises(ValueError):
            d.theme(None, "both")


class Legibility(unittest.TestCase):
    def test_every_brand_text_token_meets_its_target(self):
        for hx in ("#F2C94C", "#FFFFFF", "#111111", "#1A74AD", "#E0FFE0", "#FF00FF"):
            t = d.theme({"primary": hx}, "buyer")
            self.assertGreaterEqual(d.contrast(t["brand_ink"]), d.AA, hx)
            self.assertGreaterEqual(d.contrast(t["brand_strong"]), d.AAA, hx)
            self.assertGreaterEqual(d.contrast(t["brand_deep"]), d.DEEP, hx)

    def test_light_color_keeps_original_for_accents_and_warns(self):
        t = d.theme({"primary": "#F2C94C"}, "buyer")
        self.assertEqual(t["brand"], "#F2C94C")
        self.assertNotEqual(t["brand_ink"], "#F2C94C")
        self.assertTrue(any("too light" in w for w in t["warnings"]))


class StatusSeparation(unittest.TestCase):
    def test_status_shifts_away_from_matching_brand(self):
        for name, tokens in d.STATUS.items():
            t = d.theme({"primary": tokens["base"]}, "buyer")
            self.assertGreaterEqual(d.distance(t["brand"], t["status"][name]["base"]), d.STATUS_MIN_DISTANCE, name)
            self.assertTrue(t["adjustments"], name)

    def test_unrelated_status_untouched(self):
        t = d.theme({"primary": d.STATUS["good"]["base"]}, "buyer")
        self.assertEqual(t["status"]["risk"], d.STATUS["risk"])


class Parties(unittest.TestCase):
    def assertDistinct(self, parties):
        for a, b in (("buyer", "seller"), ("buyer", "both"), ("seller", "both")):
            self.assertGreaterEqual(d.distance(parties[a], parties[b]), d.PARTY_MIN_DISTANCE, (a, b, parties))

    def test_single_color_stays_distinct(self):
        for hx in ("#1A74AD", "#1F3A5F", "#F2C94C", "#111111", "#FFFFFF", "#5A6672"):
            self.assertDistinct(d.party_colors({"primary": hx}))

    def test_split_colors_kept_when_distinct(self):
        p = d.party_colors({"buyer_primary": "#0B6E4F", "seller_primary": "#8C1D40"})
        self.assertEqual((p["buyer"], p["seller"]), ("#0B6E4F", "#8C1D40"))
        self.assertDistinct(p)


class Names(unittest.TestCase):
    def test_every_named_color_names_itself(self):
        for name, hx in d.NAMED.items():
            self.assertEqual(d.color_name(hx), name)

    def test_common_brand_colors(self):
        for hx, name in (("#1A74AD", "Blue"), ("#C2410C", "Burnt Orange"), ("#003366", "Navy"),
                         ("#D4AF37", "Gold"), ("#8C1D40", "Burgundy"), ("#111111", "Black"), ("#008080", "Teal")):
            self.assertEqual(d.color_name(hx), name, hx)


class Formats(unittest.TestCase):
    def test_theme_is_json_serialisable(self):
        json.dumps(d.theme({"primary": "#0B6E4F"}, "seller"))

    def test_css_and_pptx(self):
        t = d.theme(None, "buyer")
        css = d.css_vars(t)
        for var in ("--brand:#1A74AD", "--brand-ink:", "--good-bg:#E6F4EC", "--party-both:#1F3A5F", "--party-both-bg:", "--party-seller-soft:", "--text:#1A1A1A"):
            self.assertIn(var, css)
        px = d.pptx_colors(t)
        self.assertEqual(px["brand"], "1A74AD")
        self.assertTrue(all("#" not in v for v in px.values()))


if __name__ == "__main__":
    unittest.main()
