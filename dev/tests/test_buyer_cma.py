"""Tests for skills/buyer-cma/scripts (compute.py, stats.py, render.py). Facts of the unmodified fixtures are pinned by
golden (dev/golden/buyer-cma/); these tests change an input or call a function on built input."""
import contextlib
import copy
import io
import json
import os
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "skills", "buyer-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, buyer_render, buyer_stats, handoff, profiles, cma = load(
    "buyer-cma", "compute", "render", "stats", "_shared.handoff", "_shared.profiles", "_shared.cma")

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")


def report():
    with open(FIXTURE) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    return R


def run(change=None, **kw):
    """The fixture, changed by `change(R)`, through compute: (R, C, homes)."""
    R = report()
    if change:
        change(R)
    market, homes = compute.load_inputs(R, **kw)
    return R, compute.compute(R, market, homes), homes


def warnings(change=None):
    return run(change)[1]["warning_keys"]


def html(R, C, homes=(), agent=None):
    return buyer_render.build_html(copy.deepcopy(R), C, list(homes), agent or {})[0]


def with_events(events, locality_mls="O6433709"):
    def change(R):
        R["history"]["events"] = copy.deepcopy(events)
        R["subject"]["locality"] = R["subject"]["locality"].rsplit("MLS ", 1)[0] + "MLS " + locality_mls
    return change


def fha_buyer(cash, credit_alt=False):
    """FHA 3.5% as the buyer's own program, paid at a $464,000 target, no lender closing figure; with `credit_alt`, a
    $470,000 price with a $10,000 credit in the table and the plan."""
    def change(R):
        R["costs"]["buyer_cash"] = cash
        R["costs"]["payment"]["price"] = 464000
        R["costs"]["payment"]["scenarios"] = [{"label": "FHA, 3.5% Down", "type": "fha", "down_pct": 0.035},
                                              {"label": "Conventional, 3% Down", "type": "conventional", "down_pct": 0.03}]
        cs = R["costs"]["credit_scenarios"]
        cs.update(loan_type="fha", down_pct=0.035, scenarios=[{"price": 464000, "credit": 0}, {"price": 469000, "credit": 5000}])
        cs.pop("closing_cost_pct")
        cs.pop("buydown")
        if credit_alt:
            cs["scenarios"].append({"price": 470000, "credit": 10000})
            R["offer_plan"]["credit_alt"] = {"price": 470000, "credit": 10000}
    return change


def six_comps(R):
    """A sixth comp that makes the median a midpoint (not a whole $100)."""
    extra = {"address": "100 Test Ln", "sold_price": 1, "seller_concessions": 0, "meta": "", "bullets": [],
             "adjustments": [{"label": "Test", "amount": 0}]}
    R["comps"]["cards"].append(extra)
    mid = sorted(c["sold_price"] - (c.get("seller_concessions") or 0) + sum(a["amount"] for a in c["adjustments"])
                 for c in R["comps"]["cards"][:-1])[2]
    extra["sold_price"] = mid + 123


EVAL_GRID = [  # a history grid as the MLS lists it: newest first, Feb 7 misplaced
    {"date": "2026-09-16", "mls": "O6433709", "change": "DECR", "price": 474900},
    {"date": "2026-08-31", "mls": "O6433709", "change": "DECR", "price": 478900},
    {"date": "2026-08-17", "mls": "O6433709", "change": "NEW", "price": 484900},
    {"date": "2026-06-09", "mls": "O6371102", "change": "CANC", "dom": 83},
    {"date": "2026-05-21", "mls": "O6371102", "change": "BOM", "price": 484900},  # back on, higher
    {"date": "2026-05-17", "mls": "O6371102", "change": "TOM"},
    {"date": "2026-04-11", "mls": "O6371102", "change": "PNC", "price": 474500},
    {"date": "2026-02-07", "mls": "O6371102", "change": "DECR", "price": 474500},
    {"date": "2026-03-05", "mls": "O6371102", "change": "BOM"},
    {"date": "2026-01-27", "mls": "O6371102", "change": "TOM"},
    {"date": "2026-01-22", "mls": "O6371102", "change": "DECR", "price": 479900},
    {"date": "2026-01-16", "mls": "O6371102", "change": "NEW", "price": 483900},
]

SOLD_GRID = [  # the current listing, then an earlier owner's listing that sold
    {"date": "2026-09-12", "mls": "X9061187", "change": "price", "price": 464900, "dom": 64},
    {"date": "2026-08-14", "mls": "X9061187", "change": "price", "price": 474900, "dom": 35},
    {"date": "2026-07-10", "mls": "X9061187", "change": "listed", "price": 489900, "dom": 0},
    {"date": "2015-05-22", "mls": "X3320415", "change": "sold", "price": 262000, "dom": 21},
    {"date": "2015-04-21", "mls": "X3320415", "change": "pending", "price": 269900, "dom": 21},
    {"date": "2015-03-31", "mls": "X3320415", "change": "listed", "price": 269900, "dom": 0},
]


def sold_history(R):
    R["as_of"] = "2026-09-26"
    R["subject"]["list_price"] = 464900
    with_events(SOLD_GRID, "X9061187")(R)
    R["history"].pop("rows", None)


def cli(R, *args, export_beside=False):
    """compute.py's command line on report.json in a temp folder: (exit code, stdout JSON, files written)."""
    with tempfile.TemporaryDirectory() as tmp:
        if export_beside:
            shutil.copy(R["export"], os.path.join(tmp, "export.csv"))
            R["export"] = "export.csv"
        path = os.path.join(tmp, "report.json")
        with open(path, "w") as f:
            json.dump(R, f)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = compute.main([path, *args])
        return code, json.loads(out.getvalue()), sorted(os.listdir(tmp)), os.path.abspath(tmp)


