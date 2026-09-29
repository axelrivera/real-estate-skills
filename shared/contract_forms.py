"""Which contract rules apply to which form and rider set, in one place.

    from _shared import contract_forms as cf
    form = cf.normalize("AS IS")                 # 'as_is' | 'standard' | 'other' | None (not given)
    t = cf.terms(form, offer)                    # {'walkaway', 'repairs_owed', 'riders', 'label', ...} per form + riders
    cf.inspection_walkaway(form, offer)          # t['walkaway']: True when the buyer may cancel for any reason
    cf.repair_limits(price, offer)               # Standard repairs: {'general', 'wdo', 'permit'} in dollars
    cf.rider_codes(["FHA/VA Financing", "K"])    # (['E', 'K'], []): CR-7 letters, and names that aren't riders
    cf.revision_note(form, "ASIS-8 Rev. 1/27")   # chat note when the contract isn't the verified revision

Fully supported forms are the FR/BAR AS IS and Standard contracts and their CR-7 riders, verified against the PDFs
listed in dev/forms/frbar-forms.json (make forms-check). Their rules differ in Para. 12 and 9(a), so the math never
mixes, and three riders change them:

- AS IS: the inspection period is a walk-away right; the seller has no repair obligation, so a seller's downside
  reserves the market's typical post-inspection credit. Riders I, K and L are RESERVED on this form.
- Standard: no walk-away; the inspection period is the deadline for repair notices, and the seller owes repairs up
  to the General Repair, WDO and Permit Limits (1.5% of price each when blank). Either party may terminate only when
  repairs exceed a limit, after the seller's estimates (10 days) and the election (5 days).
- Standard + Rider K ("As Is"): Paras. 9(a) limits, 11 and 12 are deleted; the buyer may cancel for any reason in
  the rider's inspection period (15 days if blank) and the seller owes no repairs. AS IS math, Standard label.
- Standard + Rider L (Right to Inspect and Cancel): the buyer may cancel for any reason in the Right To Inspect
  Period (15 days if blank), and repairs timely reported are still owed up to the limits. Both rules apply.
- Any other contract ('other'): best effort. No FR/BAR default or figure applies; whether its inspection period is a
  walk-away comes only from the file (`inspection_walkaway`), and callers ask or record an assumption when it's missing.
"""
import re

AS_IS, STANDARD, OTHER = "as_is", "standard", "other"
FRBAR = (AS_IS, STANDARD)
REPAIR_LIMIT_DEFAULT = 0.015  # Para. 9(a): 1.5% of the price for each limit when blank
REPAIR_LIMIT_KEYS = ("general", "wdo", "permit")
INSPECTION_DAYS_DEFAULT = 15  # Para. 12(a) of both forms: 15 days after the Effective Date when blank
STANDARD_REPAIR_WINDOW_DAYS = 15  # after the repair notice: the seller's estimates (10 days), then the election (5 days)
RIDER_INSPECTION_DAYS_DEFAULT = 15  # Rider K 2(a) and Rider L 1: 15 days when blank

# The revisions the built-in rules were checked against: must match dev/forms/frbar-forms.json (make forms-check).
VERIFIED = {"FRBAR-ASIS": "FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26",
            "FRBAR-STANDARD": "FloridaRealtors/FloridaBar – 7x Rev. 2/26"}
_VERIFIED_FOR = {AS_IS: "FRBAR-ASIS", STANDARD: "FRBAR-STANDARD"}

_ALIASES = {  # compared lowercase, with "_" and "-" read as spaces. CRSP-17 is a different form: 'other'.
    "as is": AS_IS, "asis": AS_IS, "asis 7": AS_IS, "asis 7x": AS_IS, "fr/bar as is": AS_IS, "frbar as is": AS_IS,
    "as is residential contract for sale and purchase": AS_IS,
    "standard": STANDARD, "fr/bar standard": STANDARD, "frbar standard": STANDARD,
    "residential contract for sale and purchase": STANDARD,
}

