"""Buyer CMA on generated inputs (dev/generators/buyer_cma.py): universal properties of the document model and the
printed report, for any valid input. Never a sentence, never a past case.

  - money: every payment column's lines add up to its total and its cash to close, every credit column's cash lines
    to its cash to close, every comp card's lines (sale price, seller-paid costs, adjustments) to its adjusted value;
  - rules: time adjustments follow the method's rule (rate x quarters since the sale, to $100, none after the cutoff);
    a range set by the shared rule passes the shared range checks and stays within the cap;
  - notes: each note is said once (by key and by text) and printed once; no label carries a note;
  - the scatter's legend names exactly the series drawn;
  - compute never changes its input; every dollar figure and percent on the page comes from the model;
  - printed: nothing clipped or over a page, page 1 on one page, no page between the first and last under half full,
    no table split against the rule (3 rows a side, a total with the 2 rows above it, a small table whole).

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
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

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

    def test_range_by_the_rule(self):
        """The range is the shared rule's for the adjusted comps (cma.choose_range), so it passes every range check;
        an agent's range_override is used as given and said beside the method's. Each condition line is the levels'
        difference."""
        for seed, R, C in cases():
            with self.subTest(seed=seed):
                market = compute.load_inputs(R)[0]
                values = [c["adjusted"] for c in C["comps"]["cards"]]
                rule = cma.choose_range(values, market)
                over = R.get("range_override")
                self.assertEqual((C["range"]["low"], C["range"]["high"]), (over["low"], over["high"]) if over else rule)
                self.assertEqual(C["range"]["override"], bool(over))
                if over:
                    self.assertIn(fmt.range(*rule), C["bottom_line"]["line"])
                else:
                    self.assertFalse({"range_wide", "range_one_comp", "range_narrow"} & set(C["warning_keys"]))
                    self.assertLessEqual(C["range"]["width"], C["range"]["cap"] + 1)
                levels = cma.condition_values(market, R["comps"].get("condition_values"))
                mine = levels.get(R["subject"]["condition"], 0)
                for card, given in zip(C["comps"]["cards"], R["comps"]["cards"]):
                    lines = [fmt.money(mine - levels[given["condition"]], style="signed")] \
                        if levels.get(given["condition"], mine) != mine else []
                    self.assertEqual([v for a, v in card["lines"] if a.startswith("Condition: ")], lines)

    def check_target(self, op):
        """The target leaves room above the opening: at least a quarter of the way to the walk-away (the target range
        too), so it's above the opening whenever the walk-away is $4,000 or more above it. An agent's own target range
        is theirs."""
        if op["override"] and {"target_low", "target_high"} & set(op["override"]):
            return
        floor = compute.target_floor(op["opening"], op["walk_away"])
        self.assertGreaterEqual(op["target_low"], min(floor, op["target"]))
        self.assertEqual(op["target"], min(max(op["target"], floor), op["walk_away"]))
        if op["walk_away"] - op["opening"] >= 4000:
            self.assertGreater(op["target"], op["opening"])

    def test_offer_plan_by_rule(self):
        """The posture's plan runs opening <= target_low <= target <= target_high <= walk-away, with the walk-away at or
        under asking and the range's high (only the agent's override leaves them); the same input gives the same plan;
        every credit offer is the opening plus its credit; a posture left out is the suggested one; the handoff carries
        the posture and the plan's numbers."""
        for seed, R, C in cases():
            op = C["offer_plan"]
            with self.subTest(seed=seed):
                steps = [op[k] for k in ("opening", "target_low", "target", "target_high", "walk_away")]
                self.assertEqual(steps, sorted(steps))
                self.check_target(op)
                if not op["override"]:
                    self.assertLessEqual(op["walk_away"], min(R["subject"]["list_price"], C["range"]["high"]))
                self.assertEqual(set(op["override"]), set((R["offer_plan"].get("plan_override") or {})) - {"reason"})
                if not R["offer_plan"].get("posture"):
                    self.assertEqual(op["posture"], op["posture_suggested"])
                again = compute.run(R)["offer_plan"]
                self.assertEqual([again[k] for k in compute.PLAN_KEYS + ("target", "posture")],
                                 [op[k] for k in compute.PLAN_KEYS + ("target", "posture")])
                for col in (C["credit"] or {}).get("columns", []):
                    self.assertEqual(col["price"] - col["credit"], op["opening"])
                self.assertEqual(C["handoff"]["posture"], op["posture"])
                self.assertEqual(C["handoff"]["offer_plan"], {k: op[k] for k in compute.PLAN_KEYS})

    def test_every_posture_renders(self):
        """Each of the four postures computes and renders for every input, its ladder in order, with each step's reason
        from labels.json."""
        for seed, R, _ in cases():
            for posture in cma.POSTURES:
                with self.subTest(seed=seed, posture=posture):
                    R2 = copy.deepcopy(R)
                    R2["offer_plan"].update(posture=posture, posture_reason="The buyer's own situation sets the plan.")
                    C = compute.run(R2)
                    op = C["offer_plan"]
                    self.assertEqual(op["posture"], posture)
                    steps = [op[k] for k in ("opening", "target_low", "target", "target_high", "walk_away")]
                    self.assertEqual(steps, sorted(steps))
                    self.check_target(op)
                    self.assertTrue(all(row[2] for row in op["ladder"]))
                    self.assertIn(op["opening_display"], render.build_html(C, {}))

    def test_gut_check_agrees_with_the_report(self):
        """The gut check's rough plan is the full report's plan with the suggested posture, on the same comps."""
        for seed, R, _ in cases():
            with self.subTest(seed=seed):
                G = {k: copy.deepcopy(R[k]) for k in ("subject", "split_date", "as_of", "export", "mls", "history",
                                                      "range_override") if k in R}
                G["comps"] = {k: copy.deepcopy(v) for k, v in R["comps"].items()
                              if k in ("cards", "time_adjustment", "condition_values")}
                rough = compute.run(G)["rough"]
                R2 = copy.deepcopy(R)
                for k in ("posture", "posture_reason", "plan_override"):
                    R2["offer_plan"].pop(k, None)
                op = compute.run(R2)["offer_plan"]
                self.assertEqual([rough[k] for k in ("posture", "opening", "target", "walk_away")],
                                 [op[k] for k in ("posture", "opening", "target", "walk_away")])

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

    def test_no_placeholder_left_empty(self):
        """No sentence it writes (model, page, Check lines) shows a placeholder left empty (placeholders.py)."""
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                texts = list(placeholders.strings(C)) + placeholders.page_text(render.build_html(C, gen.agent(seed)))
                self.assertEqual(placeholders.problems(texts), [])

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
@mock.patch.dict(os.environ, {"LAYOUT_PROBE": "1"})  # the layout probe: printed tables read back for the split rule
class Printed(unittest.TestCase):
    def test_nothing_clipped_page_one_fits_no_near_empty_page(self):
        for seed, _, C in cases()[:PRINT_N]:
            agent = gen.agent(seed)
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                err = io.StringIO()
                with contextlib.redirect_stderr(err):
                    (path,) = render.build(C, "pdf", tmp, {"agent": agent})
                for bad in ("clipped", "overflows", "doesn't fit on one page", "split table"):
                    self.assertNotIn(bad, err.getvalue())
                self.assertEqual(placeholders.problems(err.getvalue().splitlines()), [])
                pages = layout.page_fill(path, 0.45, 0.55)
                self.assertTrue(pages)
                # the page before the scatter may end early: the chart keeps its full size and moves whole (owner rule)
                chart = (C.get("scatter") or {}).get("heading")
                middle = [i + 1 for i, (fill, _) in enumerate(pages) if 0 < i < len(pages) - 1 and fill < layout.HALF_EMPTY
                          and not (chart and pages[i + 1][1] == chart)]
                self.assertEqual(middle, [], err.getvalue())
                text = squash(subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout)
                self.assertIn(C["offer_plan"]["opening_display"], text)


if __name__ == "__main__":
    unittest.main()
