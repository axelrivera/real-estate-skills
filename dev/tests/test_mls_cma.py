"""Tests for shared/mls.py and shared/cma.py."""
import csv
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
from shared import cma, mls, profiles  # noqa: E402

EXPORT = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "export-spring-oaks.csv")
FL = profiles.load_market(state="FL", county="Seminole")
SUBJECT = {"address": "517 HICKORYWOOD AVE", "living_area": 1849, "private_pool": True, "subdivision": "SPRING OAKS UNIT 2"}


class Load(unittest.TestCase):
    def test_stellar_export(self):
        homes = mls.load(EXPORT, FL)
        self.assertEqual(len(homes), 51)
        h = next(h for h in homes if h["address"] == "622 SPRING OAKS BLVD")
        self.assertEqual((h["status"], h["close_price"], h["living_area"], h["private_pool"]), ("SOLD", 505500.0, 1824.0, True))
        self.assertEqual(str(h["close_date"]), "2026-04-24")
        self.assertEqual({h["status"] for h in homes}, {"SOLD", "ACTIVE", "PENDING", "EXPIRED"})

    def test_missing_columns_and_unknown_mls(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.csv")
            with open(path, "w", newline="") as f:
                csv.writer(f).writerows([["Address", "Status"], ["1 A ST", "SLD"]])
            with self.assertRaises(mls.ExportError):
                mls.load(path, FL)
        with self.assertRaises(mls.ExportError):
            mls.load(EXPORT, profiles.load_market(state="TX"))

    def test_other_mls_column_names(self):
        tx_cols = {"address": "Street", "status": "St", "living_area": "SqFt", "close_price": "Sold $", "current_price": "List $",
                   "close_date": "Closed", "original_list_price": "Orig $"}
        with tempfile.TemporaryDirectory() as tmp:
            prof = os.path.join(tmp, "tx.md")
            with open(prof, "w") as f:
                f.write("---\nprofile: market\nstate: TX\nmls: ACTRIS\nmls_format:\n  cma_export_columns:\n" +
                        "".join(f'    {k}: "{v}"\n' for k, v in tx_cols.items()) + "---\n")
            path = os.path.join(tmp, "e.csv")
            with open(path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(["Street", "St", "SqFt", "Sold $", "List $", "Closed", "Orig $"])
                w.writerow(["1 Elm", "Closed", "2,000", "$500,000", "$510,000", "2026-08-01", "$510,000"])
            homes = mls.load(path, profiles.load_market(prof))
        self.assertEqual((homes[0]["status"], homes[0]["close_price"], homes[0]["living_area"]), ("SOLD", 500000.0, 2000.0))


class Stats(unittest.TestCase):
    def setUp(self):
        self.homes = mls.load(EXPORT, FL)

    def test_market_stats(self):
        s = mls.market_stats(self.homes, SUBJECT, split_date="2026-07-01")
        self.assertEqual(s["sold_early"]["n"] + s["sold_recent"]["n"], s["sold_all"]["n"])
        self.assertEqual(s["active_count"], 14)  # subject excluded
        self.assertLess(s["sold_recent"]["median_sale_to_original_list"], s["sold_early"]["median_sale_to_original_list"])
        self.assertEqual(s["subdivision"]["name_match"], "SPRING OAKS")
        top = [c["address"] for c in s["sold_candidates"][:5]]
        self.assertIn("602 MOCKINGBIRD LN", top)
        self.assertNotIn("517 HICKORYWOOD AVE", [c["address"] for c in s["competition"]])

    def test_exclude_address_drops_subject_rows(self):
        s = mls.market_stats(self.homes, SUBJECT, exclude_address="517 hickorywood ave")
        self.assertEqual(s["status_counts"]["ACTIVE"], 14)

    def test_trend(self):
        fit = mls.trend(self.homes, 1849, exclude_address="517 HICKORYWOOD AVE")
        self.assertGreater(fit["slope"], 0)
        self.assertTrue(0 <= fit["r2"] <= 1)
        self.assertEqual(mls.r2_key(0.1), "r2_small")
        self.assertEqual(mls.r2_key(0.83), "r2_most")
        self.assertIsNone(mls.trend(self.homes[:2], 1849))


class Blocks(unittest.TestCase):
    def test_groups_heading_intro_and_figure(self):
        els = ['<h2>A</h2>', '<p>intro</p>', '<div class="tbl"><table></table></div>', '<p class="note">n</p>',
               '<p>loose</p>', '<h2>B</h2>', '<p>method</p>', '<footer>agent</footer>']
        out = cma.group_blocks(els)
        self.assertTrue(out.startswith('<div class="kg sec"><h2>A</h2><p>intro</p><div class="tbl">'))
        self.assertIn('<p class="note">n</p></div><p>loose</p>', out)
        self.assertIn('<div class="kg sec"><h2>B</h2><p>method</p><footer>agent</footer></div>', out)

    def test_lone_h2_gets_section_class(self):
        self.assertEqual(cma.group_blocks(["<h2>Only</h2>"]), '<h2 class="sec">Only</h2>')

    def test_dotplot_marks(self):
        cards = [{"address": "1 A St", "adjusted": 450000}, {"address": "2 B St", "adjusted": 470000}]
        svg = cma.dotplot(cards, 455000, 480000, 474900, "Asking $474,900", (455000, "Offer"))
        self.assertIn("Asking $474,900", svg)
        self.assertEqual(svg.count('class="dp-dot"'), 2)



class SubjectHeading(unittest.TestCase):
    def test_location_line_puts_mls_last(self):
        h = cma.subject_heading({"address": "517 Hickorywood Ave", "summary_facts": "4 bed · 2 bath",
                                 "locality": "Altamonte Springs, FL 32714 · MLS O6433709 · Spring Oaks · Seminole County"})
        self.assertIn('<h1>517 Hickorywood Ave</h1>', h)
        self.assertIn('<div class="divrow loc"><div><span>Altamonte Springs, FL 32714</span><span>Spring Oaks</span>'
                      '<span>Seminole County</span><span>MLS O6433709</span></div></div>', h)
        self.assertIn("<span>4 bed</span><span>2 bath</span>", h)

    def test_escaping_and_empty_rows(self):
        h = cma.subject_heading({"address": "1 A & B St"})
        self.assertIn("1 A &amp; B St", h)
        self.assertNotIn("loc", h)
        self.assertNotIn("homefacts", h)


class AuditStatsAndCharts(unittest.TestCase):
    """CMA-8, CMA-9, CMA-12, CMA-22."""

    def setUp(self):
        self.homes = mls.load(EXPORT, FL)

    def test_distressed_and_new_construction_flags(self):
        from datetime import date
        self.assertEqual(mls.sale_flags({"sale_terms": "REO/Bank Owned", "remarks": ""}), ["distressed"])
        self.assertEqual(mls.sale_flags({"remarks": "Short sale, subject to lender approval"}), ["distressed"])
        self.assertEqual(mls.sale_flags({"year_built": 2026, "close_date": date(2026, 5, 1), "remarks": ""}), ["new_construction"])
        self.assertEqual(mls.sale_flags({"year_built": 1972, "close_date": date(2026, 5, 1), "remarks": "Updated kitchen"}), [])

    def test_distressed_sale_ranks_lower(self):
        base = mls.market_stats(self.homes, SUBJECT)["sold_candidates"]
        top = base[0]["address"]
        for h in self.homes:
            if h["address"] == top:
                h["sale_terms"] = "Foreclosure"
        ranked = [c["address"] for c in mls.market_stats(self.homes, SUBJECT)["sold_candidates"]]
        self.assertNotEqual(ranked[0], top)
        self.assertIn("distressed", next(c for c in mls.market_stats(self.homes, SUBJECT)["sold_candidates"]
                                         if c["address"] == top)["flags"])

    def test_limit_and_rest(self):
        s = mls.market_stats(self.homes, SUBJECT, limit=5)
        self.assertEqual(len(s["sold_candidates"]), 5)
        n_sold = s["sold_all"]["n"]
        self.assertEqual(s["more_candidates"], n_sold - 5)

    def test_sale_to_list_is_net_of_seller_costs(self):
        sold = [{"close_price": 500000, "original_list_price": 500000, "seller_paid": 10000, "living_area": 2000,
                 "days_on_market": 10}]
        self.assertEqual(mls.period_stats(sold)["median_sale_to_original_list"], 0.98)

    def test_months_supply_runs_to_as_of_with_pendings(self):
        s = mls.market_stats(self.homes, SUBJECT, split_date="2026-07-01")
        later = mls.market_stats(self.homes, SUBJECT, split_date="2026-07-01", as_of="2026-12-31")
        self.assertGreater(later["months_supply_at_recent_pace"], s["months_supply_at_recent_pace"])  # slower pace
        self.assertEqual(later["window"]["as_of"], "2026-12-31")

    def test_bad_split_date_is_a_plain_error(self):
        with self.assertRaisesRegex(mls.ExportError, "--split-date"):
            mls.market_stats(self.homes, SUBJECT, split_date="07/01/2026")

    def test_million_dollar_ticks(self):
        self.assertEqual((cma.k(455000), cma.k(1250000), cma.k(2000000)), ("$455K", "$1.25M", "$2M"))
        cards = [{"address": f"{i} Bay Dr", "adjusted": v} for i, v in enumerate((1210000, 1390000, 1480000, 1620000, 1790000))]
        svg = cma.dotplot(cards, 1400000, 1600000, 1550000, "Asking")
        ticks = [t for t in svg.split('class="dp-tick">')[1:]]
        self.assertLessEqual(len(ticks), 8)  # was 29 overlapping labels at $20k steps
        self.assertIn("$1.5M", svg)

if __name__ == "__main__":
    unittest.main()


class DeriveComps(unittest.TestCase):
    """CMA-2: adjusted comp values come from their parts; hand-typed values must agree."""

    def card(self, addr, sold, conc, *adj):
        return {"address": addr, "sold_price": sold, "seller_concessions": conc,
                "adjustments": [{"label": "X", "amount": a} for a in adj]}

    def test_itemized(self):
        comps = {"cards": [self.card("A", 429000, 12000, 30000, -8600), self.card("B", 505500, 0, 1800, -5000, -10000)]}
        self.assertEqual(cma.derive_comps(comps), [])
        self.assertEqual([c["adjusted"] for c in comps["cards"]], [438400, 492300])
        self.assertEqual(comps["summary_rows"], [["B", 505500, 0, 492300], ["A", 429000, 12000, 438400]])

    def test_limits_and_replaced_values(self):
        big = self.card("C", 400000, 0, 70000)          # 17.5% net
        wide = self.card("D", 400000, 0, 60000, -45000)  # 26.3% gross
        typed = dict(self.card("E", 400000, 0, 5000), adjusted=410000)
        w = cma.derive_comps({"cards": [big, wide, typed]})
        self.assertTrue(any(x.startswith("C:") and "18% net" in x for x in w))
        self.assertTrue(any(x.startswith("D:") and "26% gross" in x for x in w))
        self.assertTrue(any(x.startswith("E:") and "replaced by the computed $405,000" in x for x in w))

    def test_hand_typed_must_agree(self):
        ok = {"cards": [{"address": "A", "adjusted": 438400}], "summary_rows": [["A", 429000, 12000, 438400]]}
        self.assertEqual(cma.derive_comps(ok), [])
        for bad in ({"cards": [{"address": "A", "adjusted": 438400}], "summary_rows": [["A", 429000, 12000, 440000]]},
                    {"cards": [{"address": "A", "adjusted": 438400}], "summary_rows": []},
                    {"cards": [self.card("A", 1, 0), {"address": "B", "adjusted": 2}]}):
            with self.assertRaises(ValueError):
                cma.derive_comps(bad)
