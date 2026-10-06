"""Client wording (workstream B): the render-time check on the text the model writes (shared/prose.py), labels put in
Title Case before the build, the other files a render reads (deck file, CMA handoff, profile) checked the same way,
and dev/style_check.py's scan of rendered HTML and calendar text for the same words."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(__file__)
sys.path.insert(0, os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)
from shared import handoff, prose, render  # noqa: E402
import style_check as sc  # noqa: E402
from skill_import import load  # noqa: E402

(seller_render,) = load("seller-cma", "render")


def problems(data, **kw):
    return prose.issues(data, **kw)


def message(data, **kw):
    try:
        prose.check(data, **kw)
    except prose.ProseError as e:
        return str(e)
    raise AssertionError("no ProseError")


def run_main(data, *, argv=(), files=None, build=None, **kw):
    """render.main on `data` (written to a temp file, plus `files` {name: text}); returns (exit message, built)."""
    built = []
    with tempfile.TemporaryDirectory() as tmp:
        for name, text in (files or {}).items():
            with open(os.path.join(tmp, name), "w", encoding="utf-8") as f:
                f.write(text)
        src = os.path.join(tmp, "data.json")
        with open(src, "w", encoding="utf-8") as f:
            json.dump(data(tmp) if callable(data) else data, f)
        args = [src, "--out", tmp, *[a.replace("{tmp}", tmp) for a in argv]]
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                render.main(build or (lambda d, fmt, out, ctx: built.append(d) or []), ("pdf",), args, **kw)
        except SystemExit as e:
            return str(e.code), built
    return None, built


class Rules(unittest.TestCase):
    def test_each_rule_names_the_field_and_the_fix(self):
        table = [
            ("Insurance is a placeholder for now.", '"placeholder": a tool word → write the number'),
            ("Numbers come from the JSON.", '"JSON": a tool word'),
            ("See the data file.", '"data file": a tool word'),
            ("Re-run once the roof year is known.", '"Re-run": a tool word'),
            ("The script estimates insurance.", '"script": a tool word'),
            ("Every sale in the export.", '"export": a tool word'),
            ("Sales from the CSV.", '"CSV": a tool word'),
            ("Taxes: null", '"null": an empty value printed as text → leave the field out'),
            ("Closing undefined", '"undefined": an empty value'),
            ("Rate TBD", '"TBD": unfinished text'),
            ("TODO: add the HOA", '"TODO": unfinished text'),
            ("Ask about {roof_permit} first.", '"{roof_permit}": a placeholder no script fills here → write the words'),
            ("Set insurance_annual to the quote.", '"insurance_annual": a data key in the text → say it in words'),
            ("Closing on 2026-09-26 works.", '"2026-09-26": a date in data form → write "Sep 26, 2026"'),
            ("Median DOM is 30.", '"DOM": jargon a client may not know → write "days on market"'),
            ("CDOM of 120 days", '"CDOM": jargon a client may not know → write "cumulative days on market"'),
            ("Ask for the wind-mit report.", '"wind-mit": jargon a client may not know → write "wind mitigation"'),
            ("Seller signs the CASSB-1.", '"CASSB-1": jargon a client may not know → write "the compensation agreement'),
            ("95% LTV loan", '"LTV": jargon a client may not know → write "loan-to-value"'),
            ("DTI is tight", '"DTI": jargon'),
            ("COE Nov 20", '"COE": jargon a client may not know → write "closing"'),
            ("EMD due in 3 days", '"EMD": jargon a client may not know → write "escrow deposit'),
        ]
        for text, want in table:
            found = problems({"summary": {"note": text}})
            self.assertEqual([p for p, _ in found], ["$.summary.note"], text)
            self.assertIn(want, found[0][1], text)

    def test_allowed_wording(self):
        """Plain words, a one-word value, a date with no words around it, and terms clients use pass."""
        for text in ("Escrow deposit due in 3 days", "as_is", "2026-09-26", "2026-09-25 17:00", "null and void",
                     "None / None", "HOA dues $120 a month", "MLS #O6123456", "Your CMA shows", "4-point and wind-mitigation report",
                     "wind mitigation", "Re-roofed in 2019", "a scripted walk-through", "Sep 26, 2026", "Dom Rivera"):
            self.assertEqual(problems({"note": text}), [], text)

    def test_every_problem_listed_at_once(self):
        data = {"summary": "Median DOM is 30, see the data file.", "rows": [["Close", "Set closing_date"]],
                "deck": {"title": "COE 2026-11-20"}, "cards": ["Price—now", "Great for young families"]}
        msg = message(data)
        for line in ('- summary: "DOM": jargon', '- summary: "data file": a tool word', '- rows[0][1]: "closing_date"',
                     '- deck.title: "COE"', '- deck.title: "2026-11-20": a date in data form → write "Nov 20, 2026"',
                     "- cards[0]: em dash in a sentence → use a comma", '- cards[1]: "Great for young families"'):
            self.assertIn(line, msg)
        self.assertIn("Rewrite these 8 things", msg)
        self.assertNotIn("more", msg)

    def test_exempt_fields(self):
        """Names, identifiers, form and rider names, addresses, links, emails and file names keep their own spelling."""
        data = {"id": "offer_a", "key": "earnest_money", "buyer_agent": "DOM Realty TBD", "lender": "LTV Lending",
                "contract_form": "as_is", "riders": ["CASSB-1", "FHA/VA Financing"], "address": "12 Script Rd",
                "export_columns": {"price": "sold_price data"}, "export": "listing_data.json",
                "note": "Details at https://example.com/rerun_page and agent_name@example.com, file comps_2026-09-26.csv.",
                "buyer": {"financing": "Lender wrote 95% LTV"}}  # a `buyer` object is still read
        self.assertEqual([p for p, _ in problems(data)], ["$.buyer.financing"])

    def test_placeholders_the_skill_fills_pass(self):
        data = {"why": ["Adjusted comps center on {median_adjusted}.", "{active_days} on the market"]}
        self.assertTrue(problems(data))
        self.assertEqual(problems(data, placeholders=True), [])  # seller-cma fills and names its own

    def test_agent_only_text_may_use_jargon_but_not_tool_words(self):
        data = {"worksheet": {"note": "95% LTV, EMD in 3 days"}, "summary": "95% LTV"}
        self.assertEqual([p for p, _ in problems(data, agent_only=("worksheet",))], ["$.summary"])
        data["worksheet"]["note"] = "TBD"
        self.assertEqual([p for p, _ in problems(data, agent_only=("worksheet",))], ["$.worksheet.note", "$.summary"])

    def test_profile_rules(self):
        """The profile's voice and disclaimers get em dashes, fair housing and tool words, not jargon or dates."""
        voice = {"voice": "Short sentences. Mention DOM when it helps.", "disclaimers": "Data as of 2026-09-01."}
        self.assertEqual(problems(voice, rules=prose.PROFILE_RULES), [])
        voice["voice"] = "Warm—never pushy. TODO: tagline"
        self.assertEqual(len(problems(voice, rules=prose.PROFILE_RULES)), 2)


