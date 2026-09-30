"""Compute every contract deadline from a deal file.

    python3 scripts/timeline.py deal.json [--side buyer|seller]

Prints JSON with every date already formatted (for the markdown template and the PDF), or
{"ok": false, "problems": [...]} when something needed is missing. See references/deal-file.md.

Time rules (day counting, any short-period rule, end of day, weekend/holiday rollover) come from the
market's `contract` section (built in for Florida), overridden by the deal file's `rules`.
FR/BAR contracts get their deadline list from the contract fields; any other contract lists its
deadlines explicitly in `deadlines`.
"""
import argparse
import copy
import json
import os
import re
import sys
from datetime import date, datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import contract_forms as cf, dates, profiles  # noqa: E402

RULE_KEYS = dates.RULE_KEYS
RULE_DEFAULTS = {"rollover_time": "17:00", "closing_time": "10:00"}
# TL-121: the reading used for a time rule the contract doesn't state, until the agent answers (never a borrowed rule)
UNKNOWN_RULES = {"short_period_days": 0, "end_time": "23:59", "weekend_holiday_rollover": "none",
                 "before_closing_rollover": "none", "holidays": "us_federal"}
UNKNOWN_TEXT = {"short_period_days": "whether short periods skip weekends and holidays (counted as calendar days)",
                "end_time": "when a day ends (dates show no time of day)",
                "weekend_holiday_rollover": "whether a deadline on a weekend or holiday moves (not moved)",
                "before_closing_rollover": "whether a date counted back from closing moves off a weekend or holiday "
                                           "(not moved)",
                "holidays": "which holidays count (the federal list used)"}
FINANCING = {"cash": "Cash", "conventional": "Conventional", "fha": "FHA", "va": "VA", "usda": "USDA"}


class DealError(ValueError):
    """Something the deal file needs; the message is written for the agent."""


# --- parsing -----------------------------------------------------------------

def _d(v):
    if v in (None, "") or isinstance(v, date):
        return v or None
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def _t(v):
    h, m = map(int, str(v).split(":")[:2])
    return time(h, m)


def _dt(v, default_time):
    s = str(v)
    return datetime.strptime(s[:16], "%Y-%m-%d %H:%M") if len(s) >= 16 else datetime.combine(_d(s), default_time)


def _plural(n, word):
    return f"{n} {word}{'' if n == 1 else 's'}"


# --- rules --------------------------------------------------------------------

def _form_covered(market_contract, deal, frbar):
    """True when the market's rules are for this deal's form. A market that names its `forms` (Florida:
    the FR/BAR forms) doesn't cover another contract, such as a builder's or a commercial form."""
    forms = [str(f).lower() for f in market_contract.get("forms") or []]
    if not forms:
        return True
    if frbar:
        return any(f.startswith("fr/bar") for f in forms)
    form = str((deal.get("contract") or {}).get("form") or "").strip().lower()
    return bool(form) and form in forms


def load_rules(deal, frbar=True):
    """Built-in `contract` rules for the deal's state/county, then the deal file's `rules`."""
    if not deal.get("state"):
        raise DealError("The deal file needs the property's state (for example FL): time rules and holidays "
                        "depend on it. Ask the agent; don't assume Florida.")
    market = profiles.load_market(state=deal.get("state"), county=deal.get("county"))
    mc = market.get("contract") or {}
    given = {**(mc if _form_covered(mc, deal, frbar) else {}), **(deal.get("rules") or {})}
    given = {k: v for k, v in given.items() if v not in (None, "")}
    rules = {**RULE_DEFAULTS, **given}
    if "day_count" not in given:
        raise DealError("The contract's time rules are missing day_count. Read how the contract counts days (calendar "
                        "or business days) from its definitions, or ask the agent, and add it to the deal file's rules.")
    # TL-121: every other rule the contract doesn't state is asked, never invented. The dates are computed on the
    # neutral reading (nothing skipped or moved, federal holidays, no time of day) and an agent note lists the questions.
    # TL-243: counting business days already skips weekends and holidays, so a short-period rule isn't asked then
    rules["_unknown"] = [k for k in RULE_KEYS if k not in given
                         and not (k == "short_period_days" and given["day_count"] == "business")]
    rules = {**rules, **{k: v for k, v in UNKNOWN_RULES.items() if k in rules["_unknown"]}}
    rules.setdefault("short_period_days", 0)
    rules["_no_end_time"] = "end_time" in rules["_unknown"]  # TL-123: dates show no time of day
    if "before_closing_time" not in given:  # dates counted back from closing end when the contract's days end
        rules["before_closing_time"] = rules["end_time"]
    hol = rules["holidays"]
    try:  # us_federal; a list of the contract's dates on top of the federal holidays; or {"base": "none", "dates": [...]}
        # when the contract defines its own full holiday list
        if isinstance(hol, dict):
            extra = dates.Holidays({_d(x): CONTRACT_HOLIDAY for x in hol.get("dates") or []}, base=hol.get("base", "us_federal"))
        elif isinstance(hol, list):
            extra = dates.Holidays({_d(x): CONTRACT_HOLIDAY for x in hol})
        else:
            extra = dates.Holidays(base=hol)
    except ValueError as e:
        raise DealError(str(e)) from None
    rules["_extra_holidays"] = extra
    rules["_tz"], rules["_tz_note"] = time_zone(deal, rules)
    return rules, market


CONTRACT_HOLIDAY = "a holiday the contract lists"  # TL-114: reads as "falls on a holiday the contract lists (Thu Nov 26)"


def time_zone(deal, rules):
    """(zone, note): the deal's `time_zone`, else the market's for the county (TL-19). Times print with the zone when it
    isn't the market's usual one ("5:00 PM CT" in the western Panhandle)."""
    if deal.get("time_zone"):
        return deal["time_zone"], None
    county = str(deal.get("county") or "").lower().removesuffix(" county")
    for zone, names in (rules.get("time_zone_counties") or {}).items():
        if county and county in {str(n).lower() for n in names}:
            if zone == "ask":
                return None, (f"{deal.get('county')} County spans two time zones: confirm the property's (set time_zone "
                              "in the deal file) before relying on a time of day.")
            return zone, None
    return rules.get("time_zone"), None


# --- period math --------------------------------------------------------------

def forward(start, days, rules, business=False, end_time=None, rollover=None):
    """Deadline `days` after `start`. Returns (datetime, note).

    `end_time` and `rollover` are per-deadline exceptions to the contract's rules: `False` never extends (a period the
    contract says ends at a set time on its last day, whatever the day), `True` extends past a weekend or holiday even
    when the contract's general rule doesn't (a contract that extends only one date); None follows the rules."""
    extra = rules["_extra_holidays"]
    notes = []
    short = int(rules["short_period_days"])
    if business or rules["day_count"] == "business" or (short > 0 and days <= short):
        d = dates.add_business_days(start, days, extra)
        if not business and rules["day_count"] != "business":
            notes.append(f"{days} days or less: weekends and holidays skipped")
        else:
            notes.append("business days")
    else:
        d = start + timedelta(days=days)
    rolls = rollover if rollover is not None else rules["weekend_holiday_rollover"] == "next_business_day"
    if rolls and not dates.is_business_day(d, extra):
        nd = dates.next_business_day(d, extra)
        rt = _t(rules["rollover_time"])
        notes.append(f"ends on {_on(d, nd, extra)}: extended to {_clock(rt)} {nd:%a %b %-d}")
        return datetime.combine(nd, rt), "; ".join(notes)
    return datetime.combine(d, _t(end_time or rules["end_time"])), "; ".join(notes)


def backward(closing, days, rules, business=False, at=None, rollover=None):
    """Deadline `days` before closing, at the contract's before-closing time or `at` (a time of day). `rollover=False`
    keeps a date that falls on a weekend or holiday where it is (a deadline the contract never moves)."""
    extra = rules["_extra_holidays"]
    t = at or _t(rules["before_closing_time"])
    if business == "trid":  # TL-17: Reg Z business days (Saturdays count; Sundays and federal holidays don't)
        return datetime.combine(dates.add_trid_days(closing, -days), t), "TRID business days (Saturdays count)"
    if business:
        return datetime.combine(dates.add_business_days(closing, -days, extra), t), "business days (weekends and holidays skipped)"
    d = closing - timedelta(days=days)
    if rollover is False:
        return datetime.combine(d, t), ""
    if not dates.is_business_day(d, extra) and rules["before_closing_rollover"] == "previous_business_day":
        nd = dates.previous_business_day(d, extra)
        return datetime.combine(nd, t), f"falls on {_on(d, nd, extra)}: moved earlier to {nd:%a %b %-d} (conservative)"
    if not dates.is_business_day(d, extra) and rules["before_closing_rollover"] == "next_business_day":
        nd = dates.next_business_day(d, extra)
        return datetime.combine(nd, t), f"falls on {_on(d, nd, extra)}: extended to {nd:%a %b %-d}"
    return datetime.combine(d, t), ""


def _on(d, nd, extra, dated=True):
    """What a date that isn't a business day falls on, naming every holiday the move to `nd` passes:
    "a Saturday (Mon Oct 12 is Columbus Day)", "Thanksgiving Day (Thu Nov 26)". `dated=False` leaves out the date
    when the sentence already gives it."""
    name = dates.holiday_name(d, extra)
    text = (f"{name} ({d:%a %b %-d})" if dated else name) if name else f"a {d:%A}"
    if nd == d:
        return text
    step = timedelta(days=1 if nd > d else -1)
    passed, x = [], d + step
    while x != nd:
        if dates.holiday_name(x, extra):
            passed.append(f"{x:%a %b %-d} is {dates.holiday_name(x, extra)}")
        x += step
    return text + (f" ({'; '.join(passed)})" if passed else "")


def _clock(t):
    return "the end of" if t == time(23, 59) else f"{t:%-I:%M %p}"


# --- FR/BAR deadline list ----------------------------------------------------

def _loan_type(c):
    """'FHA' or 'VA' from the financing; 'FHA/VA' when the rider is attached but the loan type isn't recorded."""
    return {"fha": "FHA", "va": "VA"}.get(c.get("financing"), "FHA/VA")


INSURANCE_COVERAGE = ("homeowners", "flood", "both")


def insurance_coverage(c):
    """TL-239: which Rider H boxes are checked: "homeowners" ((a) only), "flood" ((b) only), "both", or None when not
    recorded. `insurance_coverage` wins; the older `insurance_flood` / `flood_insurance_date` / `insurance_homeowners`
    fields still read the same way."""
    given = c.get("insurance_coverage")
    if given not in (None, ""):
        v = re.sub(r"[^a-z]", "", str(given).lower())  # "Homeowner's" -> "homeowners"
        v = "homeowners" if v == "homeowner" else v
        if v not in INSURANCE_COVERAGE:
            raise DealError(f"contract.insurance_coverage is {given!r}: use \"homeowners\" (box (a) only), \"flood\" "
                            "(box (b) only) or \"both\" (Rider H).")
        return v
    if c.get("insurance_flood") or c.get("flood_insurance_date"):
        return "flood" if c.get("insurance_homeowners") is False else "both"
    if c.get("insurance_homeowners") is True or c.get("insurance_flood") is False:
        return "homeowners"
    return None


def _unset(c, *fields):
    """TL-257: how a default note names a term the deal file doesn't give: "blank" only when the contract was seen with
    it blank (`blanks` lists the field), else "not given" (a partial copy or text extract may just leave it out)."""
    return "blank" if any(f in (c.get("blanks") or []) for f in fields) else "not given"


def _blank_default(c, field, text, topic):
    """TL-229: `default` and `default_topic` for a row whose period is blank in the deal file, so the script's agent note
    says which form default it used; {} when the contract gives the days. "{blank}" in `text` reads "blank" or "not
    given" (TL-257)."""
    return {} if c.get(field) is not None else {"default": text.replace("{blank}", _unset(c, field)), "default_topic": topic}


