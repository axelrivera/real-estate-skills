"""Compute every contract deadline from a deal file.

    python3 scripts/timeline.py deal.json [--market market-profile.md] [--side buyer|seller]

Prints JSON with every date already formatted (for the markdown template and the PDF), or
{"ok": false, "problems": [...]} when something needed is missing. See references/deal-file.md.

Time rules (day counting, any short-period rule, end of day, weekend/holiday rollover) come from the
market profile's `contract` section (built in for Florida), overridden by the deal file's `rules`.
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
RULE_DEFAULTS = {"rollover_time": "17:00", "before_closing_time": "17:00", "closing_time": "10:00"}
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


def load_rules(deal, market_path=None, frbar=True):
    """Market profile `contract` rules for the deal's state/county, then the deal file's `rules`."""
    if not deal.get("state") and not market_path:
        raise DealError("The deal file needs the property's state (for example FL or TX): time rules and holidays "
                        "depend on it. Ask the agent; don't assume Florida.")
    market = profiles.load_market(market_path, state=deal.get("state"), county=deal.get("county"))
    mc = market.get("contract") or {}
    rules = {**RULE_DEFAULTS, **(mc if _form_covered(mc, deal, frbar) else {}), **(deal.get("rules") or {})}
    missing = [k for k in RULE_KEYS if rules.get(k) in (None, "")]
    if missing:
        raise DealError("The contract's time rules are missing: " + ", ".join(missing) +
                        ". Read them from the contract's definitions (how days are counted, when a day ends, "
                        "what happens on weekends and holidays) and add them to the deal file's rules.")
    hol = rules["holidays"]
    try:  # a preset (us_federal, tx_state), or the contract's own list of dates on top of the federal holidays
        extra = dates.Holidays({_d(x): "Holiday (contract)" for x in hol}) if isinstance(hol, list) else dates.Holidays(base=hol)
    except ValueError as e:
        raise DealError(str(e)) from None
    rules["_extra_holidays"] = extra
    rules["_tz"], rules["_tz_note"] = time_zone(deal, rules)
    return rules, market


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

    `end_time` and `rollover` are per-deadline exceptions to the contract's rules: `False` never extends (a TREC
    option period ends at 5:00 PM on its last day), `True` extends past a weekend or holiday even when the contract's
    general rule doesn't (TREC 20-19 extends only the earnest money date, Para. 5A); None follows the rules."""
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
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        d = dates.next_business_day(d, extra)
        rt = _t(rules["rollover_time"])
        notes.append(f"ends on a {why}: extended to {_clock(rt)} {d:%a %b %-d}")
        return datetime.combine(d, rt), "; ".join(notes)
    return datetime.combine(d, _t(end_time or rules["end_time"])), "; ".join(notes)


def backward(closing, days, rules, business=False):
    extra = rules["_extra_holidays"]
    t = _t(rules["before_closing_time"])
    if business == "trid":  # TL-17: Reg Z business days (Saturdays count; Sundays and federal holidays don't)
        return datetime.combine(dates.add_trid_days(closing, -days), t), "TRID business days (Saturdays count)"
    if business:
        return datetime.combine(dates.add_business_days(closing, -days, extra), t), "business days (weekends and holidays skipped)"
    d = closing - timedelta(days=days)
    if not dates.is_business_day(d, extra) and rules["before_closing_rollover"] == "previous_business_day":
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        d = dates.previous_business_day(d, extra)
        return datetime.combine(d, t), f"falls on a {why}: moved earlier to {d:%a %b %-d} (conservative)"
    if not dates.is_business_day(d, extra) and rules["before_closing_rollover"] == "next_business_day":
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        d = dates.next_business_day(d, extra)
        return datetime.combine(d, t), f"falls on a {why}: extended to {d:%a %b %-d}"
    return datetime.combine(d, t), ""


def _clock(t):
    return "the end of" if t == time(23, 59) else f"{t:%-I:%M %p}"


# --- FR/BAR deadline list ----------------------------------------------------