class Labels(unittest.TestCase):
    def test_title_case(self):
        self.assertEqual(prose.title_case("list at $479,900 with a seller credit"), "List at $479,900 with a Seller Credit")
        self.assertEqual(prose.title_case("price-cut history vs. the HOA vote"), "Price-Cut History vs. the HOA Vote")
        self.assertEqual(prose.title_case("{price_cut_count} price cuts since May"), "{price_cut_count} Price Cuts Since May")
        self.assertEqual(prose.title_case("Morales · eXp Realty"), "Morales · eXp Realty")

    def test_title_labels(self):
        data = {"pricing": {"strategies": [{"label": "current list price", "note": "keep as is"}]},
                "summary_page": {"key_stats": [["$470K", "median adjusted value"]], "headline": "a sentence stays."},
                "market": {"heading": "the market shifted", "rows": [{"heading": "in spring"}]}}
        out = prose.title_labels(data, ("pricing.strategies[].label", "summary_page.key_stats[][1]", "**.heading"))
        self.assertEqual(out["pricing"]["strategies"][0], {"label": "Current List Price", "note": "keep as is"})
        self.assertEqual(out["summary_page"]["key_stats"], [["$470K", "Median Adjusted Value"]])
        self.assertEqual(out["summary_page"]["headline"], "a sentence stays.")
        self.assertEqual(out["market"]["heading"], "The Market Shifted")
        self.assertEqual(out["market"]["rows"][0]["heading"], "In Spring")
        self.assertEqual(data["pricing"]["strategies"][0]["label"], "current list price")  # a copy

    def test_render_fixes_labels_instead_of_stopping(self):
        err, built = run_main({"scenarios": [{"label": "after a price cut", "price": 450000}]},
                              labels=("scenarios[].label",))
        self.assertIsNone(err)
        self.assertEqual(built[0]["scenarios"][0]["label"], "After a Price Cut")