# CR-7 riders as printed in Para. 19 of both forms. EE was the PACE Disclosure rider before Rev. 2/26.
RIDERS = {
    "A": "Condominium", "B": "Homeowners' Association", "C": "Seller Financing", "D": "Mortgage Assumption",
    "E": "FHA/VA Financing", "F": "Appraisal Contingency", "G": "Short Sale", "H": "Homeowners'/Flood Insurance",
    "I": "Mold Inspection", "J": "Interest-Bearing Account", "K": "As Is", "L": "Right to Inspect and Right to Cancel",
    "M": "Defective Drywall", "N": "Coastal Construction Control Line", "O": "Insulation Disclosure",
    "P": "Lead-Based Paint Disclosure", "Q": "Housing for Older Persons", "R": "Rezoning",
    "S": "Lease Purchase/Lease Option", "T": "Pre-Closing Occupancy", "U": "Post-Closing Occupancy",
    "V": "Sale of Buyer's Property", "W": "Back-Up Contract", "X": "Kick-Out Clause", "Y": "Seller's Attorney Approval",
    "Z": "Buyer's Attorney Approval", "AA": "Licensee Property Interest", "BB": "Binding Arbitration",
    "CC": "Miami-Dade County Special Taxing District Disclosure", "DD": "Seasonal/Vacation Rentals",
    "EE": "Qualifying Improvements Disclosure", "FF": "Credit Related to Buyer's Broker Compensation",
    "GG": "Seller's Agreement with Respect to Buyer's Broker Compensation",
}
RESERVED_ON_AS_IS = ("I", "K", "L")
_SHORT = {"K": "As Is", "L": "Right to Inspect"}  # labels on reports

# Name words to rider letter, checked in order (most specific first), as whole words in the lowercase name with hyphens
# read as spaces ("Short-Sale Rider"). Condominium comes before the association words: "Condominium Association" is A.
_RIDER_WORDS = (
    ("GG", r"seller'?s?'? agreement"), ("FF", r"credit related|broker compensation credit"),
    ("T", r"pre ?closing occupancy"), ("U", r"post ?closing occupancy"),
    ("Y", r"seller'?s?'? attorney"), ("Z", r"buyer'?s?'? attorney"),
    ("V", r"sale of buyer'?s?( property)?|sale contingency"), ("X", r"kick ?out"), ("W", r"back ?up"),
    ("L", r"right to inspect|right to cancel"), ("K", r"as ?is"),
    ("H", r"insurance|flood ins"), ("A", r"condominium|condo"),
    ("B", r"homeowners'? assn|association|hoa|community disclosure"),
    ("C", r"seller financing|purchase money"), ("D", r"assumption"),
    ("E", r"fha|va"), ("F", r"appraisal contingency|appraisal(?! gap)"), ("G", r"short ?sale"), ("I", r"mold"),
    ("J", r"interest bearing"), ("M", r"drywall"), ("N", r"coastal construction|cccl"), ("O", r"insulation"),
    ("P", r"lead ?based paint|lead paint"), ("Q", r"older persons"), ("R", r"rezoning"),
    ("S", r"lease purchase|lease option"), ("AA", r"licensee|personal interest"), ("BB", r"arbitration"),
    ("CC", r"special taxing district"), ("DD", r"seasonal|vacation rental"),
    ("EE", r"qualifying improvements?|pace"),
)


class FormError(ValueError):
    """A contract form or rider value that can't be used; the message is written for the agent."""


# Text that names an FR/BAR form: "FR/BAR", "FRBAR", the footer's "FloridaRealtors/FloridaBar", or a bare "ASIS-" number.
_FRBAR_TEXT = re.compile(r"\bfr ?/? ?bar\b|florida ?realtors ?/ ?florida ?bar|^asis\b")
FORM_TITLES = {AS_IS: "FR/BAR AS IS Residential Contract for Sale and Purchase",
               STANDARD: "FR/BAR Residential Contract for Sale and Purchase (Standard)"}


def normalize(value):
    """'as_is', 'standard' or 'other' from a data file's contract_form; None when it isn't given.

    Reads the short names, the form titles and the printed footer ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26",
    "FR/BAR Standard Contract"). Text that names an FR/BAR form without saying which one raises FormError instead of
    becoming 'other', which would silently drop the form's rules (ENG-8)."""
    if value in (None, ""):
        return None
    s = " ".join(str(value).lower().replace("_", " ").replace("-", " ").replace("–", " ").split())
    if s in _ALIASES:
        return _ALIASES[s]
    if not _FRBAR_TEXT.search(s):
        return OTHER
    s = re.sub(r"\bas ?is (rider|addendum)\b", " ", s)  # "Standard with the As Is Rider (K)" is the Standard form
    if re.search(r"\bstandard\b", s):
        return STANDARD
    if re.search(r"\bas ?is\b", s):
        return AS_IS
    if re.search(r"residential contract|\b7x?\b", s):  # the Standard form's title and footer ("FloridaBar – 7x")
        return STANDARD
    raise FormError(f"The contract form \"{value}\" names an FR/BAR form but not which one. Read the title: \"AS IS "
                    "Residential Contract for Sale and Purchase\" is as_is, \"Residential Contract for Sale and Purchase\" "
                    "is standard.")