def frbar_deadlines(c):
    """Deadlines for an FR/BAR AS IS or Standard contract, from its fields (blank = form default).

    Checked against ASIS-7x Rev. 2/26 and its riders (see docs/audits/2026-09-23-verification.md). A row may
    carry `default` (a form default used for a blank, for agent_notes), `cap_at_closing` (a right that ends at
    closing) or `from_key` (counted from another row's date instead of the Effective Date).
    """
    financed = c.get("financing", "conventional") != "cash"
    riders = [r.lower() for r in c.get("riders", [])]
    has = lambda words: any(re.search(rf"\b{words}\b", r) for r in riders)  # noqa: E731  whole words: "va" isn't "private"
    fha_va = has("fha") or has("va")
    as_is = c["contract_form"] == cf.AS_IS  # set by analyze(); never defaulted, so AS IS and Standard rows never mix
    out = []

    def add(**k):
        k.setdefault("contingency", False)
        out.append(k)

    add(key="deposit", label="Initial Escrow Deposit Due", short="Deposit", basis="after", days=c.get("deposit_days", 3),
        source="Para. 2(a)", party="Buyer", critical=True,
        action=f"Deliver {c.get('deposit_amount_str') or 'the initial deposit'} to {c.get('escrow_agent') or 'the escrow agent'}; get a receipt",
        if_missed="Buyer in default; seller may cancel")
    if c.get("additional_deposit_amount_str"):
        add(key="add_deposit", label="Additional Deposit Due", short="Add'l Deposit", basis="after",
            days=c.get("additional_deposit_days", 10), source="Para. 2(b)", party="Buyer", critical=True,
            action=f"Deliver the additional deposit ({c['additional_deposit_amount_str']})",
            if_missed="Buyer in default; seller may cancel")
    if financed:
        add(key="loan_app", label="Loan Application", short="Loan App", basis="after", days=c.get("loan_application_days", 5),
            source="Para. 8(b)", party="Buyer", critical=False,
            action="Apply for the loan and provide the lender's written confirmation if requested",
            if_missed="Buyer may lose financing protections")
    if c.get("seller_has_survey"):
        add(key="seller_survey", label="Seller Delivers Existing Survey", short="Seller's Survey", basis="after", days=5,
            source="Para. 9(d)", party="Seller", critical=False,
            action="Seller gives a copy of the existing survey to the buyer and the closing agent",
            if_missed="Buyer may need a new survey sooner")
    if as_is:
        add(key="inspection", label="Inspection Period Ends (Right to Cancel)", short="Inspection Ends",
            basis="after", days=c.get("inspection_days", 15), source="Para. 12(a)", party="Buyer", critical=True, contingency=True,
            action="Complete inspections (including 4-point and wind mitigation); deliver written cancellation notice before the deadline if not proceeding",
            if_missed="Right to cancel for inspection ends; deposit at risk")
    else:
        # Standard: no right to cancel for inspection. The period is the deadline for the repair, WDO and permit
        # notices; the seller's repair obligation is capped by the repair limits in Para. 9(a) (1.5% each if blank).
        add(key="inspection", label="Inspection Period Ends (Repair Notices Due)", short="Repair Notices",
            basis="after", days=c.get("inspection_days", 15), source="Para. 12(a)-(d)", party="Buyer", critical=True,
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
            action="When repairs exceed a repair limit: the seller may pay the excess, or the buyer chooses repairs up to "
                   "the limit and takes the rest as is",
            if_missed="If neither party sends notice, either may terminate and the deposit is refunded")
        if c.get("open_permits"):
            add(key="permits_closed", label="Open Permits Closed", short="Permits Closed", basis="before", days=5,
                source="Para. 12(d)(ii)", party="Seller", critical=True,
                action="Seller closes the open or expired permits the buyer reported, up to the Permit Limit",
                if_missed="Closing may extend up to 10 days for final inspections, then either party may terminate")
    # The Appraisal Contingency rider has its own period. The FHA/VA rider has none: its protection runs to
    # closing, so it's a standing note (analyze), not a dated row.
    if financed and (has("appraisal") or (c.get("appraisal_days") and not fha_va)):
        add(key="appraisal", label="Appraisal Contingency Ends", short="Appraisal Ends", basis="after",
            days=c.get("appraisal_days", 21), source="Appraisal Contingency rider", party="Buyer", critical=True,
            contingency=True, action="Confirm the appraisal is in; cancel or renegotiate before the deadline if it's low",
            if_missed="Appraisal protection ends")
    if financed:
        add(key="loan_approval", label="Loan Approval Period Ends", short="Loan Approval", basis="after",
            days=c.get("loan_approval_days", 30), source="Para. 8(b)", party="Buyer", critical=True, contingency=True,
            action="Deliver written loan approval, or written notice to cancel or proceed, before the deadline",
            if_missed="Buyer's right to cancel for financing ends; deposit at risk")
        add(key="seller_terminate", label="Seller's Right to Terminate (No Loan Notice)", short="Seller May Terminate",
            basis="after", from_key="loan_approval", days=3, source="Para. 8(b)(v)", party="Seller", critical=False,
            action="If the buyer sent no loan approval or loan notice by the Loan Approval deadline, the seller may terminate "
                   "in writing within 3 days after it",
            if_missed="Seller's right ends; the buyer proceeds without the financing contingency")
    if c.get("sale_contingency_days") or has("sale of buyer"):
        add(key="sale_contingency", label="Sale-of-Buyer's-Property Contingency Ends", short="Sale Contingency",
            basis="after", days=c.get("sale_contingency_days", 30), source="Sale of Buyer's Property rider", party="Buyer",
            critical=True, contingency=True, action="Buyer's property must be under contract or closed as the rider requires",
            if_missed="Per the rider, the contract may terminate")
    if not c.get("lbp_waived") and (c.get("lead_paint_days") or (c.get("year_built") and int(c["year_built"]) < 1978)):
        add(key="lead_paint", label="Lead-Based Paint Risk Assessment Ends", short="Lead Paint", basis="after",
            days=c.get("lead_paint_days", 10), source="Lead-Based Paint rider", party="Buyer", critical=True, contingency=True,
            action="Complete any risk assessment and deliver notice if canceling", if_missed="Assessment and cancellation right ends")
    if c.get("flood_elevation_days") or re.match(r"^\s*[AV]", str(c.get("flood_zone") or ""), re.I):
        add(key="flood_elevation", label="Flood Elevation Cancellation Ends", short="Flood Elevation", basis="after",
            days=c.get("flood_elevation_days", 20), source="Para. 10(d)", party="Buyer", critical=True, contingency=True,
            action="Get the elevation certificate; if the home is below minimum flood elevation or can't get flood insurance, "
                   "deliver written cancellation notice", if_missed="Buyer accepts the existing elevation and flood zone")
    if c.get("insurance_days") or has("insurance"):
        add(key="insurance", label="Insurance Contingency Ends", short="Insurance Ends", basis="after",
            days=c.get("insurance_days", c.get("inspection_days", 15)), source="Homeowners' / Flood Insurance rider",
            party="Buyer", critical=True, contingency=True, action="Bind coverage or cancel per the rider",
            if_missed="Insurance protection ends")
    # Association document rights are the buyer's, run from receipt, and end at closing (CR-7x A, CR-7 B).
    if (c.get("hoa") or has("association")) and not c.get("hoa_disclosure_before_contract"):
        add(key="hoa_docs", label="HOA Disclosure Cancellation Window", short="HOA Disclosure", basis="event",
            received=c.get("hoa_docs_received"), what="the HOA disclosure summary", days=3, cap_at_closing=True, source="HOA rider; s. 720.401 F.S.",
            party="Buyer", critical=True, contingency=True,
            action="The HOA disclosure summary came after signing: the buyer may cancel in writing within 3 days after receiving it",
            if_missed="Cancellation right under s. 720.401 ends")
    if (c.get("condo") or has("condominium")) and not c.get("condo_docs_before_contract"):
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
            if_missed="The contract's approval contingency applies")
    title_days = c.get("title_evidence_days_before")
    add(key="title", label="Title Evidence Delivered", short="Title Evidence", basis="before",
        days=title_days if title_days is not None else (15 if financed else 5), source="Para. 9(c)",
        party="Seller" if c.get("title_by", "seller") == "seller" else "Buyer", critical=False,
        default=None if title_days is not None else
        f"Title evidence deadline blank: used the form default, {15 if financed else 5} days before closing"
        + ("" if financed else " (cash)"),
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
        add(key="insurance_bound", label="Homeowners Insurance Bound (Lender Target)", short="Insurance Bound", basis="before",
            days=c.get("insurance_bound_days_before", 7), source="Lender's usual target, not a contract date", party="Buyer",
            critical=False, action="Bind the policy and send the declarations page to the lender",
            if_missed="The lender may not be ready to fund on time")  # TL-25
        add(key="clear_to_close", label="Clear to Close / Closing Disclosure", short="Closing Disclosure", basis="before",
            days=c.get("cd_days_before", 3), business="trid", source="Lender (TRID 3-business-day rule)", party="Buyer",
            critical=True, action="Buyer receives and signs the Closing Disclosure at least 3 business days before closing",
            if_missed="Closing must move")
    add(key="walkthrough", label="Final Walk-Through", short="Walk-Through", basis="before", days=c.get("walkthrough_days_before", 1),
        cap_at_closing=True, source="Para. 12(b)" if as_is else "Para. 12(e)", party="Buyer", critical=False,
        action="Walk the property the day before closing or on closing day; confirm condition, repairs and included items",
        if_missed="Buyer loses the chance to verify condition")
    return out


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
        history.append({"date": a.get("date"), "description": a.get("description", ""),
                        "changes": a.get("changes", {}), "before": before, "date_overrides": a.get("date_overrides", {})})
    return c, history


OPEN_RIGHT_KEYS = ("hoa_docs", "condo_docs", "title_exam", "survey_notice")
FORM_DEFAULTS = {"inspection_days": 15, "loan_approval_days": 30, "deposit_days": 3, "additional_deposit_days": 10,
                 "appraisal_days": 21, "loan_application_days": 5, "sale_contingency_days": 30, "lead_paint_days": 10,
                 "flood_elevation_days": 20, "walkthrough_days_before": 1, "survey_days_before": 5}  # FR/BAR blanks


def _date_text(v):
    """'2026-11-24' -> 'Nov 24, 2026'; anything else as written."""
    try:
        d = _d(v)
    except ValueError:
        return str(v)
    return f"{d:%b %-d, %Y}" if d else ""


def _value_text(v):
    return _date_text(v) if isinstance(v, str) and re.match(r"^\d{4}-\d{2}-\d{2}", v) else str(v)


def _was(key, before, frbar):
    """TL-21: a blank that the form filled in reads as its value ("30 (form default)"), not "blank"."""
    if before is None:
        return f"{FORM_DEFAULTS[key]} (form default)" if frbar and key in FORM_DEFAULTS else "not set"
    return _value_text(before)


def _override(value, rules):
    """A deadline stated as a specific date. With a time it's kept as given; a date alone ends at the contract's
    end of day, and a weekend or holiday rolls forward like any period."""
    if len(str(value)) >= 16:
        return _dt(value, _t(rules["end_time"])), ""
    d, extra = _d(value), rules["_extra_holidays"]
    if not dates.is_business_day(d, extra) and rules["weekend_holiday_rollover"] == "next_business_day":
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        nd = dates.next_business_day(d, extra)
        return datetime.combine(nd, _t(rules["rollover_time"])), f"falls on a {why}: extended to {nd:%a %b %-d}"
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
    for x in extra_deadlines:
        if x.get("days") is not None and (not isinstance(x["days"], int) or x["days"] < 0):
            raise DealError(f"Deadline {x.get('key')!r} has days {x['days']!r}: use a whole number, 0 or more.")


def compute(c, extra_deadlines, rules, frbar):
    check_inputs(c, extra_deadlines)
    eff, extra = _d(c["effective_date"]), rules["_extra_holidays"]
    overrides = c.get("date_overrides") or {}
    closing_dt = None  # the closing everything counts back from: an override, then the contract date, rolled forward
    closing_note = ""
    raw = overrides.get("closing") or c.get("closing_date")
    if raw:
        closing = _d(raw)
        if not dates.is_business_day(closing, extra) and rules.get("closing_rollover") \
                and rules["weekend_holiday_rollover"] == "next_business_day":
            why = dates.holiday_name(closing, extra) or closing.strftime("%A")
            rolled = dates.next_business_day(closing, extra)
            closing_note = f"contract date {closing:%a %b %-d} is a {why}: closing extends to {rolled:%a %b %-d}"
            closing = rolled
        elif not dates.is_business_day(closing, extra):
            closing_note = (f"closing date falls on a {dates.holiday_name(closing, extra) or closing.strftime('%A')}: "
                            "confirm the title company can close")
        t = str(raw)[11:16] if len(str(raw)) >= 16 else (c.get("closing_time") or rules["closing_time"])
        closing_dt = datetime.combine(closing, _t(t))
    closing = closing_dt.date() if closing_dt else None

    items = (frbar_deadlines(c) if frbar else []) + [dict(x, contingency=x.get("contingency", False)) for x in extra_deadlines]
    if closing:
        items += closing_rows(c, frbar)
    rows, done = [], {}
    for x in items:
        r = dict(x)
        basis, days = x["basis"], x.get("days")
        if basis == "after" and x.get("from_key"):
            ref = done.get(x["from_key"])
            if not ref or not ref["when"]:
                continue
            r["when"], r["note"] = forward(ref["when"].date(), int(days), rules, x.get("business", False), x.get("time"),
                                           x.get("rollover"))
            r["rule"] = f"{_plural(int(days), 'day')} after {ref['short']}"
        elif basis == "after":
            start = _d(x.get("receipt_date")) or eff  # TL-15: a period that runs from someone's receipt (TREC title)
            r["when"], r["note"] = forward(start, int(days), rules, x.get("business", False), x.get("time"), x.get("rollover"))
            r["rule"] = (f"{_plural(int(days), 'day')} after " + (f"{x.get('what', 'receipt')} ({start:%b %-d})" if x.get("receipt_date")
                         else "Effective Date") + (" (business days)" if x.get("business") else ""))
        elif basis == "before" and not closing:
            r["when"], r["rule"], r["note"] = None, f"{_plural(int(days), 'day')} before Closing", "Add the closing date and re-run"
        elif basis == "before":
            r["when"], r["note"] = backward(closing, int(days), rules, x.get("business", False))
            r["rule"] = f"{_plural(int(days), 'day')} before Closing" + (" (TRID business days)" if x.get("business") == "trid"
                                                                       else " (business days)" if x.get("business") else "")
        elif basis == "date":
            r["when"], r["rule"], r["note"] = _dt(x["date"], _t(x.get("time") or rules["end_time"])), "Specific date in contract", ""
        elif basis == "closing":
            r["when"], r["rule"], r["note"] = closing_dt, "Closing date in contract", closing_note
        elif basis == "possession":
            pd = _d(c.get("possession_date")) or closing
            r["when"] = datetime.combine(pd, _t(c.get("possession_time") or "17:00"))
            r["rule"], r["note"] = ("At closing" if pd == closing else "Per occupancy agreement"), ""
        elif basis == "event":
            received = _d(x.get("received"))
            if received:
                start = max(received, eff) if x.get("start_after_effective") else received
                r["when"], r["note"] = forward(start, int(days or 3), rules, x.get("business", False))
                r["rule"] = (f"{_plural(int(days or 3), 'day')}{' (business days)' if x.get('business') else ''} "
                             f"after {x.get('what', 'documents')} received ({received:%b %-d})")
            else:
                r["when"], r["rule"] = None, f"Runs from receipt of {x.get('what', 'documents')}"
                r["note"] = "Record the receipt date and re-run"
        else:
            raise DealError(f"Deadline {x.get('key')!r} has an unknown basis {basis!r} (use after, before, date or event).")
        override = overrides.get(x["key"]) if x["key"] != "closing" else None
        if override:
            r["when"], r["note"] = _override(override, rules)
            r["rule"] = "Specific date in contract / amendment"
        if x.get("cap_at_closing") and r["when"] and closing_dt and r["when"] > closing_dt:
            r["when"] = closing_dt
            r["note"] = "; ".join(n for n in (r.get("note"), "the right ends at closing") if n)
        if x.get("default"):
            r["default"] = x["default"]
        rows.append(r)
        done[x["key"]] = r
    rows.sort(key=lambda r: (r["when"] is None, r["when"] or datetime.max))
    return rows


def _fmt(dt, rules, with_time=True):
    if dt is None:
        return "On event"
    if not with_time:
        return f"{dt:%a %b %-d}"
    t = "11:59 PM" if dt.time() == time(23, 59) else f"{dt:%-I:%M %p}"
    zone = rules.get("_tz")
    suffix = f" {zone}" if zone and zone != rules.get("time_zone", zone) else ""  # only when it differs from the usual
    return f"{dt:%a %b %-d} · {t}{suffix}"


def analyze(deal, market_path=None, side=None):
    """Everything the markdown template and the PDF need, as plain JSON-ready data."""
    contract = deal.get("contract") or {}
    if not contract.get("effective_date"):
        raise DealError("contract.effective_date is required. The Effective Date is the date the last party signed or "
                        "initialed and delivered the final counteroffer or acceptance.")
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
    rules, market = load_rules(deal, market_path, frbar)

    original = compute(copy.deepcopy(contract), deal.get("deadlines") or [], rules, frbar)
    current_contract, history = apply_amendments(contract, deal.get("amendments"))
    current_contract["contract_form"] = cf.normalize(current_contract.get("contract_form"))
    if frbar and current_contract["contract_form"] not in cf.FRBAR:
        raise DealError("An amendment changes contract_form: use as_is or standard.")
    current = compute(current_contract, deal.get("deadlines") or [], rules, frbar)
    was = {r["key"]: r["when"] for r in original}
    eff = _d(current_contract["effective_date"])

    rows = []
    for r in current:
        moved = was.get(r["key"]) if was.get(r["key"]) != r["when"] else None
        rows.append({
            "key": r["key"], "label": r["label"], "short": r.get("short") or r["label"], "party": r["party"],
            "critical": bool(r.get("critical")), "contingency": bool(r.get("contingency")),
            "when": r["when"].strftime("%Y-%m-%d %H:%M") if r["when"] else None,
            "display": _fmt(r["when"], rules), "date_display": _fmt(r["when"], rules, False),
            "day": (r["when"].date() - eff).days if r["when"] else None,
            "rule": r["rule"], "note": r.get("note", ""), "source": r.get("source", ""),
            "action": r.get("action", ""), "if_missed": r.get("if_missed", ""),
            "was": _fmt(moved, rules) if moved else None,
        })

    side = (side or deal.get("side") or "buyer").lower()
    dated = [r for r in rows if r["when"]]
    closing_row = next((r for r in rows if r["key"] == "closing"), None)  # None: a quick question without a closing date
    contingent = [r for r in dated if r["contingency"]]
    firm = max(contingent, key=lambda r: r["when"]) if contingent else None
    names = {r["key"]: r["label"] for r in rows}
    # TL-14: rights that outlast the main contingencies (association documents, title and survey notices, FHA/VA)
    open_rights = [r["short"] for r in rows if r["key"] in OPEN_RIGHT_KEYS
                   and (r["when"] is None or not firm or r["when"] > firm["when"])]
    if current_contract.get("financing") in ("fha", "va"):
        open_rights.append("FHA/VA appraisal clause (to closing)")
    first = next((r for r in dated if r["party"] != "Both"), None)

    # flags print on the report as "Check:" lines; agent_notes stay in chat (defaults used, assumptions to confirm)
    flags = list(deal.get("flags") or [])
    agent_notes = list(deal.get("agent_notes") or [])
    if rules.get("_tz_note"):
        flags.append(rules["_tz_note"])
    if closing_row and closing_row["note"]:
        flags.append(closing_row["note"][:1].upper() + closing_row["note"][1:])
    riders = " ".join(current_contract.get("riders") or []).lower()
    if frbar and current_contract.get("financing") in ("fha", "va") or re.search(r"\b(fha|va)\b", riders):
        flags.append("FHA/VA rider: the buyer isn't obligated to close if the appraisal comes in below the price, and that "
                     "protection runs to closing. The buyer's choice to go ahead anyway is due within 3 days after receiving "
                     "the appraisal")
    approval = next((r for r in dated if r["key"] == "loan_approval"), None)
    if closing_row and approval and _d(approval["when"]) > _d(closing_row["when"]):
        flags.append("Loan approval period ends after closing: extend closing or shorten the loan approval period in writing")
    elif closing_row and approval and _d(approval["when"]) > _d(closing_row["when"]) - timedelta(days=5):
        flags.append("Loan approval deadline is within 5 days of closing: little room if financing slips")
    if closing_row:
        late = [r["label"] for r in contingent if r["key"] != "loan_approval" and r["when"] > closing_row["when"]]
        if late:
            flags.append(", ".join(late) + " ends after closing: amend the dates in writing")
    agent_notes += [r["default"] for r in current if r.get("default")]
    if not closing_row:
        agent_notes.append("No closing date given: dates counted back from closing are left out")
    elif not current_contract.get("closing_time"):
        agent_notes.append(f"Closing time isn't stated in the contract: used {_t(rules['closing_time']):%-I:%M %p}")
    agent_notes += [n for n in market.notes if "MLS" not in n  # MLS assumptions don't matter for a timeline
                    and not (deal.get("rules") and n.startswith("No market profile"))]  # the contract's rules are given

    return {
        "ok": True,
        "side": side,
        "sample": bool(deal.get("sample")),
        "client": deal.get("client") or side.title(),
        "property": contract.get("property", ""),
        "buyer": contract.get("buyer", ""), "seller": contract.get("seller", ""),
        "price": f"${contract['price']:,.0f}" if contract.get("price") else None,
        "financing": FINANCING.get(contract.get("financing", ""), contract.get("financing") or None),
        "contract_label": (("AS IS" if contract["contract_form"] == cf.AS_IS else "Standard") if frbar
                           else contract.get("form") or "Contract"),
        "escrow_agent": contract.get("escrow_agent"),
        "effective": {"date": str(eff), "display": f"{eff:%b %-d, %Y}", "short": f"{eff:%b %-d}",
                      "source": contract.get("effective_date_source") or ""},
        "closing": {"date": closing_row["when"][:10], "display": closing_row["display"], "day": closing_row["day"],
                    "long": f"{_d(closing_row['when']):%b %-d, %Y}", "short": f"{_d(closing_row['when']):%b %-d}"}
        if closing_row else None,
        "length_days": closing_row["day"] if closing_row else None,
        "moved": [{"label": r["label"], "now": r["display"], "was": r["was"]} for r in rows if r["was"]],
        "contingencies_end": firm,
        "open_rights": open_rights,
        "first_deadline": first,
        "rows": dated,
        "pending": [r for r in rows if not r["when"]],
        "history": [{**h, "date_display": _date_text(h.get("date")), "summary": "; ".join(
            [f"{k.replace('_', ' ')}: {_was(k, h['before'].get(k), frbar)} → {_value_text(v)}" for k, v in h["changes"].items()] +
            [f"{names.get(k, k.replace('_', ' '))} → {_value_text(v)}" for k, v in h["date_overrides"].items()])}
            for h in history],
        "flags": flags,
        "agent_notes": agent_notes,
        "rules": {
            "family": "FR/BAR contract definitions" if frbar else "the contract's definitions",
            "lines": rules_text(rules, eff),
        },
    }


def rules_text(rules, eff):
    """The time rules in plain sentences, for 'How the dates were computed'."""
    lines = [("Counting", f"{'Business' if rules['day_count'] == 'business' else 'Calendar'} days, starting the day after the Effective Date ({eff:%b %-d, %Y}).")]
    if int(rules["short_period_days"]) > 0 and rules["day_count"] != "business":
        lines.append(("Short Periods", f"Periods of {rules['short_period_days']} days or less skip Saturdays, Sundays and holidays."))
    if rules["weekend_holiday_rollover"] == "next_business_day":
        lines.append(("Weekend / Holiday End", f"A period ending on a Saturday, Sunday or holiday extends to {_clock(_t(rules['rollover_time']))} the next business day."))
    end = _t(rules["end_time"])
    lines.append(("End of Day", "Otherwise a period runs to the end of its last day, where the property is located." if end == time(23, 59)
                  else f"Otherwise deadlines end at {end:%-I:%M %p} local time."))
    if rules["before_closing_rollover"] == "previous_business_day":
        lines.append(("Before-Closing Dates", "Counted back from closing; a weekend or holiday moves the date earlier (conservative)."))
    elif rules["before_closing_rollover"] == "next_business_day":
        lines.append(("Before-Closing Dates", "Counted back from closing; a weekend or holiday extends to the next business day."))
    if rules.get("closing_rollover"):
        lines.append(("Closing Date", "A closing date on a weekend or holiday extends to the next business day."))
    lines.append(("Holidays", "National legal holidays (5 U.S.C. 6103), including observed dates" +
                  (", plus holidays listed in the contract." if rules["_extra_holidays"] else ".")))
    return [{"label": a, "text": b} for a, b in lines]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("deal")
    ap.add_argument("--market", help="market profile (time rules); built in for Florida")
    ap.add_argument("--side", choices=["buyer", "seller"])
    a = ap.parse_args(argv)
    with open(a.deal, encoding="utf-8") as f:
        deal = json.load(f)
    try:
        result = analyze(deal, a.market, a.side)
    except (DealError, profiles.ProfileError, ValueError, KeyError) as e:
        result = {"ok": False, "problems": [str(e)]}
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