def frbar_deadlines(c):
    """Deadlines for an FR/BAR AS IS or Standard contract, from its fields (blank = form default).

    Checked against ASIS-7x Rev. 2/26 and its riders (see docs/audits/2026-09-23-verification.md). A row may
    carry `default` (a form default used for a blank, for agent_notes), `cap_at_closing` (a right that ends at
    closing) or `from_key` (counted from another row's date instead of the Effective Date).
    """
    financed = c.get("financing", "conventional") != "cash"
    t = cf.terms(c["contract_form"], c)  # set by analyze(); never defaulted, so AS IS and Standard rows never mix
    codes = t["riders"]
    has = lambda code: code in codes  # noqa: E731  CR-7 letters from contract_forms, never substrings of names
    fha_va = has("E")
    # ENG-11: the inspection rows follow what the form and riders mean (contract_forms), never the form's name. The rider
    # letter is read only to cite it (Standard + Rider K or L).
    walkaway, repairs_owed, rider = t["walkaway"], t["repairs_owed"], t["inspection_rider"]
    cite = lambda para: f"{cf.rider_name(rider)}, {para}" if rider else None  # noqa: E731
    unit = bool(c.get("condo") or has("A"))  # a condo unit: the building is the association's
    insp_default = _blank_default(c, "inspection_days", (
        f"{cf.rider_name(rider)} period {{blank}}: used the rider default, 15 days after the Effective Date" if rider else
        "Inspection Period {blank} (Para. 12(a)): used the form default, 15 days after the Effective Date"), "inspection")
    out = []

    def add(**k):
        k.setdefault("contingency", False)
        out.append(k)

    amount = c.get("deposit_amount_str") or (  # TL-236: the words as written, else the number
        f"${c['deposit_amount']:,.0f}" if isinstance(c.get("deposit_amount"), (int, float)) else None)
    add(key="deposit", label="Initial Escrow Deposit Due", short="Deposit", basis="after", days=c.get("deposit_days", 3),
        source="Para. 2(a)", party="Buyer", critical=True,
        action=f"Deliver {amount or 'the initial deposit'} to {c.get('escrow_agent') or 'the escrow agent'}; get a receipt",
        if_missed="Buyer in default; seller may cancel",
        **_blank_default(c, "deposit_days", "Initial deposit days {blank} (Para. 2(a)): used the form default, 3 days after "
                         "the Effective Date", "deposit"))
    add_amount = c.get("additional_deposit_amount_str") or (  # the words as written, else the number
        f"${c['additional_deposit_amount']:,.0f}" if isinstance(c.get("additional_deposit_amount"), (int, float)) else None)
    if add_amount or c.get("additional_deposit_amount") or c.get("additional_deposit_days"):
        add(key="add_deposit", label="Additional Deposit Due", short="Additional Deposit", basis="after",
            days=c.get("additional_deposit_days", 10), source="Para. 2(b)", party="Buyer", critical=True,
            **_blank_default(c, "additional_deposit_days", "Additional deposit days {blank} (Para. 2(b)): used the form "
                             "default, 10 days after the Effective Date", "additional deposit"),
            action=f"Deliver the additional deposit ({add_amount})" if add_amount else "Deliver the additional deposit",
            if_missed="Buyer in default; seller may cancel")
    if financed:
        add(key="loan_app", label="Loan Application", short="Loan App", basis="after", days=c.get("loan_application_days", 5),
            source="Para. 8(b)", party="Buyer", critical=False,
            **_blank_default(c, "loan_application_days", "Loan application days {blank} (Para. 8(b)): used the form "
                             "default, 5 days after the Effective Date", "loan application"),
            action="Apply for the loan and provide the lender's written confirmation if requested",
            if_missed="Buyer may lose financing protections")
    if c.get("seller_has_title_evidence"):  # TL-116: Para. 9(c) of both forms
        add(key="seller_title", label="Seller Delivers Existing Title Policy", short="Seller's Title Policy", basis="after",
            days=5, source="Para. 9(c)", party="Seller", critical=False,
            action="Seller gives a copy of the existing owner's title policy or other evidence of title to the buyer and the "
                   "closing agent", if_missed="Title work may take longer")
    if c.get("seller_has_survey"):
        add(key="seller_survey", label="Seller Delivers Existing Survey", short="Seller's Survey", basis="after", days=5,
            source="Para. 9(d)", party="Seller", critical=False,
            action="Seller gives a copy of the existing survey to the buyer and the closing agent",
            if_missed="Buyer may need a new survey sooner")
    if walkaway and not repairs_owed:
        # AS IS, or Standard + Rider K (which deletes Paras. 9(a) limits, 11 and 12): a walk-away, 15 days if blank.
        add(key="inspection", label="Inspection Period Ends (Right to Cancel)", short="Inspection Ends",
            basis="after", days=c.get("inspection_days", 15), **insp_default, source=cite("Para. 2") or "Para. 12(a)",
            party="Buyer", critical=True, contingency=True,
            action=("Complete inspections of the unit (the insurer may ask for a 4-point on the unit); deliver written "
                    "cancellation notice before the deadline if not proceeding" if unit else
                    "Complete inspections (including 4-point and wind mitigation); deliver written cancellation notice "
                    "before the deadline if not proceeding"),
            if_missed="Right to cancel for inspection ends; deposit at risk")
    else:
        # Standard: no right to cancel for inspection. The period is the deadline for the repair, WDO and permit
        # notices; the seller's repair obligation is capped by the repair limits in Para. 9(a) (1.5% each if blank).
        # Rider L replaces it with a Right To Inspect Period (15 days if blank) that adds a walk-away and keeps repairs.
        if walkaway:  # Standard + Rider L: a walk-away that keeps the repair obligation
            add(key="inspection", label="Right to Inspect Period Ends (Cancel or Repair Notices)", short="Inspection Ends",
                basis="after", days=c.get("inspection_days", 15), **insp_default, source=cite("Para. 1"),
                party="Buyer", critical=True, contingency=True,
                action="Deliver written cancellation notice if not proceeding; otherwise deliver written notice of General "
                       "Repair Items, the WDO report and open or unpermitted work to keep the seller's repair obligation",
                if_missed="Right to cancel ends; the seller owes no repairs for items not inspected and reported")
        else:
            add(key="inspection", label="Inspection Period Ends (Repair Notices Due)", short="Repair Notices",
                basis="after", days=c.get("inspection_days", 15), **insp_default, source="Para. 12(a)-(d)", party="Buyer", critical=True,
                action="Deliver written notice of General Repair Items, the WDO report if it found anything, and any open or "
                       "unpermitted work to the seller",
                if_missed="Buyer waives the seller's obligation to repair, treat or permit anything not reported")
        add(key="repair_estimates", label="Seller's Repair Estimates Due", short="Repair Estimates", basis="event",
            received=c.get("repair_notice_delivered"), what="the buyer's repair notice", days=10,
            source="Para. 12(b)(iii), (c)(ii), (d)(ii)", party="Seller", critical=True,
            action="Seller makes the repairs, or delivers licensed estimates or a second inspection report",
            if_missed="Seller is in breach of the repair provisions")
        add(key="repair_election", label="Repair Limit Election", short="Repair Election", basis="event",
            received=c.get("repair_estimates_received"), what="the last repair estimate", days=5,
            source="Para. 12(b)(iii), (c)(ii), (d)(ii)", party="Both", critical=True,
            action="When repairs exceed a repair limit: for general repairs and permits the seller may pay the excess, or "
                   "the buyer designates repairs up to the limit and takes the rest as is; for WDO repairs only the buyer's "
                   "notice counts (pay the excess, or designate repairs up to the WDO limit)",
            if_missed="Either party may terminate and the deposit is refunded (for WDO repairs, when the buyer sends no "
                      "notice)")
        if c.get("open_permits"):
            add(key="permits_closed", label="Open Permits Closed", short="Permits Closed", basis="before", days=5,
                source="Para. 12(d)(ii)", party="Seller", critical=True,
                action="Seller closes the open or expired permits the buyer reported, up to the Permit Limit",
                if_missed="Closing may extend up to 10 days for final inspections, then either party may terminate")
    # Rider F: the appraisal is due by the date written in the rider (at least 10 days before Closing if blank), and a
    # low appraisal must be sent with the buyer's notice within 3 days after that date. The FHA/VA rider has no period:
    # its protection runs to closing, so it's a standing note (analyze), not a dated row.
    if has("F") or ((c.get("appraisal_date") or c.get("appraisal_days")) and not fha_va):
        due = dict(key="appraisal_due", label="Appraisal Due", short="Appraisal Due", source="Appraisal Contingency Rider (F)",
                   party="Buyer", critical=False, action="Buyer has the written appraisal in hand, at the buyer's expense",
                   if_missed="The appraisal contingency is waived; the buyer continues")
        if c.get("appraisal_date"):
            add(**due, basis="date", date=c["appraisal_date"], date_rule="Date written in the rider")
        elif c.get("appraisal_days"):
            add(**due, basis="after", days=c["appraisal_days"])
        else:
            add(**due, basis="before", days=10, default_topic="appraisal date",
                default=f"Appraisal date {_unset(c, 'appraisal_date', 'appraisal_days')}: used the rider default, "
                        "10 days before Closing")
        add(key="appraisal", label="Low-Appraisal Notice Due", short="Low-Appraisal Notice", basis="after", from_key="appraisal_due",
            days=3, source="Appraisal Contingency Rider (F)", party="Buyer", critical=True, contingency=True,
            action="If the value is below the rider's amount, deliver a copy of the appraisal with written notice to cancel "
                   "or to waive the contingency",
            if_missed="The appraisal contingency is waived and removed")
    if financed:
        add(key="loan_approval", label="Loan Approval Period Ends", short="Loan Approval", basis="after",
            days=c.get("loan_approval_days", 30), source="Para. 8(b)", party="Buyer", critical=True, contingency=True,
            **_blank_default(c, "loan_approval_days", "Loan Approval Period {blank} (Para. 8(b)): used the form default, "
                             "30 days after the Effective Date", "loan approval"),
            action="Deliver written loan approval, or written notice to cancel or proceed, before the deadline",
            if_missed="Buyer's right to cancel for financing ends; deposit at risk")
        add(key="seller_terminate", label="Seller's Right to Terminate (No Loan Notice)", short="Seller May Terminate",
            basis="after", from_key="loan_approval", days=3, source="Para. 8(b)(v)", party="Seller", critical=False,
            action="If the buyer sent no loan approval or loan notice by the Loan Approval deadline, the seller may terminate "
                   "in writing within 3 days after it",
            if_missed="Seller's right ends; the buyer proceeds without the financing contingency")
    # Rider V: a date blank (no day default) for the buyer's sale to close, then 3 days for the buyer to cancel.
    if c.get("sale_contingency_date") or has("V"):
        sale = dict(key="buyer_sale_closes", label="Buyer's Sale Must Close", short="Buyer's Sale", party="Buyer",
                    source="Sale of Buyer's Property Rider (V)", critical=False,
                    action="The buyer's other property must close by this date", if_missed="The buyer's 3-day cancel window opens")
        add(**sale, basis="date", date=c.get("sale_contingency_date"), date_rule="Date written in the rider",
            blank_note="the rider's sale date is blank and has no default")
        add(key="sale_contingency", label="Sale Contingency Ends (Last Day to Cancel)", short="Sale Contingency",
            basis="after", from_key="buyer_sale_closes", days=3, source="Sale of Buyer's Property Rider (V)", party="Buyer",
            critical=True, contingency=True,
            action="If the buyer's sale hasn't closed, deliver written notice to cancel; the deposit is refunded",
            if_missed="The sale contingency ends; the buyer must close without the sale and the deposit is at risk")
    # TL-242: Rider P itself grants the 10-day opportunity unless the buyer waived it, whether or not year_built is recorded
    if not c.get("lbp_waived") and (c.get("lead_paint_days") or has("P")
                                    or (c.get("year_built") and int(c["year_built"]) < 1978)):
        add(key="lead_paint", label="Lead-Based Paint Risk Assessment Ends", short="Lead Paint", basis="after",
            days=c.get("lead_paint_days", 10), source="Lead-Based Paint rider", party="Buyer", critical=True, contingency=True,
            action="Complete any risk assessment and deliver notice if canceling", if_missed="Assessment and cancellation right ends")
    if c.get("flood_elevation_days") or re.match(r"^\s*[AV]", str(c.get("flood_zone") or ""), re.I):
        add(key="flood_elevation", label="Flood Elevation Cancellation Ends", short="Flood Elevation", basis="after",
            days=c.get("flood_elevation_days", 20), source="Para. 10(d)", party="Buyer", critical=True, contingency=True,
            action="Get the elevation certificate; if the home is below minimum flood elevation or can't get flood insurance, "
                   "deliver written cancellation notice", if_missed="Buyer accepts the existing elevation and flood zone")
    # Rider H: (a) homeowner's and (b) flood insurance each have their own date (TL-116): the date written in the rider,
    # else the earlier of 30 days after the Effective Date or 10 days before Closing. TL-239: `insurance_coverage` says
    # which boxes are checked (homeowners, flood or both), one row per box; one generic row while it isn't recorded.
    # TL-258: the rider's blank is a date; days written in instead are `insurance_days` (after the Effective Date, the
    # reading used unless the agent confirms otherwise) or `insurance_days_before` (before Closing)
    coverage = insurance_coverage(c)
    if c.get("insurance_date") or c.get("insurance_days") or c.get("insurance_days_before") or coverage or has("H"):
        boxes = []
        if coverage in (None, "homeowners", "both"):
            boxes.append(("insurance", "insurance_date", "Homeowner's Insurance" if coverage else "Insurance",
                          "Para. (a)" if coverage else "", "homeowner's coverage (including windstorm)" if coverage else
                          "coverage the rider names (homeowner's, flood, or both as checked)"))
        if coverage in ("flood", "both"):
            boxes.append(("flood_insurance", "flood_insurance_date", "Flood Insurance", "Para. (b)",
                          "flood coverage (NFIP or private)"))
        for key, field, what, para, cover in boxes:
            ins = dict(key=key, label=f"{what} Contingency Ends", short=f"{what} Ends" if coverage else "Insurance Ends",
                       source="Homeowner's/Flood Insurance Rider (H)" + (f", {para}" if para else ""), party="Buyer",
                       critical=True, contingency=True,
                       action=f"If the {cover} isn't available within any premium cap written in the rider, deliver "
                              "written notice to cancel",
                       if_missed="The insurance cancel right ends")
            # with (b) alone, the one date the rider has may be recorded in the (a) fields
            only = coverage == "flood"
            if c.get(field) or (only and c.get("insurance_date")):
                add(**ins, basis="date", date=c.get(field) or c["insurance_date"], date_rule="Date written in the rider")
            elif (key == "insurance" or only) and c.get("insurance_days"):
                add(**ins, basis="after", days=c["insurance_days"])
            elif (key == "insurance" or only) and c.get("insurance_days_before"):
                add(**ins, basis="before", days=c["insurance_days_before"])
            else:
                add(**ins, basis="earliest", of=[{"basis": "after", "days": 30}, {"basis": "before", "days": 10}],
                    default=f"{what} date {_unset(c, field)}: used the rider default, the earlier of 30 days after the "
                            "Effective Date or 10 days before Closing", default_topic=f"{what.lower()} date")
    # Rider E (TL-120): the buyer's election to go ahead despite a low appraisal is due 3 days after receiving the
    # appraisal (Para. 5). Appraisal repairs over the seller's cap start a 3-day seller election, then 3 days for the
    # buyer's (Para. 3(b) or 4(b)); those rows appear once the overage notice is recorded.
    if c.get("financing") in ("fha", "va") or fha_va:
        loan = _loan_type(c)  # TL-233: "VA" on a VA deal, never "FHA/VA"
        add(key="fha_va_election", label=f"{loan} Low-Appraisal Election to Proceed", short=f"{loan} Election",
            basis="event", received=c.get("appraisal_received"), what="the appraisal", days=3,
            source="FHA/VA Rider (E), Para. 5", party="Buyer", critical=False,
            action="If the appraised value is below the price and the buyer wants to go ahead anyway, deliver the written "
                   "election to proceed",
            if_missed="The rider doesn't say; the buyer's low-appraisal protection runs to closing")
        if c.get("appraisal_repairs_notice_received"):
            add(key="fha_va_repair_seller", label="Seller's Appraisal Repair Election", short="Seller's Repair Election",
                basis="event", received=c["appraisal_repairs_notice_received"],
                what="the notice that appraisal repairs exceed the cap", days=3,
                source="FHA/VA Rider (E), Para. 3(b) or 4(b)", party="Seller", critical=False,
                action="Seller gives written notice of paying all, some or none of the appraisal repairs over the cap",
                if_missed="The rider doesn't say; confirm the next step with your agent")
            add(key="fha_va_repair_buyer", label="Buyer's Appraisal Repair Election", short="Buyer's Repair Election",
                basis="event", received=c.get("seller_repair_election_received"), what="the seller's repair election",
                days=3, source="FHA/VA Rider (E), Para. 3(b) or 4(b)", party="Buyer", critical=True,
                action="If the seller pays less than all of the excess, elect in writing to pay the balance or cancel",
                if_missed="The buyer's right to cancel over the repairs likely ends (the rider doesn't say)")
    rider_rows(c, has, add)
    # Association document rights are the buyer's, run from receipt, and end at closing (CR-7x A, CR-7 B).
    if (c.get("hoa") or has("B")) and not c.get("hoa_disclosure_before_contract"):
        add(key="hoa_docs", label="HOA Disclosure Cancellation Window", short="HOA Disclosure", basis="event",
            received=c.get("hoa_docs_received"), what="the HOA disclosure summary", days=3, cap_at_closing=True, source="HOA rider; s. 720.401 F.S.",
            party="Buyer", critical=True, contingency=True,
            action="The HOA disclosure summary came after signing: the buyer may cancel in writing within 3 days after receiving it",
            if_missed="Cancellation right under s. 720.401 ends")
    if (c.get("condo") or has("A")) and not c.get("condo_docs_before_contract"):
        developer = bool(c.get("developer_sale"))
        add(key="condo_docs", label="Condo Documents Cancellation Window", short="Condo Docs", basis="event",
            received=c.get("condo_docs_received"), what="the condo documents", start_after_effective=True, days=15 if developer else 7,
            business=not developer, cap_at_closing=True,
            source="Condominium rider; s. 718.503 F.S." + (" (developer)" if developer else ""), party="Buyer",
            critical=True, contingency=True,
            action=("The buyer may cancel in writing within 15 days after signing and receiving the developer's documents"
                    if developer else
                    "The buyer may cancel in writing within 7 business days after signing and receiving the condo documents "
                    "(declaration, bylaws, rules, budget, financials, FAQ, and the milestone inspection summary and SIRS)"),
            if_missed="Cancellation right under s. 718.503 ends")
    if c.get("association_approval"):
        add(key="assoc_apply", label="Seller Starts Association Approval", short="Approval Applied", basis="after",
            days=c.get("association_apply_days", 5), source="Condominium / HOA rider", party="Seller", critical=False,
            action="Seller starts the association's approval process; the buyer applies and attends any interview",
            if_missed="Approval may not come in time")
        add(key="assoc_approval", label="Association Approval Deadline", short="Association Approval", basis="before",
            days=c.get("association_approval_days_before", 5), source="Condominium / HOA rider", party="Buyer",
            critical=True, contingency=True, action="Written association approval in hand",
            # TL-232: Rider A Para. 1 ends the contract automatically; Rider B Part B Para. 1 lets the buyer terminate
            if_missed="The contract terminates automatically and the deposit is refunded to the buyer" if unit else
            "The buyer may terminate in writing and the deposit is refunded (not automatic)")
    title_days = c.get("title_evidence_days_before")
    title_by = str(c.get("title_by") or "").strip().lower()
    if title_by not in ("", "seller", "buyer"):
        raise DealError(f"contract.title_by is {c['title_by']!r}: use \"seller\" or \"buyer\" (who designates the "
                        "closing agent and obtains title evidence, Para. 9(c)).")
    add(key="title", label="Title Evidence Delivered", short="Title Evidence", basis="before",
        days=title_days if title_days is not None else (15 if financed else 5), source="Para. 9(c)",
        party="Buyer" if title_by == "buyer" else "Seller", critical=False,
        default=None if title_days is not None else
        f"Title evidence deadline {_unset(c, 'title_evidence_days_before')}: used the form default, "
        f"{15 if financed else 5} days before closing" +("" if financed else " (cash)"),
        default_topic="title evidence",
        action="Title commitment delivered to the buyer", if_missed="Buyer may extend closing to review it")
    add(key="title_exam", label="Title Defect Notice", short="Title Defects", basis="event",
        received=c.get("title_commitment_received"), what="the title commitment", days=5, source="Standard A(ii)", party="Buyer", critical=True,
        action="Review the title commitment and give written notice of any defects that make title unmarketable",
        if_missed="Buyer accepts title as it is")
    add(key="survey", label="Survey Deadline", short="Survey", basis="before", days=c.get("survey_days_before", 5),
        source="Para. 9(d)", party="Buyer", critical=False, action="If the buyer wants a survey, have it done by this date",
        if_missed="Survey issues can't be raised in time")
    add(key="survey_notice", label="Survey Defect Notice", short="Survey Defects", basis="event",
        received=c.get("survey_received"), what="the survey", days=5, cap_at_closing=True, source="Standard B", party="Buyer", critical=False,
        action="Send the seller written notice of any encroachment or violation, with a copy of the survey",
        if_missed="Survey matters can't be raised as a title defect")
    if financed:
        add(key="insurance_bound", label="Homeowner's Insurance Bound (Lender Target)", short="Insurance Bound", basis="before",
            days=c.get("insurance_bound_days_before", 7), source="Lender's usual target, not a contract date", party="Buyer",
            critical=False, lender=True, action="Bind the policy and send the declarations page to the lender",
            if_missed="The lender may not be ready to fund on time")  # TL-25
        add(key="clear_to_close", label="Clear to Close / Closing Disclosure", short="Closing Disclosure", basis="before",
            days=c.get("cd_days_before", 3), business="trid", source="Lender (TRID 3-business-day rule)", party="Buyer",
            critical=False, lender=True, action="Buyer receives and signs the Closing Disclosure at least 3 business days before closing",
            if_missed="Closing must move")
    add(key="walkthrough", label="Final Walk-Through", short="Walk-Through", basis="before", days=c.get("walkthrough_days_before", 1),
        cap_at_closing=True, no_time=True,
        source=(cite("Para. 3") or "Para. 12(b)") if walkaway and not repairs_owed else "Para. 12(e)",
        party="Buyer", critical=False,
        action="Walk the property the day before closing or on closing day; confirm condition, repairs and included items",
        if_missed="Buyer loses the chance to verify condition")
    if has("G"):  # Rider G Para. 5: every other period runs from the buyer's receipt of the short sale approval
        for x in out:
            if (x["key"] not in SHORT_SALE_PHASE1 and x["basis"] in ("after", "earliest")
                    and not x.get("from_key") and not x.get("receipt_date")):
                x["from_approval"] = True
    return out


