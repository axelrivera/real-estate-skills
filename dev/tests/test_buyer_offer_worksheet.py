"""Tests for the buyer-offer-strategy outputs: the Offer Package Worksheet (contract entries, riders, checklist),
FAR/BAR vs. other contracts, the markdown template's keys, and the PDF renderer (scripts/render.py)."""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

strategy, buyer_render, cf = load("buyer-offer-strategy", "strategy", "render", "_shared.contract_forms")

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "buyer-offer-strategy")
TEMPLATE = os.path.join(ROOT, "skills", "buyer-offer-strategy", "assets", "offer-strategy-template.md")


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def run(d):
    return strategy.analyze(d, cma=strategy.load_cma(d))


def analyze(name):
    return run(fixture(name))


class FloridaWorksheet(unittest.TestCase):
    def test_riders_and_entries(self):
        w = strategy.worksheet(analyze("fha-competitive.json"))
        self.assertTrue(w["farbar"])
        self.assertEqual([x["rider"] for x in w["riders"]], ["FHA/VA Financing Rider (E)", "Homeowner's/Flood Insurance Rider (H)",
                                                         "Seller's Agreement with Respect to Buyer's Broker Compensation Rider (GG)"])
        self.assertIn("$11,000", next(r for r in w["rows"] if r["field"] == "Initial Deposit")["entry"])
        self.assertIn("Inspection Period", [r["field"] for r in w["rows"]])
        rider_e = next(x for x in w["riders"] if "(E)" in x["rider"])
        self.assertIn("Para. 2", rider_e["inputs"])
        self.assertIn("[", rider_e["inputs"])  # the cap has no default: a blank
        never = [x for x in w["package"] if x["group"] == "Do Not Include"]
        self.assertTrue(never and all(x["status"] == "Never" for x in never))  # personal letters, photos

    def test_paragraphs_riders_and_hoa_dues_in_order(self):
        d = fixture("one-competing-reach.json")
        d["property"]["hoa_frequency"] = "quarterly"
        d["property"]["hoa_monthly"] = 35
        W = strategy.worksheet(run(d))
        paras = [x["para"] for x in W["rows"]]
        keys = [strategy.para_key((p,)) for p in paras]
        self.assertEqual(keys, sorted(keys))
        self.assertLess(paras.index("2(d)"), paras.index("3"))
        self.assertLess(paras.index("3"), paras.index("8(b)"))
        self.assertEqual([cf.rider_code(x["rider"]) for x in W["riders"]], ["B", "F", "H", "GG"])
        self.assertEqual(cf.rider_order(["Appraisal Gap Addendum (AGA-1)", "Rider GG", "Rider F", "Rider B"]),
                         ["Rider B", "Rider F", "Rider GG", "Appraisal Gap Addendum (AGA-1)"])
        b = next(x for x in W["riders"] if cf.rider_code(x["rider"]) == "B")
        self.assertIn("$105 per quarter", b["inputs"])  # $35/mo, as billed
        self.assertIn("$35", strategy.hoa_dues({"hoa_monthly": 35}))  # no billing period: the monthly figure and a blank
        self.assertIn("[", strategy.hoa_dues({"hoa_monthly": 35}))
        item = next(p["item"] for p in W["package"] if p["item"].startswith("Riders attached"))
        for code in ("(B)", "(F)", "(H)", "(GG)"):
            self.assertIn(code, item)

    def test_appraisal_gap_form_follows_the_financing(self):
        """AGA-1 is for conventional or cash offers and isn't used with the Appraisal Contingency Rider (F); a USDA
        gap is written as a clause instead."""
        d = fixture("fha-competitive.json")
        d["buyer"].update(financing="conventional", down_pct=0.2)
        d["overrides"] = {"appraisal_gap": 10000}
        w = strategy.worksheet(run(d))
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn("Appraisal Gap Addendum (AGA-1)", riders)
        self.assertNotIn("Appraisal Contingency Rider (F)", riders)
        self.assertNotIn("Appraisal Gap", [c["title"] for c in w["clauses"]])
        d = {"analysis_date": "2026-09-23",
             "property": {"address": "100 Test Rd, Sanford, FL 32771", "county": "Seminole", "list_price": 400000,
                          "year_built": 2012},
             "value": {"cma_low": 380000, "cma_high": 398000}, "competition": {"level": 3},
             "buyer": {"financing": "usda", "down_pct": 0, "cash_available": 140000, "max_price": 420000},
             "worksheet": {"contract_form": "as_is"}, "overrides": {"price": 400000, "appraisal_gap": 5000}}
        r = run(d)
        self.assertNotEqual(r["O"]["recommended"]["appraisal_form"], "aga")
        w = strategy.worksheet(r)
        self.assertFalse([x for x in w["riders"] if "AGA-1" in x["rider"]])
        self.assertIn("Appraisal Gap", [c["title"] for c in w["clauses"]])

    def test_lender_timeline_box_and_closing_note_agree(self):
        d = fixture("fha-competitive.json")  # lender_called: the financing is confirmed, the date isn't
        for confirmed, status in ((False, "Pending"), (True, "Yes")):
            d["buyer"]["lender_confirmed_timeline"] = confirmed
            w = strategy.worksheet(run(d))
            box = next(p for p in w["package"] if p["item"].startswith("Lender confirms"))
            self.assertEqual(box["status"], status)

    def test_condo_documents_flood_disclosure_and_rider_h_default(self):
        res = strategy.result(analyze("condo-flood.json"))
        text = json.dumps(res)
        self.assertIn("SIRS", text)
        self.assertIn("s. 689.302", text)
        # Rider H's blank shows the form's own default deadline, not a hint
        self.assertIn("the earlier of 30 days after the Effective Date or 10 days before Closing", json.dumps(res["worksheet"]))

    def test_deposit_label_follows_the_contract_words(self):
        r = analyze("one-competing-reach.json")
        self.assertIn("Escrow Deposit", [t["term"] for t in strategy.summary(r)["terms"]])  # FAR/BAR's name
        r["B"]["words"] = dict(r["B"]["words"], deposit_label="Deposit")
        labels = [t["term"] for t in strategy.summary(r)["terms"]]
        self.assertIn("Deposit", labels)
        self.assertNotIn("Escrow Deposit", labels + [x["term"] for x in strategy.pushback(r)])


