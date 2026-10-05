"""seller-cma compute.py rules: costs and nets, buyer payments, warnings, the expected-sale rule, data the script owns,
other markets, the handoff and the chat template.

The nets, payments and keys of the unmodified fixtures are pinned by golden (dev/golden/seller-cma/); these tests change
an input and check the rule. The shared helpers here (report, run, row, texas, tanager, reprice, AGENT) are imported by
the other test_seller_cma_* files, with the modules loaded here (one copy, so ReportError and DeckError match).
"""
import contextlib
import io
import json
import os
import statistics
import sys
import tempfile
import unittest
from datetime import date

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
SKILL = os.path.join(ROOT, "skills", "seller-cma")
sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, seller_render, deck, handoff, profiles, stats_mod = load(
    "seller-cma", "compute", "render", "deck", "_shared.handoff", "_shared.profiles", "stats")

FIXTURE = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "hickorywood.json")
TANAGER = os.path.join(ROOT, "dev", "fixtures", "seller-cma", "tanager", "report.json")
AGENT = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "phone": None,
         "email": None, "website": None, "brand": {"seller_primary": "#0B6E4F"}}


def report():
    with open(FIXTURE) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    R["deck"] = os.path.join(ROOT, R["deck"])
    return R


def report_with_deck():
    R = report()
    with open(R["deck"]) as f:
        R["deck"] = json.load(f)
    return R


def tanager():
    """842 Tanager Ridge Dr: five comps clustered at $384,000 to $395,100 adjusted, an export whose sold rows echo the
    sale price as the current price, a July 1 market split and the seller's stated $171,500 payoff."""
    with open(TANAGER) as f:
        R = json.load(f)
    R["export"] = os.path.join(os.path.dirname(TANAGER), R["export"])
    return R


def run(R):
    market, homes = compute.load_inputs(R)
    return compute.compute(R, market, homes), homes


def row(C, key):
    return next(r for r in C["net"]["rows"] if r["key"] == key)


def texas(R):
    R["costs"] = {}  # no terms given: national estimates, never Florida's numbers
    R["subject"].update(state="TX", county="Travis", city="Austin")
    R.pop("export")
    R["buyer_payment"].pop("district")
    R["buyer_payment"].update(school_mills=9.5, total_mills=19.0)
    return R


def reprice(current=479900):
    """The agent's own listing at `current`, 60 days on market: Stay at Current Price plus cuts."""
    R = report()
    stay = {"label": "Stay at Current Price", "list_price": current, "expected_sale": 458000, "time": "2–4 months",
            "seller_credit": 10000, "note": "Has sat 60 days"}
    R["pricing"]["strategies"] = [stay] + R["pricing"]["strategies"][1:]
    R["reprice"] = {"current_price": current, "days_on_market": 60}
    return R


def card(R, address):
    return next(c for c in R["comps"]["cards"] if c["address"] == address)


class Handoff(unittest.TestCase):
    def test_cli_writes_a_valid_seller_handoff(self):
        C, _ = run(report())
        handoff.validate(C["handoff"])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "report.json")
            with open(path, "w") as f:
                json.dump(report(), f)
            with contextlib.redirect_stdout(io.StringIO()) as out:
                self.assertEqual(compute.main([path, "--out", tmp]), 0)
            result = json.loads(out.getvalue())
            self.assertEqual(handoff.load(result["handoff_file"])["side"], "seller")
            self.assertTrue(result["handoff_file"].endswith(".seller.cma.json"))