# Rider G Para. 5: the rows still counted from the Effective Date (Phase 1). Rider GG stays here too: its own words count
# from the Effective Date, and analyze() adds an agent note that Para. 5 could be read otherwise.
GG_KEYS = ("compensation_agreement", "compensation_cancel")  # Rider GG's rows
SHORT_SALE_PHASE1 = ("deposit", "short_sale_application", "short_sale_forms", "short_sale_approval", "short_sale_expires",
                     "short_sale_copy", "compensation_agreement", "compensation_cancel")


def rider_rows(c, has, add):
    """Rows for the CR-7 riders and contract standards that set their own dates, beyond the core ones above. Every
    default is the rider's own "if left blank" value (shared references frbar-riders.md and frbar-contract.md); a
    date blank with no default stays pending until the agent gives it."""
    if has("I"):  # Standard only (RESERVED on AS IS; contract_forms stops that combination)
        add(key="mold", label="Mold Inspection Period Ends", short="Mold Inspection", basis="after", days=c.get("mold_days", 20),
            source="Mold Inspection Rider (I)", party="Buyer", critical=True, contingency=True,
            action="Complete the mold inspection; if remediation exceeds the rider's amount, deliver the report and written "
                   "notice to cancel",
            if_missed="The mold contingency is waived")
    if has("M") and not c.get("drywall_waived"):
        add(key="drywall", label="Drywall Inspection Period Ends", short="Drywall Inspection", basis="after",
            days=c.get("drywall_days", 15), source="Defective Drywall Rider (M)", party="Buyer", critical=True, contingency=True,
            action="Inspect for defective drywall; if repair exceeds the rider's amount, deliver written notice to cancel",
            if_missed="The buyer can't cancel under the drywall rider")
    if has("A") and c.get("rofr"):
        add(key="rofr_docs", label="Right of First Refusal Documents Signed", short="ROFR Documents", basis="after",
            days=c.get("rofr_days", 5), source="Condominium Rider (A), Para. 2(c)", party="Both", critical=False,
            action="Buyer and seller sign what the association needs to waive or exercise its right of first refusal",
            if_missed="The association's review may not start")
    if has("G"):
        add(key="short_sale_application", label="Seller Gets Short Sale Application", short="Application Forms",
            basis="after", days=c.get("short_sale_application_days", 10), source="Short Sale Rider (G), Para. 2", party="Seller",
            critical=False, action="Seller obtains the lender's short sale application forms",
            if_missed="Seller is in default of the rider")
        add(key="short_sale_forms", label="Seller Returns Completed Short Sale Forms", short="Forms Returned",
            basis="after", from_key="short_sale_application", days=5, source="Short Sale Rider (G), Para. 2", party="Seller",
            critical=False, action="Seller completes and returns the lender's forms, then promptly sends any added documents",
            if_missed="Seller is in default of the rider")
        # Not a buyer contingency: after this date either party may cancel, so nothing the buyer relies on ends here.
        add(key="short_sale_approval", label="Short Sale Approval Deadline", short="Short Sale Deadline", basis="after",
            days=c.get("short_sale_approval_days", 90), source="Short Sale Rider (G), Para. 4", party="Seller", critical=True,
            action="Seller delivers the lender's written short sale approval",
            if_missed="Either party may cancel in writing; the deposit is refunded")
        if not c.get("short_sale_approval_received"):  # once the approval is in, the contract can't expire for want of it
            # TL-116: Para. 1, the seller sends the buyer and the closing agent a copy within 3 days of receiving it
            add(key="short_sale_copy", label="Seller Delivers Short Sale Approval Copy", short="Approval Copy",
                basis="event", received=c.get("short_sale_approval_seller_received"),
                what="the short sale approval", from_text="the seller's receipt of the short sale approval", days=3,
                source="Short Sale Rider (G), Para. 1",
                party="Seller", critical=False,
                action="Seller delivers a copy of the accepted short sale approval to the buyer and the closing agent",
                if_missed="Seller is in default of the rider")
            add(key="short_sale_expires", label="Contract Expires Without Approval", short="Contract Expires", basis="after",
                from_key="short_sale_approval", days=30, source="Short Sale Rider (G), Para. 4", party="Both", critical=True,
                action="The contract ends automatically if approval hasn't been delivered",
                if_missed="The contract terminates and the deposit is refunded")
    if has("R"):
        add(key="rezoning", label="Rezoning Final Action Deadline", short="Rezoning", basis="date", date=c.get("rezoning_date"),
            date_rule="Date written in the rider", source="Rezoning Contingency Rider (R)", party="Buyer", critical=True,
            contingency=True, action="Final government action on the rezoning; the buyer pursues it at the buyer's expense",
            if_missed="Either party may cancel in writing; the deposit is refunded",
            blank_note="the rider's date is blank and has no default")
    if has("S"):
        add(key="lease_agreement", label="Lease Purchase or Option Agreement Signed", short="Lease Agreement", basis="after",
            days=5, source="Lease Purchase/Lease Option Rider (S)", party="Both", critical=True, contingency=True,
            action="Sign the separate lease purchase or lease option agreement",
            if_missed="The contract terminates automatically; the deposit is refunded")
    if has("T"):
        add(key="pre_closing_agreement", label="Pre-Closing Occupancy Agreement Delivered", short="Occupancy Agreement",
            basis="after", days=c.get("pre_closing_agreement_days", 10), source="Pre-Closing Occupancy Rider (T)", party="Both",
            critical=True,  # TL-249: missing it lets either party cancel (the rider's last paragraph)
            action="Buyer and seller deliver the signed pre-closing occupancy agreement",
            if_missed="Either party may cancel in writing before the buyer moves in; the deposit is refunded")
    if has("U"):
        add(key="post_closing_agreement", label="Post-Closing Occupancy Agreement Delivered", short="Rent-Back Agreement",
            basis="before", days=c.get("post_closing_agreement_days_before", 10), source="Post-Closing Occupancy Rider (U)",
            party="Both", critical=True,  # TL-249: missing it lets either party cancel (the rider's last paragraph)
            action="Buyer and seller deliver the signed post-closing occupancy agreement",
            if_missed="Either party may cancel in writing; the deposit is refunded")
        if c.get("seller_occupancy_days"):
            add(key="seller_moves_out", label="Seller Delivers Possession", short="Seller Moves Out", basis="after_closing",
                days=c["seller_occupancy_days"], source="Post-Closing Occupancy Rider (U)", party="Seller", critical=True,
                action="Seller moves out and delivers keys; the final walk-through before closing doesn't cover this condition",
                if_missed="Per the post-closing occupancy agreement")
    if has("W"):
        add(key="backup_notice", label="Back-Up: Seller's Notice Deadline", short="Back-Up Notice", basis="date",
            date=c.get("backup_notice_date"), date_rule="Date written in the rider", source="Back-Up Contract Rider (W)",
            party="Seller", critical=True,
            action="Seller delivers written notice that the prior contract ended; that date becomes the Effective Date",
            if_missed="The back-up contract doesn't move into first position (the rider doesn't say; confirm with your agent)",
            blank_note="the rider's date is blank")
    if has("X"):
        add(key="kickout", label="Kick-Out: Additional Deposit Due", short="Kick-Out Deposit", basis="event",
            received=c.get("kickout_notice_received"), what="the seller's copy of a back-up contract", days=3,
            source="Kick-Out Clause Rider (X)", party="Buyer", critical=True,
            action="Deliver the additional deposit to escrow; doing so waives the financing and sale-of-property contingencies",
            if_missed="The contract terminates automatically; the deposit is refunded")
    for code, key, who, field in (("Y", "seller_attorney", "Seller", "seller_attorney_date"),
                                  ("Z", "buyer_attorney", "Buyer", "buyer_attorney_date")):
        if has(code):
            add(key=key, label=f"{who}'s Attorney Approval Deadline", short=f"{who}'s Attorney", basis="date",
                date=c.get(field), date_rule="Date written in the rider",
                source=f"{who}'s Attorney Approval Rider ({code})", party=who, critical=True, contingency=code == "Z",
                action=f"If the {who.lower()}'s attorney disapproves, the {who.lower()} delivers written notice to cancel",
                if_missed="The attorney approval right ends (the rider doesn't say; confirm with your agent)",
                blank_note="the rider's date is blank and has no default")
    if has("DD"):
        add(key="management_agreements", label="Seller Delivers Rental Management Agreements", short="Rental Agreements",
            basis="after", days=5, source="Seasonal and Vacation Rentals Rider (DD)", party="Seller", critical=False,
            action="Seller gives the buyer copies of the property management agreements behind existing bookings",
            if_missed="The buyer's 5-day review doesn't start")
        add(key="management_review", label="Rental Management Review Ends", short="Rental Review", basis="event",
            received=c.get("management_agreements_received"), what="the property management agreements", days=5,
            source="Seasonal and Vacation Rentals Rider (DD); Para. 6(b)", party="Buyer", critical=True, contingency=True,
            action="If the management terms aren't acceptable, deliver written notice to cancel",
            if_missed="The buyer is bound by the agreements for bookings in place at closing")
    if has("GG"):
        add(key="compensation_agreement", label="Buyer's Broker Compensation Agreement Signed", short="Compensation Agreement",
            basis="after", days=c.get("compensation_agreement_days", 3), source="Rider GG", party="Both", critical=False,
            broker=True,  # TL-246: a broker matter, never the client's first deadline
            action="The seller or listing broker signs and delivers the compensation agreement with the buyer's broker",
            if_missed="The buyer's 3-day cancel window opens")
        add(key="compensation_cancel", label="Compensation Contingency Ends", short="Compensation Contingency", basis="after",
            from_key="compensation_agreement", days=3, source="Rider GG", party="Buyer", critical=True, contingency=True,
            broker=True,
            action="If the agreement wasn't signed and delivered, the buyer may deliver written notice to cancel",
            if_missed="The contingency ends; the buyer proceeds")
    if has("N") and c.get("cccl_requested"):
        title_days = c.get("title_evidence_days_before")
        financed = c.get("financing", "conventional") != "cash"
        add(key="cccl", label="Coastal Construction Line Affidavit or Survey", short="CCCL Affidavit", basis="before",
            days=title_days if title_days is not None else (15 if financed else 5),
            source="Coastal Construction Control Line Rider (N); Para. 9(c)", party="Seller", critical=False,
            action="Seller delivers the CCCL affidavit or survey the buyer requested", if_missed="Seller is in default of the rider")
    if c.get("tenants"):  # Para. 6(b) checked for a tenant: the lease facts, the buyer's review, then the estoppels
        add(key="lease_disclosure", label="Seller Discloses Leases", short="Lease Disclosure", basis="after", days=5,
            source="Para. 6(b)", party="Seller", critical=False,
            action="Seller discloses the lease and occupancy terms in writing and delivers copies of the written leases",
            if_missed="The buyer's 5-day review doesn't start")
        add(key="lease_review", label="Lease Review Cancellation Window", short="Lease Review", basis="event",
            received=c.get("leases_received"), what="the lease terms and copies", days=5, source="Para. 6(b)",
            party="Buyer", critical=True, contingency=True,
            action="If the lease terms aren't acceptable, deliver written notice to cancel; the deposit is refunded",
            if_missed="The buyer takes the property subject to the disclosed leases")
        add(key="tenant_estoppels", label="Tenant Estoppel Letters Due", short="Estoppel Letters", basis="before", days=10,
            source="Standard D", party="Seller", critical=False,
            action="Seller delivers tenant estoppel letters (or a seller's affidavit with the same facts)",
            if_missed="The buyer may cancel if the letters show different terms than the seller disclosed")
    if c.get("title_defect_notice"):
        add(key="title_cure", label="Seller's Title Cure Period Ends", short="Title Cure", basis="after",
            receipt_date=c["title_defect_notice"], what="the buyer's title defect notice", days=30, source="Standard A(ii)",
            party="Seller", critical=True, action="Seller cures the title defects the buyer reported",
            if_missed="The buyer has 5 days to extend up to 120 days, accept title as it is, or cancel")
    if c.get("fincen_report"):
        add(key="fincen", label="FinCEN Report Information Due", short="FinCEN Info", basis="before", days=1,
            source="Standard I(iii)", party="Both", critical=True,
            action="Buyer and seller give the closing agent the beneficial-owner information for the FinCEN report; "
                   "the buyer pays its fees",
            if_missed="Closing may be delayed")