class OtherContractWorksheet(unittest.TestCase):
    """Only FAR/BAR is built in: any other contract gets the generic entries by name, never another state's rules."""

    def setUp(self):
        self.r = analyze("texas-cma-escalation.json")

    def test_rows_and_riders_are_generic(self):
        w = strategy.worksheet(self.r)
        text = json.dumps(w)
        for florida in ("FAR/BAR", "Form Simplicity", "4-point", "Florida"):
            self.assertNotIn(florida, text)
        self.assertEqual(w["form_name"], "Sample Residential Purchase Agreement")
        self.assertTrue(all(row["para"] == "" for row in w["rows"]))
        fields = [r["field"] for r in w["rows"]]
        words = cf.term_words(cf.OTHER)
        self.assertIn(words["inspection_label"], fields)
        self.assertNotIn("Inspection Period", fields)
        self.assertNotIn("Option Fee", fields)
        riders = [r["rider"] for r in w["riders"]]
        self.assertIn(words["appraisal_addendum"], riders)
        self.assertFalse(any("TREC" in x or "Third Party" in x for x in riders))
        d = fixture("texas-cma-escalation.json")
        d["buyer"].update(financing="fha", down_pct=0.035)
        self.assertIn("FHA/VA Financing Addendum", [r["rider"] for r in strategy.worksheet(run(d))["riders"]])

    def test_terms_use_the_generic_words(self):
        words = cf.term_words(cf.OTHER)
        self.assertEqual(self.r["B"]["words"], words)
        res = strategy.result(self.r)
        labels = [t["term"] for t in res["summary"]["terms"]] + [x["term"] for x in res["side_by_side"]]
        self.assertIn(words["inspection_label"], labels)
        self.assertNotIn("Inspection Period", labels + [p["term"] for p in res["pushback"]])
        self.assertEqual(words["deposit_refund"], self.r["why"]["deposit"]["refund"])
        fl = analyze("fha-competitive.json")
        self.assertEqual(fl["B"]["words"], cf.term_words(cf.AS_IS))
        self.assertIsNone(fl["B"]["words"]["appraisal_addendum"])


