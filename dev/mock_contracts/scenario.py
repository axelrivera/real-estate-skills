"""A scenario spec (JSON) to everything the builder needs: the documents in package order, the values for each
form, who signs what and when, the defects to inject, and the answer key.

Every key is optional except `form`; anything missing gets a realistic mock default, seeded from the scenario name
so the same spec always builds the same package. The spec reference is docs/mock-contracts.md#scenario-spec.
Rules come from shared/contract_forms.py (never re-implemented here). Local dev only.
"""
import hashlib
import json
import random
import re
from datetime import date, datetime, timedelta

from fields import map_value_keys
from locate import manifest
from shared import contract_forms as cf
from shared import dates as sd

STAGES = ("offer", "countered", "executed", "amended")
DEFECTS = {
    "missing-initials": "One party's initials left off one page of the contract",
    "missing-signature": "One party's signature (and its date) left off the contract",
    "blank-default": "Deposit, loan, inspection and title day blanks left empty so the form defaults apply",
    "rider-conflict": "A rider the form doesn't allow (K on AS IS; K and L together on Standard), bypassing validation",
    "missing-disclosure": "A rider the property's facts require (P, A, B or E) left out of the package",
    "unchecked-rider": "A rider attached to the package but not checked in Para. 19",
    "unattached-rider": "A rider checked in Para. 19 but not attached to the package",
    "late-compensation-agreement": "Rider GG's compensation agreement signed after its window, so the buyer's right to cancel opens",
}
# Counter terms written as structured `changes` become CO-3 "Other" rows: the contract line they change and the text.
COUNTER_TERMS = {
    "inspection_days": ({"as_is": 261, "standard": 277}, "Inspection Period is changed to {} days."),
    "loan_approval_days": ({"as_is": 89, "standard": 90}, "Loan Approval Period is changed to {} days."),
    "loan_application_days": ({"as_is": 97, "standard": 98}, "Buyer shall make application for Financing within {} days."),
    "deposit_days": ({"as_is": 30, "standard": 30}, "Initial deposit is to be made within {} days after Effective Date."),
    "additional_deposit": ({"as_is": 37, "standard": 37}, "Additional deposit is changed to ${:,.2f}."),
    "additional_deposit_days": ({"as_is": 36, "standard": 36}, "Additional deposit is due within {} days after Effective Date."),
    "title_evidence_days": ({"as_is": 155, "standard": 171}, "Title Evidence Deadline is changed to {} days prior to Closing Date."),
}
# Spec keys that aren't values printed on a blank: how a document is named, filled by hand, answered or scheduled.
STRUCTURAL = {"code", "name", "form", "fill", "answers", "default_answer", "date", "signed", "number", "description"}
COUNTER_STRUCTURAL = {"by", "accepted", "changes", "seller_signs_offer", "method"}
# Keys a form's values carry that another document prints: Rider A's community names the condo on RCD-8, and Rider
# GG's agreement terms go on the CASSB-1 compensation agreement.
PRINTED_ELSEWHERE = {"CR-7_A": ("community",), "CR-7_GG": ("CASSB",)}
# Rider values the deal file (skills/contract-timeline/references/frbar.md) names differently; None: not a deal field.
DEAL_FLAGS = ("cccl_requested", "rofr", "condo_docs_before_contract")  # yes/no rider boxes the deal file reads
DEAL_NAMES = {"rent_back_days": "seller_occupancy_days", "short_sale_closing_days": None, "flood_date": None}
# EA-4 "until" dates: the contract-timeline deadline each one overrides (deal-file.md date_overrides).
EA_OVERRIDES = {"inspection_until": "inspection", "loan_approval_until": "loan_approval", "title_cure_until": "title_cure",
                "short_sale_until": "short_sale_approval", "sale_lease_until": "buyer_sale_closes"}
# A counter made on the contract itself (`method: contract`): each change is struck through and retyped on the
# contract's own blank (its field in the contract map), with the value formatted as that field prints it.
CONTRACT_CHANGE_FIELDS = {"price": "price", "closing": "closing_date", "inspection_days": "inspection_days",
                          "loan_approval_days": "loan_approval_days", "loan_application_days": "loan_application_days",
                          "deposit_days": "deposit_days", "additional_deposit": "additional_deposit",
                          "additional_deposit_days": "additional_deposit_days", "title_evidence_days": "title_evidence_days"}
PRESIGNED_BY_SELLER = ("P",)
LETTERS = ("pre_approval", "proof_of_funds", "escrow_receipt")  # generated third-party documents (letters.py)
# Plausible answers for a condo's milestone and reserve-study disclosure; everything else uses answers.py's defaults.
DEFAULT_ANSWERS = {"MISIRS": {"exempt from performing the milestone": "no", "phase 1": "yes", "phase 2 of the milestone "
                              "inspection required": "no", "exempt from performing the structural": "no",
                              "reserve study been completed": "yes"}}


def default_disclosures(ptype, prop, spec):
    """The seller's disclosures a Florida resale package carries, from the property's facts (frbar-package-check.md,
    frbar-addenda.md): the property disclosure (SPDC-2 for a condo, else SPDR-4x) and the statutory flood disclosure
    (FD-2) always; the milestone/SIRS disclosure and the buyer's receipt of the condo documents for a condo; and the
    rest only when the facts call for them. Informational notices (SOD-2, HID-2, WFPN-3...) only when included."""
    out = ["SPDC" if ptype == "condo" else "SPDR", "FD"]
    if ptype == "condo":
        out += ["MISIRS", "RCD"]
    if prop.get("sinkhole_claim"):
        out.append("SD")
    waived = any(isinstance(r, dict) and cf.rider_code(r.get("code") or r.get("name")) == "N" and r.get("cccl_requested") is False
                 for r in spec.get("riders") or [])
    if prop.get("coastal") and not waived:  # the seller's CCCL affidavit, unless the buyer waived it on Rider N
        out.append("CCCLA")
    if prop.get("septic") and prop.get("county") == "Miami-Dade":
        out.append("MDSTS")
    if str(prop.get("flood_zone") or "").upper()[:1] in ("A", "V"):
        out.append("FIN")
    if spec.get("multiple_offers"):
        out.append("NMOB")
    return out  # riders the seller completes and signs at listing, before any offer
FINANCING = ("cash", "conventional", "fha", "va", "usda", "other")
FAMILY = {cf.AS_IS: "FRBAR-ASIS", cf.STANDARD: "FRBAR-STANDARD"}
ADDENDA_ORDER = ("AGA", "EAC", "CDDA", "COOP", "BBCCA", "SPRA", "AA", "CASSB")  # offer addenda, before counters
DISCLOSURE_FORMS = ("SPDR", "SPDC", "SPDU", "FD", "SD", "SOD", "HID", "LBPL", "MISIRS", "MDSTS", "FIN", "WFPN", "TRID",
                    "SUP", "CCCLA", "NTA", "FND", "RCD", "EDRV", "MODS", "NMOB", "BWTIR", "BRR", "RC")

FIRST = ["Jordan", "Avery", "Morgan", "Riley", "Casey", "Taylor", "Quinn", "Reese", "Harper", "Rowan", "Emerson",
         "Parker", "Sawyer", "Hayden", "Blake", "Dana", "Ellis", "Finley", "Jamie", "Kendall", "Logan", "Marley"]
LAST = ["Whitfield", "Castellanos", "Okafor", "Lindqvist", "Brightwater", "Delacroix", "Hollister", "Nakamura",
        "Prescott", "Vandermeer", "Ashcombe", "Fairbanks", "Galloway", "Kowalczyk", "Merriweather", "Thornbury"]
STREETS = ["Cypress Bend Dr", "Heron Lake Ct", "Larkwood Ave", "Sable Palm Way", "Osprey Ridge Ln", "Juniper Hollow Rd",
           "Coral Vine Ter", "Magnolia Crest Blvd", "Tern Island Cir", "Saw Grass Pointe"]