class Costs(unittest.TestCase):
    def test_agent_terms_replace_the_defaults(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.02}
        C, _ = run(R)
        self.assertEqual((row(C, "listing_fee")["amounts"][0], row(C, "buyer_broker_fee")["amounts"][0]), (-13890, -9260))
        self.assertFalse(C["net"]["standard_terms"])
        self.assertNotIn("brokerage_assumed", C["assumption_keys"])
        R["costs"] = {"listing_fee_pct": 0.025, "buyer_broker_fee_pct": 0}
        self.assertNotIn("buyer_broker_fee", {r["key"] for r in run(R)[0]["net"]["rows"]})
        R["costs"] = {"listing_fee_pct": 2.5}  # *_pct fields are fractions everywhere (0.025)
        with self.assertRaises(compute.ReportError):
            run(R)
        R = report()
        R["costs"] = {"title_fees": {"settlement_fee": 850, "title_search": 200}}
        C, _ = run(R)
        self.assertEqual(row(C, "title_fees")["amounts"][0], -1050)
        self.assertNotIn("title_fees_built_in", C["assumption_keys"])

    def test_default_brokerage_is_unlabeled_and_still_asked(self):
        """A default commission is a default: 2.5% + 2.5%, the files build, no label beside a net; the chat asks."""
        R = report()
        R["costs"] = {}
        C, homes = run(R)
        self.assertEqual(row(C, "listing_fee")["amounts"][1], -0.025 * 462000)
        self.assertEqual(row(C, "buyer_broker_fee")["amounts"][1], -0.025 * 462000)
        self.assertTrue(C["net"]["standard_terms"])
        self.assertFalse(C["net"]["incomplete"])
        self.assertIn("brokerage_assumed", C["assumption_keys"])
        self.assertNotIn("net_header_sub", C["options_summary"])
        doc, _ = seller_render.build_html(R, C, homes, AGENT)
        self.assertNotIn("th-sub", doc)

    def test_credit_rows_by_key_and_totals_add_up(self):
        """A credit in only some options keeps its row, in either order, and every column adds up."""
        for credits in ((0, 10000, 0), (10000, 0, 0), (0, 0, 5000)):
            with self.subTest(credits=credits):
                R = report()
                for x, c in zip(R["pricing"]["strategies"], credits):
                    x["seller_credit"] = c
                C, _ = run(R)
                self.assertEqual(row(C, "credit")["amounts"], [-c for c in credits])
                for i, total in enumerate(C["net"]["totals"]):
                    self.assertAlmostEqual(sum(r["amounts"][i] for r in C["net"]["rows"]
                                               if r["key"] not in ("total", "holding", "after_holding")), total, places=2)
                    self.assertEqual(C["net"]["after_holding"][i], total - C["net"]["holding"][i])

    def test_payoff_hoa_and_other_costs(self):
        R = report()
        base = run(R)[0]["strategies"][0]["net"]
        R["costs"].update({"mortgage_payoff": 210000, "hoa": True, "other": [{"label": "Survey", "amount": 450}]})
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"])
        self.assertEqual(row(C, "estoppel")["amounts"][0], -299)
        self.assertEqual(row(C, "other")["amounts"][0], -450)
        self.assertEqual(round(C["strategies"][0]["net"]), round(base) - 299 - 450 - 210000)
        self.assertIn("payoff_seller", C["assumption_keys"])
        R["costs"]["mortgage_payoff"] = 0
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"] and C["net"]["no_mortgage"])
        self.assertNotIn("payoff", {r["key"] for r in C["net"]["rows"]})
        R = tanager()
        C, _ = run(R)
        self.assertEqual(row(C, "payoff")["amounts"][0], -171500)
        self.assertIn("payoff_seller", C["assumption_keys"])
        R["costs"].pop("mortgage_payoff")
        R["costs"]["mortgage_balance"] = 171500
        C, _ = run(R)
        self.assertEqual(row(C, "payoff")["amounts"][0], -round(171500 * (1 + 0.045 / 12)))
        self.assertTrue(C["net"]["payoff_estimated"])
        self.assertIn("payoff_estimated", C["assumption_keys"])
        R = report()
        R["costs"].update(mortgage_balance=200000, mortgage_rate=6)
        self.assertEqual(row(run(R)[0], "payoff")["amounts"][0], -201000)
        self.assertEqual(compute.finance.payoff_from_balance(200000, 6), 201000)


