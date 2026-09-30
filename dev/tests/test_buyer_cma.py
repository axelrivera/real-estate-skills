"""Tests for skills/buyer-cma/scripts."""
import copy
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "skills", "buyer-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, buyer_render, buyer_stats, handoff, profiles = load(
    "buyer-cma", "compute", "render", "stats", "_shared.handoff", "_shared.profiles")

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")


def report():
    with open(FIXTURE) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    return R


class MatchesPrototype(unittest.TestCase):
    """The prototype's 517-Hickorywood-Buyer-CMA.pdf. Its taxes, payments, credit scenarios, warnings and handoff values
    are pinned by golden (dev/golden/buyer-cma/hickorywood.json); the handoff schema isn't."""

    @classmethod
    def setUpClass(cls):
        R = report()
        market, homes = compute.load_inputs(R)
        cls.C = compute.compute(R, market, homes)

    def test_handoff_is_valid(self):
        handoff.validate(self.C["handoff"])
        self.assertEqual(len(self.C["comps_table"]), len(self.C["handoff"]["comps"]))  # the chat template's rows
        self.assertTrue(self.C["comps_table"][0]["adjusted_display"].startswith("$"))


class Warnings(unittest.TestCase):
    def test_credit_over_program_limit(self):
        R = report()
        R["costs"]["credit_scenarios"]["scenarios"].append({"price": 480000, "credit": 25000})
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertEqual(C["warning_keys"], ["credit_over_cap"])
        self.assertEqual(len(C["warnings"]), len(C["warning_keys"]))

    def test_walk_away_above_range_and_credit_alt_mismatch(self):
        R = report()
        R["offer_plan"]["walk_away"] = 490000
        R["offer_plan"]["credit_alt"] = {"price": 470000, "credit": 7000}
        market, homes = compute.load_inputs(R)
        keys = compute.compute(R, market, homes)["warning_keys"]
        self.assertIn("walk_away_above_range", keys)
        self.assertIn("credit_alt_mismatch", keys)

    def test_missing_field(self):
        R = report()
        del R["bottom_line"]["low"]
        market, homes = compute.load_inputs(R)
        with self.assertRaises(compute.ReportError):
            compute.compute(R, market, homes)


    def test_input_checks(self):
        """CMA-19, CMA-21: formatted numbers, no comps and a scenario without down_pct are plain errors."""
        for change in (lambda R: R["competition"]["rows"][0].__setitem__(2, "$474,500"),
                       lambda R: R["comps"].__setitem__("cards", []),
                       lambda R: R["costs"]["payment"]["scenarios"][0].pop("down_pct"),
                       lambda R: R["costs"]["payment"].__setitem__("rate", 0.0695),  # a fraction, not 6.95
                       lambda R: R["costs"].__setitem__("transfer_tax_rate", 0.7),  # 0.7 meant 0.7%
                       lambda R: R["costs"]["payment"].__setitem__("tax_jurisdiction_index", 5)):
            R = report()
            change(R)
            market, homes = compute.load_inputs(R)
            with self.assertRaises(compute.ReportError):
                compute.compute(R, market, homes)

    def test_thin_comps_warn(self):
        R = report()
        R["comps"]["cards"] = R["comps"]["cards"][:2]
        market, homes = compute.load_inputs(R)
        self.assertIn("thin_comps", compute.compute(R, market, homes)["warning_keys"])

    def test_no_current_bill(self):
        """CMA-13: new construction has no tax bill; the report renders "Not available"."""
        R = report()
        del R["costs"]["taxes"]["current_bill"]
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, homes, {"name": None, "brokerage": None, "brand": {}})
        self.assertIn("Not available", doc)