def closing_rows(c, frbar):
    default_source = "Para. 4 · possession Para. 6" if frbar else "Contract"
    rows = [dict(key="closing", label="Closing", short="Closing", basis="closing", source=c.get("closing_source", default_source),
                 party="Both", critical=True, contingency=False, action="Sign, fund and record; keys and possession delivered",
                 if_missed="Default unless extended in writing")]
    if c.get("possession_date") or c.get("possession_note"):
        rows.append(dict(key="possession", label="Possession", short="Possession", basis="possession",
                         source=c.get("possession_source", "Para. 6" if frbar else "Contract"), party="Seller", critical=False, contingency=False,
                         action=c.get("possession_note") or "Seller vacates and delivers keys",
                         if_missed="Per the contract or occupancy agreement"))
    return rows


# --- compute ------------------------------------------------------------------

def apply_amendments(contract, amendments):
    c = copy.deepcopy(contract)
    history = []
    for a in amendments or []:
        before = {k: c.get(k) for k in a.get("changes", {})}
        c.update(a.get("changes", {}))
        c.setdefault("date_overrides", {}).update(a.get("date_overrides", {}))
        history.append({"date": a.get("date"), "description": a.get("description", ""), "name": a.get("name") or "",
                        "changes": a.get("changes", {}), "before": before, "date_overrides": a.get("date_overrides", {})})
    return c, history


_ORDINALS = ("first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth", "ninth", "tenth")


def _amendment_name(h, i):
    """TL-231: an amendment as the agent knows it: its form or title when recorded ("Extension Addendum (EA-4)"), else
    its place in signing order ("The first amendment"), never "Amendment 1", which reads as a form's own number."""
    if h.get("name"):
        return f"The {h['name']}" if not re.match(r"^(the|an?)\s", h["name"], re.I) else h["name"][:1].upper() + h["name"][1:]
    return f"The {_ORDINALS[i - 1] if i <= len(_ORDINALS) else f'#{i}'} amendment"


OPEN_RIGHT_KEYS = ("hoa_docs", "condo_docs", "title_exam", "survey_notice")
WAITS_FOR_CLOSING = "Waits for the closing date, set by the short sale approval"
FORM_DEFAULTS = {"inspection_days": 15, "loan_approval_days": 30, "deposit_days": 3, "additional_deposit_days": 10,
                 "loan_application_days": 5, "lead_paint_days": 10, "flood_elevation_days": 20, "walkthrough_days_before": 1,
                 "survey_days_before": 5, "mold_days": 20, "drywall_days": 15, "short_sale_application_days": 10,
                 "short_sale_approval_days": 90, "pre_closing_agreement_days": 10, "post_closing_agreement_days_before": 10,
                 "compensation_agreement_days": 3, "rofr_days": 5}  # FR/BAR and CR-7 blanks


def _date_text(v):
    """'2026-11-24' -> 'Nov 24, 2026'; anything else as written."""
    try:
        d = _d(v)
    except ValueError:
        return str(v)
    return f"{d:%b %-d, %Y}" if d else ""


def _value_text(v):
    """A changed value as the report shows it; a date with a time keeps the time (TL-117)."""
    if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}", v):
        return f"{_date_text(v)} {datetime.strptime(v[:16], '%Y-%m-%d %H:%M'):%-I:%M %p}"
    return _date_text(v) if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v) else str(v)


def _was(key, before, frbar):
    """TL-21: a blank that the form filled in reads as its value ("30 days (form default)"), not "blank"."""
    if before is None:
        return f"{_field_value(key, FORM_DEFAULTS[key])} (form default)" if frbar and key in FORM_DEFAULTS else "not set"
    return _field_value(key, before)


# TL-215: the amendment history names each changed field as the report does, never the deal file's field name
FIELD_LABELS = {"closing_date": "Closing Date", "closing_time": "Closing Time", "price": "Price",
                "inspection_days": "Inspection Period", "loan_approval_days": "Loan Approval Period",
                "loan_application_days": "Loan Application Period", "deposit_days": "Deposit Period",
                "additional_deposit_days": "Additional Deposit Period", "financing": "Financing",
                "title_evidence_days_before": "Title Evidence Deadline", "survey_days_before": "Survey Deadline",
                "walkthrough_days_before": "Walk-Through", "appraisal_date": "Appraisal Date",
                "appraisal_days": "Appraisal Period", "insurance_date": "Insurance Date", "insurance_days": "Insurance Period",
                "insurance_days_before": "Insurance Period",
                "possession_date": "Possession Date", "possession_time": "Possession Time",
                "short_sale_approval_received": "Short Sale Approval Received",
                "condo_docs_received": "Condo Documents Received", "hoa_docs_received": "HOA Disclosure Received",
                "loan_amount": "Loan Amount", "deposit_amount": "Initial Deposit",
                "additional_deposit_amount": "Additional Deposit", "balance_to_close": "Balance to Close"}
_ACRONYMS = {"hoa": "HOA", "fha": "FHA", "va": "VA", "rofr": "ROFR", "cccl": "CCCL", "sirs": "SIRS", "cd": "CD"}
MONEY_FIELDS = ("price", "loan_amount", "deposit_amount", "additional_deposit_amount", "other_amount",
                "balance_to_close", "preapproval_amount", "preapproval_price")


def _field_label(key):
    """'inspection_days' -> 'Inspection Period'; a field not in FIELD_LABELS reads in title case without its unit."""
    if key in FIELD_LABELS:
        return FIELD_LABELS[key]
    words = re.sub(r"_(days_before|days)$", "", key).split("_")
    return " ".join(_ACRONYMS.get(w, w.capitalize()) for w in words)


def _field_value(key, v):
    """A changed field's value with its unit: "15 days", "5 days before closing", "$469,000"."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        if key in MONEY_FIELDS:
            return f"${v:,.0f}"
        if key.endswith("_days_before"):
            return f"{_plural(int(v), 'day')} before closing"
        if key.endswith("_days"):
            return _plural(int(v), "day")
    return _value_text(v)


def _override(value, rules, rollover=None):
    """A deadline stated as a specific date. With a time it's kept as given; a date alone ends at the contract's
    end of day, and a weekend or holiday rolls forward like any period (`rollover` as in forward())."""
    if len(str(value)) >= 16:
        return _dt(value, _t(rules["end_time"])), ""
    d, extra = _d(value), rules["_extra_holidays"]
    rolls = rollover if rollover is not None else rules["weekend_holiday_rollover"] == "next_business_day"
    if not dates.is_business_day(d, extra) and rolls:
        nd = dates.next_business_day(d, extra)
        return datetime.combine(nd, _t(rules["rollover_time"])), f"falls on {_on(d, nd, extra)}: extended to {nd:%a %b %-d}"
    return datetime.combine(d, _t(rules["end_time"])), ""


def check_inputs(c, extra_deadlines):
    """Plain errors for dates and periods that can't be right (TL-9)."""
    eff, closing = _d(c["effective_date"]), _d((c.get("date_overrides") or {}).get("closing") or c.get("closing_date"))
    if closing and closing <= eff:
        raise DealError(f"The closing date ({closing:%b %-d, %Y}) is on or before the Effective Date ({eff:%b %-d, %Y}): "
                        "check both dates.")
    for key, v in c.items():
        if key.endswith("_days") or key.endswith("_days_before"):
            if v is not None and (isinstance(v, bool) or not isinstance(v, int) or v < 0):
                raise DealError(f"contract.{key} is {v!r}: a period is a whole number of days, 0 or more.")
    for i, x in enumerate(extra_deadlines):
        _check_deadline(x, i)


CUSTOM_BASES = ("after", "before", "date", "event")
PARTIES = ("Buyer", "Seller", "Both")


def _check_deadline(x, i):
    """TL-109, TL-110: a custom deadline the script can't compute is a plain error naming the entry and the field."""
    if not isinstance(x, dict) or not x.get("key"):
        raise DealError(f"deadlines[{i}] needs a key (a short id such as \"due_diligence\").")
    name = f"Deadline {x['key']!r}"
    for field in ("label", "basis", "party"):
        if not x.get(field):
            raise DealError(f"{name} needs {field}.")
    if x["basis"] not in CUSTOM_BASES:
        raise DealError(f"{name} has basis {x['basis']!r}: use after, before, date or event.")
    if str(x["party"]).title() not in PARTIES:
        raise DealError(f"{name} has party {x['party']!r}: use Buyer, Seller or Both.")
    if x["basis"] in ("after", "before", "event") and x.get("days") is None:
        raise DealError(f"{name} needs days (a whole number, 0 or more) for basis {x['basis']!r}.")
    if x.get("days") is not None and (isinstance(x["days"], bool) or not isinstance(x["days"], int) or x["days"] < 0):
        raise DealError(f"{name} has days {x['days']!r}: use a whole number, 0 or more.")
    t = x.get("time")
    if t is not None:
        if t == "closing":
            if x["basis"] not in ("before", "date"):
                raise DealError(f"{name} has time \"closing\", which works only with basis before (days before Closing, "
                                "or 0 for closing day) or date.")
        elif not re.match(r"^([01]?\d|2[0-3]):[0-5]\d$", str(t)):
            raise DealError(f"{name} has time {t!r}: use HH:MM (\"17:00\") or \"closing\".")
    if x.get("rollover") is not None and not isinstance(x["rollover"], bool):
        raise DealError(f"{name} has rollover {x['rollover']!r}: use true or false.")


