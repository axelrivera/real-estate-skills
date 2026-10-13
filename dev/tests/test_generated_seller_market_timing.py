"""Seller market timing on generated inputs (dev/generators/seller_market_timing.py): universal properties of the
document model and the printed page, for any valid input. Never a sentence, never a past case.

  - counts: every sale is in the window and in its month, and the months add up to the total;
  - seasons: months in a row (December into January), two to seven of them, at most two, their sales the months';
    the takeaway's counts are the seasons' and the total; the busiest month is the one top month;
  - the chart: one dot per sale, the legend names exactly the series drawn;
  - the page: one landscape page, nothing clipped or over it.

FUZZ_N inputs (8 by default), seeds from FUZZ_SEED (0). The printed checks need Chromium and pdftotext and are skipped
without them.
"""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import seller_market_timing as gen  # noqa: E402

compute, render, layout = load("seller-market-timing", "compute", "render", "_shared.layout")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
SEED = int(os.environ.get("FUZZ_SEED", "0"))


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


PRINTS = bool(shutil.which("pdftotext")) and have_chromium()


def model(seed, tmp):
    """(data, model or the TimingError) for one seed, its export written beside the data file."""
    data, text = gen.generate(seed)
    with open(os.path.join(tmp, "export.csv"), "w", encoding="utf-8") as f:
        f.write(text)
    path = os.path.join(tmp, "market-timing.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    try:
        return data, compute.run(copy.deepcopy(data), data_file=path)
    except compute.TimingError as e:  # an export with no sale in the window says so; nothing else may fail
        return data, e


def cases():
    for seed in range(SEED, SEED + N_CASES):
        with tempfile.TemporaryDirectory() as tmp:
            data, C = model(seed, tmp)
            if isinstance(C, compute.TimingError):
                assert "No closed sales" in str(C), str(C)
                continue
            yield seed, data, C


def consecutive(months):
    return all((b - a) % 12 == 1 for a, b in zip(months, months[1:]))


class Model(unittest.TestCase):
    def test_counts_add_up(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                start, end = date.fromisoformat(C["window"]["start"]), date.fromisoformat(C["window"]["end"])
                pts = C["_points"]
                self.assertEqual(len(pts), C["sales"])
                self.assertTrue(all(start <= p["date"] < end for p in pts))
                for m in C["months"]:
                    self.assertEqual(m["sales"], sum(1 for p in pts if p["date"].month == m["month"]))
                    self.assertEqual(m["median_price"] is None, m["sales"] == 0)
                self.assertTrue(all(0 <= p["x"] < 12 and int(p["x"]) == p["date"].month - 1 for p in pts))
                self.assertTrue(all(0 <= p["year"] < C["window"]["lookback"] // 12 for p in pts))

    def test_seasons_and_takeaway(self):
        for seed, data, C in cases():
            with self.subTest(seed=seed):
                self.assertLessEqual(len(C["seasons"]), compute.MAX_SEASONS)
                for s in C["seasons"]:
                    self.assertTrue(consecutive(s["months"]))
                    self.assertEqual(s["sales"], sum(C["months"][m - 1]["sales"] for m in s["months"]))
                    if C["season_source"] == "sales":
                        self.assertTrue(2 <= len(s["months"]) <= compute.MAX_SEASON)
                    for m in s["months"]:
                        self.assertIn(C["months"][m - 1]["season"], ("busy", "peak"))
                flagged = {m["month"] for m in C["months"] if m["season"]}
                self.assertEqual(flagged - {C["peak_month"]}, {m for s in C["seasons"] for m in s["months"]} - {C["peak_month"]})
                if C["peak_month"]:
                    rates = [m["per_year"] for m in C["months"]]
                    self.assertEqual(rates.index(max(rates)) + 1, C["peak_month"])
                    self.assertEqual(rates.count(max(rates)), 1)
                if C["seasons"]:
                    n, total = map(int, re.match(r"(\d+) of (\d+) sales", C["takeaway"]).groups())
                    self.assertEqual((n, total), (sum(s["sales"] for s in C["seasons"]), C["sales"]))
                if C["sales"] < compute.MIN_SALES and not data.get("season_override"):
                    self.assertEqual((C["seasons"], C["peak_month"]), ([], None))
                self.assertEqual(C["list_by"] is not None, "List by" in C["takeaway"])
                if C["list_by"]:
                    self.assertEqual(C["basis"], "contract")

    def test_no_placeholder_left_empty(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                texts = list(placeholders.strings(compute.public(C)))
                self.assertEqual(placeholders.problems(texts), [])

    def test_compute_never_changes_the_input(self):
        for seed in range(SEED, SEED + N_CASES):
            data, text = gen.generate(seed)
            with tempfile.TemporaryDirectory() as tmp:
                with open(os.path.join(tmp, "export.csv"), "w", encoding="utf-8") as f:
                    f.write(text)
                before = copy.deepcopy(data)
                with contextlib.suppress(compute.TimingError):
                    compute.run(data, data_file=os.path.join(tmp, "market-timing.json"))
                self.assertEqual(data, before)

    def test_one_dot_per_sale_and_the_legend_names_what_is_drawn(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                chart = layout.Chart()
                svg = render.draw(C, chart, (1000, 560))
                self.assertEqual(svg.count('class="sale"'), C["sales"])
                drawn = {f"y{p['year']}" for p in C["_points"]}
                drawn |= {"season"} if C["seasons"] else set()
                drawn |= {"peak"} if C["peak_month"] else set()
                self.assertEqual(set(chart.drawn()), drawn)


@unittest.skipUnless(PRINTS, "needs Chromium and pdftotext")
class Printed(unittest.TestCase):
    def test_one_page_nothing_clipped(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    (path,) = render.build(C, "pdf", tmp, {"agent": {}})
                self.assertNotIn("clipped", err.getvalue())
                self.assertNotIn("overflows", err.getvalue())
                text = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout
                self.assertEqual(text.count("\f"), 1, "one page")
                if C["takeaway"]:
                    self.assertIn(" ".join(C["takeaway"].split()[:4]), " ".join(text.split()))


if __name__ == "__main__":
    unittest.main()
