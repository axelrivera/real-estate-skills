"""Contract timeline rules (skills/contract-timeline/scripts/timeline.py): which rows a contract gets and their dates,
rider rules, notes and flags as keys, amendments, completed rows and input validation. Date math is in
test_timeline_dates.py, the calendar and render wiring in test_timeline_calendar.py. Every fact of the unmodified
fixtures is pinned by dev/golden/contract-timeline/."""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(__file__))
from skill_import import ROOT, load  # noqa: E402

timeline, timeline_render = load("contract-timeline", "timeline", "render")
FIXTURES = os.path.join(ROOT, "dev", "fixtures", "contract-timeline")


def fixture(name):
    """A fixture deal prepared on the day the fixtures assume (dev/golden.py), so its deadlines don't read as past."""
    with open(os.path.join(FIXTURES, name)) as f:
        deal = json.load(f)
    deal.setdefault("report_date", "2026-09-26")
    return deal


def by_key(result):
    return {r["key"]: r for r in result["rows"] + result["pending"]}


def fha(**contract):
    """buyer-fha.json (AS IS, Riders E and H, effective Fri 2026-09-25, closing Fri 2026-10-30) with contract changes."""
    d = fixture("buyer-fha.json")
    if "effective_date" in contract:  # the last signature's stamp belongs to the fixture's own Effective Date
        d["contract"].pop("effective_date_signed", None)
    d["contract"].update(contract)
    return d


class FarbarRows(unittest.TestCase):
    """Rows the FAR/BAR forms give a deal, hand-checked against ASIS-7x / 7x Rev. 2/26."""

    def test_title_rows(self):
        """Para. 9(c): 15 days before closing, or 5 when the deal is cash; the seller's own evidence 5 days after."""
        rows = by_key(timeline.analyze(fha(financing="cash")))
        self.assertEqual(rows["title"]["when"], "2026-10-26 23:59")  # Sun Oct 25 extends
        self.assertFalse(set(rows) & {"loan_app", "loan_approval", "appraisal", "insurance_bound", "clear_to_close"})
        self.assertEqual(by_key(timeline.analyze(fha(seller_has_title_evidence=True)))["seller_title"]["when"],
                         "2026-09-30 23:59")
        r = timeline.analyze(fha(title_by="buyer"))
        self.assertEqual(by_key(r)["title"]["party"], "Buyer")
        self.assertNotIn("title_by_unknown", r["note_keys"])
        d = fixture("buyer-fha.json")
        d["contract"].pop("title_by", None)
        self.assertIn("title_by_unknown", timeline.analyze(d)["note_keys"])

    def test_contingency_after_closing_is_flagged(self):
        r = timeline.analyze(fha(inspection_days=40))
        rows = by_key(r)
        self.assertGreater(rows["inspection"]["when"], rows["closing"]["when"])
        self.assertIn("after_closing", r["flag_keys"])
        self.assertIn("loan_approval_after_closing", timeline.analyze(fha(loan_approval_days=40))["flag_keys"])

    def test_association_rows(self):
        """Condo 7 business days (capped at closing), HOA 3 calendar days; both the buyer's contingencies."""
        row = by_key(timeline.analyze(fha(riders=["Condominium Rider"], condo_docs_received="2026-10-22")))["condo_docs"]
        self.assertEqual((row["party"], row["contingency"], row["when"]), ("Buyer", True, "2026-10-30 10:00"))
        row = by_key(timeline.analyze(fha(riders=["Condominium Rider"], condo_docs_received="2026-10-01")))["condo_docs"]
        self.assertEqual(row["when"], "2026-10-13 23:59")  # skips Columbus Day
        d = fha(riders=["Homeowners' Association"], hoa_docs_received="2026-10-01")
        row = by_key(timeline.analyze(d))["hoa_docs"]
        self.assertEqual((row["party"], row["contingency"], row["when"]), ("Buyer", True, "2026-10-05 23:59"))  # Sun -> Mon
        d["contract"]["hoa_disclosure_before_contract"] = True
        self.assertNotIn("hoa_docs", by_key(timeline.analyze(d)))
        r = timeline.analyze(fha(association_approval="unknown", preapproval_expires="2026-10-20"))
        self.assertTrue({"assoc_apply", "assoc_approval"} <= set(by_key(r)))
        self.assertIn("assoc_box_blank", r["flag_keys"])
        self.assertIn("preapproval_expires", r["note_keys"])
        self.assertEqual(len(r["flags"]), len(r["flag_keys"]))  # every flag the script adds has a key

    def test_rows_from_receipts(self):
        """Survey and title notices count from receipt; flood elevation from the Effective Date; FHA/VA election 3 days
        after the buyer receives the appraisal (Rider E Para. 5); a waived lead-paint assessment has no row."""
        rows = by_key(timeline.analyze(fha(title_commitment_received="2026-10-14", survey_received="2026-10-27",
                                           flood_zone="AE", seller_has_survey=True, year_built=1970, lbp_waived=True,
                                           appraisal_received="2026-10-08")))
        self.assertEqual(rows["title_exam"]["when"], "2026-10-19 23:59")
        self.assertEqual(rows["survey_notice"]["when"], "2026-10-30 10:00")  # 5 days after receipt, capped at closing
        self.assertEqual(rows["flood_elevation"]["when"], "2026-10-15 23:59")
        self.assertEqual(rows["seller_survey"]["when"], "2026-09-30 23:59")
        self.assertEqual(rows["fha_va_election"]["when"], "2026-10-13 23:59")  # Sun Oct 11, Columbus Day Oct 12
        self.assertNotIn("lead_paint", rows)

    def test_standard_contract_has_repair_notices_not_a_cancel_right(self):
        rows = by_key(timeline.analyze(fha(contract_form="standard", repair_notice_delivered="2026-10-05",
                                           repair_estimates_received="2026-10-12", open_permits=True)))
        self.assertFalse(rows["inspection"]["contingency"])
        self.assertEqual(rows["repair_estimates"]["when"], "2026-10-15 23:59")
        self.assertEqual(rows["repair_election"]["when"], "2026-10-19 23:59")  # Sat Oct 17 extends
        self.assertEqual(rows["permits_closed"]["when"], "2026-10-26 23:59")  # Sun Oct 25 extends
        self.assertEqual(rows["walkthrough"]["source"], "Para. 12(e)")

    def test_rows_counted_back_from_closing(self):
        """A custom row due "by closing" sorts before it; without a closing date such rows wait."""
        d = fixture("buyer-fha.json")
        d["deadlines"] = [{"key": "carpet", "label": "Seller Cleans Carpets", "short": "Carpets", "basis": "before",
                           "days": 0, "time": "closing", "party": "Seller", "source": "Para. 20"}]
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["carpet"]["when"], "2026-10-30 10:00")
        self.assertTrue(by_key(r)["carpet"]["by_closing"])
        keys = [x["key"] for x in r["rows"]]
        self.assertLess(keys.index("carpet"), keys.index("closing"))
        d["deadlines"][0].update(days=2, time="17:00")
        self.assertEqual(by_key(timeline.analyze(d))["carpet"]["when"], "2026-10-28 17:00")
        d = fixture("buyer-fha.json")
        del d["contract"]["closing_date"]
        r = timeline.analyze(d)
        self.assertIsNone(r["closing"])
        self.assertIn("walkthrough", {x["key"] for x in r["pending"]})  # counted back from closing: waits for the date
        self.assertIn("deposit", {x["key"] for x in r["rows"]})

    def test_deposit_rows_from_the_number(self):
        """The deposit rows come from the numeric amount when the words aren't given (the additional deposit used to be
        lost without a word)."""
        d = fixture("buyer-fha.json")
        d["contract"].pop("deposit_amount_str")
        d["contract"]["deposit_amount"] = 11000
        self.assertIn("$11,000", by_key(timeline.analyze(d))["deposit"]["action"])
        d = fixture("standard-riders.json")
        for k in ("additional_deposit_amount_str", "additional_deposit_amount", "additional_deposit_days"):
            d["contract"].pop(k, None)
        self.assertNotIn("add_deposit", by_key(timeline.analyze(d)))
        d["contract"]["additional_deposit_amount"] = 10000
        row = by_key(timeline.analyze(d))["add_deposit"]
        self.assertTrue(row["critical"])
        self.assertIn("$10,000", row["action"])

    def test_effective_date_delivery_and_source(self):
        """Signatures without a delivery time are asked; the e-sign platform never reaches the source."""
        self.assertNotIn("effective_delivery_unconfirmed", timeline.analyze(fha())["note_keys"])
        self.assertIn("effective_delivery_unconfirmed", timeline.analyze(fha(effective_date_delivered=False))["note_keys"])
        self.assertNotIn("effective_delivery_unconfirmed", timeline.analyze(fha(effective_date_delivered=True))["note_keys"])
        o = fixture("other-contract.json")
        o["contract"]["effective_date_delivered"] = False
        self.assertIn("effective_delivery_unconfirmed", timeline.analyze(o)["note_keys"])
        r = timeline.analyze(fha(effective_date_source="Seller's signature (Dotloop)"))
        self.assertNotIn("Dotloop", r["effective"]["source"])
        self.assertEqual(timeline.no_platform("Signed via DocuSign on the acceptance"), "Signed on the acceptance")

    def test_effective_source_states_no_date_of_its_own(self):
        """The source's time stamp is a field the script prints: a date or time written into the source (or into an
        amendment's description) stops the run, and a stamp after the Effective Date can't be."""
        r = timeline.analyze(fha())
        self.assertEqual(r["effective"]["signed"], "2026-09-25 16:12")
        self.assertIn(timeline.fmt.when("2026-09-25 16:12", "dot"), r["effective"]["source"])
        for text in ("Seller's signature, 9/22/26", "Buyer's initials at 4:12 PM", "Signed Sept 22", "Signed 2026-09-22"):
            with self.assertRaisesRegex(timeline.DealError, "effective_date_source"):
                timeline.analyze(fha(effective_date_source=text))
        for text in ("Seller's initials on Counteroffer #2", "Buyer's initials on the changes (Para. 3(b))",
                     "Second seller's signature on Addendum No. 1 (CR-7)"):
            timeline.analyze(fha(effective_date_source=text))
        with self.assertRaisesRegex(timeline.DealError, "effective_date_signed"):
            timeline.analyze(fha(effective_date_signed="2026-09-26 09:00"))
        d = fha()
        d["amendments"] = [{"date": "2026-09-26", "description": "Extend closing to Nov 6", "changes": {}}]
        with self.assertRaisesRegex(timeline.DealError, r"amendments\[0\]\.description"):
            timeline.analyze(d)


