"""What the review assumes and asks: which assumptions each review lists (and the counts that go with them), what goes
to the agent to confirm, the listing-brokerage check, Rider GG's compensation agreement, assumed terms said once,
and the questions for the buyer's agent and the loan officer."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import load  # noqa: E402

review, render, oe = load("seller-offer-review", "review", "render", "_shared.offer_engine")
cf = oe.cf

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "seller-offer-review")
SAMPLE = os.path.join(ROOT, "dev", "samples", "seller-offer-review.json")
PROFILE = {"brokerage": "LPT Realty, LLC"}


def fixture(name):
    with open(os.path.join(FIXTURES, name)) as f:
        return json.load(f)


def case05(a=None, b=None, listing=None, both=None):
    """Two offers on 2604 Sable Palm Way: A (Castellanos, AGA-1) and B (Ostrander, escalation); `both` goes on each."""
    d = fixture("listing-pays-buyer-broker.json")
    for o in d["offers"]:
        o.update(both or {})
    d["offers"][0].update(a or {})
    d["offers"][1].update(b or {})
    d["listing"].update(listing or {})
    return d


def offer(R, oid):
    return next(o for o in R["offers"] if o["id"] == oid)


def fields(items):
    return sorted(a["field"] for a in items)


def flag(o, topic):
    return next((f for f in o["flags"] if f.get("topic") == topic), None)


class Scope(unittest.TestCase):
    """A single review lists only its own offer's items; the comparison lists the shared ones; counts match the lists."""

    def test_single_review_lists_its_own(self):
        with open(SAMPLE, encoding="utf-8") as f:
            R = review.analyze(json.load(f))
        out = review.result(R, "single", "B")  # B closes Oct 30 with its compensation stated
        own = review.listed_assumptions(R, offer_id="B")
        self.assertEqual(fields(out["assumptions"]), fields(own))
        self.assertFalse({"buyer_broker_pct", "current_tax_bill_paid"} & set(fields(out["assumptions"])))  # C's
        self.assertIn(f"{len(out['assumptions'])} input", out["summary"]["data_note"])
        self.assertTrue(out["to_confirm"])
        self.assertLessEqual(set(out["to_confirm"]), {a["why"] for a in own})
        self.assertEqual([a["where"] for a in out["assumptions"] if a["field"] == "title_by"], [offer(R, "B")["label"]])
        m = review.result(R, "multi")
        self.assertEqual(fields(m["assumptions"]), fields(review.listed_assumptions(R, multi=True)))
        self.assertIn(f"{len(m['assumptions'])} input", m["summary"]["data_note"])
        d = fixture("four-offers.json")  # an incomplete offer's review lists its own too
        d["offers"][2]["contract_issues"] = [{"sev": "Blocking", "issue": "Page 3 is missing.", "fix": "Ask for it."}]
        R = review.analyze(d)
        oid = R["incomplete"][0]["id"]
        out = review.result(R, "single", oid)
        self.assertEqual(fields(out["assumptions"]), fields(review.listed_assumptions(R, offer_id=oid)))

    def test_comparison_table_matches_its_count(self):
        data = fixture("four-offers.json")
        for o in data["offers"]:
            o.pop("title_by", None)
        R = review.analyze(data)
        listed = review.listed_assumptions(R, multi=True)
        self.assertIn("title_by", [a["field"] for a in listed])  # shared by several offers, so the comparison lists it
        self.assertTrue(review.multi_view(R)["data_note"].startswith(f"{len(listed)} input"))
        doc = render.build_html(R, {}, sample=False, mode="multi")[0]
        self.assertEqual(doc.split("Assumptions &amp; Data to Confirm</h2>")[-1].count('<span class="pill '), len(listed))

    def test_offer_scoped_items_stay_on_their_review(self):
        R = review.analyze(fixture("four-offers.json"))

        def scopes(a):
            return [x for x in [a["scope"], *(a.get("also") or [])] if x.startswith("offer ")]
        only_b = [a for a in R["missing"] if "offer B" in scopes(a) and "offer A" not in scopes(a)]
        self.assertTrue(only_b)
        self.assertFalse([a for a in review.listed_assumptions(R, False, "A") if a in only_b])
        self.assertTrue(all(a in review.listed_assumptions(R, False, "B") for a in only_b))

    def test_shared_item_names_only_its_offer(self):
        R = review.analyze(case05())
        a = next(a for a in R["missing"] if a.get("also") and a["scope"].startswith("offer "))
        ids = [x[6:] for x in [a["scope"], *a["also"]] if x.startswith("offer ")]
        others = [o["label"] for o in R["offers"] if o["id"] in ids[1:]]
        self.assertFalse([lab for lab in others if lab in render.assumptions_table(R, offer_id=ids[0])])
        self.assertTrue(all(lab in render.assumptions_table(R, multi=True) for lab in others))


