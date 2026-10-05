"""Buyer offer strategy on generated inputs (dev/generators/buyer_offer_strategy.py): universal properties of the
document model and the printed pages, for any valid input. Never a sentence, never a past case.

  - money: every seller net sheet column's lines add up to its net, the net plus holding to the net after holding;
    every cash column's lines add up to cash to close, plus the gap to the worst case, and the reserve is the buyer's
    cash less the worst case;
  - limits: the recommended offer is inside every buyer limit (max price, payment, reserve floor, the program's
    concession cap) unless the model says it breaks one, and then it names one;
  - the worksheet is offer terms only: changing the buyer's max, cash, reserve and payment limit leaves it unchanged;
  - notes: each note once (by key and by text), never also in What to Confirm; no label carries a note;
  - the input is unchanged;
  - buyer_priority: every priority renders on every input with the same offer each run; win never recommends a lower
    outlook or score than balanced, protect_cash never more worst-case cash, and overrides turn the choice off;
  - a buyer CMA's own handoff (dev/generators/buyer_cma.py through buyer-cma's compute) is read as the offer's range;
  - printed: both PDFs, nothing clipped or over page 1, no near-empty page, every dollar figure and percent on the
    page comes from the model, and each note prints once.

FUZZ_N inputs (8 by default; FUZZ_N=200 before a release), seeds from FUZZ_SEED (0). The printed checks need Chromium
and pdftotext and are skipped without them; without FUZZ_N set they print every other input.
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
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import buyer_offer_strategy as gen  # noqa: E402

strategy, render, notes, fmt, layout, finance = load("buyer-offer-strategy", "strategy", "render", "_shared.notes",
                                                     "_shared.fmt", "_shared.layout", "_shared.finance")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
EVERY = "FUZZ_N" in os.environ
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


_cache = {}


def cases():
    """(seed, data, r, M) for every input, computed once per test run."""
    for seed in range(SEED, SEED + N_CASES):
        if seed not in _cache:
            data = gen.generate(seed)
            r = strategy.analyze(data, cma=strategy.load_cma(data))
            _cache[seed] = (data, r, strategy.result(r, package_ready=bool(seed % 2)))
        yield (seed, *_cache[seed])


def amounts(cells):
    return [c["amount"] for c in cells]


class Model(unittest.TestCase):
    def test_columns_add_up(self):
        for seed, _, r, M in cases():
            with self.subTest(seed=seed):
                ns = M["detail"]["net_sheet"]
                for i in range(len(ns["columns"])):
                    lines = [row["cells"][i]["amount"] for row in ns["rows"]]
                    net, hold, adj = (ns[k]["cells"][i]["amount"] for k in ("net", "holding", "net_adj"))
                    self.assertEqual(sum(lines), net)
                    self.assertEqual(net + hold, adj)
                    for row in ns["rows"]:  # each figure printed is its amount, formatted once
                        self.assertEqual(row["cells"][i]["text"], fmt.money(row["cells"][i]["amount"], style="accounting"))
                ct = M["detail"]["cash"]
                cash = r["B"]["buyer"]["cash_available"]
                for i in range(len(ct["columns"])):
                    lines = [row["cells"][i]["amount"] for row in ct["rows"]]
                    to_close, gap, worst, reserve = (ct[k]["cells"][i]["amount"] for k in ("to_close", "gap", "worst", "reserve"))
                    self.assertEqual(sum(lines), to_close)
                    self.assertEqual(to_close + gap, worst)
                    self.assertEqual(cash - worst, reserve)
                rec = M["summary"]["tiles"]
                self.assertEqual(rec[2]["value"], fmt.money(r["cash"]["recommended"]["worst"]))
                self.assertEqual(rec[1]["value"], fmt.money(r["O"]["recommended"]["ns"]["net_adj"]))

    def test_recommended_offer_is_inside_every_limit_or_says_which_it_breaks(self):
        for seed, _, r, M in cases():
            with self.subTest(seed=seed):
                B, t = r["B"], r["terms"]["recommended"]
                BU, c = B["buyer"], r["cash"]["recommended"]
                broken = []
                if t["price"] > BU["max_price"]:
                    broken.append("max_price")
                if c["reserve"] < BU["reserve_floor"]:
                    broken.append("reserve")
                if BU.get("max_payment") and r["payment"]["recommended"] > BU["max_payment"]:
                    broken.append("max_payment")
                if t.get("seller_concessions", 0) > strategy.concession_cap(B, t["price"]) + 1:
                    broken.append("program_cap")
                if c["wasted_conc"] or strategy.fha_over_limit(B, t["price"], strategy.profiles.loan_limits()):
                    broken.append("program")
                says = M["summary"]["framing"] in ("breaks", "override_breaks")
                self.assertEqual(bool(broken), says, broken)
                if says:
                    self.assertTrue(M["summary"]["breaks_limits"])
                    self.assertEqual(M["summary"]["options"][0]["status"], "risk")
                for k, t2 in r["terms"].items():  # never an alternative past the max price or the payment limit
                    if k != "recommended" and not r["overrides"]:
                        self.assertLessEqual(t2["price"], max(BU["max_price"], t["price"]), k)

    def test_every_priority_picks_by_its_rule(self):
        """Every buyer_priority on every input, rendered: the same inputs give the same offer; win never recommends
        less outlook or score than balanced, protect_cash never more worst-case cash; overrides turn the choice off."""
        for seed, data, _, _ in cases():
            got = {}
            for p in strategy.BUYER_PRIORITIES:
                d = dict(data, buyer_priority=p)
                r = strategy.analyze(d, cma=strategy.load_cma(d))
                self.assertTrue(strategy.result(r))
                again = strategy.analyze(d, cma=strategy.load_cma(d))
                self.assertEqual(r["terms"]["recommended"], again["terms"]["recommended"])
                got[p] = r
            lvl = got["balanced"]["B"]["competition"]["level"]
            with self.subTest(seed=seed):
                rank = {p: strategy.BAND_RANK[r["bands"]["recommended"][lvl][0]] for p, r in got.items()}
                score = {p: r["O"]["recommended"]["score"]["total"] for p, r in got.items()}
                worst = {p: r["cash"]["recommended"]["worst"] for p, r in got.items()}
                if data.get("overrides"):
                    self.assertTrue(all(r["promoted"] is None for r in got.values()))
                    continue
                self.assertGreaterEqual((rank["win"], score["win"]), (rank["balanced"], score["balanced"]))
                self.assertLessEqual(worst["protect_cash"], worst["balanced"])
                self.assertNotEqual(got["protect_cash"]["promoted"], "stronger")
                pc = got["protect_cash"]
                if pc["promoted"] == "lower_cost" and rank["protect_cash"] < strategy.BAND_RANK["comp"]:
                    # never dropped to At Risk or Unlikely by choice: the fuller terms read the same (or were dropped
                    # for gaining nothing)
                    if "stronger" in pc["bands"]:
                        self.assertEqual(strategy.BAND_RANK[pc["bands"]["stronger"][lvl][0]], rank["protect_cash"])

    def test_worksheet_is_offer_terms_only(self):
        for seed, _, r, M in cases():
            with self.subTest(seed=seed):
                r2 = copy.copy(r)
                r2["B"] = copy.deepcopy(r["B"])
                BU = r2["B"]["buyer"]
                for k in ("cash_available", "reserve_floor", "max_price", "max_payment"):
                    BU[k] = (BU.get(k) or 1000) * 3 + 7
                self.assertEqual(strategy.worksheet(r2), M["worksheet"])

    def test_each_note_once_and_no_label_carries_one(self):
        for seed, _, r, M in cases():
            with self.subTest(seed=seed):
                self.assertEqual(len(M["note_keys"]), len(set(M["note_keys"])))
                said = M["notes"] + [a["what"] for a in M["assumptions"]]
                self.assertEqual(len({squash(s).casefold().rstrip(".") for s in said}), len(said))
                N = notes.Notes()
                for i, text in enumerate(said):
                    N.add(f"n{i}", text)
                self.assertEqual(N.label_problems(strategy.labels_of(M)), [])

    def test_no_placeholder_left_empty(self):
        """No sentence it writes (model, page, Check lines) shows a placeholder left empty (placeholders.py)."""
        for seed, _, r, M in cases():
            with self.subTest(seed=seed):
                agent = gen.agent(seed)
                texts = list(placeholders.strings(M)) + placeholders.page_text(render.options_html(M, agent)) + \
                    placeholders.page_text(render.worksheet_html(M, agent))
                self.assertEqual(placeholders.problems(texts), [])

    def test_compute_never_changes_the_input(self):
        for seed in range(SEED, SEED + N_CASES):
            data = gen.generate(seed)
            before = copy.deepcopy(data)
            strategy.result(strategy.analyze(data, cma=strategy.load_cma(data)))
            self.assertEqual(data, before, seed)

    def test_reads_the_buyer_cmas_own_handoff(self):
        """The handoff buyer-cma writes is the offer's value range, plan and market (two generated CMAs)."""
        from generators import buyer_cma as cma_gen
        (cma_compute,) = load("buyer-cma", "compute")
        for seed in range(SEED, SEED + 2):
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                R = cma_gen.generate(seed, tmp)
                market, homes = cma_compute.load_inputs(R)
                h = cma_compute.compute(R, market, homes)["handoff"]
                data = gen.with_cma(gen.generate(seed), h)
                r = strategy.analyze(data, cma=strategy.load_cma(data))
                V = r["B"]["value"]
                self.assertEqual((V["cma_low"], V["cma_high"]), (h["value"]["low"], h["value"]["high"]))
                self.assertFalse(V.get("assumed"))
                M = strategy.result(r)
                self.assertEqual(M["value_range"], fmt.range(h["value"]["low"], h["value"]["high"]))
                if (h.get("offer_plan") or {}).get("walk_away"):
                    self.assertEqual(r["B"]["cma_offer_plan"]["walk_away"], h["offer_plan"]["walk_away"])