def inspection_days_default(form):
    """The inspection period when the blank is empty: 15 days on both FR/BAR forms (Para. 12(a), and Riders K and L),
    None for another contract (the caller uses the market's norm and records an assumption)."""
    return INSPECTION_DAYS_DEFAULT if form in FRBAR else None


def frbar_market(forms):
    """True when a market's built-in contract rules are the FR/BAR forms' (Florida)."""
    return any(str(f).upper().startswith("FR/BAR") for f in forms or [])


def rider_code(name):
    """The CR-7 letter for one rider as written in a data file ("K", "Rider K", "CR-7 K", "As Is Rider",
    "FHA/VA Financing", "PACE"), or None when it isn't a CR-7 rider (an addendum such as the Appraisal Gap Addendum)."""
    s = " ".join(str(name or "").split())
    m = re.match(r"^(?:CR-?7x?\s+|Rider\s+)?([A-Z]{1,2})(?:[.:)]|\s|$)", s)
    if m and m.group(1) in RIDERS and (len(m.group(1)) == 1 or m.group(1)[0] == m.group(1)[1]):
        return m.group(1)
    low = s.lower().replace("-", " ").replace("\u2019", "'")
    for code, words in _RIDER_WORDS:
        if re.search(rf"\b(?:{words})\b", low):
            return code
    return None


def rider_codes(names):
    """(codes, others): CR-7 letters in the order given without repeats, and the names that aren't CR-7 riders."""
    codes, others = [], []
    for n in names or []:
        c = rider_code(n)
        if c is None:
            others.append(n)
        elif c not in codes:
            codes.append(c)
    return codes, others


def rider_name(code):
    return f"{RIDERS[code]} Rider ({code})"


def terms(form, item=None):
    """What the form and its riders mean for the inspection period and repairs.

    Returns {'walkaway': bool or None, 'repairs_owed': bool, 'riders': [codes], 'inspection_rider': 'K' | 'L' | None,
    'label': "Standard + As Is Rider (K)", 'title': "Standard contract with the As Is Rider (K)"}. walkaway is None only
    for another contract that doesn't say; its label and title are the contract's own name.
    Raises FormError for a rider the form doesn't allow (I, K, L on AS IS) or K and L together."""
    item = item or {}
    codes, _ = rider_codes(item.get("riders"))
    if form == AS_IS:
        bad = [c for c in codes if c in RESERVED_ON_AS_IS]
        if bad:
            raise FormError(f"{', '.join(rider_name(c) for c in bad)}: RESERVED on the FR/BAR AS IS form (Para. 19), which "
                            "already gives the buyer a walk-away inspection period. Check which form was signed and which "
                            "riders are attached.")
        return {"walkaway": True, "repairs_owed": False, "riders": codes, "inspection_rider": None, "label": "AS IS",
                "title": "AS IS contract"}
    if form == STANDARD:
        if "K" in codes and "L" in codes:
            raise FormError("The As Is Rider (K) and the Right to Inspect and Right to Cancel Rider (L) are both attached, "
                            "and each replaces the Standard form's inspection terms differently. Ask which one governs.")
        rider = "K" if "K" in codes else "L" if "L" in codes else None
        return {"walkaway": rider is not None, "repairs_owed": rider != "K", "riders": codes, "inspection_rider": rider,
                "label": f"Standard + {_SHORT[rider]} Rider ({rider})" if rider else "Standard",
                "title": f"Standard contract with the {rider_name(rider)}" if rider else "Standard contract"}
    given = item.get("inspection_walkaway")
    name = item.get("contract_name") or item.get("form") or "Other contract"
    return {"walkaway": None if given is None else given is not False, "repairs_owed": False, "riders": codes,
            "inspection_rider": None, "label": name, "title": name}


def inspection_walkaway(form, item=None):
    """True when the buyer may cancel for any reason during the inspection period (terms()['walkaway']).

    AS IS: yes. Standard: only with Rider K or L. Another contract: the file's `inspection_walkaway`, or None when
    it doesn't say (the caller asks the agent or records an assumption)."""
    return terms(form, item)["walkaway"]


