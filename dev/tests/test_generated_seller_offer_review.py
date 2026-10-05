"""Seller offer review on generated inputs (dev/generators/seller_offer_review.py), first renders and step-2
re-renders: universal properties of the document model and the printed pages, for any valid input. Never a sentence,
never a past case.

  - money: every net sheet column's lines add up to its net, the net plus holding to the net after holding, and the
    key numbers show those nets;
  - one target closing per report: every offer's Seller's Target closes on the report's one date;
  - scores read facts only: each certainty total is the scaled sum of its scored rows, every score is 1-5 with its
    reason, a criterion whose fact the offer leaves out (deposit, approval, closing) has no score, one whose fact is
    given has one, and the scorecard prints the rest Not scored over the scored weight;
  - notes: each note is said once (by key and by text), never also in What to Confirm; no label carries a note;
  - legends name exactly the series drawn (the contingency timeline, the comparison's chart);
  - the input is unchanged;
  - counter stance: the same inputs give the same counter; every stance renders on every input, terms_only keeps the
    offered price, firm never asks less or allows more concessions than meet_partway, no counter above the seller's
    number or the offer's own price;
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
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import seller_offer_review as gen  # noqa: E402

review, render, notes, fmt, layout, oe = load("seller-offer-review", "review", "render", "_shared.notes", "_shared.fmt",
                                              "_shared.layout", "_shared.offer_engine")
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

    def test_scores_read_facts_only(self):
        W = {k: w for k, _, w in oe.CRITERIA}
        reads = {"deposit": lambda x: x.get("deposit") is None, "approval": lambda x: x.get("approval") in (None, ""),
                 "timeline": lambda x: not (x.get("closing_date") or x.get("closing_days"))}
        for seed, step, data, R, docs in cases():
            given = {x.get("id", "A"): x for x in data["offers"]}
            for o in R["offers"]:
                sc = o["score"]
                with self.subTest(seed=seed, step=step, offer=o["id"]):
                    scored = [k for k in W if sc["scores"][k] is not None]
                    self.assertEqual(sc["weight"], sum(W[k] for k in scored))
                    self.assertEqual(sc["total"], fmt.half_up(100 * sum(W[k] * sc["scores"][k] / 5 for k in scored)
                                                              / sc["weight"]))
                    for k in W:
                        self.assertEqual(sc["scores"][k] is None, sc["why"][k] is None)
                        self.assertIn(sc["scores"][k], (None, 1, 2, 3, 4, 5))
                    for k, missing in reads.items():
                        self.assertEqual(sc["scores"][k] is None, missing(given[o["id"]]), k)
            for M in docs:
                card = M["doc"].get("scorecard")
                if not card:
                    continue
                o = next(x for x in R["offers"] if x["id"] == M["summary"]["offer"])
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]):
                    self.assertEqual(card["total"]["weight"], fmt.pct(o["score"]["weight"] / 100, 0))
                    for row in card["rows"]:
                        self.assertEqual(row["score"], o["score"]["scores"][row["key"]])
                        if row["score"] is None:
                            self.assertEqual(row["why"], review.L_["sc_not_scored"])

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

    def test_no_placeholder_left_empty(self):
        """No sentence it writes (model, page, Check lines) shows a placeholder left empty (placeholders.py)."""
        for seed, step, _, R, docs in cases():
            for M in docs:
                with self.subTest(seed=seed, step=step, report=M["doc"]["subtitle"]):
                    texts = list(placeholders.strings(M)) + placeholders.page_text(render.build_html(M, gen.agent(seed)))
                    self.assertEqual(placeholders.problems(texts), [])

    def test_counter_is_the_same_on_the_same_inputs(self):
        for seed, step, data, R, _ in cases():
            again = review.analyze(data, cma=review.load_cma(data))
            with self.subTest(seed=seed, step=step):
                self.assertEqual([(o["counter_stance"], o["counter_terms"]) for o in R["offers"]],
                                 [(o["counter_stance"], o["counter_terms"]) for o in again["offers"]])
                for o in R["offers"]:  # the agent's stance when given, else the suggestion
                    given = ((data["offers"][R["offers"].index(o)].get("counter") or {}).get("stance"))
                    self.assertEqual(o["counter_stance"]["stance"], given or o["counter_stance"]["suggested"])

    def test_every_stance_renders_and_orders_the_counter(self):
        """Every stance on every input: terms_only keeps the offered price; firm never asks a lower price or allows more
        concessions than meet_partway; no stance counters above the seller's number or the offer's own price."""
        for seed, step, data, _, _ in cases():
            by, L = {}, None
            for stance in oe.COUNTER_STANCES:
                d = copy.deepcopy(data)
                for o in d["offers"]:
                    o["counter"] = {"stance": stance, "stance_reason": "The seller chose this stance."}
                R = review.analyze(d, cma=review.load_cma(d))
                self.assertTrue(review.reports(R))
                by[stance], L = {o["id"]: o for o in R["offers"]}, R["listing"]
            for k, mp in by["meet_partway"].items():
                firm, terms = by["firm"][k]["counter_terms"], by["terms_only"][k]["counter_terms"]
                with self.subTest(seed=seed, step=step, offer=k):
                    self.assertEqual(terms["price"], mp["price"])
                    self.assertGreaterEqual(firm["price"], mp["counter_terms"]["price"])
                    self.assertLessEqual(firm["seller_concessions"], mp["counter_terms"]["seller_concessions"])
                    for x in (firm, mp["counter_terms"], terms):
                        self.assertLessEqual(x["price"], max(mp["price"], oe.price_ceiling(mp, L)))

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
@mock.patch.dict(os.environ, {"LAYOUT_PROBE": "1"})  # the layout probe: printed tables read back for the split rule
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
                    self.assertNotIn("split table", err.getvalue())
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
