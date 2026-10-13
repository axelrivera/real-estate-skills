"""Seller market timing: the window, the date each sale is placed by, busy seasons (wrapping, a gap month, a flat
market), the busiest month, when to list, and the warnings for thin or short data."""
import json
import os
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

compute, render, mls = load("seller-market-timing", "compute", "render", "_shared.mls")

AS_OF = date(2026, 9, 26)


def sale(day, price=400000, contract=True, dom=10, status="SOLD"):
    """A closed sale that went under contract on `day` (closing 30 days later), or closed on it without a contract date."""
    d = date.fromisoformat(day)
    return {"address": f"{d.toordinal() % 9000} SAMPLE OAK CT", "status": status, "close_price": price,
            "contract_date": d if contract else None,
            "close_date": date.fromordinal(d.toordinal() + 30) if contract else d, "days_on_market": dom}


def spread(per_month, years=(2024, 2025, 2026), contract=True, dom=10):
    """Sales by month number: per_month[m - 1] sales in that month of each year, on the 5th, 12th, 19th..."""
    out = []
    for y in years:
        for m, n in enumerate(per_month, 1):
            for i in range(n):
                out.append(sale(f"{y}-{m:02d}-{5 + 7 * (i % 4):02d}", 300000 + 5000 * i, contract, dom))
    return out


def run(homes, **R):
    return compute.compute({"as_of": AS_OF.isoformat(), **R}, homes)


class Window(unittest.TestCase):
    def test_contract_dates_end_before_last_month(self):
        C = run(spread([3] * 12))
        self.assertEqual(C["basis"], "contract")
        self.assertEqual((C["window"]["start"], C["window"]["end"]), ("2024-08-01", "2026-08-01"))
        self.assertEqual(sum(m["sales"] for m in C["months"]), C["sales"])
        self.assertEqual(C["sales"], 72)  # every calendar month twice

    def test_close_dates_end_before_this_month(self):
        C = run(spread([3] * 12, contract=False))
        self.assertEqual(C["basis"], "close")
        self.assertEqual((C["window"]["start"], C["window"]["end"]), ("2024-09-01", "2026-09-01"))
        self.assertTrue(any("no contract dates" in w for w in C["warnings"]))

    def test_mixed_dates_use_the_close_date_for_the_rest(self):
        homes = spread([3] * 12)
        homes[0] = sale("2025-03-05", contract=False)
        C = run(homes)
        self.assertEqual(C["basis"], "contract")
        self.assertTrue(any("1 of" in w and "close date" in w for w in C["warnings"]))

    def test_lookback_whole_years_only(self):
        with self.assertRaises(compute.TimingError):
            run(spread([3] * 12), lookback_months=18)
        self.assertEqual(run(spread([3] * 12, years=(2023, 2024, 2025, 2026)), lookback_months=36)["window"]["months"], 36)

    def test_other_rows_left_off_and_counted(self):
        homes = spread([3] * 12) + [sale("2025-05-05", status="ACTIVE"), sale("2025-05-05", price=None)]
        C = run(homes)
        self.assertEqual(C["sales"], 72)
        self.assertTrue(any("no sold price (1)" in w and "not closed sales (1)" in w for w in C["warnings"]))

    def test_short_export_covers_what_is_there(self):
        C = run(spread([3] * 12, years=(2025, 2026)))
        self.assertEqual(C["window"]["months"], 19)  # January 2025 through July 2026
        self.assertTrue(any("19 months, not the 24" in w for w in C["warnings"]))
        self.assertTrue(any("one season" in w for w in C["warnings"]))

    def test_no_sales_in_the_window(self):
        with self.assertRaises(compute.TimingError):
            run([sale("2020-05-05")])


class Seasons(unittest.TestCase):
    def test_spring_season_and_peak(self):
        C = run(spread([1, 1, 4, 5, 9, 5, 4, 2, 1, 1, 1, 1]))
        self.assertEqual([s["months"] for s in C["seasons"]], [[3, 4, 5, 6, 7]])
        self.assertEqual(C["peak_month"], 5)
        self.assertEqual(C["seasons"][0]["sales"], 2 * (4 + 5 + 9 + 5 + 4))
        self.assertIn(f'{C["seasons"][0]["sales"]} of {C["sales"]} sales went under contract March through July.',
                      C["takeaway"])

    def test_winter_season_wraps_the_new_year(self):
        C = run(spread([6, 6, 5, 2, 1, 1, 1, 1, 1, 2, 5, 6]))
        self.assertEqual([s["months"] for s in C["seasons"]], [[11, 12, 1, 2, 3]])
        self.assertIn("November through March", C["takeaway"])

    def test_a_month_just_under_average_does_not_split_a_season(self):
        rate = [1, 1, 6, 6, 6, 3, 6, 6, 1, 1, 1, 1]
        avg = sum(rate) / 12
        self.assertLess(rate[5], avg)
        self.assertEqual(compute.seasons(rate, avg), [[2, 3, 4, 5, 6, 7]])

    def test_two_seasons(self):
        C = run(spread([1, 1, 6, 6, 1, 1, 1, 1, 6, 6, 1, 1]))
        self.assertEqual(sorted(s["months"] for s in C["seasons"]), [[3, 4], [9, 10]])
        self.assertIsNone(C["peak_month"])  # a tie is no one busiest month

    def test_flat_market_has_no_season(self):
        rate = [5, 6, 5, 6, 5, 6, 5, 6, 5, 6, 5, 6]
        self.assertEqual(compute.seasons(rate, sum(rate) / 12), [])
        C = run(spread([3] * 12))
        self.assertEqual(C["seasons"], [])
        self.assertIn("no clear busy season", C["takeaway"])

    def test_most_of_the_year_is_no_season(self):
        rate = [1, 1, 3, 3, 3, 3, 3, 3, 3, 3, 1, 1]  # eight busy months
        self.assertEqual(compute.seasons(rate, sum(rate) / 12), [])

    def test_thin_data_draws_no_boxes(self):
        C = run(spread([0, 0, 1, 1, 2, 1, 1, 0, 0, 0, 0, 0], years=(2025, 2026)))
        self.assertLess(C["sales"], compute.MIN_SALES)
        self.assertEqual((C["seasons"], C["peak_month"], C["takeaway"]), ([], None, ""))
        self.assertTrue(any("too few" in w for w in C["warnings"]))

    def test_override(self):
        C = run(spread([3] * 12), season_override=[11, 12, 1])
        self.assertEqual(C["seasons"][0]["months"], [11, 12, 1])
        self.assertEqual(C["season_source"], "agent")
        for bad in ([3, 5], [0, 1], [1] * 2, list(range(1, 13)), "spring"):
            with self.subTest(bad=bad), self.assertRaises(compute.TimingError):
                run(spread([3] * 12), season_override=bad)