# Real cities, ZIP codes and area codes by county; the street names above are made up, so no address is real.
CITIES = {
    "Seminole": [("Casselberry", "32707"), ("Oviedo", "32765"), ("Sanford", "32771"), ("Winter Springs", "32708")],
    "Orange": [("Orlando", "32803"), ("Winter Park", "32789"), ("Apopka", "32703"), ("Windermere", "34786")],
    "Osceola": [("Kissimmee", "34744"), ("St. Cloud", "34769")],
    "Lake": [("Clermont", "34711"), ("Mount Dora", "32757")],
    "Volusia": [("DeLand", "32720"), ("Ormond Beach", "32174")],
    "Hillsborough": [("Tampa", "33606"), ("Brandon", "33511"), ("Riverview", "33569")],
    "Pinellas": [("St. Petersburg", "33704"), ("Clearwater", "33755"), ("Dunedin", "34698")],
    "Pasco": [("Wesley Chapel", "33544"), ("New Port Richey", "34652"), ("Land O' Lakes", "34638")],
    "Polk": [("Lakeland", "33803"), ("Winter Haven", "33880")],
    "Manatee": [("Bradenton", "34209"), ("Lakewood Ranch", "34202")],
    "Sarasota": [("Sarasota", "34231"), ("Venice", "34293")],
    "Lee": [("Cape Coral", "33990"), ("Fort Myers", "33901"), ("Bonita Springs", "34135")],
    "Collier": [("Naples", "34102"), ("Marco Island", "34145")],
    "Palm Beach": [("Jupiter", "33458"), ("Boca Raton", "33431"), ("Wellington", "33414"), ("West Palm Beach", "33401")],
    "Broward": [("Fort Lauderdale", "33301"), ("Coral Springs", "33065"), ("Hollywood", "33020")],
    "Miami-Dade": [("Miami", "33133"), ("Coral Gables", "33134"), ("Homestead", "33030")],
    "Duval": [("Jacksonville", "32207")],
    "St. Johns": [("St. Augustine", "32084"), ("Ponte Vedra Beach", "32082")],
    "Brevard": [("Melbourne", "32901"), ("Palm Bay", "32905"), ("Titusville", "32780")],
    "Leon": [("Tallahassee", "32308")],
    "Alachua": [("Gainesville", "32605")],
    "Escambia": [("Pensacola", "32501")],
}
AREA_CODES = {"Seminole": "407", "Orange": "407", "Osceola": "407", "Lake": "352", "Volusia": "386", "Hillsborough": "813",
              "Pinellas": "727", "Pasco": "813", "Polk": "863", "Manatee": "941", "Sarasota": "941", "Lee": "239",
              "Collier": "239", "Palm Beach": "561", "Broward": "954", "Miami-Dade": "305", "Duval": "904",
              "St. Johns": "904", "Brevard": "321", "Leon": "850", "Alachua": "352", "Escambia": "850"}
SUBDIVISIONS = ["Cypress Bend", "Heron Lake Estates", "Larkwood Village", "Sable Palm Reserve", "Osprey Ridge"]
TITLE_COS = ["Palmetto Crossing Title Co.", "Sunrise Coast Title Agency", "Harrow Lane Title & Escrow",
             "Bayridge Title Services"]
LENDERS = [("Harborline Home Lending", "2200 Harborline Pkwy, Suite 300"), ("Keystone Coast Mortgage", "415 Keystone Blvd, Suite 120"),
           ("Palm Ridge Mortgage Co.", "88 Palm Ridge Center, Suite 210")]
BANKS = ["First Palmetto Bank", "Coastal Heron Bank", "Sunward Federal Credit Union"]
BROKERAGES = ["Coastline Realty Group", "Harborview Properties", "Sunward Homes Realty", "Greenleaf Realty Partners"]


class ScenarioError(ValueError):
    """A scenario the forms can't represent; the message says why and what to change."""


def _dt(v):
    if isinstance(v, datetime):
        return v
    s = str(v).strip()
    return datetime.strptime(s, "%Y-%m-%d %H:%M") if " " in s else datetime.strptime(s + " 12:00", "%Y-%m-%d %H:%M")


def _d(v):
    return _dt(v).date() if not isinstance(v, date) or isinstance(v, datetime) else v


def money(v, cents=True):
    if v in (None, ""):
        return None
    return f"{v:,.2f}" if cents else f"{v:,.0f}"


def mdy(v):
    if v in (None, ""):
        return None
    d = _d(v)
    return f"{d.month:02d}/{d.day:02d}/{d.year}"


def when(v):
    """'09/25/2026 4:12 PM' from a datetime."""
    dt = _dt(v)
    return f"{mdy(dt)} {dt.strftime('%I:%M %p').lstrip('0')}"


def clock(v):
    """'9:00' from a datetime: the time on a form that checks a.m. or p.m. separately."""
    return _dt(v).strftime("%I:%M").lstrip("0") if v else None


def tz(dt):
    """Eastern time label for a Dotloop stamp (EDT between the second Sunday of March and the first Sunday of November)."""
    y = dt.year
    start = sd._nth(y, 3, 6, 2)
    end = sd._nth(y, 11, 6, 1)
    return "EDT" if start <= dt.date() < end else "EST"


def initials_of(name):
    return "".join(p[0] for p in re.split(r"[\s-]+", name) if p and p[0].isalpha()).upper()[:3]


def _weekday(d):
    while d.weekday() >= 5 or sd.holiday_name(d):
        d += timedelta(days=1)
    return d


def _next_daytime(t, rng):
    """A response the next day during waking hours (counters and acceptances aren't signed at 2 AM)."""
    return datetime.combine(t.date() + timedelta(days=1), datetime.min.time()).replace(
        hour=rng.randint(9, 19), minute=rng.randint(0, 59))


class Ctx(dict):
    """Scenario values for field-map expressions: attribute access, None for anything missing."""

    def __getattr__(self, k):
        return self.get(k)


def form_title(family):
    """The printed name of a form from its file name: "Appraisal Gap Addendum (AGA-1)"."""
    f = manifest().get(family)
    if not f:
        raise ScenarioError(f"{family} isn't in dev/forms/frbar-forms.json. Known forms: {', '.join(sorted(manifest()))}.")
    return re.sub(r"-\d+\.pdf$|\.pdf$", "", f["file"].split("/")[-1])


def rider_list(spec):
    """[(code, values)] from the spec's riders: letters ("E"), names ("FHA/VA Financing") or {"code": "E", ...}."""
    out = []
    for r in spec.get("riders") or []:
        values = dict(r) if isinstance(r, dict) else {}
        name = values.pop("code", None) or values.pop("name", None) if isinstance(r, dict) else r
        code = cf.rider_code(name)
        if not code:
            raise ScenarioError(f"Rider {name!r} isn't a CR-7 rider. Put addenda (AGA-1, EAC-1, CDDA-2...) in `addenda`.")
        out.append((code, values))
    return out


def printed_keys(family):
    """The value keys a form prints: its map's `v.<key>` references, plus keys another document prints for it."""
    keys = set(map_value_keys(family))
    for extra in PRINTED_ELSEWHERE.get(family, ()):
        keys |= map_value_keys(extra) if extra in manifest() else {extra}
    return keys


def _check_values(spec, form):
    """Every value the spec gives a rider, addendum, disclosure, counter or amendment must have a blank that prints
    it, so the answer key never holds a value the PDF doesn't show (and a typo stops the build)."""
    def check(family, values, what, allowed=STRUCTURAL):
        extra = set(values) - allowed - printed_keys(family)
        if not extra:
            return
        mapped = sorted(printed_keys(family))
        where = (f"has no blank in fields/{family}.json. Mapped keys: {', '.join(mapped)}" if mapped else
                 f"has no blank: {family} has no field map yet, so only its parties, property, signatures and initials "
                 f"are filled")
        raise ScenarioError(f"{what}: {', '.join(sorted(extra))} {where}. Map the blank (docs/mock-contracts.md#field-maps) "
                            "or drop the value.")

    for code, values in rider_list(spec):
        check(f"CR-7_{code}", values, f"Rider {code}")
    bb = spec.get("buyer_broker")
    if isinstance(bb, dict) and str(bb.get("form", "GG")).upper() in ("GG", "FF"):
        code = str(bb.get("form", "GG")).upper()
        check(f"CR-7_{code}", bb, f"buyer_broker (Rider {code})")
    for a in spec.get("addenda") or []:
        if isinstance(a, dict):
            family = a["form"] if a["form"].startswith("CR-7") else a["form"].upper().split("-")[0]
            check(family, a, family)
    for f, values in (spec.get("disclosures") or {}).items():
        family = str(f).upper().split("-")[0]
        check(family, values or {}, family)
    counters = spec.get("counters") or ([spec["counter"]] if spec.get("counter") else [])
    for i, c in enumerate(counters, start=1):
        # CO-3 prints the counter; on the contract (`method: contract`) the same terms go on the contract's blanks.
        check("CO", c, f"Counter #{i}", STRUCTURAL | COUNTER_STRUCTURAL)
    for i, a in enumerate(spec.get("amendments") or [], start=1):
        family = str(a.get("form") or ("EA" if set(a) & printed_keys("EA") and not a.get("text") else "ACSP")).upper().split("-")[0]
        check(family, a, f"Amendment {i} ({family})")


