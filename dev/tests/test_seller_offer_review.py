"""seller-offer-review: the review result (single and multi), its markdown wiring, support levels and the PDF."""
import contextlib
import io
import json
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, review_render, handoff = load("seller-offer-review", "review", "render", "_shared.handoff")
oe = review.oe

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")
SAMPLE = os.path.join(ROOT, "dev", "samples", "seller-offer-review.json")
TEMPLATE = os.path.join(ROOT, "skills", "seller-offer-review", "assets", "offer-review-template.md")
AGENT = {"name": "Jane Doe", "brokerage": "Sunshine Realty", "team": None, "license": None, "brand": {"primary": "#0B6E4F"}}

def page(R, agent=None, sample=False, mode="auto", offer_id=None):
    """The report's HTML, from the one document model (review.result)."""
    return review_render.build_html(review.result(R, mode, offer_id), agent or {}, sample)



def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def run(argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = review.main(argv)
    return code, json.loads(out.getvalue())


class Results(unittest.TestCase):
    def test_single_summary(self):
        R = review.analyze(fixture("minimal-single.json"))
        out = review.result(R)
        s = out["summary"]
        self.assertEqual((out["mode"], s["action"]), ("single", "COUNTER"))
        self.assertTrue(s["preliminary"])
        self.assertEqual(s["kpis"][1]["value"], review.money(R["offers"][0]["ns"]["net_adj"]))  # net as written
        self.assertEqual(s["counter"]["rows"][-1]["term"], "Time for Acceptance")
        self.assertEqual(out["value_range"], "not provided")
        self.assertTrue(out["to_confirm"])
        self.assertEqual(out["offers"][0]["net_sheet"]["columns"], ["As Offered", "Downside Case", "Proposed Counter"])
        lapsed = review.result(review.analyze(fixture("expired-aga.json")))
        self.assertEqual(lapsed["offers"][0]["net_sheet"]["columns"][-1], "Counter (Reference)")

    def test_no_active_offers_stops(self):
        d = fixture("minimal-single.json")
        d["offers"][0]["status"] = "declined"
        with self.assertRaises(oe.OfferError):
            review.result(review.analyze(d))
        self.assertEqual(review.result(review.analyze(d), offer_id="A")["summary"]["action"], "DECLINE")

    def test_multi_plan_follows_the_sellers_priority(self):
        data = fixture("four-offers.json")
        for o in data["offers"]:  # the priority on the same counter terms (four offers suggest a firm counter)
            o["counter"] = {"stance": "meet_partway", "stance_reason": "The seller wants this buyer."}
        out = review.result(review.analyze(data))
        s = out["summary"]
        self.assertEqual(s["headline"], "ACCEPT")  # certainty: B (86) isn't risked for a 0.7% gain
        self.assertEqual([(p["key"], p["action"]) for p in s["ranked"]],
                         [("B", "Accept"), ("C", "Hold as Backup"), ("A", "Decline"), ("D", "Decline")])
        self.assertEqual(s["offer_label"], s["ranked"][0]["offer"])
        data["seller"]["priority"] = "balanced"
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["headline"], "COUNTER")
        self.assertIsNone(s["preliminary"])

    def test_single_review_in_a_multi_listing(self):
        R = review.analyze(fixture("four-offers.json"))
        out = review.result(R, mode="single", offer_id="A")
        self.assertEqual(out["summary"]["action"], "DECLINE")
        self.assertEqual(out["summary"]["compare"]["vs"], "Park · Coldwell Banker")
        data = fixture("four-offers.json")
        del data["offers"][0]["deposit"]
        out = review.result(review.analyze(data), mode="single", offer_id="A")
        self.assertIn("Morales · Keller Williams", [a["where"] for a in out["assumptions"]])
        with self.assertRaises(oe.OfferError):
            review.result(review.analyze(fixture("minimal-single.json")), mode="multi")

    def test_offer_labels(self):
        self.assertEqual([oe.surname(n) for n in ("J. Morales", "Ana de la Cruz", "Tom Hill Jr.", "Cher")],
                         ["Morales", "de la Cruz", "Hill", "Cher"])
        self.assertEqual([oe.short_price(v) for v in (432000, 432500, 1250000, 1000000)], ["$432K", "$432.5K", "$1.25M", "$1M"])
        offs = [{"id": "A", "price": 400000, "financing": "fha", "buyer_agent": "Ana Ruiz", "buyer_brokerage": "Compass"},
                {"id": "B", "price": 410000, "financing": "cash", "buyer_agent": "Bo Ruiz", "buyer_brokerage": "Compass"},
                {"id": "C", "price": 400000, "financing": "fha"}, {"id": "D", "price": 400000, "financing": "fha"},
                {"id": "offer-5", "price": 390000, "financing": "va", "label": "Smith Offer"}]
        oe.label_offers(offs)
        self.assertEqual([o["label"] for o in offs], ["Ruiz · Compass, $400K FHA", "Ruiz · Compass, $410K Cash",
                                                      "$400K FHA, C", "$400K FHA, D", "Smith"])
        self.assertEqual(offs[4]["key"], "E")

    def test_offers_go_by_label_never_a_letter(self):
        s = review.result(review.analyze(fixture("four-offers.json")))["summary"]
        self.assertNotIn("Offer B", json.dumps(s))
        R = review.analyze(fixture("texas-single.json"))
        out = review.result(R)
        self.assertNotRegex(json.dumps(out["summary"]) + json.dumps(out["assumptions"]), r"Offer [A-D]\b")
        self.assertNotRegex(page(R, {}, sample=False), r"Offer [A-D]\b")

    def test_incomplete_contract_gets_no_recommendation(self):
        s = review.result(review.analyze(fixture("incomplete-single.json")))["summary"]
        self.assertEqual((s["action"], s["headline"], s["counter"], s["options"], s["revive"]),
                         ("INCOMPLETE", "CONTRACT INCOMPLETE", None, [], None))
        self.assertEqual([f["sev"] for f in s["fixes"]], ["Blocking", "High", "High", "High"])

    def test_incomplete_offer_is_listed_but_not_ranked(self):
        d = fixture("four-offers.json")
        d["offers"][2]["contract_issues"] = [{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for it."}]
        R = review.analyze(d)
        s = review.result(R)["summary"]
        self.assertEqual([(r["rank"], r["offer"], r["action"]) for r in s["ranked"]][-1], ("—", "Díaz · eXp Realty", "Incomplete"))
        self.assertEqual((s["offers_active"], s["offers_incomplete"]), (3, 1))
        self.assertEqual(review.result(R, "single", R["incomplete"][0]["id"])["summary"]["action"], "INCOMPLETE")

    def test_ranked_rows_carry_the_id_for_each_single_review(self):
        with open(SAMPLE, encoding="utf-8") as f:
            R = review.analyze(json.load(f))
        ranked = review.result(R, "multi")["summary"]["ranked"]
        self.assertEqual([r["id"] for r in ranked if r["rank"] != "—"], [o["id"] for o in R["ranked"]])
        for r in ranked:
            self.assertEqual(review.result(R, "single", r["id"])["summary"]["offer"], r["id"])

    def test_template_paths_exist(self):
        """Every summary.<key> the markdown template names is in some review.py output, and every output has the
        top-level and per-offer keys the template reads."""
        with open(TEMPLATE, encoding="utf-8") as f:
            summary_keys = set(re.findall(r"summary\.(\w+)", f.read()))
        seen, outs = set(), []
        for name in ("minimal-single.json", "expired-aga.json", "escalation.json", "listing-pays-buyer-broker.json"):
            R = review.analyze(fixture(name))
            outs.append(review.result(R))
            if R["mode"] == "multi":
                outs += [review.result(R, "single", o["id"]) for o in R["ranked"]]
        for out in outs:
            seen |= set(out["summary"])
            for k in ("property", "list_price", "offers", "to_confirm", "estimated_costs", "assumptions"):
                self.assertIn(k, out)
            for o in out["offers"]:
                for k in ("label", "biggest_risk", "downside_note", "net_sheet"):
                    self.assertIn(k, o)
        self.assertEqual(sorted(summary_keys - seen), [])

    def test_net_sheet_rows_read_each_column_by_key(self):
        """A rider money line on one column and not another (rent-back, seller financing) still lines up."""
        ns = {"lines": [("price", "Price", 400000), ("rent_back", "Rent-Back Credit", -1500), ("conc", "Concessions", 0)]}
        target = {"lines": [("price", "Price", 410000), ("conc", "Concessions", 0)]}
        rows = review.net_sheet_rows([("As Offered", ns), ("Target", target)])
        self.assertEqual([r["key"] for r in rows], ["price", "rent_back", "conc"])
        by_key = {r["key"]: r["values"] for r in rows}
        self.assertEqual((by_key["price"], by_key["rent_back"]), ([400000, 410000], [-1500, 0]))


class Inputs(unittest.TestCase):
    def test_cli_reports_problems(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "listing.json")
            with open(path, "w") as f:
                json.dump({"listing": {"address": "1 Main St"}, "offers": [{"price": 1}]}, f)
            code, out = run([path])
        self.assertEqual((code, out["ok"]), (1, False))
        self.assertIn("list price", out["problems"][0])

    def test_cma_handoff_in_markdown(self):
        h = handoff.build(side="seller", as_of="2026-09-20", subject={"address": "1207 Palmetto Way"},
                          value={"low": 380000, "high": 398000, "midpoint": 390000}, comps=[])
        with tempfile.TemporaryDirectory() as tmp:
            md = os.path.join(tmp, "seller-cma.md")
            with open(md, "w") as f:
                f.write("## Seller CMA\n\nSummary.\n\n" + handoff.to_block(h) + "\n")
            code, out = run([os.path.join(FIXTURES, "minimal-single.json"), "--cma", md])
        self.assertEqual(code, 0)
        self.assertEqual(out["value_range"], "$380,000–$398,000")
        self.assertNotIn("cma_low / cma_high", [a["field"] for a in out["assumptions"]])


class Support(unittest.TestCase):
    """FAR/BAR is fully supported; anything else is best effort, said in chat only, never on the report."""

    def test_support_levels(self):
        out = review.result(review.analyze(fixture("two-offers-accept.json")))
        self.assertEqual((out["support"], out["chat_notes"]), ("full", []))
        out = review.result(review.analyze(fixture("texas-single.json")))  # an offer described, not a named form
        self.assertEqual((out["support"], out.pop("chat_notes")), ("best_effort", [oe.cf.DESCRIBED_NOTE]))
        self.assertNotIn("Florida", json.dumps(out))  # never Florida's numbers or rules for another state
        data = fixture("texas-single.json")
        data["offers"][0]["contract_form"] = "TREC One to Four Family Residential Contract"
        self.assertEqual(review.result(review.analyze(data))["chat_notes"], [oe.cf.BEST_EFFORT_NOTE])
        data = fixture("four-offers.json")  # a blocked other-state contract still carries its note
        data["offers"][0].update(contract_form="Texas TREC 20-18", inspection_walkaway=True,
                                 contract_issues=[{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for it."}])
        self.assertEqual(review.result(review.analyze(data), mode="multi")["support"], "best_effort")

    def test_note_never_on_the_report(self):
        doc = page(review.analyze(fixture("texas-single.json")), {}, sample=False)
        for note in (oe.cf.DESCRIBED_NOTE, oe.cf.BEST_EFFORT_NOTE):
            self.assertNotIn(note, doc)
        self.assertNotIn("Florida", doc)


class Pdf(unittest.TestCase):
    def test_theme_and_profile(self):
        doc = page(review.analyze(fixture("two-offers-accept.json")), AGENT, sample=True)
        self.assertIn("B (#1)", doc)  # a letter only with its rank
        self.assertIn("--brand:#0B6E4F", doc)
        self.assertIn("Sunshine Realty", doc)
        self.assertNotIn("Lic.", doc)  # no license in the profile: nothing printed
        self.assertNotIn("#C2410C", doc)  # the default orange isn't hard-coded anywhere
        doc = page(review.analyze(fixture("minimal-single.json")), {}, sample=False)
        self.assertIn("--brand:#C2410C", doc)  # seller default from shared/design
        self.assertNotIn("None", doc.split("<body")[1].split("</header>")[0])  # no agent lines without a profile

    def test_comparison_is_one_row_per_offer(self):
        data = fixture("four-offers.json")
        base = data["offers"][1]
        for i in range(5):  # nine offers: rows, not columns, and no chart past six
            data["offers"].append(dict(base, id="EFGHI"[i], price=base["price"] - 1000 * (i + 1),
                                       buyer_agent=f"Agent{i} · Brokerage{i}"))
        doc = page(review.analyze(data), AGENT, sample=True)
        self.assertEqual(len(re.findall(r'<td class="[^"]*\brk\b', doc)), 9)
        self.assertNotIn('class="scat"', doc)
        doc = page(review.analyze(fixture("four-offers.json")), AGENT, sample=True)
        self.assertIn('class="scat"', doc)
        self.assertIn("@page{size:Letter landscape}", doc)
        single = page(review.analyze(fixture("minimal-single.json")), {}, sample=False)
        self.assertNotIn("@page{size:Letter landscape}", single)

    def test_comparison_comes_with_each_single_review(self):
        """Two or more active offers: the comparison plus a single review of each, in rank order; one offer asked for:
        just its review."""
        saved = review_render.write_pdf
        review_render.write_pdf = lambda M, agent, sample, out: f"{M['mode']}:{M['summary']['offer'] if M['mode'] == 'single' else None}"
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                ctx = {"agent": {}, "mode": None, "offer": None}
                built = [review_render.build(review.compute(fixture("two-offers-accept.json"), c), "pdf", "/tmp", c)
                         for c in (ctx, dict(ctx, mode="single", offer="B"))]
                paths, one = built
        finally:
            review_render.write_pdf = saved
        self.assertEqual(paths, ["multi:None", "single:B", "single:C"])
        self.assertEqual(one, ["single:B"])

    def test_renders_a_pdf(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(err):
            paths = review_render.main([os.path.join(FIXTURES, "texas-single.json"), "--out", tmp])
            self.assertEqual(len(paths), 1)
            self.assertTrue(paths[0].endswith("-Offer-Review.pdf"))
            with open(paths[0], "rb") as f:
                self.assertEqual(f.read(4), b"%PDF")
        self.assertIn(oe.cf.DESCRIBED_NOTE, err.getvalue())  # the same chat-only line review.py gives
        self.assertNotIn(oe.cf.BEST_EFFORT_NOTE, err.getvalue())

    def test_contract_row_names_the_rider_once(self):
        data = fixture("minimal-single.json")
        data["offers"][0].update(contract_form="standard", riders=["K"])
        R = review.analyze(data)
        rows = {r[0]: r[1] for r in review.term_rows(R["offers"][0], R)}
        self.assertEqual(rows["Contract / Riders"], "Standard + As Is Rider (K)")

    def test_inspection_chart_rolls_like_page_one(self):
        """Day 15 from Sep 26 is Sun Oct 11 and Mon Oct 12 is Columbus Day: the chart and page one both end Oct 13."""
        d = fixture("minimal-single.json")
        d["analysis_date"] = "2026-09-26"
        doc = page(review.analyze(d), {}, sample=False)
        row = doc[doc.index("Inspection (Right to Cancel)"):][:200]
        self.assertIn("Oct 13", row)
        self.assertNotIn("Oct 11", row)

    def test_target_label_moves_off_a_point_label(self):
        x, _, anchor = review_render.target_label_spot("Target $149,590 (Clean Offer at List)", 100, 45, 407,
                                                        [(40, 88, 90, 110)])
        self.assertEqual((x, anchor), (407, "end"))
        self.assertEqual(review_render.target_label_spot("Target", 100, 45, 407, [])[2], "start")


class Lapsed(unittest.TestCase):
    """A lapsed offer is CONTRACT INCOMPLETE with a reference counter that sets a new time for acceptance."""

    def test_passed_and_likely_passed(self):
        for name, prefix, revive_price in (("expired-aga.json", "Passed (", "$497,000"),
                                           ("counter-chain-standard.json", "Likely passed (", None)):
            with self.subTest(name):
                s = review.result(review.analyze(fixture(name)))["summary"]
                self.assertTrue(s["respond_by"].startswith(prefix), s["respond_by"])
                if revive_price:
                    self.assertIsNone(s["counter"])
                    self.assertEqual(s["revive"]["rows"][0]["counter"], revive_price)
        row = review.analyze(fixture("counter-chain-standard.json"))["offers"][0]["counter_rows"][-1]
        self.assertEqual(row[0], "Time for Acceptance")
        self.assertTrue(row[1].startswith("Likely passed ("))
        options = review.result(review.analyze(fixture("counter-chain-standard.json")))["summary"]["options"]
        self.assertEqual(next(x for x in options if x["option"] == "Accept as Written")["status"], "risk")

    def test_reference_counter(self):
        R = review.analyze(fixture("expired-aga.json"))
        last = review.result(R)["summary"]["revive"]["rows"][-1]
        self.assertEqual((last["term"], last["counter"]), ("Time for Acceptance", "Mon Sep 28, 5:00 PM"))
        doc = page(R, {}, sample=False)
        self.assertIn("Counter (Reference)", doc)
        self.assertNotIn("Proposed Counter", doc)

    def test_lapsed_offer_in_a_multi_listing(self):
        data = fixture("expired-aga.json")
        data["offers"].append(dict(data["offers"][0], id="B", expires="2026-10-30 17:00", price=480000))
        data["offers"].append(dict(data["offers"][0], id="C", expires="2026-10-30 17:00", price=470000))
        s = review.result(review.analyze(data), mode="multi")["summary"]
        self.assertEqual((s["offers_active"], s["offers_incomplete"]), (2, 1))  # incomplete offers aren't active
        self.assertEqual([r["action"] for r in s["ranked"]].count("Incomplete"), 1)


class Risks(unittest.TestCase):
    def test_deal_risks_lead_and_watch_items_follow(self):
        out = review.result(review.analyze(fixture("minimal-single.json")))
        o = out["offers"][0]
        self.assertEqual(o["flag_keys"][-1], "flood_disclosure")  # a reminder, last
        self.assertEqual(o["biggest_risk_key"], "threat:financing")  # only Low flags: the threat (FHA) is the risk
        R = review.analyze(fixture("four-offers.json"))
        lee = offer(R, "D")  # a High sale contingency outranks the threat
        self.assertEqual(review.biggest_risk(lee)["key"], "sale_contingency")
        lee_out = next(x for x in review.result(R, mode="multi")["offers"] if x["id"] == "D")
        self.assertEqual(lee_out["flag_keys"][0], "sale_contingency")

    def test_watch_items_are_never_top_risks(self):
        R = review.analyze(fixture("minimal-single.json"))
        o = R["offers"][0]
        o["flags"] = [{"sev": "Med", "issue": "x", "fix": "x", "topic": "flood_disclosure"}]
        self.assertEqual(review.single_view(R, o)["risks"], [])
        data = fixture("minimal-single.json")
        data["offers"][0].update(financing="conventional", down_pct=0.2, contract_form="standard", riders=["K"])
        o = review.analyze(data)["offers"][0]
        self.assertIn("rider_K_terms", [f.get("topic") for f in o["flags"]])
        self.assertNotIn("rider_K_terms", [f.get("topic") for f in review.deal_flags(o)])

    def test_decline_reasons(self):
        close = oe._d("2026-11-07")
        top = {"ns": {"net_adj": 146209}, "ns_down": {"net_adj": 143209}, "score": {"total": 84}}
        o = {"sale_contingency_days": 0, "approval": "du_approved", "financed": True, "close": close,
             "ns": {"net_adj": 146694}, "ns_down": {"net_adj": 139942}, "score": {"total": 55}}
        S = {"deadline": oe._d("2026-11-15")}
        for change, keys in (({}, ["more_net_less_certain"]), ({"score": {"total": 90}}, ["more_net_lower_downside"]),
                             ({"ns": {"net_adj": 140000}}, ["nets_less"])):
            with self.subTest(keys):
                self.assertEqual(oe.decline_reasons(dict(o, **change), top, S)[0], keys)

    def test_downside_counts_what_moves_the_net(self):
        R = review.analyze(fixture("minimal-single.json"))  # no CMA, under list, AS IS: inspection only
        o = R["offers"][0]
        self.assertEqual(review.downside_hits(o), ["inspection"])
        kpi = next(k for k in review.result(R)["summary"]["kpis"] if k["label"] == "Downside Net")
        self.assertEqual(kpi["note"], review.downside_note(o, R["listing"]))
        self.assertEqual(review.downside_hits(offer(review.analyze(fixture("four-offers.json")), "D")),
                         ["appraisal", "inspection"])  # over the CMA high, no gap coverage
        d = review.result(review.analyze(fixture("expired-aga.json")))["offers"][0]  # an appraisal risk that costs nothing
        self.assertEqual((d["downside_counts"], d["downside_checked"]), (["inspection"], ["appraisal", "inspection"]))
        d = review.result(review.analyze(fixture("texas-single.json")))["offers"][0]
        self.assertEqual(d["downside_checked"], ["appraisal"])


class Plan(unittest.TestCase):
    def test_certainty_words_need_a_real_gap(self):
        """A certainty difference under CERTAINTY_GAP points is "about the same" everywhere the script compares two
        offers or an offer and its counter; at the gap or more it says which side is more certain."""
        gap = review.CERTAINTY_GAP
        for d in range(-12, 13):
            want = 0 if abs(d) < gap else (1 if d > 0 else -1)
            self.assertEqual(review.certainty_side(d), want, d)
            sure = {1: "cw_more", -1: "cw_less", 0: "cw_same"}[want]
            self.assertIn(review.L_[sure], review.counter_what(1000, 500, d, "COUNTER"), d)
        R = review.analyze(fixture("two-offers-accept.json"))
        top, other = R["ranked"][0], R["ranked"][1]
        for diff, key in ((1, "now_same"), (gap, "now_most")):  # the other offer scores that much above the plan
            plan = top["counter_score"] if top["action"] == "COUNTER" else top["score"]["total"]
            other["score"] = dict(other["score"], total=plan + diff)
            opts = review.multi_view(R)["options"]
            now = [o for o in opts if o["option"] == review.t("opt_accept_now", label=other["label"])]
            self.assertTrue(now and review.L_[key] in now[0]["what"], (diff, opts))

    def test_no_zero_gain_counter_option(self):
        R = review.analyze(fixture("two-offers-accept.json"))
        top = R["ranked"][0]
        top["ns_counter"] = dict(top["ns_counter"], net_adj=top["ns"]["net_adj"])
        self.assertFalse([o for o in review.multi_view(R)["options"] if o["option"].endswith("Anyway")])

    def test_respond_by_names_the_offer_the_plan_acts_on(self):
        data = fixture("two-offers-accept.json")
        for o in data["offers"]:
            o.pop("expires", None)
        self.assertEqual(review.first_expiry(review.analyze(data))[0], "No time stated")
        R = review.analyze(fixture("four-offers.json"))  # only the declined Morales offer has a time for acceptance
        s = review.result(R)["summary"]
        top = R["ranked"][0]
        self.assertEqual((s["respond_by"], s["respond_by_offer"]), ("No time stated", top["label"]))
        data = fixture("four-offers.json")
        data["offers"][1]["expires"] = "2026-09-26 20:00"  # Park, the offer the plan accepts
        s = review.result(review.analyze(data))["summary"]
        self.assertEqual(s["respond_by_offer"], top["label"])
        self.assertIn("Sep 26", s["respond_by"])
        self.assertIn("Fri Nov 13", review.result(R)["deadline_note"])  # the seller's Nov 15 deadline is a Sunday
        data["seller"]["deadline"] = "2026-11-13"
        self.assertIsNone(review.result(review.analyze(data))["deadline_note"])

    def test_earliest_live_deadline_shows(self):
        R = review.analyze(fixture("four-offers.json"))
        self.assertEqual(offer(R, "A")["action"], "DECLINE")
        for out in (review.result(R), review.result(R, "single", "B")):  # never a declined offer's deadline
            self.assertNotIn("offer_expires", {x["key"] for x in out["summary"]["respond_by_also"]})
        kept = [o for o in R["active"] if o["action"] != "DECLINE" and o is not R["ranked"][0]]
        self.assertTrue(kept)
        for o in kept:  # a kept offer that lapses before the pick's deadline still shows
            o["expires_raw"], o["expires"] = "2026-09-24 09:00", "Sep 24, 2026 · 9:00 AM"
        keys = {x["key"] for x in review.respond_also(R, shown=R["ranked"][0])}
        self.assertTrue(keys & {"offer_expires", "backup_lapses"})

    def test_terms_reason_only_on_the_picks_review(self):
        data = fixture("four-offers.json")
        data["ranking_reason"] = "Best net with a strong lender."
        R = review.analyze(data)
        self.assertEqual(review.multi_view(R)["terms_reason"], data["ranking_reason"])
        self.assertEqual(review.single_view(R, R["ranked"][0])["terms_reason"], data["ranking_reason"])
        self.assertIsNone(review.single_view(R, R["ranked"][1])["terms_reason"])
        self.assertIn("Terms Reason:", page(R, {}, sample=False, mode="multi"))


if __name__ == "__main__":
    unittest.main()