class OtherMarkets(unittest.TestCase):
    def test_texas_without_millage_estimates_the_tax(self):
        R = report()
        R["subject"].update(state="TX", county="Travis")
        R.pop("export")
        for j in R["costs"]["taxes"]["jurisdictions"]:
            j.pop("school_mills", None), j.pop("total_mills", None)
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax"], 474900 * 0.011 / 12)  # national estimate, labeled
        self.assertIn("tax_estimated", C["warning_keys"])

    def test_explicit_millage_works_anywhere(self):
        R = report()
        R["subject"].update(state="TX", county="Travis")
        R.pop("export")
        R["costs"]["taxes"]["jurisdictions"] = [{"label": "in Austin", "short": "Austin", "school_mills": 9.5, "total_mills": 19.0}]
        R["costs"]["payment"]["tax_jurisdiction_index"] = 0
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertAlmostEqual(C["taxes"][0]["annual"], 474900 * 19.0 / 1000)  # no Florida homestead in Texas
        self.assertIsNotNone(C["payments"])


class Pdf(unittest.TestCase):
    def test_brand_side_and_agent_fields(self):
        R = report()
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        agent = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
                 "email": None, "website": None, "brand": {"buyer_primary": "#0B6E4F"}}
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, homes, agent)
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Buyer Summary", doc)  # the side shows in the page-1 label; no separate pill
        self.assertNotIn('class="tag', doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)
        self.assertIn("--subject:var(--text)", doc)  # DS-3: black, never a status color or a second hue
        self.assertNotIn("var(--party", doc)

    def test_full_pdf(self):
        R = report()
        with tempfile.TemporaryDirectory() as tmp:
            import contextlib
            import io
            with contextlib.redirect_stderr(io.StringIO()):
                paths = buyer_render.build(R, "pdf", tmp, {"agent": profiles.load_agent(None), "market": None, "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(paths, [paths[0]])  # the PDF only: no JSON handed to the agent
            self.assertFalse([f for f in os.listdir(tmp) if f.endswith(".json")])


class Flood(unittest.TestCase):
    """CMA-6: the payment has a flood line, a quote or "Get a Quote", never $0."""

    def run_(self, **payment):
        R = report()
        R["costs"]["payment"].update(payment)
        market, homes = compute.load_inputs(R)
        return R, compute.compute(R, market, homes)

    def test_get_a_quote(self):
        R, C = self.run_()
        pay = C["payments"]
        self.assertIsNone(pay["flood"]["annual"])
        self.assertTrue(all(r["flood"] is None for r in pay["rows"]))
        self.assertIn("Citizens", pay["flood"]["note"])  # zone X from the facts, Florida, 2026
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertIn("Flood Insurance", html)
        self.assertIn("Get a Quote", html)
        self.assertNotIn("isn't required", html)

    def test_quote_counts(self):
        _, base = self.run_()
        _, C = self.run_(flood_insurance_annual=1800)
        for a, b in zip(base["payments"]["rows"], C["payments"]["rows"]):
            self.assertAlmostEqual(b["total"] - a["total"], 150)
        self.assertNotIn("Get a quote", C["payments"]["flood"]["note"])

    def test_zone_override(self):
        _, C = self.run_(flood_zone="AE")
        self.assertEqual(C["payments"]["flood"]["required"], "lender")


class LoanTaxes(unittest.TestCase):
    """CORE-16: without a lender figure, the credit scenarios add Florida's loan taxes on the loan amount."""

    def test_itemized_without_a_lender_figure(self):
        R = report()
        R["costs"]["credit_scenarios"].pop("closing_cost_pct")
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        col = C["credit"]["columns"][0]
        loan = col["loan"]
        self.assertEqual(col["loan_taxes"], round(loan * 0.0035) + round(loan * 0.002))
        self.assertAlmostEqual(col["closing_costs"], col["price"] * 0.025 + col["loan_taxes"])


class AuditMethod(unittest.TestCase):
    """CMA-10, CMA-11, CMA-14, CMA-15, CMA-17, CMA-20."""

    def run_(self, R, **kw):
        market, homes = compute.load_inputs(R, **kw)
        return compute.compute(R, market, homes)

    def test_adjustment_rates_outside_their_area_warn(self):
        C = self.run_(report())
        self.assertNotIn("adjustment_scope", C["warning_keys"])  # Seminole, $474,900: inside
        R = report()
        R["subject"]["county"] = "Hillsborough"  # Stellar, but not where the rates were set
        C = self.run_(R)
        self.assertIn("adjustment_scope", C["warning_keys"])
        self.assertTrue(any("Hillsborough" in w for w in C["warnings"]))  # names the county

    def test_price_minus_credit_is_not_called_the_same_net(self):
        R = report()
        R["costs"]["credit_scenarios"]["seller_pays_buyer_broker_pct"] = 0.025
        C = self.run_(R)
        self.assertEqual(C["credit"]["seller_cost_per_10k"], 320)  # 0.7% doc stamps + 2.5% buyer-broker pay
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertNotIn("Same Seller Net", html)
        self.assertIn("$320", html)

    def test_no_homestead_label(self):
        R = report()
        R["costs"]["taxes"]["homestead"] = False
        C = self.run_(R)
        html, _ = buyer_render.build_html(R, C, [], {})
        self.assertNotIn("With Homestead", html)
        self.assertIn("No Homestead", html)

    def test_mls_option(self):
        R = report()
        R["subject"]["county"] = "Brevard"  # not Stellar: no MLS assumed, so the export can't be read
        with self.assertRaises(compute.mls.ExportError):
            compute.load_inputs(R)
        market, homes = compute.load_inputs(R, mls_name="Stellar")
        self.assertEqual(market.mls, "Stellar")
        self.assertTrue(homes)

    def test_handoff_file_has_the_side(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            self.assertTrue(json.loads(out.getvalue())["handoff_file"].endswith(".buyer.cma.json"))

    def test_export_resolves_beside_the_report(self):
        # report.json names its export "export.csv": found in report.json's folder, whatever folder the script runs from.
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            R = report()
            shutil.copy(R["export"], os.path.join(tmp, "export.csv"))
            R["export"] = "export.csv"
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(R, f)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            self.assertTrue(json.loads(out.getvalue())["ok"])

    def test_handoff_file_defaults_next_to_report(self):
        # A working file beside report.json, never in the outputs folder the agent downloads from.
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path]), 0)
            hfile = json.loads(out.getvalue())["handoff_file"]
            self.assertEqual(os.path.dirname(hfile), os.path.abspath(tmp))

    def test_offer_ladder_order(self):
        R = report()
        R["offer_plan"]["opening"] = R["offer_plan"]["walk_away"] + 5000
        with self.assertRaisesRegex(compute.ReportError, "opening"):
            self.run_(R)