def _rider_defaults(code, values, v):
    """Mock values for the blanks a rider prints with no default of its own ("if left blank, then 10" blanks stay
    blank). `v` holds what they're built from. Returns a note when the value is one frbar-package-check.md says to
    ask the agent for (the sale date on V, the dates on W and Z)."""
    price, rng = v["price"], v["rng"]
    if code == "C":
        values.setdefault("lien", "second" if v["loan"] else "first")
        values.setdefault("seller_financing", round(price * (0.1 if v["loan"] else 0.8), -3))
        values.setdefault("rate", 7.25)
        values.setdefault("payment_period", "monthly")
        values.setdefault("first_payment_months", 1)
        if values.get("loan_type", "amortized") in ("amortized", "balloon", "adjustable"):
            r, n = float(values["rate"]) / 1200, 12 * int(values.get("term_years") or 30)
            values.setdefault("payment", round(values["seller_financing"] * r / (1 - (1 + r) ** -n), 2))
    elif code == "D":
        values.setdefault("mortgage_balance", round(price * 0.55, -3))
        values.setdefault("rate_type", "fixed")
        values.setdefault("rate", 3.375)
    elif code == "S":
        values.setdefault("lease_type", "purchase")
    elif code == "T":
        values.setdefault("possession_date", v["closing"] - timedelta(days=14))
        values.setdefault("rent", round(price * 0.0055, -1))
    elif code == "U":
        values.setdefault("rent_back_days", 30)
        values.setdefault("rent_back_monthly", round(price * 0.0055, -1))
    elif code == "V":
        values.setdefault("buyer_property", f"{rng.randint(100, 9899)} {rng.choice(STREETS)}, {v['city_line']}")
        if not values.get("sale_contingency_date"):
            values["sale_contingency_date"] = v["closing"] - timedelta(days=7)
            return f"Rider V's sale date has no default: used {mdy(values['sale_contingency_date'])} (a real deal asks the agent)."
    elif code == "W" and not values.get("backup_notice_date"):
        values["backup_notice_date"] = v["start"] + timedelta(days=14)
        return f"Rider W's notice date has no default: used {mdy(values['backup_notice_date'])} (a real deal asks the agent)."
    elif code == "X":
        values.setdefault("kickout_deposit", v["deposit"])
    elif code == "Z" and not values.get("buyer_attorney_date"):
        values["buyer_attorney_date"] = v["start"] + timedelta(days=5)
        return f"Rider Z's attorney approval date has no default: used {mdy(values['buyer_attorney_date'])} (a real deal asks the agent)."
    return None