def compute(c, extra_deadlines, rules, frbar):
    check_inputs(c, extra_deadlines)
    eff, extra = _d(c["effective_date"]), rules["_extra_holidays"]
    overrides = c.get("date_overrides") or {}
    closing_dt = None  # the closing everything counts back from: an override, then the contract date, rolled forward
    closing_note, closing_rule = "", "Closing date in contract"
    # Rider G: most periods, and the closing, count from the buyer's receipt of the short sale approval (Paras. 5, 6)
    short_sale = frbar and "G" in cf.rider_codes(c.get("riders"))[0]
    approval = _d(c.get("short_sale_approval_received")) if short_sale else None
    ss_days = int(c.get("short_sale_closing_days") or 45)
    raw = overrides.get("closing") or (None if short_sale else c.get("closing_date"))
    if short_sale and not raw and approval:
        raw = str(approval + timedelta(days=ss_days))
        closing_rule = f"{_plural(ss_days, 'day')} after short sale approval (Rider G, Para. 6)"
    if raw:
        closing = _d(raw)
        if not dates.is_business_day(closing, extra) and rules.get("closing_rollover") \
                and rules["weekend_holiday_rollover"] == "next_business_day":
            rolled = dates.next_business_day(closing, extra)
            closing_note = (f"the Closing Date, {closing:%a %b %-d}, is {_on(closing, rolled, extra, dated=False)}: "
                            f"closing extends to {rolled:%a %b %-d}")
            closing = rolled
        elif not dates.is_business_day(closing, extra):
            closing_note = (f"the Closing Date, {closing:%a %b %-d}, is {_on(closing, closing, extra, dated=False)}: "
                            "confirm the title company can close")
        t = str(raw)[11:16] if len(str(raw)) >= 16 else (c.get("closing_time") or rules["closing_time"])
        closing_dt = datetime.combine(closing, _t(t))
    closing = closing_dt.date() if closing_dt else None

    items = (frbar_deadlines(c) if frbar else []) + [
        dict(x, party=str(x["party"]).title(), contingency=x.get("contingency", False)) for x in extra_deadlines]
    if closing:
        items += closing_rows(c, frbar)
    elif short_sale:  # the closing waits for the approval: shown as pending, never dated from the Effective Date
        items += [dict(closing_rows(c, frbar)[0], basis="pending_closing")]
    keys = [x["key"] for x in items]
    dup = sorted({k for k in keys if keys.count(k) > 1})
    if dup:  # TL-111: amendments, overrides and completed dates find a deadline by its key
        raise DealError(f"Deadline key {', '.join(map(repr, dup))} is used twice (a custom deadline can't reuse a built-in "
                        "key): give the custom deadline its own key, or change the built-in one through the contract "
                        "fields or date_overrides.")
    after_approval = "after short sale approval"
    rows, done = [], {}
    for x in items:
        r = dict(x)
        basis, days = x["basis"], x.get("days")
        by_closing = x.get("time") == "closing"  # a custom row due by the closing time ("by Closing")
        at = None if by_closing or not x.get("time") else _t(x["time"])
        roll = x.get("rollover")
        if basis == "after" and x.get("from_key"):
            ref = done.get(x["from_key"])
            if not ref:
                continue
            if not ref["when"]:  # the row it counts from is still pending: so is this one
                r["when"], r["rule"] = None, f"{_plural(int(days), 'day')} after {ref['short']}"
                r["note"] = ref.get("note", "")
            else:
                r["when"], r["note"] = forward(ref["when"].date(), int(days), rules, x.get("business", False), at, roll)
                r["rule"] = f"{_plural(int(days), 'day')} after {ref['short']}"
        elif basis in ("after", "earliest") and x.get("from_approval") and not approval:
            r["when"] = None
            r["rule"] = (f"{_plural(int(days), 'day')} {after_approval}" if basis == "after" else
                         "Earlier of " + " or ".join(
                             f"{_plural(int(p['days']), 'day')} " + (after_approval if p["basis"] == "after" else "before Closing")
                             for p in x["of"]))
            r["note"] = "Starts when the buyer receives the short sale approval (Rider G, Para. 5)"
        elif basis == "after" and x.get("from_approval"):
            r["when"], r["note"] = forward(approval, int(days), rules, x.get("business", False), at, roll)
            r["rule"] = f"{_plural(int(days), 'day')} {after_approval} ({approval:%b %-d})"
        elif basis == "pending_closing":
            r["when"], r["rule"] = None, f"{_plural(ss_days, 'day')} {after_approval} (Rider G, Para. 6)"
            r["note"] = "Set by the short sale approval date"
        elif basis == "after":
            start = _d(x.get("receipt_date")) or eff  # TL-15: a period that runs from someone's receipt
            r["when"], r["note"] = forward(start, int(days), rules, x.get("business", False), at, roll)
            r["rule"] = (f"{_plural(int(days), 'day')} after " + (f"{x.get('what', 'receipt')} ({start:%b %-d})" if x.get("receipt_date")
                         else "Effective Date") + (" (business days)" if x.get("business") else ""))
        elif basis == "before" and not closing:
            r["when"], r["rule"] = None, f"{_plural(int(days), 'day')} before Closing"
            r["note"] = WAITS_FOR_CLOSING if short_sale else "Set once the closing date is known"
        elif basis == "before":
            r["when"], r["note"] = backward(closing, int(days), rules, x.get("business", False),
                                            closing_dt.time() if by_closing else at, roll)
            counted = closing - timedelta(days=int(days))
            if not x.get("business") and r["when"].date() > counted:  # TL-226: extended forward, closer to closing
                r["rolled_from"] = counted
            r["rule"] = ("By Closing" if by_closing and int(days) == 0 else "Closing day" if int(days) == 0 else
                         f"{_plural(int(days), 'day')} before Closing" + (" (TRID business days)" if x.get("business") == "trid"
                                                                         else " (business days)" if x.get("business") else ""))
        elif basis == "date" and not x.get("date"):  # a date blank with no form default (Riders R, V, W, Y, Z)
            r["when"], r["rule"] = None, x.get("blank_rule", "Date written in the rider")
            r["note"] = "Left blank in the rider: to be confirmed"  # FH-102: the instruction goes to the agent
            r["agent_note"] = f"{x['label']}: {x.get('blank_note') or 'the date is blank'}. Ask the agent for it and re-run"
        elif basis == "date":
            r["when"], r["note"] = _override(x["date"], rules, roll)
            if by_closing and closing_dt:
                r["when"] = datetime.combine(r["when"].date(), closing_dt.time())
            elif at:
                r["when"] = datetime.combine(r["when"].date(), at)
            r["rule"] = x.get("date_rule", "Specific date in contract")
        elif basis == "earliest":  # the earlier of several periods (Rider H: 30 days after Effective Date or 10 before Closing)
            opts = []
            for part in x["of"]:
                if part["basis"] == "after":
                    start = approval if x.get("from_approval") else eff
                    when, note = forward(start, int(part["days"]), rules)
                    opts.append((when, note, f"{_plural(int(part['days']), 'day')} "
                                 + (after_approval if x.get("from_approval") else "after Effective Date")))
                elif closing:
                    when, note = backward(closing, int(part["days"]), rules)
                    opts.append((when, note, f"{_plural(int(part['days']), 'day')} before Closing"))
            r["when"], r["note"], first = min(opts, key=lambda o: o[0])
            r["rule"] = "Earlier of " + " or ".join(o[2] for o in opts) + (f": {first}" if len(opts) > 1 else "")
        elif basis == "after_closing":
            if closing:
                r["when"], r["note"] = forward(closing, int(days), rules)
                r["rule"] = f"{_plural(int(days), 'day')} after Closing"
            else:
                r["when"], r["rule"] = None, f"{_plural(int(days), 'day')} after Closing"
                r["note"] = WAITS_FOR_CLOSING if short_sale else "Set once the closing date is known"
        elif basis == "closing":
            r["when"], r["rule"], r["note"] = closing_dt, closing_rule, closing_note
        elif basis == "possession":
            pd = _d(c.get("possession_date")) or closing
            r["when"] = datetime.combine(pd, _t(c.get("possession_time") or "17:00")) if pd else None
            r["rule"], r["note"] = ("At closing" if pd == closing else "Per occupancy agreement"), ""
        elif basis == "event":
            received = _d(x.get("received"))
            if received:
                start = max(received, eff) if x.get("start_after_effective") else received
                r["when"], r["note"] = forward(start, int(days), rules, x.get("business", False), at, roll)
                # TL-211: `from_text` names the event itself when it's a receipt by someone other than the reader
                # ("the seller's receipt of the short sale approval"), so the rule never reads "receipt of ... receipt"
                r["rule"] = (f"{_plural(int(days), 'day')}{' (business days)' if x.get('business') else ''} after "
                             + (f"{x['from_text']} ({received:%b %-d})" if x.get("from_text") else
                                f"{x.get('what', 'documents')} received ({received:%b %-d})"))
            else:
                r["when"], r["rule"] = None, (f"Runs from {x['from_text']}" if x.get("from_text") else
                                              f"Runs from receipt of {x.get('what', 'documents')}")
                r["note"] = "Dated once the receipt is recorded"  # FH-102: client-safe; analyze() tells the agent
        else:
            raise DealError(f"Deadline {x.get('key')!r} has an unknown basis {basis!r} (use after, before, date or event).")
        override = overrides.get(x["key"]) if x["key"] != "closing" else None
        if override:
            r["when"], r["note"] = _override(override, rules, roll)
            r["rule"] = "Specific date in contract / amendment"
            r.pop("rolled_from", None)
        if x.get("cap_at_closing") and r["when"] and closing_dt and r["when"] > closing_dt:
            r["when"] = closing_dt
            r["note"] = "; ".join(n for n in (r.get("note"), "the right ends at closing") if n)
        if (basis == "before" and r["when"] and closing_dt and r["when"].date() == closing_dt.date()
                and r["when"] > closing_dt):  # TL-105: rolled onto closing day, so it's due by the closing, not after it
            r["when"], by_closing = closing_dt, True
            r["note"] = "; ".join(n for n in (r.get("note"), "falls on closing day: due by the closing time") if n)
        if x.get("default"):
            r["default"] = x["default"]
        if (rules.get("_no_end_time") and basis not in ("closing", "possession", "pending_closing") and not x.get("time")
                and not (basis == "date" and len(str(x.get("date"))) >= 16)):
            r["no_time"] = True  # TL-123: the contract states no time of day, so none is shown
        r["by_closing"] = bool(by_closing and r["when"] and closing_dt and r["when"].date() == closing_dt.date())
        rows.append(r)
        done[x["key"]] = r
    # the closing sorts after anything due "by Closing" at the same time
    rows.sort(key=lambda r: (r["when"] is None, r["when"] or datetime.max, r["key"] == "closing"))
    return rows


def _fmt(dt, rules, with_time=True):
    if dt is None:
        return "Pending"
    if not with_time:
        return f"{dt:%a %b %-d}"
    t = "11:59 PM" if dt.time() == time(23, 59) else f"{dt:%-I:%M %p}"
    zone = rules.get("_tz")
    suffix = f" {zone}" if zone and zone != rules.get("time_zone", zone) else ""  # only when it differs from the usual
    return f"{dt:%a %b %-d} · {t}{suffix}"


def _row_display(r, when, rules, closing_dt):
    """A deadline's date and time. An event rather than a deadline (the walk-through) shows its date only, or "before
    Closing" on closing day; a row due by the closing time shows "by Closing"."""
    if when is None:
        return _fmt(None, rules)
    on_closing_day = bool(closing_dt) and when.date() == closing_dt.date()
    if r.get("no_time"):
        return f"{when:%a %b %-d}" + (" · before Closing" if on_closing_day else "")
    if r.get("by_closing") and on_closing_day:
        return f"{when:%a %b %-d} · by Closing"
    return _fmt(when, rules)


def _completed(deal, keys):
    """{key: date}: deadlines already met (an escrow receipt shows the deposit in). An unknown key is a plain error."""
    done = deal.get("completed") or {}
    if not isinstance(done, dict):
        raise DealError('completed is a map of deadline key to the date it was done: {"deposit": "2026-09-26"}.')
    bad = [k for k in done if k not in keys]
    if bad:
        raise DealError(f"completed names {', '.join(map(repr, bad))}, not a deadline in this timeline. Use one of: "
                        + ", ".join(sorted(keys)) + ".")
    out = {}
    for k, v in done.items():
        try:
            out[k] = _d(v)
        except ValueError:
            raise DealError(f"completed.{k} is {v!r}: use the date it was done, YYYY-MM-DD.") from None
        if not out[k]:
            raise DealError(f"completed.{k} needs the date it was done, YYYY-MM-DD.")
    return out


def _norm(text):
    return re.sub(r"\W+", " ", str(text).lower()).strip()


def _sentence(text):
    """A flag as a sentence: ends with a period (TL-211)."""
    text = str(text).strip()
    return text if not text or text.endswith((".", "?", "!")) else text + "."


_STOP = {"the", "a", "an", "and", "or", "of", "to", "in", "on", "is", "it", "its", "for", "by", "be", "was", "this",
         "that", "as", "at", "with", "from", "so", "if", "s"}


def _words(text):
    return {w for w in _norm(text).split() if w not in _STOP}


def _restates(agent_note, script_note):
    """TL-211: True when the agent's note says what a script note already says in other words: nearly every word of the
    agent's (three in four) is in the script's. Short notes (under four words) are only dropped as exact repeats."""
    a = _words(agent_note)
    return len(a) >= 4 and len(a & _words(script_note)) >= 0.75 * len(a)


def _agent_note(n):
    """(key, text) for an agent note: a plain string, or {"key": ..., "text": ...} naming the script note key or the
    deadline key it's about (TL-247)."""
    if isinstance(n, dict):
        return (str(n.get("key") or "").strip() or None), str(n.get("text") or "")
    return None, str(n)


def _dedupe_notes(agent_given, script_notes, topics, covered=frozenset(), rows=None):
    """(notes, merged): the agent's notes plus the script's, without saying the same thing twice. A script note replaces
    an agent note keyed to it (TL-247: the agent note's `key` is a script note key, or a deadline key a script note
    covers), one on the same default (same topic words and "default"), or one that restates it (_restates), since the
    script's is exact. `merged` lists the keys of the agent notes dropped for their key.

    TL-259: an agent note keyed to a deadline no script note covers merges with that row instead: one line that names
    the row and its date ("Buyer's Broker Compensation Agreement Signed (Mon Sep 28): ..."), and a second note on the
    same row joins it. `joined` lists those row keys. `rows` maps a row key to its (label, date text)."""
    kept, merged, joined, at, rows = [], [], [], {}, rows or {}
    for n in agent_given:
        key, text = _agent_note(n)
        if key and key in covered:
            merged.append(key)
        elif key and key in rows:
            if key in at:
                kept[at[key]] = _sentence(kept[at[key]]) + " " + text
            else:
                label, when = rows[key]
                at[key] = len(kept)
                kept.append(f"{label} ({when}): {text}")
                joined.append(key)
        elif not (any(t in _norm(text) and "default" in _norm(text) for t in topics)
                  or any(_restates(text, s) for s in script_notes)):
            kept.append(text)
    out = []
    for n in kept + script_notes:
        if _norm(n) not in {_norm(x) for x in out}:
            out.append(n)
    return out, merged, joined


def _check_riders(contract):
    """A rider the form doesn't allow (I, K, L on AS IS) or K and L together stops the run: the dates would be wrong."""
    try:
        cf.terms(contract["contract_form"], contract)
    except cf.FormError as e:
        raise DealError(str(e)) from e


DATE_LIKE = re.compile(r"^\d{4}-\d{2}-\d{2}")


def _check_dates(value, path):
    """TL-110: every date in the deal file is a real date; a bad one ("2026-11-31") names its field."""
    if isinstance(value, dict):
        for k, v in value.items():
            _check_dates(v, f"{path}.{k}" if path else str(k))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            _check_dates(v, f"{path}[{i}]")
    elif isinstance(value, str) and DATE_LIKE.match(value):
        try:
            if len(value) >= 16:
                datetime.strptime(value[:16], "%Y-%m-%d %H:%M")
            else:
                datetime.strptime(value[:10], "%Y-%m-%d")
        except ValueError:
            raise DealError(f"{path} is {value!r}: not a real date. Use YYYY-MM-DD (or YYYY-MM-DD HH:MM).") from None


def _price(v, field="price"):
    """TL-110: the price (or another dollar amount) as a number; "$412,000" reads as 412000."""
    if v in (None, "") or (isinstance(v, (int, float)) and not isinstance(v, bool)):
        return v if v not in (None, "") else None
    try:
        return float(re.sub(r"[$,\s]", "", str(v)))
    except ValueError:
        raise DealError(f"contract.{field} is {v!r}: use a number (412000).") from None


def _amount_in(text):
    """The first dollar amount in a written deposit ("$11,000", "$11,000 (10 days)"), or None."""
    m = re.search(r"\$?\s*(\d[\d,]*(?:\.\d+)?)", str(text or ""))
    return float(m.group(1).replace(",", "")) if m else None