class CompsFirst(unittest.TestCase):
    """CMA-110 (the median before the range exists, an outlier rule) and CMA-112 (the adjusted spread)."""

    def run_cli(self, R):
        import contextlib
        import io
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(R, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = compute.main([path])
            written = os.listdir(tmp)
        return code, json.loads(out.getvalue()), written

    def test_median_from_comps_alone(self):
        full = report()
        market, homes = compute.load_inputs(copy.deepcopy(full))
        C = compute.compute(copy.deepcopy(full), market, homes)
        R = {k: full[k] for k in ("subject", "comps", "export", "as_of")}
        code, out, written = self.run_cli(R)
        self.assertEqual(code, 0, out)
        self.assertEqual(out["stage"], "comps")
        self.assertEqual(out["median_adjusted"], C["median_adjusted"])
        self.assertEqual((out["adjusted_min"], out["adjusted_max"]), (C["adjusted_min"], C["adjusted_max"]))
        self.assertEqual(out["asking_vs_median"], full["subject"]["list_price"] - C["median_adjusted"])
        self.assertEqual(written, ["report.json"])  # no handoff without a range

    def test_adjusted_spread_in_full_output(self):
        R = report()
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        values = [c["adjusted"] for c in R["comps"]["cards"]]
        self.assertEqual((C["adjusted_min"], C["adjusted_max"]), (min(values), max(values)))

    def test_outlier_is_named(self):
        R = report()
        market, homes = compute.load_inputs(R)
        self.assertNotIn("outlier", compute.compute(copy.deepcopy(R), market, homes)["warning_keys"])
        card = R["comps"]["cards"][0]
        card["adjustments"].append({"label": "Test", "amount": 80000})
        C = compute.compute(R, market, homes)
        hits = [w for w, k in zip(C["warnings"], C["warning_keys"]) if k == "outlier"]
        self.assertEqual(len(hits), 1, C["warnings"])
        self.assertTrue(hits[0].startswith(card["address"]))  # names the comp


class StatsWithoutAnExportRow(unittest.TestCase):
    def test_facts_rank_the_comps(self):
        """A home from a property report with no export row: its facts rank the candidates, lat/lon set distances."""
        import contextlib
        import io
        export = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "export-reso.csv")
        with contextlib.redirect_stdout(io.StringIO()) as out:
            buyer_stats.main([export, "--address", "999 NOWHERE LN", "--state", "FL", "--county", "Seminole",
                              "--sqft", "1849", "--pool", "--subdivision", "FERNWOOD PARK UNIT 2",
                              "--lat", "28.67", "--lon", "-81.41"])
        d = json.loads(out.getvalue())
        self.assertEqual(d["sold_candidates"][0]["address"], "602 QUAIL LN")
        self.assertEqual(d["sold_candidates"][0]["distance"], 0.15)
        self.assertIn("ranked from the facts given", d["market_notes"][-1])