class TaxProration(unittest.TestCase):
    def test_proration_to_each_options_closing(self):
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-01")
        C, _ = run(R)
        self.assertTrue(C["net"]["has_tax"])
        self.assertEqual(C["net"]["closings"][1], "2026-12-01")  # the recommended option closes by the seller's goal
        self.assertEqual(row(C, "tax_proration")["amounts"][1], -round(6000 * 0.96 * 334 / 365))
        R["costs"]["current_tax_bill_paid"] = True
        self.assertEqual(row(run(R)[0], "tax_proration")["amounts"][1], round(6000 * 0.96 * 31 / 365))
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-18")
        C, _ = run(R)
        self.assertEqual(C["net"]["closings"], ["2027-01-22", "2026-12-18", "2026-12-18"])
        tax = row(C, "tax_proration")["amounts"]
        jan = (date(2027, 1, 22) - date(2027, 1, 1)).days
        self.assertEqual(tax[0], -(round(6000 * 0.96) + round(6000 * 0.96 * jan / 365)))  # this year's bill, then 2027's
        self.assertEqual(tax[1], -round(6000 * 0.96 * (date(2026, 12, 18) - date(2026, 1, 1)).days / 365))
        R = report()
        R["costs"]["annual_tax"] = 6000  # no closing date: each option's time to contract sets it
        C = run(R)[0]
        self.assertNotIn("tax_no_closing_date", C["warning_keys"])
        self.assertEqual(C["net"]["closings"], ["2027-01-22", "2026-11-23", "2026-11-05"])
        R["pricing"]["strategies"] = [{**x, "time": ""} for x in R["pricing"]["strategies"]]  # nothing to date it by
        self.assertIn("tax_no_closing_date", run(R)[0]["warning_keys"])

    def test_late_year_closing_assumes_the_bill_unpaid(self):
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-15")
        C, _ = run(R)
        self.assertTrue(C["net"]["tax_assumed"])
        self.assertIn("tax_bill_unpaid", C["assumption_keys"])
        self.assertLess(row(C, "tax_proration")["amounts"][1], 0)  # a cost to the seller
        R["costs"]["current_tax_bill_paid"] = True
        C, _ = run(R)
        self.assertFalse(C["net"]["tax_assumed"])
        self.assertGreater(row(C, "tax_proration")["amounts"][1], 0)  # the buyer credits back Dec 15 to Dec 31
        R = report()
        R["costs"]["annual_tax"] = 6000  # before bills go out: no assumption
        for x in R["pricing"]["strategies"]:
            x["closing_date"] = "2026-09-15"
        self.assertFalse(run(R)[0]["net"]["tax_assumed"])


class HoldingCosts(unittest.TestCase):
    def test_net_after_holding(self):
        """Slower options pay more to hold the home, and options are compared after that."""
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, _ = run(R)
        hold = C["net"]["holding"]
        self.assertTrue(hold[0] > hold[1] > hold[2] > 0)
        self.assertEqual([x["net_after_holding"] for x in C["strategies"]], [t - h for t, h in zip(C["net"]["totals"], hold)])
        after = C["net"]["after_holding"]
        self.assertEqual(C["net_spread"], max(after) - min(after))
        self.assertEqual(C["net_basis"], "after_holding")
        nets = [x["net_after_holding"] for x in C["strategies"]]
        ri = C["recommended_index"]
        self.assertEqual([x["net_vs_recommended"] for x in C["strategies"]], [v - nets[ri] for v in nets])
        self.assertTrue(C["net"]["holding_rate_assumed"])
        self.assertIn("holding_rate", C["assumption_keys"])
        R["costs"]["mortgage_rate"] = 6.25
        C, _ = run(R)
        self.assertFalse(C["net"]["holding_rate_assumed"])
        self.assertNotIn("holding_rate", C["assumption_keys"])
        f = compute.finance
        self.assertEqual((f.months_in("45–90 days"), f.months_in("3–6 weeks"), f.months_in("2 months")), (2.22, 1.03, 2.0))
        self.assertIsNone(f.months_in("soon"))

    def test_rounded_differences(self):
        """Rounded to $100 under $10,000, so "about" agrees with the exact figure beside it."""
        for value, about in ((6796, "$6,800"), (-3976, "$4,000"), (2240, "$2,200"), (3678, "$3,700"),
                             (12345, "$12,500"), (61400, "$61,000")):
            self.assertEqual(compute.about(value), "about " + about)
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, _ = run(R)
        self.assertEqual(C["strategies"][C["recommended_index"]]["net_vs_recommended_about"], "")
        for x in C["strategies"]:
            if not x["recommended"] and abs(x["net_vs_recommended"]) >= 250:
                self.assertIn(compute.about(x["net_vs_recommended"]), x["net_vs_recommended_about"])
        self.assertEqual(C["net_spread_about"], compute.about(C["net_spread"]))


