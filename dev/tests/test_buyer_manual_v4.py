"""Fixes from the fourth manual round (sources/Results_v4, 2315 Kestrel Point Ct): the buyer CMA's payment table,
pagination, headings, ranges, chart labels and market table; the offer strategy's appraisal protection, status colors,
minimum concession ask, wording, and the offer package's dates, order and HOA dues."""
import copy
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

compute, cma_render, cma = load("buyer-cma", "compute", "render", "_shared.cma")
strategy, offer_render, cf = load("buyer-offer-strategy", "strategy", "render", "_shared.contract_forms")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")


def cma_report():
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json")) as f:
        R = json.load(f)
    R["export"] = os.path.join(ROOT, R["export"])
    return R


def kestrel(**buyer):
    """The v4 case: one competing offer, the buyer CMA's range, a 2010 roof and HOA dues (one-competing-reach.json)."""
    with open(os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy", "one-competing-reach.json")) as f:
        d = json.load(f)
    d["buyer"].update(buyer)
    return d


def run(d):
    return strategy.analyze(d, cma=strategy.load_cma(d))


def browser_page(doc, width=730):
    """A Chromium page laid out at print width, as html_to_pdf and cma.paginate measure it."""
    from playwright.sync_api import sync_playwright
    p = sync_playwright().start()
    b = p.chromium.launch()
    pg = b.new_page(viewport={"width": width, "height": 1000})
    pg.set_content(doc, wait_until="load")
    pg.emulate_media(media="print")
    return p, b, pg


CLIPPED = """() => [...document.querySelectorAll('.tbl')].filter(t => t.scrollWidth > t.clientWidth + 1)
  .map(t => (t.querySelector('th, td') || {}).textContent)"""


class PaymentTableFits(unittest.TestCase):
    def test_widest_realistic_headers_fit(self):
        """The payment and credit tables were clipped at the right ("Conventional, 20% Dowr"): their headers wrap now.
        Seven-figure prices and three Assumed scenarios are about the widest a report gets."""
        R = cma_report()
        R["costs"]["payment"]["price"] = 1442000
        R["costs"]["payment"]["scenarios"] = [
            {"label": "Conventional, 5% Down", "type": "conventional", "down_pct": 0.05, "assumed": True},
            {"label": "FHA, 3.5% Down", "type": "fha", "down_pct": 0.035, "assumed": True},
            {"label": "Conventional, 20% Down", "type": "conventional", "down_pct": 0.2, "assumed": True}]
        cs = R["costs"]["credit_scenarios"]
        cs["scenarios"] = [{"price": 1435000, "credit": 0}, {"price": 1445000, "credit": 10000},
                           {"price": 1455000, "credit": 20000}, {"price": 1465000, "credit": 30000}]
        cs.pop("buydown", None)
        market, homes = compute.load_inputs(R)
        C = compute.compute(R, market, homes)
        doc, _ = cma_render.build_html(copy.deepcopy(R), C, homes, {})
        self.assertEqual(doc.count('class="tbl wrap-head"'), 2)
        p, b, pg = browser_page(doc)
        try:
            self.assertEqual(pg.evaluate(CLIPPED), [])
        finally:
            b.close()
            p.stop()


class Pagination(unittest.TestCase):
    def test_a_table_block_runs_on_rather_than_leave_half_a_page(self):
        """Pages 8 to 11 were each about half empty: a table block that doesn't fit with a third of the page or more
        left now runs on (whole rows, header repeated) once its heading, intro and first rows fit."""
        filler = [f"<p>{'Filler text for the page. ' * 30}</p>" for _ in range(4)]  # about half a page
        rows = [[f"Row {i}", "$1,000", "$2,000"] for i in range(24)]  # more than the rest of the page
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


class Wording(unittest.TestCase):
    def setUp(self):
        self.R = cma_report()
        market, self.homes = compute.load_inputs(self.R)
        self.C = compute.compute(self.R, market, self.homes)

    def test_headings_are_title_case(self):
        self.assertEqual(cma_render.title_case("Property taxes will be much higher than the listing shows"),
                         "Property Taxes Will Be Much Higher than the Listing Shows")
        self.assertEqual(cma_render.title_case("2 price cuts since the HOA vote"), "2 Price Cuts Since the HOA Vote")
        R = copy.deepcopy(self.R)
        R["costs"]["taxes"]["heading"] = "your taxes will go up"
        doc, _ = cma_render.build_html(R, self.C, [], {})
        self.assertIn("<h3>Your Taxes Will Go Up</h3>", doc)

    def test_one_range_format(self):
        doc, _ = cma_render.build_html(copy.deepcopy(self.R), self.C, [], {})
        self.assertNotRegex(doc, r"\$[\d,K]+ – \$")  # never a spaced dash between two amounts
        self.assertRegex(doc, r"<b>\$\d+K–\$\d+K</b>")
        self.assertNotIn(" – ", self.C["range"]["display"])

    def test_chart_labels_use_the_printed_address(self):
        sc = {"subject_label": "517 Hickorywood", "callouts": [{"address": "1512 BUTTONBUSH DR", "label": "1512 Buttonbush"}]}
        out = cma_render.chart_labels(sc, {"address": "517 Hickorywood Ave"})
        self.assertEqual(out["subject_label"], "517 Hickorywood Ave")
        self.assertEqual(out["callouts"][0]["label"], "1512 Buttonbush Dr")

    def test_market_table_has_the_median_sale_price(self):
        rows = self.C["market_rows"]
        self.assertEqual(rows[1][0], "Median Sale Price")
        self.assertTrue(all(v.startswith("$") for v in rows[1][1:]))
        doc, _ = cma_render.build_html(copy.deepcopy(self.R), self.C, self.homes, {})
        self.assertIn("Median Sale Price", doc)
        R = copy.deepcopy(self.R)  # a table that already has one isn't given a second
        R["market"]["rows"].insert(1, ["Median Sale Price", "$450,000", "$440,000"])
        self.assertEqual(sum(r[0] == "Median Sale Price" for r in compute.market_rows(R, [1, 2])), 1)
        self.assertEqual(compute.market_rows(R, None), R["market"]["rows"])  # no export: as written

    def test_no_placeholder_wording(self):
        doc, _ = cma_render.build_html(copy.deepcopy(self.R), self.C, self.homes, {})
        self.assertNotIn("placeholder", doc.lower())


class AppraisalProtection(unittest.TestCase):
    def test_rider_f_window_inside_the_deposit_risk_is_named(self):
        """Rider F attached, its window ends a day before the deposit is at risk: the cell names that date, never a dash."""
        r = run(kestrel())
        o = r["O"]["recommended"]
        self.assertIsNone(strategy.appraisal_until(o, r["B"], r["costs"]))
        text = strategy.appraisal_protection(o, r["B"], r["costs"])
        self.assertRegex(text, r"^Until \w{3} \w{3} \d+ \(before the deposit is at risk\)$")
        doc = offer_render.options_html(r, {}, False)
        row = re.search(r"<tr><td>Low-Appraisal Protection</td>(.*?)</tr>", doc).group(1)
        self.assertNotIn("—", row)


class StatusColors(unittest.TestCase):
    def test_brand_panel_and_status_that_agrees(self):
        r = run(kestrel(cash_available=41900))  # At Risk, with a thin cushion
        s = strategy.summary(r)
        self.assertEqual(s["outlook_class"], "risk")
        self.assertEqual(s["reserve_status"], "caution")
        css = offer_render.css("options")
        ctr = re.search(r"\.ctr\{[^}]*\}", css).group(0)
        self.assertIn("var(--brand)", ctr)
        self.assertNotIn("good", ctr)
        doc = offer_render.options_html(r, {}, False)
        self.assertIn('<b class="ct">', doc)  # Left in Reserve in caution, under the thin-cushion line
        self.assertNotIn('class="gt"', doc)
        net = re.search(r'<tr class="total2"><td>Net as the Listing Agent Sees It</td>(.*?)</tr>', doc).group(1)
        self.assertNotIn("worst", net)
        self.assertNotIn("best", net)
        self.assertEqual(next(x for x in s["options"] if x["key"] == "recommended")["status"], "")
        self.assertEqual(strategy.reserve_status(r["B"], 4000), "risk")
        self.assertEqual(strategy.reserve_status(r["B"], 9000), "")


class MinimumConcessionAsk(unittest.TestCase):
    def test_small_ask_rounds_up_when_the_cash_needs_it(self):
        r = run(kestrel())
        conc = r["terms"]["recommended"]["seller_concessions"]
        self.assertTrue(conc == 0 or conc >= strategy.MIN_CONCESSION_ASK)
        B, costs = r["B"], r["costs"]
        t = dict(r["terms"]["recommended"], seller_concessions=0)
        self.assertFalse(strategy.within_limits(B, costs, dict(t, price=445000)))  # $0 would break the reserve here
        self.assertEqual(strategy.meaningful_ask(B, costs, dict(t, price=445000), 500), 1000)

    def test_small_ask_drops_when_every_limit_holds(self):
        r = run(kestrel(cash_available=60000))
        B, costs = r["B"], r["costs"]
        t = dict(r["terms"]["recommended"], seller_concessions=0)
        self.assertTrue(strategy.within_limits(B, costs, t))
        self.assertEqual(strategy.meaningful_ask(B, costs, t, 500), 0)
        self.assertEqual(strategy.meaningful_ask(B, costs, t, 2500), 2500)  # above the minimum: as is

    def test_no_option_asks_under_the_minimum(self):
        for cash in (41000, 41900, 42000, 43000, 45000):
            r = run(kestrel(cash_available=cash))
            for k, t in r["terms"].items():
                c = t.get("seller_concessions", 0)
                self.assertTrue(c == 0 or c >= 1000, (cash, k, c))


class OfferWording(unittest.TestCase):
    def setUp(self):
        self.r = run(kestrel())
        self.doc = offer_render.options_html(self.r, {}, False)
        self.text = re.sub(r"<[^>]+>", " ", self.doc)

    def test_no_stronger_reason_is_plain(self):
        why = strategy.no_stronger_reason(self.r["B"], self.r["terms"]["recommended"])
        self.assertIn("the price is inside the value range, so there's no appraisal gap to cover", why)
        self.assertNotIn("uncovered", why)

    def test_labels_name_what_they_measure(self):
        self.assertIn("Sale to Original List", self.doc)
        self.assertNotIn("Sale-to-List", self.doc)
        self.assertIn("Months of Supply", self.doc)
        self.assertNotIn("Months Supply", self.doc)
        self.assertNotRegex(self.text, r"\bDOM\b")
        self.assertNotIn("At/under", self.text)
        self.assertNotIn("CMA high", self.text)

    def test_market_read_is_one_plain_sentence(self):
        read = next(m for m in strategy.market_check(self.r["B"]) if m["label"] == "Market Read")
        self.assertEqual(read["value"], "Soft")
        self.assertNotIn("secondary", read["note"])
        self.assertNotIn("reads normal", read["note"])
        self.assertTrue(read["note"].endswith("."))
        self.assertNotRegex(read["note"], r"\.\s+[A-Z]")  # one sentence

    def test_dates_and_assumptions(self):
        self.assertNotRegex(self.text, r"\d{4}-\d{2}-\d{2}")
        self.assertIn("buyer CMA, Sep 26, 2026", self.doc)
        ins = next(a["why"] for a in self.r["missing"] if a["field"] == "insurance_annual")
        self.assertEqual(ins.lower().count("estimate"), 1)
        self.assertIn('<th class="c nw">Lower-Cost</th>', self.doc)


class OfferPackage(unittest.TestCase):
    def setUp(self):
        d = kestrel()
        d["property"]["hoa_frequency"] = "quarterly"
        d["property"]["hoa_monthly"] = 35
        self.r = run(d)
        self.W = strategy.worksheet(self.r)

    def test_time_for_acceptance_on_a_business_day(self):
        """The expected acceptance is Sunday Sep 27: the seller's deadline moves to Monday 5:00 PM."""
        row = next(x for x in self.W["rows"] if x["field"] == "Time for Acceptance")
        self.assertEqual(row["entry"], "September 28, 2026, 5:00 PM")

    def test_paragraphs_in_numeric_order(self):
        paras = [x["para"] for x in self.W["rows"]]
        keys = [strategy.para_key((p,)) for p in paras]
        self.assertEqual(keys, sorted(keys))
        self.assertLess(paras.index("2(d)"), paras.index("3"))
        self.assertLess(paras.index("3"), paras.index("8(b)"))

    def test_riders_in_letter_order(self):
        codes = [cf.rider_code(x["rider"]) for x in self.W["riders"]]
        self.assertEqual(codes, ["B", "F", "H", "GG"])
        self.assertEqual(cf.rider_order(["Appraisal Gap Addendum (AGA-1)", "Rider GG", "Rider F", "Rider B"]),
                         ["Rider B", "Rider F", "Rider GG", "Appraisal Gap Addendum (AGA-1)"])

    def test_hoa_dues_as_billed(self):
        b = next(x for x in self.W["riders"] if cf.rider_code(x["rider"]) == "B")
        self.assertIn("dues: $105 per quarter", b["inputs"])
        self.assertIn("[amount and how often, as billed] (about $35/mo)", strategy.hoa_dues({"hoa_monthly": 35}))

    def test_no_jargon(self):
        text = json.dumps(self.W)
        self.assertNotIn("wind-mit", text)
        self.assertIn("wind mitigation", text)


if __name__ == "__main__":
    unittest.main()
