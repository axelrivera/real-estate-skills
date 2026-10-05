"""Which contract rules apply to which form and rider set, in one place.

    from _shared import contract_forms as cf
    form = cf.normalize("AS IS")                 # 'as_is' | 'standard' | 'other' | None (not given)
    t = cf.terms(form, offer)                    # {'walkaway', 'repairs_owed', 'riders', 'label', ...} per form + riders
    cf.inspection_walkaway(form, offer)          # t['walkaway']: True when the buyer may cancel for any reason
    cf.repair_limits(price, offer)               # Standard repairs: {'general', 'wdo', 'permit'} in dollars
    cf.rider_codes(["FHA/VA Financing", "K"])    # (['E', 'K'], []): CR-7 letters, and names that aren't riders
    cf.revision_note(form, "ASIS-8 Rev. 1/27")   # chat note when the contract isn't the verified revision

Fully supported forms are the FAR/BAR AS IS and Standard contracts and their CR-7 riders, verified against the PDFs
listed in dev/forms/farbar-forms.json (make forms-check). Their rules differ in Para. 12 and 9(a), so the math never
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
- Any other contract ('other'): best effort. No FAR/BAR default or figure applies; whether its inspection period is a
  walk-away comes only from the file (`inspection_walkaway`), and callers ask or record an assumption when it's missing.
"""
import re

AS_IS, STANDARD, OTHER = "as_is", "standard", "other"
FARBAR = (AS_IS, STANDARD)
REPAIR_LIMIT_DEFAULT = 0.015  # Para. 9(a): 1.5% of the price for each limit when blank
REPAIR_LIMIT_KEYS = ("general", "wdo", "permit")
INSPECTION_DAYS_DEFAULT = 15  # Para. 12(a) of both forms: 15 days after the Effective Date when blank
STANDARD_REPAIR_WINDOW_DAYS = 15  # after the repair notice: the seller's estimates (10 days), then the election (5 days)
RIDER_INSPECTION_DAYS_DEFAULT = 15  # Rider K 2(a) and Rider L 1: 15 days when blank

# The revisions the built-in rules were checked against: must match dev/forms/farbar-forms.json (make forms-check).
VERIFIED = {"FARBAR-ASIS": "FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26",
            "FARBAR-STANDARD": "FloridaRealtors/FloridaBar – 7x Rev. 2/26"}
_VERIFIED_FOR = {AS_IS: "FARBAR-ASIS", STANDARD: "FARBAR-STANDARD"}