class BuyerPayments(unittest.TestCase):
    def test_flood_quote_and_tax_rate(self):
        C, _ = run(report())
        R = report()
        R["buyer_payment"]["flood_insurance_annual"] = 1200
        Q, _ = run(R)
        for a, b in zip(C["payments"]["rows"], Q["payments"]["rows"]):
            self.assertAlmostEqual(b["payment"] - a["payment"], 100)
        R = texas(report())
        R["buyer_payment"].pop("total_mills")
        C, _ = run(R)
        self.assertAlmostEqual(C["payments"]["rows"][0]["tax_monthly"], 479900 * 0.011 / 12)
        self.assertIn("tax_estimated", C["warning_keys"])

    def test_homestead_only_in_florida(self):
        R = texas(report())
        R["buyer_payment"].pop("homestead", None)  # left at its default (true)
        default = run(R)[0]["payments"]
        self.assertFalse(default["homestead_applied"])
        self.assertIsNone(default["flood"]["required"])  # no Citizens rule outside Florida
        R["buyer_payment"]["homestead"] = False
        self.assertEqual([r["payment"] for r in default["rows"]], [r["payment"] for r in run(R)[0]["payments"]["rows"]])
        self.assertAlmostEqual(default["rows"][0]["tax_monthly"], 479900 * 19.0 / 1000 / 12)
        R = report()  # Florida: the exemption lowers the payment
        home = run(R)[0]["payments"]["rows"]
        R["buyer_payment"]["homestead"] = False
        self.assertGreater(run(R)[0]["payments"]["rows"][0]["payment"], home[0]["payment"])


class OtherMarkets(unittest.TestCase):
    def test_texas_uses_estimates_never_florida_numbers(self):
        C, _ = run(texas(report()))
        self.assertFalse(C["preliminary"])
        self.assertEqual({r["key"] for r in C["net"]["rows"]},
                         {"sale", "listing_fee", "buyer_broker_fee", "owner_title", "title_fees", "credit", "total",
                          "holding", "after_holding"})  # no transfer tax in Texas, never Florida's stamps
        self.assertEqual(C["net"]["missing"], [])
        self.assertFalse(C["net"]["incomplete"])
        self.assertLessEqual({"brokerage_assumed", "estimates", "no_homestead"}, set(C["assumption_keys"]))
        R = texas(report())
        R["subject"].update(state="GA", county="Fulton", city="Atlanta")  # a state that taxes deeds
        self.assertIn("transfer_tax", {r["key"] for r in run(R)[0]["net"]["rows"]})
        R = texas(report())
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.025, "transfer_tax_rate": 0,
                      "title_fees": {"escrow_fee": 650}, "hoa": True}
        C, _ = run(R)
        self.assertNotIn("transfer_tax", {r["key"] for r in C["net"]["rows"]})
        self.assertIn("estoppel", {r["key"] for r in C["net"]["rows"]})
        self.assertEqual(row(C, "title_fees")["amounts"][0], -650)
        self.assertFalse(C["net"]["standard_terms"])

    def test_preliminary(self):
        """No state, a Stellar export: national estimates, Preliminary, and what Florida would change."""
        R = report()
        for k in ("state", "county"):
            R["subject"].pop(k)
        R["mls"] = "Stellar"
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertEqual(C["state_hint"]["state"], "FL")
        self.assertIn("state_unknown", C["assumption_keys"])
        self.assertIn("0.70%", C["state_hint"]["transfer_tax_label"])
        self.assertNotEqual(C["state_hint"]["transfer_tax_label"], C["state_hint"]["estimate_label"])
        R = report()
        R["preliminary"] = "the tax bill and the roof date are still to be confirmed, so the figures may change."
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertEqual(C["preliminary_reason"], R["preliminary"][0].upper() + R["preliminary"][1:])
        self.assertEqual(run(report())[0]["preliminary_reason"], "")


