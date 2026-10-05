"""Buyer CMA on generated inputs (dev/generators/buyer_cma.py): universal properties of the document model and the
printed report, for any valid input. Never a sentence, never a past case.

  - money: every payment column's lines add up to its total and its cash to close, every credit column's cash lines
    to its cash to close, every comp card's lines (sale price, seller-paid costs, adjustments) to its adjusted value;
  - rules: time adjustments follow the method's rule (rate x quarters since the sale, to $100, none after the cutoff);
    a range set by the shared rule passes the shared range checks and stays within the cap;
  - notes: each note is said once (by key and by text) and printed once; no label carries a note;
  - the scatter's legend names exactly the series drawn;
  - compute never changes its input; every dollar figure and percent on the page comes from the model;
  - printed: nothing clipped or over a page, page 1 on one page, no page between the first and last under half full.

FUZZ_N inputs (8 by default; FUZZ_N=200 before a release), seeds from FUZZ_SEED (0). The printed checks need Chromium
and pdftotext and run on the first PRINT_N of them (all by default).
"""
import contextlib
import copy
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import buyer_cma as gen  # noqa: E402

compute, render, notes, fmt, cma, layout = load("buyer-cma", "compute", "render", "_shared.notes", "_shared.fmt",
                                                "_shared.cma", "_shared.layout")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
PRINT_N = int(os.environ.get("PRINT_N", str(N_CASES)))
SEED = int(os.environ.get("FUZZ_SEED", "0"))
FIGURE = re.compile(r"[−-]?\$[\d,]+(?:\.\d+)?[KM]?|\d+(?:\.\d+)?%")


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


PRINTS = bool(shutil.which("pdftotext")) and have_chromium()
TMP = tempfile.mkdtemp(prefix="gen-buyer-cma-")
_CASES = []


def squash(text):
    return " ".join(str(text).split())


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for k, x in v.items():
            if not str(k).startswith("_"):
                yield from strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from strings(x)


def dollars(text):
    """'$1,200', '−$1,200', '+$1,200' as a number."""
    t = text.replace(",", "").replace("$", "")
    sign = -1 if t[:1] in ("−", "-") else 1
    return sign * float(t.lstrip("+−-"))


def cases():
    if not _CASES:
        for seed in range(SEED, SEED + N_CASES):
            d = os.path.join(TMP, str(seed))
            os.makedirs(d, exist_ok=True)
            R = gen.generate(seed, d)
            _CASES.append((seed, R, compute.run(R)))
    return _CASES


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Model(unittest.TestCase):
    def test_tables_add_up(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                for r in C["payments"]["rows"]:
                    self.assertEqual(sum(a for _, _, a in r["monthly"]), r["total"])
                    self.assertEqual(sum(a for _, _, a in r["cash_lines"]), r["cash_to_close"])
                pm = C["costs"]["payment"]
                total = pm["rows"][pm["total_row"]]
                self.assertEqual(total[1:], [fmt.money(r["total"]) for r in C["payments"]["rows"]])
                for c in (C["credit"] or {}).get("columns", []):
                    self.assertEqual(sum(a for _, _, a in c["cash_lines"]), c["cash"])
                for card in C["comps"]["cards"]:
                    self.assertEqual(sum(dollars(v) for _, v in card["lines"]), card["adjusted"])
                    self.assertEqual(card["adjusted_display"], fmt.money(card["adjusted"]))

    def test_time_adjustments_follow_the_rule(self):
        for seed, R, C in cases():
            info = C["time_adjustment"]
            with self.subTest(seed=seed):
                stated = (R["comps"].get("time_adjustment") or {}).get("rate_per_quarter")
                self.assertEqual(bool(info), bool(stated))
                for raw, card in zip(R["comps"]["cards"], C["comps"]["cards"]):
                    lines = [dollars(v) for a, v in card["lines"] if a == cma.TIME_LABEL]
                    closed = fmt.to_date(card["close_date"]) if card["close_date"] else None
                    want = 0
                    if info and closed and closed < fmt.to_date(info["cutoff"]):
                        days = (fmt.to_date(C["data_source"]["as_of"]) - closed).days
                        base = raw["sold_price"] - (raw.get("seller_concessions") or 0)
                        want = round(base * info["rate"] * days / cma.QUARTER_DAYS / 100) * 100
                        want = -want if info["falling"] else want
                    self.assertEqual(sum(lines), want)

    def test_range_within_the_cap(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                self.assertFalse({"range_wide", "range_one_comp", "range_narrow"} & set(C["warning_keys"]))
                self.assertLessEqual(C["range"]["width"], C["range"]["cap"] + 1)

    def test_each_note_once_and_no_label_carries_one(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                self.assertEqual(len(C["note_keys"]), len(set(C["note_keys"])))
                said = C["assumptions"] + C["chat_notes"]
                self.assertEqual(len({squash(s).casefold() for s in said}), len(said))
                self.assertTrue(set(C["notes"]) <= set(said))
                N = notes.Notes()
                for i, text in enumerate(said):
                    N.add(f"n{i}", text)
                self.assertEqual(N.label_problems(compute.all_labels(C)), [])

    def test_compute_never_changes_the_input(self):
        for seed in range(SEED, SEED + min(N_CASES, 3)):
            d = os.path.join(TMP, f"in{seed}")
            os.makedirs(d, exist_ok=True)
            R = gen.generate(seed, d)
            before = copy.deepcopy(R)
            compute.run(R)
            self.assertEqual(R, before)

    def test_legend_and_figures_from_the_model(self):
        for seed, _, C in cases():
            agent = gen.agent(seed)
            with self.subTest(seed=seed):
                doc = render.build_html(C, agent)
                if C["scatter"]:
                    svg = doc.split('class="scatter"', 1)[1].split("</svg>", 1)[0]
                    drawn = {k for k, n in (("comp", "m-comp"), ("sold", "m-sold"), ("active", "m-active"),
                                            ("trend", 'class="trend"'), ("subject", 'class="subj"')) if n in svg}
                    self.assertEqual(set(re.findall(r'data-series="(\w+)"', doc)), drawn)
                body = re.sub(r"<style>.*?</style>|<svg.*?</svg>", " ", doc, flags=re.S)
                text = squash(re.sub(r"<[^>]+>", " ", body)).replace("&#x27;", "'").replace("&amp;", "&")
                allowed = {m for s in strings(C) for m in FIGURE.findall(s)} | \
                          {m for s in strings(agent) for m in FIGURE.findall(s)}
                self.assertEqual(set(FIGURE.findall(text)) - allowed, set())
                for n in C["notes"]:
                    self.assertEqual(text.count(squash(n).replace("&", "&")), 1, n)


@unittest.skipUnless(PRINTS, "needs Chromium and pdftotext")
class Printed(unittest.TestCase):
    def test_nothing_clipped_page_one_fits_no_near_empty_page(self):
        for seed, _, C in cases()[:PRINT_N]:
            agent = gen.agent(seed)
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    (path,) = render.build(C, "pdf", tmp, {"agent": agent})
                for bad in ("clipped", "overflows", "doesn't fit on one page"):
                    self.assertNotIn(bad, err.getvalue())
                pages = layout.page_fill(path, 0.45, 0.55)
                self.assertTrue(pages)
                middle = [i + 1 for i, (fill, _) in enumerate(pages) if 0 < i < len(pages) - 1 and fill < layout.HALF_EMPTY]
                self.assertEqual(middle, [], err.getvalue())
                text = squash(subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout)
                self.assertIn(C["offer_plan"]["opening_display"], text)


if __name__ == "__main__":
    unittest.main()