def repair_limits(price, item=None):
    """Standard contract repair limits in dollars. `repair_limits` in the file may give each as dollars (6000)
    or a share of price (0.02); a blank one is the form's 1.5%."""
    given = (item or {}).get("repair_limits") or {}
    out = {}
    for key in REPAIR_LIMIT_KEYS:
        v = given.get(key)
        if v is None:
            v = REPAIR_LIMIT_DEFAULT
        if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
            raise FormError(f"repair_limits.{key} should be dollars (6000) or a share of price (0.015 for 1.5%).")
        if 1 <= v < 100:  # a percent written as 1.5: neither a share of price nor a real dollar limit
            raise FormError(f"repair_limits.{key} is {v:g}: write a share of price as a fraction ({v / 100:g} for {v:g}%) "
                            "or the limit in dollars (6000).")
        out[key] = round(v * price) if v < 1 else round(v)
    return out


def _rev(text):
    """(form version, revision date) from a footer such as "FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26"."""
    s = str(text or "")
    ver = re.search(r"(\d+)x?[\s_]*Rev", s)
    date = re.search(r"Rev\.?\s*(\d{1,2})\s*/\s*(\d{2,4})", s)
    return (ver.group(1) if ver else None,
            (int(date.group(1)), int(date.group(2)) % 100) if date else None)


def revision_note(form, printed):
    """A sentence for the chat reply when the contract's printed revision isn't the one the built-in rules were
    verified against, else None. Never printed on a report: it tells the agent what to double-check."""
    key = _VERIFIED_FOR.get(form)
    if not key or not printed:
        return None
    want_ver, want_date = _rev(VERIFIED[key])
    ver, date = _rev(printed)
    if (ver is None or ver == want_ver) and (date is None or date == want_date):
        return None
    return (f"This contract's footer reads \"{printed}\"; the built-in FR/BAR rules were checked against "
            f"\"{VERIFIED[key]}\". Confirm the deposit, inspection, financing and closing paragraphs against the signed form.")


BEST_EFFORT_NOTE = ("Only Florida FR/BAR contracts are fully supported. This contract was read on a best-effort basis: check "
                    "every date and term against the signed contract, and have a real estate attorney licensed in the "
                    "property's state confirm anything that matters.")


def support(forms, revisions=()):
    """What the skill tells the agent in chat, never on a report: {'support': 'full' | 'best_effort', 'chat_notes': [...]}.

    `forms` are normalized forms ('as_is', 'standard', 'other'; None is ignored). Any 'other' contract makes the run
    best effort and adds BEST_EFFORT_NOTE. `revisions` are (form, printed footer) pairs; a revision that isn't the
    verified one adds its revision_note()."""
    forms = [f for f in forms if f]
    notes = [BEST_EFFORT_NOTE] if OTHER in forms else []
    for form, printed in revisions:
        note = revision_note(form, printed)
        if note and note not in notes:
            notes.append(note)
    return {"support": "best_effort" if OTHER in forms else "full", "chat_notes": notes}


# Appraisal protection on an FR/BAR offer (frbar-riders.md Rider F, frbar-addenda.md AGA-1). AGA-1 is for conventional
# or cash offers and isn't used with Rider F; FHA/VA offers use Rider E, whose protection runs to closing.
AGA_VALUATION_DAYS, AGA_DELIVERY_DAYS, AGA_RENEGOTIATE_DAYS = 30, 3, 3  # AGA-1 blanks: 30 days, then 3 and 3 (3 preprinted)
AGA_FINANCING = ("conventional", "cash")  # AGA-1's own instructions: conventional or cash offers only
RIDER_F_DAYS_BEFORE_CLOSING, RIDER_F_NOTICE_DAYS = 10, 3
_AGA_NAME = re.compile(r"\bAGA(-1)?\b|appraisal gap addendum", re.I)


def aga_named(item=None):
    """True when the Appraisal Gap Addendum (AGA-1) is attached: `appraisal_form: "aga"` or its name in `riders` or
    `addenda`. Whether it fits the loan is aga_fits()."""
    item = item or {}
    names = [str(n) for n in list(item.get("riders") or []) + list(item.get("addenda") or [])]
    return str(item.get("appraisal_form") or "").lower().replace("-", "") in ("aga", "aga1") \
        or any(_AGA_NAME.search(n) for n in names)