def build(spec):
    """The normalized scenario: a dict with ctx (values), documents, events, defects, notes and key (answer key)."""
    spec = dict(spec)
    # The package's id: the spec's name when given (starters, saved specs); otherwise the street, the stage and a hash
    # of the spec, set once the address is known, so two scenarios never share a folder and a rebuild reuses its own.
    digest = hashlib.sha1(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:6]
    name = spec.get("name")
    rng = random.Random(name or f"spec-{digest}")
    notes = []
    defects = [d if isinstance(d, dict) else {"type": d} for d in spec.get("defects") or []]
    for d in defects:
        if d["type"] not in DEFECTS:
            raise ScenarioError(f"Unknown defect {d['type']!r}. Known: {', '.join(DEFECTS)}.")
    has = lambda t: any(d["type"] == t for d in defects)  # noqa: E731

    # Form: never defaulted (CLAUDE.md). Only the FR/BAR forms have PDFs to fill.
    form = cf.normalize(spec.get("form"))
    if form is None:
        raise ScenarioError("Which contract form: FR/BAR AS IS or Standard? Set `form` (the form is never defaulted).")
    if form not in cf.FRBAR:
        raise ScenarioError(f"{spec.get('form')!r} isn't an FR/BAR contract. Mock packages can only be built from the "
                            "FR/BAR forms in sources/Contracts/FARBAR/ (AS IS or Standard).")
    stage = spec.get("stage") or ("amended" if spec.get("amendments") else "countered" if spec.get("counters") or spec.get("counter") else "executed")
    if stage not in STAGES:
        raise ScenarioError(f"stage must be one of {', '.join(STAGES)}.")
    _check_values(spec, form)

    # Parties and property.
    buyers = spec.get("buyers") or [f"{rng.choice(FIRST)} {rng.choice(LAST)}"]
    taken = {n.split()[-1] for n in ([buyers] if isinstance(buyers, str) else buyers)}  # sellers never share the buyers' surname
    sellers = spec.get("sellers") or [f"{rng.choice(FIRST)} {rng.choice([n for n in LAST if n not in taken])}"]
    buyers, sellers = [buyers] if isinstance(buyers, str) else buyers, [sellers] if isinstance(sellers, str) else sellers
    prop = dict(spec.get("property") or {})
    prop.setdefault("county", spec.get("county") or "Seminole")
    given = re.search(r",\s*([^,]+?),\s*FL\s*(\d{5})\s*$", prop.get("address") or "")
    if given:  # the escrow agent's office goes in the same city as a given address
        city, zipc = given.group(1), given.group(2)
    elif prop["county"] in CITIES:
        city, zipc = rng.choice(CITIES[prop["county"]])
    else:
        raise ScenarioError(f"No built-in city for {prop['county']} County: give property.address with a real city "
                            f"and ZIP code (\"123 Any St, City, FL 32000\"), or use one of {', '.join(CITIES)}.")
    area = AREA_CODES.get(prop["county"], "407")
    street = f"{rng.randint(100, 9899)} {rng.choice(STREETS)}"
    unit = prop.get("unit")
    prop.setdefault("address", f"{street}{', Unit ' + str(unit) if unit else ''}, {city}, FL {zipc}")
    street_slug = re.sub(r"[^A-Za-z0-9]+", "-", prop["address"].split(",")[0]).strip("-")
    if not name:
        name = f"{street_slug.lower()}-{stage}-{digest}"
    prop.setdefault("tax_id", f"{rng.randint(10, 36)}-{rng.randint(19, 22)}-{rng.randint(28, 31)}-{rng.randint(1, 9)}"
                              f"{rng.choice('ABCDEFG')}{rng.choice('ABCDEFG')}-{rng.randint(0, 9999):04d}-{rng.randint(10, 990):04d}")
    ptype = prop.setdefault("type", "condo" if unit else "single_family")
    sub = rng.choice(SUBDIVISIONS)
    if ptype == "condo":
        legal = (f"UNIT {unit or rng.randint(101, 420)}, {sub.upper()} CONDOMINIUM, ACCORDING TO THE DECLARATION OF "
                 f"CONDOMINIUM RECORDED IN OFFICIAL RECORDS BOOK {rng.randint(2000, 9999)}, PAGE {rng.randint(1, 1900)}, "
                 f"PUBLIC RECORDS OF {prop['county'].upper()} COUNTY, FLORIDA")
    else:
        legal = (f"LOT {rng.randint(1, 180)}, BLOCK {rng.choice('ABCDEFGH')}, {sub.upper()} UNIT {rng.randint(1, 4)}, "
                 f"ACCORDING TO THE PLAT THEREOF AS RECORDED IN PLAT BOOK {rng.randint(10, 99)}, PAGES "
                 f"{rng.randint(1, 90)}-{rng.randint(91, 99)}, PUBLIC RECORDS OF {prop['county'].upper()} COUNTY, FLORIDA")
    prop.setdefault("legal_description", legal)
    prop.setdefault("year_built", rng.choice([1986, 1994, 2003, 2007, 2016]))
    prop.setdefault("hoa", False)

    # Money.
    price = spec.get("price") or rng.choice([315000, 365000, 389900, 425000, 489000, 545000])
    list_price = spec.get("list_price") or int(round(price * rng.choice([1.0, 1.02, 1.03, 1.05]), -3))
    fin = spec.get("financing") or {}
    fin = {"type": fin} if isinstance(fin, str) else dict(fin)
    ftype = str(fin.get("type") or "conventional").lower()
    if ftype not in FINANCING:
        raise ScenarioError(f"financing.type must be one of {', '.join(FINANCING)}.")
    dep = dict(spec.get("deposit") or {})
    blank_default = has("blank-default")
    dep.setdefault("initial", round(price * (0.01 if ftype in ("fha", "va", "usda") else 0.02), -3) or 1000)
    dep.setdefault("with_offer", False)
    dep.setdefault("days", None if blank_default or dep["with_offer"] else 3)
    dep.setdefault("additional", round(price * 0.02, -3) if ftype in ("conventional", "cash") and price > 400000 else None)
    dep.setdefault("additional_days", None if blank_default or not dep["additional"] else 10)
    def loan_for(p, additional):
        """The loan at price p: the spec's amount, else the LTV share. A 100% loan is written as the price less the
        deposits, so the balance to close isn't negative."""
        if ftype == "cash":
            return None
        pct = fin.get("ltv") or {"fha": 96.5, "va": 100, "usda": 100}.get(ftype, 80)
        return fin.get("loan_amount") or min(round(p * pct / 100, -2 if ftype in ("fha", "va") else 3),
                                             p - (dep["initial"] or 0) - (additional or 0))
    loan = loan_for(price, dep["additional"])
    other_amt = spec.get("other_amount")
    balance = price - (dep["initial"] or 0) - (dep["additional"] or 0) - (loan or 0) - (other_amt or 0)
    if balance < 0:
        raise ScenarioError(f"Deposits and loan add up to more than the price (balance to close {balance:,.0f}).")

    # Dates. The offer comes first; a counter the next day; acceptance (the Effective Date) after that.
    D = dict(spec.get("dates") or {})
    base = _dt(D.get("offer") or "2026-09-21 19:05")
    counters = spec.get("counters") or ([spec["counter"]] if spec.get("counter") else [])
    counters = [dict(c) for c in counters]
    if stage == "countered" and not counters:
        counters = [{}]
    t = base
    for i, c in enumerate(counters, start=1):
        c.setdefault("number", i)
        c.setdefault("by", "seller" if i % 2 else "buyer")
        c.setdefault("method", "co")
        if c["method"] not in ("co", "contract"):
            raise ScenarioError(f"Counter #{i} method must be co (a CO-3 counter offer, the default) or contract.")
        if c["method"] == "contract":
            if i != 1 or c["by"] != "seller":
                raise ScenarioError(f"Counter #{i}: only the seller's first counter can be made on the contract itself "
                                    "(Para. 20's counter box). Use a CO-3 counter (method co) for this one.")
            if c.get("deadline"):
                raise ScenarioError("Counter #1 on the contract: the contract has no blank for a new acceptance deadline "
                                    "(Para. 3(a) gives 2 days). Drop `deadline`, or use a CO-3 counter (method co).")
            c["seller_signs_offer"] = True  # the seller signs the contract to make the counter
        unknown = set(c.get("changes") or {}) - set(COUNTER_TERMS)
        if unknown:
            raise ScenarioError(f"Counter #{i} changes {', '.join(sorted(unknown))}: structured changes cover "
                                f"{', '.join(COUNTER_TERMS)}; put anything else in `terms` as text.")
        if c.get("changes") and c["method"] == "co":  # structured changes become CO-3 rows ahead of any free-text terms
            c["terms"] = [{"line": COUNTER_TERMS[k][0][form], "text": COUNTER_TERMS[k][1].format(v)}
                          for k, v in c["changes"].items()] + list(c.get("terms") or [])
        t = _dt(c["date"]) if c.get("date") else _next_daytime(t, rng)
        c["date"] = t
    last_counter = counters[-1] if counters else None
    if len(counters) > 1:
        dropped_terms = sorted({k for c in counters[:-1] for k in ("price", "closing", *(c.get("changes") or {}))
                                if c.get(k) or k in (c.get("changes") or {})} - {k for k in ("price", "closing", *(last_counter.get("changes") or {}))
                                                                                   if last_counter.get(k) or k in (last_counter.get("changes") or {})})
        if dropped_terms:
            notes.append(f"Counter #{last_counter['number']} doesn't restate {', '.join(dropped_terms)} from earlier counters, so "
                         "those terms don't carry over (CO-3); the answer key uses the original offer's values.")
    accepted = stage in ("executed", "amended") or (stage == "countered" and bool(last_counter and last_counter.get("accepted")))
    if last_counter is not None:
        last_counter["accepted"] = accepted
    effective = None
    if accepted:
        effective = _dt(D["effective"]) if D.get("effective") else _next_daytime(t, rng)
        if last_counter is not None:
            last_counter["accepted_at"] = effective
    acceptance_deadline = _dt(D["acceptance_deadline"]) if D.get("acceptance_deadline") else \
        datetime.combine(base.date() + timedelta(days=2), datetime.min.time()).replace(hour=17)
    closing = _d(D["closing"]) if D.get("closing") else _weekday((effective or base).date() + timedelta(days=36))

    # Riders: the scenario's, plus what the property's facts require (frbar-package-check.md).
    riders = rider_list(spec)
    codes = [c for c, _ in riders]
    # Buyer's broker compensation: every package carries it unless the spec says "none". Default: Rider GG with a
    # broker-to-broker compensation agreement due 3 days after the Effective Date. Rider FF (a credit to the buyer)
    # instead when asked. A GG or FF already in `riders` takes the spec's values.
    bb = spec.get("buyer_broker", "GG")
    bb = {"form": bb} if isinstance(bb, str) or bb is None else dict(bb)
    bb_form = str(bb.pop("form", "GG") or "none").upper()
    if bb_form not in ("GG", "FF", "NONE", "FALSE"):
        raise ScenarioError("buyer_broker.form must be GG (compensation agreement), FF (credit to the buyer) or none.")
    if bb_form == "GG":
        bb.setdefault("between", "brokers")
        bb.setdefault("compensation_agreement_days", 3)
    elif bb_form == "FF":
        if not bb.get("percent") and not bb.get("amount"):
            bb["percent"] = 2.5
    present = [c for c in codes if c in ("GG", "FF")]
    if present:
        for code, values in riders:
            if code in present:
                for k, v in bb.items():
                    values.setdefault(k, v)
        bb_form = present[0]
    elif bb_form in ("GG", "FF"):
        riders.append((bb_form, bb))
        codes.append(bb_form)
        how = ("a compensation agreement between the brokers" if bb.get("between") == "brokers" else
               "a compensation agreement between the seller and the buyer's broker") if bb_form == "GG" else "a seller credit to the buyer"
        notes.append(f"Added {cf.rider_name(bb_form)}: buyer's broker paid through {how}.")
    else:
        bb_form = None
    required = []
    if prop["year_built"] < 1978:
        required.append(("P", "built before 1978"))
    if ptype == "condo":
        required.append(("A", "condominium"))
    if prop.get("hoa"):
        required.append(("B", "mandatory homeowners' association"))
    if ftype in ("fha", "va"):
        required.append(("E", "FHA or VA loan"))
    if spec.get("sale_of_buyers_property"):
        required.append(("V", "sale of the buyer's home"))
    dropped = None
    for code, why in required:
        if code in codes:
            continue
        if has("missing-disclosure") and dropped is None:
            dropped = (code, why)
            continue
        riders.append((code, {}))
        codes.append(code)
        notes.append(f"Added {cf.rider_name(code)}: {why}.")
    if has("rider-conflict"):
        bad = "K" if form == cf.AS_IS else ("L" if "K" in codes else "K")
        if bad not in codes:
            riders.append((bad, {}))
            codes.append(bad)
        if form == cf.STANDARD and not {"K", "L"} <= set(codes):
            other = "L" if bad == "K" else "K"
            riders.append((other, {}))
            codes.append(other)
    else:
        try:
            terms = cf.terms(form, {"riders": codes})
        except cf.FormError as e:
            raise ScenarioError(f"{e} (Add the rider-conflict defect to build it anyway.)")
    basis = {"price": price, "rng": rng, "loan": loan, "closing": closing, "city_line": f"{city}, FL {zipc}",
             "start": (effective or base).date(), "deposit": dep["initial"]}
    for code, values in riders:
        note = _rider_defaults(code, values, basis)
        if note:
            notes.append(note)
        if code in ("A", "B"):  # mock association details for the condo and HOA riders
            kind = "Condominium" if code == "A" else "Homeowners"
            values.setdefault("community", sub)
            values.setdefault("association", f"{sub} {kind} Association, Inc.")
            values.setdefault("management_company", rng.choice(["Tidewater Community Management", "Keystone Association Services",
                                                                "Pelican Bay Property Management"]))
            values.setdefault("contact", f"{rng.choice(FIRST)} {rng.choice(LAST)}")
            values.setdefault("phone", f"({area}) 555-{rng.randint(200, 299):04d}")
            values.setdefault("email", "manager@" + re.sub(r"[^a-z]", "", sub.lower()) + "hoa.example")
            values.setdefault("website", re.sub(r"[^a-z]", "", sub.lower()) + "hoa.example")
            values.setdefault("fee", rng.choice([385, 465, 540, 615]) if code == "A" else rng.choice([95, 140, 225, 310]))
            values.setdefault("fee_period", "monthly" if code == "A" else rng.choice(["month", "quarter"]))
            values.setdefault("approval_required", code == "A")
    riders.sort(key=lambda r: (len(r[0]), r[0]))
    codes = [c for c, _ in riders]

    addenda = []
    for a in spec.get("addenda") or []:
        a = {"form": a} if isinstance(a, str) else dict(a)
        a["form"] = a["form"].upper().split("-")[0] if not a["form"].startswith("CR-7") else a["form"]
        addenda.append(a)
    if prop.get("cdd") and "CDDA" not in [a["form"] for a in addenda]:
        addenda.append({"form": "CDDA"})
        notes.append("Added the Community Development District Addendum (CDDA-2): the property is in a CDD.")
    for a in addenda:
        if a["form"] == "CDDA":  # the district and its current assessments have no printed default
            a.setdefault("district", sub.upper())
            a.setdefault("assessments", [{"amount": rng.choice([985, 1150, 1320]), "per": "year", "to": f"{prop['county']} County Tax Collector"},
                                         {"amount": rng.choice([640, 780, 915]), "per": "year", "to": f"{prop['county']} County Tax Collector"}])
    appraisal = cf.appraisal_form(form, {"riders": codes, "addenda": [a["form"] for a in addenda]})
    aga = next((a for a in addenda if a["form"] == "AGA"), None)
    if aga is not None and not D.get("closing"):
        # A default closing falls after the appraisal gap's last date (valuation, delivery, renegotiation) plus 5 days,
        # so a clean scenario never has a contingency outliving closing. A closing the spec gives is kept as is.
        need = (effective or base).date() + timedelta(days=cf.appraisal_window("aga", 0, aga) + 5)
        if closing < need:
            closing = _weekday(need)
    if appraisal == "aga" and ({"F", "E"} & set(codes)):
        notes.append("AGA-1 with Rider F or E: frbar-package-check.md flags this combination (kept as asked).")

    days = {
        "inspection_days": None if blank_default else spec.get("inspection_days", 10 if form == cf.AS_IS else 15),
        "loan_approval_days": None if blank_default or ftype == "cash" else fin.get("approval_days", 30),
        "loan_application_days": None if blank_default or ftype == "cash" else fin.get("application_days", 5),
        "title_evidence_days": None if blank_default else spec.get("title_evidence_days"),
        "flood_elevation_days": spec.get("flood_elevation_days"),
    }

    escrow = dict(spec.get("escrow_agent") or {})
    escrow.setdefault("name", rng.choice(TITLE_COS))
    escrow.setdefault("address", f"{rng.randint(100, 2999)} {rng.choice(['Commerce Pkwy', 'Market St', 'Center Ave'])}, "
                                 f"{city}, FL {zipc}")
    escrow.setdefault("phone", f"({area}) 555-{rng.randint(100, 199):04d}")
    escrow.setdefault("email", "escrow@" + re.sub(r"[^a-z]", "", escrow["name"].lower().replace("title", "")[:14]) + "title.example")
    brokers = dict(spec.get("brokers") or {})
    brokers.setdefault("listing_associate", f"{rng.choice(FIRST)} {rng.choice(LAST)}")
    brokers.setdefault("listing_broker", rng.choice(BROKERAGES))
    brokers.setdefault("cooperating_associate", f"{rng.choice(FIRST)} {rng.choice(LAST)}")
    brokers.setdefault("cooperating_broker", rng.choice([b for b in BROKERAGES if b != brokers["listing_broker"]]))

    ctx = Ctx(
        form=form, stage=stage, buyers=buyers, sellers=sellers,
        buyer_names=" and ".join(buyers), seller_names=" and ".join(sellers),
        property_address=prop["address"], county=prop["county"], tax_id=prop["tax_id"],
        legal_description=prop["legal_description"], year_built=prop["year_built"], property_type=ptype,
        personal_property_included=spec.get("personal_property_included"), excluded_items=spec.get("excluded_items"),
        price=price, list_price=list_price, deposit_initial=dep["initial"], deposit_with_offer=dep["with_offer"], deposit_days=dep["days"],
        additional_deposit=dep["additional"], additional_deposit_days=dep["additional_days"],
        escrow_name=escrow["name"], escrow_address=escrow["address"], escrow_phone=escrow["phone"],
        escrow_email=escrow["email"], escrow_fax=escrow.get("fax"),
        loan_amount=loan, other_amount=other_amt, other_label=spec.get("other_label"), balance_to_close=balance,
        financing=ftype, financing_other=fin.get("other_description"), rate_type=fin.get("rate_type", "fixed" if ftype != "cash" else None),
        max_rate=fin.get("max_rate"), term_years=fin.get("term_years"),
        acceptance_deadline=acceptance_deadline, closing_date=closing, effective_date=effective, offer_date=base,
        tenants=bool(spec.get("tenants")), assignability=spec.get("assignability", "no"),
        title_by=spec.get("title_by", "seller"), title_search_cap=spec.get("title_search_cap"),
        warranty_by=(spec.get("home_warranty") or {}).get("paid_by", "na"),
        warranty_provider=(spec.get("home_warranty") or {}).get("provider"),
        warranty_max=(spec.get("home_warranty") or {}).get("max"),
        assessments=spec.get("special_assessments", "a"),
        seller_costs_other=spec.get("seller_costs_other"), buyer_costs_other=spec.get("buyer_costs_other"),
        repair_limits=spec.get("repair_limits") or {},
        riders=codes, addenda_names=[a["form"] for a in addenda], additional_terms=spec.get("additional_terms"),
        other_addenda=", ".join(form_title(a["form"]) for a in addenda if a["form"] not in DISCLOSURE_FORMS),
        buyer_notice_address=spec.get("buyer_notice_address"), seller_notice_address=spec.get("seller_notice_address"),
        **brokers, **days,
    )
    ctx["counter_on_contract"] = bool(counters and counters[0]["method"] == "contract")
    change_marks = _change_marks(counters[0], ctx, loan_for, effective if counters[0] is last_counter else None) \
        if ctx["counter_on_contract"] else []
    ctx["repair_limit_amounts"] = cf.repair_limits(price, {"repair_limits": ctx["repair_limits"]}) if form == cf.STANDARD else {}
    ctx["area_code"], ctx["escrow_city_line"] = area, f"{city}, FL {zipc}"
    rider_a = next((v for c, v in riders if c == "A"), {})
    ctx["condo_association"] = rider_a.get("association") or f"{sub} Condominium Association, Inc."
    ctx["condo_name"] = rider_a.get("community", sub) + " Condominium"
    # Cash the buyer brings: the down payment and deposits, about 3% in closing costs, and any appraisal gap or
    # escalation the buyer offered to pay in cash (the proof of funds must cover it).
    extra = sum((a.get("gap_amount") or round(price * 0.03, -3)) if a["form"] == "AGA" else
                (a.get("maximum_price") or round(price * 1.05, -3)) - price if a["form"] == "EAC" else 0 for a in addenda)
    ctx["funds_needed"] = price - (loan or 0) + round(price * 0.03) + extra
    if has("unattached-rider") or has("unchecked-rider"):
        pass  # applied when documents are assembled

    # Documents in the order the parties exchange them: the offer (contract, riders, addenda, the seller's disclosures,
    # the buyer's proof of financing or funds), then counters, then what follows acceptance (condo document receipt,
    # escrow deposit receipts), then amendments.
    docs = [{"family": FAMILY[form], "role": "contract", "values": {}, "fill": (spec.get("fill") or {}).get(FAMILY[form], {})}]
    unattached = None
    for code, values in riders:
        if has("unattached-rider") and unattached is None and code not in ("P",):
            unattached = code
            continue
        docs.append({"family": f"CR-7_{code}", "role": "rider", "code": code, "values": values,
                     "fill": values.pop("fill", {}), "presigned_by_seller": code in PRESIGNED_BY_SELLER})
    unchecked = None
    if has("unchecked-rider"):
        unchecked = next((c for c in reversed(codes) if c != unattached), None)
        ctx["riders"] = [c for c in codes if c != unchecked]
    for a in sorted(addenda, key=lambda a: ADDENDA_ORDER.index(a["form"]) if a["form"] in ADDENDA_ORDER else 99):
        if a["form"] not in DISCLOSURE_FORMS:
            docs.append({"family": a["form"], "role": "addendum", "values": a, "fill": a.get("fill", {})})

    package = dict(spec.get("package") or {})
    norm = lambda x: str(x).lower() if str(x).lower() in LETTERS else str(x).upper().split("-")[0]  # noqa: E731
    include = [norm(x) for x in package.get("include") or []]
    exclude = {norm(x) for x in package.get("exclude") or []}
    spec_disclosures = {norm(k): dict(v or {}) for k, v in (spec.get("disclosures") or {}).items()}
    for a in addenda:
        if a["form"] in DISCLOSURE_FORMS:
            spec_disclosures.setdefault(a["form"], {}).update({k: v for k, v in a.items() if k != "form"})
    wanted = default_disclosures(ptype, prop, spec) + list(spec_disclosures) + [f for f in include if f not in LETTERS]
    seen = set()
    wanted = [f for f in wanted if f not in seen and not seen.add(f) and f not in exclude]
    for f in wanted:
        form_title(f)  # an unknown family stops the build here, with the list of known ones
    dropped_disclosure = None
    if has("missing-disclosure") and dropped is None:
        dropped_disclosure = next((f for f in ("FD", "SPDR", "SPDC") if f in wanted), None)
        wanted = [f for f in wanted if f != dropped_disclosure]
    receipt_date = _next_daytime((effective or base) + timedelta(days=1), rng)
    for f in wanted:
        if f == "RCD" and not accepted:
            continue  # the buyer receives the condo documents after the contract is signed
        values = spec_disclosures.get(f, {})
        # Answers that follow the property's facts, so a disclosure never contradicts a rider; the spec's own win.
        facts = {"membership in a homeowner": "yes"} if f == "SPDR" and prop.get("hoa") else {}
        if f == "SPDR" and prop.get("sinkhole_claim"):
            facts["insurance claim for sinkhole damage"] = "yes"
        if f == "SPDR" and prop.get("coastal"):
            facts["seaward of the coastal construction control line"] = "yes"
        values["answers"] = {**DEFAULT_ANSWERS.get(f, {}), **facts, **(values.get("answers") or {})}
        if f == "RCD":
            values["received"] = _dt(values.get("received") or receipt_date)
        if f == "NMOB":  # the highest-and-best deadline: after the buyer's offer goes in
            values["deadline"] = _dt(values["deadline"]) if values.get("deadline") else \
                (base.replace(hour=21, minute=0) if base.hour < 20 else (base + timedelta(days=1)).replace(hour=12, minute=0))
        docs.append({"family": f, "role": "disclosure", "values": values, "fill": values.get("fill", {}),
                     "after_acceptance": f == "RCD"})
    proof = package.get("proof") or ("proof_of_funds" if ftype == "cash" else
                                     "both" if {"AGA", "EAC"} & {a["form"] for a in addenda} else "pre_approval")
    kinds = ["pre_approval", "proof_of_funds"] if proof == "both" else [proof] if proof in LETTERS else []
    kinds += [k for k in include if k in ("pre_approval", "proof_of_funds") and k not in kinds]
    for kind in kinds:
        if kind in exclude or (kind == "pre_approval" and ftype == "cash"):
            continue
        when_ = base - timedelta(days=4 if kind == "pre_approval" else 2)
        values = {"date": when_.replace(hour=10, minute=15), **dict((spec.get("letters") or {}).get(kind) or {})}
        if kind == "pre_approval":
            values.setdefault("lender", rng.choice(LENDERS))  # chosen here so the answer key can name the lender
        else:
            values.setdefault("bank", rng.choice(BANKS))
        docs.append({"family": kind, "role": "letter", "values": values})
    for c in counters:
        if c["method"] == "co":
            docs.append({"family": "CO", "role": "counter", "values": c, "fill": c.get("fill", {})})
    # After acceptance: the condo document receipt, then the escrow agent's receipt for each deposit made so far.
    docs = [d for d in docs if not d.get("after_acceptance")] + [d for d in docs if d.get("after_acceptance")]
    deposits = []
    if accepted and "ESCROW_RECEIPT" not in exclude and "escrow_receipt" not in exclude:
        first = base + timedelta(hours=1) if dep["with_offer"] else \
            (_next_daytime(effective, rng) if (dep["days"] or 3) > 1 else effective + timedelta(hours=2))
        deposits.append({"label": "Initial deposit", "amount": dep["initial"], "date": first})
        if dep["additional"] and stage == "amended":
            deposits.append({"label": "Additional deposit", "amount": dep["additional"],
                             "date": _next_daytime(effective + timedelta(days=(dep["additional_days"] or 10) - 2), rng)})
        for d in deposits:
            docs.append({"family": "escrow_receipt", "role": "letter", "values": {**d, "method": "Wire transfer"}})
    amendments = [dict(a) for a in spec.get("amendments") or []]
    if stage == "amended" and not amendments:
        amendments = [{"form": "EA", "closing": str(closing + timedelta(days=7))}]
    t_am = effective
    per_form = {}
    for a in amendments:
        a.setdefault("form", "EA" if set(a) & printed_keys("EA") and not a.get("text") else "ACSP")
        a["form"] = a["form"].upper().split("-")[0]
        per_form[a["form"]] = per_form.get(a["form"], 0) + 1
        a.setdefault("number", per_form[a["form"]])
        i = sum(per_form.values())
        if a.get("date"):
            t_am = _dt(a["date"])
        elif a.get("inspection_extra_days") and effective:
            insp = next((c["changes"]["inspection_days"] for c in reversed(counters) if (c.get("changes") or {}).get("inspection_days")),
                        days["inspection_days"] or 15)
            t_am = effective + timedelta(days=max(1, insp - 2), hours=2)
        else:
            t_am = (t_am or base) + timedelta(days=6 + 2 * i, hours=2)
        a["date"] = t_am
        a.setdefault("signed", "all")
        docs.append({"family": a["form"], "role": "amendment", "values": a, "fill": a.get("fill", {})})
    events = _signing(docs, ctx, counters, amendments, stage, accepted, base, effective)
    gg_values = next((v for c, v in riders if c == "GG"), bb)
    compensation = _compensation(bb_form, gg_values, ctx, accepted, base, effective, rng, has("late-compensation-agreement"))
    if has("late-compensation-agreement") and not (compensation and compensation["executed"]):
        raise ScenarioError("The late-compensation-agreement defect needs Rider GG on an accepted contract.")
    # Where each signature defect lands, so the answer key says exactly what's missing.
    for d in defects:
        if d["type"] in ("missing-initials", "missing-signature"):
            d.setdefault("party", "seller" if accepted else "buyer")
            d.setdefault("signer", 0)
            d.setdefault("doc_index", 0)
            names = ctx["buyers"] if d["party"] == "buyer" else ctx["sellers"]
            d["name"] = names[min(d["signer"], len(names) - 1)]
            d["document"] = docs[d["doc_index"]]["family"]
            if d["type"] == "missing-initials":
                d.setdefault("page", 4)
    key = _answer_key(spec, ctx, form, docs, counters, amendments, stage, effective, riders, notes, defects,
                      dropped, unattached, unchecked, bb_form, bb, dropped_disclosure)
    key["mock"]["compensation_agreement"] = None if not compensation else {
        k: (when(v) if isinstance(v, datetime) else v) for k, v in compensation.items() if k != "values"}
    # File names follow the address, as an agent's files do: "1532-Cypress-Bend-Dr-Contract.pdf".
    files = {"key": f"key/{street_slug}-Answer-Key.json", "spec": f"key/{street_slug}-Spec.json",
             "package": f"{street_slug}-{'Contract' if accepted else 'Offer'}.pdf",
             "scanned": f"{street_slug}-{'Contract' if accepted else 'Offer'}-Scanned.pdf",
             "compensation": f"{street_slug}-Compensation-Agreement.pdf"}
    return {"name": name, "files": files, "ctx": ctx, "documents": docs, "events": events, "defects": defects, "notes": notes,
            "compensation": compensation, "change_marks": change_marks,
            "key": key, "rng_seed": name, "dropped": dropped, "unattached": unattached, "unchecked": unchecked}