class Warnings(unittest.TestCase):
    def test_warning_keys(self):
        def edit(path, value):
            def f(R):
                obj = R
                for p in path[:-1]:
                    obj = obj[p]
                obj[path[-1]] = value
            return f

        def no_county(R):
            R["subject"].pop("county")
            R["mls"] = "Stellar"

        cases = [
            ("list_outside_range", edit(("recommendation", "list_price"), 489900)),
            ("expected_above_range", edit(("pricing", "strategies", 2, "expected_sale"), 485000)),
            ("top_nets_more", edit(("pricing", "strategies", 0, "expected_sale"), 470000)),
            ("expected_sale_order", edit(("pricing", "strategies", 0, "expected_sale"), 461000)),
            ("bottom_nets_more", lambda R: R["pricing"].pop("competing_offer_upside")),
            ("range_wide", lambda R: R["recommendation"].update(low=400000, high=520000)),
            ("range_one_comp", lambda R: R["recommendation"].update(low=400000, high=520000)),
            ("no_county", no_county),
        ]
        self.assertEqual(run(report())[0]["warning_keys"], [])
        for key, change in cases:
            with self.subTest(key):
                R = report()
                change(R)
                C, _ = run(R)
                self.assertIn(key, C["warning_keys"])
                self.assertEqual(len(C["warnings"]), len(C["warning_keys"]))
        R = report()
        R["recommendation"]["list_price"] = 489900
        self.assertEqual(run(R)[0]["warning_keys"], ["list_outside_range", "list_mismatch"])
        R = report()  # the competing-offer option netting less: no warning without the upside note
        R["pricing"].pop("competing_offer_upside")
        R["pricing"]["strategies"][2].update(expected_sale=452000, seller_credit=10000)
        self.assertNotIn("bottom_nets_more", run(R)[0]["warning_keys"])
        self.assertNotIn("no_county", run(texas(report()))[0]["warning_keys"])

    def test_report_errors(self):
        def above_list(R):
            R["pricing"]["strategies"][0]["expected_sale"] = 485000  # only the competing-offer option may sell above list

        def missing(R):
            del R["recommendation"]["low"]

        def bad_history(R):
            R["listing_history"] = [{"status": "sold", "price": 1}]

        for change, pattern in ((above_list, r"strategies\[0\]"), (missing, ""), (bad_history, r"listing_history\[0\]")):
            with self.subTest(change.__name__):
                R = report()
                change(R)
                with self.assertRaisesRegex(compute.ReportError, pattern):
                    run(R)


class ExpectedSale(unittest.TestCase):
    """List x the recent sale-to-final-list ratio plus the option's credit, to $500, inside the range."""

    def no_typed(self, R=None):
        R = R or report()
        for x in R["pricing"]["strategies"]:
            x.pop("expected_sale")
        return R

    def test_rule(self):
        R = self.no_typed()
        C, homes = run(R)
        ratio = C["expected_sale_basis"]["ratio"]
        top, rec, low = C["strategies"]
        floor = R["recommendation"]["low"]
        for x, cap in ((rec, rec["list_price"]), (low, R["recommendation"]["high"])):  # the last is the competing option
            rule = round((x["list_price"] * ratio + x["seller_credit"]) / 500) * 500
            self.assertEqual(x["expected_sale"], min(max(rule, floor), cap))
            self.assertEqual(x["expected_sale_source"], "rule")
        self.assertEqual(top["expected_sale"], rec["expected_sale"])  # a higher price buys time, not a higher sale
        again, _ = run(R)  # render.py runs compute once per format: the same figures
        self.assertEqual([x["expected_sale"] for x in again["strategies"]], [x["expected_sale"] for x in C["strategies"]])
        R["summary_page"]["expected_sale"] = "Upper $380,000s to about $390,000"  # a typed phrase is never shown
        C, _ = run(R)
        self.assertIn(rec["expected_sale_display"], C["recommendation"]["expected_sale"])
        doc, _ = seller_render.build_html(R, C, homes, AGENT)
        self.assertNotIn("Upper $380,000s", doc)
        R = report()
        R["pricing"]["strategies"][2].pop("expected_sale")  # a typed figure is the agent's own
        self.assertEqual([x["expected_sale_source"] for x in run(R)[0]["strategies"]], ["agent", "agent", "rule"])

    def test_caps_floor_and_assumed_ratio(self):
        R = texas(self.no_typed())
        R["market"]["sale_to_list"] = 1.05  # a hot market's ratio: still never above list (but the last) or the range
        C, _ = run(R)
        self.assertEqual(C["expected_sale_basis"]["source"], "report")
        for i, x in enumerate(C["strategies"]):
            self.assertLessEqual(x["expected_sale"], R["recommendation"]["high"])
            if i < 2:
                self.assertLessEqual(x["expected_sale"], x["list_price"])
        C, _ = run(texas(self.no_typed()))
        self.assertEqual(C["expected_sale_basis"]["source"], "assumed")
        self.assertIn("expected_sale_ratio", C["assumption_keys"])
        R = tanager()
        C, _ = run(R)
        self.assertEqual([x["expected_sale"] for x in C["strategies"]], [384500, 384500, 380000])  # the last floored
        self.assertNotIn("expected_below_range", C["assumption_keys"])
        R["recommendation"].update(low=385000, high=390000)  # narrower than the rule's figure: its bottom
        self.assertEqual([x["expected_sale"] for x in run(R)[0]["strategies"]], [385000, 385000, 385000])

    def test_ratio_from_an_export_that_carries_the_final_list(self):
        """Sold rows with the final list price give the ratio against it; an export that echoes the sale price falls
        back to an assumed 97%."""
        C, _ = run(tanager())
        self.assertEqual(C["expected_sale_basis"]["source"], "assumed")
        market, homes = compute.load_inputs(tanager())
        final = {"790 TANAGER RIDGE DR": 389900, "1012 GROSBEAK CT": 369900, "402 LINNET CIR": 379900}
        for h in homes:
            if h["status"] == "SOLD" and h["address"] in final:
                h["current_price"] = final[h["address"]]
        self.assertTrue(compute.mls.carries_final_list([h for h in homes if h["status"] == "SOLD"]))
        recent = [h for h in homes if h["status"] == "SOLD" and str(h["close_date"]) >= "2026-07-01"]
        want = round(statistics.median((h["close_price"] - (h["seller_paid"] or 0)) / h["current_price"] for h in recent), 4)
        C = compute.compute(tanager(), market, homes)
        self.assertEqual((C["expected_sale_basis"]["source"], C["expected_sale_basis"]["ratio"]), ("export", want))
        self.assertGreater(want, C["handoff"]["market"]["sale_to_original_list_recent"])  # earlier cuts don't count