class AuditBuyerBrokerShortfall(unittest.TestCase):
    def test_shortfall_row_and_cash(self):
        """CMA-4: a 2.5% agreement with the seller paying 0 adds the full fee to cash to close."""
        R = report()
        market, homes = compute.load_inputs(R)
        base = compute.compute(R, market, homes)["credit"]["columns"]
        R["costs"]["credit_scenarios"].update(buyer_broker_agreement_pct=0.025, seller_pays_buyer_broker_pct=0)
        cols = compute.compute(R, market, homes)["credit"]["columns"]
        for b, c in zip(base, cols):
            self.assertEqual(c["bb_short"], round(0.025 * c["price"]))
            self.assertEqual(round(c["cash"] - b["cash"]), c["bb_short"])
        doc, _ = buyer_render.build_html(copy.deepcopy(R), compute.compute(R, market, homes), homes,
                                         {"name": None, "brokerage": None, "brand": {}})
        self.assertIn("Broker Fee (Not Paid by Seller)", doc)


EVAL_GRID = [  # dev/evals/buyer-cma/files/history-517-hickorywood.md as the grid lists it: newest first, Feb 7 misplaced
    {"date": "2026-09-16", "mls": "O6433709", "change": "DECR", "price": 474900},
    {"date": "2026-08-31", "mls": "O6433709", "change": "DECR", "price": 478900},
    {"date": "2026-08-17", "mls": "O6433709", "change": "NEW", "price": 484900},
    {"date": "2026-06-09", "mls": "O6371102", "change": "CANC", "dom": 83},
    {"date": "2026-05-21", "mls": "O6371102", "change": "BOM", "price": 484900},  # "INCR ... (BOM)": back on, higher
    {"date": "2026-05-17", "mls": "O6371102", "change": "TOM"},
    {"date": "2026-04-11", "mls": "O6371102", "change": "PNC", "price": 474500},
    {"date": "2026-02-07", "mls": "O6371102", "change": "DECR", "price": 474500},
    {"date": "2026-03-05", "mls": "O6371102", "change": "BOM"},
    {"date": "2026-01-27", "mls": "O6371102", "change": "TOM"},
    {"date": "2026-01-22", "mls": "O6371102", "change": "DECR", "price": 479900},
    {"date": "2026-01-16", "mls": "O6371102", "change": "NEW", "price": 483900},
]


