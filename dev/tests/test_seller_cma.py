"""seller-cma compute.py rules: the pricing stance and the options it sets, costs and nets, one closing per option,
buyer payments, warnings, the expected-sale rule, the judgment-only schema, other markets, the handoff and the chat
template.

The nets, payments and keys of the unmodified fixtures are pinned by golden (dev/golden/seller-cma/); these tests change
an input and check the rule. The shared helpers here (report, run, row, texas, tanager, reprice, card, AGENT) are
imported by the other test_seller_cma_* files, with the modules loaded here (one copy, so ReportError and DeckError
match).
"""
import contextlib
import copy
import io
import json
import os
import re
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
    sale price as the current price, a July 1 market split, the seller's stated $171,500 payoff and a December 18
    closing goal."""
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
    R["comps"]["condition_values"] = {"original": 0, "kitchen_only": 15000, "full_renovation": 45000}  # the agent's
    R.pop("export")
    R["buyer_payment"].pop("district")
    R["buyer_payment"].update(school_mills=9.5, total_mills=19.0)
    return R


def reprice(current=479900):
    """The agent's own listing at `current`, 60 days on market: Stay at Current Price (the agent's own figures for it)
    plus cuts."""
    R = report()
    R["pricing"]["options"] = {"stay": {"expected_sale": 458000, "time": "2–4 months", "seller_credit": 10000,
                                        "note": "Has sat without an offer"}}
    R["reprice"] = {"current_price": current, "days_on_market": 60}
    return R


def card(C, address):
    return next(c for c in C["comps"]["cards"] if c["address"] == address)


def stops(test, R, pattern):
    with test.assertRaisesRegex(compute.ReportError, pattern):
        run(R)


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
            self.assertNotIn("_homes", result)

    def test_compute_never_changes_its_input(self):
        for R in (report_with_deck(), tanager(), reprice()):
            before = copy.deepcopy(R)
            run(R)
            self.assertEqual(R, before)


class Stance(unittest.TestCase):
    """The model picks a pricing stance; the script turns it into the list price and the options, by rule."""

    def test_suggest_stance_thresholds(self):
        cases = (({}, "market"), ({"months_supply": 6}, "draw_offers"), ({"months_supply": 5.9}, "market"),
                 ({"active_share_with_price_cut": 0.40}, "draw_offers"), ({"active_share_with_price_cut": 0.39}, "market"),
                 ({"sale_to_final_list_recent": 0.969}, "draw_offers"), ({"sale_to_final_list_recent": 0.97}, "market"),
                 ({"months_supply": 2.9, "sale_to_final_list_recent": 1.0}, "premium"),
                 ({"months_supply": 3.0, "sale_to_final_list_recent": 1.0}, "market"),
                 ({"months_supply": 2.9, "sale_to_final_list_recent": 0.999}, "market"),
                 ({"months_supply": 2.9}, "market"),
                 ({"months_supply": 2.0, "sale_to_final_list_recent": 1.02, "active_share_with_price_cut": 0.5}, "draw_offers"))
        for stats, want in cases:
            with self.subTest(stats=stats):
                self.assertEqual(compute.cma.suggest_stance(stats)[0], want)
        hot = {"months_supply": 1.5, "sale_to_final_list_recent": 1.02}
        self.assertEqual(compute.cma.suggest_stance(hot, failed=True)[0], "market")  # a reprice or relist: never premium

    def test_list_price_at_snaps_to_a_bracket_inside_the_range(self):
        at, bracket = compute.cma.list_price_at, compute.cma.bracket_price
        for point, low, high, want in ((467000, 455000, 480000, 464900), (467500, 455000, 480000, 469900),
                                       (455500, 455000, 480000, 459900), (479600, 455000, 480000, 479900),
                                       (1236000, 1200000, 1270000, 1239000), (1004000, 970000, 1030000, 999000),
                                       (456000, 455000, 457000, 456000)):  # narrower than a step: the point itself
            with self.subTest(point=point):
                self.assertEqual(at(point, low, high), want)
        self.assertEqual((bracket(474900, "down"), bracket(474000, "down"), bracket(465000, "up"), bracket(469900, "up")),
                         (474900, 469900, 469900, 469900))
        self.assertEqual(bracket(1255000, "down"), 1249000)

    def test_each_stance_sets_the_price_and_the_options(self):
        R = report()
        low, high = run(R)[0]["recommendation"]["low"], run(R)[0]["recommendation"]["high"]
        prices = {}
        for stance in compute.cma.STANCES:
            with self.subTest(stance=stance):
                R["pricing"]["stance"] = stance
                C, _ = run(R)
                rec = C["recommendation"]["list_price"]
                share = compute.cma.STANCE_SHARE[stance]
                self.assertEqual(rec, compute.cma.list_price_at(low + share * (high - low), low, high))
                self.assertEqual(C["stance"]["value"], stance)
                listed = [x["list_price"] for x in C["strategies"]]
                self.assertEqual(listed, sorted(listed, reverse=True))
                self.assertTrue(all(a - b > 0.01 * b for a, b in zip(listed, listed[1:])))
                self.assertTrue(all(low <= p <= high for p in listed))
                self.assertEqual([x["list_price"] for x in run(R)[0]["strategies"]], listed)  # the same pick, the same
                prices[stance] = rec
        self.assertLess(prices["draw_offers"], prices["market"])
        self.assertLess(prices["market"], prices["premium"])

    def test_the_suggestion_when_left_out_and_a_reason_when_it_differs(self):
        R = report()
        R["pricing"].pop("stance")
        R["pricing"].pop("stance_reason")
        C, _ = run(R)
        self.assertEqual(C["stance"]["value"], C["stance"]["suggested"])
        self.assertFalse(C["stance"]["differs"])
        C, _ = run(report())
        self.assertTrue(C["stance"]["differs"])
        self.assertIn(C["stance"]["name"], C["stance"]["line"])
        self.assertIn(C["stance"]["line"], seller_render.build_html(C, AGENT).replace("&#x27;", "'"))

    def test_the_agents_own_price(self):
        R = report()
        R["price_override"] = {"list_price": 472500, "reason": "The agent wants the price in the search most buyers use."}
        C, _ = run(R)
        self.assertEqual(C["recommendation"]["list_price"], 472500)
        self.assertTrue(C["stance"]["agent_price"] and C["recommendation"]["price_override"])
        self.assertIn(C["stance"]["rule_price_display"], C["stance"]["line"])
        self.assertEqual(C["handoff"]["recommended_list_price"], 472500)
        listed = [x["list_price"] for x in C["strategies"]]
        self.assertIn(472500, listed)
        self.assertTrue(all(a - b > 0.01 * b for a, b in zip(listed, listed[1:])))

    def test_the_comps_stage_prints_the_suggestion_and_each_stances_price(self):
        R = report()
        for k in ("pricing", "costs", "buyer_payment"):
            R.pop(k)
        C = compute.run(R)
        self.assertEqual(C["stage"], "comps")
        self.assertIn(C["stance"]["suggested"], compute.cma.STANCES)
        R2 = report()
        for stance in compute.cma.STANCES:
            R2["pricing"]["stance"] = stance
            self.assertEqual(C["stance"]["prices"][stance]["list_price"], run(R2)[0]["recommendation"]["list_price"])


class Costs(unittest.TestCase):
    def test_agent_terms_replace_the_defaults(self):
        R = report()
        R["costs"] = {"listing_fee_pct": 0.03, "buyer_broker_fee_pct": 0.02}
        C, _ = run(R)
        sale = C["strategies"][0]["expected_sale"]
        self.assertEqual((row(C, "listing_fee")["amounts"][0], row(C, "buyer_broker_fee")["amounts"][0]),
                         (-compute.fmt.half_up(0.03 * sale), -compute.fmt.half_up(0.02 * sale)))
        self.assertNotIn("commission_default", C["assumption_keys"])
        R["costs"] = {"listing_fee_pct": 0.025, "buyer_broker_fee_pct": 0}
        self.assertNotIn("buyer_broker_fee", {r["key"] for r in run(R)[0]["net"]["rows"]})
        R["costs"] = {"listing_fee_pct": 2.5}  # *_pct fields are fractions everywhere (0.025)
        with self.assertRaises(compute.ReportError):
            run(R)
        R = report()
        R["costs"] = {"title_fees": {"settlement_fee": 850, "title_search": 200}}
        C, _ = run(R)
        self.assertEqual(row(C, "title_fees")["amounts"][0], -1050)
        self.assertNotIn("title_fees", C["note_keys"])

    def test_default_brokerage_is_unlabeled_and_still_asked(self):
        """A default commission is a default: 2.5% + 2.5%, rounded once, no label beside a net; the reply asks."""
        R = report()
        R["costs"] = {}
        C, _ = run(R)
        self.assertEqual(row(C, "listing_fee")["amounts"][1],
                         -compute.fmt.half_up(0.025 * C["strategies"][1]["expected_sale"]))
        self.assertFalse(C["net"]["incomplete"])
        self.assertIn("commission_default", C["assumption_keys"])
        self.assertNotIn("commission_default", [k for k in C["note_keys"] if C["notes"] and k in C["chat_notes"]])
        self.assertEqual(C["notes"].count(compute.finance.COMMISSION_NOTE), 1)

    def test_columns_add_up_whatever_the_credits(self):
        """A credit in only some options keeps its row, in either order, and every column adds up from its lines."""
        for credits in ((0, 10000, 0), (10000, 0, 0), (0, 0, 5000)):
            with self.subTest(credits=credits):
                R = report()
                R["pricing"]["options"] = {role: {"seller_credit": c} for role, c in
                                           zip(("top", "recommended", "competing"), credits)}
                C, _ = run(R)
                self.assertEqual(row(C, "credit")["amounts"], [-c for c in credits])
                self.assertEqual(row(C, "credit")["display"].count(compute.fmt.EMPTY), credits.count(0))
                lines = [r for r in C["net"]["rows"] if r["kind"] == "line"]
                for i, total in enumerate(C["net"]["totals"]):
                    self.assertEqual(sum(r["amounts"][i] for r in lines if r["key"] != "holding"), total)
                    self.assertEqual(C["net"]["after_holding"][i], total + C["net"]["holding"][i])

    def test_payoff_hoa_and_other_costs(self):
        R = report()
        base = run(R)[0]["strategies"][0]["net"]
        R["costs"].update({"mortgage_payoff": 210000, "hoa": True, "other": [{"label": "Survey", "amount": 450}]})
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"])
        self.assertEqual(row(C, "estoppel")["amounts"][0], -299)
        self.assertEqual(row(C, "other")["amounts"][0], -450)
        self.assertEqual(C["strategies"][0]["net"], base - 299 - 450 - 210000)
        self.assertEqual([k for k in C["note_keys"] if k == "payoff"], ["payoff"])
        R["costs"]["mortgage_payoff"] = 0
        C, _ = run(R)
        self.assertTrue(C["net"]["cash_at_closing"] and C["net"]["no_mortgage"])
        self.assertNotIn("payoff", {r["key"] for r in C["net"]["rows"]})
        R = tanager()
        R["costs"].pop("mortgage_payoff")
        R["costs"]["mortgage_balance"] = 171500
        C, _ = run(R)
        self.assertEqual(row(C, "payoff")["amounts"][0], -compute.fmt.half_up(171500 * (1 + 0.045 / 12)))
        self.assertTrue(C["net"]["payoff_estimated"])
        self.assertIn("payoff", C["assumption_keys"])
        R = report()
        R["costs"].update(mortgage_balance=200000, mortgage_rate=6)
        self.assertEqual(row(run(R)[0], "payoff")["amounts"][0], -201000)


class OneClosing(unittest.TestCase):
    """Each option has one closing date; its tax proration and its holding costs both run to it."""

    def test_proration_and_holding_run_to_the_same_closing(self):
        R = tanager()
        C, _ = run(R)
        as_of = date.fromisoformat(R["as_of"])
        closings = [date.fromisoformat(x["closing"]) for x in C["strategies"]]
        self.assertEqual(closings[1:], [date(2026, 12, 18)])  # the seller's goal when the time allows it
        self.assertGreater(closings[0], date(2026, 12, 18))  # a slower option can't close by it
        self.assertEqual(row(C, "closing")["display"], [compute.fmt.date_short(d) for d in closings])
        monthly = C["net"]["monthly"]
        for x, d, hold in zip(C["strategies"], closings, row(C, "holding")["amounts"]):
            self.assertEqual(x["hold_months"], round((d - as_of).days / compute.MONTH_DAYS, 2))
            self.assertAlmostEqual(-hold, monthly * x["hold_months"], delta=monthly * 0.01 + 1)
        tax = row(C, "tax_proration")["amounts"]
        self.assertEqual(tax[1], -compute.fmt.half_up(3505.61 * 0.96 * (date(2026, 12, 18) - date(2026, 1, 1)).days / 365))
        self.assertEqual(row(C, "tax_prior_year")["display"][1:], [compute.fmt.EMPTY])  # only the 2027 closing
        self.assertIn("tax", C["assumption_keys"])

    def test_launch_date_moves_every_closing_it_sets(self):
        R = report()
        R["costs"]["annual_tax"] = 6000
        a = [x["closing"] for x in run(R)[0]["strategies"]]
        R["launch_date"] = "2026-10-30"
        C, _ = run(R)
        b = [x["closing"] for x in C["strategies"]]
        self.assertTrue(all(y > x for x, y in zip(a, b)))
        self.assertEqual(C["launch"]["date"], "2026-10-30")
        self.assertIn(compute.fmt.date_long("2026-10-30"), C["summary"]["launch_line"])
        R["pricing"]["options"] = {role: {"time": "when the market allows"}  # nothing to date it by
                                   for role in ("top", "recommended", "competing")}
        C, _ = run(R)
        self.assertIn("tax_no_closing_date", C["warning_keys"])
        self.assertIsNone(C["net"]["after_holding"])

    def test_late_year_closing_assumes_the_bill_unpaid(self):
        R = report()
        R["costs"].update(annual_tax=6000, expected_closing_date="2026-12-15")
        C, _ = run(R)
        self.assertIn("tax", C["assumption_keys"])
        self.assertLess(row(C, "tax_proration")["amounts"][1], 0)  # a cost to the seller
        R["costs"]["current_tax_bill_paid"] = True
        C, _ = run(R)
        self.assertGreater(row(C, "tax_proration")["amounts"][1], 0)  # the buyer credits back Dec 15 to Dec 31


class HoldingCosts(unittest.TestCase):
    def test_net_after_holding(self):
        R = report()
        R["costs"]["mortgage_payoff"] = 210000
        C, _ = run(R)
        hold = row(C, "holding")["amounts"]
        self.assertTrue(hold[0] < hold[1] < hold[2] < 0)  # slower options hold the home longer
        self.assertEqual([x["net_after_holding"] for x in C["strategies"]], C["net"]["after_holding"])
        self.assertEqual(C["net_spread"], max(C["net"]["after_holding"]) - min(C["net"]["after_holding"]))
        nets = [x["net_after_holding"] for x in C["strategies"]]
        ri = C["recommended_index"]
        self.assertEqual([x["net_vs_recommended"] for x in C["strategies"]], [v - nets[ri] for v in nets])
        self.assertIn("holding", C["assumption_keys"])
        R["costs"]["mortgage_rate"] = 6.25
        C2, _ = run(R)
        self.assertGreater(C2["net"]["monthly"], C["net"]["monthly"])

    def test_rounded_differences(self):
        for value, about in ((6796, "$6,800"), (-3976, "$4,000"), (2240, "$2,200"), (3678, "$3,700"),
                             (12345, "$12,500"), (61400, "$61,000")):
            self.assertEqual(compute.about(value), "about " + about)
        C, _ = run(report())
        self.assertEqual(C["strategies"][C["recommended_index"]]["net_vs_recommended_about"], "")
        self.assertEqual(C["net_spread_about"], compute.about(C["net_spread"]))


class BuyerPayments(unittest.TestCase):
    def test_lines_add_up_and_a_flood_quote_counts(self):
        C, _ = run(report())
        for r in C["payments"]["rows"]:
            self.assertEqual(sum(a for _, _, a in r["lines"]), r["payment"])
        R = report()
        R["buyer_payment"]["flood_insurance_annual"] = 1200
        Q, _ = run(R)
        for a, b in zip(C["payments"]["rows"], Q["payments"]["rows"]):
            self.assertEqual(b["payment"] - a["payment"], 100)
        R = texas(report())
        R["buyer_payment"].pop("total_mills")
        C, _ = run(R)
        self.assertIn("tax_estimated", C["warning_keys"])

    def test_homestead_only_in_florida(self):
        R = texas(report())
        default = run(R)[0]["payments"]
        self.assertFalse(default["homestead_applied"])
        self.assertIsNone(default["flood"]["required"])  # no Citizens rule outside Florida
        R["buyer_payment"]["homestead"] = False
        self.assertEqual([r["payment"] for r in default["rows"]], [r["payment"] for r in run(R)[0]["payments"]["rows"]])
        R = report()  # Florida: the exemption lowers the payment
        home = run(R)[0]["payments"]["rows"]
        R["buyer_payment"]["homestead"] = False
        self.assertGreater(run(R)[0]["payments"]["rows"][0]["payment"], home[0]["payment"])


class OtherMarkets(unittest.TestCase):
    def test_texas_uses_estimates_never_florida_numbers(self):
        C, _ = run(texas(report()))
        self.assertFalse(C["preliminary"])
        self.assertEqual({r["key"] for r in C["net"]["rows"]},
                         {"sale", "closing", "listing_fee", "buyer_broker_fee", "owner_title", "title_fees", "credit",
                          "total", "holding", "after_holding"})  # no transfer tax in Texas, never Florida's stamps
        self.assertEqual(C["net"]["missing"], [])
        self.assertLessEqual({"commission_default", "national", "payment"}, set(C["assumption_keys"]))
        R = texas(report())
        R["subject"].update(state="GA", county="Fulton", city="Atlanta")  # a state that taxes deeds
        self.assertIn("transfer_tax", {r["key"] for r in run(R)[0]["net"]["rows"]})

    def test_preliminary(self):
        R = report()
        for k in ("state", "county"):
            R["subject"].pop(k)
        R["mls"] = "Stellar"
        R["comps"]["condition_values"] = {"original": 0, "kitchen_only": 15000, "full_renovation": 45000}
        C, _ = run(R)
        self.assertTrue(C["preliminary"])
        self.assertEqual(C["state_hint"]["state"], "FL")
        self.assertIn("state_unknown", C["assumption_keys"])
        self.assertIn("0.70%", C["state_hint"]["transfer_tax_label"])
        R = report()
        R["preliminary"] = "the tax bill and the roof date are still to be confirmed, so the figures may change."
        C, _ = run(R)
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

        def agent_option(role, **values):
            return lambda R: R["pricing"].__setitem__("options", {role: values})

        cases = [  # only the agent's own figures can trip these: the script's are inside the rules by construction
            ("list_outside_range", lambda R: R.__setitem__("price_override", {"list_price": 489900,
                                                                               "reason": "The agent's own price."})),
            ("expected_above_range", agent_option("competing", expected_sale=485000)),
            ("top_nets_more", agent_option("top", expected_sale=474000)),
            ("expected_sale_order", agent_option("top", expected_sale=461000)),
            ("range_wide", lambda R: R.__setitem__("range_override", {"low": 400000, "high": 520000,
                                                                       "reason": "The agent's own range."})),
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

    def test_report_errors(self):
        def above_list(R):
            R["pricing"]["options"] = {"top": {"expected_sale": 485000}}

        def typed_price(R):
            R["recommendation"]["list_price"] = 469900  # the stance sets it, or the agent's price_override

        def typed_options(R):
            R["pricing"]["strategies"] = [{"list_price": 469900, "time": "3–6 weeks"}]

        def unknown_stance(R):
            R["pricing"]["stance"] = "aggressive"

        def no_reason(R):
            R["pricing"].update(stance="premium", stance_reason="")

        def unknown_role(R):
            R["pricing"]["options"] = {"bottom": {"time": "1–3 weeks"}}

        def override_no_reason(R):
            R["price_override"] = {"list_price": 472500}

        def typed_range(R):
            R["recommendation"]["low"] = 455000  # the script sets the range

        def typed_condition(R):
            R["comps"]["cards"][1]["adjustments"].append({"label": "Remodeled Baths", "amount": -10000, "kind": "other"})

        def no_level(R):
            R["subject"]["condition"] = "updated"

        def bad_history(R):
            R["listing_history"] = [{"status": "sold", "price": 1}]

        for change, pattern in ((above_list, r"options\.top\.expected_sale"), (typed_price, r"recommendation\.list_price"),
                                (typed_options, r"pricing\.strategies"), (unknown_stance, r"pricing\.stance: 'aggressive'"),
                                (no_reason, r"pricing\.stance_reason"), (unknown_role, r"pricing\.options\.bottom"),
                                (override_no_reason, r"price_override\.reason"), (bad_history, r"listing_history\[0\]"),
                                (typed_range, r"recommendation\.low"), (typed_condition, r"cards\[1\]\.adjustments"),
                                (no_level, r"subject\.condition")):
            with self.subTest(change.__name__):
                R = report()
                change(R)
                stops(self, R, pattern)


class ExpectedSale(unittest.TestCase):
    """List x the recent sale-to-final-list ratio plus the option's credit, to $500, inside the range."""

    def test_rule(self):
        R = report()
        C, _ = run(R)
        ratio = C["expected_sale_basis"]["ratio"]
        top, rec, low = C["strategies"]
        floor = C["recommendation"]["low"]
        for x, cap in ((rec, rec["list_price"]), (low, C["recommendation"]["high"])):
            rule = compute.fmt.half_up(x["list_price"] * ratio + x["seller_credit"], 500)
            self.assertEqual(x["expected_sale"], min(max(rule, floor), cap))
            self.assertEqual(x["expected_sale_source"], "rule")
        self.assertEqual(top["expected_sale"], rec["expected_sale"])  # a higher price buys time, not a higher sale
        self.assertEqual(run(R)[0]["strategies"], C["strategies"])  # the same input, the same figures
        R = report()
        R["pricing"]["options"] = {"top": {"expected_sale": 467000}, "recommended": {"expected_sale": 466000}}
        C, _ = run(R)  # a typed figure is the agent's own
        self.assertEqual([x["expected_sale_source"] for x in C["strategies"]], ["agent", "agent", "rule"])
        self.assertIn("expected_agent", C["note_keys"])

    def test_caps_floor_and_assumed_ratio(self):
        R = texas(report())
        R["market"]["sale_to_list"] = 1.05
        C, _ = run(R)
        self.assertEqual(C["expected_sale_basis"]["source"], "report")
        for i, x in enumerate(C["strategies"]):
            self.assertLessEqual(x["expected_sale"], C["recommendation"]["high"])
            if i < 2:
                self.assertLessEqual(x["expected_sale"], x["list_price"])
        C, _ = run(texas(report()))
        self.assertEqual(C["expected_sale_basis"]["source"], "assumed")
        self.assertIn("expected_sale", C["assumption_keys"])
        R = tanager()  # the rule's figure falls under the range: each option expects the bottom of it
        C, _ = run(R)
        self.assertEqual({x["expected_sale"] for x in C["strategies"]}, {C["recommendation"]["low"]})
        self.assertTrue(C["expected_sale_basis"]["floored"])
        R["range_override"] = {"low": 385000, "high": 390000, "reason": "The agent's own range."}
        self.assertEqual({x["expected_sale"] for x in run(R)[0]["strategies"]}, {385000})

    def test_ratio_from_an_export_that_carries_the_final_list(self):
        market, homes = compute.load_inputs(tanager())
        final = {"790 TANAGER RIDGE DR": 389900, "1012 GROSBEAK CT": 369900, "402 LINNET CIR": 379900}
        for h in homes:
            if h["status"] == "SOLD" and h["address"] in final:
                h["current_price"] = final[h["address"]]
        recent = [h for h in homes if h["status"] == "SOLD" and str(h["close_date"]) >= "2026-07-01"]
        want = round(statistics.median((h["close_price"] - (h["seller_paid"] or 0)) / h["current_price"] for h in recent), 4)
        C = compute.compute(tanager(), market, homes)
        self.assertEqual((C["expected_sale_basis"]["source"], C["expected_sale_basis"]["ratio"]), ("export", want))