class ScriptOwnedData(unittest.TestCase):
    """Figures the scripts compute are written as placeholders; a typed figure or a wrong name stops with its path."""

    def test_typed_stats_stop_with_every_problem(self):
        R = report()
        R["summary_page"]["key_stats"][1][0] = "95.2%"
        R["market"]["rows"][2][2] = "30"
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        msg = str(e.exception)
        for part in ("summary_page.key_stats[1][0]", "{sale_to_list_recent}", "market.rows[2][2]", "{days_recent}"):
            self.assertIn(part, msg)
        R = report()
        R["market"]["bullets"][2] = "Only five homes are for sale nearby, about a month and a half of supply."
        with self.assertRaisesRegex(compute.ReportError, r"market\.bullets\[2\].*\{months_supply\}"):
            run(R)
        R["market"]["bullets"][2] = "Buyers have plenty of inventory to choose from."  # no figure: nothing typed
        run(R)
        self.assertEqual((compute.months_text(1.3), compute.months_text(1.0)), ("1.3 months", "1 month"))
        R = report()
        R["comps"]["cards"][0]["adjustments"][0]["kind"] = "vibes"
        with self.assertRaisesRegex(compute.ReportError, r"comps\.cards\[0\]\.adjustments\[0\]\.kind"):
            run(R)
        R = report()
        R["market"]["intro"] = "Homes sold since August took longer to sell than in the spring."
        with self.assertRaisesRegex(compute.ReportError, r"market\.intro.*\{split_month\}"):
            run(R)
        R["market"]["intro"] = "Homes sold since {split_month} took longer to sell than in the spring."
        R["comps"]["time_adjustment"]["cutoff"] = "2026-08-01"
        R["comps"]["method_note"] = "About 1% per quarter off sales from before August, since prices softened."
        R["comps"]["intro"] = "Sales from before August are adjusted down for the softer market."
        R["summary_page"]["why"][0] = "The home has sat since January without an offer."  # not a period boundary
        self.assertEqual(run(R)[0]["placeholders"]["split_month"], "July")

    def test_market_table_and_stats_come_from_the_export(self):
        R = report_with_deck()
        R["market"].pop("rows"), R["market"].pop("columns"), R["summary_page"].pop("key_stats")
        R["deck"].pop("market_stats")
        C, homes = run(R)
        n = C["market_numbers"]
        self.assertEqual(C["market_table"]["columns"], ["", "April–June", "July–September"])
        self.assertIn([n["sale_to_list_early"], n["sale_to_list_recent"]], [r[1:] for r in C["market_table"]["rows"]])
        self.assertEqual(C["key_stats"][1][0], n["sale_to_list_recent"])
        D = deck.deck_data(R, C, homes, AGENT, compute.labels(R), "footer")
        self.assertEqual(D["content"]["market_stats"][0][1:3], [n["sale_to_list_early"], n["sale_to_list_recent"]])

    def test_launch_plan_and_date(self):
        R = report_with_deck()
        R["deck"]["launch_plan"].append(["Professional Staging", "A stager furnishes every room", "staging"])
        with self.assertRaisesRegex(compute.ReportError, r"deck\.launch_plan\[\d\]"):
            run(R)
        R = tanager()
        plan = R["deck"]["launch_plan"]
        plan[3][0], plan[4][0] = "Seller-Credit Budget", "3-Week Review"
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        self.assertIn("deck.launch_plan[3]", str(e.exception))
        self.assertIn("deck.launch_plan[4]", str(e.exception))
        plan[3][0], plan[4][0] = "Decide On A Seller Credit Budget", "agree on the review point!"  # trivial differences
        run(R)
        self.assertTrue(compute.same_step("Gather Kitchen Records", "Gather the kitchen records."))
        self.assertFalse(compute.same_step("Kitchen Records", "Gather the kitchen records."))
        R = tanager()
        R["deck"]["timeline"][2] = ["Mid-October", "Go live at {list_price}"]
        with self.assertRaisesRegex(compute.ReportError, r"deck\.timeline\[2\]\[0\]"):
            run(R)
        R["deck"]["timeline"][2] = ["{launch_when}", "Go live at {list_price}"]
        R["summary_page"]["next_step"] = "Go live within about three weeks."
        with self.assertRaisesRegex(compute.ReportError, r"summary_page\.next_step"):
            run(R)
        R["summary_page"]["next_step"] = "Go live in {launch_weeks}."
        C, _ = run(R)
        self.assertEqual((C["launch"]["when"], C["placeholders"]["launch_weeks"]), ("early October", "about two weeks"))
        R["launch_date"] = "2026-10-15"
        self.assertEqual(run(R)[0]["placeholders"]["launch_when"], "mid-October")

    def test_deck_claims_are_checked(self):
        R = tanager()
        card(R, "818 Tanager Ridge Dr")["adjustments"][0]["amount"] = 7100
        R["deck"]["comp_lines"]["818 Tanager Ridge Dr"] = "Strongest match; your street"
        with self.assertRaisesRegex(compute.ReportError, r'deck\.comp_lines\["818 Tanager Ridge Dr"\].*790 Tanager Ridge Dr'):
            run(R)
        R["deck"]["comp_lines"]["818 Tanager Ridge Dr"] = "Your street; 12 days"
        C, _ = run(R)
        self.assertEqual(R["comps"]["cards"][C["strongest_comp"]]["address"], "790 Tanager Ridge Dr")
        R = report_with_deck()
        self.assertNotIn("driver_amount", run(R)[0]["warning_keys"])
        R["deck"]["value_drivers"][1][1] = "Worth about $25,000 against similar homes without one."
        self.assertEqual(run(R)[0]["warning_keys"].count("driver_amount"), 1)
        R["deck"]["value_drivers"][1][1] = "Worth $30,000 to $45,000 against the partly updated sales."
        self.assertNotIn("driver_amount", run(R)[0]["warning_keys"])