class History(unittest.TestCase):
    """CMA-201 (the price changes and active days counted by the script) and CMA-208 (out-of-order rows and MLS
    numbers that don't match are warned)."""

    def run_(self, events, locality_mls="O6448292"):
        R = report()
        R["history"]["events"] = copy.deepcopy(events)
        R["subject"]["locality"] = R["subject"]["locality"].rsplit("MLS ", 1)[0] + "MLS " + locality_mls
        market, homes = compute.load_inputs(R)
        return R, compute.compute(R, market, homes)

    def test_four_cuts_and_one_increase(self):
        """The eval's history: 4 cuts and 1 increase (runs typed "five cuts"), 83 + 36 active days, 1 failed contract."""
        _, C = self.run_(EVAL_GRID, "O6433709")
        h = C["history"]
        self.assertEqual((h["price_cuts"], h["price_increases"]), (4, 1))
        self.assertEqual(h["price_cut_total"], 4000 + 5400 + 6000 + 4000)
        self.assertEqual(h["price_increase_total"], 10400)
        self.assertEqual(h["price_cut_pct"], round(19400 / 483900, 4))
        self.assertEqual(h["failed_contracts"], 1)
        self.assertEqual(h["active_days"], 83 + 36)  # the CANC row's DOM, then Aug 17 to as_of Sep 22
        self.assertEqual(h["listings"], 2)
        self.assertEqual(C["placeholders"]["price_cuts"], "4 price cuts")
        self.assertEqual(C["placeholders"]["price_increases"], "1 price increase")

    def test_out_of_order_row_and_mls_mismatch_warn(self):
        _, C = self.run_(EVAL_GRID, "O6433709")
        self.assertEqual(C["warning_keys"].count("history_order"), 1)
        self.assertIn("export_mls_mismatch", C["warning_keys"])  # the export's active row is O6448292
        self.assertNotIn("history_mls_mismatch", C["warning_keys"])  # the newest row is the listing's number
        fixed = sorted(EVAL_GRID, key=lambda e: e["date"], reverse=True)
        _, C = self.run_(fixed, "O6448292")
        self.assertNotIn("history_order", C["warning_keys"])
        self.assertNotIn("export_mls_mismatch", C["warning_keys"])
        self.assertIn("history_mls_mismatch", C["warning_keys"])  # the history's newest row is O6433709
        self.assertEqual(C["history"]["price_cuts"], 4)  # same counts once sorted

    def test_calendar_days_without_dom(self):
        events = [e for e in EVAL_GRID if e["change"] != "CANC"] + [{"date": "2026-06-09", "mls": "O6371102", "change": "CANC"}]
        events.sort(key=lambda e: e["date"], reverse=True)
        _, C = self.run_(events, "O6433709")
        # Jan 16-27 (11), Mar 5-Apr 11 (37), May 21-Jun 9 (19), Aug 17-Sep 22 (36): pending and off-market days don't count
        self.assertEqual(C["history"]["active_days"], 11 + 37 + 19 + 36)

    def test_rows_built_from_events(self):
        R, C = self.run_(sorted(EVAL_GRID, key=lambda e: e["date"], reverse=True), "O6433709")
        R["history"].pop("rows", None)
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, [], {})
        self.assertIn("Back on the market at a higher price", doc)
        self.assertIn("Relisted as a new listing", doc)

    def test_rows_without_events_warn(self):
        R = report()
        R["history"].pop("events")
        R["history"]["rows"] = [["Jan 16, 2026", "First listed", "$483,900"]]
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertIn("history_no_events", C["warning_keys"])
        self.assertIsNone(C["history"])

    def test_bad_change_is_an_error(self):
        with self.assertRaises(compute.ReportError):
            self.run_([{"date": "2026-01-16", "change": "relisted?"}])

    def test_stats_mls_number(self):
        import contextlib
        import io
        export = os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "export-spring-oaks.csv")
        for number, keys in (("O6433709", ["export_mls_mismatch"]), ("O6448292", [])):
            with contextlib.redirect_stdout(io.StringIO()) as out:
                buyer_stats.main([export, "--address", "517 HICKORYWOOD AVE", "--state", "FL", "--county", "Seminole",
                                  "--mls-number", number])
            self.assertEqual(json.loads(out.getvalue())["warning_keys"], keys)