def money_check(c, price):
    """TL-208: agent notes (key, text) when the contract's money doesn't add up. Para. 2: the initial and additional
    deposits, the loan, any other amount and the balance to close make up the price; a pre-approval below the loan
    amount (or a purchase price cap below the price) won't cover the deal. Deposits come from `deposit_amount` /
    `additional_deposit_amount`, else the amounts written in `deposit_amount_str` / `additional_deposit_amount_str`."""
    out = []
    num = {k: _price(c.get(k), k) for k in MONEY_FIELDS if k != "price"}
    for k, s in (("deposit_amount", "deposit_amount_str"), ("additional_deposit_amount", "additional_deposit_amount_str")):
        if num[k] is None:
            num[k] = _amount_in(c.get(s))
    loan, balance = num["loan_amount"], num["balance_to_close"]
    if loan is None and c.get("financing") == "cash":
        loan = 0
    deposits = sum(x or 0 for x in (num["deposit_amount"], num["additional_deposit_amount"], num["other_amount"]))
    if price and loan is not None and balance is not None:  # every part of Para. 2 is known: it must equal the price
        total = deposits + loan + balance
        if abs(total - price) >= 1:
            # TL-234: worded to the agent, who can answer it (a counter often changes the price but not Para. 2)
            out.append(("money_mismatch", f"Para. 2 doesn't add up: the deposits, loan and balance to close total "
                        f"${total:,.0f}, but the price is ${price:,.0f}. A counteroffer or amendment may have changed the "
                        "price without updating Para. 2. Which figures are current?"))
    elif price and loan and deposits + loan > price:  # no balance given: the parts known can't pass the price
        out.append(("money_mismatch", f"Para. 2 doesn't add up: the deposits and the ${loan:,.0f} loan total "
                    f"${deposits + loan:,.0f}, more than the ${price:,.0f} price. Which figures are current?"))
    pre = num["preapproval_amount"]
    if pre is not None and num["loan_amount"] and pre < num["loan_amount"]:
        out.append(("preapproval_below_loan", f"The pre-approval (${pre:,.0f}) is below the ${num['loan_amount']:,.0f} "
                    "loan amount: ask the lender for an updated letter before the loan approval deadline"))
    cap = num["preapproval_price"]
    if cap is not None and price and cap < price:
        out.append(("preapproval_below_price", f"The pre-approval covers a purchase price up to ${cap:,.0f}, below the "
                    f"${price:,.0f} price: ask the lender for an updated letter before the loan approval deadline"))
    return out


REPAIR_LIMIT_NAMES = {"general": "General Repair", "wdo": "WDO Repair", "permit": "Permit"}


def repair_limits(c, price):
    """TL-245: the Para. 9(a) repair limits in dollars, when the form and riders keep the seller's repair obligation
    (contract_forms decides: the Standard form alone or with Rider L), and the price is known. `blank` lists the limits
    the contract leaves blank (1.5% of the price each). None when no repair limits apply."""
    if not price or not cf.terms(c["contract_form"], c)["repairs_owed"]:
        return None
    try:
        out = cf.repair_limits(price, c)
    except cf.FormError as e:
        raise DealError(str(e)) from e
    given = c.get("repair_limits") or {}
    return {**out, "blank": [k for k in cf.REPAIR_LIMIT_KEYS if given.get(k) is None]}


def _dated(found):
    """'Appraisal Due Tue Nov 3 and Low-Appraisal Notice Due Fri Nov 6' from alternative rows."""
    return " and ".join(f"{x['label']} {x['date_display']}" for x in found if x["date_display"] != "Pending")


def consistency_notes(c, current, rules, eff, note, side="buyer", alt=None):
    """FR/BAR agent notes for recorded terms that don't fit together or that the rows leave out on purpose.

    TL-241: `alt(note_key, condition, changes, keys)` re-runs the timeline with the answer changed and returns the rows
    it would give, so a note's question comes with the date that applies if the answer changes (the output's
    `if_changed` lists them too)."""
    alt = alt or (lambda *a: [])
    codes = cf.rider_codes(c.get("riders"))[0]
    financed = c.get("financing", "conventional") != "cash"
    # TL-203: Rider F's fields without Rider F. With the FHA/VA rider (E) they add nothing (its protection runs to
    # closing); without it they still date the rows, on Rider F's rules
    given = [f for f in ("appraisal_date", "appraisal_days") if c.get(f)]
    if given and "F" not in codes:
        what = " and ".join(given) + (" is" if len(given) == 1 else " are")
        if "E" in codes:
            dated = _dated(alt("appraisal_without_rider_f", "Rider F is attached",
                               {"riders": list(c.get("riders") or []) + ["F"]}, ("appraisal_due", "appraisal")))
            tail = f" If Rider F is attached: {dated}." if dated else ""
        else:
            alt("appraisal_without_rider_f", "Rider F isn't attached", {f: None for f in given}, ("appraisal_due", "appraisal"))
            tail = " If it isn't, the appraisal rows drop."
        note("appraisal_without_rider_f", f"{what} set but the Appraisal Contingency Rider (F) isn't in riders: "
             + ("with the FHA/VA rider (E) the appraisal protection runs to closing, so no appraisal rows were added. "
                if "E" in codes else "the appraisal rows use Rider F's rules. ")
             + "Confirm whether Rider F is attached, and remove the field if it isn't." + tail)
    # TL-203: Para. 9(c)'s blank is 15 days before closing when financed, 5 when cash; the other one usually means the
    # financing or the days were misread
    title_days = c.get("title_evidence_days_before")
    if title_days is not None and title_days == (5 if financed else 15):
        dated = _dated(alt("title_days_financing", "Para. 9(c) is blank (the form default)",
                           {"title_evidence_days_before": None}, ("title",)))
        note("title_days_financing", f"The title evidence deadline is recorded as {title_days} days before closing, the "
             f"form's default for a {'cash' if financed else 'financed'} deal, but this deal is "
             f"{FINANCING.get(c.get('financing', 'conventional'), 'financed') if financed else 'cash'}. Confirm the "
             "number written in Para. 9(c) and the financing"
             + (f". With the form's {15 if financed else 5} days: {dated}" if dated else ""))
    # TL-240: Para. 10(d)'s flood window shows only for a Special Flood Hazard Area zone. When the zone isn't recorded at
    # all, the row is left out and the agent is asked, with the date it would have
    if not c.get("flood_zone") and not c.get("flood_elevation_days"):
        found = [x for x in alt("flood_zone_unknown", "the property is in a Special Flood Hazard Area (a zone starting "
                                "with A or V)", {"flood_zone": "A"}, ("flood_elevation",)) if x["date_display"] != "Pending"]
        note("flood_zone_unknown", "The flood zone isn't recorded, so Para. 10(d)'s flood elevation window is left out"
             + (f" (it would end {found[0]['date_display']}, 20 days after the Effective Date)" if found else "")
             + ". Is the property in a Special Flood Hazard Area (a zone starting with A or V)? Check the seller's flood "
             "or property disclosure, then set flood_zone (\"none\" when it isn't) and re-run")
    # TL-239: Rider H's row is generic ("homeowner's, flood, or both as checked") until the checked boxes are recorded
    if (("H" in codes or c.get("insurance_date") or c.get("insurance_days") or c.get("insurance_days_before"))
            and insurance_coverage(c) is None):
        note("rider_h_boxes", "Rider H: which boxes are checked isn't recorded, so the report's insurance row reads "
             "\"homeowner's, flood, or both as checked\". Which are checked, (a) homeowner's, (b) flood or both? Set "
             "insurance_coverage and re-run")
    # TL-258: Rider H's blank is a date ("by ____"); its default counts both ways (30 days after the Effective Date or 10
    # days before Closing), so days written in don't say which way they count. The timeline counts from the Effective
    # Date; the note gives the other reading's date and the one that is safe for the agent's side
    days = c.get("insurance_days")
    keys = [r["key"] for r in current if r["key"] in ("insurance", "flood_insurance") and r.get("basis") == "after"]
    used = next((r["when"] for r in current if r["key"] in keys and r["when"]), None)
    closing = next((r["when"] for r in current if r["key"] == "closing" and r["when"]), None)
    if days and used and closing and not c.get("insurance_date"):
        other = backward(closing.date(), int(days), rules)[0].date()
        if other != used.date():
            alt("insurance_days_reading", f"the {days} days count back from Closing",
                {"insurance_days": None, "insurance_days_before": days}, tuple(keys))
            early, late = min(other, used.date()), max(other, used.date())
            safe = (f"To be safe, the buyer should deliver any cancellation by {early:%a %b %-d}" if side == "buyer" else
                    f"The buyer could argue for the later date, so treat the buyer's right as open through {late:%a %b %-d}")
            note("insurance_days_reading", f"Rider H: the insurance deadline is written as {days} days, but the rider's "
                 f"blank asks for a date and doesn't say which way days count. The timeline counts {days} days after the "
                 f"Effective Date ({used:%a %b %-d}); counted back from Closing, it ends {other:%a %b %-d}. {safe}. "
                 "Confirm the reading; if it counts from Closing, set insurance_days_before instead and re-run", keys)
    # TL-242: Rider P is for homes built before 1978; year_built and the rider should agree, like any other rider field
    year = c.get("year_built")
    if "P" in codes and not year:
        note("rider_p_year_built", "The Lead-Based Paint rider (P) is attached but the year built isn't recorded: the "
             "rider is for homes built before 1978. Confirm the year built and set year_built")
    elif "P" in codes and int(year) >= 1978:
        note("rider_p_year_built", f"The Lead-Based Paint rider (P) is attached but the home was built in {year}; the "
             "rider is for homes built before 1978. Confirm the year built")
    elif "P" not in codes and year and int(year) < 1978:
        note("year_built_without_rider_p", f"The home was built in {year}, before 1978, but the Lead-Based Paint rider (P) "
             "isn't in riders: federal law requires the disclosure, and the timeline dates the 10-day risk assessment "
             "as if it were attached. Confirm whether Rider P is attached")
    # TL-209: Para. 6(b) is usually checked for the seller's stay under Rider U, which isn't a tenancy: its 5-day lease
    # disclosure and the buyer's 5-day cancel window aren't dated then
    if "U" in codes and not c.get("tenants"):
        note("rider_u_6b", "Rider U: Para. 6(b)'s 5-day lease disclosure and the buyer's 5-day cancel window after it "
             "aren't dated, because the seller's stay after closing isn't a tenancy. If 6(b) was also checked for a "
             "tenant, set tenants and re-run")
    # TL-210: Rider GG's cancel window runs from the end of the Time Period as extended past a weekend or holiday; the
    # rider could be read to count from the unextended day
    rows = {r["key"]: r for r in current}
    agreement, cancel = rows.get("compensation_agreement"), rows.get("compensation_cancel")
    if agreement and cancel and agreement["when"] and cancel["when"] and not agreement.get("from_approval"):
        day = eff + timedelta(days=int(agreement["days"]))
        if agreement["when"].date() != day:
            other = forward(day, int(cancel["days"]), rules)[0]
            if other.date() != cancel["when"].date():
                # TL-235: one reading used plus the date that is safe for the agent's side, never two dates side by side
                safe = (f"To be safe, the buyer should deliver any cancellation by {other:%a %b %-d}, the earlier "
                        f"reading (counted from {day:%a %b %-d})" if side == "buyer" else
                        f"The buyer could argue for the later date, so treat the buyer's right as open through "
                        f"{cancel['when']:%a %b %-d}")
                note("gg_rolled_start", f"Rider GG: the buyer's cancel window ends {cancel['when']:%a %b %-d}, counted from "
                     f"the agreement deadline as extended ({day:%a %b %-d} to {agreement['when']:%a %b %-d}); the timeline "
                     f"uses this reading. {safe}", GG_KEYS)


# TL-214: the deal-file field an extension changes, and the row it dates (counted from the Effective Date)
EXTENDED_ROWS = {"inspection_days": "inspection", "loan_approval_days": "loan_approval", "loan_application_days": "loan_app",
                 "deposit_days": "deposit", "additional_deposit_days": "add_deposit", "lead_paint_days": "lead_paint",
                 "flood_elevation_days": "flood_elevation", "mold_days": "mold", "drywall_days": "drywall",
                 "insurance_days": "insurance", "appraisal_days": "appraisal_due",
                 "short_sale_approval_days": "short_sale_approval", "compensation_agreement_days": "compensation_agreement",
                 "pre_closing_agreement_days": "pre_closing_agreement"}


def extension_readings(history, current, rules, eff, frbar):
    """TL-214: (key, note, facts) for each amendment that lengthens a period whose original end had rolled past a weekend or
    holiday. The timeline uses the safe reading (the new day count from the Effective Date, rolled once: EA-4 in
    frbar-addenda.md); adding the extra days to the rolled end gives a later date, which the note gives with both."""
    rows = {r["key"]: r for r in current}
    out = []
    overrides = {}
    for i, h in enumerate(history, 1):
        overrides.update(h.get("date_overrides") or {})
        for field, new in (h.get("changes") or {}).items():
            key = EXTENDED_ROWS.get(field)
            r = rows.get(key)
            old = h["before"].get(field)
            old = FORM_DEFAULTS.get(field) if old is None and frbar else old
            if (not r or r["basis"] != "after" or r.get("from_key") or r.get("receipt_date") or r.get("from_approval")
                    or r.get("business") or key in overrides or not isinstance(new, int) or not isinstance(old, int)
                    or new <= old):
                continue
            old_end = forward(eff, old, rules)[0]
            if old_end.date() == eff + timedelta(days=old):  # the original end didn't roll: both readings agree
                continue
            safe, later = forward(eff, new, rules)[0], forward(old_end.date(), new - old, rules)[0]
            if later.date() == safe.date():
                continue
            out.append((f"extension_reading:{key}",
                        f"{_amendment_name(h, i)} moves the {_field_label(field)} from {old} to {new} days after the Effective Date: it ends "
                        f"{safe:%a %b %-d} (the safe reading, used). If the amendment adds the {new - old} days to the "
                        f"original end as extended ({old_end:%a %b %-d}) instead, it ends {later:%a %b %-d}. Confirm "
                        "which reading the parties intend",
                        {"key": key, "label": r["label"], "safe": safe, "later": later, "amendment": _amendment_name(h, i),
                         "days": new - old}))
    return out


# TL-230: every contract field the script or contract_forms reads (deal-file.md, frbar.md). Anything else is most likely
# a typo that would drop a deadline silently, so it comes back as a warning to fix.
KNOWN_CONTRACT_KEYS = frozenset("""
    form_family form contract_form contract_name blanks form_revision form_revision_source effective_date effective_date_source
    closing_date closing_time closing_source possession_date possession_time possession_note possession_source
    property buyer seller price escrow_agent deposit_amount deposit_amount_str deposit_days additional_deposit_amount
    additional_deposit_amount_str additional_deposit_days loan_amount other_amount balance_to_close preapproval_amount
    preapproval_price preapproval_expires financing loan_application_days loan_approval_days date_overrides riders
    counter_chain title_by title_evidence_days_before title_commitment_received title_defect_notice survey_days_before
    survey_received seller_has_title_evidence seller_has_survey inspection_days inspection_walkaway repair_limits
    repair_notice_delivered repair_estimates_received open_permits walkthrough_days_before flood_zone flood_elevation_days
    tenants leases_received fincen_report insurance_bound_days_before cd_days_before condo condo_docs_received
    condo_docs_before_contract developer_sale rofr rofr_days association_approval association_apply_days
    association_approval_days_before hoa hoa_docs_received hoa_disclosure_before_contract appraisal_received
    appraisal_repairs_notice_received seller_repair_election_received appraisal_date appraisal_days
    short_sale_application_days short_sale_approval_days short_sale_approval_seller_received short_sale_approval_received
    short_sale_closing_days short_sale_backup insurance_date insurance_days insurance_days_before insurance_flood flood_insurance_date
    insurance_homeowners insurance_coverage mold_days drywall_days drywall_waived cccl_requested year_built lead_paint_days lbp_waived
    rezoning_date pre_closing_agreement_days post_closing_agreement_days_before seller_occupancy_days
    sale_contingency_date backup_notice_date kickout_notice_received seller_attorney_date buyer_attorney_date
    management_agreements_received compensation_agreement_days
""".split())