class FirstDeadline(unittest.TestCase):
    def test_first_deadline_is_the_earliest_open_contract_deadline(self):
        """The earliest dated row not done or past, whoever owes it, critical or not, Rider GG's rows included while
        open; never a lender target; never a cancel window the signed agreement closed."""
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"]["riders"]) + ["GG"]
        d["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(d)
        self.assertEqual(r["first_deadline"]["key"], "compensation_agreement")  # Mon Sep 28, before the inspection
        self.assertTrue(by_key(r)["compensation_cancel"]["broker"])
        d["completed"].update(compensation_agreement="2026-09-27", loan_app="2026-09-27")
        self.assertEqual(timeline.analyze(d)["first_deadline"]["key"], "inspection")  # not the closed window (Oct 1)
        d["completed"] = {"deposit": "2026-09-26", "loan_app": "2026-09-27"}
        d["report_date"] = "2026-09-29"  # the agreement deadline passed unrecorded: the open window still counts
        self.assertEqual(timeline.analyze(d)["first_deadline"]["key"], "compensation_cancel")
        o = fixture("other-contract.json")
        o["side"] = "seller"
        o["deadlines"][0]["party"] = "both"
        self.assertEqual(timeline.analyze(o)["first_deadline"]["key"], "earnest_money")  # a Both row isn't skipped
        late = fixture("buyer-fha.json")
        late["report_date"] = "2026-10-27"  # the lender's Closing Disclosure (Oct 27) is never it
        late["completed"] = {k: "2026-10-26" for k in ("deposit", "inspection", "insurance", "loan_approval")}
        r = timeline.analyze(late)
        self.assertFalse(r["first_deadline"]["lender"])
        self.assertEqual(r["first_deadline"]["key"], "seller_terminate")

    def test_done_and_past_rows(self):
        """A deadline before the report date and not done is past, never the first deadline, and noted for the agent;
        a done row is out of the way."""
        d = fixture("buyer-fha.json")
        d["report_date"] = "2026-10-01"
        r = timeline.analyze(d)
        rows = by_key(r)
        self.assertTrue(rows["deposit"]["past"])
        self.assertEqual(rows["deposit"]["past_display"], "Past, Confirm")
        self.assertFalse(rows["inspection"]["past"])
        self.assertEqual(r["first_deadline"]["key"], "inspection")
        self.assertIn("past_not_done", r["note_keys"])
        d["completed"] = {"deposit": "2026-09-27"}
        self.assertFalse(by_key(timeline.analyze(d))["deposit"]["past"])
        d = fixture("buyer-fha.json")
        d["completed"] = {"deposit": "2026-09-26"}
        r = timeline.analyze(d)
        self.assertTrue(by_key(r)["deposit"]["done"])
        self.assertEqual(by_key(r)["deposit"]["done_display"], "Done Sep 26")
        self.assertEqual(r["first_deadline"]["key"], "loan_app")


class Riders(unittest.TestCase):
    """CR-7 rider rows, each checked against the rider's own "if left blank" text (shared/references/farbar-riders.md)."""

    def deal(self, riders, form="standard", **contract):
        d = fixture("buyer-fha.json")
        d["contract"].update(contract_form=form, riders=riders, financing="conventional")
        d["contract"].pop("insurance_days", None)
        d["contract"].update(contract)
        return d

    def test_inspection_riders(self):
        """Rider K turns the Standard form into a walk-away without repairs; Rider L adds the walk-away and keeps the
        repairs; I, K and L are RESERVED on AS IS."""
        rows = by_key(timeline.analyze(self.deal(["As Is"])))
        self.assertTrue(rows["inspection"]["contingency"])
        self.assertIn("Rider (K)", rows["inspection"]["source"])
        self.assertIn("Rider (K)", rows["walkthrough"]["source"])
        self.assertNotIn("repair_estimates", rows)
        rows = by_key(timeline.analyze(self.deal(["L"])))
        self.assertTrue(rows["inspection"]["contingency"])
        self.assertTrue({"repair_estimates", "repair_election"} <= set(rows))
        with self.assertRaisesRegex(timeline.DealError, "RESERVED"):
            timeline.analyze(self.deal(["K"], form="as_is"))

    def test_rider_dates(self):
        """Effective Date Fri Sep 25 2026, closing Fri Oct 30 2026."""
        cases = [
            (["Appraisal Contingency"], {}, "appraisal_due", "2026-10-20"),  # Rider F blank: closing - 10
            (["Appraisal Contingency"], {}, "appraisal", "2026-10-23"),  # + 3 days for the buyer's notice
            (["F"], {"appraisal_date": "2026-10-14"}, "appraisal_due", "2026-10-14"),
            (["F"], {"appraisal_date": "2026-10-14"}, "appraisal", "2026-10-19"),
            (["Homeowners'/Flood Ins"], {}, "insurance", "2026-10-20"),  # Rider H blank: closing - 10 is before ED + 30
            (["V"], {"sale_contingency_date": "2026-10-15"}, "sale_contingency", "2026-10-19"),  # Oct 18 is a Sunday
            (["Short Sale"], {}, "short_sale_application", "2026-10-05"),  # ED + 10
            (["Short Sale"], {}, "short_sale_approval", "2026-12-24"),  # ED + 90
            (["Short Sale"], {}, "short_sale_expires", "2027-01-25"),  # + 30 = Sat Jan 23, rolled
            (["U"], {"seller_occupancy_days": 14}, "post_closing_agreement", "2026-10-20"),
            (["U"], {"seller_occupancy_days": 14}, "seller_moves_out", "2026-11-13"),
            (["Y", "Z"], {"buyer_attorney_date": "2026-10-02"}, "buyer_attorney", "2026-10-02"),
            (["Mold Inspection", "GG"], {}, "mold", "2026-10-15"),  # ED + 20
            (["Mold Inspection", "GG"], {}, "compensation_agreement", "2026-09-28"),  # ED + 3
            (["Mold Inspection", "GG"], {}, "compensation_cancel", "2026-10-01"),
        ]
        for riders, contract, key, want in cases:
            with self.subTest(riders=riders, key=key):
                self.assertEqual(by_key(timeline.analyze(self.deal(riders, **contract)))[key]["when"][:10], want)
        self.assertIn("buyer_sale_closes", {x["key"] for x in timeline.analyze(self.deal(["Sale of Buyer's Property"]))["pending"]})
        r = timeline.analyze(self.deal(["Y", "Z"], buyer_attorney_date="2026-10-02"))
        self.assertTrue(by_key(r)["buyer_attorney"]["contingency"])
        self.assertIn("seller_attorney", {x["key"] for x in r["pending"]})

    def test_rider_names(self):
        """Riders are read by name through contract_forms: "va" is a whole word, a hyphenated name maps, and a name that
        isn't a CR-7 rider is noted, never dropped silently."""
        r = timeline.analyze(fha(riders=["Private Well and Septic", "Vacant Land"], financing="conventional"))
        self.assertNotIn("appraisal", by_key(r))
        self.assertNotIn("fha_va_appraisal", r["flag_keys"])
        self.assertIn("rider_not_read", r["note_keys"])
        self.assertIn("appraisal", by_key(timeline.analyze(fha(riders=["Appraisal Contingency"], financing="conventional"))))
        r = timeline.analyze(fha(riders=["Short-Sale Rider"]))
        self.assertIn("short_sale_approval", by_key(r))
        self.assertNotIn("rider_not_read", r["note_keys"])

    def test_label_and_citations_name_the_riders(self):
        """The header label lists the riders on both forms; the closing row cites the riders that set it."""
        self.assertEqual(timeline.analyze(fixture("buyer-fha.json"))["contract_label"], "AS IS · Riders E, H")
        self.assertTrue(timeline.analyze(fixture("standard-riders.json"))["contract_label"].startswith("Standard"))
        d = fixture("short-sale.json")
        d["contract"]["riders"] = list(d["contract"].get("riders") or []) + ["U"]
        d["contract"]["short_sale_approval_received"] = "2026-10-20"
        self.assertEqual(by_key(timeline.analyze(d))["closing"]["source"], "Rider G, Para. 6 · possession Rider U")
        self.assertEqual(by_key(timeline.analyze(fixture("buyer-fha.json")))["closing"]["source"], "Para. 4 · possession Para. 6")

    def test_rider_h_coverage(self):
        """`insurance_coverage` records which boxes are checked; unrecorded is asked."""
        d = fixture("buyer-fha.json")
        self.assertIn("rider_h_boxes", timeline.analyze(d)["note_keys"])
        for coverage in ("homeowners", "Homeowner's"):
            d["contract"]["insurance_coverage"] = coverage
            r = timeline.analyze(d)
            self.assertIn("insurance", by_key(r))
            self.assertNotIn("flood_insurance", by_key(r))
            self.assertNotIn("rider_h_boxes", r["note_keys"])
            self.assertEqual(r["warning_keys"], [])
        d["contract"]["insurance_coverage"] = "flood"  # (b) only: the one date may sit in insurance_days
        rows = by_key(timeline.analyze(d))
        self.assertNotIn("insurance", rows)
        self.assertEqual(rows["flood_insurance"]["when"][:10], "2026-10-05")
        d["contract"]["insurance_coverage"] = "both"
        self.assertTrue({"insurance", "flood_insurance"} <= set(by_key(timeline.analyze(d))))
        d["contract"]["insurance_coverage"] = "wind"
        with self.assertRaisesRegex(timeline.DealError, "insurance_coverage"):
            timeline.analyze(d)
        rows = by_key(timeline.analyze(fha(riders=["E", "H"], insurance_flood=True, flood_insurance_date="2026-10-15")))
        self.assertEqual(rows["flood_insurance"]["when"], "2026-10-15 23:59")
        # days in Rider H's date blank don't say which way they count: if_changed gives the date counted back from
        # closing; `insurance_days_before` records that reading.
        d = fixture("buyer-fha.json")  # insurance_days 10: Mon Oct 5 after the Effective Date, Tue Oct 20 before closing
        r = timeline.analyze(d)
        alt = next(x for x in r["if_changed"] if x["note_key"] == "insurance_days_reading")
        self.assertEqual([(x["key"], x["date_display"]) for x in alt["rows"]], [("insurance", "Tue Oct 20")])
        self.assertEqual(by_key(r)["insurance"]["date_display"], "Mon Oct 5")
        d["contract"]["insurance_days_before"] = d["contract"].pop("insurance_days")
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["insurance"]["date_display"], "Tue Oct 20")
        self.assertNotIn("insurance_days_reading", r["note_keys"])
        self.assertEqual(r["warning_keys"], [])

    def test_occupancy_riders(self):
        """Riders T and U agreements are critical; Rider U alone asks about Para. 6(b) unless the occupancy answers it,
        and a tenancy dates 6(b)'s windows."""
        rows = by_key(timeline.analyze(fha(riders=["E", "H", "T", "U"], seller_occupancy_days=5)))
        self.assertTrue(rows["pre_closing_agreement"]["critical"])
        self.assertTrue(rows["post_closing_agreement"]["critical"])
        d = fha(riders=["E", "U"], seller_occupancy_days=3)
        for occupancy, asked in ((None, True), ("owner", False), ("vacant", False), ("tenant", True)):
            d["contract"]["occupancy"] = occupancy
            if occupancy is None:
                d["contract"].pop("occupancy")
            self.assertEqual("rider_u_6b" in timeline.analyze(d)["note_keys"], asked, occupancy)
        d["contract"]["occupancy"] = "owner-occupied"
        with self.assertRaisesRegex(timeline.DealError, "occupancy"):
            timeline.analyze(d)
        d["contract"].pop("occupancy")
        d["contract"]["tenants"] = True
        r = timeline.analyze(d)
        self.assertNotIn("rider_u_6b", r["note_keys"])
        self.assertEqual(by_key(r)["lease_disclosure"]["when"], "2026-09-30 23:59")  # 5 days after Fri Sep 25
        self.assertIsNone(by_key(r)["lease_review"]["when"])  # runs from the receipt of the leases
        s = fixture("short-sale.json")
        s["completed"] = {"deposit": "2026-09-23", "compensation_agreement": "2026-09-23"}
        self.assertIn("rider_u_6b", timeline.analyze(s)["note_keys"])

    def test_year_built_and_rider_p(self):
        """A home built before 1978 without Rider P, and Rider P without the year, are asked; Rider P dates the 10-day
        risk assessment unless waived; `built_before_1978` answers the question without the year."""
        d = fixture("buyer-fha.json")
        d["contract"]["year_built"] = 1965
        r = timeline.analyze(d)
        self.assertIn("year_built_without_rider_p", r["note_keys"])
        self.assertIn("lead_paint", by_key(r))
        d["contract"].pop("year_built")
        d["contract"]["riders"] = ["E", "H", "P"]
        r = timeline.analyze(d)
        self.assertIn("rider_p_year_built", r["note_keys"])
        self.assertIn("lead_paint", by_key(r))
        d["contract"]["lbp_waived"] = True
        self.assertNotIn("lead_paint", by_key(timeline.analyze(d)))
        d["contract"].update(year_built=1994, riders=["E", "H"], lbp_waived=False)
        self.assertFalse({"rider_p_year_built", "year_built_without_rider_p"} & set(timeline.analyze(d)["note_keys"]))
        d["contract"].pop("year_built")
        d["contract"]["built_before_1978"] = False
        r = timeline.analyze(d)
        self.assertNotIn("lead_paint", by_key(r))
        self.assertFalse({"rider_p_year_built", "year_built_without_rider_p"} & set(r["note_keys"]))
        d["contract"]["riders"] = ["E", "H", "P"]
        self.assertIn("rider_p_year_built", timeline.analyze(d)["note_keys"])
        d["contract"].update(riders=["E", "H"], built_before_1978=True)
        r = timeline.analyze(d)
        self.assertIn("lead_paint", by_key(r))
        self.assertIn("year_built_without_rider_p", r["note_keys"])
        for bad, field in (({"year_built": 1985}, "disagree"), ({"built_before_1978": "no"}, "built_before_1978")):
            e = dict(d["contract"], **bad)
            with self.assertRaisesRegex(timeline.DealError, field):
                timeline.analyze(dict(d, contract=e))

    def test_repair_limits(self):
        """The Standard form's repair limits come from contract_forms; none on AS IS or with Rider K."""
        d = fixture("standard-riders.json")
        d["contract"]["price"] = 445000
        r = timeline.analyze(d)
        self.assertEqual((r["repair_limits"]["general"], r["repair_limits"]["blank"]), (6675, ["general", "wdo", "permit"]))
        self.assertIn("repair_limits_blank", r["note_keys"])
        d["contract"]["repair_limits"] = {"general": 5000, "wdo": 0.01, "permit": 2000}
        r = timeline.analyze(d)
        self.assertEqual((r["repair_limits"]["wdo"], r["repair_limits"]["blank"]), (4450, []))
        self.assertNotIn("repair_limits_blank", r["note_keys"])
        d["contract"]["riders"] = ["K"]
        self.assertIsNone(timeline.analyze(d)["repair_limits"])