class JudgmentOnly(unittest.TestCase):
    """report.json writes judgment; a figure in it, or a field the script now writes, stops with its path."""

    def test_figures_and_retired_fields_stop_with_every_problem(self):
        R = report_with_deck()
        R["summary_page"]["why"][1] = "Homes now sell about 4% under asking."
        R["comps"]["lean"] = "The summer sales since July sit lower."
        R["competition"]["rows"][0][6] = "Cut from $449,900."
        R["deck"]["comp_lines"][next(iter(R["deck"]["comp_lines"]))] = "Sold in {launch_when}"
        R["recommendation"]["paragraph"] = "Priced well."
        R["comps"]["cards"][0]["meta"] = "Sold $1"
        R["pricing"]["stance_reason"] = "Sales here close at 99% of asking."
        R["pricing"]["options"] = {"top": {"note": "Sits for 60 days"}}
        with self.assertRaises(compute.ReportError) as e:
            run(R)
        msg = str(e.exception)
        for part in ("summary_page.why[1]", "comps.lean", "competition.rows[0][6]", "deck.comp_lines.",
                     "recommendation.paragraph", "comps.cards[0].meta", "pricing.stance_reason",
                     "pricing.options.top.note"):
            self.assertIn(part, msg)
        R = report()
        R["prep"]["items"][0] = "<strong>Document the roof.</strong> Permits."
        stops(self, R, r"prep\.items")
        R = report()
        R["comps"]["cards"][0]["adjustments"][0]["kind"] = "vibes"
        stops(self, R, r"comps\.cards\[0\]\.adjustments\[0\]\.kind")

    def test_the_script_states_the_facts(self):
        C, _ = run(tanager())
        rec, cmp_ = C["recommendation"], C["comps"]
        for figure in (rec["range_display"].split("–")[0], C["median_adjusted_display"], rec["list_price_display"]):
            self.assertIn(figure, rec["line"])
        best = cmp_["strongest"]["index"]
        self.assertTrue(cmp_["cards"][best]["strongest"])
        self.assertEqual(sum(c["strongest"] for c in cmp_["cards"]), 1)
        highest = max(C["comps"]["cards"], key=lambda c: c["sold_price"])
        self.assertIn(highest["address"], cmp_["highest_line"])
        self.assertIn(compute.money(highest["sold_price"]), cmp_["highest_line"])
        self.assertEqual(C["summary"]["first_steps"], [[it["heading"], it["short"]] for it in C["prep"]["items"][:3]])