def aga_fits(financing):
    """True when AGA-1 can govern this loan type (conventional or cash). On FHA, VA or USDA the gap it states is
    intent only: the callers flag it and never model or recommend it."""
    return financing in AGA_FINANCING


def appraisal_form(form, item=None, financing=None):
    """'aga' (Appraisal Gap Addendum), 'F' (Appraisal Contingency Rider), 'E' (FHA/VA Rider) or None, for an FR/BAR
    offer. AGA-1 counts only where it fits the loan (`financing`, when given: conventional or cash); the riders by
    letter. With AGA-1 on a loan it doesn't fit, the answer is the rider attached, or None (Para. 8(b)(2))."""
    if form not in FRBAR:
        return None
    item = item or {}
    if aga_named(item) and (financing is None or aga_fits(financing)):
        return "aga"
    codes, _ = rider_codes(item.get("riders"))
    return "E" if "E" in codes else "F" if "F" in codes else None


def appraisal_in_loan_approval(form, item=None, financing=None):
    """True when an FR/BAR financed offer has no appraisal rider or addendum (no F, E or AGA-1): Para. 8(b)(2) makes
    the lender's appraisal part of Loan Approval, so the appraisal window is the Loan Approval Period (both forms)."""
    return form in FRBAR and appraisal_form(form, item, financing) is None


# Para. 9(c), check one: who designates the Closing Agent and pays the "Owner's Policy and Charges" (the owner's premium
# and the title search). `title_by` in a data file: "seller" (i), "buyer" (ii), "buyer_regional" (iii, the
# Miami-Dade/Broward regional provision). Verified against ASIS-7x and 7x Rev. 2/26 (ENG-17).
TITLE_SEARCH_CAP_DEFAULT = 200  # 9(c)(iii)(A): the seller's title search, not over $200 if blank
_TITLE_BOX = {"seller": "i", "i": "i", "buyer": "ii", "ii": "ii", "buyer_regional": "iii", "buyer regional": "iii",
              "regional": "iii", "iii": "iii"}


def title_box(form, item=None):
    """'i', 'ii' or 'iii' for the Para. 9(c) box an FR/BAR offer's `title_by` records, else None (not given, or
    another contract)."""
    who = str((item or {}).get("title_by") or "").lower().strip()
    return _TITLE_BOX.get(who) if form in FRBAR else None


def owner_title_payer(form, item=None):
    """Who pays the owner's title policy under the contract, from `title_by` (who designates the Closing Agent), or
    None when the contract doesn't settle it. FR/BAR Para. 9(c): (i) Seller designates and pays the Owner's Policy;
    (ii) and (iii) Buyer designates and pays it (under (iii) the Seller still pays the title search, up to $200 if
    blank). Another contract: None (local custom, or the listing's costs)."""
    box = title_box(form, item)
    return None if box is None else "seller" if box == "i" else "buyer"


def seller_title_searches(form, item=None):
    """What the Para. 9(c) box leaves the seller to pay for searches: {'title_search': True | False | cap in dollars,
    'municipal_lien_search': bool}, or None when no box is recorded (the market's custom applies).

    (i): the seller pays the Owner's Policy and Charges, title search included, and the lien search. (ii): the buyer
    pays both. (iii): the seller pays the title search up to the cap (`title_search_cap`, $200 if blank), the tax
    search and the municipal lien search. Each party pays its own Closing Services (the settlement fee) either way."""
    box = title_box(form, item)
    if box is None:
        return None
    if box == "iii":
        cap = (item or {}).get("title_search_cap")
        return {"title_search": cap if cap is not None else TITLE_SEARCH_CAP_DEFAULT, "municipal_lien_search": True}
    return {"title_search": box == "i", "municipal_lien_search": box == "i"}


def appraisal_window(kind, close_days, item=None, cap=True):
    """Days after the Effective Date until the appraisal protection ends, from the form's defaults and filled blanks.

    AGA-1: valuation (30 days if blank) + 3 days to deliver it + the renegotiation period (3 if blank), never past
    closing unless `cap` is False (the full window, to flag one that runs past closing). Rider F: the appraisal date
    (10 days before closing if blank) + 3 days for the buyer's notice, never less than the notice itself. E: to closing."""
    item = item or {}
    if kind == "aga":
        full = (item.get("aga_valuation_days") or AGA_VALUATION_DAYS) + AGA_DELIVERY_DAYS + \
            (item.get("aga_renegotiate_days") or AGA_RENEGOTIATE_DAYS)
        return min(full, close_days) if cap and close_days else full  # 0 or None: closing not known
    if kind == "F":
        return max(close_days - RIDER_F_DAYS_BEFORE_CLOSING + RIDER_F_NOTICE_DAYS, RIDER_F_NOTICE_DAYS)
    return close_days


