"""seller-cma report PDF: brand colors, page 1 figures and labels from compute.py's output, the checks render.py reports
for the chat (page fill, chart labels, callouts, profile), and one PDF build. Page fit for every fixture is test_layout's."""
import contextlib
import copy
import io
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from test_seller_cma import (AGENT, compute, profiles, report, reprice, run, seller_render, tanager,  # noqa: E402
                             texas)


def html(R, agent=AGENT):
    C, homes = run(R)
    doc, L = seller_render.build_html(copy.deepcopy(R), C, homes, agent)
    return doc, L, C


def page_one(doc):
    return doc.split('<div class="pb">')[0]


class Brand(unittest.TestCase):
    def test_colors_and_agent_fields(self):
        doc, _, _ = html(report())
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("License", doc)
        self.assertIn("--subject:var(--text)", doc)  # the subject home is black: one brand hue, no second color
        self.assertNotIn("var(--party", doc)  # no party color outside party coding
        self.assertNotIn("tag prelim", doc)
        bare = html(report(), profiles.load_agent(None))[0]
        self.assertIn("--brand:#C2410C", bare)  # default seller orange
        # a missing name or brokerage is a chat check only; the PDF leaves them out
        self.assertIn("no profile", seller_render.profile_check(profiles.load_agent(None)))
        self.assertIn("profile incomplete", seller_render.profile_check({**AGENT, "brokerage": None}))
        self.assertIsNone(seller_render.profile_check(AGENT))
        self.assertNotIn("no profile", bare)


class PageOne(unittest.TestCase):
    def test_nets_on_the_reply_basis(self):
        """Page 1, the pricing table and the tile show the after-holding nets the reply compares; the net sheet's
        total row alone shows the net before holding costs."""
        R = reprice()
        R["costs"]["mortgage_payoff"] = 210000
        doc, L, C = html(R)
        self.assertEqual(C["net_basis"], "after_holding")
        ri = C["recommended_index"]
        self.assertEqual(C["recommended_net_display"], C["strategies"][ri]["net_after_holding_display"])
        self.assertEqual(C["placeholders"]["recommended_net"], C["strategies"][ri]["net_after_holding_display"])
        for x in C["strategies"]:
            self.assertNotEqual(x["net_display"], x["net_after_holding_display"])
            self.assertEqual(doc.count(f'<td class="n">{x["net_after_holding_display"]}</td>'), 3)
            self.assertEqual(doc.count(f'<td class="n">{x["net_display"]}</td>'), 1)
        self.assertIn(L("sum_cash_tile_holding", price=C["recommendation"]["list_price_display"]), doc)
        for key in ("th_est_cash", "th_cash"):  # the after-holding net is never called cash at closing
            self.assertNotIn(L(key), doc)

    def test_labels_by_case(self):
        R = reprice()
        doc, L, C = html(R)
        self.assertEqual(C["recommended_index"], 1)
        self.assertIn(L("sum_rec"), doc)  # New List Price
        self.assertNotIn(compute.labels(report())("sum_rec"), doc)
        self.assertIn(L("sum_stay", price="$479,900"), page_one(doc))
        R = report()
        doc, L, C = html(R)
        self.assertEqual(C["competing_offer_caveat"], 2)
        caveat = L("sum_options_note_competing", price=C["strategies"][2]["list_price_display"])
        self.assertIn(caveat, doc[:doc.index(L("h_home"))])  # page 1
        R["pricing"]["strategies"][2].update(expected_sale=452000, seller_credit=10000)  # now it nets less
        doc, _, C = html(R)
        self.assertIsNone(C["competing_offer_caveat"])
        self.assertNotIn(caveat, doc)

    def test_figures_from_compute(self):
        R = tanager()
        doc, _, C = html(R)
        one = doc[doc.index('class="onepage"'):]
        self.assertIn("$380,000 – $400,000", one)
        self.assertIn(C["strategies"][1]["expected_sale_display"], one)
        self.assertIn("$389,900&nbsp;★", doc)  # the star stays on the price line
        self.assertIn(C["adjustment_summary"], doc)
        R = report()
        R["listing_history"] = [{"status": "expired", "price": 229900, "original_price": 239900, "ended": "2017-03",
                                 "days_on_market": 184}]
        doc, _, C = html(R)
        self.assertIn(C["listing_history"][0]["text"], page_one(doc))
        doc, L, _ = html(report())
        tail = doc[doc.rindex('<div class="kg sec">'):]
        self.assertIn(L("h_method"), tail)
        self.assertIn('<div class="notices">', tail)
        self.assertIn("<footer>", tail)
        self.assertIn('class="kg sec runon"', doc)  # the method may run on to a last page

    def test_no_export_key_stats_from_the_comps(self):
        R = texas(report())
        R["mls"] = "Unlock MLS"
        R["summary_page"].pop("key_stats")
        doc, L, C = html(R)
        self.assertFalse({"mls_not_built_in", "mls_assumed", "mls_not_given"} & set(C["market_note_keys"]))
        self.assertIn(L("sum_stat_median", n=C["n_comps"]), doc)
        self.assertIn(L("sum_stat_comps"), doc)
        self.assertNotIn("mls_assumed", run(report())[0]["market_note_keys"])  # read by the MLS's own columns
        R = report()
        R["export_columns"] = {"address": "Address", "status": "Status", "living_area": "Heated Area",
                               "close_price": "Close Price", "current_price": "Current Price", "close_date": "Close Date"}
        self.assertIn("mls_assumed", run(R)[0]["market_note_keys"])