class RiderGG(unittest.TestCase):
    """Rider GG: the compensation agreement within 3 days, then the buyer's cancel window."""

    def gg(self, **completed):
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"]["riders"]) + ["GG"]
        d["completed"] = completed
        return d

    def test_signed_agreement_closes_the_cancel_window(self):
        """With the agreement signed the cancel right can't arise: the window is done, voided, no star, off page 1 and
        the calendar, never the next deadline or the end of the contingencies. A done date before the window's own date
        is refused unless the buyer ended it in writing."""
        d = self.gg(deposit="2026-09-26", compensation_agreement="2026-09-26")
        r = timeline.analyze(d)
        row = by_key(r)["compensation_cancel"]
        self.assertTrue(by_key(r)["compensation_agreement"]["done"])
        self.assertTrue(row["done"] and row["voided"] and not row["critical"])
        self.assertNotEqual(r["first_deadline"]["key"], "compensation_cancel")
        self.assertNotEqual(r["contingencies_end"]["key"], "compensation_cancel")
        self.assertNotIn("compensation_cancel", {x["key"] for x in timeline_render.page_one_rows(r)})
        self.assertNotIn("UID:compensation_cancel-", timeline_render.ics(r))
        open_r = timeline.analyze(self.gg())
        self.assertTrue(by_key(open_r)["compensation_cancel"]["critical"])
        self.assertIn("compensation_cancel", {x["key"] for x in timeline_render.page_one_rows(open_r)})
        self.assertIn("UID:compensation_cancel-", timeline_render.ics(open_r))
        d["completed"]["compensation_cancel"] = "2026-09-26"  # Thu Oct 1 is still ahead
        with self.assertRaisesRegex(timeline.DealError, "compensation_cancel"):
            timeline.analyze(d)
        d["completed"]["compensation_cancel"] = "2026-10-01"
        self.assertTrue(by_key(timeline.analyze(d))["compensation_cancel"]["done"])
        d["completed"]["compensation_cancel"] = "2026-09-26"
        d["ended_in_writing"] = ["compensation_cancel"]
        self.assertTrue(by_key(timeline.analyze(d))["compensation_cancel"]["done"])
        s = fixture("short-sale.json")
        s["completed"] = {"deposit": "2026-09-23", "compensation_agreement": "2026-09-23"}
        self.assertNotIn("short_sale_gg", timeline.analyze(s)["note_keys"])

    def test_rolled_agreement_day(self):
        """Day 3 on a Sunday rolls to Monday; the cancel window counts from Monday and the other reading is noted."""
        d = fha(effective_date="2026-09-24", riders=["E", "GG"])
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["compensation_agreement"]["when"][:10], "2026-09-28")
        self.assertEqual(by_key(r)["compensation_cancel"]["when"][:10], "2026-10-01")
        self.assertIn("gg_rolled_start", r["note_keys"])
        self.assertIn("gg_rolled_start", timeline.analyze(d, "seller")["note_keys"])
        d["contract"]["effective_date"] = "2026-09-25"  # day 3 is a Monday: one reading
        self.assertNotIn("gg_rolled_start", timeline.analyze(d)["note_keys"])