class Placeholders(unittest.TestCase):
    def test_fill_and_unknown_names(self):
        R = report()
        R["comps"]["summary_paragraph"] = "From {adjusted_min} to {adjusted_max}, median {median_adjusted}; {net_spread_about}."
        C, homes = run(R)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        doc, _ = seller_render.build_html(R, C, homes, AGENT)
        for k in ("adjusted_min", "adjusted_max", "median_adjusted"):
            self.assertIn(C["placeholders"][k], doc)
        self.assertNotIn("{median_adjusted}", doc)
        R["means"] = ["A sale at {typo_price} would appraise.", "It has sat at {current_price}.",
                      "It expired at {failed_price}."]  # neither a reprice nor a relist
        C, _ = run(R)
        self.assertEqual(C["warning_keys"].count("unfilled_placeholder"), 3)
        self.assertIn("$.means[0]", C["warnings"][C["warning_keys"].index("unfilled_placeholder")])
        R = reprice()
        R["means"] = ["It has sat at {current_price}."]
        C, _ = run(R)
        self.assertNotIn("unfilled_placeholder", C["warning_keys"])
        self.assertEqual(C["placeholders"]["current_price"], "$479,900")
        R = report()
        R["as_of"] = "2026-09-26"
        self.assertEqual(run(R)[0]["data_source"]["as_of_display"], "September 26, 2026")

    def test_adjusted_values_round_to_100(self):
        """Adjusted values show to $100 in placeholders, the table and cards; the math stays exact."""
        R = report()
        R["comps"]["cards"][4]["adjustments"][1]["amount"] = -1200
        C, homes = run(R)
        exact = [c["adjusted"] for c in R["comps"]["cards"]]
        self.assertTrue(any(v % 100 for v in exact))
        self.assertEqual(C["adjusted_min"], min(exact))
        for v in [C["placeholders"][k] for k in ("adjusted_min", "adjusted_max", "median_adjusted")] + [
                r["adjusted_display"] for r in C["comps_table"]]:
            self.assertTrue(v.endswith("00"), v)
        doc, _ = seller_render.build_html(R, C, homes, AGENT)
        for v in exact:
            if v % 100:
                self.assertNotIn(compute.money(v), doc)
                self.assertIn(compute.money(v, 100), doc)
        R = report()
        R["comps"]["cards"] = R["comps"]["cards"][:4]  # an even count's median is rounded too
        C, _ = run(R)
        self.assertEqual(C["median_adjusted_display"], compute.money(C["median_adjusted"], 100))