def _change_marks(c, ctx, loan_for, accepted_at):
    """The marks a seller's counter on the contract leaves: [{field, old, new, seller_at, buyer_at}] for each change on
    a mapped contract blank, then {field: additional_terms, text, ...} for free-text terms, which go on Para. 20's
    lines after the buyer's. The seller initials each at the counter; on acceptance the buyer initials each one, the
    last at the Effective Date (Para. 3(b)). buyer_at is None while the counter is pending. A new price or additional
    deposit also changes the loan (same LTV rule as the offer) and the balance to close in Para. 2, so those lines
    are struck and retyped too and the page still adds up."""
    fmt = {"price": money, "closing_date": mdy, "additional_deposit": money, "loan_amount": money, "balance_to_close": money}
    items = []
    for key, new in [("price", c.get("price")), ("closing", c.get("closing")), *(c.get("changes") or {}).items()]:
        if new in (None, ""):
            continue
        field = CONTRACT_CHANGE_FIELDS.get(key)
        if not field:
            raise ScenarioError(f"Counter #1 on the contract changes {key}, which has no blank on the contract. Put it in "
                                "`terms` as text, or use a CO-3 counter (method co).")
        old = {"price": ctx["price"], "closing_date": ctx["closing_date"]}.get(field, ctx.get(field))
        f = fmt.get(field, str)
        items.append({"field": field, "old": f(old) if old not in (None, "") else None, "new": f(new)})
    price = c.get("price") or ctx["price"]
    additional = (c.get("changes") or {}).get("additional_deposit", ctx["additional_deposit"])
    if price != ctx["price"] or additional != ctx["additional_deposit"]:
        loan = loan_for(price, additional) if price != ctx["price"] else ctx["loan_amount"]
        balance = price - (ctx["deposit_initial"] or 0) - (additional or 0) - (loan or 0) - (ctx["other_amount"] or 0)
        if balance < 0:
            raise ScenarioError(f"Counter #1 on the contract: deposits and loan add up to more than ${price:,.0f}.")
        for field, old, new in (("loan_amount", ctx["loan_amount"], loan), ("balance_to_close", ctx["balance_to_close"], balance)):
            if new != old and (field != "loan_amount" or loan is not None):
                items.append({"field": field, "old": money(old) if old is not None else None, "new": money(new)})
    text = [t["text"] for t in c.get("terms") or []]
    text += [f"The following items are included: {c['included']}."] if c.get("included") else []
    text += [f"The following items are excluded: {c['excluded']}."] if c.get("excluded") else []
    if text:
        items.append({"field": "additional_terms", "text": "Seller's counter-offer: " + " ".join(text)})
    for n, m in enumerate(items):
        m["seller_at"] = c["date"] + timedelta(minutes=n)
        m["buyer_at"] = accepted_at - timedelta(minutes=len(items) - 1 - n) if accepted_at else None
    return items