class ToConfirm(unittest.TestCase):
    def test_assumed_inspection_and_deposit_are_asked(self):
        R = review.analyze(fixture("minimal-single.json"))
        asked = [a["field"] for a in review.confirm_items(R)]
        self.assertLessEqual({"inspection_days", "deposit"}, set(asked))
        self.assertEqual(asked[:4], [a["field"] for a in R["missing"] if a["impact"] == "high"][:4])  # high gaps lead
        data = fixture("minimal-single.json")
        data["offers"][0].update(inspection_days=10, deposit=10000)
        self.assertFalse({"inspection_days", "deposit"} & {a["field"] for a in review.confirm_items(review.analyze(data))})
        asks = review.to_confirm(review.analyze(fixture("listing-pays-buyer-broker.json")))
        self.assertEqual(len(asks), len(set(asks)))  # a shared ask is one item

    def test_year_built_and_lead_paint(self):
        data = fixture("counter-chain-standard.json")
        data["listing"]["year_built"] = 1995
        self.assertNotIn("year_built", [a["field"] for a in review.analyze(data)["missing"]])
        data = fixture("counter-chain-standard.json")
        data["listing"]["built_before_1978"] = False  # the seller's disclosure answers it
        R = review.analyze(data)
        self.assertNotIn("year_built", [a["field"] for a in R["missing"]])
        self.assertNotIn("lead_paint", [f.get("topic") for f in R["offers"][0]["flags"]])
        data["listing"]["built_before_1978"] = True
        self.assertIn("lead_paint", [f.get("topic") for f in review.analyze(data)["offers"][0]["flags"]])

    def test_date_only_expiry_is_end_of_day_and_assumed(self):
        data = fixture("counter-chain-standard.json")
        data["offers"][0]["expires"] = "2026-09-25"
        R = review.analyze(data)
        self.assertTrue(R["offers"][0]["expires"].endswith("end of day"))
        self.assertEqual(R["offers"][0]["lapsed"], "likely")
        self.assertIn("expires", [a["field"] for a in R["assumptions"]])

    def test_assumed_terms_are_listed_once_not_marked(self):
        d = fixture("minimal-single.json")
        d["offers"][0]["inspection_days"] = 7
        R = review.analyze(d)
        o = R["offers"][0]
        rows = {r[0]: r[1] for r in render.term_rows(o, R)}
        self.assertEqual(rows["Inspection Period"], "7 days (AS IS)")  # the form shows plain
        self.assertNotIn("assumed", json.dumps(list(rows.values())))
        self.assertNotIn("assumed", o["score"]["why"]["approval"])
        self.assertNotIn("assumed", review.walk_away(o, R["costs"])[1])
        self.assertNotIn("(assumed)", render.build_html(R, {}, sample=False)[0])
        listed = {a["field"] for a in review.listed_assumptions(review.analyze(fixture("minimal-single.json")))}
        self.assertLessEqual({"approval", "inspection_days", "loan_approval_days", "contract_form"}, listed)

    def test_assumed_form_is_marked_per_offer(self):
        data = fixture("four-offers.json")
        for o in data["offers"][1:]:
            o.pop("contract_form", None)
        R = review.analyze(data)
        s = review.result(R, "multi")["summary"]
        self.assertIsNone(s["preliminary"])  # the form alone doesn't decide the ranking
        self.assertEqual({r["key"]: r["form_assumed"] for r in s["ranked"]}, {"A": False, "B": True, "C": True, "D": True})
        self.assertNotIn('class="prelim"', render.build_html(R, {}, sample=False, mode="multi")[0])
        self.assertTrue(review.result(R, "single", R["ranked"][0]["id"])["summary"]["preliminary"])

    def test_rider_bookkeeping_doesnt_move_the_review(self):
        """An offer read from a summary (no riders listed) isn't flagged for a missing HOA rider; listing Rider U for
        its rent-back changes no score."""
        def summary(riders=None):
            data = fixture("four-offers.json")
            for o in data["offers"]:
                o.pop("riders", None)
                if o["id"] != "A":
                    o.pop("contract_form", None)
            data["offers"][2].update(rent_back_days=30, rent_back_monthly=0)
            if riders is not None:
                data["offers"][2]["riders"] = riders
            return data
        plain, with_u = (review.result(review.analyze(d), mode="multi") for d in (summary(), summary(["U"])))
        for out in (plain, with_u):
            self.assertNotIn("rider_B", next(o for o in out["offers"] if o["id"] == "C")["flag_keys"])
        self.assertEqual([(o["id"], o["score"]) for o in plain["offers"]], [(o["id"], o["score"]) for o in with_u["offers"]])
        R = review.analyze(summary())
        self.assertIn("riders", [x["field"] for x in R["missing"]])
        self.assertIn("U", [w[0] for w in offer(R, "C")["rider_windows"]])  # the rent-back's window counts anyway
        read = summary()
        read["offers"][1]["riders"] = []  # the contract has no riders: the HOA rider is missing
        self.assertIn("rider_B", next(o for o in review.result(review.analyze(read), mode="multi")["offers"]
                                      if o["id"] == "B")["flag_keys"])