class Inputs(unittest.TestCase):
    def test_input_errors(self):
        """Formatted numbers, no comps, a scenario without down_pct, rates as the wrong unit, a bad tax index, a
        missing field, an opening above the walk-away and an unknown history change are plain errors."""
        changes = (lambda R: R["competition"]["rows"][0].__setitem__(2, "$474,500"),
                   lambda R: R["comps"].__setitem__("cards", []),
                   lambda R: R["costs"]["payment"]["scenarios"][0].pop("down_pct"),
                   lambda R: R["costs"]["payment"].__setitem__("rate", 0.0695),  # a fraction, not 6.95
                   lambda R: R["costs"].__setitem__("transfer_tax_rate", 0.7),  # 0.7 meant 0.7%
                   lambda R: R["costs"]["payment"].__setitem__("tax_jurisdiction_index", 5),
                   lambda R: R["bottom_line"].pop("low"),
                   lambda R: R["offer_plan"].__setitem__("opening", R["offer_plan"]["walk_away"] + 5000),
                   with_events([{"date": "2026-01-16", "change": "relisted?"}]))
        for i, change in enumerate(changes):
            with self.subTest(i), self.assertRaises(compute.ReportError):
                run(change)

    def test_mls_option(self):
        R = report()
        R["subject"]["county"] = "Brevard"  # not Stellar: no MLS assumed, so the export can't be read
        with self.assertRaises(compute.mls.ExportError):
            compute.load_inputs(R)
        market, homes = compute.load_inputs(R, mls_name="Stellar")
        self.assertEqual(market.mls, "Stellar")
        self.assertTrue(homes)

    def test_cli_finds_the_export_and_writes_the_handoff_beside_the_report(self):
        """The export resolves beside report.json; the handoff is a working file there (never the outputs folder),
        named for the side."""
        code, out, _, tmp = cli(report(), export_beside=True)
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertTrue(out["handoff_file"].endswith(".buyer.cma.json"))
        self.assertEqual(os.path.dirname(out["handoff_file"]), tmp)


class Warnings(unittest.TestCase):
    def test_credit_warnings(self):
        self.assertEqual(warnings(lambda R: R["costs"]["credit_scenarios"]["scenarios"].append(
            {"price": 480000, "credit": 25000})), ["credit_over_cap"])

        def plan(R):
            R["offer_plan"]["walk_away"] = 490000
            R["offer_plan"]["credit_alt"] = {"price": 470000, "credit": 7000}
        _, C, _ = run(plan)
        self.assertIn("walk_away_above_range", C["warning_keys"])
        self.assertIn("credit_alt_mismatch", C["warning_keys"])
        self.assertIsNone(C["credit_alt"])
        self.assertEqual(len(C["warnings"]), len(C["warning_keys"]))

    def test_thin_comps_and_an_outlier(self):
        self.assertIn("thin_comps", warnings(lambda R: R["comps"].__setitem__("cards", R["comps"]["cards"][:2])))
        R, C, _ = run(lambda R: R["comps"]["cards"][0]["adjustments"].append({"label": "Test", "amount": 80000}))
        hits = [w for w, k in zip(C["warnings"], C["warning_keys"]) if k == "outlier"]
        self.assertEqual(len(hits), 1)
        self.assertTrue(hits[0].startswith(R["comps"]["cards"][0]["address"]))  # names the comp

    def test_adjustment_rates_outside_their_area(self):
        _, C, _ = run(lambda R: R["subject"].__setitem__("county", "Hillsborough"))  # Stellar, not where the rates were set
        self.assertIn("adjustment_scope", C["warning_keys"])
        self.assertTrue(any("Hillsborough" in w for w in C["warnings"]))
        m = profiles.load_market(state="FL", county="Seminole")  # the built-in partial-update and roof-age rates
        self.assertEqual((m.get("cma.adjustments.kitchen_only_vs_dated"), m.get("cma.adjustments.baths_only_vs_dated")),
                         (15000, 10000))
        bands = m.get("cma.adjustments.roof_age")
        self.assertEqual([b["value"] for b in bands], [0, -5000, -10000, -15000])
        self.assertEqual(bands[2]["years"], [15, 19])
        self.assertIsNone(cma.adjustment_scope_warning(m, "Seminole", 450000))
        self.assertIsNotNone(cma.adjustment_scope_warning(m, "Miami-Dade", 450000))

    def test_range_width_and_one_comp_end(self):
        """A range end past the second-highest or second-lowest adjusted comp, or a range wider than about 6% of the
        median adjusted value, warns."""
        self.assertFalse({"range_wide", "range_one_comp"} & set(warnings()))
        keys = warnings(lambda R: R["bottom_line"].__setitem__("high", 495000))
        self.assertEqual(keys.count("range_one_comp"), 1)
        self.assertIn("range_wide", keys)

        def wide(R):
            R["bottom_line"]["low"] = 400000
            R["offer_plan"]["opening"] = 400000
        keys = warnings(wide)
        self.assertIn("range_wide", keys)
        self.assertEqual(keys.count("range_one_comp"), 1)  # the low end, below $435,000

    def test_as_is_preference_stays_with_the_agent(self):
        """The seller's As-Is preference (Realtor Information) stated in the report warns; a conditional sentence, or
        one the public remarks back (`as_is_public`), doesn't."""
        def stated(R):
            R["subject"]["summary"] += " The seller prefers an As-Is contract."
        self.assertIn("as_is_private", warnings(stated))
        self.assertNotIn("as_is_private", warnings(lambda R: R["watch"]["items"].append(
            "<strong>As-Is.</strong> If the offer is written on the As-Is contract, the seller isn't committing to repairs.")))

        def public(R):
            stated(R)
            R["subject"]["as_is_public"] = True
        self.assertNotIn("as_is_private", warnings(public))

    def test_fractional_days_in_the_market_table(self):
        """A median of an even count ("7.5 days") is rounded to a whole day, half up."""
        _, C, _ = run(lambda R: R["market"]["rows"][2].__setitem__(2, "7.5 days"))
        self.assertIn("8 days", C["warnings"][C["warning_keys"].index("market_days_rounding")])
        self.assertNotIn("market_days_rounding", warnings())


class Handoff(unittest.TestCase):
    def test_handoff_is_valid_and_carries_the_history(self):
        _, C, _ = run()
        h = C["handoff"]
        handoff.validate(h)
        self.assertEqual(len(C["comps_table"]), len(h["comps"]))  # the chat template's rows
        self.assertEqual((h["subject"]["dom"], h["subject"]["price_cuts"]),
                         (C["history"]["active_days"], C["history"]["price_cuts"]))
        bad = copy.deepcopy(h)
        bad["subject"]["price_cuts"] = "two"
        with self.assertRaises(handoff.HandoffError):
            handoff.validate(bad)


