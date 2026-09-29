"""The mock contract generator (dev/mock_contracts, docs/mock-contracts.md). Local only: skipped without PyMuPDF
(dev/requirements-tools.txt) or the FR/BAR PDFs in the git-ignored sources/Contracts/FARBAR/."""
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
MOCK = os.path.join(ROOT, "dev", "mock_contracts")
sys.path.insert(0, MOCK)
sys.path.insert(0, ROOT)

try:
    import pymupdf  # noqa: F401
    HAVE_TOOLS = os.path.isdir(os.path.join(ROOT, "sources", "Contracts", "FARBAR"))
except ImportError:
    HAVE_TOOLS = False

if HAVE_TOOLS:
    import build  # noqa: E402
    import fields  # noqa: E402
    import locate  # noqa: E402
    import scenario as sc  # noqa: E402


def spec(name):
    with open(os.path.join(MOCK, "scenarios", f"{name}.json")) as f:
        return json.load(f)


@unittest.skipUnless(HAVE_TOOLS, "PyMuPDF (dev/requirements-tools.txt) or sources/Contracts/FARBAR/ missing")
class FieldMaps(unittest.TestCase):
    def test_every_map_resolves_on_its_form(self):
        """Every anchor in every committed map finds a blank, and the map's revision is the manifest's."""
        for path in sorted(os.listdir(fields.FIELDS_DIR)):
            family = path[:-5]
            with self.subTest(family=family):
                _, found, m = fields.form_blanks(family)
                for name, f in m["fields"].items():
                    self.assertTrue(fields.resolve(found, f["at"]), f"{family} {name}: {f['at']}")
                for role, at in m.get("roles", {}).items():
                    self.assertTrue(fields.resolve(found, at if isinstance(at, list) else [at]), f"{family} {role}")

    def test_auto_roles_on_an_unmapped_rider(self):
        """A form without a map still gets its parties, property, signatures or initials by their printed labels."""
        _, found, m = fields.form_blanks("CR-7_M")
        self.assertIsNone(m)
        roles = fields.auto_roles(found)
        for role in ("seller_names", "buyer_names", "property", "initials:buyer", "initials:seller"):
            self.assertIn(role, roles)