def aga_valuation_days(limit_days):
    """The AGA-1 valuation blank that ends the whole AGA-1 window (valuation + 3 + 3) by `limit_days` after the
    Effective Date (the Loan Approval Period, or closing): the form's 30 days when that fits, else fewer, at least 1."""
    return max(1, min(AGA_VALUATION_DAYS, limit_days - AGA_DELIVERY_DAYS - AGA_RENEGOTIATE_DAYS))


# Rider periods, each the rider's own "if left blank" value (frbar-riders.md). The timeline dates them; the offer engine
# counts the ones that let a party cancel toward "days until firm" (rider_windows).
RIDER_DAYS = {"mold_days": 20, "drywall_days": 15, "compensation_agreement_days": 3, "pre_closing_agreement_days": 10,
              "post_closing_agreement_days_before": 10, "short_sale_application_days": 10, "short_sale_approval_days": 90,
              "rofr_days": 5, "lease_agreement_days": 5, "rental_agreements_days": 5, "rental_review_days": 5}
RIDER_NOTICE_DAYS = 3  # Riders V, X and GG: 3 days to give notice after their date
INSURANCE_DAYS_AFTER, INSURANCE_DAYS_BEFORE_CLOSING = 30, 10  # Rider H blank: the earlier of the two


def rider_windows(form, item=None, close_days=None):
    """Cancel windows the CR-7 riders add to an FR/BAR offer, counted from the Effective Date.

    Returns (windows, missing): windows are (code, days, what) for each right to cancel a rider creates (for the buyer,
    or for either party while a required agreement isn't signed); missing are the codes whose window is a date the
    offer doesn't give (Z, R), so the caller records an assumption. Rider Y is the seller's own right, and V, the
    appraisal riders and K/L are counted by their own fields."""
    if form not in FRBAR:
        return [], []
    item = item or {}
    codes, _ = rider_codes(item.get("riders"))
    D = {k: item.get(k) or v for k, v in RIDER_DAYS.items()}
    out, missing = [], []
    if "H" in codes:
        days = item.get("insurance_days") or (max(0, min(INSURANCE_DAYS_AFTER, close_days - INSURANCE_DAYS_BEFORE_CLOSING))
                                              if close_days is not None else INSURANCE_DAYS_AFTER)
        out.append(("H", days, "insurance rider"))
    if "I" in codes and form == STANDARD:
        out.append(("I", D["mold_days"], "mold inspection rider"))
    if "M" in codes and not item.get("drywall_waived"):
        out.append(("M", D["drywall_days"], "drywall rider"))
    if "S" in codes:
        out.append(("S", D["lease_agreement_days"], "lease agreement due"))
    if "T" in codes:
        out.append(("T", D["pre_closing_agreement_days"], "pre-closing occupancy agreement"))
    if "U" in codes and close_days is not None:
        out.append(("U", max(close_days - D["post_closing_agreement_days_before"], 0), "rent-back agreement"))
    if "DD" in codes:
        out.append(("DD", D["rental_agreements_days"] + D["rental_review_days"], "rental management review"))
    if "GG" in codes:
        out.append(("GG", D["compensation_agreement_days"] + RIDER_NOTICE_DAYS, "compensation agreement"))
    for code, field, what in (("Z", "attorney_days", "buyer's attorney approval"), ("R", "rezoning_days", "rezoning")):
        if code in codes:
            if item.get(field):
                out.append((code, item[field], what))
            else:
                missing.append(code)
    return out, missing


def buyer_broker_as_credit(form, item=None):
    """True when the buyer's broker is paid through a seller credit to the buyer (Rider FF), which lenders generally
    count toward the loan program's cap on seller concessions. Rider GG (a separate compensation agreement paid as a
    commission) doesn't use that room."""
    item = item or {}
    return form in FRBAR and ("FF" in rider_codes(item.get("riders"))[0] or str(item.get("buyer_broker_form") or "").upper() == "FF")