@unittest.skipUnless(PRINTS, "needs Chromium and pdftotext")
@mock.patch.dict(os.environ, {"LAYOUT_PROBE": "1"})  # the layout probe: printed tables read back for the split rule
class Printed(unittest.TestCase):
    def test_pages_fit_and_figures_come_from_the_model(self):
        for seed, _, r, M in cases():
            if not EVERY and seed % 2:
                continue
            agent = gen.agent(seed)
            allowed = {m for s in strings(M) for m in FIGURE.findall(s)} | {m for s in strings(agent) for m in FIGURE.findall(s)}
            for kind, write in (("options", render.write_options), ("worksheet", render.write_worksheet)):
                with self.subTest(seed=seed, doc=kind), tempfile.TemporaryDirectory() as tmp:
                    err = io.StringIO()
                    with contextlib.redirect_stderr(err):
                        path = write(M, agent, False, tmp)
                    self.assertNotIn("clipped", err.getvalue())
                    self.assertNotIn("split table", err.getvalue())
                    self.assertNotIn("overflows", err.getvalue())
                    pages = layout.page_fill(path, 0.3, 0.4)
                    for i, (fill, _) in enumerate(pages[1:], start=2):
                        if i < len(pages):
                            self.assertGreaterEqual(fill, layout.HALF_EMPTY, f"page {i} near-empty")
                        else:
                            self.assertGreaterEqual(fill, layout.LONE_TAIL, "near-empty last page")
                    flat = squash(subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout)
                    self.assertEqual({m for m in FIGURE.findall(flat)} - allowed, set())
                    if kind == "options":
                        for note in M["notes"]:
                            self.assertEqual(flat.count(squash(note)), 1, note)


if __name__ == "__main__":
    unittest.main()