# One or more specs per mapped form that set every key its map prints: {key: (value, text on the page or None for a
# checkbox)}. Values are distinctive so they can't be mistaken for the form's own text.
ROUND_TRIP = {
    "CR-7_A": [{"association": ("Tern Isle Condominium Association, Inc.", "Tern Isle Condominium Association"),
                "management_company": ("Kestrel Association Services", "Kestrel Association Services"),
                "contact": ("Dana Ashcombe", "Dana Ashcombe"), "management_contact": ("Ellis Galloway", "Ellis Galloway"),
                "phone": ("(407) 555-0231", "555-0231"), "management_phone": ("(407) 555-0277", "555-0277"),
                "email": ("board@ternisle.example", "board@ternisle.example"),
                "management_email": ("help@kestrel.example", "help@kestrel.example"), "website": ("ternisle.example", "ternisle.example"),
                "fee": (465, "465.00"), "fee_period": ("quarterly", None), "approval_required": (True, None),
                "approval_days": (17, "17"), "approval_initiate_days": (6, "6"), "community": ("Tern Isle", None),
                "rofr": (True, None), "rofr_members": (False, None), "condo_docs_before_contract": (False, None)}],
    "CR-7_B": [{"community": ("Osprey Hammock", "Osprey Hammock"), "association": ("Osprey Hammock HOA, Inc.", "Osprey Hammock HOA"),
                "management_company": ("Kestrel Association Services", "Kestrel Association Services"),
                "contact": ("Dana Ashcombe", "Dana Ashcombe"), "phone": ("(407) 555-0231", "555-0231"),
                "email": ("board@ospreyhoa.example", "board@ospreyhoa.example"), "website": ("ospreyhoa.example", "ospreyhoa.example"),
                "fee": (140, "140.00"), "fee_period": ("month", "month"), "approval_required": (True, None),
                "approval_days": (12, "12"), "approval_initiate_days": (6, "6")}],
    "CR-7_C": [{"seller_financing": (48000, "48,000.00"), "rate": (6.875, "6.875"), "lien": ("second", None),
                "loan_type": ("amortized", None), "term_years": (25, "25"), "payment": (335.21, "335.21"),
                "payment_period": ("quarterly", None), "first_payment_months": (2, "2")},
               {"loan_type": ("balloon", None), "term_years": (30, "30"), "balloon_due_months": (84, "84")},
               {"loan_type": ("interest_only", None), "interest_only_months": (48, "48")}],
    "CR-7_D": [{"mortgage_balance": (212000, "212,000.00"), "rate_type": ("fixed", None), "rate": (3.375, "3.375"),
                "max_rate": (4.5, "4.5"), "fees_cap": (1800, "1,800.00")}],
    "CR-7_E": [{"repair_cap": (5475, "5,475.00"), "appraised_value": (371000, "371,000.00"),
                "fha_fees_max": (1250, "1,250.00"), "va_fees_max": (1350, "1,350.00")}],
    "CR-7_F": [{"appraisal_date": ("2026-10-19", "10/19/2026"), "appraised_value": (402000, "402,000.00")}],
    "CR-7_FF": [{"buyer_brokerage": ("Tidal Key Realty", "Tidal Key Realty"), "percent": (2.25, "2.25"),
                 "amount": (1500, "1,500.00"), "excess": ("reduce", None)}],
    "CR-7_G": [{"short_sale_application_days": (8, "8"), "short_sale_approval_days": (75, "75"),
                "short_sale_closing_days": (40, "40"), "backup_offers": ("b", None)}],
    "CR-7_GG": [{"between": ("seller", None), "compensation_agreement_days": (4, "4")}],
    "CR-7_H": [{"homeowners": (True, None), "homeowners_premium_max": (4200, "4,200.00"), "homeowners_premium_pct": (1.25, "1.25"),
                "insurance_date": ("2026-10-09", "10/09/2026"), "flood": (True, None), "flood_premium_max": (1900, "1,900.00"),
                "flood_premium_pct": (0.65, "0.65"), "flood_date": ("2026-10-12", "10/12/2026")}],
    "CR-7_K": [{"inspection_days": (12, "12")}],
    "CR-7_L": [{"inspection_days": (13, "13")}],
    "CR-7_N": [{"cccl_requested": (True, None)}, {"cccl_requested": (False, None)}],
    "CR-7_P": [{"lead_known": ("Peeling paint on the rear porch trim", "Peeling paint on the rear porch trim"),
                "records": ("1998 lead inspection report", "1998 lead inspection report"), "risk_assessment": ("received", None)}],
    "CR-7_S": [{"lease_type": ("option", None), "attorney_fees_by": ("buyer", None)}],
    "CR-7_T": [{"pre_closing_agreement_days": (7, "7"), "expense": ("buyer", None), "possession_date": ("2026-10-26", "10/26/2026"),
                "rent": (2150, "2,150.00")}],
    "CR-7_U": [{"post_closing_agreement_days_before": (9, "9"), "expense": ("seller", None), "rent_back_days": (21, "21"),
                "rent_back_monthly": (2400, "2,400.00")}],
    "CR-7_V": [{"buyer_property": ("4410 Larkwood Ave, Oviedo, FL 32765", "4410 Larkwood Ave"),
                "sale_contingency_date": ("2026-10-23", "10/23/2026"), "under_contract": (True, None)}],
    "CR-7_W": [{"backup_notice_date": ("2026-10-08", "10/08/2026")}],
    "CR-7_X": [{"kickout_deposit": (7500, "7,500.00")}],
    "CR-7_Z": [{"buyer_attorney_date": ("2026-09-30", "09/30/2026")}],
    "AGA": [{"gap_amount": (12000, "12,000.00"), "pay": ("finance", None), "valuation_days": (21, "21"), "renegotiate_days": (4, "4")}],
    "EAC": [{"escalation_amount": (3000, "3,000.00"), "maximum_price": (510000, "510,000.00"), "pay": ("finance", None),
             "revised_price": (505000, "505,000.00")}],
    "CCCLA": [{}],
    "CDDA": [{"district": ("HERON LAKE", "HERON LAKE"),
              "assessments": ([{"amount": 1150, "per": "year", "to": "Seminole County Tax Collector"},
                               {"amount": 780, "per": "quarter", "to": "Heron Lake CDD"}], "Heron Lake CDD")}],
    "NMOB": [{"deadline": ("2026-09-21 21:00", "09/21/2026"), "other": ("Include proof of funds with the offer.", "Include proof of funds")}],
    "CO": [{"number": (1, None), "price": (431500, "431,500.00"), "closing": ("2026-11-19", "11/19/2026"),
            "included": ("Patio furniture", "Patio furniture"), "excluded": ("Garage freezer", "Garage freezer"),
            "terms": ([{"line": 261, "text": "Inspection Period is changed to 12 days."}], "Inspection Period is changed to 12 days."),
            "deadline": ("2026-09-24 17:00", "09/24/2026")}],
    "EA": [{"closing": ("2026-11-13", "11/13/2026"), "loan_approval_extra_days": (7, "7"), "loan_approval_until": ("2026-11-02", "11/02/2026"),
            "inspection_extra_days": (5, "5"), "inspection_until": ("2026-10-09", "10/09/2026"),
            "title_cure_extra_days": (11, "11"), "title_cure_until": ("2026-11-06", "11/06/2026"),
            "short_sale_extra_days": (19, "19"), "short_sale_until": ("2026-12-18", "12/18/2026"),
            "sale_lease_extra_days": (13, "13"), "sale_lease_until": ("2026-11-04", "11/04/2026"),
            "due_diligence_extra_days": (9, "9"), "due_diligence_until": ("2026-10-16", "10/16/2026"),
            "except_terms": ("Buyer pays the rate lock extension fee.", "rate lock extension fee")}],
    "ACSP": [{"number": (2, None), "text": ("Seller shall leave the pool cleaning equipment.", "pool cleaning equipment")}],
    "CASSB": [{"between": ("seller", None), "percent": (2.75, "2.75"), "amount": (650, "650.00"), "term_days": (45, "45"),
               "other_terms": ("Paid at closing through the closing agent.", "through the closing agent")}],
    "SPDR": [{"occupancy": ("unoccupied", None), "vacant_since": ("March 2026", "March 2026")}],
    "SPDC": [{"occupancy": ("tenant", None)}],
    "FD": [{"copy_date": ("2026-09-18", "09/18/2026")}],
    "MISIRS": [{"association": ("Tern Isle Condominium Association, Inc.", "Tern Isle Condominium Association")}],
    "RCD": [{"condo_name": ("Tern Isle Condominium", "Tern Isle Condominium"), "received": ("2026-09-29", "09/29/2026")}],
}
CONDO_FORMS = ("SPDC", "MISIRS", "RCD", "CR-7_A")