def unknown_key_warnings(deal):
    """TL-230: (key, text) naming contract fields (and amendment changes) the script doesn't read."""
    out = []
    places = [("contract", deal.get("contract") or {})] + [
        (f"amendments[{i}].changes", a.get("changes") or {}) for i, a in enumerate(deal.get("amendments") or [])
        if isinstance(a, dict)]
    for where, fields in places:
        bad = sorted(k for k in fields if k not in KNOWN_CONTRACT_KEYS)
        if bad:
            out.append(("unknown_key", f"{where} has {', '.join(map(repr, bad))}, which the script doesn't read (a typo "
                        "drops a deadline without a word). Fix the field name from references/deal-file.md or "
                        "references/frbar.md, or remove it, and re-run"))
    return out


def analyze(deal, side=None):
    """Everything the markdown template and the PDF need, as plain JSON-ready data."""
    contract = deal.get("contract") or {}
    if not contract.get("effective_date"):
        raise DealError("contract.effective_date is required. The Effective Date is the date the last party signed or "
                        "initialed and delivered the final counteroffer or acceptance.")
    for field in ("contract", "deadlines", "amendments", "completed", "report_date"):
        _check_dates(deal.get(field), field)
    price = _price(contract.get("price"))
    report = _report_date(deal.get("report_date"))
    today = _d(report["date"])
    form = cf.normalize(contract.get("contract_form"))
    family = contract.get("form_family")
    frbar = family == "frbar" or (family is None and form in cf.FRBAR)
    if frbar and form not in cf.FRBAR:
        raise DealError("An FR/BAR contract needs contract_form: as_is or standard. Read the form's title (\"AS IS Residential "
                        "Contract for Sale and Purchase\" or \"Residential Contract for Sale and Purchase\"): the two have "
                        "different inspection and repair deadlines.")
    contract = {**contract, "contract_form": form}
    if not frbar and not deal.get("deadlines"):
        raise DealError("This contract isn't FR/BAR, so its deadlines have to be listed in the deal file's deadlines.")
    rules, market = load_rules(deal, frbar)
    if frbar:
        _check_riders(contract)

    original = compute(copy.deepcopy(contract), deal.get("deadlines") or [], rules, frbar)
    current_contract, history = apply_amendments(contract, deal.get("amendments"))
    current_contract["contract_form"] = cf.normalize(current_contract.get("contract_form"))
    if frbar and current_contract["contract_form"] not in cf.FRBAR:
        raise DealError("An amendment changes contract_form: use as_is or standard.")
    if frbar:
        _check_riders(current_contract)
    current = compute(current_contract, deal.get("deadlines") or [], rules, frbar)
    was = {r["key"]: r["when"] for r in original}
    eff = _d(current_contract["effective_date"])

    closing_dt = next((r["when"] for r in current if r["key"] == "closing" and r["when"]), None)
    completed = _completed(deal, {r["key"] for r in current})
    if _d(current_contract.get("short_sale_approval_received")) and "short_sale_approval" in {r["key"] for r in current}:
        completed.setdefault("short_sale_approval", _d(current_contract["short_sale_approval_received"]))
    rows = []
    for r in current:
        moved = was.get(r["key"]) if was.get(r["key"]) != r["when"] else None
        done_on = completed.get(r["key"])
        # TL-104: a deadline before the report date that isn't recorded as done is shown to confirm, never as due
        past = bool(r["when"] and not done_on and r["when"].date() < today)
        rows.append({
            "key": r["key"], "label": r["label"], "short": r.get("short") or r["label"], "party": r["party"],
            # TL-256: a lender's target is an estimate, never a starred contract deadline on the client's report
            "critical": bool(r.get("critical")) and not r.get("lender"), "contingency": bool(r.get("contingency")),
            "when": r["when"].strftime("%Y-%m-%d %H:%M") if r["when"] else None,
            "display": _row_display(r, r["when"], rules, closing_dt), "date_display": _fmt(r["when"], rules, False),
            "day": (r["when"].date() - eff).days if r["when"] else None,
            "rule": r["rule"], "note": r.get("note", ""), "source": r.get("source", ""),
            "action": r.get("action", ""), "if_missed": r.get("if_missed", ""),
            "was": _row_display(r, moved, rules, closing_dt) if moved else None,
            "done": bool(done_on), "done_display": f"Done {done_on:%b %-d}" if done_on else None,
            "past": past, "past_display": "Past, Confirm" if past else None,
            "waits_on_approval": bool(r.get("from_approval") and not r["when"]),
            "no_time": bool(r.get("no_time")), "by_closing": bool(r.get("by_closing")),
            "lender": bool(r.get("lender")),  # a lender's target or rule, not a contract deadline
            "broker": bool(r.get("broker")),  # TL-246: between the brokers (Rider GG), never the first deadline
        })

    side = (side or deal.get("side") or "buyer").lower()
    dated = [r for r in rows if r["when"]]
    closing_row = next((r for r in dated if r["key"] == "closing"), None)  # None: no closing date yet
    contingent = [r for r in dated if r["contingency"]]
    # Rider G before the approval: the buyer's contingencies haven't started, so none of the dated ones is "the end"
    waiting = [r for r in rows if r["waits_on_approval"] and r["contingency"]]
    firm = max(contingent, key=lambda r: r["when"]) if contingent and not waiting else None
    names = {r["key"]: r["label"] for r in rows}
    # TL-14: rights that outlast the main contingencies (association documents, title and survey notices, FHA/VA)
    open_rights = [r["short"] for r in rows if r["key"] in OPEN_RIGHT_KEYS
                   and (r["when"] is None or not firm or r["when"] > firm["when"])]
    if current_contract.get("financing") in ("fha", "va"):
        open_rights.append(f"{_loan_type(current_contract)} appraisal clause (to closing)")
    # TL-104, TL-204: the next deadline from the report date: the earliest open contract deadline marked critical, whoever
    # owes it (Buyer, Seller or Both), else the earliest open contract deadline. A lender's target (insurance bound, the
    # Closing Disclosure) is never it; done and past rows never are. TL-246: nor are Rider GG's rows, a matter between the
    # brokers that would otherwise lead the client's report. The loan application isn't critical (missing it by a day
    # costs no right by itself; Para. 8(b) asks for diligent effort), so an earlier one doesn't lead either.
    upcoming = [r for r in dated if not r["done"] and not r["past"] and not r["lender"] and not r["broker"]]
    first = next((r for r in upcoming if r["critical"]), None) or next(iter(upcoming), None)

    # flags print on the report as "Check:" lines; agent_notes stay in chat (defaults used, assumptions to confirm)
    flags = [_sentence(f) for f in deal.get("flags") or []]
    agent_notes = []  # the script's own; the agent's are merged in at the end without repeats
    # TEST-2: a stable key for each flag and note the script adds (flag_keys, note_keys), so tests and golden can
    # tell which one fired without matching the sentence; the printed text is unchanged
    flag_keys, note_keys = [], []
    warnings = unknown_key_warnings(deal)
    if_changed = []  # TL-241: the dates that apply if the answer to a note's question changes

    def flag(key, text):
        text = _sentence(text)  # TL-211: a Check line is a sentence, and the agent's own flag isn't printed twice
        if _norm(text) not in {_norm(f) for f in flags}:
            flags.append(text)
            flag_keys.append(key)

    about = {}  # TL-247: note key -> the deadline keys it covers, so an agent's note keyed to one of them is merged away

    def note(key, text, rows=()):
        about.setdefault(key, set()).update(rows)
        if ":" in key:  # "default:inspection", "blank:rezoning", "extension_reading:inspection"
            about[key].add(key.split(":", 1)[1])
        if key in note_keys:  # TL-247: one line per key; a second note on the same key joins the first
            i = note_keys.index(key)
            agent_notes[i] = _sentence(agent_notes[i]) + " " + text
            return
        agent_notes.append(text)
        note_keys.append(key)
    # TL-201: the note quotes "the footer reads" only when the revision was read from the footer
    from_footer = str(current_contract.get("form_revision_source") or "").strip().lower() == "footer"
    sup = cf.support([current_contract["contract_form"] if frbar else cf.OTHER],
                     [(current_contract["contract_form"], current_contract.get("form_revision"), from_footer)]
                     if frbar else [])
    # chat_notes (the best-effort and revision notes) stay in chat_notes only: agent_notes can reach a template (TL-107)
    if rules.get("_tz_note"):  # TL-108: a question for the agent, not a line for the client
        note("time_zone_split", rules["_tz_note"])
    if frbar:  # TL-101: a rider name that isn't a CR-7 rider adds no dates, so say so rather than drop it silently
        unread = cf.rider_codes(current_contract.get("riders"))[1]
        if unread:
            note("rider_not_read", f"Not read as a CR-7 rider: {', '.join(map(str, unread))}. Its dates aren't in the timeline: "
                               "record the rider by its letter (\"G\") or add its dates to deadlines, and re-run")
    # TL-227: the end-of-day question says "no time of day" only for the dates that show none; when every deadline
    # sets its own time (a period that ends at 5:00 PM), the contract's end of day changes nothing and isn't asked
    unknown = [k for k in rules.get("_unknown") or []
               if k != "end_time" or any(r.get("no_time") for r in current if r["when"])]
    timed = any(r["when"] and not r.get("no_time") and r["basis"] not in ("closing", "possession", "pending_closing")
                for r in current)
    if unknown:  # TL-121: asked, never invented
        note("rules_unknown", "The contract's time rules as recorded don't say " + "; ".join(
            "when a day ends (dates without their own time show the day only)" if k == "end_time" and timed else
            UNKNOWN_TEXT[k] for k in unknown) + ". Ask the agent what the contract says, add each to rules and re-run")
    if eff > today and not deal.get("what_if"):  # TL-119
        # TL-243: what_if only matters for a file (the PDF or calendar). Without a closing date there's no report to label
        # (a quick question), so the note doesn't suggest it
        reportable = bool(closing_dt) or (frbar and "G" in cf.rider_codes(current_contract.get("riders"))[0])
        note("effective_after_report", f"The Effective Date ({eff:%b %-d, %Y}) is after the report date ({today:%b %-d, %Y}): confirm the "
                           "contract is signed and delivered" + (". For a hypothetical timeline delivered as a PDF or "
                                                                 "calendar, set what_if so they say What-If"
                                                                 if reportable else ""))
    for i, h in enumerate(history, 1):
        if _d(h.get("date")) and _d(h["date"]) > today:
            note("amendment_after_report", f"{_amendment_name(h, i)} ({h.get('description') or 'no description'}) is dated "
                               f"{_date_text(h['date'])}, after the report date: confirm it was signed before relying on it")
    past = [r for r in rows if r["past"]]
    if past:  # TL-104
        note("past_not_done", "Before the report date and not recorded as done: " + ", ".join(
            f"{r['label']} ({r['date_display']})" for r in past) + ". Confirm each was met and record it in completed "
            "(the report shows them as Past, Confirm and the calendar leaves them out)", [r["key"] for r in past])
    waiting_on = [r for r in current if r["basis"] == "event" and not r["when"]]
    if waiting_on:  # FH-102: the report says "dated once the receipt is recorded"; the instruction is the agent's
        note("waiting_on_receipt", "Waiting on a receipt date: " + ", ".join(r["label"] for r in waiting_on)
             + ". Record each date when it happens and re-run", [r["key"] for r in waiting_on])
    for r in current:
        if r.get("agent_note"):
            note("blank:" + r["key"], r["agent_note"])
    if closing_row and closing_row["note"]:
        flag("closing_note", closing_row["note"][:1].upper() + closing_row["note"][1:])
    if frbar and (current_contract.get("financing") in ("fha", "va") or "E" in cf.rider_codes(current_contract.get("riders"))[0]):
        loan = _loan_type(current_contract)
        value = {"VA": "the VA's reasonable value", "FHA": "the FHA appraisal"}.get(loan, "the appraisal")
        flag("fha_va_appraisal", f"FHA/VA rider{f' ({loan} loan)' if loan != 'FHA/VA' else ''}: the buyer isn't obligated "
                     f"to close if {value} comes in below the price, and that protection runs to closing. The buyer's choice "
                     "to go ahead anyway is due within 3 days after receiving the appraisal")
    if str(current_contract.get("association_approval")).lower() == "unknown":  # the rider's "is / is not" box left blank
        flag("assoc_box_blank", "The rider's association approval box is blank: these dates assume approval is required. Confirm with "
                     "the association")
        note("assoc_box_blank", "Association approval box blank on the rider (no default): assumed required; ask the listing agent "
                           "or the association")
    exp = current_contract.get("preapproval_expires")
    if exp and closing_row and _d(exp) < _d(closing_row["when"]):
        note("preapproval_expires", f"The buyer's pre-approval expires {_date_text(exp)}, before closing: ask the lender to extend or "
                           "update it")
    elif exp and not closing_row:  # TL-212: a short sale's closing waits for the approval; compare with its latest date
        ss_due = next((r for r in current if r["key"] == "short_sale_approval" and r["when"]), None)
        ss_days = int(current_contract.get("short_sale_closing_days") or 45)
        if ss_due and _d(exp) < ss_due["when"].date() + timedelta(days=ss_days):
            by = _d(exp) - timedelta(days=ss_days)
            note("preapproval_expires", f"The buyer's pre-approval expires {_date_text(exp)}. Closing is "
                 f"{_plural(ss_days, 'day')} after the buyer receives the short sale approval, so an approval received "
                 f"after {by:%b %-d, %Y} (the approval deadline is {ss_due['when']:%b %-d}) puts closing after the "
                 "expiry: ask the lender to extend or update it when the approval arrives")
    for key, text in money_check(current_contract, _price(current_contract.get("price"))):
        note(key, text)
    price_now = _price(current_contract.get("price"))
    limits = repair_limits(current_contract, price_now) if frbar else None
    if limits and limits["blank"]:  # TL-245: the dollars come from here, never worked out by hand
        names = [REPAIR_LIMIT_NAMES[k] for k in limits["blank"]]
        amount = f"${limits[limits['blank'][0]]:,.0f}"  # every blank limit is the same 1.5% of the price
        note("repair_limits_blank", (
            "Para. 9(a)'s repair limits are blank, so each is" if len(names) == 3 else
            f"Para. 9(a)'s {' and '.join(names)} Limit{'s are' if len(names) > 1 else ' is'} blank, so "
            f"{'each is' if len(names) > 1 else 'it is'}") + f" 1.5% of the ${price_now:,.0f} price ({amount}). Is that "
            "what the parties intended?")
    if frbar:
        def alt(note_key, condition, changes, keys):
            """TL-241: the rows `keys` if the answer to a note's question changes (a field set, or removed with None)."""
            c2 = copy.deepcopy(current_contract)
            for k, v in changes.items():
                if v is None:
                    c2.pop(k, None)
                else:
                    c2[k] = v
            try:
                rows2 = compute(c2, deal.get("deadlines") or [], rules, frbar)
            except (DealError, cf.FormError):
                return []
            cl = next((r["when"] for r in rows2 if r["key"] == "closing" and r["when"]), None)
            found = [{"key": r["key"], "label": r["label"], "display": _row_display(r, r["when"], rules, cl),
                      "date_display": _fmt(r["when"], rules, False)} for r in rows2 if r["key"] in keys]
            if_changed.append({"note_key": note_key, "if": condition, "rows": found})
            return found
        consistency_notes(current_contract, current, rules, eff, note, side, alt)
        done_keys = {r["key"] for r in rows if r["done"]}
        for key, text, x in extension_readings(history, current, rules, eff, frbar):
            note(key, text)
            # TL-248: the reading used has ended but the later one hasn't: the client sees it on the report too
            if x["key"] not in done_keys and x["safe"].date() < today <= x["later"].date():
                flag(f"extension_reading_open:{x['key']}",
                     f"{x['label']}: ended {x['safe']:%a %b %-d} on the reading used. If {x['amendment'][:1].lower()}"
                     f"{x['amendment'][1:]} adds the {_plural(x['days'], 'day')} to the original end as extended, it runs "
                     f"through {x['later']:%a %b %-d}. Confirm in writing which reading the parties intend")
    approval = next((r for r in dated if r["key"] == "loan_approval"), None)
    if closing_row and approval and _d(approval["when"]) > _d(closing_row["when"]):
        flag("loan_approval_after_closing", "Loan approval period ends after closing: extend closing or shorten the loan approval period in writing")
    elif closing_row and approval and _d(approval["when"]) > _d(closing_row["when"]) - timedelta(days=5):
        flag("loan_approval_near_closing", "Loan approval deadline is within 5 days of closing: little room if financing slips")
    if closing_row:
        late = [r["label"] for r in contingent if r["key"] != "loan_approval" and r["when"] > closing_row["when"]]
        if late:
            flag("after_closing", ", ".join(late) + " ends after closing: amend the dates in writing")
    # TL-226: a date counted back from closing that fell on a weekend or holiday extends to the next business day
    # (FR/BAR Standard F, read literally), closer to closing; the safe course is the business day before
    open_keys = {r["key"] for r in rows if not r["done"] and not r["past"]}
    rolled = [r for r in current if r.get("rolled_from") and r["key"] in open_keys and not r.get("lender")
              and not r.get("no_time")]
    if rolled and closing_dt:
        extra = rules["_extra_holidays"]
        groups = {}  # (safe date, date used): labels
        for r in rolled:
            groups.setdefault((dates.previous_business_day(r["rolled_from"], extra), r["when"].date()), []).append(r["label"])
        parts = [f"{' and '.join(labels) if len(labels) < 3 else ', '.join(labels[:-1]) + ' and ' + labels[-1]} by "
                 f"{safe:%a %b %-d}, not {used:%a %b %-d}" for (safe, used), labels in groups.items()]
        flag("before_closing_rolled", "Counted back from closing, a date on a weekend or holiday moves to the next "
             "business day, closer to closing. To be safe: " + "; ".join(parts))
    for r in current:
        if r.get("default"):
            note("default:" + r["key"], r["default"])
    short_sale = frbar and "G" in cf.rider_codes(current_contract.get("riders"))[0]
    approval = _d(current_contract.get("short_sale_approval_received")) if short_sale else None
    if short_sale:
        ss_row = next((r for r in current if r["key"] == "short_sale_approval" and r["when"]), None)
        if approval and ss_row:  # TL-103: an approval after the deadline, or after the contract expired, is flagged
            deadline = ss_row["when"].date()
            expires = forward(deadline, 30, rules)[0].date()
            if approval > expires:
                flag("short_sale_after_expiration", f"The short sale approval was received {approval:%b %-d, %Y}, after the Contract Expiration "
                             f"Date ({expires:%b %-d, %Y}): under Rider G, Para. 4 the contract ended automatically unless "
                             "the deadline was extended in writing. Confirm the contract is still in effect")
            elif approval > deadline:
                flag("short_sale_after_deadline", f"The short sale approval was received {approval:%b %-d, %Y}, after the Short Sale Approval "
                             f"Deadline ({deadline:%b %-d, %Y}): until then either party could cancel. Confirm neither "
                             "party canceled, or that the deadline was extended in writing")
        backup = str(current_contract.get("short_sale_backup") or "").strip().lower()  # TL-122: Rider G Para. 7
        note("short_sale_backup", "Rider G Para. 7(b): the seller may accept back-up contracts conditioned on this one failing"
                           if backup == "b" else
                           "Rider G Para. 7(a): the seller may not accept back-up offers while this contract is in effect"
                           + ("" if backup == "a" else " (neither box recorded: option (a) applies when neither is checked)"))
        if current_contract.get("closing_date") and not (current_contract.get("date_overrides") or {}).get("closing"):
            note("short_sale_closing_replaced", f"Para. 4 closing date ({_date_text(current_contract['closing_date'])}) is replaced by the "
                               "short sale rider: closing is "
                               f"{_plural(int(current_contract.get('short_sale_closing_days') or 45), 'day')} after the "
                               "buyer receives the approval (Rider G, Para. 6)")
        if not approval:
            note("short_sale_waiting", "Short sale approval not received yet: every period except the deposit and the short sale "
                               "rows waits for it (Rider G, Para. 5). Record short_sale_approval_received when it arrives "
                               "and re-run")
        if "GG" in cf.rider_codes(current_contract.get("riders"))[0]:
            note("short_sale_gg", "Rider GG is counted from the Effective Date, as its own words say; Rider G Para. 5 "
                               "(all other periods run from the approval) could be read to move it. Confirm which reading the parties use",
                 GG_KEYS)
    if not closing_row:
        # TL-243: only when a date waits for it; a one-deadline quick question has nothing counted back from closing
        if not short_sale and any(r["basis"] in ("before", "after_closing") for r in current):
            note("no_closing_date", "No closing date given: dates counted back from closing are left out")
    elif not current_contract.get("closing_time"):
        note("closing_time_assumed", f"Closing time isn't stated in the contract: used {_t(rules['closing_time']):%-I:%M %p}")
    if frbar and not current_contract.get("title_by"):
        note("title_by_unknown", "Who designates the closing agent (Para. 9(c)) isn't recorded: the title evidence row shows "
                           "the seller. Set title_by and re-run if the buyer designates")
    for n in market.notes:
        if ("MLS" not in n and "transfer tax" not in n  # costs don't matter here
                and not (deal.get("rules") and n.startswith("Nothing is built in for"))):  # the contract's rules are given
            note("market", n)
    topics = [r["default_topic"] for r in current if r.get("default") and r.get("default_topic")]
    topics += ["closing time"] if closing_row and not current_contract.get("closing_time") else []
    covered = set(note_keys).union(*about.values()) if about else set(note_keys)
    agent_notes, merged, joined = _dedupe_notes(
        list(deal.get("agent_notes") or []), agent_notes, topics, covered,
        {r["key"]: (r["label"], r["date_display"] if r["when"] else "not dated yet") for r in rows})

    return {
        "ok": True,
        "side": side,
        "sample": bool(deal.get("sample")),
        "client": deal.get("client") or side.title(),
        "property": contract.get("property", ""),
        "buyer": contract.get("buyer", ""), "seller": contract.get("seller", ""),
        "price": f"${price:,.0f}" if price else None,
        "what_if": bool(deal.get("what_if")),
        "time_zone": rules.get("_tz"),  # ET, CT or None (not known): the calendar's TZID
        "financing": FINANCING.get(contract.get("financing", ""), contract.get("financing") or None),
        "contract_label": _contract_label(current_contract) if frbar else contract.get("form") or "Contract",
        "escrow_agent": contract.get("escrow_agent"),
        "effective": {"date": str(eff), "display": f"{eff:%b %-d, %Y}", "short": f"{eff:%b %-d}",
                      "source": contract.get("effective_date_source") or ""},
        "closing": {"date": closing_row["when"][:10], "display": closing_row["display"], "day": closing_row["day"],
                    "long": f"{_d(closing_row['when']):%b %-d, %Y}", "short": f"{_d(closing_row['when']):%b %-d}"}
        if closing_row else None,
        "length_days": closing_row["day"] if closing_row else None,
        # TL-238: the closing first when it moved (the date the agent asks about), then the rest in date order
        "moved": [{"label": r["label"], "now": r["display"], "was": r["was"]}
                  for r in sorted((r for r in rows if r["was"]), key=lambda r: r["key"] != "closing")],
        # TL-113: rows an amendment dated for the first time (a short sale approval recorded by amendment)
        "newly_dated": [{"label": r["label"], "now": r["display"]} for r in rows
                        if r["when"] and history and was.get(r["key"]) is None],
        "contingencies_end": firm,
        "contingencies_waiting": [r["short"] for r in waiting],
        "short_sale": ({"approval_received": f"{approval:%b %-d, %Y}" if approval else None,
                        "closing_days": int(current_contract.get("short_sale_closing_days") or 45)} if short_sale else None),
        "open_rights": open_rights,
        "repair_limits": limits,  # TL-245: Para. 9(a) in dollars when the seller's repair obligation applies, else None
        "first_deadline": first,
        "report_date": report,
        "rows": dated,
        "pending": _pending_order([r for r in rows if not r["when"]], {r["key"]: r for r in current}),
        "history": [{**h, "date_display": _date_text(h.get("date")), "summary": "; ".join(
            [f"{_field_label(k)}: {_was(k, h['before'].get(k), frbar)} → {_field_value(k, v)}" for k, v in h["changes"].items()] +
            [f"{names.get(k, k.replace('_', ' '))} → {_value_text(v)}" for k, v in h["date_overrides"].items()])}
            for h in history],
        "flags": flags,
        "agent_notes": agent_notes,
        "warnings": [text for _, text in warnings],  # for Claude to fix in the deal file; never passed on
        "warning_keys": [key for key, _ in warnings],
        "flag_keys": flag_keys,  # one per flag the script added (the agent's own flags have none)
        "note_keys": note_keys,  # one per note the script added, before repeats of the agent's notes are dropped
        "merged_agent_notes": merged,  # TL-247: keys of the agent's notes a script note already covers (dropped)
        "joined_agent_notes": joined,  # TL-259: row keys of the agent's notes merged into one line with that row's date
        "if_changed": if_changed,  # TL-241: {note_key, if, rows}: the dates if the answer to that note's question changes
        **sup,
        "rules": {
            "family": "FR/BAR contract definitions" if frbar else "the contract's definitions",
            "lines": rules_text(rules, eff),
        },
    }