class ListingBrokerage(unittest.TestCase):
    """The listing brokerage the contracts name is checked against the profile's, once, never pinning one offer's firm
    on another."""

    def found(self, d, sid=None, agent=PROFILE):
        out = review.result(review.analyze(d, agent=agent), "single" if sid else "multi", sid)
        return [a["what"] for a in out["assumptions"] if a["field"] == "listing_brokerage"], out["to_confirm"]

    def test_profile_mismatch_asked_once(self):
        d = case05(both={"listing_brokerage": "Greenleaf Realty Partners"})
        found, ask = self.found(d)
        self.assertEqual(len(found), 1)
        self.assertIn(found[0], ask)
        self.assertTrue("Greenleaf Realty Partners" in found[0] and "LPT Realty, LLC" in found[0])
        for sid in ("A", "B"):
            found, ask = self.found(d, sid)
            self.assertEqual(len(found), 1, sid)
            self.assertIn(found[0], ask)
            self.assertFalse([lab for lab in ("Castellanos", "Ostrander") if lab in found[0]])
        d["offers"] = d["offers"][:1]
        d["listing"].pop("highest_and_best_due")
        self.assertEqual(len(self.found(d, "A")[0]), 1)

    def test_each_review_names_its_own_firm(self):
        d = case05(a={"listing_brokerage": "Harborview Realty Group"}, both={"listing_brokerage": "Greenleaf Realty Partners"})
        found, _ = self.found(d)
        self.assertTrue("Harborview" in found[0] and "Greenleaf" in found[0])
        a, b = self.found(d, "A")[0][0], self.found(d, "B")[0][0]
        self.assertTrue("Harborview" in a and "Greenleaf" not in a)
        self.assertTrue("Greenleaf" in b and "Harborview" not in b)
        d = case05(a={"listing_brokerage": "LPT Realty"}, both={"listing_brokerage": "Greenleaf Realty Partners"})
        self.assertEqual(self.found(d, "A")[0], [])  # matches the profile: not asked in its review
        self.assertEqual(len(self.found(d, "B")[0]), 1)

    def test_without_a_profile(self):
        def items(d):
            return [a for a in review.analyze(d)["missing"] if a["field"] == "listing_brokerage"]
        self.assertEqual(len(items(case05(a={"listing_brokerage": "LPT Realty"},
                                          b={"listing_brokerage": "Greenleaf Realty Partners"}))), 1)  # offers disagree
        self.assertEqual(items(case05(both={"listing_brokerage": "Greenleaf Realty Partners"})), [])