def round_trip_spec(family, values):
    """A minimal executed spec that puts `values` on `family`."""
    s = {"name": f"rt-{family.lower()}", "form": "standard" if family in ("CR-7_K", "CR-7_L") else "as_is",
         "financing": "fha" if family == "CR-7_E" else "conventional", "price": 420000}
    if family in CONDO_FORMS:
        s["property"] = {"unit": "204", "year_built": 2004}
    if family.startswith("CR-7_"):
        s["riders"] = [{"code": family[5:], **values}]
    elif family == "CASSB":
        s["buyer_broker"] = {"form": "GG", **values}
    elif family in ("AGA", "EAC", "CDDA"):
        s["addenda"] = [{"form": family, **values}]
    elif family == "CO":
        s.update(stage="countered", counters=[{**values, "accepted": True}])
    elif family in ("EA", "ACSP"):
        s.update(stage="amended", amendments=[{"form": family, **values}])
    else:
        s["disclosures"] = {family: values}
    return s


@unittest.skipUnless(HAVE_TOOLS, "PyMuPDF (dev/requirements-tools.txt) or sources/Contracts/FARBAR/ missing")
class KeyMatchesPdf(unittest.TestCase):
    def test_samples_cover_every_printed_key(self):
        """Every map but the contracts has samples, and they set exactly the keys it prints: a map expression naming a
        key no spec could set fails here."""
        maps = {p[:-5] for p in os.listdir(fields.FIELDS_DIR)} - {"FRBAR-ASIS", "FRBAR-STANDARD"}
        self.assertEqual(maps, set(ROUND_TRIP))
        for family, samples in ROUND_TRIP.items():
            with self.subTest(family=family):
                given = {k for s in samples for k in s}
                self.assertLessEqual(fields.map_value_keys(family), given)
                self.assertLessEqual(given, sc.printed_keys(family))

    def test_every_value_is_on_its_form(self):
        """Each sample value is typed on its own form's pages (more often than the blank form prints that text)."""
        for family, samples in ROUND_TRIP.items():
            blank = " ".join(p.get_text() for p in pymupdf.open(locate.form_path(family)))
            for n, sample in enumerate(samples):
                with self.subTest(family=family, sample=n):
                    S = sc.build(round_trip_spec(family, {k: v for k, (v, _) in sample.items()}))
                    if family == "CASSB":
                        pdf = build.render_compensation(S)
                    else:
                        idx = next(i for i, d in enumerate(S["documents"]) if d["family"] == family)
                        pdf, _ = build.render_document(S["documents"][idx], idx, S, set())
                    text = " ".join(p.get_text() for p in pdf)
                    for key, (_, want) in sample.items():
                        if want is not None:
                            self.assertGreater(text.count(want), blank.count(want), f"{family} {key}: {want!r} not typed")

    def test_a_value_with_no_blank_stops_the_build(self):
        with self.assertRaisesRegex(sc.ScenarioError, r"Rider U: rent_back_deposit has no blank in fields/CR-7_U.json\. Mapped keys: "):
            sc.build({"name": "guard", "form": "as_is", "riders": [{"code": "U", "rent_back_deposit": 5000}]})
        with self.assertRaisesRegex(sc.ScenarioError, "CR-7_M has no field map yet"):
            sc.build({"name": "guard", "form": "as_is", "riders": [{"code": "M", "drywall_known": True}]})
        with self.assertRaisesRegex(sc.ScenarioError, "Counter #1: price_typo"):
            sc.build({"name": "guard", "form": "as_is", "counters": [{"price_typo": 1}]})
        sc.build({"name": "guard", "form": "as_is", "riders": [{"code": "N"}, {"code": "H", "fill": {"P1.7": "x"}}]})  # structural keys pass

    def test_rider_values_reach_both_keys(self):
        """Printed rider values go into the deal file under frbar.md's names and the offer under listing-file.md's."""
        riders = [{"code": "U", "rent_back_days": 21, "rent_back_monthly": 2400}, {"code": "G", "short_sale_approval_days": 75},
                  {"code": "Z", "buyer_attorney_date": "2026-09-28"}, {"code": "C", "seller_financing": 40000}]
        deal = sc.build({"name": "keys", "form": "as_is", "riders": riders})["key"]["contract"]
        self.assertEqual((deal["seller_occupancy_days"], deal["short_sale_approval_days"], deal["buyer_attorney_date"]),
                         (21, 75, "2026-09-28"))
        self.assertNotIn("rent_back_monthly", deal)
        offer = sc.build({"name": "keys", "form": "as_is", "stage": "offer", "riders": riders})["key"]["offers"][0]
        self.assertEqual((offer["rent_back_days"], offer["rent_back_monthly"], offer["attorney_days"], offer["seller_financing"]),
                         (21, 2400, 7, 40000))
        S = sc.build({"name": "keys", "form": "as_is", "riders": ["V"]})
        self.assertTrue(any("Rider V's sale date has no default" in n for n in S["notes"]))
        self.assertIn("sale_contingency_date", S["key"]["contract"])