def _compensation(bb_form, bb, ctx, accepted, offer, effective, rng, late):
    """The CASSB-1 compensation agreement Rider GG calls for, as a separate file: who pays (the seller, or the listing
    broker through its associate), the amount, and when each side signs.

    Accepted contract: the buyer's broker signs shortly after the Effective Date and the payer signs later, on a day
    inside GG's window (N days after the Effective Date, 3 if blank), so the agreement is executed after the contract
    and before the buyer's cancel right opens. With the late-compensation-agreement defect the payer signs 1 or 2
    days after the window. Offer not yet accepted: a draft the buyer's broker has signed and sent with the offer."""
    if bb_form != "GG":
        return None
    days = bb.get("compensation_agreement_days") or 3
    between = bb.get("between", "brokers")
    values = {"between": between, "percent": bb.get("percent"), "amount": bb.get("amount"),
              "term_days": bb.get("term_days", 30), "other_terms": bb.get("other_terms")}
    if not values["percent"] and not values["amount"]:
        values["percent"] = 2.5
    payer = "seller" if between == "seller" else "listing_agent"
    out = {"between": between, "payer": ctx["seller_names"] if payer == "seller" else
           f"{ctx['listing_broker']} (signed by {ctx['listing_associate']})",
           "buyers_broker": f"{ctx['cooperating_broker']} (signed by {ctx['cooperating_associate']})",
           "percent": values["percent"], "amount": values["amount"], "window_days": days, "values": values,
           "payer_party": payer}
    if not accepted:
        out.update(executed=False, buyers_broker_signed=offer + timedelta(minutes=35), payer_signed=None,
                   note="Draft sent with the offer; the window starts at the Effective Date")
        return out
    window_end = datetime.combine(effective.date() + timedelta(days=days), datetime.min.time()).replace(hour=23, minute=59)
    bb_signed = effective + timedelta(hours=1, minutes=rng.randint(5, 50))
    if late:
        day = effective.date() + timedelta(days=days + rng.randint(1, 2))
    else:
        day = effective.date() + timedelta(days=rng.randint(1, days))
    payer_signed = datetime.combine(day, datetime.min.time()).replace(hour=rng.randint(9, 18), minute=rng.randint(0, 59))
    if payer_signed <= bb_signed:
        payer_signed = bb_signed + timedelta(hours=3)
    out.update(executed=True, buyers_broker_signed=bb_signed, payer_signed=payer_signed, window_ends=window_end,
               within_window=payer_signed <= window_end)
    return out