class ShortSale(unittest.TestCase):
    """Rider G: Phase 1 counts from the Effective Date; every other period, and the closing, from the approval."""

    def test_after_approval_rows_get_dates(self):
        deal = fixture("short-sale.json")
        deal["amendments"] = [{"date": "2026-11-02", "description": "Short sale approval received",
                               "changes": {"short_sale_approval_received": "2026-11-02"}}]
        r = timeline.analyze(deal)
        rows = by_key(r)
        self.assertEqual(rows["loan_app"]["when"], "2026-11-09 23:59")  # Sat Nov 7, extended
        self.assertEqual(rows["inspection"]["when"], "2026-11-12 23:59")  # Veterans Day Wed Nov 11 isn't the end
        self.assertEqual(rows["loan_approval"]["when"], "2026-12-02 23:59")
        self.assertEqual(rows["closing"]["when"], "2026-12-17 10:00")  # approval + 45
        self.assertEqual(rows["deposit"]["when"], "2026-09-25 23:59")  # Phase 1 doesn't move
        self.assertNotIn("short_sale_expires", rows)
        self.assertTrue(rows["short_sale_approval"]["done"])
        self.assertEqual(r["contingencies_end"]["key"], "loan_approval")
        self.assertIsNone(rows["inspection"]["was"])  # it had no date before, so nothing "moved"
        self.assertEqual(r["moved"], [])
        self.assertIn("Closing", [x["label"] for x in r["newly_dated"]])
        deal = fixture("short-sale.json")
        deal["contract"].update(short_sale_approval_received="2026-11-02", date_overrides={"closing": "2026-12-11"})
        self.assertEqual(by_key(timeline.analyze(deal))["closing"]["when"], "2026-12-11 10:00")

    def test_late_approval_is_flagged(self):
        """Approval deadline Mon Nov 23 (ED + 60, extended); the contract expires 30 days later (Wed Dec 23)."""
        deal = fixture("short-sale.json")
        for received, flag in (("2026-11-30", "short_sale_after_deadline"), ("2027-01-04", "short_sale_after_expiration"),
                               ("2026-11-02", None)):
            deal["contract"]["short_sale_approval_received"] = received
            keys = set(timeline.analyze(deal)["flag_keys"]) & {"short_sale_after_deadline", "short_sale_after_expiration"}
            self.assertEqual(keys, {flag} if flag else set(), received)

    def test_preapproval_expiry_before_a_closing_date(self):
        """No closing date yet: the expiry is compared with the approval deadline plus the closing days."""
        d = fixture("short-sale.json")
        d["contract"]["preapproval_expires"] = "2026-12-16"
        self.assertIn("preapproval_expires", timeline.analyze(d)["note_keys"])
        d["contract"]["preapproval_expires"] = "2027-02-01"
        self.assertNotIn("preapproval_expires", timeline.analyze(d)["note_keys"])