class GutCheck(unittest.TestCase):
    """CMA-202: a rough range (the adjusted span) and a rough opening, target and walk-away from the median."""

    def comps_only(self, **subject):
        full = report()
        R = {k: copy.deepcopy(full[k]) for k in ("subject", "comps", "history", "export", "as_of")}
        R["subject"].update(subject)
        R["export"] = full["export"]
        market, homes = compute.load_inputs(R)
        return compute.comps_first(R, market, homes)

    def test_rough_plan(self):
        out = self.comps_only()
        rough, median = out["rough"], out["median_adjusted"]
        self.assertEqual((rough["range"]["low"], rough["range"]["high"]), (out["adjusted_min"], out["adjusted_max"]))
        self.assertEqual(rough["walk_away"], median // 1000 * 1000)  # at or below the median
        self.assertEqual(rough["opening"], (median - 25000 / 2) // 1000 * 1000)  # Florida's typical range width, halved
        self.assertTrue(rough["opening"] <= rough["target"] <= rough["walk_away"])
        self.assertEqual(out["history"]["price_cuts"], 4)  # the gut check counts the history too
        self.assertEqual(out["warning_keys"], [])

    def test_never_above_asking(self):
        out = self.comps_only(list_price=440000)
        rough = out["rough"]
        self.assertEqual(rough["walk_away"], 440000)
        self.assertTrue(rough["capped_at_asking"])
        self.assertLessEqual(rough["opening"], rough["target"])


class Placeholders(unittest.TestCase):
    """CMA-203: {median_adjusted} and the history's placeholders fill every field; an unknown one warns."""

    def test_filled_everywhere(self):
        R = report()
        R["comps"]["summary_paragraph"] = "The median is {median_adjusted}, after {price_cuts}."
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, homes, {})
        self.assertIn(f"The median is {C['median_adjusted_display']}, after 4 price cuts.", doc)
        self.assertNotIn("{median_adjusted}", doc)
        self.assertEqual(C["summary_page"]["key_stats"][0][0], C["median_adjusted_display"])  # the chat template's copy

    def test_unknown_placeholder_warns(self):
        R = report()
        R["watch"]["items"][0] += " {median_value}"
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        self.assertEqual(C["warning_keys"], ["unfilled_placeholder"])
        self.assertIn("$.watch.items[0]", C["warnings"][0])


class PaymentBasis(unittest.TestCase):
    """CMA-204: the payment at the plan's target (or says which price), the buyer's cash, and which tax it uses."""

    def run_(self, change=None):
        R = report()
        if change:
            change(R)
        market, homes = compute.load_inputs(R)
        return R, compute.compute(R, market, homes)

    def test_target_by_default(self):
        def change(R):
            R["costs"]["payment"].pop("price")
            R["costs"]["taxes"].pop("purchase_price")
        R, C = self.run_(change)
        op = R["offer_plan"]
        self.assertEqual(C["payments"]["price"], (op["target_low"] + op["target_high"]) / 2)
        self.assertEqual(C["payments"]["price_basis"], "target")
        self.assertEqual(R["costs"]["taxes"]["purchase_price"], C["payments"]["price"])  # page 1's tax and payment agree
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, [], {})
        self.assertIn("(Target), 5% Down", doc)

    def test_asking_says_so(self):
        R, C = self.run_()
        self.assertEqual(C["payments"]["price_basis"], "asking")
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, [], {})
        self.assertIn("(Asking)", doc)

    def test_cash_short(self):
        R, C = self.run_(lambda R: R["costs"].__setitem__("buyer_cash", 30000))
        cols = C["credit"]["columns"]
        short = [c for c in cols if c["cash"] > 30000]
        self.assertTrue(short)
        self.assertTrue(all(c["cash_short"] == round(c["cash"] - 30000) for c in short))
        rows = C["payments"]["rows"]
        self.assertTrue(rows[2]["cash_short"])  # 20% down: flagged in the table, but a comparison, so not warned
        self.assertEqual(C["warning_keys"].count("cash_short"), len(short) + bool(rows[0]["cash_short"]))
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, [], {})
        self.assertIn("over your $30,000", doc)
        _, C = self.run_(lambda R: R["costs"].__setitem__("buyer_cash", 200000))
        self.assertNotIn("cash_short", C["warning_keys"])

    def test_unconfirmed_district_uses_the_higher_bill(self):
        R, C = self.run_(lambda R: R["costs"]["payment"].pop("tax_jurisdiction_index"))
        annual = [t["annual"] for t in C["taxes"]]
        self.assertEqual(C["payments"]["tax_index"], annual.index(max(annual)))
        tb = C["payments"]["tax_basis"]
        self.assertTrue(tb["unconfirmed"] and tb["higher"] and tb["label_estimate"])
        doc, _ = buyer_render.build_html(copy.deepcopy(R), C, [], {})
        self.assertIn("Estimate)", doc)
        self.assertIn("the higher of the two", doc)

    def test_one_confirmed_district_is_not_an_estimate(self):
        def change(R):
            R["costs"]["taxes"]["jurisdictions"] = R["costs"]["taxes"]["jurisdictions"][:1]
            R["costs"]["payment"]["tax_jurisdiction_index"] = 0
        _, C = self.run_(change)
        self.assertFalse(C["payments"]["tax_basis"]["label_estimate"])