def _signing(docs, ctx, counters, amendments, stage, accepted, offer, effective):
    """For each document, the signers and when: {doc index: [(party, index, datetime)]}.

    Offer documents (contract, riders, offer addenda): buyers at the offer, sellers at acceptance when the offer
    itself is accepted (no counter). A counter: its maker when made; the other side when it's accepted (the final
    one sets the Effective Date). Amendments: both sides on their date, or only `signed` ("buyer"/"seller").
    Disclosures: seller two weeks before the offer, buyer at the offer."""
    events = {}
    no_counter = not counters

    def sign(i, party, dt):
        n = len(ctx["buyers"] if party == "buyer" else ctx["sellers"])
        events.setdefault(i, []).extend((party, k, dt + timedelta(minutes=3 * k)) for k in range(n))

    seller_signs_offer = bool(counters and counters[0].get("seller_signs_offer"))
    for i, d in enumerate(docs):
        role, v = d["role"], d["values"]
        if role in ("contract", "rider", "addendum"):
            if d.get("presigned_by_seller"):  # the seller's own disclosure (Rider P), filled in before any offer
                sign(i, "seller", offer - timedelta(days=12, hours=2))
                sign(i, "buyer", offer)
                continue
            sign(i, "buyer", offer)
            if accepted and no_counter:
                sign(i, "seller", effective)
            elif seller_signs_offer:  # some sellers sign the offer along with their counter
                sign(i, "seller", counters[0]["date"])
        elif role == "counter":
            maker = v["by"]
            other = "buyer" if maker == "seller" else "seller"
            sign(i, maker, v["date"])
            if v is counters[-1] and v.get("accepted"):
                sign(i, other, v["accepted_at"])
        elif role == "amendment":
            who = v.get("signed", "all")
            for party in ("buyer", "seller"):
                if who in ("all", party):
                    sign(i, party, v["date"] + (timedelta(hours=3) if party == "seller" else timedelta()))
        elif role == "disclosure":
            if d["family"] == "RCD":  # the buyer's receipt for the condo documents, dated when they arrive
                sign(i, "buyer", v["received"])
                continue
            if d["family"] == "NMOB":  # the seller's call for highest and best, then the buyer's acknowledgment, before the offer
                sign(i, "seller", offer - timedelta(days=1, hours=4))
                sign(i, "buyer", offer - timedelta(hours=20))
                continue
            sign(i, "seller", offer - timedelta(days=14, hours=3))
            sign(i, "buyer", offer - timedelta(minutes=20))
    return events


def _answer_key(spec, ctx, form, docs, counters, amendments, stage, effective, riders, notes, defects, dropped,
                unattached, unchecked, bb_form=None, bb=None, dropped_disclosure=None):
    """The ground truth in contract-timeline's deal-file schema, plus what the mock package holds."""
    accepted = effective is not None
    last = counters[-1] if counters else None
    # Only the accepted counter changes the offer: CO-3 "does not include terms and conditions of any other counter
    # offer unless restated herein". A pending one changes nothing (it's listed under mock.counters).
    price, closing, changed = ctx["price"], ctx["closing_date"], {}
    if accepted and counters:
        c = counters[-1]
        price = c.get("price") or price
        closing = _d(c["closing"]) if c.get("closing") else closing
        changed.update(c.get("changes") or {})
    if accepted and last is not None and last["method"] == "contract":
        source = f"Buyer's initials on the Seller's counter-offer changes (Para. 3(b)), {when(effective)}"
    elif accepted and last is not None:
        party = "Seller" if last["by"] == "buyer" else "Buyer"
        source = f"{party}'s signature on Counter Offer #{last['number']}, {when(effective)}"
    elif accepted:
        source = f"Seller's signature on the contract, {when(effective)}"
    else:
        source = None
    contract = {
        "form_family": "frbar", "contract_form": form, "form_revision": cf.VERIFIED[FAMILY[form]],
        "property": ctx["property_address"], "buyer": ctx["buyer_names"], "seller": ctx["seller_names"], "price": price,
        "financing": ctx["financing"], "effective_date": effective.date().isoformat() if effective else None,
        "effective_date_source": source, "closing_date": closing.isoformat(),
        "escrow_agent": ctx["escrow_name"], "deposit_amount_str": f"${ctx['deposit_initial']:,.0f}",
        "deposit_days": 0 if ctx["deposit_with_offer"] else (ctx["deposit_days"] or 3),
        "loan_application_days": None if ctx["financing"] == "cash" else ctx["loan_application_days"] or 5,
        "loan_approval_days": None if ctx["financing"] == "cash" else ctx["loan_approval_days"] or 30,
        "inspection_days": ctx["inspection_days"] or 15,
        "riders": [cf.RIDERS[c] for c, _ in riders if c != unattached],
        "year_built": ctx["year_built"], "title_by": ctx["title_by"],
        "hoa": True if "B" in [c for c, _ in riders] else None,
        "hoa_disclosure_before_contract": True if "B" in [c for c, _ in riders] else None,
        "condo": True if ctx["property_type"] == "condo" else None,
        "condo_docs_received": next((d["values"]["received"].date().isoformat() for d in docs if d["family"] == "RCD"), None),
    }
    if ctx["additional_deposit"]:
        contract["additional_deposit_amount_str"] = f"${ctx['additional_deposit']:,.0f}"
        contract["additional_deposit_days"] = ctx["additional_deposit_days"] or 10
    if ctx["title_evidence_days"]:
        contract["title_evidence_days_before"] = ctx["title_evidence_days"]
    if ctx["tenants"]:
        contract["tenants"] = True
    for code, values in riders:  # rider days and dates the rider prints, under the deal file's names (frbar.md)
        printed = printed_keys(f"CR-7_{code}")
        for k, v in values.items():
            name = DEAL_NAMES.get(k, k)
            if k in printed and name and k.endswith(("_days", "_date", "_days_before")) and not k.startswith("approval") \
                    and v not in (None, ""):
                contract[name] = _d(v).isoformat() if k.endswith("_date") else v
        if code == "P":  # Rider P checks "Waived the opportunity" unless the buyer received a risk assessment
            contract["lbp_waived"] = values.get("risk_assessment") != "received"
        for flag in DEAL_FLAGS:  # yes/no boxes the rider prints (Rider N's CCCL request, Rider A's)
            if flag in printed and values.get(flag) is not None:
                contract[flag] = bool(values[flag])
        if code in ("A", "B") and values.get("approval_required"):
            contract["association_approval"] = True
            if values.get("approval_initiate_days"):
                contract["association_apply_days"] = values["approval_initiate_days"]
            if values.get("approval_days"):
                contract["association_approval_days_before"] = values["approval_days"]
    offer_addenda = [d for d in docs if d["role"] == "addendum"]
    if offer_addenda:
        contract["addenda"] = [form_title(d["family"]) for d in offer_addenda]
    for k, v in changed.items():
        if k == "additional_deposit":
            contract["additional_deposit_amount_str"] = f"${v:,.0f}"
        elif k == "title_evidence_days":
            contract["title_evidence_days_before"] = v
        else:
            contract[k] = v
    contract = {k: v for k, v in contract.items() if v is not None}
    amend = []
    contract = dict(contract)
    base_contract = dict(contract)
    for a in amendments:
        if a.get("signed", "all") != "all":
            continue
        changes = {k: a[k] for k in ("closing_date", "inspection_days", "loan_approval_days", "price") if k in a}
        if a.get("closing"):
            changes["closing_date"] = str(a["closing"])
        if a.get("inspection_extra_days"):
            contract["inspection_days"] = changes["inspection_days"] = contract["inspection_days"] + a["inspection_extra_days"]
        if a.get("loan_approval_extra_days") and ctx["financing"] != "cash":
            contract["loan_approval_days"] = changes["loan_approval_days"] = \
                contract["loan_approval_days"] + a["loan_approval_extra_days"]
        if a.get("short_sale_extra_days") and "G" in ctx["riders"]:
            contract["short_sale_approval_days"] = changes["short_sale_approval_days"] = \
                contract.get("short_sale_approval_days", 90) + a["short_sale_extra_days"]
        entry = {"date": a["date"].date().isoformat(), "description": a.get("description") or
                 ("Extension Addendum" if a["form"] == "EA" else f"Addendum No. {a['number']}"), "changes": changes}
        overrides = {EA_OVERRIDES[k]: _d(a[k]).isoformat() for k in EA_OVERRIDES if a.get(k)} if a["form"] == "EA" else {}
        if overrides:
            entry["date_overrides"] = overrides
        amend.append(entry)
    contract = base_contract  # the deal file keeps the contract as signed; amendments carry the changes
    deadlines = []
    aga = next((d["values"] for d in docs if d["family"] == "AGA"), None)
    if aga is not None:  # frbar.md: AGA-1 sets no timeline row of its own, so its dates go in `deadlines`
        valuation = aga.get("valuation_days") or cf.AGA_VALUATION_DAYS
        deadlines += [
            {"key": "aga_valuation", "label": "Appraisal Gap Valuation Due", "short": "Gap Valuation", "basis": "after",
             "days": valuation, "party": "Buyer", "critical": False, "contingency": False, "source": "AGA-1",
             "action": "Obtain the Valuation, then deliver a copy to Seller within 3 days",
             "if_missed": "The form is silent: confirm with the other side"},
            {"key": "aga_renegotiation", "label": "Appraisal Gap Renegotiation Ends", "short": "Gap Renegotiation",
             "basis": "after", "days": cf.appraisal_window("aga", 0, aga), "party": "Both", "critical": True,
             "contingency": True, "source": "AGA-1",
             "action": "If the Valuation plus the Gap Amount is below the price, sign an addendum with revised terms",
             "if_missed": "The contract terminates and the Buyer's deposit is returned"}]
    mock = {
            "stage": stage, "documents": [d["family"] for d in docs], "accepted": accepted,
            "deposits_received": [{"label": d["values"]["label"], "amount": d["values"]["amount"], "date": when(d["values"]["date"])}
                                  for d in docs if d["family"] == "escrow_receipt"],
            "pending": None if accepted else ("counter offer" if counters else "seller's acceptance"),
            "counters": [{"number": c["number"], "by": c["by"], "method": c["method"], "date": when(c["date"]), "accepted": c.get("accepted", False),
                          **{k: (str(v) if isinstance(v, (date, datetime)) else v) for k, v in c.items()
                             if k in ("price", "closing", "terms", "changes")}} for c in counters],
            "defects": [{**d, "what": DEFECTS[d["type"]]} for d in defects],
            "buyer_broker": {"form": bb_form, **{k: v for k, v in bb.items() if k != "fill"}} if bb_form else None,
            "property_facts": {"type": ctx["property_type"], "year_built": ctx["year_built"], "hoa": bool(spec.get("property", {}).get("hoa")) or (dropped or ("",))[0] == "B",
                               **{k: (spec.get("property") or {})[k] for k in ("cdd", "sinkhole_claim", "coastal", "septic", "flood_zone")
                                  if (spec.get("property") or {}).get(k)}},
            "dropped_rider": dropped[0] if dropped else None, "dropped_disclosure": dropped_disclosure, "unattached_rider": unattached, "unchecked_rider": unchecked,
            "notes": notes,
    }
    if not accepted:  # not a contract yet: the key is the offer as seller-offer-review records it
        return _offer_key(ctx, form, docs, riders, bb_form, bb, mock)
    return {
        "side": spec.get("side", "buyer"), "state": "FL", "county": ctx["county"], "client": ctx["buyer_names"],
        "contract": contract, "deadlines": deadlines, "amendments": amend, "flags": [], "mock": mock,
    }