class MarkdownTemplate(unittest.TestCase):
    """The markdown template carries what the PDFs print, from keys strategy.result() outputs."""

    @classmethod
    def setUpClass(cls):
        with open(TEMPLATE, encoding="utf-8") as f:
            cls.text = f.read()

    def test_template_paths_exist(self):
        res = strategy.result(analyze("minimal.json"))
        for root, key in re.findall(r"\b(summary|worksheet)\.([a-z_]+)", self.text):
            self.assertIn(key, res[root], f"{root}.{key}")
        loops = {"t": res["summary"]["terms"], "o": res["summary"]["options"], "b": res["summary"]["bands"],
                 "e": res["summary"]["exposure"],
                 "row": res["side_by_side"], "m": res["market_check"], "p": res["pushback"],
                 "a": strategy.result(analyze("fha-competitive.json"))["assumptions"]}
        for var, key in re.findall(r"\b(t|o|b|e|row|m|p|a)\.([a-z_]+)", self.text):
            self.assertIn(key, loops[var][0], f"{var}.{key}")
        for key in ("property", "list_price", "reply_lines", "to_confirm", "side_by_side", "market_check",
                    "pushback", "assumptions", "chat_notes"):
            self.assertIn(key, self.text)
            self.assertIn(key, res)

    def test_package_statuses(self):
        statuses = {x["status"] for x in strategy.result(analyze("texas-cma-escalation.json"))["worksheet"]["package"]}
        self.assertLessEqual({"Never", "Yes"}, statuses)
        self.assertIn('status Never: "- ✕ "', self.text)
        self.assertIn('status Yes, Done, True or ✓: "- [x] "', self.text)
        for key in ("docs", "form_why", "software", "farbar"):
            self.assertIn("worksheet." + key, self.text)

    def test_value_range_market_check_and_side_by_side(self):
        res = strategy.result(analyze("minimal.json"))
        self.assertIsNone(res["value_range"])
        self.assertEqual(res["market_check"][0], {"label": "Value Range", "value": "Not provided", "note": None})
        labels = [m["label"] for m in strategy.result(analyze("texas-cma-escalation.json"))["market_check"]]
        self.assertIn("Median Adjusted Comp", labels)
        self.assertEqual(labels[-2:], ["Market Read", "CMA Offer Plan"])
        r = analyze("condo-flood.json")  # the side-by-side ends with the payment
        rows = strategy.result(r)["side_by_side"]
        self.assertEqual(rows[-1]["key"], "payment")
        self.assertEqual(rows[-1]["values"], [strategy.per_month(r["payment"][k]) for k in r["O"]])
        self.assertNotIn("payment", [x["key"] for x in rows[:-1]])

    def test_handoff_file_via_cli(self):
        d = fixture("texas-cma-escalation.json")
        h = d.pop("cma")
        with tempfile.TemporaryDirectory() as tmp:
            bp, hp = os.path.join(tmp, "buyer.json"), os.path.join(tmp, "8104-Shoal-Creek-Blvd.cma.json")
            with open(bp, "w") as f:
                json.dump(d, f)
            with open(hp, "w") as f:
                json.dump(h, f)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                code = strategy.main([bp, "--cma", hp])
        res = json.loads(out.getvalue())
        self.assertEqual(code, 0)
        self.assertEqual(res["value_range"], "$598,000–$632,000")
        self.assertIn({"label": "Median Adjusted Comp", "value": "$618,500", "note": None}, res["market_check"])