class Amendments(unittest.TestCase):
    """Amendments and extensions: what moved, and the two readings of an extension added to a rolled date."""

    def test_extension_readings(self):
        """8 days from Fri Sep 25 is Sat Oct 3, rolled to Mon Oct 5. Extended to 13 days: Thu Oct 8 (counted from the
        Effective Date, used); 5 days added to Mon Oct 5 would be Tue Oct 13 (the other reading, noted)."""
        d = fha(inspection_days=8)
        d["amendments"] = [{"date": "2026-09-26", "description": "EA-4", "changes": {"inspection_days": 13}}]
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["inspection"]["when"][:10], "2026-10-08")
        self.assertIn("extension_reading:inspection", r["note_keys"])
        d["contract"]["inspection_days"] = 10  # Mon Oct 5 didn't roll: one reading
        d["amendments"][0]["changes"]["inspection_days"] = 15
        self.assertNotIn("extension_reading:inspection", timeline.analyze(d)["note_keys"])
        # when the reading used has ended but the later one is open on the report date, it's a flag too
        d = fha(effective_date="2026-09-23", inspection_days=10, financing="cash", closing_date="2026-11-06")
        d["amendments"] = [{"date": "2026-10-01", "name": "Extension Addendum (EA-4)", "changes": {"inspection_days": 15}}]
        for report, completed, flagged in (("2026-10-12", {}, True), ("2026-10-14", {}, False),
                                           ("2026-10-12", {"inspection": "2026-10-08"}, False)):
            d.update(report_date=report, completed=completed)
            r = timeline.analyze(d)
            self.assertEqual("extension_reading_open:inspection" in r["flag_keys"], flagged, (report, completed))
            if not completed:
                self.assertTrue(by_key(r)["inspection"]["past"])

    def test_moved_named_and_summarized(self):
        """The closing leads the moved list; an amendment keeps the name it's given; fields read as labels."""
        d = fixture("buyer-fha.json")
        d["amendments"] = [{"date": "2026-09-28", "name": "Extension Addendum (EA-4)",
                            "changes": {"closing_date": "2026-11-06", "loan_approval_days": 37}}]
        r = timeline.analyze(d)
        self.assertEqual(r["moved"][0]["label"], "Closing")
        self.assertGreater(len(r["moved"]), 2)
        self.assertEqual(r["history"][0]["name"], "Extension Addendum (EA-4)")
        self.assertEqual(timeline._field_label("rofr_days"), "ROFR")
        self.assertEqual(timeline._field_value("price", 412000), "$412,000")
        summary = timeline.analyze(fixture("seller-amended.json"))["history"][0]["summary"]
        self.assertNotIn("_", summary)  # field names never reach the summary

    def test_future_effective_date_and_what_if(self):
        d = fixture("buyer-fha.json")
        d["report_date"] = "2026-09-20"
        d["amendments"] = [{"date": "2026-09-28", "description": "Extend", "changes": {"loan_approval_days": 25}}]
        keys = timeline.analyze(d)["note_keys"]
        self.assertIn("effective_after_report", keys)
        self.assertIn("amendment_after_report", keys)
        d["what_if"] = True
        self.assertNotIn("effective_after_report", timeline.analyze(d)["note_keys"])