def _contract_label(c):
    """TL-216: the header chip for an FR/BAR contract, with every rider on both forms: "AS IS · Riders E, H, GG",
    "Standard + Right to Inspect Rider (L) · Riders F, H". The inspection rider already named in the label isn't
    listed twice."""
    t = cf.terms(c["contract_form"], c)
    others = sorted((x for x in t["riders"] if x != t["inspection_rider"]), key=list(cf.RIDERS).index)  # CR-7 order
    if not others:
        return t["label"]
    return f'{t["label"]} · Rider{"s" if len(others) > 1 else ""} {", ".join(others)}'


def _pending_order(pending, src):
    """Rows without a date: those counted from an event first (in contract order), then the ones counted back from
    closing (farthest first), the closing, and anything after it."""
    def key(ir):
        i, r = ir
        x = src[r["key"]]
        group = {"before": 2, "pending_closing": 3, "closing": 3, "after_closing": 4}.get(x["basis"], 0)
        return (group, -int(x.get("days") or 0) if group == 2 else i)
    return [r for _, r in sorted(enumerate(pending), key=key)]


def _report_date(v):
    """The "Prepared" date: the deal file's report_date (YYYY-MM-DD) when set, else today."""
    try:
        d = _d(v) or date.today()
    except ValueError:
        raise DealError(f"report_date is {v!r}: use YYYY-MM-DD.") from None
    return {"date": str(d), "long": f"{d:%B %-d, %Y}"}


def rules_text(rules, eff):
    """The time rules in plain sentences, for 'How the dates were computed'."""
    lines = [("Counting", f"{'Business' if rules['day_count'] == 'business' else 'Calendar'} days, starting the day after the Effective Date ({eff:%b %-d, %Y}).")]
    if int(rules["short_period_days"]) > 0 and rules["day_count"] != "business":
        lines.append(("Short Periods", f"Periods of {rules['short_period_days']} days or less skip Saturdays, Sundays and holidays."))
    unknown = rules.get("_unknown") or []
    to_confirm = "Not stated in the contract terms recorded (to confirm): "
    if rules["weekend_holiday_rollover"] == "next_business_day":
        lines.append(("Weekend / Holiday End", f"A period ending on a Saturday, Sunday or holiday extends to {_clock(_t(rules['rollover_time']))} the next business day."))
    elif "weekend_holiday_rollover" in unknown:
        lines.append(("Weekend / Holiday End", to_confirm + "a period ending on a weekend or holiday isn't moved."))
    end = _t(rules["end_time"])
    lines.append(("End of Day", to_confirm + "dates show the day only, with no time." if rules.get("_no_end_time") else
                  "A period runs to the end of its last day, where the property is located." if end == time(23, 59)
                  else f"Deadlines end at {end:%-I:%M %p} local time."))
    if "before_closing_rollover" in unknown:
        lines.append(("Before-Closing Dates", to_confirm + "a date counted back from closing isn't moved off a weekend or "
                                                           "holiday."))
    elif rules["before_closing_rollover"] == "previous_business_day":
        lines.append(("Before-Closing Dates", "Counted back from closing; a weekend or holiday moves the date earlier (conservative)."))
    elif rules["before_closing_rollover"] == "next_business_day":
        lines.append(("Before-Closing Dates", "Counted back from closing; a weekend or holiday extends to the next business day."))
    if rules.get("closing_rollover"):
        lines.append(("Closing Date", "A closing date on a weekend or holiday extends to the next business day."))
    if getattr(rules["_extra_holidays"], "base", "us_federal") == "none":
        lines.append(("Holidays", "Only the holidays the contract lists."))
    else:
        lines.append(("Holidays", (to_confirm if "holidays" in unknown else "") +
                      "National legal holidays (5 U.S.C. 6103), including observed dates" +
                      (", plus holidays listed in the contract." if rules["_extra_holidays"] else ".")))
    return [{"label": a, "text": b} for a, b in lines]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("deal")
    ap.add_argument("--side", choices=["buyer", "seller"])
    a = ap.parse_args(argv)
    with open(a.deal, encoding="utf-8") as f:
        deal = json.load(f)
    try:
        result = analyze(deal, a.side)
    except (DealError, profiles.ProfileError, ValueError, KeyError) as e:
        result = {"ok": False, "problems": [str(e)]}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