class Pdf(unittest.TestCase):
    """The renderer places the document model (strategy.result); its layout properties are in
    test_generated_buyer_offer_strategy.py."""

    @classmethod
    def setUpClass(cls):
        cls.r = analyze("fha-competitive.json")
        cls.M = strategy.result(cls.r, package_ready=True)

    def test_options_page_brand_and_agent(self):
        doc = buyer_render.options_html(self.M, {"name": "Jane Doe", "brokerage": "Sunshine Realty"}, sample=True)
        self.assertIn("--brand:#1A74AD", doc)  # buyer blue by default
        self.assertIn(strategy.L_["tag"], doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)
        self.assertIn("font-bundled", doc)
        self.assertEqual(doc.count('class="dh pb"'), 1)  # one break, before the detail pages

    def test_worksheet_hides_the_buyers_limits_and_takes_an_option(self):
        doc = buyer_render.worksheet_html(self.M, {}, sample=False)
        for secret in ("$375,000", "$26,000", "$3,200"):
            self.assertNotIn(secret, doc)
        self.assertIn('<span class="fill">[', doc)
        w = strategy.result(self.r, "lower_cost")["worksheet"]  # the option chosen
        self.assertEqual(w["price"], strategy.money(self.r["terms"]["lower_cost"]["price"]))
        with self.assertRaises(strategy.oe.OfferError):
            strategy.worksheet(self.r, "nope")

    def test_status_colors(self):
        d = fixture("one-competing-reach.json")
        d["buyer"]["cash_available"] = 41900  # At Risk, with a thin cushion
        r = run(d)
        s = strategy.summary(r)
        self.assertEqual((s["outlook_class"], s["reserve_status"]), ("risk", "caution"))
        self.assertEqual(next(x for x in s["options"] if x["key"] == "recommended")["status"], "")
        self.assertEqual(strategy.reserve_status(r["B"], 4000), "risk")
        self.assertEqual(strategy.reserve_status(r["B"], 9000), "")
        ctr = re.search(r"\.ctr\{[^}]*\}", buyer_render.css("options")).group(0)
        self.assertIn("var(--brand)", ctr)
        doc = buyer_render.options_html(strategy.result(r), {}, False)
        self.assertIn("t-caution", doc)  # Left in Reserve in caution
        self.assertIn('<div class="cnote">', doc)  # the thin cushion, caution style

    def test_next_step_never_offers_what_the_run_delivers(self):
        """With the worksheet made in the same run, the next step submits it; a quick answer offers to prepare it."""
        r = analyze("kestrel-v5.json")
        quick, files = strategy.result(r)["summary"]["next_step"], strategy.result(r, package_ready=True)["summary"]["next_step"]
        self.assertNotEqual(quick, files)
        self.assertEqual(files, strategy.next_step(r["B"], "", len(r["O"]), True, strategy.opt_name("recommended")))

    def test_renders_both_pdfs(self):
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            paths = buyer_render.main([os.path.join(FIXTURES, "fha-competitive.json"), "--out", tmp, "--format", "all"])
            self.assertEqual([os.path.basename(p) for p in paths],
                             ["1532-Cypress-Bend-Dr-Offer-Options.pdf", "1532-Cypress-Bend-Dr-Offer-Package.pdf"])
            for p in paths:
                with open(p, "rb") as f:
                    self.assertEqual(f.read(4), b"%PDF")

    def test_chat_notes_and_profile_check(self):
        """The best-effort note (another contract) and the no-profile check go to stderr once, not once per file."""
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "buyer.json")
            with open(path, "w") as f:
                json.dump(fixture("texas-cma-escalation.json"), f)
            err = io.StringIO()
            with mock.patch.object(buyer_render.layout, "print_pdf", return_value={"checks": []}), \
                    contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                buyer_render.main([path, "--format", "all", "--out", tmp])
        self.assertEqual(err.getvalue().count(cf.BEST_EFFORT_OFFER_NOTE), 1)
        self.assertEqual(err.getvalue().count("no profile"), 1)
        self.assertIn("no profile", buyer_render.profile_check({}))
        self.assertIn("profile incomplete", buyer_render.profile_check({"name": "A"}))
        self.assertIsNone(buyer_render.profile_check({"name": "A", "brokerage": "B"}))


if __name__ == "__main__":
    unittest.main()
