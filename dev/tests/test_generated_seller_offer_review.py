"""Seller offer review on generated inputs (dev/generators/seller_offer_review.py), first renders and step-2
re-renders: universal properties of the document model and the printed pages, for any valid input. Never a sentence,
never a past case.

  - money: every net sheet column's lines add up to its net, the net plus holding to the net after holding, and the
    key numbers show those nets;
  - one target closing per report: every offer's Seller's Target closes on the report's one date;
  - notes: each note is said once (by key and by text), never also in What to Confirm; no label carries a note;
  - legends name exactly the series drawn (the contingency timeline, the comparison's chart);
  - the input is unchanged;
  - printed: nothing clipped or over page 1, no near-empty page, every dollar figure and percent on the page comes from
    the model, every Respond By time is the model's, and each note prints once.

FUZZ_N inputs (8 by default; FUZZ_N=200 before a release), seeds from FUZZ_SEED (0). Each input renders twice (the
listing as given and a step later). Without FUZZ_N set, the printed checks print the first and last report of each
input; with it, every report. They need Chromium and pdftotext and are skipped without them.
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
from generators import seller_offer_review as gen  # noqa: E402

review, render, notes, fmt, layout = load("seller-offer-review", "review", "render", "_shared.notes", "_shared.fmt",
                                          "_shared.layout")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
ALL_REPORTS = "FUZZ_N" in os.environ
SEED = int(os.environ.get("FUZZ_SEED", "0"))
FIGURE = re.compile(r"\$[\d,]+(?:\.\d+)?[KM]?|\d+(?:\.\d+)?%")


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


PRINTS = bool(shutil.which("pdftotext")) and have_chromium()


def squash(text):
    return " ".join(str(text).split())


def strings(v):
    if isinstance(v, str):
        yield v
    elif isinstance(v, dict):
        for x in v.values():
            yield from strings(x)
    elif isinstance(v, (list, tuple)):
        for x in v:
            yield from strings(x)


def inputs():
    for seed in range(SEED, SEED + N_CASES):
        data = gen.generate(seed)
        yield seed, "first", data
        yield seed, "step2", gen.step2(data, seed)


_cache = {}


def cases():
    """(seed, step, data, R, reports) for every input, computed once per test run."""
    for seed, step, data in inputs():
        key = (seed, step)
        if key not in _cache:
            R = review.analyze(data, cma=review.load_cma(data))
            _cache[key] = (R, review.reports(R))
        yield (seed, step, data, *_cache[key])


class Model(unittest.TestCase):
    def test_net_sheet_columns_add_up(self):
        for seed, step, _, R, docs in cases():
            for M in docs:
                ns = M["doc"].get("net_sheet")
                if not ns:
                    continue
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]):
                    for i, _ in enumerate(ns["columns"]):
                        lines = [r["cells"][i]["amount"] for r in ns["rows"]]
                        net, hold, adj = (ns[k]["cells"][i]["amount"] for k in ("net", "holding", "net_adj"))
                        self.assertTrue(all(isinstance(a, int) for a in lines + [net, hold, adj]))
                        self.assertEqual(sum(lines), net)
                        self.assertEqual(net + hold, adj)
                        for r in ns["rows"]:  # each figure printed is its amount, formatted once
                            self.assertEqual(r["cells"][i]["text"], fmt.money(r["cells"][i]["amount"], style="accounting"))
                    o = next(x for x in R["offers"] if x["id"] == M["summary"]["offer"])
                    self.assertEqual(ns["net_adj"]["cells"][0]["amount"], o["ns"]["net_adj"])
                    self.assertIn(fmt.money(o["ns"]["net_adj"]), [k["value"] for k in M["summary"]["kpis"]])

    def test_one_target_closing_per_report(self):
        for seed, step, _, R, docs in cases():
            with self.subTest(seed=seed, step=step):
                if R["ranked"]:
                    self.assertEqual({o["target"]["close"] for o in R["offers"]}, {R["target_close"]})
                    self.assertEqual(R["target"]["close"], R["target_close"])
                for M in docs:
                    ch = M["doc"].get("chart")
                    if ch:
                        self.assertIn(review.day(R["target_close"]), ch["target_label"])

    def test_each_note_once_and_no_label_carries_one(self):
        for seed, step, _, R, docs in cases():
            for M in docs:
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]):
                    self.assertEqual(len(M["note_keys"]), len(set(M["note_keys"])))
                    said = M["notes"] + [a["what"] for a in M["doc"]["confirm"]]
                    self.assertEqual(len({squash(s).casefold() for s in said}), len(said))
                    N = notes.Notes()
                    for i, text in enumerate(said):
                        N.add(f"n{i}", text)
                    self.assertEqual(N.label_problems(review.labels_of(M)), [])
                    self.assertEqual(len(M["doc"]["confirm"]), len(M["assumptions"]))

    def test_compute_never_changes_the_input(self):
        for seed, step, data in inputs():
            before = copy.deepcopy(data)
            review.reports(review.analyze(data, cma=review.load_cma(data)))
            self.assertEqual(data, before, (seed, step))

    def test_legends_name_the_series_drawn(self):
        for seed, step, _, R, docs in cases():
            for M in docs:
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]):
                    doc = render.build_html(M, gen.agent(seed))
                    if M["mode"] == "single":
                        part = doc.split('class="tbl gantt-tbl"', 1)[1].split('class="firm"', 1)[0]
                        drawn = set(re.findall(r'class="gantt [^"]*on-(\w+)"', part))
                        if M["doc"]["timeline"]["deadline_cell"] is not None:
                            drawn.add("deadline")
                        self.assertEqual(drawn, set(re.findall(r'data-series="(\w+)"', part)))
                    elif M["doc"]["chart"]:
                        part = doc.split('class="chartbox"', 1)[1]
                        self.assertEqual(set(re.findall(r'data-series="(\w+)"', part)), {"offered", "down"})
                        self.assertEqual(part.count("<circle"), 2 * len(M["doc"]["chart"]["points"]) + 2)


@unittest.skipUnless(PRINTS, "needs Chromium and pdftotext")
class Printed(unittest.TestCase):
    def test_pages_fit_and_figures_come_from_the_model(self):
        for seed, step, data, R, docs in cases():
            agent = gen.agent(seed)
            shown = docs if ALL_REPORTS else list({id(d): d for d in (docs[0], docs[-1])}.values())
            for M in shown:
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]), tempfile.TemporaryDirectory() as tmp:
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        path = render.write_pdf(M, agent, False, tmp)
                    self.assertNotIn("clipped", err.getvalue())
                    self.assertNotIn("overflows", err.getvalue())
                    pages = layout.page_fill(path, 0.3, 0.4)
                    for i, (fill, first) in enumerate(pages[1:], start=2):
                        if i < len(pages):
                            self.assertGreaterEqual(fill, layout.HALF_EMPTY, f"page {i} near-empty")
                        else:
                            self.assertGreaterEqual(fill, layout.LONE_TAIL, "near-empty last page")
                    text = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout
                    flat = squash(text)
                    allowed = {m for s in strings(M) for m in FIGURE.findall(s)} | \
                              {m for s in strings(agent) for m in FIGURE.findall(s)}
                    self.assertEqual({m for m in FIGURE.findall(flat)} - allowed, set())
                    v = M["summary"]
                    for when in [v["respond_by"]] + [a["when"] for a in v.get("respond_by_also") or ()]:
                        self.assertIn(squash(when), flat)
                    for note in M["notes"]:
                        self.assertEqual(flat.count(squash(note)), 1, note)


if __name__ == "__main__":
    unittest.main()