class RenderChecks(unittest.TestCase):
    def test_scatter_checks(self):
        """A label still covering a marker or left off is a Check; a label moved off its asked side is a note."""
        checks, notes = seller_render.scatter_checks(
            {"labels_overlapping": ["749 Cedar Ln W"], "crowded_labels": [],
             "labels_moved": [("749 Cedar Ln W", "below", "right"), ("Your Home", "right", "left")]})
        self.assertEqual((len(checks), len(notes)), (1, 1))
        self.assertIn("749 Cedar Ln W", checks[0])
        self.assertNotIn("749 Cedar", notes[0])  # already named in the check
        self.assertEqual(seller_render.scatter_checks({"labels_overlapping": [], "labels_moved": []}), ([], []))
        checks, _ = seller_render.scatter_checks({"labels_dropped": ["882 Siskin Way (For Sale)", "Your Home"]}, "Your Home")
        self.assertEqual(len(checks), 1)
        self.assertIn("882 Siskin Way (For Sale)", checks[0])
        self.assertNotIn("Your Home", checks[0])
        R = report()
        C, homes = run(R)
        comps = {" ".join(cd["address"].upper().split()) for cd in R["comps"]["cards"]}
        pend = next(h for h in homes if h["status"] == "SOLD" and h.get("living_area")
                    and " ".join(h["address"].upper().split()) not in comps)
        pend["status"] = "PENDING"
        R["scatter"]["callouts"] = R["scatter"]["callouts"][:1] + [
            {"address": pend["address"], "label": "Pending Sale", "side": "right"},
            {"address": "1 NOWHERE LN", "label": "Missing", "side": "left"}]
        seller_render.build_html(copy.deepcopy(R), C, homes, AGENT)
        self.assertEqual(C["render_check_keys"].count("callout_not_plotted"), 2)
        self.assertEqual(len(C["render_checks"]), len(C["render_check_keys"]))
        _, info = compute.cma.scatter(homes, {**R["scatter"], "subject_label": "Your Home"}, 1849,
                                      R["recommendation"]["list_price"], R["subject"]["mls_address"],
                                      (R["recommendation"]["low"], R["recommendation"]["high"]), compute.labels(R))
        self.assertEqual([d[2] for d in info["callouts_dropped"]], ["pending", "not_in_export"])
        R = report()  # the fixture's own callouts are all plotted
        C, homes = run(R)
        seller_render.build_html(R, C, homes, AGENT)
        self.assertNotIn("callout_not_plotted", C.get("render_check_keys", []))

    def test_page_checks(self):
        """A page under half full before a moved block, a last page with a few lines, and the comp table apart from its
        cards are Checks; a method-only last page only when a modest cut brings it back."""
        full = (0.9, "x")
        self.assertEqual(seller_render.page_checks([full, full, full]), [])
        checks = seller_render.page_checks([full, (0.34, "a"), (0.9, "Where Your Home Fits"), (0.1, "Sales data")])
        self.assertEqual(len(checks), 2)
        self.assertIn("Page 2", checks[0])
        self.assertIn("page 4", checks[1])
        L = compute.labels(report())
        head = " ".join(L(k) for k in ("th_sale", "th_sold_for", "th_seller_paid", "th_adjusted"))
        pages = [(0.9, "Seller Summary"), (0.8, "The Home"), (0.97, head), (0.77, "Before We List"), (0.37, L("h_method"))]
        checks = seller_render.page_checks(pages, L)
        self.assertEqual(len(checks), 2)
        self.assertIn("page 3", checks[0])
        self.assertIn("page 5", checks[1])
        pages[3] = (0.93, "Before We List")  # a full page before it: no cut would bring the method back
        self.assertEqual(len(seller_render.page_checks(pages, L)), 1)
        self.assertEqual(seller_render.page_checks(pages),
                         seller_render.cma.page_checks(pages, "the needs list, the launch steps or the method"))

    def test_page_fill_reads_the_pdf(self):
        render = seller_render.render
        if not shutil.which("pdftotext"):
            self.skipTest("pdftotext isn't installed here")
        doc = render.page('<div style="height:300px">Top line</div><div style="break-before:page">Second page</div>')
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.pdf")
            render.html_to_pdf(doc, path, margins=compute.cma.PAGE_MARGINS)
            pages = seller_render.page_fill(path)
        self.assertEqual([p[1] for p in pages], ["Top line", "Second page"])
        self.assertLess(pages[1][0], 0.1)


class Build(unittest.TestCase):
    def test_pdf_only(self):
        """The PDF build hands the agent the PDF alone: no JSON beside it."""
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                paths = seller_render.build(report(), "pdf", tmp, {"agent": profiles.load_agent(None), "market": None,
                                                                   "sample": True})
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(5), b"%PDF-")
            self.assertEqual(paths, [paths[0]])
            self.assertFalse([f for f in os.listdir(tmp) if f.endswith(".json")])


if __name__ == "__main__":
    unittest.main()