class Notes(unittest.TestCase):
    def test_each_note_once_and_never_in_a_label(self):
        for R in (report(), tanager(), texas(report()), reprice()):
            C, _ = run(R)
            self.assertEqual(len(C["note_keys"]), len(set(C["note_keys"])))
            N = compute.notes.Notes()
            for i, text in enumerate(C["assumptions"] + C["chat_notes"]):
                N.add(f"n{i}", text)
            self.assertEqual(N.label_problems(compute.all_labels(C)), [])
            doc = seller_render.build_html(C, AGENT)
            text = re.sub(r"<[^>]+>", " ", doc)
            self.assertEqual(text.count("not an appraisal"), 1)
            self.assertLessEqual(text.lower().count("not guarantees"), 1)


def resolve(C, path):
    v = C
    for part in path.split("."):
        v = v[int(part)] if isinstance(v, list) else v[part]
    return v


class ChatTemplate(unittest.TestCase):
    """The chat template reads compute.py's output alone, on the same basis as page 1."""

    def test_every_template_path_is_in_compute_output(self):
        with open(os.path.join(SKILL, "assets", "seller-cma-template.md")) as f:
            text = f.read()
        C, _ = run(report())
        paths = set(re.findall(r"\b([a-z_]+(?:\.[a-z_0-9]+)+)", re.sub(r"\[(\d+)\]", r".\1", text)))
        paths -= {"seller.cma"}
        for p in sorted(paths):
            with self.subTest(p):
                resolve(C, p)
        for field in ("net_after_holding_display", "seller_paid_display", "price_history", "history_line"):
            self.assertIn(field, text)


if __name__ == "__main__":
    unittest.main()
