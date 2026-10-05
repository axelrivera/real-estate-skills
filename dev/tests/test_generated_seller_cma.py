"""Seller CMA on generated inputs (dev/generators/seller_cma.py): universal properties of the document model, the
printed report and the deck, for any valid input. Never a sentence, never a past case.

  - money: every net sheet column's lines add up to its total, and the holding line to the net after it; every buyer
    payment's lines to its total; every comp card's lines to its adjusted value;
  - one closing per option: the net sheet's Expected Closing is the option's, its holding costs run from the report
    date to it, and the tax lines exist only where a closing does;
  - notes: each said once (by key and by text) and printed once; no label carries a note;
  - the scatter's legend names exactly the series drawn, in the report and on the deck (only series with points);
  - compute never changes its input; every dollar figure and percent on the page and on the slides comes from the model;
    the deck's net sheet, comps table and nets are the report's;
  - printed: nothing clipped or over a page, page 1 on one page, no page between the first and last under half full,
    no table split against the rule (3 rows a side, a total with the 2 rows above it, a small table whole);
    the deck builds, and no slide text reaches the footer.

FUZZ_N inputs (8 by default; FUZZ_N=200 before a release), seeds from FUZZ_SEED (0). The printed checks need Chromium
and pdftotext and run on the first PRINT_N of them (all by default); the deck needs Node (DECK_N of them, 3 by default).
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
from datetime import date

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402
import placeholders  # noqa: E402

sys.path.insert(0, os.path.join(ROOT, "dev"))
from generators import seller_cma as gen  # noqa: E402

compute, render, deck, notes, fmt, layout = load("seller-cma", "compute", "render", "deck", "_shared.notes",
                                                 "_shared.fmt", "_shared.layout")
N_CASES = int(os.environ.get("FUZZ_N", "8"))
PRINT_N = int(os.environ.get("PRINT_N", str(N_CASES)))
DECK_N = int(os.environ.get("DECK_N", "3"))
SEED = int(os.environ.get("FUZZ_SEED", "0"))
FIGURE = re.compile(r"[−-]?\$[\d,]+(?:\.\d+)?[KM]?|\d+(?:\.\d+)?%")


def have_chromium():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            return os.path.exists(p.chromium.executable_path)
    except Exception:  # noqa: BLE001 - no Playwright, or no browser installed
        return False


def node_ready():
    local = os.path.join(ROOT, "dev", "node_modules")
    if os.path.isdir(local) and local not in os.environ.get("NODE_PATH", ""):
        os.environ["NODE_PATH"] = os.pathsep.join(p for p in (os.environ.get("NODE_PATH"), local) if p)
    node = shutil.which("node")
    return bool(node) and subprocess.run([node, "-e", "require('pptxgenjs');require('sharp');require('react-icons/fa')"],
                                         capture_output=True, env=deck.node_env(), timeout=60).returncode == 0


PRINTS = bool(shutil.which("pdftotext")) and have_chromium()
TMP = tempfile.mkdtemp(prefix="gen-seller-cma-")
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


def allowed(C, agent):
    return {m for s in strings(C) for m in FIGURE.findall(s)} | {m for s in strings(agent) for m in FIGURE.findall(s)}


def tearDownModule():
    shutil.rmtree(TMP, ignore_errors=True)


class Model(unittest.TestCase):
    def test_columns_add_up(self):
        for seed, _, C in cases():
            with self.subTest(seed=seed):
                rows = C["net"]["rows"]
                for i, total in enumerate(C["net"]["totals"]):
                    lines = [r for r in rows if r["kind"] == "line" and r["key"] != "holding"]
                    self.assertEqual(sum(r["amounts"][i] for r in lines), total)
                    if C["net"]["after_holding"]:
                        self.assertEqual(total + C["net"]["holding"][i], C["net"]["after_holding"][i])
                for r in rows:
                    if r["kind"] != "info":
                        for a, d in zip(r["amounts"], r["display"]):
                            self.assertIn(d, (fmt.money(a), fmt.EMPTY))
                            if d == fmt.EMPTY:
                                self.assertEqual(a, 0)
                self.assertEqual([x["net_after_holding"] for x in C["strategies"]], C["net"]["after_holding"] or C["net"]["totals"])
                for r in C["payments"]["rows"]:
                    self.assertEqual(sum(a for _, _, a in r["lines"]), r["payment"])
                for card in C["comps"]["cards"]:
                    self.assertEqual(sum(dollars(v) for _, v in card["lines"]), card["adjusted"])

    def test_range_by_the_rule(self):
        """The range is the shared rule's for the adjusted comps (cma.choose_range); an agent's range_override is
        used as given and said beside the method's. Each condition line is the levels' difference."""
        for seed, R, C in cases():
            with self.subTest(seed=seed):
                market = compute.load_inputs(R)[0]
                values = [c["adjusted"] for c in C["comps"]["cards"]]
                rule = compute.cma.choose_range(values, market)
                over = R.get("range_override")
                rec = C["recommendation"]
                self.assertEqual((rec["low"], rec["high"]), (over["low"], over["high"]) if over else rule)
                self.assertEqual(rec["override"], bool(over))
                if over:
                    self.assertIn(fmt.range(*rule), rec["line"])
                else:
                    self.assertFalse({"range_wide", "range_one_comp", "range_narrow"} & set(C["warning_keys"]))
                levels = compute.cma.condition_values(market, R["comps"].get("condition_values"))
                mine = levels.get(R["subject"]["condition"], 0)
                for card, given in zip(C["comps"]["cards"], R["comps"]["cards"]):
                    lines = [fmt.money(mine - levels[given["condition"]], style="signed")] \
                        if levels.get(given["condition"], mine) != mine else []
                    self.assertEqual([v for a, v in card["lines"] if a.startswith("Condition: ")], lines)

    def check_options(self, R, C):
        """The options the stance sets, by rule: the recommended price inside the range on a search-bracket step (or at
        the cap a relist or reprice sets), Stay first on a reprice and the rest strictly descending, every two at least
        1% apart, nothing above a relist's failed price or a reprice's current price unless the agent allowed it."""
        rec, strats = C["recommendation"], C["strategies"]
        prices = [x["list_price"] for x in strats]
        stance = C["stance"]
        given = (R.get("pricing") or {}).get("stance")
        self.assertEqual(stance["value"], given or stance["suggested"])
        if R.get("reprice") or R.get("relist"):
            self.assertNotEqual(stance["suggested"], "premium")
        self.assertEqual(rec["list_price"], prices[C["recommended_index"]])
        self.assertTrue(strats[C["recommended_index"]]["recommended"])
        rp, rl = R.get("reprice"), R.get("relist")
        if not R.get("price_override"):
            price = rec["list_price"]
            self.assertTrue(rec["low"] <= price <= rec["high"], (price, rec["low"], rec["high"]))
            on_step = ((price + 100) % 5000 == 0 if price < 1_000_000 else (price + 1000) % 10000 == 0) \
                or price == 999000  # the $10,000 steps' first one, just under $1M
            caps = {rl["failed_price"]} if rl else {int(rp["current_price"] * 0.99) // 100 * 100} if rp else set()
            self.assertTrue(on_step or price in caps or C["recommendation"]["override"], price)
        else:
            self.assertEqual(rec["list_price"], R["price_override"]["list_price"])
            self.assertTrue(stance["agent_price"])
        if rp:
            self.assertEqual(strats[0]["role"], "stay")
            self.assertEqual(prices[0], rp["current_price"])
            if not rp.get("allow_increase"):
                self.assertTrue(all(p <= rp["current_price"] * 0.99 for p in prices[1:]), prices)
        else:
            self.assertNotIn("stay", [x["role"] for x in strats])
        rest = prices[1:] if rp else prices
        self.assertEqual(rest, sorted(rest, reverse=True))
        for i, a in enumerate(prices):
            for b in prices[i + 1:]:
                self.assertGreater(abs(a - b), 0.01 * min(a, b), prices)
        if rl and not rl.get("reason_above"):
            self.assertTrue(all(p <= rl["failed_price"] for p in prices), (prices, rl["failed_price"]))
        for x in strats:
            if x["role"] == "top":
                self.assertLessEqual(x["list_price"], rec["high"])
            if x["role"] == "competing":
                self.assertGreaterEqual(x["list_price"], rec["low"])

    def test_options_by_rule_and_reproducible(self):
        """Same inputs and stance, same prices and options (run twice from scratch)."""
        for seed, R, C in cases():
            with self.subTest(seed=seed):
                self.check_options(R, C)
                agent = bool(R["pricing"].get("options") or R.get("price_override"))  # warnings only on the agent's figures
                for key in ("list_outside_range", "expected_above_range", "expected_sale_order", "top_nets_more",
                            "stay_nets_more"):
                    if key in C["warning_keys"]:
                        self.assertTrue(agent, key)
                again = compute.run(copy.deepcopy(R))
                key = lambda M: [(x["role"], x["list_price"], x["expected_sale"], x["time"], x["seller_credit"])  # noqa: E731
                                 for x in M["strategies"]]
                self.assertEqual(key(again), key(C))

    def test_every_stance_renders(self):
        """Each of the three stances builds valid options for every input (a stance other than the suggestion with
        its reason)."""
        for seed, R, _ in cases():
            for stance in compute.cma.STANCES:
                with self.subTest(seed=seed, stance=stance):
                    R2 = copy.deepcopy(R)
                    R2["pricing"].update(stance=stance, stance_reason="Our read of this home against the closest sales.")
                    self.check_options(R2, compute.run(R2))

    def test_one_closing_per_option(self):
        for seed, R, C in cases():
            with self.subTest(seed=seed):
                as_of = date.fromisoformat(R["as_of"])
                rows = {r["key"]: r for r in C["net"]["rows"]}
                if "closing" in rows:
                    self.assertEqual(rows["closing"]["display"],
                                     [x["closing_display"] or fmt.EMPTY for x in C["strategies"]])
                for i, x in enumerate(C["strategies"]):
                    closing = date.fromisoformat(x["closing"]) if x["closing"] else None
                    if closing is None:
                        self.assertNotIn("holding", rows)
                        continue
                    self.assertEqual(x["hold_months"], round(max((closing - as_of).days, 0) / compute.MONTH_DAYS, 2))
                    if "holding" in rows:
                        want = C["net"]["monthly"] * x["hold_months"]
                        self.assertAlmostEqual(-rows["holding"]["amounts"][i], want, delta=0.01 * C["net"]["monthly"] + 1)
                    if "tax_prior_year" in rows and rows["tax_prior_year"]["amounts"][i]:
                        self.assertGreater(closing.year, as_of.year)
                self.assertEqual(len({x["closing"] for x in C["strategies"] if x["closing"]}) > 0,
                                 "closing" in rows)

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
                agent = gen.agent(seed)
                texts = list(placeholders.strings(C)) + placeholders.page_text(render.build_html(C, agent))
                if C["deck"]:  # the deck's own wording; its labels are templates the deck fills
                    D = deck.deck_data(C, agent, render.footer_label(C, agent, "", False))
                    texts += list(placeholders.strings({k: v for k, v in D.items() if k != "labels"}))
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
                self.assertEqual(set(FIGURE.findall(text)) - allowed(C, agent), set())
                for n in C["notes"]:
                    self.assertEqual(text.count(squash(n)), 1, n)

    def test_deck_figures_are_the_reports(self):
        for seed, _, C in cases():
            if not C["deck"]:
                continue
            agent = gen.agent(seed)
            with self.subTest(seed=seed):
                D = deck.deck_data(C, agent, "footer")
                self.assertEqual(D["net_rows"], [[r["label"]] + r["display"] for r in C["net"]["rows"]])
                self.assertEqual(D["comps_rows"], C["comps"]["table"] + [C["comps"]["subject_row"]])
                self.assertEqual([x["net"] for x in D["strategies"]], [x["net_after_holding"] for x in C["strategies"]])
                if D["scatter"]:
                    self.assertTrue(all(s["points"] for s in D["scatter"]["series"]))
                    self.assertEqual({s["key"] for s in D["scatter"]["series"]} - {"trend", "subject"},
                                     {k for k, hs in C["_points"][0].items() if hs})
                shown = {k: v for k, v in D.items() if k not in ("dot", "scatter", "colors")}
                if D["scatter"]:
                    shown["scatter"] = {k: v for k, v in D["scatter"].items() if k in ("band_label", "trend_note")}
                figures = {m for s in strings(shown) for m in FIGURE.findall(s)}
                self.assertEqual(figures - allowed(C, agent), set())


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
                middle = [i + 1 for i, (fill, _) in enumerate(pages) if 0 < i < len(pages) - 1 and fill < layout.HALF_EMPTY]
                self.assertEqual(middle, [], err.getvalue())
                text = squash(subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True).stdout)
                self.assertIn(C["recommendation"]["list_price_display"], text)

    @unittest.skipUnless(node_ready(), "needs Node with pptxgenjs")
    def test_deck_builds_and_nothing_reaches_the_footer(self):
        done = 0
        for seed, _, C in cases():
            if not C["deck"] or done >= DECK_N:
                continue
            done += 1
            with self.subTest(seed=seed), tempfile.TemporaryDirectory() as tmp:
                D = deck.deck_data(C, gen.agent(seed), render.footer_label(C, gen.agent(seed), "", False))
                checks = deck.build_pptx(D, os.path.join(tmp, "deck.pptx"))
                self.assertTrue(os.path.exists(os.path.join(tmp, "deck.pptx")))
                self.assertEqual([c for c in checks if "reaches the footer" in c or "above the footer" in c], [])


if __name__ == "__main__":
    unittest.main()
