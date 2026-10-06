"""Seller net sheet on generated inputs (dev/generators/seller_net_sheet.py): universal properties of the document
model and the printed page, for any valid input. Never a sentence, never a past case.

  - money: every column's lines add up to its subtotals and its net, and the tile shows that net;
  - notes: each note is said once (by key and by text), in the PDF notes block once, and the reply's assumption
    lines and the markdown sheet's notes never repeat each other; no label carries a note;
  - the chart's legend names exactly the series drawn;
  - the page: one page, nothing clipped or over it, every dollar figure and percent printed comes from the model.

FUZZ_N inputs (8 by default; FUZZ_N=200 before a release), seeds from FUZZ_SEED (0). The printed checks need Chromium
and pdftotext and are skipped without them.
"""
import contextlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import seller_net_sheet as gen  # noqa: E402

compute, render, notes, fmt = load("seller-net-sheet", "compute", "render", "_shared.notes", "_shared.fmt")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
SEED = int(os.environ.get("FUZZ_SEED", "0"))
FIGURE = re.compile(r"[−-]?\$[\d,]+(?:\.\d+)?|\d+(?:\.\d+)?%")


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


def cases():
    for seed in range(SEED, SEED + N_CASES):
        data = gen.generate(seed)
        yield seed, data, compute.run(data)


class Model(unittest.TestCase):
    def test_columns_add_up(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                rows = {r["key"]: r for r in C["rows"] if r["kind"] != "line"}
                for i, c in enumerate(C["columns"]):
                    lines = [r["amounts"][i] for r in C["rows"] if r["kind"] == "line" and r["key"] != "payoff"]
                    pays = [r["amounts"][i] for r in C["rows"] if r["kind"] == "line" and r["key"] == "payoff"]
                    self.assertEqual(rows["total_costs"]["amounts"][i], sum(lines))
                    self.assertEqual(c["price"] + sum(lines), c["net_before_payoff"])
                    self.assertEqual(c["net_before_payoff"] + sum(pays), c["net"])
                    self.assertEqual(rows["net"]["amounts"][i], c["net"])
                    self.assertEqual(c["total_costs"], -sum(lines))
                    self.assertEqual(c["tile_display"], fmt.money(abs(c["net"])))
                    self.assertTrue(all(isinstance(a, int) for r in C["rows"] for a in r.get("amounts", [])))
                    for r in C["rows"]:  # each figure printed is its amount, formatted once
                        if "amounts" in r:
                            self.assertIn(r["display"][i], (fmt.money(r["amounts"][i]), fmt.EMPTY))

    def test_each_note_once_and_no_label_carries_one(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                self.assertEqual(len(C["note_keys"]), len(set(C["note_keys"])))
                said = C["assumptions"] + C["chat_notes"]
                self.assertEqual(len({squash(s).casefold() for s in said}), len(said))  # reply and markdown: once
                self.assertTrue(set(C["notes"]) <= set(said))  # every PDF note reaches the chat once
                # every note prints on the page but a default commission rate (a default, never an assumption)
                self.assertEqual(len(C["note_keys"]) - len(C["notes"]), 1 if C["commission_assumed"] else 0)
                N = notes.Notes()
                for i, text in enumerate(said):
                    N.add(f"n{i}", text)
                labels = ([r["label"] for r in C["rows"]] + [c["label"] for c in C["columns"]] + C["facts"]
                          + [c["tile_label"] for c in C["columns"]] + [s["label"] for s in C["summary_tiles"]])
                self.assertEqual(N.label_problems(labels), [])

    def test_comparisons_are_the_nets_difference(self):
        """The reply's "what separates them" figures come from the model: each price after the first against the
        first, its difference the two nets' and the only figure in its line."""
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                cols = C["columns"]
                self.assertEqual(len(C["comparisons"]), max(len(cols) - 1, 0))
                for c, x in zip(cols[1:], C["comparisons"]):
                    self.assertEqual(x["difference"], c["net"] - cols[0]["net"])
                    self.assertEqual(x["difference_display"], fmt.money(abs(x["difference"])))
                    shown = FIGURE.findall(x["line"].replace(c["label"], "").replace(cols[0]["label"], ""))
                    self.assertEqual(shown, [x["difference_display"]] if x["difference"] else [])

    def test_no_placeholder_left_empty(self):
        """No sentence it writes (model, page, Check lines) shows a placeholder left empty (placeholders.py)."""
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                texts = list(placeholders.strings(C)) + placeholders.page_text(render.build_html(C, gen.agent(seed)))
                self.assertEqual(placeholders.problems(texts), [])

    def test_compute_never_changes_the_input(self):
        import copy
        for seed in range(SEED, SEED + N_CASES):
            data = gen.generate(seed)
            before = copy.deepcopy(data)
            compute.run(data)
            self.assertEqual(data, before)

    def test_legend_names_the_series_drawn(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                doc = render.build_html(C, gen.agent(seed))
                chart = doc.split('class="chart-box', 1)[1]
                drawn = set(re.findall(r'class="seg (\w+)"', chart))
                legend = set(re.findall(r'data-series="(\w+)"', chart))
                self.assertEqual(drawn, legend)


@unittest.skipUnless(PRINTS, "needs Chromium and pdftotext")
@mock.patch.dict(os.environ, {"LAYOUT_PROBE": "1"})  # the layout probe: printed tables read back for the split rule
class Printed(unittest.TestCase):
    def test_one_page_nothing_clipped_figures_from_the_model(self):
        for seed, data, C in cases():
            agent = gen.agent(seed)
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    (path,) = render.build(C, "pdf", tmp, {"agent": agent})
                self.assertNotIn("clipped", err.getvalue())
                self.assertNotIn("split table", err.getvalue())
                self.assertNotIn("overflows", err.getvalue())
                text = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout
                self.assertEqual(text.count("\f"), 1, "one page")
                flat = squash(text)
                allowed = {m for s in strings(C) for m in FIGURE.findall(s)} | \
                          {m for s in strings(agent) for m in FIGURE.findall(s)}
                self.assertEqual({m for m in FIGURE.findall(flat)} - allowed, set())
                for note in C["notes"]:
                    self.assertEqual(flat.count(squash(note)), 1, note)


if __name__ == "__main__":
    unittest.main()