_ALIASES = {  # compared lowercase, with "_" and "-" read as spaces. CRSP-17 is a different form: 'other'.
    "as is": AS_IS, "asis": AS_IS, "asis 7": AS_IS, "asis 7x": AS_IS, "far/bar as is": AS_IS, "farbar as is": AS_IS,
    "as is residential contract for sale and purchase": AS_IS,
    "standard": STANDARD, "far/bar standard": STANDARD, "farbar standard": STANDARD,
    "fr/bar as is": AS_IS, "frbar as is": AS_IS, "fr/bar standard": STANDARD, "frbar standard": STANDARD,  # legacy
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


# Text that names a FAR/BAR form: "FAR/BAR", "FARBAR" (or the legacy name "FR/BAR"), the footer's
# "FloridaRealtors/FloridaBar", or a bare "ASIS-" number.
_FARBAR_TEXT = re.compile(r"\bfa?r ?/? ?bar\b|florida ?realtors ?/ ?florida ?bar|^asis\b")
FORM_TITLES = {AS_IS: "FAR/BAR AS IS Residential Contract for Sale and Purchase",
               STANDARD: "FAR/BAR Residential Contract for Sale and Purchase (Standard)"}


def normalize(value):
    """'as_is', 'standard' or 'other' from a data file's contract_form; None when it isn't given.

    Reads the short names, the form titles and the printed footer ("FloridaRealtors/FloridaBar-ASIS-7x Rev. 2/26",
    "FAR/BAR Standard Contract"). Text that names a FAR/BAR form without saying which one raises FormError instead of
    becoming 'other', which would silently drop the form's rules (ENG-8)."""
    if value in (None, ""):
        return None
    s = " ".join(str(value).lower().replace("_", " ").replace("-", " ").replace("–", " ").split())
    if s in _ALIASES:
        return _ALIASES[s]
    if not _FARBAR_TEXT.search(s):
        return OTHER
    s = re.sub(r"\bas ?is (rider|addendum)\b", " ", s)  # "Standard with the As Is Rider (K)" is the Standard form
    if re.search(r"\bstandard\b", s):
        return STANDARD
    if re.search(r"\bas ?is\b", s):
        return AS_IS
    if re.search(r"residential contract|\b7x?\b", s):  # the Standard form's title and footer ("FloridaBar – 7x")
        return STANDARD
    raise FormError(f"The contract form \"{value}\" names a FAR/BAR form but not which one. Read the title: \"AS IS "
                    "Residential Contract for Sale and Purchase\" is as_is, \"Residential Contract for Sale and Purchase\" "
                    "is standard.")


def inspection_days_default(form):
    """The inspection period when the blank is empty: 15 days on both FAR/BAR forms (Para. 12(a), and Riders K and L),
    None for another contract (the caller uses the market's norm and records an assumption)."""
    return INSPECTION_DAYS_DEFAULT if form in FARBAR else None


def farbar_market(forms):
    """True when a market's built-in contract rules are the FAR/BAR forms' (Florida)."""
    return any(str(f).upper().startswith(("FAR/BAR", "FR/BAR")) for f in forms or [])  # FR/BAR: legacy name


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


def rider_order(names):
    """`names` (rider and addendum names as a package lists them) in the order the forms print them: CR-7 riders by
    letter, the single letters first and then the double ones (B, F, H, GG), then the addenda that aren't CR-7 riders
    (AGA-1, EAC-1) in the order given."""
    def key(item):
        i, name = item
        c = rider_code(name)
        return (0, len(c), c, i) if c else (1, 0, "", i)
    return [n for _, n in sorted(enumerate(names), key=key)]


def rider_name(code):
    return f"{RIDERS[code]} Rider ({code})"


def terms(form, item=None):
    """What the form and its riders mean for the inspection period and repairs.

    Returns {'walkaway': bool or None, 'repairs_owed': bool, 'riders': [codes], 'inspection_rider': 'K' | 'L' | None,
    'label': "Standard + As Is Rider (K)", 'title': "Standard contract with the As Is Rider (K)", 'watch': (issue, fix)
    or None}: `watch` is what the inspection rider leaves open (farbar-riders.md K), for the offer review's flags. walkaway is None only
    for another contract that doesn't say; its label and title are the contract's own name.
    Raises FormError for a rider the form doesn't allow (I, K, L on AS IS) or K and L together."""
    item = item or {}
    codes, _ = rider_codes(item.get("riders"))
    if form == AS_IS:
        bad = [c for c in codes if c in RESERVED_ON_AS_IS]
        if bad:
            raise FormError(f"{', '.join(rider_name(c) for c in bad)}: RESERVED on the FAR/BAR AS IS form (Para. 19), which "
                            "already gives the buyer a walk-away inspection period. Check which form was signed and which "
                            "riders are attached.")
        return {"walkaway": True, "repairs_owed": False, "riders": codes, "inspection_rider": None, "watch": None, "label": "AS IS",
                "title": "AS IS contract"}
    if form == STANDARD:
        if "K" in codes and "L" in codes:
            raise FormError("The As Is Rider (K) and the Right to Inspect and Right to Cancel Rider (L) are both attached, "
                            "and each replaces the Standard form's inspection terms differently. Ask which one governs.")
        rider = "K" if "K" in codes else "L" if "L" in codes else None
        return {"walkaway": rider is not None, "repairs_owed": rider != "K", "riders": codes, "inspection_rider": rider,
                "watch": _K_WATCH if rider == "K" else None,
                "label": f"Standard + {_SHORT[rider]} Rider ({rider})" if rider else "Standard",
                "title": f"Standard contract with the {rider_name(rider)}" if rider else "Standard contract"}
    given = item.get("inspection_walkaway")
    name = item.get("contract_name") or item.get("form") or "Other contract"
    return {"walkaway": None if given is None else given is not False, "repairs_owed": False, "riders": codes,
            "inspection_rider": None, "watch": None, "label": name, "title": name}


# iteration 10 eval 5: what the As Is Rider (K) leaves open on the Standard form (farbar-riders.md K)
_K_WATCH = ("As Is Rider (K): deletes the Para. 9(a) repair, WDO and permit limits and all of Paras. 11 and 12, so the "
            "seller owes no repairs. The Para. 9(a) 125% escrow isn't deleted, and there's no permit cooperation clause "
            "like the AS IS form's Para. 12(c).",
            "Agree in Additional Terms whether the 125% escrow applies to the as-is maintenance duty and whether the "
            "seller helps close open permits.")


def inspection_walkaway(form, item=None):
    """True when the buyer may cancel for any reason during the inspection period (terms()['walkaway']).

    AS IS: yes. Standard: only with Rider K or L. Another contract: the file's `inspection_walkaway`, or None when
    it doesn't say (the caller asks the agent or records an assumption)."""
    return terms(form, item)["walkaway"]


def term_words(form):
    """OFR-234: what an offer's terms are called on this form, for labels and reasons. The FAR/BAR forms' own words
    (Inspection Period, a deposit refundable in it); for any other contract, generic words that fit most forms (a Texas
    TREC contract's option period, an appraisal right in its financing addendum), never Florida's names.

    {'inspection_label', 'inspection', 'deposit_label', 'deposit_refund', 'appraisal_addendum', 'deposit_risk_confirm'};
    appraisal_addendum is None on FAR/BAR (its riders are named by letter: appraisal_form()), and so is
    deposit_risk_confirm (the engine's windows follow the form and riders)."""
    if form in FARBAR:
        return {"inspection_label": "Inspection Period", "inspection": "inspection period", "deposit_label": "Escrow Deposit",
                "deposit_refund": "refundable during inspection", "appraisal_addendum": None, "deposit_risk_confirm": None}
    return {"inspection_label": "Inspection or Option Period", "inspection": "inspection or option period",
            "deposit_label": "Deposit",  # iteration 9 eval 3: "Escrow Deposit" is FAR/BAR's name
            # OFR-316: the engine counts the deposit's risk date from the offer's own periods; on another contract the
            # agent confirms when that form makes the deposit nonrefundable (no other state's rules are built in)
            "deposit_risk_confirm": "counted from this offer's periods: confirm when your contract releases the deposit",
            "deposit_refund": "refundable if the buyer ends the contract within the inspection or option period (per your contract)",
            "appraisal_addendum": "Appraisal Protection (Per Your Contract's Addendum)"}


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


def revision_note(form, printed, from_footer=True):
    """A sentence for the chat reply when the contract's printed revision isn't the one the built-in rules were
    verified against, else None. Never printed on a report: it tells the agent what to double-check.
    `from_footer=False` (TL-201): the revision came from somewhere else (a header, a summary, the agent), so the note
    quotes it as the revision given, never as what the footer reads."""
    key = _VERIFIED_FOR.get(form)
    if not key or not printed:
        return None
    want_ver, want_date = _rev(VERIFIED[key])
    ver, date = _rev(printed)
    if (ver is None or ver == want_ver) and (date is None or date == want_date):
        return None
    said = f"This contract's footer reads \"{printed}\"" if from_footer else f"The revision given for this contract is \"{printed}\""
    return (f"{said}; the built-in FAR/BAR rules were checked against \"{VERIFIED[key]}\". Confirm the deposit, "
            "inspection, financing and closing paragraphs against the signed form.")


BEST_EFFORT_NOTE = ("Only Florida FAR/BAR contracts are fully supported. This contract was read on a best-effort basis: check "
                    "every date and term against the signed contract, and have a real estate attorney licensed in the "
                    "property's state confirm anything that matters.")
# iteration 9 eval 3: an offer described in chat (no form named) wasn't read from a contract, so its line says so
DESCRIBED_NOTE = ("Only Florida FAR/BAR contracts are fully supported. This offer was reviewed on a best-effort basis from "
                  "its description: check every date and term against the signed contract once you have it, and have a "
                  "real estate attorney licensed in the property's state confirm anything that matters.")
# OFR-314: the buyer side writes an offer that isn't signed yet, so its line points at the form being filled in
BEST_EFFORT_OFFER_NOTE = ("Only Florida FAR/BAR contracts are fully supported. This offer was built on a best-effort basis for "
                          "another contract form: check every term and date against that form before the offer goes out, "
                          "and have a real estate attorney licensed in the property's state confirm anything that matters.")


def support(forms, revisions=(), drafting=False):
    """What the skill tells the agent in chat, never on a report: {'support': 'full' | 'best_effort', 'chat_notes': [...]}.

    `forms` are normalized forms ('as_is', 'standard', 'other'; None is ignored). Any 'other' contract makes the run
    best effort and adds BEST_EFFORT_NOTE, or BEST_EFFORT_OFFER_NOTE when `drafting` (an offer still being written, not
    a signed contract). `revisions` are (form, printed footer) pairs, or (form, revision, from_footer) when the caller
    knows whether the revision was read from the footer; a revision that isn't the verified one adds its
    revision_note()."""
    forms = [f for f in forms if f]
    notes = [BEST_EFFORT_OFFER_NOTE if drafting else BEST_EFFORT_NOTE] if OTHER in forms else []
    for form, printed, *source in revisions:
        note = revision_note(form, printed, *source)
        if note and note not in notes:
            notes.append(note)
    return {"support": "best_effort" if OTHER in forms else "full", "chat_notes": notes}


# Appraisal protection on a FAR/BAR offer (farbar-riders.md Rider F, farbar-addenda.md AGA-1). AGA-1 is for conventional
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
    """'aga' (Appraisal Gap Addendum), 'F' (Appraisal Contingency Rider), 'E' (FHA/VA Rider) or None, for a FAR/BAR
    offer. AGA-1 counts only where it fits the loan (`financing`, when given: conventional or cash); the riders by
    letter. With AGA-1 on a loan it doesn't fit, the answer is the rider attached, or None (Para. 8(b)(2))."""
    if form not in FARBAR:
        return None
    item = item or {}
    if aga_named(item) and (financing is None or aga_fits(financing)):
        return "aga"
    codes, _ = rider_codes(item.get("riders"))
    return "E" if "E" in codes else "F" if "F" in codes else None


def appraisal_in_loan_approval(form, item=None, financing=None):
    """True when a FAR/BAR financed offer has no appraisal rider or addendum (no F, E or AGA-1): Para. 8(b)(2) makes
    the lender's appraisal part of Loan Approval, so the appraisal window is the Loan Approval Period (both forms)."""
    return form in FARBAR and appraisal_form(form, item, financing) is None


# Para. 9(c), check one: who designates the Closing Agent and pays the "Owner's Policy and Charges" (the owner's premium
# and the title search). `title_by` in a data file: "seller" (i), "buyer" (ii), "buyer_regional" (iii, the
# Miami-Dade/Broward regional provision). Verified against ASIS-7x and 7x Rev. 2/26 (ENG-17).
TITLE_SEARCH_CAP_DEFAULT = 200  # 9(c)(iii)(A): the seller's title search, not over $200 if blank
_TITLE_BOX = {"seller": "i", "i": "i", "buyer": "ii", "ii": "ii", "buyer_regional": "iii", "buyer regional": "iii",
              "regional": "iii", "iii": "iii"}


def title_box(form, item=None):
    """'i', 'ii' or 'iii' for the Para. 9(c) box a FAR/BAR offer's `title_by` records, else None (not given, or
    another contract)."""
    who = str((item or {}).get("title_by") or "").lower().strip()
    return _TITLE_BOX.get(who) if form in FARBAR else None


def owner_title_payer(form, item=None):
    """Who pays the owner's title policy under the contract, from `title_by` (who designates the Closing Agent), or
    None when the contract doesn't settle it. FAR/BAR Para. 9(c): (i) Seller designates and pays the Owner's Policy;
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


# Rider periods, each the rider's own "if left blank" value (farbar-riders.md). The timeline dates them; the offer engine
# counts the ones that let a party cancel toward "days until firm" (rider_windows).
RIDER_DAYS = {"mold_days": 20, "drywall_days": 15, "compensation_agreement_days": 3, "pre_closing_agreement_days": 10,
              "post_closing_agreement_days_before": 10, "short_sale_application_days": 10, "short_sale_approval_days": 90,
              "rofr_days": 5, "lease_agreement_days": 5, "rental_agreements_days": 5, "rental_review_days": 5}
RIDER_NOTICE_DAYS = 3  # Riders V, X and GG: 3 days to give notice after their date
INSURANCE_DAYS_AFTER, INSURANCE_DAYS_BEFORE_CLOSING = 30, 10  # Rider H blank: the earlier of the two


def rider_windows(form, item=None, close_days=None):
    """Cancel windows the CR-7 riders add to a FAR/BAR offer, counted from the Effective Date.

    Returns (windows, missing): windows are (code, days, what) for each right to cancel a rider creates (for the buyer,
    or for either party while a required agreement isn't signed); missing are the codes whose window is a date the
    offer doesn't give (Z, R), so the caller records an assumption. Rider Y is the seller's own right, and V, the
    appraisal riders and K/L are counted by their own fields."""
    if form not in FARBAR:
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
    if "GG" in codes and compensation_agreement(item) != "received":  # signed by both: the contingency is met
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
    return form in FARBAR and ("FF" in rider_codes(item.get("riders"))[0] or str(item.get("buyer_broker_form") or "").upper() == "FF")


# Rider GG: where the separate compensation agreement stands (an offer's `compensation_agreement`). Left out: it isn't
# in the package. The seller's side signs as the rider's signer box says: the Seller's Broker (the listing broker) or
# the Seller.
COMPENSATION_AGREEMENT = ("received", "signed_by_buyer_broker", "signed_by_listing_broker", "signed_by_seller")
_CA_ALIASES = {"signed_both": "received", "fully_signed": "received", "signed_by_both": "received"}


def compensation_agreement(item=None):
    """The offer's `compensation_agreement`, normalized, or None when it isn't given (or isn't a known status:
    compensation_agreement_problems names that one)."""
    v = (item or {}).get("compensation_agreement")
    if v in (None, ""):
        return None
    s = str(v).strip().lower().replace(" ", "_").replace("-", "_")
    s = _CA_ALIASES.get(s, s)
    return s if s in COMPENSATION_AGREEMENT else None


def compensation_agreement_problems(item=None, listing_pays=False, where="compensation_agreement"):
    """`field: problem → fix` lines for a compensation agreement status that can't be right (the render stops)."""
    item = item or {}
    v = item.get("compensation_agreement")
    if v in (None, ""):
        return []
    status = compensation_agreement(item)
    if status is None:
        return [f"{where}: {v!r} isn't a status → use one of {', '.join(COMPENSATION_AGREEMENT)}, or leave it out when "
                "the agreement isn't in the package"]
    out = []
    if "GG" not in rider_codes(item.get("riders"))[0]:
        out.append(f"{where}: set, but Rider GG isn't in riders → add GG to riders, or leave the status out")
    if status == "signed_by_seller" and listing_pays:
        out.append(f"{where}: 'signed_by_seller', but buyer_broker_paid_by says the listing broker pays → use "
                   "'signed_by_listing_broker', or correct buyer_broker_paid_by")
    if status == "signed_by_listing_broker" and not listing_pays:
        out.append(f"{where}: 'signed_by_listing_broker', but the listing broker isn't the payer → set "
                   "buyer_broker_paid_by: \"listing_broker\", or use 'signed_by_seller'")
    if not listing_pays and item.get("buyer_broker_pct") is None and item.get("buyer_broker_amount") is None:
        out.append(f"{where}: the agreement is in the package but its amount isn't recorded → record buyer_broker_pct "
                   "or buyer_broker_amount from it")
    return out


def compensation_agreement_check(form, item=None, listing_pays=False, amount=None):
    """Rider GG's flag for the offer review: (issue, fix, request or None), or None when there's nothing to do (the
    agreement is in the package, signed by both). `amount` is the agreement's terms as text ("2.5%"), when known.

    Rider GG (farbar-riders.md): the contract is contingent on the compensation agreement being signed and delivered
    within the Time Period (3 days after the Effective Date if blank); if it isn't, the buyer may cancel within the next
    3 days and get the deposit back."""
    item = item or {}
    if form not in FARBAR or "GG" not in rider_codes(item.get("riders"))[0]:
        return None
    status = compensation_agreement(item)
    if status == "received":
        return None
    days = item.get("compensation_agreement_days") or RIDER_DAYS["compensation_agreement_days"]
    ours = "the listing broker" if listing_pays else "the seller"
    terms = (f" ({amount} to the buyer's broker" + (", paid by the listing broker)" if listing_pays else ")")) if amount else ""
    net = "it comes out of the listing fee, so it isn't in the seller's net." if listing_pays else "its amount is in the net."
    window = f"within {days} days after the Effective Date, or the buyer may cancel and get the deposit back"
    if status == "signed_by_buyer_broker":
        return (f"Rider GG: the compensation agreement{terms} is signed by the buyer's broker but not yet by {ours}.",
                f"{ours[0].upper() + ours[1:]} signs and delivers it {window}; {net}", None)
    if status in ("signed_by_listing_broker", "signed_by_seller"):
        return (f"Rider GG: the compensation agreement{terms} is signed by {ours} but not yet by the buyer's broker.",
                f"Ask the buyer's agent to have the buyer's broker sign and deliver it {window}; {net}",
                "Please have your broker sign and deliver the compensation agreement.")
    if listing_pays:  # not in the package: the listing side's own paperwork, nothing to ask the buyer's agent
        return ("Rider GG: the buyer's broker compensation is in a separate compensation agreement that isn't in the "
                "package.", f"The listing broker signs and delivers it {window}; {net}", None)
    return ("Rider GG: the buyer's broker compensation amount is in a separate compensation agreement, not the rider.",
            f"Get the signed agreement (due {days} days after the Effective Date if blank) and put its amount in the net.",
            "Please send the compensation agreement for the seller's review.")


# Addenda that print a box for the contract they go with (farbar-addenda.md: EAC-1 checks AS IS FAR/BAR, FAR/BAR,
# CRSP, Commercial or Vacant Land), and the plain names the seller reads.
_FORM_PLAIN = {AS_IS: "AS IS contract", STANDARD: "Standard contract"}


def addendum_form_conflict(form, named, addendum="Escalation Addendum"):
    """(issue, fix, request) when an addendum's contract box names another form than the offer's FAR/BAR contract, else
    None. `named` is the box as read (anything normalize() reads; another form's name stays as written). Raises
    FormError for text that names a FAR/BAR form without saying which."""
    if form not in FARBAR or named in (None, ""):
        return None
    other = normalize(named)
    if other == form:
        return None
    theirs = _FORM_PLAIN.get(other) or f"\"{named}\""
    return (f"The {addendum} has the box checked for the {theirs}, but the offer is on the {_FORM_PLAIN[form]}.",
            f"Have the buyer's agent correct the box to the {_FORM_PLAIN[form]} and have the buyer initial the change "
            "before the seller signs.",
            f"Please correct the {addendum} to check the {_FORM_PLAIN[form]} box, initialed by the buyer.")