class ListBy(unittest.TestCase):
    def test_season_start_less_median_days_on_market(self):
        self.assertEqual(compute.list_by(3, 10), "late March")  # April 1 less 10 days: March 22
        self.assertEqual(compute.list_by(3, 20), "mid-March")
        self.assertEqual(compute.list_by(0, 45), "mid-November")  # across the new year
        self.assertEqual(compute.list_by(3, 0), "early April")

    def test_only_with_contract_dates_and_days_on_market(self):
        shape = [1, 1, 4, 5, 9, 5, 4, 2, 1, 1, 1, 1]
        self.assertEqual(run(spread(shape, dom=25))["list_by"], "early February")
        self.assertIsNone(run(spread(shape, contract=False))["list_by"])
        C = run(spread(shape, dom=None))
        self.assertIsNone(C["list_by"])
        self.assertTrue(any("days on market" in w for w in C["warnings"]))


class Export(unittest.TestCase):
    def test_load_asks_only_for_the_columns_it_needs(self):
        csv = ("Address,Status,Close Price,Close Date,Contract Date\n"
               '1 SAMPLE OAK CT,SLD,"$400,000",05/20/2026,04/20/2026\n')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "export.csv")
            with open(path, "w") as f:
                f.write(csv)
            with open(os.path.join(tmp, "market-timing.json"), "w") as f:
                json.dump({"export": "export.csv", "state": "FL", "county": "Seminole"}, f)
            _, homes = compute.load_inputs({"export": "export.csv", "state": "FL", "county": "Seminole"},
                                           data_file=os.path.join(tmp, "market-timing.json"))
            self.assertEqual(homes[0]["contract_date"], date(2026, 4, 20))
            market = compute.profiles.load_market(state="FL", county="Seminole")
            with self.assertRaises(mls.ExportError):  # a CMA still needs the size and list price
                mls.load(path, market)


class FromTheExport(unittest.TestCase):
    def test_the_mls_comes_from_the_headers_without_a_place(self):
        csv = ("ML Number,Status,Address,Legal Subdivision Name,Close Price,Close Date,Contract Date,CDOM\n"
               'X1,SLD,1 SAMPLE OAK CT,SAMPLE RIDGE,"$400,000",05/20/2026,04/20/2026,9\n')
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "export.csv"), "w") as f:
                f.write(csv)
            _, homes = compute.load_inputs({"export": "export.csv"}, data_file=os.path.join(tmp, "m.json"))
        self.assertEqual(homes[0]["contract_date"], date(2026, 4, 20))
        self.assertIsNone(compute.profiles.mls_for_headers({"Addr", "Price"}, compute.REQUIRED))

    def test_an_area_the_export_does_not_name_is_flagged(self):
        homes = spread([3] * 12)
        for h in homes:
            h["subdivision"] = "SAMPLE RIDGE UNIT 2"
        self.assertFalse(any("not Example Lakes" in w for w in run(homes, area="Sample Ridge")["warnings"]))
        self.assertTrue(any("not Example Lakes" in w for w in run(homes, area="Example Lakes")["warnings"]))


class Chart(unittest.TestCase):
    def test_dots_stay_inside_their_month_and_its_boxes(self):
        C = run(spread([1, 1, 4, 5, 9, 5, 4, 2, 1, 1, 1, 1]) + [sale("2026-05-01"), sale("2026-05-31")])
        for p in C["_points"]:
            frac = p["x"] - (p["date"].month - 1)
            self.assertTrue(compute.INSET - 1e-9 <= frac <= 1 - compute.INSET + 1e-9, p)
        band = (render.cma.SHEET_SIZE[0] - 78 - 16) / 12  # the sheet's month column
        self.assertGreater(compute.INSET * band - render.HALF_WIDTH, 1.5 + 1.5)  # clear of the busiest month's box


    def test_wrapping_season_draws_two_boxes(self):
        self.assertEqual(render._runs([10, 11, 0, 1]), [[10, 11], [0, 1]])
        self.assertEqual(render._runs([2, 3, 4]), [[2, 3, 4]])

    def test_legend_names_what_is_drawn(self):
        C = run(spread([1, 1, 4, 5, 9, 5, 4, 2, 1, 1, 1, 1]))
        chart = render.layout.Chart()
        svg = render.draw(C, chart, (1000, 560))
        self.assertEqual(chart.drawn(), ["y0", "y1", "season", "peak"])
        self.assertEqual(svg.count('class="sale"'), C["sales"])
        self.assertEqual(svg.count('class="season"'), 1)


if __name__ == "__main__":
    unittest.main()