def _offer_key(ctx, form, docs, riders, bb_form, bb, mock):
    """The answer key for a package that isn't a contract yet (an offer, or an offer with a counter pending): a
    seller-offer-review listing file (skills/seller-offer-review/references/listing-file.md) with the offer as written.
    A pending counter is in mock.counters; it changes nothing until it's accepted. contract-timeline takes only an
    executed contract, so feeding it this package should get a "not executed yet" answer (mock.accepted is false)."""
    codes = [c for c, _ in riders if c != mock.get("unattached_rider")]
    values = {c: v for c, v in riders}
    letters_ = {d["family"]: d["values"] for d in docs if d["role"] == "letter"}
    addenda = {d["family"]: d["values"] for d in docs if d["role"] == "addendum"}
    price, loan = ctx["price"], ctx["loan_amount"]
    offer = {
        "id": "A", "status": "active", "received": ctx["offer_date"].strftime("%Y-%m-%d %H:%M"),
        "expires": ctx["acceptance_deadline"].strftime("%Y-%m-%d %H:%M"), "buyer": ctx["buyer_names"],
        "buyer_agent": ctx["cooperating_associate"], "buyer_brokerage": ctx["cooperating_broker"],
        "contract_form": form, "form_revision": cf.VERIFIED[FAMILY[form]], "price": price, "financing": ctx["financing"],
        "down_pct": None if ctx["financing"] == "cash" else round(1 - (loan or 0) / price, 4), "loan_amount": loan,
        "approval": "preapproval" if "pre_approval" in letters_ else "pof_verified" if "proof_of_funds" in letters_ else "none",
        "deposit": (ctx["deposit_initial"] or 0) + (ctx["additional_deposit"] or 0),
        "seller_concessions": 0, "closing_date": ctx["closing_date"].isoformat(), "title_by": ctx["title_by"],
        "inspection_days": (values.get("K") or values.get("L") or {}).get("inspection_days") or ctx["inspection_days"] or 15,
        "loan_approval_days": None if ctx["financing"] == "cash" else ctx["loan_approval_days"] or 30,
        "riders": codes,
    }
    lender = (letters_.get("pre_approval") or {}).get("lender")
    if lender:
        offer["lender"] = lender[0] if isinstance(lender, (list, tuple)) else lender
    if ctx["warranty_by"] == "seller" and ctx["warranty_max"]:
        offer["home_warranty"] = ctx["warranty_max"]
    if form == cf.STANDARD and ctx["repair_limits"]:
        offer["repair_limits"] = ctx["repair_limits"]
    if bb_form == "GG":
        offer["buyer_broker_form"] = "GG"
        if bb.get("percent"):
            offer["buyer_broker_pct"] = bb["percent"] / 100
        elif bb.get("amount"):
            offer["buyer_broker_amount"] = bb["amount"]
        else:
            offer["buyer_broker_pct"] = 0.025
    elif bb_form == "FF":
        offer["buyer_broker_form"] = "FF"
        if bb.get("percent"):
            offer["buyer_broker_pct"] = bb["percent"] / 100
        if bb.get("amount"):
            offer["buyer_broker_amount"] = bb["amount"]
    if "F" in codes:
        offer["appraisal_contingency"] = True
    if "AGA" in addenda:
        a = addenda["AGA"]
        offer.update(appraisal_form="aga", appraisal_gap=a.get("gap_amount") or round(price * 0.03, -3))
        for k_from, k_to in (("valuation_days", "aga_valuation_days"), ("renegotiate_days", "aga_renegotiate_days")):
            if a.get(k_from):
                offer[k_to] = a[k_from]
    if "EAC" in addenda:
        a = addenda["EAC"]
        offer["escalation"] = {"cap": a.get("maximum_price") or round(price * 1.05, -3),
                               "increment": a.get("escalation_amount") or 2500, "proof": True}
    if "X" in codes:
        offer["kickout"] = True
    if "U" in codes:
        offer.update({k: values["U"][k] for k in ("rent_back_days", "rent_back_monthly") if values["U"].get(k)})
    if "C" in codes:
        offer["seller_financing"] = values["C"]["seller_financing"]
    # Rider dates become days from the offer (the listing file counts them from the Effective Date, not known yet).
    for code, k_from, k_to in (("H", "insurance_date", "insurance_days"), ("V", "sale_contingency_date", "sale_contingency_days"),
                               ("Z", "buyer_attorney_date", "attorney_days")):
        if code in codes and values[code].get(k_from):
            offer[k_to] = (_d(values[code][k_from]) - ctx["offer_date"].date()).days
    if ctx["additional_terms"]:
        offer["other_terms"] = ctx["additional_terms"]
    if ctx["personal_property_included"]:
        offer["personal_property"] = ctx["personal_property_included"]
    listing = {"address": ctx["property_address"], "state": "FL", "county": ctx["county"], "list_price": ctx["list_price"],
               "year_built": ctx["year_built"], "property_type": ctx["property_type"],
               "flood_disclosure": any(d["family"] == "FD" for d in docs)}
    return {"analysis_date": ctx["offer_date"].date().isoformat(), "listing": listing, "seller": {"name": ctx["seller_names"]},
            "offers": [{k: v for k, v in offer.items() if v is not None}], "mock": mock}