class OtherFiles(unittest.TestCase):
    def test_missing_data_never_stops(self):
        err, built = run_main({})
        self.assertIsNone(err)
        self.assertEqual(len(built), 1)

    def test_profile_voice_is_checked(self):
        profile = ("---\nprofile: agent\nname: \"Sample Agent\"\nbrokerage: \"Sample Realty, LLC\"\n---\n\n"
                   "## Voice\n\nPlain and warm. TODO: add a sign-off.\n\n## Disclaimers\n\nNot an appraisal—an opinion.\n")
        err, built = run_main({"summary": "Fine."}, argv=("--profile", "{tmp}/profile.md"), files={"profile.md": profile})
        self.assertIn('- profile.voice: "TODO": unfinished text', err)
        self.assertIn("- profile.disclaimers: em dash", err)
        self.assertEqual(built, [])

    def test_cma_handoff_client_fields_are_checked(self):
        h = {"handoff": "cma", "version": 1, "side": "buyer", "as_of": "2026-09-22", "source": "buyer_cma",
             "subject": {"address": "1 Sample St"}, "value": {"low": 1, "high": 2, "midpoint": 1.5}, "comps": [],
             "market": {"note": "Median DOM 30"}}

        def cma_arg(ap):
            ap.add_argument("--cma")
        err, built = run_main({"summary": "Fine."}, argv=("--cma", "{tmp}/h.cma.json"), files={"h.cma.json": json.dumps(h)},
                              extra_args=cma_arg, linked=handoff.linked)
        self.assertIn('- cma.market.note: "DOM": jargon', err)
        self.assertNotIn("buyer_cma", err)  # only what a client can see
        self.assertEqual(built, [])
        self.assertEqual(handoff.linked({}, {"cma": "/nonexistent.cma.json"}), [])  # the skill names a missing file

    def test_seller_cma_deck_file_is_checked(self):
        deck = {"title": "Pricing 1 Sample St", "market_takeaway": "Median DOM fell to 21.",
                "timeline": [["Week 1", "Go live 2026-10-01 at {list_price}"]]}

        def data(tmp):
            return {"deck": os.path.join(tmp, "deck.json")}
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "deck.json"), "w") as f:
                json.dump(deck, f)
            self.assertEqual(seller_render.deck_file({"deck": os.path.join(tmp, "deck.json")}, {})[0][0], "deck")
        err, built = run_main(data, files={"deck.json": json.dumps(deck)}, placeholders=True, linked=seller_render.deck_file)
        self.assertIn('- deck.market_takeaway: "DOM": jargon', err)
        self.assertIn('- deck.timeline[0][1]: "2026-10-01": a date in data form → write "Oct 1, 2026"', err)
        self.assertNotIn("list_price", err)  # the deck's {placeholders} are filled by the skill
        self.assertEqual(built, [])

    def test_fixtures_and_samples_pass(self):
        root = os.path.join(HERE, "..", "..")
        fills = {"seller-cma"}  # buyer-cma writes every figure itself: its fixtures carry no {placeholders}
        for folder in ("fixtures", "samples"):
            for dirpath, _, names in os.walk(os.path.join(root, "dev", folder)):
                for n in names:
                    if not n.endswith(".json"):
                        continue
                    with open(os.path.join(dirpath, n), encoding="utf-8") as f:
                        data = json.load(f)
                    where = os.path.join(dirpath, n)
                    agent_only = ("worksheet",) if "buyer-offer-strategy" in where else ()
                    self.assertEqual(problems(data, placeholders=any(s in where for s in fills) or "deck" in n,
                                              agent_only=agent_only), [], where)


class StyleCheck(unittest.TestCase):
    def test_planted_script_text_is_caught(self):
        from bs4 import BeautifulSoup
        html = ("<html><style>.a_b{}</style><body><h2>Costs</h2><p>Insurance is a placeholder: re-run with "
                "insurance_annual set.</p><td>Closing 2026-11-20</td><td>2026-11-20</td><p>Median DOM: 30</p>"
                "<p>{unfilled}</p></body></html>")
        found = sc.html_wording(BeautifulSoup(html, "html.parser"))
        for want in ('"placeholder"', '"re-run"', '"insurance_annual"', '"2026-11-20": a date', '"DOM"', '"{unfilled}"'):
            self.assertTrue(any(want in f for f in found), want)
        self.assertFalse(any("a_b" in f for f in found))  # CSS isn't text
        draft = BeautifulSoup('<div class="draftbar">Draft</div><p>loan (95.0% LTV)</p>', "html.parser")
        self.assertEqual(sc.html_wording(draft), [])  # the agent's worksheet may use agent jargon

    def test_calendar_text(self):
        ics = ("BEGIN:VEVENT\r\nSUMMARY:EMD Due\r\nDESCRIPTION:Deliver the deposit\\, then re-run the time\r\n line"
               "\\nsee 2026-11-20 notes\r\nDTSTART:20261120T170000\r\nEND:VEVENT\r\n")
        found = sc.ics_wording(ics)
        self.assertTrue(any('"EMD"' in f for f in found))
        self.assertTrue(any('"re-run"' in f for f in found))
        self.assertTrue(any('"2026-11-20"' in f for f in found))
        self.assertEqual(sc.ics_wording("SUMMARY:Escrow Deposit Due\r\nDTSTART:20261120\r\n"), [])


if __name__ == "__main__":
    unittest.main()