@unittest.skipUnless(HAVE_TOOLS, "PyMuPDF (dev/requirements-tools.txt) or sources/Contracts/FARBAR/ missing")
class Packages(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def build(self, s, **kw):
        return build.build(s, self.tmp.name, **kw)

    def text(self, path):
        return " ".join(page.get_text() for page in pymupdf.open(path))

    def test_executed_package_reads_back_as_its_answer_key(self):
        r = self.build(spec("asis-fha-executed"), answer_key=True)
        with open(r["answer_key"]) as f:
            key = json.load(f)
        c = key["contract"]
        self.assertEqual((c["effective_date"], c["closing_date"], c["price"], c["financing"]),
                         ("2026-09-25", "2026-10-30", 365000, "fha"))
        self.assertEqual(c["riders"], ["FHA/VA Financing", "Homeowners'/Flood Insurance",
                                       "Seller's Agreement with Respect to Buyer's Broker Compensation"])
        self.assertEqual(c["compensation_agreement_days"], 3)
        text = self.text(r["pdf"])
        for want in ("Jordan Avery", "Morgan Whitfield and Casey Whitfield", "1532 Cypress Bend Dr", "365,000.00",
                     "11,000.00", "10/30/2026", "dotloop verified", "09/25/26"):
            self.assertIn(want, text)
        self.assertNotIn("Licensed to dotloop", text)  # the source account's name is redacted

    def test_offer_is_signed_by_the_buyer_only(self):
        r = self.build(spec("asis-offer-aga"), answer_key=True)
        with open(r["answer_key"]) as f:
            key = json.load(f)
        self.assertFalse(key["mock"]["accepted"])
        self.assertNotIn("contract", key)  # not a contract yet: the key is seller-offer-review's listing file
        offer = key["offers"][0]
        self.assertEqual((offer["price"], offer["approval"], offer["appraisal_form"], offer["appraisal_gap"], offer["lender"] != ""),
                         (489000, "preapproval", "aga", 15000, True))
        self.assertGreaterEqual(key["listing"]["list_price"], offer["price"])
        doc = pymupdf.open(r["pdf"])
        contract = " ".join(doc[i].get_text() for i in range(13))
        self.assertIn("Sawyer Nakamura", contract)
        # On the contract the seller's name is only typed in Para. 1: no signature, date or initials yet.
        self.assertEqual(contract.count("Logan Prescott"), 1)
        self.assertNotIn("escrow_receipt", key["mock"]["documents"])

    def test_only_the_accepted_counter_changes_the_offer(self):
        s = spec("standard-counter-chain")
        s["counters"][2] = {"by": "seller", "terms": [{"line": "", "text": "Seller keeps the refrigerator."}]}
        S = sc.build(s)
        self.assertEqual((S["key"]["contract"]["price"], S["key"]["contract"]["loan_approval_days"]), (425000, 30))
        self.assertTrue(any("don't carry over" in n for n in S["notes"]))
        full = sc.build(spec("standard-counter-chain"))["key"]["contract"]
        self.assertEqual((full["price"], full["closing_date"], full["loan_approval_days"]), (432500, "2026-11-20", 25))

    def test_pending_counter_leaves_the_offer_terms(self):
        key = sc.build(spec("standard-l-countered"))["key"]
        offer = key["offers"][0]
        self.assertEqual((offer["price"], offer["inspection_days"], key["mock"]["pending"]), (545000, 10, "counter offer"))
        self.assertEqual(key["mock"]["counters"][0]["price"], 552000)  # the pending counter changes nothing yet

    def test_amendments_carry_the_changes(self):
        key = sc.build(spec("condo-asis-amended"))["key"]
        ea = key["amendments"][0]
        self.assertEqual(ea["changes"], {"closing_date": "2026-11-06", "inspection_days": 15})  # 10 + 5 more
        self.assertEqual(key["contract"]["inspection_days"], 10)  # the deal file keeps the contract as signed
        self.assertIn("Condominium", key["contract"]["riders"])
        self.assertIn("Lead-Based Paint Disclosure", key["contract"]["riders"])  # built in 1974
        self.assertTrue(key["contract"]["lbp_waived"])  # Rider P's default: the buyer waived the risk assessment

    def test_buyer_broker_compensation(self):
        """Rider GG (broker to broker) by default; FF on request; none only when asked; a listed rider isn't doubled."""
        def riders(**kw):
            S = sc.build({"name": "bb", "form": "as_is", "financing": "cash", **kw})
            return [d.get("code") for d in S["documents"] if d["role"] == "rider"], S["key"]["mock"]["buyer_broker"]
        codes, bb = riders()
        self.assertEqual((codes, bb["form"], bb["between"], bb["compensation_agreement_days"]), (["GG"], "GG", "brokers", 3))
        codes, bb = riders(buyer_broker={"form": "GG", "between": "seller"})
        self.assertEqual((codes, bb["between"]), (["GG"], "seller"))
        codes, bb = riders(buyer_broker={"form": "FF", "amount": 9000})
        self.assertEqual((codes, bb["amount"]), (["FF"], 9000))
        self.assertEqual(riders(buyer_broker="none"), ([], None))
        self.assertEqual(riders(riders=["FF"])[0], ["FF"])

    def test_compensation_agreement(self):
        """GG gets a separate CASSB-1: executed after the Effective Date and inside GG's window, signed by the listing
        broker's associate (broker to broker) or the sellers; a draft before acceptance; none with FF or none."""
        base = {"form": "as_is", "financing": "cash"}
        for between, days in (("brokers", 3), ("seller", 5)):
            with self.subTest(between=between):
                S = sc.build({**base, "name": f"cassb-{between}", "buyer_broker": {"form": "GG", "between": between,
                                                                                 "compensation_agreement_days": days}})
                C, effective = S["compensation"], S["ctx"]["effective_date"]
                self.assertTrue(C["executed"] and C["within_window"])
                self.assertLess(effective, C["buyers_broker_signed"])
                self.assertLess(C["buyers_broker_signed"], C["payer_signed"])
                self.assertLessEqual(C["payer_signed"].date(), (effective + sc.timedelta(days=days)).date())
                self.assertEqual(C["payer_party"], "listing_agent" if between == "brokers" else "seller")
        late = sc.build({**base, "name": "late", "defects": ["late-compensation-agreement"]})["compensation"]
        self.assertFalse(late["within_window"])
        draft = sc.build({**base, "name": "draft", "stage": "offer"})["compensation"]
        self.assertEqual((draft["executed"], draft["payer_signed"]), (False, None))
        self.assertIsNone(sc.build({**base, "name": "ff", "buyer_broker": "FF"})["compensation"])
        r = self.build({**base, "name": "cassb-file", "sellers": ["Reese Okafor"], "buyer_broker": {"form": "GG", "between": "seller"}})
        text = " ".join(p.get_text() for p in pymupdf.open(r["compensation_agreement"]))
        self.assertIn("Reese Okafor", text)
        self.assertNotIn("CASSB-1", " ".join(p.get_text() for p in pymupdf.open(r["pdf"])))  # not merged into the package

    def test_names(self):
        """An unnamed spec gets street-stage-hash: stable for the same spec, different for another; files follow the address."""
        a = sc.build({"form": "as_is", "stage": "offer", "property": {"address": "12 Any Way, Oviedo, FL 32765"}})
        again = sc.build({"form": "as_is", "stage": "offer", "property": {"address": "12 Any Way, Oviedo, FL 32765"}})
        other = sc.build({"form": "as_is", "stage": "offer", "price": 400000, "property": {"address": "12 Any Way, Oviedo, FL 32765"}})
        self.assertRegex(a["name"], r"^12-any-way-offer-[0-9a-f]{6}$")
        self.assertEqual(a["name"], again["name"])
        self.assertNotEqual(a["name"], other["name"])
        self.assertEqual((a["files"]["package"], a["files"]["compensation"]),
                         ("12-Any-Way-Offer.pdf", "12-Any-Way-Compensation-Agreement.pdf"))
        self.assertEqual(sc.build(spec("asis-fha-executed"))["files"]["package"], "1532-Cypress-Bend-Dr-Contract.pdf")

    def test_key_is_kept_apart_and_carries_the_gap_deadlines(self):
        """The key and spec live in key/, named for the property; an AGA-1 adds its deadlines and pushes a default
        closing past them."""
        r = self.build({"name": "aga", "form": "as_is", "addenda": [{"form": "AGA", "gap_amount": 15000}]}, answer_key=True)
        top = sorted(os.listdir(self.tmp.name))
        self.assertFalse([f for f in top if f.endswith(".json")], top)
        self.assertTrue(r["answer_key"].endswith(os.path.join("key", os.path.basename(r["pdf"]).rsplit("-Contract", 1)[0]
                                                               + "-Answer-Key.json")))
        with open(r["answer_key"]) as f:
            key = json.load(f)
        self.assertEqual(key["contract"]["addenda"], ["Appraisal Gap Addendum (AGA-1)"])
        self.assertEqual([(d["key"], d["days"]) for d in key["deadlines"]], [("aga_valuation", 30), ("aga_renegotiation", 36)])
        closing = sc.date.fromisoformat(key["contract"]["closing_date"])
        effective = sc.date.fromisoformat(key["contract"]["effective_date"])
        self.assertGreaterEqual((closing - effective).days, 41)

    def test_flowed_text_skips_no_line(self):
        """Additional Terms fill the lines in order: every map id in a flowed list exists."""
        r = self.build({"name": "terms", "form": "as_is", "financing": "cash",
                        "additional_terms": " ".join(f"Term{i:02d} lorem ipsum dolor sit amet consectetur." for i in range(1, 25))})
        page = pymupdf.open(r["pdf"])[11]
        rows = sorted({round(w[3]) for w in page.get_text("words") if w[4].startswith("Term")})
        gaps = [b - a for a, b in zip(rows, rows[1:])]
        self.assertTrue(gaps and max(gaps) < 14, gaps)  # one printed line apart, never two

    def test_package_follows_the_stage_and_the_facts(self):
        """Offer: disclosures and proof of financing; accepted: escrow receipts; condo: MISIRS and, once accepted, RCD."""
        docs = lambda **kw: sc.build({"name": "pkg", "form": "as_is", **kw})["key"]["mock"]["documents"]  # noqa: E731
        offer = docs(stage="offer", financing="fha")
        for f in ("SPDR", "FD", "pre_approval"):
            self.assertIn(f, offer)
        self.assertNotIn("SOD", offer)  # informational: only when included
        self.assertNotIn("escrow_receipt", offer)
        self.assertNotIn("proof_of_funds", offer)
        self.assertIn("proof_of_funds", docs(stage="offer", financing="cash"))
        self.assertNotIn("pre_approval", docs(stage="offer", financing="cash"))
        condo = {"unit": "12", "year_built": 2004}
        self.assertNotIn("RCD", docs(stage="offer", property=condo))
        executed = docs(property=condo)
        for f in ("SPDC", "MISIRS", "RCD", "escrow_receipt"):
            self.assertIn(f, executed)
        self.assertLess(executed.index("MISIRS"), executed.index("RCD"))
        trimmed = docs(stage="offer", package={"exclude": ["SPDR", "pre_approval"], "include": ["SOD", "proof_of_funds"]})
        self.assertEqual(("SPDR" in trimmed, "pre_approval" in trimmed, "SOD" in trimmed, "proof_of_funds" in trimmed),
                         (False, False, True, True))
        self.assertIn("SD", docs(property={"sinkhole_claim": True}))
        self.assertIn("CDDA", docs(property={"cdd": True}))

    def test_missing_disclosure_drops_the_flood_disclosure_when_no_rider_is_required(self):
        key = sc.build({"name": "fd", "form": "as_is", "financing": "cash", "property": {"year_built": 2010},
                        "defects": ["missing-disclosure"]})["key"]
        self.assertEqual((key["mock"]["dropped_rider"], key["mock"]["dropped_disclosure"]), (None, "FD"))
        self.assertNotIn("FD", key["mock"]["documents"])

    def test_disclosure_answers(self):
        """Condition questions default to yes, problems to no; the spec overrides by question text."""
        import answers
        path, found, _ = fields.form_blanks("SPDR")
        words = {i + 1: [w[:5] for w in p.get_text("words")] for i, p in enumerate(pymupdf.open(path))}
        picked = {q: a for _, q, a in answers.choose(found, words, {"water intrusion": "yes"})}
        self.assertGreater(len(picked), 50)
        self.assertEqual(next(a for q, a in picked.items() if "free of leaks" in q), "yes")
        self.assertEqual(next(a for q, a in picked.items() if "water intrusion" in q), "yes")
        self.assertEqual(next(a for q, a in picked.items() if "aluminum wiring" in q), "no")
        # Property facts set the matching answers, so the SPDR never contradicts Rider B or a sinkhole claim.
        S = sc.build({"name": "facts", "form": "as_is", "property": {"hoa": True, "sinkhole_claim": True}})
        given = next(d for d in S["documents"] if d["family"] == "SPDR")["values"]["answers"]
        picked = {q: a for _, q, a in answers.choose(found, words, given)}
        self.assertEqual(next(a for q, a in picked.items() if "membership in a homeowner" in q), "yes")
        self.assertEqual(next(a for q, a in picked.items() if "claim for sinkhole damage been made" in q), "yes")

    def test_rules_come_from_contract_forms(self):
        s = {"name": "k-on-as-is", "form": "as_is", "riders": ["K"]}
        with self.assertRaisesRegex(sc.ScenarioError, "RESERVED"):
            sc.build(s)
        S = sc.build({**s, "defects": ["rider-conflict"]})
        self.assertIn("CR-7_K", [d["family"] for d in S["documents"]])
        with self.assertRaisesRegex(sc.ScenarioError, "never defaulted"):
            sc.build({"name": "no-form"})
        with self.assertRaisesRegex(sc.ScenarioError, "isn't an FR/BAR contract"):
            sc.build({"name": "trec", "form": "TREC 20-18"})

    def test_defects_are_recorded_in_the_key(self):
        s = copy.deepcopy(spec("asis-fha-executed"))
        s["defects"] = ["missing-initials", "blank-default", "unattached-rider"]
        key = sc.build(s)["key"]
        kinds = {d["type"]: d for d in key["mock"]["defects"]}
        self.assertEqual((kinds["missing-initials"]["party"], kinds["missing-initials"]["page"]), ("seller", 4))
        self.assertEqual(key["contract"]["inspection_days"], 15)  # blank: the form default
        self.assertEqual(key["mock"]["unattached_rider"], "E")

    def test_generated_people_never_share_a_name(self):
        """No two made-up people share a first name or surname (a shared surname reads as a relative: Rider AA)."""
        for seed in ("a", "b", "c", "d"):
            S = sc.build({"name": seed, "form": "as_is", "property": {"hoa": True}})
            c = S["ctx"]
            people = c["buyers"] + c["sellers"] + [c["listing_associate"], c["cooperating_associate"]]
            people += [v["contact"] for d in S["documents"] if d.get("code") == "B" for v in [d["values"]]]
            words = [w for n in people for w in n.split()]
            self.assertEqual(len(words), len(set(words)), people)

    def test_follow_up_questions_follow_their_answer(self):
        """'If yes, was the claim paid?' stays blank when no claim was made, and is Yes with a paid claim."""
        import answers
        path, found, _ = fields.form_blanks("SPDR")
        words = {i + 1: [w[:5] for w in p.get_text("words")] for i, p in enumerate(pymupdf.open(path))}
        picked = {answers._own(q): a for _, q, a in answers.choose(found, words, {})}
        self.assertNotIn("If yes, was the claim paid?", picked)
        S = sc.build({"name": "sink", "form": "as_is", "property": {"sinkhole_claim": True}})
        given = next(d for d in S["documents"] if d["family"] == "SPDR")["values"]["answers"]
        picked = {answers._own(q): a for _, q, a in answers.choose(found, words, given)}
        self.assertEqual(picked["If yes, was the claim paid?"], "yes")

    def test_rent_back_checks_para_6b(self):
        S = sc.build({"name": "u6b", "form": "as_is", "financing": "cash", "riders": ["U"]})
        pdf, _ = build.render_document(S["documents"][0], 0, S, set())
        _, found, m = fields.form_blanks("FRBAR-ASIS")
        b = fields.resolve(found, m["fields"]["tenants"]["at"])[0]
        self.assertIn("X", [w[4] for w in pdf[b["page"] - 1].get_text("words", clip=pymupdf.Rect(b["rect"]))])
        self.assertNotIn("tenants", S["key"]["contract"])  # a seller's rent-back isn't a tenancy

    def test_scanned_copy_has_no_text_layer(self):
        r = self.build({"name": "scan", "form": "as_is", "financing": "cash"}, scan=True)
        scan = pymupdf.open(r["scanned"])
        self.assertEqual(len(scan), r["pages"])
        self.assertEqual(scan[0].get_text().strip(), "")

    def test_every_scenario_builds(self):
        for f in sorted(os.listdir(os.path.join(MOCK, "scenarios"))):
            with self.subTest(scenario=f):
                r = self.build(spec(f[:-5]), answer_key=True)
                self.assertGreater(r["pages"], 10)
                self.assertTrue(os.path.exists(r["answer_key"]))

    def test_keys_render_through_the_skills(self):
        """Every starter's key is the file its skill reads: a deal file renders through contract-timeline, an offer's
        listing file through seller-offer-review."""
        for f in sorted(os.listdir(os.path.join(MOCK, "scenarios"))):
            with self.subTest(scenario=f):
                key = sc.build(spec(f[:-5]))["key"]
                skill = "contract-timeline" if "contract" in key else "seller-offer-review"
                path = os.path.join(self.tmp.name, f)
                with open(path, "w") as fh:
                    json.dump(key, fh, default=str)
                out = os.path.join(self.tmp.name, f[:-5])
                run = subprocess.run([sys.executable, os.path.join(ROOT, "skills", skill, "scripts", "render.py"), path,
                                      "--out", out], capture_output=True, text=True, timeout=120)
                self.assertEqual(run.returncode, 0, run.stderr[-800:])
                self.assertTrue(any(n.endswith(".pdf") for n in os.listdir(out)))

    def test_seller_signs_offer(self):
        """With seller_signs_offer the seller signs the offer's documents at the first counter; without it, not."""
        base = {"name": "sso", "form": "as_is", "financing": "cash", "stage": "countered"}
        S = sc.build({**base, "counters": [{"seller_signs_offer": True}]})
        countered = next(d for d in S["documents"] if d["family"] == "CO")["values"]["date"]
        self.assertEqual([(p, dt) for p, _, dt in S["events"][0] if p == "seller"], [("seller", countered)])
        self.assertFalse([p for p, _, _ in sc.build({**base, "counters": [{}]})["events"][0] if p == "seller"])

    def test_counter_on_the_contract(self):
        """The seller counters on the contract: struck values and new ones on its blanks, the counter box checked, no
        CO-3; the buyer's last initial is the Effective Date. Pending: seller's marks only, and the offer as written."""
        S = sc.build(spec("asis-counter-on-contract"))
        c = S["key"]["contract"]
        self.assertEqual((c["price"], c["closing_date"], c["inspection_days"]), (412000, "2026-11-06", 7))
        self.assertTrue(c["effective_date_source"].startswith("Buyer's initials on the Seller's counter-offer changes (Para. 3(b))"))
        self.assertNotIn("CO", S["key"]["mock"]["documents"])
        marks = S["change_marks"]
        self.assertEqual([m["field"] for m in marks], ["price", "closing_date", "inspection_days", "loan_amount",
                                                     "balance_to_close", "additional_terms"])
        self.assertEqual(marks[-1]["buyer_at"], S["ctx"]["effective_date"])
        self.assertTrue(all(m["seller_at"] < m["buyer_at"] for m in marks))
        r = self.build(spec("asis-counter-on-contract"))
        page1 = pymupdf.open(r["pdf"])[0].get_text()
        self.assertIn("405,000.00", page1)
        self.assertIn("412,000.00", page1)
        # A new price moves the loan (same LTV) and, with it, the loan line; a 100% VA loan keeps the balance at 0.
        va = sc.build({"name": "coc-va", "form": "standard", "stage": "executed", "financing": "va", "price": 410000,
                       "counter": {"method": "contract", "price": 418000}})["change_marks"]
        self.assertEqual([(m["field"], m["old"], m["new"]) for m in va], [("price", "410,000.00", "418,000.00"),
                                                                          ("loan_amount", "406,000.00", "414,000.00")])
        pending = sc.build({**spec("asis-counter-on-contract"), "stage": "countered"})
        self.assertTrue(all(m["buyer_at"] is None for m in pending["change_marks"]))
        self.assertEqual((pending["key"]["offers"][0]["price"], pending["key"]["mock"]["pending"]), (405000, "counter offer"))
        with self.assertRaisesRegex(sc.ScenarioError, "only the seller's first counter"):
            sc.build({"name": "coc", "form": "as_is", "counters": [{"by": "buyer", "method": "contract"}]})
        with self.assertRaisesRegex(sc.ScenarioError, "no blank for a new acceptance deadline"):
            sc.build({"name": "coc", "form": "as_is", "counter": {"method": "contract", "deadline": "2026-09-24 17:00"}})


@unittest.skipUnless(HAVE_TOOLS, "PyMuPDF (dev/requirements-tools.txt) or sources/Contracts/FARBAR/ missing")
class Docs(unittest.TestCase):
    def test_documented_flags_exist(self):
        """docs/mock-contracts.md and the CLIs agree: every flag the doc names is a real option, and back."""
        with open(os.path.join(ROOT, "docs", "mock-contracts.md")) as f:
            doc = f.read()
        documented = set(re.findall(r"`(--[a-z][a-z-]+)", doc))
        real = {o for a in build.parser()._actions for o in a.option_strings if o.startswith("--")} - {"--help"}
        real |= {"--pages", "--debug", "--draft", "--json"}  # locate.py
        self.assertEqual(documented - real, set(), "documented but not an option")
        self.assertEqual({o for a in build.parser()._actions for o in a.option_strings if o.startswith("--")}
                         - {"--help"} - documented, set(), "an option the doc doesn't describe")
        for d in sc.DEFECTS:
            self.assertIn(f"`{d}`", doc)


if __name__ == "__main__":
    unittest.main()