def resolve(C, path):
    v = C
    for part in path.split("."):
        v = v[part]
    return v


class ChatTemplate(unittest.TestCase):
    """The chat template reads compute.py's output alone, on the same basis as page 1."""

    def test_every_template_path_is_in_compute_output(self):
        with open(os.path.join(SKILL, "assets", "seller-cma-template.md")) as f:
            text = f.read()
        self.assertNotIn("recommendation.paragraph", text)  # the filled copy, never report.json's
        C, _ = run(report())
        paths = ["subject.address", "preliminary_reason", "recommendation.list_price_display", "recommendation.range_display",
                 "recommendation.expected_sale", "summary_page.headline", "recommendation_paragraph", "summary_page.why",
                 "expected_sale_basis.note", "median_adjusted_display", "comps_table", "options_summary.net_header",
                 "net.incomplete", "options_summary.note", "payments.per_10k_display", "net.notes", "net_spread_about",
                 "payments.basis_note", "payments.flood.annual", "payments.flood.required", "first_steps_heading",
                 "summary_page.first_steps", "summary_page.next_step", "data_source.as_of_display"]
        for p in paths:
            self.assertIn(p, text)
            resolve(C, p)
        for field in ("net_after_holding_display", "seller_paid_display", "reprice.stay_index"):
            self.assertIn(field, text)
        for p in ("recommendation_paragraph", "summary_page"):
            self.assertNotRegex(json.dumps(resolve(C, p)), r"\{(median_adjusted|list_price|low|high|per_10k)\}")
        self.assertTrue(all(len(step) == 2 for step in C["summary_page"]["first_steps"]))  # [heading, detail]
        self.assertIn("{{summary_page.first_steps[0][0]}}", text)

    def test_options_summary_by_basis(self):
        L = compute.labels(report())
        for costs, note in (({}, "sum_options_note_holding"), ({"mortgage_payoff": 0}, "sum_options_note_free_holding"),
                            ({"mortgage_payoff": 210000}, "sum_options_note_cash_holding")):
            with self.subTest(costs=costs):
                R = report()
                R["costs"].update(costs)
                C, _ = run(R)
                self.assertEqual(C["options_summary"]["net_header"], L("th_est_net"))
                self.assertTrue(C["options_summary"]["note"].startswith(L(note)))
        C["net_basis"] = "net"  # no holding costs, with a payoff: the column is the net sheet's cash at closing
        self.assertEqual(compute.options_summary(C, L)["net_header"], L("th_est_cash"))
        self.assertTrue(compute.options_summary(C, L)["note"].startswith(L("sum_options_note_cash")))


if __name__ == "__main__":
    unittest.main()