class RiderGG(unittest.TestCase):
    """Rider GG: the compensation agreement's status decides the flag and who is asked."""

    def test_agreement_status_sets_the_flag(self):
        for b, flagged, asks in (({"compensation_agreement": "signed_by_buyer_broker", "buyer_broker_pct": 0.025}, True, False),
                                 ({"compensation_agreement": "signed_by_listing_broker"}, True, True),
                                 ({"buyer_broker_paid_by": None, "compensation_agreement": "signed_by_buyer_broker",
                                   "buyer_broker_pct": 0.025}, True, None),
                                 ({"compensation_agreement": "received", "buyer_broker_pct": 0.025}, False, None)):
            with self.subTest(b):
                R = review.analyze(case05(b=b))
                f = flag(offer(R, "B"), "rider_GG")
                self.assertEqual(f is not None, flagged)
                if asks is not None:
                    self.assertEqual(bool(f.get("request")), asks)  # the listing side's own signature: nothing to ask
                self.assertIsNotNone(flag(offer(R, "A"), "rider_GG"))  # A's agreement still isn't recorded
        b = offer(review.analyze(case05(b={"compensation_agreement": "received", "buyer_broker_pct": 0.025})), "B")
        self.assertNotIn("GG", [w[0] for w in b["rider_windows"]])  # received: the window is over

    def test_bad_status_stops_with_every_problem(self):
        with self.assertRaises(oe.OfferError) as e:
            review.analyze(case05(a={"compensation_agreement": "maybe"},
                                  b={"compensation_agreement": "signed_by_seller", "riders": ["B"]}))
        lines = str(e.exception).splitlines()
        self.assertEqual(sum(1 for m in lines if m.startswith("offers[A].compensation_agreement:")), 1)
        self.assertEqual(sum(1 for m in lines if m.startswith("offers[B].compensation_agreement:")), 2)
        self.assertTrue(cf.compensation_agreement_problems({"riders": ["GG"], "compensation_agreement": "received"}, False))
        self.assertEqual(cf.compensation_agreement_problems({"riders": ["GG"], "compensation_agreement": "signed both",
                                                              "buyer_broker_pct": 0.02}, False), [])

    def test_what_is_asked(self):
        R = review.analyze(fixture("expired-aga.json"))  # Rider GG, no amount in the package, the seller pays
        self.assertIn("compensation_agreement", [a["field"] for a in review.confirm_items(R)])
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_pct"] = 0.025  # the amount was given
        self.assertNotIn("compensation_agreement", [a["field"] for a in review.analyze(data)["missing"]])
        data = fixture("expired-aga.json")
        data["offers"][0]["buyer_broker_paid_by"] = "listing_broker"  # between brokers: the listing fee is what's asked
        R = review.analyze(data)
        asked = [a["field"] for a in review.confirm_items(R)]
        self.assertNotIn("compensation_agreement", asked)
        self.assertIn("listing_fee_pct", asked)
        self.assertIsNone(flag(R["offers"][0], "rider_GG").get("request"))


class Questions(unittest.TestCase):
    """What's already in the package isn't asked for again."""

    def test_documents_in_the_package_arent_asked_for(self):
        d = case05(listing={"highest_and_best_due": None})
        R = review.analyze(d)
        without = render.questions(offer(R, "B"), R)
        d["offers"][1]["loan_officer"] = "Riley Galloway"
        R = review.analyze(d)
        self.assertEqual(len(without) - len(render.questions(offer(R, "B"), R)), 1)  # a named loan officer
        counts = {}
        for pof in (None, 90000, 156000):  # covers the down payment, the counter and the $15,000 gap at $156,000
            R = review.analyze(case05(a={"proof_of_funds": pof}))
            counts[pof] = len(render.lender_questions(offer(R, "A"), R))
            self.assertEqual(render.funds_shown(offer(R, "A"), 15000), pof == 156000, pof)
        self.assertEqual(counts[None] - counts[156000], 1)

    def test_short_names_keep_offers_apart(self):
        R = review.analyze(case05(a={"buyer_agent": "Emery Ostrander"}))
        self.assertNotEqual(review.short_name(offer(R, "A"), R), review.short_name(offer(R, "B"), R))


if __name__ == "__main__":
    unittest.main()