class Notes(unittest.TestCase):
    """Questions for the agent and flags, by key."""

    def test_questions_give_the_other_dates(self):
        """Rider F fields with only Rider E, and the other financing's title default, are asked with the dates that
        apply if the answer changes; the run itself is unchanged."""
        d = fha(appraisal_days=21, title_evidence_days_before=5)
        r = timeline.analyze(d)
        self.assertTrue({"appraisal_without_rider_f", "title_days_financing"} <= set(r["note_keys"]))
        self.assertNotIn("appraisal_due", by_key(r))
        alts = {x["note_key"]: x for x in r["if_changed"]}
        self.assertEqual([x["key"] for x in alts["appraisal_without_rider_f"]["rows"]], ["appraisal_due", "appraisal"])
        self.assertEqual(alts["title_days_financing"]["rows"][0]["date_display"], "Thu Oct 15")
        d["contract"]["title_evidence_days_before"] = 15
        del d["contract"]["appraisal_days"]
        self.assertFalse({"appraisal_without_rider_f", "title_days_financing"} & set(timeline.analyze(d)["note_keys"]))
        d = fixture("buyer-fha.json")
        alt = next(x for x in timeline.analyze(d)["if_changed"] if x["note_key"] == "flood_zone_unknown")
        self.assertEqual([(x["key"], x["date_display"]) for x in alt["rows"]], [("flood_elevation", "Thu Oct 15")])
        for zone in ("none", "X"):
            d["contract"]["flood_zone"] = zone
            self.assertNotIn("flood_zone_unknown", timeline.analyze(d)["note_keys"])

    def test_money_check(self):
        """Deposits + loan + balance vs. price, and the pre-approval vs. the loan."""
        d = fha(loan_amount=348000, balance_to_close=6000, preapproval_amount=350000)  # $365,000; $11,000 deposit
        r = timeline.analyze(d)
        self.assertFalse({"money_mismatch", "preapproval_below_loan"} & set(r["note_keys"]))
        d["contract"].update(price=372000, preapproval_amount=340000)  # a counter moved the price, not the loan
        self.assertTrue({"money_mismatch", "preapproval_below_loan"} <= set(timeline.analyze(d)["note_keys"]))
        d["contract"].pop("balance_to_close")
        d["contract"]["loan_amount"] = 362000  # no balance given: $11,000 + $362,000 passes the $372,000 price
        self.assertIn("money_mismatch", timeline.analyze(d)["note_keys"])
        with self.assertRaisesRegex(timeline.DealError, "loan_amount"):
            timeline.money_check({"loan_amount": "a lot"}, 365000)

    def test_form_defaults_are_noted(self):
        """Each blank period the script fills with a form or rider default gets a default:<row> note."""
        d = fixture("buyer-fha.json")
        for k in ("deposit_days", "loan_application_days", "loan_approval_days", "inspection_days"):
            d["contract"].pop(k)
        keys = timeline.analyze(d)["note_keys"]
        for k in ("default:deposit", "default:loan_app", "default:loan_approval", "default:inspection"):
            self.assertIn(k, keys)
        s = fixture("standard-riders.json")
        s["contract"]["riders"] = ["L"]
        s["contract"].pop("inspection_days", None)
        self.assertIn("default:inspection", timeline.analyze(s)["note_keys"])
        d = fha(riders=["A", "U"], association_approval=True, seller_occupancy_days=5,
                blanks=["post_closing_agreement_days_before", "association_approval_days_before"])
        r = timeline.analyze(d)
        self.assertTrue({"default:post_closing_agreement", "default:assoc_apply", "default:assoc_approval"} <= set(r["note_keys"]))
        d["contract"].update(post_closing_agreement_days_before=7, association_apply_days=3, association_approval_days_before=7)
        keys = timeline.analyze(d)["note_keys"]
        self.assertFalse({"default:post_closing_agreement", "default:assoc_apply", "default:assoc_approval"} & set(keys))
        s = fixture("short-sale.json")
        s["contract"]["short_sale_closing_days"] = 30
        self.assertNotIn("default:closing", timeline.analyze(s)["note_keys"])
        self.assertNotIn("default:closing", timeline.analyze(fixture("buyer-fha.json"))["note_keys"])  # no Rider G

    def test_blanks_field(self):
        """`blanks` accepts every documented period; a printed term (survey, walk-through, Rider P's 10 days) or an
        unknown name is a deal-file warning, never an agent note."""
        d = fixture("short-sale.json")
        d["contract"].update(flood_zone="AE", blanks=["flood_elevation_days", "short_sale_closing_days", "mold_days",
                                                        "rezoning_date"])
        r = timeline.analyze(d)
        self.assertNotIn("blanks_unknown", r["warning_keys"] + r["note_keys"])
        self.assertTrue({"default:closing", "default:flood_elevation"} <= set(r["note_keys"]))
        d = fha(riders=["E", "H", "P"], year_built=1965)
        self.assertFalse({"default:survey", "default:walkthrough", "default:lead_paint"} & set(timeline.analyze(d)["note_keys"]))
        for field in ("survey_days_before", "walkthrough_days_before", "lead_paint_days", "repair_limit"):
            d["contract"]["blanks"] = ["title_evidence_days_before", field]
            r = timeline.analyze(d)
            self.assertIn("blanks_unknown", r["warning_keys"], field)
            self.assertNotIn("blanks_unknown", r["note_keys"])
            warning = r["warnings"][r["warning_keys"].index("blanks_unknown")]
            self.assertIn(field, warning)
            self.assertNotIn("title_evidence_days_before", warning)

    def test_unknown_contract_keys_warn(self):
        """A misspelled field comes back as a warning, in the contract and in an amendment's changes."""
        d = fixture("buyer-fha.json")
        self.assertEqual(timeline.analyze(d)["warnings"], [])
        d["contract"]["inspection_dayz"] = 7
        d["amendments"] = [{"date": "2026-09-28", "changes": {"closing_dat": "2026-11-06"}}]
        r = timeline.analyze(d)
        self.assertEqual(r["warning_keys"], ["unknown_key", "unknown_key"])
        self.assertIn("inspection_dayz", r["warnings"][0])
        self.assertIn("closing_dat", r["warnings"][1])

    def test_other_contract_rule_questions(self):
        """No closing-date note unless a row counts back from closing; the market's note reaches the agent."""
        quick = {"side": "buyer", "state": "OH", "report_date": "2026-11-20", "rules": {"day_count": "business"},
                 "contract": {"form_family": "other", "effective_date": "2026-11-20"},
                 "deadlines": [{"key": "due_diligence", "label": "Due Diligence Period Ends", "basis": "after", "days": 7,
                                "party": "Buyer", "time": "17:00"}]}
        r = timeline.analyze(quick)
        self.assertIn("rules_unknown", r["note_keys"])
        self.assertNotIn("no_closing_date", r["note_keys"])
        quick["deadlines"].append({"key": "walk", "label": "Walk-Through", "basis": "before", "days": 1, "party": "Buyer"})
        self.assertIn("no_closing_date", timeline.analyze(quick)["note_keys"])
        d = fixture("buyer-fha.json")
        d["county"] = "Semnole"  # a misspelled county: the market's note is passed on
        self.assertIn("market", timeline.analyze(d)["note_keys"])
        self.assertIn("closing_time_assumed", timeline.analyze(fha(closing_time=None))["note_keys"])


