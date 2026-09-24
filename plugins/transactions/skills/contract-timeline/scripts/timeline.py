"""Compute every contract deadline from a deal file.

    python3 scripts/timeline.py deal.json [--market market-profile.md] [--side buyer|seller]

Prints JSON with every date already formatted (for the markdown template and the PDF), or
{"ok": false, "problems": [...]} when something needed is missing. See references/deal-file.md.

Time rules (day counting, short periods, end of day, weekend/holiday rollover) come from the
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
from _shared import dates, profiles  # noqa: E402

RULE_KEYS = ("day_count", "short_period_days", "end_time", "weekend_holiday_rollover", "before_closing_rollover", "holidays")
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
    extra = {}
    if isinstance(rules["holidays"], list):
        extra = {_d(x): "Holiday (contract)" for x in rules["holidays"]}
    rules["_extra_holidays"] = extra
    return rules, market


# --- period math --------------------------------------------------------------

def forward(start, days, rules, business=False, end_time=None, rollover=True):
    """Deadline `days` after `start`. Returns (datetime, note).

    `end_time` and `rollover=False` are per-deadline exceptions (a TREC option period ends at 5:00 PM and
    isn't extended past a weekend or holiday)."""
    extra = rules["_extra_holidays"]
    notes = []
    if business or rules["day_count"] == "business" or days <= int(rules["short_period_days"]):
        d = dates.add_business_days(start, days, extra)
        if not business and rules["day_count"] != "business":
            notes.append(f"{days} days or less: weekends and holidays skipped")
        else:
            notes.append("business days")
    else:
        d = start + timedelta(days=days)
    if rollover and not dates.is_business_day(d, extra) and rules["weekend_holiday_rollover"] == "next_business_day":
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        d = dates.next_business_day(d, extra)
        rt = _t(rules["rollover_time"])
        notes.append(f"ends on a {why}: extended to {rt:%-I:%M %p} {d:%a %b %-d}")
        return datetime.combine(d, rt), "; ".join(notes)
    return datetime.combine(d, _t(end_time or rules["end_time"])), "; ".join(notes)


def backward(closing, days, rules, business=False):
    extra = rules["_extra_holidays"]
    t = _t(rules["before_closing_time"])
    if business:
        return datetime.combine(dates.add_business_days(closing, -days, extra), t), "business days (weekends and holidays skipped)"
    d = closing - timedelta(days=days)
    if not dates.is_business_day(d, extra) and rules["before_closing_rollover"] == "previous_business_day":
        why = dates.holiday_name(d, extra) or d.strftime("%A")
        d = dates.previous_business_day(d, extra)
        return datetime.combine(d, t), f"falls on a {why}: moved earlier to {d:%a %b %-d} (conservative)"
    return datetime.combine(d, t), ""


# --- FR/BAR deadline list ----------------------------------------------------

def frbar_deadlines(c):
    """Deadlines for an FR/BAR AS IS or Standard contract, from its fields (blank = form default)."""
    financed = c.get("financing", "conventional") != "cash"
    riders = [r.lower() for r in c.get("riders", [])]
    has = lambda words: any(re.search(rf"\b{words}\b", r) for r in riders)  # noqa: E731  whole words: "va" isn't "private"
    as_is = c.get("contract_form", "as_is") == "as_is"
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
    add(key="inspection", label="Inspection Period Ends" + (" (Right to Cancel)" if as_is else ""), short="Inspection Ends",
        basis="after", days=c.get("inspection_days", 15), source="Para. 12", party="Buyer", critical=True, contingency=True,
        action="Complete inspections (including 4-point and wind mitigation); deliver written cancellation notice before the deadline if not proceeding",
        if_missed="Right to cancel for inspection ends; deposit at risk")
    if not as_is:
        add(key="repair_notice", label="Repair Notice to Seller", short="Repair Notice", basis="after",
            days=c.get("inspection_days", 15), source="Para. 12 (Standard)", party="Buyer", critical=True,
            action="Deliver written notice of repairs within the repair limit", if_missed="Buyer accepts property condition")
    if financed and (c.get("appraisal_days") or has("appraisal") or has("fha") or has("va")):
        add(key="appraisal", label="Appraisal Contingency Ends", short="Appraisal Ends", basis="after",
            days=c.get("appraisal_days", 21), source="Appraisal Contingency / FHA-VA rider", party="Buyer", critical=True,
            contingency=True, action="Confirm the appraisal is in; cancel or renegotiate before the deadline if it's low",
            if_missed="Appraisal protection ends")
    if financed:
        add(key="loan_approval", label="Loan Approval Period Ends", short="Loan Approval", basis="after",
            days=c.get("loan_approval_days", 30), source="Para. 8(b)", party="Buyer", critical=True, contingency=True,
            action="Deliver written loan approval, or written notice to cancel or extend, before the deadline",
            if_missed="Buyer's right to cancel for financing ends; deposit at risk")
    if c.get("sale_contingency_days") or has("sale of buyer"):
        add(key="sale_contingency", label="Sale-of-Buyer's-Property Contingency Ends", short="Sale Contingency",
            basis="after", days=c.get("sale_contingency_days", 30), source="Sale of Buyer's Property rider", party="Buyer",
            critical=True, contingency=True, action="Buyer's property must be under contract or closed as the rider requires",
            if_missed="Per the rider, the contract may terminate")
    if c.get("lead_paint_days") or (c.get("year_built") and int(c["year_built"]) < 1978):
        add(key="lead_paint", label="Lead-Based Paint Risk Assessment Ends", short="Lead Paint", basis="after",
            days=c.get("lead_paint_days", 10), source="Lead-Based Paint disclosure", party="Buyer", critical=False,
            action="Complete any risk assessment and deliver notice if canceling", if_missed="Assessment right ends")
    if c.get("insurance_days") or has("insurance"):
        add(key="insurance", label="Insurance Contingency Ends", short="Insurance Ends", basis="after",
            days=c.get("insurance_days", c.get("inspection_days", 15)), source="Homeowners' / Flood Insurance rider",
            party="Buyer", critical=True, contingency=True, action="Bind coverage or cancel per the rider",
            if_missed="Insurance protection ends")
    if c.get("hoa") or has("association"):
        add(key="hoa_docs", label="HOA Documents / Approval", short="HOA Docs", basis="event",
            received=c.get("hoa_docs_received"), days=c.get("doc_review_days", 3), source="HOA rider; Ch. 720 F.S.",
            party="Seller", critical=False,
            action="Seller delivers HOA disclosure and documents; buyer applies for approval if required",
            if_missed="If documents arrive after the contract, the buyer may have a short cancellation window after receipt")
    if c.get("condo") or has("condominium"):
        add(key="condo_docs", label="Condominium Documents", short="Condo Docs", basis="event",
            received=c.get("condo_docs_received"), days=c.get("doc_review_days", 3), source="Condominium rider; Ch. 718 F.S.",
            party="Seller", critical=False,
            action="Seller delivers condo documents (including SIRS and milestone reports); note the buyer's review window after receipt",
            if_missed="Buyer's review window runs from receipt")
    add(key="title", label="Title Evidence Delivered", short="Title Evidence", basis="before", days=c.get("title_evidence_days_before", 5),
        source="Para. 9", party="Seller" if c.get("title_by", "seller") == "seller" else "Buyer", critical=False,
        action="Title commitment delivered; buyer reviews and gives notice of any title defects", if_missed="Closing may be delayed")
    add(key="survey", label="Survey Completed", short="Survey", basis="before", days=c.get("survey_days_before", 5),
        source="Para. 9", party="Buyer", critical=False, action="Order the survey early; review for encroachments",
        if_missed="Survey issues can't be raised in time")
    if financed:
        add(key="insurance_bound", label="Homeowners Insurance Bound", short="Insurance Bound", basis="before",
            days=c.get("insurance_bound_days_before", 7), source="Lender requirement", party="Buyer", critical=True,
            action="Bind the policy and send the declarations page to the lender", if_missed="Loan can't fund")
        add(key="clear_to_close", label="Clear to Close / Closing Disclosure", short="Closing Disclosure", basis="before",
            days=c.get("cd_days_before", 3), business=True, source="Lender (TRID 3-business-day rule)", party="Buyer",
            critical=True, action="Buyer receives and signs the Closing Disclosure at least 3 business days before closing",
            if_missed="Closing must move")
    add(key="walkthrough", label="Final Walk-Through", short="Walk-Through", basis="before", days=c.get("walkthrough_days_before", 1),
        source="Para. 13", party="Buyer", critical=False, action="Walk the property; confirm condition, repairs and included items",
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


def compute(c, extra_deadlines, rules, frbar):
    eff, closing = _d(c["effective_date"]), _d(c.get("closing_date"))
    items = (frbar_deadlines(c) if frbar else []) + [dict(x, contingency=x.get("contingency", False)) for x in extra_deadlines]
    if closing:
        items += closing_rows(c, frbar)
    extra = rules["_extra_holidays"]
    rows = []
    for x in items:
        r = dict(x)
        basis, days = x["basis"], x.get("days")
        if basis == "after":
            r["when"], r["note"] = forward(eff, int(days), rules, x.get("business", False), x.get("time"), x.get("rollover", True))
            r["rule"] = f"{_plural(int(days), 'day')} after Effective Date" + (" (business days)" if x.get("business") else "")
        elif basis == "before" and not closing:
            r["when"], r["rule"], r["note"] = None, f"{_plural(int(days), 'day')} before Closing", "Add the closing date and re-run"
        elif basis == "before":
            r["when"], r["note"] = backward(closing, int(days), rules, x.get("business", False))
            r["rule"] = f"{_plural(int(days), 'day')} before Closing" + (" (business days)" if x.get("business") else "")
        elif basis == "date":
            r["when"], r["rule"], r["note"] = _dt(x["date"], _t(x.get("time") or rules["end_time"])), "Specific date in contract", ""
        elif basis == "closing":
            r["when"] = datetime.combine(closing, _t(c.get("closing_time") or rules["closing_time"]))
            r["rule"], r["note"] = "Closing date in contract", ""
            if not dates.is_business_day(closing, extra):
                r["note"] = f"closing date falls on a {dates.holiday_name(closing, extra) or closing.strftime('%A')}: confirm the title company can close"
        elif basis == "possession":
            pd = _d(c.get("possession_date")) or closing
            r["when"] = datetime.combine(pd, _t(c.get("possession_time") or "17:00"))
            r["rule"], r["note"] = ("At closing" if pd == closing else "Per occupancy agreement"), ""
        elif basis == "event":
            received = _d(x.get("received"))
            if received:
                r["when"], r["note"] = forward(received, int(days or 3), rules)
                r["rule"] = f"{_plural(int(days or 3), 'day')} after documents received ({received:%b %-d})"
            else:
                r["when"], r["rule"], r["note"] = None, "Runs from receipt of documents", "Record the receipt date and re-run"
        else:
            raise DealError(f"Deadline {x.get('key')!r} has an unknown basis {basis!r} (use after, before, date or event).")
        override = (c.get("date_overrides") or {}).get(x["key"])
        if override:
            r["when"], r["rule"], r["note"] = _dt(override, _t(rules["end_time"])), "Specific date in contract / amendment", ""
        rows.append(r)
    rows.sort(key=lambda r: (r["when"] is None, r["when"] or datetime.max))
    return rows


def _fmt(dt, rules, with_time=True):
    if dt is None:
        return "On event"
    if not with_time:
        return f"{dt:%a %b %-d}"
    t = "11:59 PM" if dt.time() == time(23, 59) else f"{dt:%-I:%M %p}"
    return f"{dt:%a %b %-d} · {t}"


def analyze(deal, market_path=None, side=None):
    """Everything the markdown template and the PDF need, as plain JSON-ready data."""
    contract = deal.get("contract") or {}
    if not contract.get("effective_date"):
        raise DealError("contract.effective_date is required. The Effective Date is the date of the last signature "
                        "or initial on the final counteroffer or acceptance.")
    frbar = contract.get("form_family", "frbar" if contract.get("contract_form") else "other") == "frbar"
    if not frbar and not deal.get("deadlines"):
        raise DealError("This contract isn't FR/BAR, so its deadlines have to be listed in the deal file's deadlines.")
    rules, market = load_rules(deal, market_path, frbar)

    original = compute(copy.deepcopy(contract), deal.get("deadlines") or [], rules, frbar)
    current_contract, history = apply_amendments(contract, deal.get("amendments"))
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
    first = next((r for r in dated if r["party"] != "Both"), None)

    # flags print on the report as "Check:" lines; agent_notes stay in chat (defaults used, assumptions to confirm)
    flags = list(deal.get("flags") or [])
    agent_notes = list(deal.get("agent_notes") or [])
    if closing_row and closing_row["note"]:
        flags.append(closing_row["note"])
    approval = next((r for r in dated if r["key"] == "loan_approval"), None)
    if closing_row and approval and _d(approval["when"]) > _d(closing_row["when"]) - timedelta(days=5):
        flags.append("Loan approval deadline is within 5 days of closing: little room if financing slips")
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
        "contract_label": (("AS IS" if contract.get("contract_form", "as_is") == "as_is" else "Standard") if frbar
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
        "first_deadline": first,
        "rows": dated,
        "pending": [r for r in rows if not r["when"]],
        "history": [{**h, "summary": "; ".join(
            [f"{k.replace('_', ' ')}: {'blank' if h['before'].get(k) is None else h['before'].get(k)} → {v}"
             for k, v in h["changes"].items()] +
            [f"{k.replace('_', ' ')} → {v}" for k, v in h["date_overrides"].items()])} for h in history],
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
        lines.append(("Weekend / Holiday End", f"A period ending on a Saturday, Sunday or holiday extends to {_t(rules['rollover_time']):%-I:%M %p} the next business day."))
    lines.append(("End of Day", f"Otherwise deadlines end at {_t(rules['end_time']):%-I:%M %p} local time."))
    if rules["before_closing_rollover"] == "previous_business_day":
        lines.append(("Before-Closing Dates", "Counted back from closing; a weekend or holiday moves the date earlier (conservative)."))
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