class CompsFirst(unittest.TestCase):
    """Before the range exists: the median from the comps alone, and a rough plan from it."""

    def test_median_from_comps_alone(self):
        full = report()
        _, C, _ = run()
        code, out, written, _ = cli({k: full[k] for k in ("subject", "comps", "export", "as_of", "split_date")})
        self.assertEqual(code, 0, out)
        self.assertEqual(out["stage"], "comps")
        self.assertEqual(out["median_adjusted"], C["median_adjusted"])
        self.assertEqual((out["adjusted_min"], out["adjusted_max"]), (C["adjusted_min"], C["adjusted_max"]))
        self.assertEqual(out["asking_vs_median"], full["subject"]["list_price"] - C["median_adjusted"])
        self.assertEqual(written, ["report.json"])  # no handoff without a range

    def test_rough_plan(self):
        def comps_only(**subject):
            full = report()
            R = {k: copy.deepcopy(full[k]) for k in ("subject", "comps", "history", "export", "as_of", "split_date")}
            R["subject"].update(subject)
            market, homes = compute.load_inputs(R)
            return compute.comps_first(R, market, homes)
        out = comps_only()
        rough, median = out["rough"], out["median_adjusted"]
        # the adjusted span rounded outward to $1,000; the walk-away at or below the median; the opening half of
        # Florida's typical range width below it
        self.assertEqual((rough["range"]["low"], rough["range"]["high"]),
                         (out["adjusted_min"] // 1000 * 1000, -(-out["adjusted_max"] // 1000) * 1000))
        self.assertEqual(rough["walk_away"], median // 1000 * 1000)
        self.assertEqual(rough["opening"], (median - 25000 / 2) // 1000 * 1000)
        self.assertTrue(rough["opening"] <= rough["target"] <= rough["walk_away"])
        self.assertEqual(out["history"]["price_cuts"], 4)  # the gut check counts the history too
        self.assertEqual(out["warning_keys"], [])
        rough = comps_only(list_price=440000)["rough"]  # never above asking
        self.assertEqual(rough["walk_away"], 440000)
        self.assertTrue(rough["capped_at_asking"])
        self.assertLessEqual(rough["opening"], rough["target"])


class Stats(unittest.TestCase):
    def test_facts_rank_the_comps_and_mls_number_is_checked(self):
        """A home with no export row: its facts rank the candidates and lat/lon set distances. A listing number that
        isn't the export's active row warns."""
        export = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "export-reso.csv")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            buyer_stats.main([export, "--address", "999 NOWHERE LN", "--state", "FL", "--county", "Seminole",
                              "--sqft", "1849", "--pool", "--subdivision", "FERNWOOD PARK UNIT 2",
                              "--lat", "28.67", "--lon", "-81.41"])
        d = json.loads(out.getvalue())
        self.assertEqual((d["sold_candidates"][0]["address"], d["sold_candidates"][0]["distance"]), ("602 QUAIL LN", 0.15))
        export = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "export-spring-oaks.csv")
        for number, keys in (("O6433709", ["export_mls_mismatch"]), ("O6448292", [])):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                buyer_stats.main([export, "--address", "517 HICKORYWOOD AVE", "--state", "FL", "--county", "Seminole",
                                  "--mls-number", number])
            self.assertEqual(json.loads(out.getvalue())["warning_keys"], keys)


class History(unittest.TestCase):
    """Price changes, active days and failed contracts counted by the script; out-of-order rows and MLS numbers that
    don't match are warned."""

    def test_counts(self):
        _, C, _ = run(with_events(EVAL_GRID))
        h = C["history"]
        self.assertEqual((h["price_cuts"], h["price_increases"]), (4, 1))
        self.assertEqual(h["price_cut_total"], 4000 + 5400 + 6000 + 4000)
        self.assertEqual(h["price_increase_total"], 10400)
        self.assertEqual(h["price_cut_pct"], round(19400 / 483900, 4))
        self.assertEqual((h["failed_contracts"], h["listings"]), (1, 2))
        self.assertEqual(h["active_days"], 83 + 36)  # the CANC row's DOM, then Aug 17 to as_of Sep 22
        self.assertEqual((C["placeholders"]["price_cuts"], C["placeholders"]["price_increases"]),
                         ("4 price cuts", "1 price increase"))

    def test_order_and_mls_warnings(self):
        _, C, _ = run(with_events(EVAL_GRID))
        self.assertEqual(C["warning_keys"].count("history_order"), 1)
        self.assertEqual(C["history"]["out_of_order"], [[7, 8]])  # either could be the typo: both named
        text = C["warnings"][C["warning_keys"].index("history_order")]
        self.assertIn("history.events[7]", text)
        self.assertIn("history.events[8]", text)
        self.assertIn("export_mls_mismatch", C["warning_keys"])  # the export's active row is O6448292
        self.assertNotIn("history_mls_mismatch", C["warning_keys"])
        fixed = sorted(EVAL_GRID, key=lambda e: e["date"], reverse=True)
        _, C, _ = run(with_events(fixed, "O6448292"))
        self.assertFalse({"history_order", "export_mls_mismatch"} & set(C["warning_keys"]))
        self.assertIn("history_mls_mismatch", C["warning_keys"])  # the history's newest row is O6433709
        self.assertEqual(C["history"]["price_cuts"], 4)
        fixed[4] = {**fixed[4], "date": "2026-01-20"}  # a row whose removal alone restores the order is named alone
        _, C, _ = run(with_events(fixed))
        self.assertEqual(C["history"]["out_of_order"], [[4]])

        def rows_only(R):
            R["history"].pop("events")
            R["history"]["rows"] = [["Jan 16, 2026", "First listed", "$483,900"]]
        _, C, _ = run(rows_only)
        self.assertIn("history_no_events", C["warning_keys"])
        self.assertIsNone(C["history"])

    def test_active_days(self):
        """Without a DOM, the calendar count (pending and off-market days don't count); a CDOM on the first listing
        counts as its DOM; a later listing's CDOM spans the earlier one, so it warns; a row that says it happened more
        than once warns unless days_on/days_off or the DOM covers it."""
        cal = 11 + 37 + 19 + 36  # Jan 16-27, Mar 5-Apr 11, May 21-Jun 9, Aug 17-Sep 22
        no_dom = copy.deepcopy(EVAL_GRID)
        no_dom[3].pop("dom")
        first_cdom = copy.deepcopy(no_dom)
        first_cdom[3]["cdom"] = 83
        later_cdom = copy.deepcopy(EVAL_GRID)
        later_cdom[0]["cdom"] = 119
        repeat = copy.deepcopy(no_dom)
        repeat[9]["note"] = "Taken off the market (off and on twice through Mar 5)"
        repeat_days = copy.deepcopy(repeat)
        repeat_days[9]["days_on"] = 10
        repeat_dom = copy.deepcopy(repeat)
        repeat_dom[3]["dom"] = 83  # the MLS's DOM already counts the pairs
        cases = [(no_dom, cal, set(), {"history_cdom"}),
                 (first_cdom, 83 + 36, set(), {"history_cdom"}),
                 (later_cdom, 83 + 36, {"history_cdom"}, set()),
                 (repeat, cal, {"history_repeat"}, set()),
                 (repeat_days, cal + 10, set(), {"history_repeat"}),
                 (repeat_dom, None, set(), {"history_repeat"})]
        for i, (events, days, has, lacks) in enumerate(cases):
            with self.subTest(i):
                _, C, _ = run(with_events(events))
                if days is not None:
                    self.assertEqual(C["history"]["active_days"], days)
                self.assertLessEqual(has, set(C["warning_keys"]))
                self.assertFalse(lacks & set(C["warning_keys"]))

    def test_asking_vs_the_last_contract(self):
        """Asking $474,900 is $400 above the $474,500 it was listed at when the April contract was signed."""
        def at(price):
            def change(R):
                R["subject"]["list_price"] = price
                with_events(EVAL_GRID)(R)
            return change
        _, C, _ = run(at(474900))
        h, ph = C["history"], C["placeholders"]
        self.assertEqual((h["last_contract_date"], h["last_contract_price"], h["vs_last_contract"]), ("2026-04-11", 474500, 400))
        self.assertEqual((ph["vs_last_contract"], ph["last_contract_price"]), ("$400 above", "$474,500"))
        self.assertEqual(run(at(470000))[1]["placeholders"]["vs_last_contract"], "$4,500 below")

        def no_contract(R):
            with_events([e for e in EVAL_GRID if e["change"] != "PNC"])(R)
            R["offer"]["bullets"].append("Asking is {vs_last_contract} the last contract.")
        _, C, _ = run(no_contract)
        self.assertNotIn("vs_last_contract", C["history"])
        self.assertIn("unfilled_placeholder", C["warning_keys"])

    def test_counts_start_after_the_last_sale(self):
        """An earlier owner's listing that sold stays in the table, with its year, but not in the counts."""
        _, C, _ = run(sold_history)
        h = C["history"]
        self.assertEqual(h["active_days"], 64 + 14)  # the current listing's DOM, then Sep 12 to as_of Sep 26
        self.assertEqual((h["price_cuts"], h["price_increases"], h["failed_contracts"], h["listings"]), (2, 0, 0, 1))
        self.assertEqual((h["first_listed"], h["first_list_price"]), ("2026-07-10", 489900))
        self.assertEqual(h["counted_since_sale"], "2015-05-22")
        self.assertNotIn("last_contract_price", h)  # the only contract was the earlier owner's
        self.assertEqual(len(h["timeline"]), 6)
        hist = {"timeline": [{"date": d, "kind": "listed", "price": 1, "delta": 0} for d in
                             ("2015-03-31", "2015-04-21", "2015-05-22", "2026-07-10", "2026-08-14")]}
        rows = [r[0] for r in buyer_render.history_rows({}, hist, lambda key, **kw: key, "2026-09-26")]
        self.assertEqual(rows, ["Mar 31, 2015", "Apr 21, 2015", "May 22, 2015", "Jul 10, 2026", "Aug 14, 2026"])


class Taxes(unittest.TestCase):
    def test_other_states(self):
        def texas(R):
            R["subject"].update(state="TX", county="Travis")
            R.pop("export")
            for j in R["costs"]["taxes"]["jurisdictions"]:
                j.pop("school_mills", None), j.pop("total_mills", None)
        _, C, _ = run(texas)
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax"], 474900 * 0.011 / 12)  # the national estimate
        self.assertIn("tax_estimated", C["warning_keys"])

        def millage(R):
            texas(R)
            R["costs"]["taxes"]["jurisdictions"] = [{"label": "in Austin", "short": "Austin", "school_mills": 9.5, "total_mills": 19.0}]
            R["costs"]["payment"]["tax_jurisdiction_index"] = 0
        _, C, _ = run(millage)
        self.assertAlmostEqual(C["taxes"][0]["annual"], 474900 * 19.0 / 1000)  # no Florida homestead in Texas
        self.assertIsNotNone(C["payments"])

    def test_district_basis(self):
        """An unconfirmed district uses the higher bill, flagged once; one confirmed district isn't an estimate."""
        _, C, _ = run(lambda R: R["costs"]["payment"].pop("tax_jurisdiction_index"))
        annual = [t["annual"] for t in C["taxes"]]
        self.assertEqual(C["payments"]["tax_index"], annual.index(max(annual)))
        tb = C["payments"]["tax_basis"]
        self.assertTrue(tb["unconfirmed"] and tb["higher"] and tb["label_estimate"])

        def one(R):
            R["costs"]["taxes"]["jurisdictions"] = R["costs"]["taxes"]["jurisdictions"][:1]
            R["costs"]["payment"]["tax_jurisdiction_index"] = 0
        self.assertFalse(run(one)[1]["payments"]["tax_basis"]["label_estimate"])

    def test_no_bill_and_no_homestead_render(self):
        R, C, homes = run(lambda R: R["costs"]["taxes"].pop("current_bill"))  # new construction
        self.assertIn("Not available", html(R, C, homes))
        R, C, _ = run(lambda R: R["costs"]["taxes"].__setitem__("homestead", False))
        doc = html(R, C)
        self.assertNotIn("With Homestead", doc)
        self.assertIn("No Homestead", doc)


class Payments(unittest.TestCase):
    def test_target_by_default(self):
        def change(R):
            R["costs"]["payment"].pop("price")
            R["costs"]["taxes"].pop("purchase_price")
        R, C, _ = run(change)
        op = R["offer_plan"]
        self.assertEqual(C["payments"]["price"], (op["target_low"] + op["target_high"]) / 2)
        self.assertEqual(C["payments"]["price_basis"], "target")
        self.assertEqual(R["costs"]["taxes"]["purchase_price"], C["payments"]["price"])  # page 1's tax and payment agree

    def test_cash_checks(self):
        """Over the buyer's cash: cash_short per credit column and own program; within 5%: cash_tight; a comparison
        scenario over the cash: scenario_over_cash (flagged, not warned as short)."""
        _, C, _ = run(lambda R: R["costs"].__setitem__("buyer_cash", 30000))
        short = [c for c in C["credit"]["columns"] if c["cash"] > 30000]
        self.assertTrue(short)
        self.assertTrue(all(c["cash_short"] == round(c["cash"] - 30000) for c in short))
        rows = C["payments"]["rows"]
        self.assertTrue(rows[2]["cash_short"])
        self.assertEqual(C["warning_keys"].count("cash_short"), len(short) + bool(rows[0]["cash_short"]))
        need = run()[1]["credit"]["columns"][0]["cash"]
        _, C, _ = run(lambda R: R["costs"].__setitem__("buyer_cash", round(need + 500)))
        self.assertEqual(C["credit"]["columns"][0]["cash_left"], round(round(need + 500) - need))
        self.assertIn("cash_tight", C["warning_keys"])
        self.assertEqual(C["warning_keys"].count("scenario_over_cash"), 1)  # Conventional, 20% Down
        self.assertFalse({"cash_short", "cash_tight", "scenario_over_cash"}
                         & set(warnings(lambda R: R["costs"].__setitem__("buyer_cash", 200000))))

    def test_fha_cash_to_close(self):
        """The payment table's cash to close (down payment plus closing costs, the credit table's basis) is checked
        against the buyer's cash, not just the down payment, for the buyer's program and the comparisons."""
        _, C, _ = run(fha_buyer(30000))
        first, col = C["payments"]["rows"][0], C["credit"]["columns"][0]
        self.assertEqual(first["cash_to_close"], first["cash_down"] + first["closing_costs"])
        self.assertAlmostEqual(first["cash_to_close"], col["cash"])  # same price, no credit: the same basis
        self.assertIsNone(first["down_short"])  # the down payment alone fits
        self.assertEqual(first["cash_short"], round(first["cash_to_close"] - 30000))
        need = first["cash_to_close"]
        _, C, _ = run(fha_buyer(round(need + 500)))
        self.assertEqual(C["payments"]["rows"][0]["cash_left"], round(round(need + 500) - need))
        self.assertIn("cash_tight", C["warning_keys"])

        def conv5(R):
            fha_buyer(30000)(R)
            R["costs"]["payment"]["scenarios"][1] = {"label": "Conventional, 5% Down", "type": "conventional", "down_pct": 0.05}
        _, C, _ = run(conv5)
        row = C["payments"]["rows"][1]
        self.assertIsNone(row["down_short"])  # $23,200 down fits $30,000
        self.assertTrue(row["cash_short"])  # but not once closing costs are added
        self.assertEqual(C["warning_keys"].count("scenario_over_cash"), 1)
        self.assertNotIn("scenario_over_cash", warnings(fha_buyer(34000)))  # Conventional 3% fits

    def test_cash_short_names_the_fitting_credit_option(self):
        _, C, _ = run(fha_buyer(30000, credit_alt=True))
        self.assertIn("cash_short", C["warning_keys"])
        self.assertEqual((C["cash_fit"]["price"], C["cash_fit"]["credit"]), (470000, 10000))
        self.assertLessEqual(C["cash_fit"]["cash"], 30000)
        _, C, _ = run(fha_buyer(5000, credit_alt=True))  # nothing fits
        self.assertIsNone(C["cash_fit"])
        self.assertIn("cash_short", C["warning_keys"])

    def test_assumed_financing_is_a_flag_not_a_label(self):
        _, C, _ = run(lambda R: R["costs"]["payment"]["scenarios"][0].__setitem__("assumed", True))
        self.assertEqual(C["payments"]["rows"][0]["label"], "Conventional, 5% Down")
        self.assertTrue(C["payments"]["rows"][0]["assumed"])
        self.assertNotIn("scenario_label", C["warning_keys"])
        self.assertIn("scenario_label", warnings(lambda R: R["costs"]["payment"]["scenarios"][0].__setitem__(
            "label", "Conventional, 5% Down (Assumed)")))

    def test_flood_line(self):
        """The payment has a flood line: a quote, or "Get a Quote" (never $0); zone AE is lender-required."""
        R, C, _ = run()
        pay = C["payments"]
        self.assertIsNone(pay["flood"]["annual"])
        self.assertTrue(all(r["flood"] is None for r in pay["rows"]))
        self.assertIn("Get a Quote", html(R, C))
        _, quoted, _ = run(lambda R: R["costs"]["payment"].__setitem__("flood_insurance_annual", 1800))
        for a, b in zip(pay["rows"], quoted["payments"]["rows"]):
            self.assertAlmostEqual(b["total"] - a["total"], 150)
        _, C, _ = run(lambda R: R["costs"]["payment"].__setitem__("flood_zone", "AE"))
        self.assertEqual(C["payments"]["flood"]["required"], "lender")

    def test_loan_taxes_without_a_lender_figure(self):
        """Florida's 2.5% plus 0.5% prepaids, plus note stamps and intangible tax on the loan."""
        _, C, _ = run(lambda R: R["costs"]["credit_scenarios"].pop("closing_cost_pct"))
        col = C["credit"]["columns"][0]
        self.assertEqual(col["loan_taxes"], round(col["loan"] * 0.0035) + round(col["loan"] * 0.002))
        self.assertEqual(col["closing_costs"], round(col["price"] * 0.03 + col["loan_taxes"]))


class Credit(unittest.TestCase):
    def test_seller_cost_and_trade_off_per_credit(self):
        R, C, _ = run(lambda R: R["costs"]["credit_scenarios"].__setitem__("seller_pays_buyer_broker_pct", 0.025))
        self.assertEqual(C["credit"]["seller_cost_per_10k"], 320)  # 0.7% doc stamps + 2.5% buyer-broker pay
        doc = html(R, C)
        self.assertIn("$320", doc)
        self.assertNotIn("Same Seller Net", doc)  # price minus credit isn't the same net to the seller
        _, C, _ = run()
        cols = C["credit"]["columns"]
        per = 5000 / (cols[1]["credit"] - cols[0]["credit"])
        self.assertEqual(C["placeholders"]["credit_monthly_per_5k"], f"${round((cols[1]['payment'] - cols[0]['payment']) * per):,}")
        self.assertEqual(C["placeholders"]["credit_cash_per_5k"], f"${round((cols[0]['cash'] - cols[1]['cash']) * per, -2):,.0f}")

    def test_median_quoted_rounded(self):
        """An even number of comps has a midpoint median, quoted to the nearest $100; the credit table's room below
        it uses the median as quoted. Five comps: one comp's own value, to the dollar."""
        R, C, _ = run(six_comps)
        self.assertNotEqual(C["median_adjusted"] % 100, 0)
        self.assertEqual(C["median_adjusted_display"], compute.money(C["median_adjusted"], 100))
        self.assertEqual(C["placeholders"]["median_adjusted"], C["median_adjusted_display"])
        shown = compute.median_rounded(C["median_adjusted"], len(R["comps"]["cards"]))
        for col in C["credit"]["columns"]:
            self.assertEqual(col["appraisal_room"], shown - col["price"])
        doc = html(R, C)
        self.assertIn(C["median_adjusted_display"], doc)
        self.assertNotIn(compute.money(C["median_adjusted"]), doc)
        _, C, _ = run()
        self.assertEqual(C["median_adjusted_display"], compute.money(C["median_adjusted"]))

    def test_competing_listing_position_is_computed(self):
        """A competing listing's adjusted price and its place in the range come from the script; a note that places it
        by hand warns."""
        def pool(R):
            R["bottom_line"].update(low=435000, high=450000, midpoint=442500)
            R["offer_plan"].update(opening=435000, target_low=440000, target_high=444000, walk_away=446000)
            R["offer_plan"].pop("credit_alt", None)
            R["competition"]["rows"][0][2] = 424500
            R["competition"]["rows"][0][6] = "No pool. Add about $25,000 for a pool: {adjusted_estimate}, {range_position}."
            R["competition"]["adjustments"] = {"644 PEACHWOOD DR": [{"label": "Pool", "amount": 25000}]}
        R, C, _ = run(pool)
        est = C["competition_estimates"][0]
        self.assertEqual((est["adjusted"], est["range_position"]), (449500, "near the top of this home's range"))
        self.assertIn("$449,500", R["competition"]["rows"][0][6])
        self.assertFalse({"unfilled_placeholder", "range_position_typed"} & set(C["warning_keys"]))
        self.assertEqual(compute.range_position(430000, 435000, 450000), "below this home's range")
        self.assertEqual(compute.range_position(442000, 435000, 450000), "in the middle of this home's range")
        self.assertIn("range_position_typed", warnings(lambda R: R["competition"]["rows"][0].__setitem__(
            6, "Add about $25,000 for a pool and it lands near the bottom of this home's range.")))


class Placeholders(unittest.TestCase):
    def test_filled_everywhere(self):
        def change(R):
            R["comps"]["summary_paragraph"] = "The median is {median_adjusted}, after {price_cuts}."
            R["market"]["bullets"][0] = "<strong>Supply.</strong> About {months_supply} at the recent pace."
            R["as_of"] = "2026-09-26"
        R, C, homes = run(change)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc = html(R, C, homes)
        self.assertIn(C["median_adjusted_display"], doc)
        self.assertNotIn("{median_adjusted}", doc)
        self.assertEqual(C["summary_page"]["key_stats"][0][0], C["median_adjusted_display"])  # the chat template's copy
        self.assertRegex(C["placeholders"]["months_supply"], r"^\d+\.\d months$")
        self.assertEqual(C["data_source"]["as_of_display"], "September 26, 2026")
        self.assertEqual(compute.end_sentence("before you sign"), "before you sign.")
        self.assertEqual(compute.end_sentence("before you sign."), "before you sign.")
        self.assertEqual(compute.end_sentence("(see the roof)."), "(see the roof).")

    def test_unknown_placeholder_warns(self):
        _, C, _ = run(lambda R: R["watch"]["items"].__setitem__(0, R["watch"]["items"][0] + " {median_value}"))
        self.assertEqual(C["warning_keys"], ["unfilled_placeholder"])
        self.assertIn("$.watch.items[0]", C["warnings"][0])


class ScatterLabels(unittest.TestCase):
    """A label steps to another side rather than print over a marker or another label; boxed in, it sits farther off
    with a leader line; with no clear spot, the subject's label is dropped (the legend names it)."""

    def test_label_sides(self):
        placer = cma._LabelPlacer([(100, 100, 10), (60, 104, 6.5)], (0, 0, 400, 400))  # a comp just left of the subject
        svg = placer.place(100, 100, "left", "517 Hickorywood", "lbl-subj", 14, 13, bold=True)
        self.assertEqual((placer.moved, placer.overlapping), ([("517 Hickorywood", "left", "right")], []))
        self.assertIn('text-anchor="start"', svg)
        placer = cma._LabelPlacer([(100, 100, 10)], (0, 0, 400, 400))
        placer.place(100, 100, "below", "517 Hickorywood", "lbl-subj", 14, 13)
        self.assertEqual(placer.moved, [])  # a clear side is kept
        placer = cma._LabelPlacer([], (0, 0, 400, 400))
        placer.place(100, 100, "right", "1512 Buttonbush Dr", "lbl", 10, 12)
        placer.place(100, 104, "right", "1471 Sedgefield", "lbl", 10, 12)  # another label counts
        self.assertEqual((len(placer.moved), placer.overlapping), (1, []))

    def test_leader_line_and_dropped_label(self):
        ring = [(70, 100, 6.5), (130, 100, 6.5), (140, 80, 6.5), (140, 120, 6.5)]  # beside, above and below are covered
        placer = cma._LabelPlacer([(100, 100, 10)] + ring, (0, 0, 400, 400))
        svg = placer.place(100, 100, "left", "517 Hickorywood", "lbl-subj", 14, 13, bold=True, droppable=True)
        self.assertEqual((len(placer.leaders), placer.overlapping, placer.dropped), (1, [], []))
        self.assertIn('class="leader"', svg)
        grid = [(x, y, 6.5) for x in range(0, 401, 12) for y in range(0, 401, 12)]
        placer = cma._LabelPlacer([(100, 100, 10)] + grid, (0, 0, 400, 400))
        self.assertEqual(placer.place(100, 100, "left", "517 Hickorywood", "lbl-subj", 14, 13, bold=True, droppable=True), "")
        self.assertEqual(placer.dropped, ["517 Hickorywood"])
        self.assertTrue(placer.place(200, 200, "right", "622 Spring Oaks", "lbl", 10, 12))  # not droppable: prints
        self.assertEqual(placer.overlapping, ["622 Spring Oaks"])

    def test_render_reports_labels_and_unplotted_callouts(self):
        R, C, homes = run()
        html(R, C, homes)
        self.assertEqual(C["scatter_labels"], {"moved": [], "overlapping": [], "leader": [], "dropped": []})
        self.assertEqual(C["callout_checks"], [])
        R["scatter"]["callouts"] = R["scatter"]["callouts"] + [{"address": "1 NOWHERE LN", "label": "Missing", "side": "left"}]
        html(R, C, homes)
        self.assertEqual(len(C["callout_checks"]), 1)  # named, not dropped silently
        self.assertIn("1 NOWHERE LN", C["callout_checks"][0])


class Addresses(unittest.TestCase):
    def test_uppercase_addresses_print_in_title_case(self):
        """An export's UPPERCASE address prints in title case on the chart, cards and tables; matching to the export
        ignores case."""
        self.assertEqual(cma.display_address("436 SUMMIT DR"), "436 Summit Dr")
        self.assertEqual(cma.display_address("120 NE 1ST ST, APT #4A, LONGWOOD, FL"), "120 NE 1st St, Apt #4A, Longwood, FL")
        self.assertEqual(cma.display_address("745 Little Wekiva Cir"), "745 Little Wekiva Cir")

        def upper(R):
            for c in R["comps"]["cards"]:
                c["address"] = c["address"].upper()
        R, C, homes = run(upper)
        self.assertTrue(all(r["address"] == cma.display_address(r["address"].upper()) for r in C["comps_table"]))
        doc = html(R, C, homes)
        for card in R["comps"]["cards"]:
            self.assertNotIn(card["address"], doc)
            self.assertIn(cma.display_address(card["address"]), doc)
        self.assertIn('class="m-comp', doc)  # still matched to the export's rows
        sc = {"subject_label": "517 Hickorywood", "callouts": [{"address": "1512 BUTTONBUSH DR", "label": "1512 Buttonbush"}]}
        out = buyer_render.chart_labels(sc, {"address": "517 Hickorywood Ave"})
        self.assertEqual((out["subject_label"], out["callouts"][0]["label"]), ("517 Hickorywood Ave", "1512 Buttonbush Dr"))


def browser_page(doc, width=730):
    """A Chromium page laid out at print width, as html_to_pdf and cma.paginate measure it."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": width, "height": 1000})
    pg.set_content(doc, wait_until="load")
    pg.emulate_media(media="print")
    return p, b, pg


class Pdf(unittest.TestCase):
    def test_brand_side_agent_and_profile_check(self):
        R, C, homes = run()
        agent = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
                 "email": None, "website": None, "brand": {"buyer_primary": "#0B6E4F"}}
        doc = html(R, C, homes, agent)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Buyer Summary", doc)  # the side shows in the page-1 label; no separate pill
        self.assertNotIn('class="tag', doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)
        self.assertIn("--subject:var(--text)", doc)  # the subject is black, never a status color or a second hue
        self.assertNotIn("var(--party", doc)
        self.assertIn("no profile", buyer_render.profile_check(profiles.load_agent(None)))  # chat only
        self.assertIsNone(buyer_render.profile_check({"name": "Dana Reyes", "brokerage": "Lakeside Realty"}))
        self.assertIn("profile incomplete", buyer_render.profile_check({"name": "Dana Reyes"}))
        self.assertNotIn("no profile", html(R, C, (), profiles.load_agent(None)))

    def test_market_table_has_the_median_sale_price(self):
        R, C, _ = run()
        rows = C["market_rows"]
        self.assertEqual(rows[1][0], "Median Sale Price")
        self.assertTrue(all(v.startswith("$") for v in rows[1][1:]))
        R["market"]["rows"].insert(1, ["Median Sale Price", "$450,000", "$440,000"])  # a table that has one gets no second
        self.assertEqual(sum(r[0] == "Median Sale Price" for r in compute.market_rows(R, [1, 2])), 1)
        self.assertEqual(compute.market_rows(R, None), R["market"]["rows"])  # no export: as written

    def test_full_pdf(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = buyer_render.build(report(), "pdf", tmp, {"agent": profiles.load_agent(None), "market": None,
                                                                  "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(paths, [paths[0]])  # the PDF only: no JSON handed to the agent
            self.assertFalse([f for f in os.listdir(tmp) if f.endswith(".json")])

    def test_widest_tables_wrap_and_credit_table_stays_whole(self):
        """Seven-figure prices and three scenarios: the payment and credit table headers wrap instead of clipping; the
        credit table is kept whole by the paginator."""
        def wide(R):
            R["costs"]["payment"]["price"] = 1442000
            R["costs"]["payment"]["scenarios"] = [
                {"label": "Conventional, 5% Down", "type": "conventional", "down_pct": 0.05, "assumed": True},
                {"label": "FHA, 3.5% Down", "type": "fha", "down_pct": 0.035, "assumed": True},
                {"label": "Conventional, 20% Down", "type": "conventional", "down_pct": 0.2, "assumed": True}]
            cs = R["costs"]["credit_scenarios"]
            cs["scenarios"] = [{"price": 1435000, "credit": 0}, {"price": 1445000, "credit": 10000},
                               {"price": 1455000, "credit": 20000}, {"price": 1465000, "credit": 30000}]
            cs.pop("buydown", None)
        R, C, homes = run(wide)
        doc = html(R, C, homes)
        self.assertEqual(doc.count('class="tbl wrap-head'), 2)
        self.assertIn('class="tbl wrap-head whole"', "".join(buyer_render.credit_section(
            R, C, cma.Labels(buyer_render.ASSETS, R.get("labels")))))
        self.assertIn("!el.querySelector('.tbl.whole')", cma.PAGINATE_JS)
        p, b, pg = browser_page(doc)
        try:
            clipped = pg.evaluate("""() => [...document.querySelectorAll('.tbl')].filter(t => t.scrollWidth > t.clientWidth + 1)
              .map(t => (t.querySelector('th, td') || {}).textContent)""")
            self.assertEqual(clipped, [])
        finally:
            b.close()
            p.stop()

    def test_a_table_block_runs_on_rather_than_leave_half_a_page(self):
        """A table block that doesn't fit with a third of the page or more left runs on (whole rows, header repeated)
        once its heading, intro and first rows fit."""
        filler = [f"<p>{'Filler text for the page. ' * 30}</p>" for _ in range(4)]  # about half a page
        rows = [[f"Row {i}", "$1,000", "$2,000"] for i in range(24)]
        blocks = filler + ["<h3>Estimated Monthly Payment</h3>", "<p>Intro.</p>",
                           cma.table(["Per Month", "A", "B"], rows, num_cols=(1, 2)), '<p class="note">Note.</p>']
        doc = ('<html><head><style>' + cma.css() + '</style></head><body><div class="wrap"><div class="onepage">P1</div>'
               '<div class="pb"></div>' + cma.group_blocks(blocks) + "</div></body></html>")
        p, b, pg = browser_page(doc)
        try:
            cma.paginate(pg)
            flow = pg.evaluate("() => [...document.querySelectorAll('.kg.flow')].map(e => e.querySelector('h3').textContent)")
            self.assertEqual(flow, ["Estimated Monthly Payment"])
            self.assertTrue(pg.evaluate("() => document.querySelector('.kg.flow .tbl').classList.contains('brk')"))
        finally:
            b.close()
            p.stop()


class ChatTemplate(unittest.TestCase):
    """The chat template follows page 1 of the PDF, and every compute.py path it quotes exists."""
    TEMPLATE = os.path.join(SKILL, "assets", "buyer-cma-template.md")
    PATH = re.compile(r"\b[a-z][a-z_0-9]*(?:\[[^\]]+\]|\.[a-z][a-z_0-9]*)+")
    BARE = ("bottom_line_paragraph", "median_adjusted_display", "current_bill_display", "comps_table", "cash_fit")

    @staticmethod
    def short(R):
        """Short of cash, with a past sale: every nullable object (cash_fit, the sale) is set."""
        R["costs"]["buyer_cash"] = 30000
        sold_history(R)

    def resolve(self, C, path, nullable=False):
        """The value at `path`; with `nullable`, a null object on the way ends it."""
        node = C
        for name, index in re.findall(r"\.?([a-z_0-9]+)|\[([^\]]+)\]", path):
            if node is None and nullable:
                return None
            if name:
                self.assertIsInstance(node, dict, path)
                self.assertIn(name, node, path)
                node = node[name]
            else:
                i = int(index) if index.isdigit() else self.resolve(C, index)
                self.assertIsInstance(node, list, path)
                self.assertLess(i, len(node), path)
                node = node[i]
        return node

    def test_every_template_path_exists_and_labels_match_page_one(self):
        with open(self.TEMPLATE) as f:
            text = f.read()
        paths = sorted({m.group(0) for m in self.PATH.finditer(text) if "." in m.group(0) or "[" in m.group(0)})
        self.assertIn("payments.rows[0].cash_short_display", paths)
        self.assertIn("summary_page.check_first[0][1]", paths)
        for change in (None, self.short):
            _, C, _ = run(change)
            for p in paths:
                with self.subTest(path=p, short=bool(change)):
                    self.resolve(C, p, nullable=change is None)
            for name in self.BARE:
                self.assertIn(name, C)
        with open(os.path.join(SKILL, "assets", "labels.json")) as f:
            labels = json.load(f)
        for key in ("sum_why", "sum_comps_h", "sum_costs", "sum_check"):
            self.assertIn(f"**{labels[key]}", text)

    def test_display_values_for_the_template(self):
        _, C, _ = run(self.short)
        pay, first = C["payments"], C["payments"]["rows"][0]
        self.assertTrue(first["cash_short"])
        self.assertEqual(first["cash_short_display"], compute.money(first["cash_short"]))
        self.assertEqual(pay["closing"]["pct_display"], f'{pay["closing"]["pct"] * 100:g}%')
        self.assertTrue(pay["tax_basis"]["homestead"])
        self.assertEqual(C["history"]["counted_since_sale_display"], "May 22, 2015")
        self.assertTrue(all(isinstance(v, str) for v in C["placeholders"].values()))  # never a None placeholder
        _, C, _ = run(lambda R: R["costs"]["taxes"].__setitem__("homestead", False))
        self.assertFalse(C["payments"]["tax_basis"]["homestead"])
        self.assertIsNone(C["history"]["counted_since_sale_display"])
        self.assertIsNone(C["payments"]["rows"][0]["cash_short_display"])


if __name__ == "__main__":
    unittest.main()