class AgentNotes(unittest.TestCase):
    """Notes the agent adds to the deal file: passed on once, merged with the script's own or joined to their row."""

    def test_merged_joined_and_passed_on(self):
        d = fha(loan_amount=358000, balance_to_close=1000)  # doesn't add up: money_mismatch
        d["report_date"] = "2026-10-02"  # the deposit is past and not done
        d["agent_notes"] = [{"key": "money_mismatch", "text": "Which figures stand?"},
                            {"key": "deposit", "text": "No escrow receipt in the package."},
                            {"key": "other", "text": "The seller asked to keep the curtains."}, "A plain note."]
        r = timeline.analyze(d)
        self.assertEqual(r["merged_agent_notes"], ["money_mismatch"])
        self.assertIn("deposit", r["joined_agent_notes"])
        self.assertIn("The seller asked to keep the curtains.", r["agent_notes"])
        self.assertIn("A plain note.", r["agent_notes"])
        self.assertFalse(any("Which figures stand?" in n for n in r["agent_notes"]))
        self.assertEqual(len(r["note_keys"]), len(set(r["note_keys"])))

    def test_joined_once_and_repeats_dropped(self):
        d = fixture("buyer-fha.json")
        d["contract"]["riders"] = list(d["contract"]["riders"]) + ["GG"]
        d["agent_notes"] = [{"key": "compensation_agreement", "text": "Has it been signed?"},
                            {"key": "compensation_agreement", "text": "Ask the listing agent."}]
        r = timeline.analyze(d)
        self.assertEqual(r["joined_agent_notes"], ["compensation_agreement"])
        self.assertEqual(len([n for n in r["agent_notes"] if "Has it been signed?" in n and "Ask the listing agent." in n]), 1)
        self.assertNotIn("Ask the listing agent.", r["agent_notes"])
        d["report_date"] = "2026-10-02"  # the Past, Confirm note only lists the row: the agent's note still reaches the agent
        r = timeline.analyze(d)
        self.assertNotIn("compensation_agreement", r["merged_agent_notes"])
        self.assertTrue(any("Has it been signed?" in n for n in r["agent_notes"]))
        d = fixture("buyer-fha.json")
        d["agent_notes"] = ["Confirm the delivery date", "Confirm the delivery date"]
        self.assertEqual(timeline.analyze(d)["agent_notes"].count("Confirm the delivery date"), 1)
        d = fha(preapproval_expires="2026-10-20")
        r = timeline.analyze(d)
        flag = r["flags"][r["flag_keys"].index("loan_approval_near_closing")]
        note = r["agent_notes"][r["note_keys"].index("preapproval_expires")]
        d.update(flags=[flag], agent_notes=[note])  # the agent restates the script's own flag and note
        r = timeline.analyze(d)
        self.assertEqual(len(r["flags"]), len({f.lower() for f in r["flags"]}))
        self.assertEqual(r["agent_notes"].count(note), 1)

    def test_dedupe_is_by_key_and_check_lines_are_the_scripts(self):
        """The agent's notes are deduplicated by key, never by wording; a deal file's own flags never print on the
        report: they reach the agent as notes unless keyed to a Check line the script raised."""
        d = fha(preapproval_expires="2026-10-20")
        paraphrase = "Ask the lender to extend the pre-approval, which expires before closing"
        d["agent_notes"] = [paraphrase, {"key": "default:title", "text": "Title days were blank"}]
        d["flags"] = [{"key": "loan_approval_near_closing", "text": "Loan approval is tight"},
                      {"key": "after_closing", "text": "Inspection ends after closing"}, "Seller asked about the shed"]
        r = timeline.analyze(d)
        self.assertIn(paraphrase, r["agent_notes"])  # other words, no key: passed on as written
        self.assertIn("default:title", r["merged_agent_notes"])
        self.assertIn("loan_approval_near_closing", r["merged_agent_notes"])
        self.assertNotIn("after_closing", r["flag_keys"])  # a key the script didn't raise is an agent note, not a Check line
        self.assertIn("Inspection ends after closing", r["agent_notes"])
        self.assertIn("Seller asked about the shed", r["agent_notes"])
        self.assertTrue(set(r["flag_keys"]) <= timeline.FLAG_KEYS)
        self.assertEqual(len(r["flags"]), len(r["flag_keys"]))
        for text in ("Loan approval is tight", "Inspection ends after closing", "Seller asked about the shed"):
            self.assertNotIn(text, " ".join(r["flags"]))