class ScatterLabels(unittest.TestCase):
    """CMA-205: a label steps to another side rather than print over a marker."""

    def test_label_moves_off_a_marker(self):
        (cma,) = load("buyer-cma", "_shared.cma")
        placer = cma._LabelPlacer([(100, 100, 10), (60, 104, 6.5)], (0, 0, 400, 400))  # a comp just left of the subject
        svg = placer.place(100, 100, "left", "517 Hickorywood", "lbl-subj", 14, 13, bold=True)
        self.assertEqual(placer.moved, [("517 Hickorywood", "left", "right")])
        self.assertEqual(placer.overlapping, [])
        self.assertIn('text-anchor="start"', svg)

    def test_clear_side_is_kept(self):
        (cma,) = load("buyer-cma", "_shared.cma")
        placer = cma._LabelPlacer([(100, 100, 10)], (0, 0, 400, 400))
        placer.place(100, 100, "below", "517 Hickorywood", "lbl-subj", 14, 13)
        self.assertEqual(placer.moved, [])

    def test_render_reports_the_move(self):
        R = report()
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        buyer_render.build_html(copy.deepcopy(R), C, homes, {})
        # the fixture's subject label grazes only a background sale dot on the left; a line higher it would cover the
        # band's label, so it stays, and nothing that counts is covered
        self.assertEqual(C["scatter_labels"], {"moved": [], "overlapping": []})

    def test_another_label_counts(self):
        (cma,) = load("buyer-cma", "_shared.cma")
        placer = cma._LabelPlacer([], (0, 0, 400, 400))
        placer.place(100, 100, "right", "1512 Buttonbush Dr", "lbl", 10, 12)
        placer.place(100, 104, "right", "1471 Sedgefield", "lbl", 10, 12)  # a second point just below the first
        self.assertEqual(len(placer.moved), 1)
        self.assertEqual(placer.overlapping, [])


class CreditPlaceholders(unittest.TestCase):
    """The credit trade-off quoted from the scenarios, not typed: each $5,000 of credit's cash saved and monthly cost."""

    def test_filled_from_the_scenarios(self):
        R = report()
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        cols = C["credit"]["columns"]
        per = 5000 / (cols[1]["credit"] - cols[0]["credit"])
        self.assertEqual(C["placeholders"]["credit_monthly_per_5k"], f"${round((cols[1]['payment'] - cols[0]['payment']) * per):,}")
        self.assertEqual(C["placeholders"]["credit_cash_per_5k"], f"${round((cols[0]['cash'] - cols[1]['cash']) * per, -2):,.0f}")
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])


if __name__ == "__main__":
    unittest.main()