class OtherContracts(unittest.TestCase):
    """Any contract but FAR/BAR: best effort from the deal file's own deadlines and rules."""

    def test_period_counts_from_its_receipt(self):
        deal = fixture("other-contract.json")
        base = by_key(timeline.analyze(deal))["title_commitment"]["when"]
        row = next(x for x in deal["deadlines"] if x["key"] == "title_commitment")
        row["receipt_date"] = str(date.fromisoformat(row["receipt_date"]) + timedelta(days=7))
        moved = by_key(timeline.analyze(deal))["title_commitment"]["when"]
        self.assertEqual((datetime.fromisoformat(moved) - datetime.fromisoformat(base)).days, 7)

    def test_support_notes_are_chat_only(self):
        """The best-effort disclaimer and the FAR/BAR revision note go in chat_notes only: never agent_notes (which can
        reach a template), the PDF or the calendar."""
        r = timeline.analyze(fixture("other-contract.json"))
        self.assertEqual(r["support"], "best_effort")
        self.assertEqual(r["chat_notes"], [timeline.cf.BEST_EFFORT_NOTE])
        f = timeline.analyze(fha(form_revision="FloridaRealtors/FloridaBar-ASIS-8 Rev. 1/27"))
        self.assertEqual(f["support"], "full")
        self.assertEqual(len(f["chat_notes"]), 1)
        for t in (r, f):
            note = t["chat_notes"][0]
            self.assertNotIn(note, t["agent_notes"])
            self.assertNotIn(timeline_render.esc(note), timeline_render.build_html(t, {}, sample=True))
            self.assertNotIn(note[:40], timeline_render.ics(t))

    def test_no_farbar_consequence(self):
        """Another contract's closing carries only the consequence the deal file records."""
        d = fixture("other-contract.json")
        self.assertEqual(by_key(timeline.analyze(d))["closing"]["if_missed"], "")
        d["contract"]["closing_if_missed"] = "Either party may terminate after written notice (Para. 14)"
        r = timeline.analyze(d)
        self.assertEqual(by_key(r)["closing"]["if_missed"], d["contract"]["closing_if_missed"])
        self.assertNotIn("unknown_key", r["warning_keys"])
        self.assertNotIn("deposit", timeline.analyze(fixture("ohio-manual-v5.json"))["critical_legend"])

    def test_party_words(self):
        """A party named inside a sentence of the deal file's text reads in lower case; a sentence start or a name that
        runs on stays."""
        for text, want in (("Deliver the Seller's Disclosure to the Buyer", "Deliver the Seller's Disclosure to the buyer"),
                           ("Buyer accepts the property", "Buyer accepts the property"),
                           ("Buyer in default; Seller may cancel", "Buyer in default; the seller may cancel"),
                           ("Notify the Buyer's lender", "Notify the buyer's lender")):
            self.assertEqual(timeline.party_words(text), want)


class Validation(unittest.TestCase):
    """Bad or missing inputs are a DealError naming the field, never a guess."""

    def test_bad_inputs(self):
        def drop(*path):
            def go(d):
                obj = d
                for p in path[:-1]:
                    obj = obj[p]
                del obj[path[-1]]
            return go

        def contract(**kw):
            return lambda d: d["contract"].update(kw)

        def builder(d):
            d.update(state="FL", county="Orange")
            d["contract"]["form"] = "Builder Purchase Agreement"  # a Florida contract that isn't FAR/BAR gets no FAR/BAR rules
            d.pop("rules")
        cases = [
            ("buyer-fha.json", contract(closing_date="2026-09-20"), "closing"),  # closing before the Effective Date
            ("buyer-fha.json", contract(inspection_days=-3), "inspection_days"),
            ("buyer-fha.json", contract(closing_date="2026-11-31"), "contract.closing_date is '2026-11-31'"),
            ("buyer-fha.json", drop("state"), "state"),  # never Florida by default
            ("buyer-fha.json", drop("contract", "effective_date"), "effective_date"),
            ("buyer-fha.json", contract(title_by="lender"), "title_by"),
            ("buyer-fha.json", lambda d: d.update(report_date="Sept 26"), "report_date"),
            ("buyer-fha.json", lambda d: d.update(completed={"earnest": "2026-09-26"}), "not a deadline"),
            ("buyer-fha.json", lambda d: d.update(deadlines=[{"key": "x", "label": "X", "basis": "before", "party": "Buyer"}]),
             "needs days"),
            ("buyer-fha.json", lambda d: d.update(deadlines=[{"key": "y", "label": "Y", "basis": "after", "days": 2}]),
             "needs party"),
            ("buyer-fha.json", lambda d: d.update(deadlines=[{"key": "inspection", "label": "Dup", "basis": "after",
                                                              "days": 20, "party": "Buyer"}]), "used twice"),
            ("buyer-fha.json", lambda d: d.update(deadlines=[{"key": "x", "label": "X", "basis": "after", "days": 3,
                                                              "time": "closing", "party": "Buyer"}]), "basis before"),
            ("buyer-fha.json", lambda d: d.update(deadlines=[{"key": "x", "label": "X", "basis": "after", "days": 3,
                                                              "party": "Buyer", "event": "yes"}]), "event 'yes'"),
            ("other-contract.json", drop("rules"), "rules"),
            ("other-contract.json", drop("rules", "day_count"), "day_count"),
            ("other-contract.json", drop("deadlines"), ""),
            ("other-contract.json", lambda d: d["rules"].update(holidays="state"), "us_federal"),
            ("other-contract.json", builder, "rules"),
        ]
        for name, mutate, message in cases:
            with self.subTest(fixture=name, message=message):
                d = fixture(name)
                mutate(d)
                with self.assertRaisesRegex(timeline.DealError, message):
                    timeline.analyze(d)
        self.assertEqual(timeline.analyze(fha(price="$412,000"))["price"], "$412,000")  # a written price passes

    def test_cli_reports_problems_as_json(self):
        deal = fixture("buyer-fha.json")
        del deal["contract"]["effective_date"]
        out = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "deal.json")
            with open(path, "w") as f:
                json.dump(deal, f)
            with contextlib.redirect_stdout(out):
                code = timeline.main([path])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out.getvalue())["ok"])


if __name__ == "__main__":
    unittest.main()
