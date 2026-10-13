"""Compute the buyer CMA's document model from report.json and the MLS export: every figure, sentence and row the PDF
and the chat summary show.

    python3 scripts/compute.py report.json [--out DIR] [--mls NAME]

Prints JSON: the supported range and where asking sits against it, the listing history counted from its events, the
comps (each card's adjustments itemized and summed), the market table from the export, the taxes and payment tables
(each a finance.Ledger, so every column adds up), page 1's tiles and cost rows, the notes (one notes.Notes registry,
each said once), the handoff and `warnings` to fix. Every figure is formatted once with fmt; every sentence that states
a count, price, date or comparison is a template in assets/labels.json. What report.json writes is judgment (why this
range, what the history adds up to, watch items, questions) and is refused when it carries a figure (prose.figures) or,
in the value narrative, offer advice (VALUE_ONLY): the report is an objective analysis of value, and the offer is the
buyer offer strategy's.

With only `subject`, `comps` (and `history`) in report.json (no bottom_line or costs yet), it prints the adjusted comps
alone: the median, the spread, the outlier warnings and the supported range, to answer a gut check from. Also writes <address>.buyer.cma.json (the CMA handoff the offer skills read) next to report.json, in the
working folder, never the outputs. render.py places this same model; it never recomputes. The input is never changed.
"""
import argparse
import copy
import json
import math
import os
import re
import statistics
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import cma, finance, fmt, handoff, mls, notes, profiles, prose  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "labels.json")
with open(LABELS_PATH, encoding="utf-8") as _f:
    L = json.load(_f)
L.pop("_prose", None)

money = fmt.money
CASH_TIGHT = 0.05  # CMA-217: cash to close within 5% of the buyer's cash leaves no room for a surprise
REPLY_KINDS = ("assumption", "estimate", "chat_only")  # the reply's assumption lines; the rest are the sheet's notes


class ReportError(ValueError):
    """Something report.json needs; the message is written for the agent."""


def t(key, **kw):
    """A labels.json template, filled."""
    return fmt.fill(L[key], **kw)


def labels(key, **kw):
    """cma.py's label lookup (a callable), for the shared chart and caption code."""
    return t(key, **kw)


def _frac(block, key, where, default=None):
    """A `*_pct` value from report.json as a fraction (0.05 = 5%), or `default` when not given."""
    try:
        return finance.fraction(block.get(key), f"{where}.{key}", default)
    except ValueError as e:
        raise ReportError(str(e)) from e


def _require(R, *paths):
    for path in paths:
        node = R
        for part in path.split("."):
            if not isinstance(node, dict) or node.get(part) in (None, ""):
                raise ReportError(f"report.json is missing {path}.")
            node = node[part]


def stop_message(errors):
    return (f"report.json has {len(errors)} thing{'s' if len(errors) > 1 else ''} to fix before the files are built:\n"
            + "\n".join("- " + e for e in errors))


def plural(n, one, many):
    """'4 price cuts', '1 price cut', 'no price cuts' (labels.json words)."""
    if not n:
        return t("p_none", what=L[many])
    return f"{fmt.num(n)} {L[one] if n == 1 else L[many]}"


def number_word(n):
    return cma.number_word(n)


def month_since(d, as_of):
    """'January' (the as-of year), else 'January 2025': when a history or a split started, as a heading says it."""
    d = fmt.to_date(d)
    return fmt.MONTHS[d.month - 1] + ("" if as_of and d.year == fmt.to_date(as_of).year else f" {d.year}")


# --- what the model writes: judgment only ---------------------------------------------------------------------------

# Fields the script writes now (each a sentence or figure the report states as fact): a report that still carries one is
# told where its judgment goes instead, so nothing typed is silently dropped.
RETIRED = {
    "labels": "wording overrides are no longer read: every label and sentence the script writes is in assets/labels.json",
    "method": "the sources are listed by the script from the export and the rate: name any other sources in `sources`",
    "subject.summary_facts": "the script writes the facts line from beds, baths, sqft, pool and year_built",
    "summary_page.key_stats": "the script picks page 1's key numbers",
    "bottom_line.paragraph": "the script says where asking sits and the median: write why the range sits where it does in bottom_line.why",
    "bottom_line.midpoint": "the script computes the midpoint",
    "bottom_line.low": "the script sets the range from the adjusted comps (method.md, The Range): leave it out, or put "
                       "the agent's own range in range_override {low, high, reason}",
    "bottom_line.high": "the script sets the range from the adjusted comps (method.md, The Range): leave it out, or put "
                        "the agent's own range in range_override {low, high, reason}",
    "history.heading": "the script writes the history's heading from its counts",
    "history.intro": "the script writes the history's counts: write what they add up to in history.takeaway",
    "history.after": "write what the history adds up to (no figures) in history.takeaway",
    "history.rows": "the table is built from history.events",
    "offer_plan": "the buyer CMA reports value only: the offer (its posture, opening, target, walk-away and any credit "
                  "alternative) is the buyer offer strategy's job. Leave offer_plan out; the facts behind an offer (the "
                  "history, the market) already have their own sections",
    "offer": "the buyer CMA reports value only: negotiating points belong to the buyer offer strategy. Leave offer out",
    "split_date": "the script sets the market split by its rule (the first of the month two months before as_of), so "
                  "the same export always splits the same way: leave it out, or put the agent's own date in "
                  "split_override {date, reason}",
    "comps.time_adjustment": "the script sets the market shift from the export by its rule (method.md, Time): leave it "
                             "out, or put the agent's own rate in comps.time_override {rate_per_quarter, prices, reason}",
    "costs.credit_scenarios": "price vs. seller credit is part of the offer, not the CMA: leave it out. The lender's "
                              "closing costs go in costs.closing_costs (or a share in costs.closing_cost_pct), and the "
                              "buyer's broker agreement in costs.buyer_broker_agreement_pct and "
                              "costs.seller_pays_buyer_broker_pct",
    "comps.summary_paragraph": "write which way the range leans and why (no figures) in comps.lean",
    "scatter.intro": "the script describes what the chart plots",
    "scatter.after_paragraph": "write what the chart shows (no figures) in scatter.takeaway",
    "market.intro": "the script writes the market's counts from the export",
    "market.columns": "the script builds the market table from the export",
    "market.rows": "the script builds the market table from the export",
    "costs.taxes.heading": "the script writes the tax heading",
    "costs.taxes.intro": "the script writes the current bill and the reassessment rule",
    "costs.taxes.note": "the script writes the tax notes (millage, assessment, homestead)",
    "costs.taxes.after_paragraph": "the script writes the escrow warning",
    "costs.insurance.paragraph": "write the insurance drivers for this house (no figures) in costs.insurance.drivers",
    "costs.payment.intro": "the script writes the payment's introduction from the rate (add rate_week for the survey date)",
}
RETIRED_EACH = {
    "comps.cards[].meta": "the script writes each card's sale line from the card and the export",
    "costs.payment.scenarios[].label": "the script names each scenario from its type and down_pct",
}

# Judgment fields: what the model writes in words. Each is checked figure-free (prose.figures): the script prints every
# count, price, percent and date itself, so a figure typed here could disagree with the one beside it.
JUDGMENT = (
    "subject.summary", "summary_page.label", "summary_page.headline", "summary_page.why[]",
    "summary_page.check_first[][]", "summary_page.next_step", "bottom_line.why", "range_override.reason", "history.takeaway",
    "history.events[].note", "comps.intro", "comps.method_note", "comps.lean", "comps.cards[].keep_reason", "comps.cards[].lot_reason", "subject.lot_reason",
    "comps.time_override.reason", "split_override.reason",
    "comps.cards[].bullets[]", "comps.cards[].adjustments[].label", "scatter.heading", "scatter.takeaway",
    "competition.intro", "competition.rows[][6]", "market.bullets[]", "costs.insurance.drivers", "costs.payment.note",
    "costs.taxes.jurisdictions[].label", "costs.taxes.jurisdictions[].short",
    "watch.items[]", "watch.questions[]", "sources[]", "subject.facts[][0]",
)


# The value narrative: what the report says about value, the history and the market. The report is an objective analysis
# of value, so none of these gives offer advice (an opening price, room to negotiate, leverage, a walk-away): that is the
# buyer offer strategy's. Checked on each field (schema_errors), with the fix.
VALUE_ONLY = ("summary_page.headline", "summary_page.why[]", "bottom_line.why", "range_override.reason",
              "history.takeaway", "comps.lean", "scatter.takeaway", "market.bullets[]", "subject.summary")
OFFER_ADVICE = re.compile(r"\b(offer|offering at|open(?:ing)? (?:at|low|high|below|near)|negotiat\w*|leverage|walk[- ]?away"
                          r"|counter[- ]?offers?|lowball\w*|bargain\w*|room to (?:move|come down)|cushion\w*)\b", re.I)
# Where asking sits is the script's (asking_position, printed right above the headline), so the headline never says it:
# it gives the one fact that explains the value, and can't contradict the script's line.
HEADLINE_POSITION = re.compile(r"\b(asking|list(?:ing)? price|priced|above|below|inside|within|bottom|top|middle|median)\b",
                               re.I)


def _walk(node, parts, path):
    """(path, value) for every value a dotted pattern ('comps.cards[].bullets[]', 'rows[][6]') names."""
    if not parts:
        yield path, node
        return
    head, rest = parts[0], parts[1:]
    if head == "[]":
        if isinstance(node, list):
            for i, v in enumerate(node):
                yield from _walk(v, rest, f"{path}[{i}]")
    elif head.startswith("["):
        i = int(head[1:-1])
        if isinstance(node, list) and i < len(node):
            yield from _walk(node[i], rest, f"{path}[{i}]")
    elif isinstance(node, dict) and head in node:
        yield from _walk(node[head], rest, f"{path}.{head}" if path else head)


def _parts(pattern):
    return re.findall(r"\[\d*\]|[^.\[\]]+", pattern)


def schema_errors(R):
    """Retired fields still present, and judgment fields that carry a figure, as `field: problem → fix`."""
    out = []
    for path, why in RETIRED.items():
        if any(v not in (None, "", [], {}) for _, v in _walk(R, _parts(path), "")):
            out.append(f"{path}: no longer written by you → {why}.")
    for pattern, why in RETIRED_EACH.items():
        out += [f"{path}: no longer written by you → {why}." for path, v in _walk(R, _parts(pattern), "")
                if v not in (None, "")]
    for pattern in JUDGMENT:
        for path, v in _walk(R, _parts(pattern), ""):
            if isinstance(v, str):
                text = re.sub(r"<[^>]+>", " ", v)
                found = prose.figures(text) + prose.counts(text) + re.findall(r"\{\w*\}", v)
                if found:
                    out.append(f"{path}: has {', '.join(repr(x) for x in found)} → the report prints every count, price, "
                               "percent and date itself; write this in words, without the figure.")
                who = prose.people(text)
                if who:
                    out.append(f"{path}: has {', '.join(repr(x) for x in who)} → {prose.PEOPLE_FIX}.")
    # the fair-housing phrases render.py stops on, here too, so the first run names them (iteration 20: "young
    # families" in deck.tagline passed compute.py and stopped only at render)
    out += [f"{path.removeprefix('$.')}: {problem}" for path, problem in prose.issues(R, rules=frozenset({"fair"}))]
    for pattern in VALUE_ONLY:
        for path, v in _walk(R, _parts(pattern), ""):
            found = OFFER_ADVICE.findall(re.sub(r"<[^>]+>", " ", v)) if isinstance(v, str) else []
            if found:
                out.append(f"{path}: has {', '.join(repr(x) for x in dict.fromkeys(found))} → this report is an "
                           "objective analysis of value: say what the comps, the history and the market show, never "
                           "what to offer or how to negotiate (that is the buyer offer strategy's).")
    head = (R.get("summary_page") or {}).get("headline")
    found = HEADLINE_POSITION.findall(head) if isinstance(head, str) else []
    if found:
        out.append(f"summary_page.headline: has {', '.join(repr(x) for x in dict.fromkeys(found))} → where asking sits is "
                   "the script's line right above the headline; the headline gives the one fact that explains the value "
                   "(\"Renovated Spring Oaks pool homes of the same size set the value; this one's roof age is unknown\").")
    return out


# --- costs ---------------------------------------------------------------------------------------------------------

def taxes(R, market):
    """Buyer's estimated bill for each jurisdiction, at the purchase price in costs.taxes: the exact estimate and the
    figure the report shows (to the dollar), which every table and the payment use."""
    t_ = R["costs"]["taxes"]
    county = R["subject"].get("county")
    out = []
    for j in t_["jurisdictions"]:
        school, total, problem, year = j.get("school_mills"), j.get("total_mills"), None, None
        if total is None and j.get("district"):
            row, problem = finance.millage_row(market, county, j["district"])
            if row:
                school, total, year = row["school"], row["total"], row.get("year")
        est = finance.property_tax(t_["purchase_price"], market, school, total, t_.get("homestead", True))
        annual = fmt.half_up(est["annual"]) if est["annual"] is not None else None
        out.append({"label": j["label"], "short": j.get("short", ""), "school_mills": school, "total_mills": total,
                    "year": year, "annual_exact": est["annual"], "annual": annual,
                    "monthly": fmt.half_up(annual / 12) if annual is not None else None,
                    "annual_display": money(annual) if annual is not None else None,
                    "monthly_display": money(annual / 12) if annual is not None else None,
                    "estimated": est["estimated"], "problem": problem})
    return out


def tax_annual_at(price, market, j, homestead):
    """A jurisdiction's yearly bill at another price, to the dollar (the payment at the median adjusted value)."""
    est = finance.property_tax(price, market, j["school_mills"], j["total_mills"], homestead)
    return fmt.half_up(est["annual"] or 0)


def buyer_closing_costs(R, market, price, program, down, loan):
    """CMA-223: the buyer's closing costs at `price`, on the offer strategy's basis (finance.buyer_closing_costs): the
    lender's figure (`costs.closing_costs`) for the first payment scenario (the buyer's own financing), else
    `costs.closing_cost_pct` of the price as given, else the market's share plus prepaids and its loan taxes on `loan`
    (CORE-16; half the share for cash). Returns (amount, the itemized loan taxes, whether it's the lender's figure)."""
    c = R["costs"]
    first = (c.get("payment") or {}).get("scenarios") or [{}]
    own = (first[0].get("type") is not None and finance.program(first[0]["type"]) == program
           and abs(_frac(first[0], "down_pct", "costs.payment.scenarios[0]", 0.05) - down) < 1e-9)
    cc = finance.buyer_closing_costs(price, loan, market, cash=program == "cash",
                                     pct=_frac(c, "closing_cost_pct", "costs"),
                                     amount=c.get("closing_costs") if own and c.get("closing_costs") else None)
    return cc["amount"], cc["loan_taxes"], cc["source"] == "lender"


def broker_fee_short(R, price):
    """CMA-4: what the buyer pays their own broker at `price` when the seller pays less than the agreement."""
    c = R["costs"]
    agreement = _frac(c, "buyer_broker_agreement_pct", "costs")
    seller_pays = _frac(c, "seller_pays_buyer_broker_pct", "costs", 0)
    return finance.buyer_broker_shortfall(price, agreement, seller_pays) or 0


def _short(need, have):
    """How much more cash `need` takes than the buyer has (CMA-204), or None when it fits or `have` isn't given."""
    return fmt.half_up(need - have) if isinstance(have, (int, float)) and have and need > have + 1 else None


def _tight(need, have):
    """How much the buyer would have left when `need` fits but uses all but CASH_TIGHT of `have`, else None."""
    if not isinstance(have, (int, float)) or not have or need > have + 1 or need < have * (1 - CASH_TIGHT):
        return None
    return max(fmt.half_up(have - need), 0)


def flood_line(R, market):
    """CMA-6: the payment's flood insurance line. A quote (`costs.payment.flood_insurance_annual`) is counted; without
    one the row reads "get a quote" and the total leaves it out, never $0. The zone is `costs.payment.flood_zone`,
    else `subject.flood_zone`, else the Flood Zone fact."""
    pay, s = R["costs"]["payment"], R["subject"]
    zone = pay.get("flood_zone") or s.get("flood_zone") or fact_value(s, "flood zone")
    return finance.flood_insurance(zone, pay.get("flood_insurance_annual"), market,
                                   date.fromisoformat(R["as_of"]) if R.get("as_of") else None,
                                   condo_unit=finance.property_type(s.get("property_type")) == "condo")


def fact_value(s, label):
    return next((v for lbl, v in s.get("facts") or [] if str(lbl).lower() == label), None)


def monthly_ledger(price, program, down, rate, tax_annual, ins_annual, hoa, flood_annual, tax_label):
    """One price's monthly payment as a finance.Ledger (principal and interest, tax, insurance, flood when quoted,
    mortgage insurance, HOA): each line rounded once, the total the sum of the printed lines. Returns (ledger, the
    loan details from finance.monthly_payment)."""
    r = finance.monthly_payment(price, program, down, rate, tax_annual, ins_annual, hoa, flood_annual=flood_annual)
    led = finance.Ledger()
    led.add("pi", L["pay_pi"], r["pi"])
    led.add("tax", tax_label, tax_annual / 12)
    led.add("ins", L["pay_ins"], ins_annual / 12)
    if r["flood"] is not None:
        led.add("flood", L["pay_flood"], r["flood"])
    led.add("mi", L["pay_mi"], r["mi"])
    led.add("hoa", L["pay_hoa"], r["hoa"] or 0)
    return led, r


def cash_ledger(down_amount, closing, bb_short=0):
    """Cash to close as a finance.Ledger: the down payment, closing costs and any buyer's broker fee the seller doesn't
    pay; its total is the cash to close."""
    led = finance.Ledger()
    led.add("down", L["pay_cash"], down_amount)
    led.add("closing", L["pay_closing"], closing)
    if bb_short:
        led.add("bb", L["pay_bb"], bb_short)
    return led


def scenario_label(sc):
    """'Conventional, 5% Down', 'VA, No Down Payment', 'Cash Purchase': from the scenario's type and down payment."""
    key = finance.program(sc["type"])
    if key == "cash":
        return L["scen_label_cash"]
    if not sc["down_pct"]:
        return t("scen_label_none", program=L["prog_" + key])
    return t("scen_label", program=L["prog_" + key], down=fmt.pct(sc["down_pct"], 2))


def hoa_cdd(R):
    """The monthly HOA and CDD in the payment: `costs.payment.hoa_cdd_monthly`, else the home's own `hoa_monthly`
    (iteration 19: dues on the subject never reached the payment)."""
    pay = R["costs"]["payment"]
    v = pay.get("hoa_cdd_monthly")
    if v is None:
        v = (R.get("subject") or {}).get("hoa_monthly")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else 0


def payments(R, market, tax_rows, ji, insurance, median_shown=None):
    """The payment table at `costs.payment.price` (asking by default), one column per financing scenario, and each
    column's total at the median adjusted value when that is lower (`at_median`): the same home at what the comps
    support, a fact beside the asking price, never a suggested price."""
    pay = R["costs"]["payment"]
    price, cash, homestead = pay["price"], R["costs"].get("buyer_cash"), R["costs"]["taxes"].get("homestead", True)
    flood = flood_line(R, market)
    tj = tax_rows[ji]
    tax_label = (t("pay_tax", short=tj["short"], homestead=homestead_label(homestead)) if tj["short"]
                 else t("pay_tax_one", homestead=homestead_label(homestead)))
    rows = []
    for i, sc in enumerate(pay["scenarios"]):
        if sc.get("type") is None or sc.get("down_pct") is None:
            raise ReportError(f"costs.payment.scenarios[{i}] needs a type and a down_pct (0.05 for 5%).")
        sc["down_pct"] = _frac(sc, "down_pct", f"costs.payment.scenarios[{i}]")
        try:
            prog = finance.program(sc["type"])
        except ValueError as e:
            raise ReportError(f"costs.payment.scenarios[{i}].type: {e}") from None
        sc["label"] = scenario_label(sc)
        mled, r = monthly_ledger(price, prog, sc["down_pct"], pay["rate"], tj["annual"], insurance["annual"],
                                 hoa_cdd(R), flood["annual"], tax_label)
        cc, _, lender = buyer_closing_costs(R, market, price, prog, sc["down_pct"], r["loan"])
        cled = cash_ledger(r["cash_down"], cc, broker_fee_short(R, price))
        total, to_close = mled.total(), cled.total()
        row = {"label": sc["label"], "program": prog, "down_pct": sc["down_pct"], "assumed": bool(sc.get("assumed")),
               "loan": r["loan"], "monthly": mled.tuples(), "cash_lines": cled.tuples(),
               "pi": mled.amount("pi"), "tax": mled.amount("tax"), "ins": mled.amount("ins"),
               "flood": mled.amount("flood") if mled.has("flood") else None, "mi": mled.amount("mi"),
               "hoa": mled.amount("hoa"), "total": total, "total_display": money(total),
               "cash_down": cled.amount("down"), "cash_down_display": money(cled.amount("down")),
               "closing_costs": cled.amount("closing"), "bb_short": cled.amount("bb"), "lender_closing_costs": lender,
               "cash_to_close": to_close, "cash_to_close_display": money(to_close),
               "down_short": _short(cled.amount("down"), cash), "cash_short": _short(to_close, cash),
               "cash_left": _tight(to_close, cash)}
        row["cash_short_display"] = money(row["cash_short"]) if row["cash_short"] is not None else None
        row["cash_left_display"] = money(row["cash_left"]) if row["cash_left"] is not None else None
        rows.append(row)
    first = rows[0]
    lower, _ = monthly_ledger(price - 10000, first["program"], first["down_pct"], pay["rate"],
                              tax_annual_at(price - 10000, market, tj, homestead), insurance["annual"],
                              hoa_cdd(R), flood["annual"], tax_label)
    alt = None
    if len(tax_rows) == 2 and tax_rows[1 - ji]["annual"] is not None:
        other = tax_rows[1 - ji]
        alt = {"short": other["short"],
               "totals": [r["total"] - r["tax"] + fmt.half_up(other["annual"] / 12) for r in rows]}
    # CMA-204: which tax the payment uses. Two jurisdictions mean the district isn't confirmed: the payment uses the
    # one at tax_jurisdiction_index (the higher bill by default), an estimate the notes say, as is a fallback-rate one.
    tax_basis = {"short": tj["short"], "unconfirmed": len(tax_rows) == 2, "estimated": bool(tj["estimated"]),
                 "higher": len(tax_rows) == 2 and (tj["annual"] or 0) >= (tax_rows[1 - ji]["annual"] or 0),
                 "homestead": bool(homestead)}
    tax_basis["label_estimate"] = tax_basis["unconfirmed"] or tax_basis["estimated"]
    per_10k = first["total"] - lower.total()
    at_median = None
    if median_shown is not None and median_shown < price:
        at_median = {"price": median_shown, "price_display": money(median_shown), "totals": [
            monthly_ledger(median_shown, r["program"], r["down_pct"], pay["rate"],
                           tax_annual_at(median_shown, market, tj, homestead), insurance["annual"],
                           hoa_cdd(R), flood["annual"], tax_label)[0].total() for r in rows]}
    return {"price": price, "price_display": money(price), "price_basis": price_basis(price, R, median_shown),
            "at_median": at_median, "rate": pay["rate"],
            "rate_display": fmt.pct(pay["rate"] / 100, 3), "insurance_annual": insurance["annual"],
            "insurance": insurance, "rows": rows, "flood": flood, "per_10k": per_10k,
            "per_10k_display": money(per_10k), "alt_jurisdiction": alt, "tax_index": ji, "tax_basis": tax_basis,
            "tax_label": tax_label, "buyer_cash": cash, "buyer_cash_display": money(cash) if cash else None}


def insurance_line(R, market):
    """The payment's homeowner's insurance: the agent's figure (`costs.payment.insurance_annual`, a quote or their own
    number) as given, else the shared estimate at the payment's price (finance.insurance_estimate: the agent's
    `costs.insurance_rate` for this home, else the market's rate by the home's age, with its floor)."""
    pay = R["costs"]["payment"]
    if pay.get("insurance_annual") not in (None, ""):
        return {"annual": pay["insurance_annual"], "estimated": False, "source": "agent"}
    est = finance.insurance_estimate(pay["price"], market, R["subject"].get("year_built"), R["costs"].get("insurance_rate"))
    return {**est, "estimated": True}


def homestead_label(homestead):
    return L["with_homestead"] if homestead else L["no_homestead"]


def price_basis(price, R, median_shown=None):
    """CMA-204: what the payment's price is, so page 1 can say so: the asking price or the median adjusted value."""
    if price == R["subject"]["list_price"]:
        return "asking"
    return "median" if median_shown is not None and price == median_shown else None


def basis_words(basis):
    return L["basis_" + basis] if basis else ""


def default_prices(R):
    """CMA-204: without `costs.payment.price` the payment is figured at the asking price, the one price the buyer sees
    on the listing; without `costs.taxes.purchase_price` the tax estimate uses the payment's price, so page 1's numbers
    agree."""
    costs = R.get("costs") or {}
    pay, t_ = costs.get("payment"), costs.get("taxes")
    if isinstance(pay, dict) and pay.get("price") in (None, ""):
        pay["price"] = R["subject"]["list_price"]
    if isinstance(t_, dict) and t_.get("purchase_price") in (None, "") and isinstance(pay, dict) and pay.get("price"):
        t_["purchase_price"] = pay["price"]


# --- the listing history ---------------------------------------------------------------------------------------------

# CMA-201: history.events, one per row of the MLS history grid. `change` is a plain word or the MLS's code (Stellar's
# NEW, DECR, INCR, TOM, BOM, PNC, SLD, CANC, EXP, WDN); what each does to the listing's status.
HISTORY_CHANGES = {
    "listed": "active", "new": "active", "price": None, "decr": None, "incr": None,
    "off_market": "off", "tom": "off", "back_on": "active", "bom": "active",
    "pending": "pending", "pnc": "pending", "sold": "sold", "sld": "sold",
    "canceled": "ended", "canc": "ended", "expired": "ended", "exp": "ended", "withdrawn": "ended", "wdn": "ended",
}
HISTORY_NEW = ("listed", "new")
HISTORY_KIND = {"new": "listed", "decr": "price", "incr": "price", "tom": "off_market", "bom": "back_on", "pnc": "pending",
                "sld": "sold", "canc": "canceled", "exp": "expired", "wdn": "withdrawn"}
# CMA-229: a row whose note says it happened more than once ("off and on twice") hides undated off/on pairs
HISTORY_REPEATED = re.compile(r"\b(twice|three times|\d+ times|several|multiple|more than once|repeatedly)\b", re.I)


def _days(e, i, key):
    """CMA-229: an event's `days_off` or `days_on` (days in undated off/on pairs the row sums up), 0 when not given."""
    v = e.get(key)
    if v is None:
        return 0
    if not isinstance(v, (int, float)) or isinstance(v, bool) or v < 0:
        raise ReportError(f"history.events[{i}].{key} must be a whole number of days (12), not {v!r}.")
    return v


def history_stats(R, as_of):
    """CMA-201, CMA-208: the listing history counted from `history.events` instead of by hand: price cuts and
    increases, the total cut in dollars and as a share of the first list price, failed contracts, and the days the
    home was actively for sale across every MLS number since the last sale (CMA-307: an earlier owner's listings are
    in the table, never in the counts). Returns (stats or None, [(warning key, text)]).

    Each event is {date: YYYY-MM-DD, mls, change, price (the asking price after it, when the row shows one), dom (the
    grid's days on market at that row, when it shows one), days_off / days_on (days off or back on the market in
    undated off/on pairs the row sums up, CMA-229), note (optional wording for the report's row)}, in the
    grid's order. `timeline` is the same events oldest first, for the report's table. A price that differs from the asking
    price before it is a cut or an increase, whatever the row's code. A listing's active days are its latest `dom`
    (plus the days since, while it's still for sale), else counted by the calendar from its status changes; the
    current listing runs to `as_of`. Rows out of date order in the grid and an MLS number that doesn't match the
    subject's are warned, never silently fixed."""
    h = R.get("history") or {}
    events, warns = h.get("events"), []
    if not events:
        return None, warns
    rows = []
    for i, e in enumerate(events):
        change = str(e.get("change", "")).strip().lower().replace(" ", "_")
        if change not in HISTORY_CHANGES:
            raise ReportError(f"history.events[{i}].change is {e.get('change')!r}: use listed, price, off_market, back_on, "
                              "pending, sold, canceled, expired or withdrawn (or the MLS code, such as DECR).")
        try:
            when = date.fromisoformat(str(e.get("date")))
        except ValueError:
            raise ReportError(f"history.events[{i}].date is {e.get('date')!r}: write it as YYYY-MM-DD.") from None
        price = e.get("price")
        if price is not None and (not isinstance(price, (int, float)) or isinstance(price, bool)):
            raise ReportError(f"history.events[{i}].price must be a plain number (474900), not {price!r}.")
        rows.append({"i": i, "date": when, "mls": str(e.get("mls") or "").strip().upper() or None, "change": change,
                     "price": price, "dom": e.get("dom"), "cdom": e.get("cdom"),
                     "days_off": _days(e, i, "days_off"), "days_on": _days(e, i, "days_on"),
                     "repeated": bool(HISTORY_REPEATED.search(str(e.get("note") or "")))})
    # the grid's order: newest first normally; any row that breaks the direction is out of date order
    newest_first = rows[0]["date"] >= rows[-1]["date"]
    out_of_order = order_breaks(rows, newest_first)
    for group in out_of_order:
        if len(group) == 1:
            r = rows[group[0]]
            warns.append(("history_order", f"history.events[{r['i']}] ({fmt.date_short(r['date'])}) is out of date order "
                          "in the grid: without it the rest is in order. Check that row's date with the MLS before quoting "
                          "it; it was counted by its date."))
        else:
            a, b = rows[group[0]], rows[group[1]]
            warns.append(("history_order", f"history.events[{a['i']}] ({fmt.date_short(a['date'])}) and history.events"
                          f"[{b['i']}] ({fmt.date_short(b['date'])}) are out of date order with each other in the grid: one "
                          "of them is likely mistyped. Check both dates with the MLS before quoting them; each was counted "
                          "by its date."))
    rows.sort(key=lambda r: (r["date"], -r["i"] if newest_first else r["i"]))
    subject_mls = subject_mls_number(R["subject"])
    newest_mls = next((r["mls"] for r in reversed(rows) if r["mls"]), None)
    if subject_mls and newest_mls and newest_mls != subject_mls:
        warns.append(("history_mls_mismatch", f"The newest history row is MLS {newest_mls}, but the listing is MLS "
                      f"{subject_mls}: check that the history is this home's current listing."))
    # CMA-307: the counts start after the last sale (an ownership change): an earlier owner's listing stays in the
    # table but its days, price changes and contracts aren't this seller's
    sale = max((n for n, r in enumerate(rows[:-1]) if HISTORY_CHANGES[r["change"]] == "sold"), default=None)
    counted = rows[sale + 1:] if sale is not None else rows
    cuts, increases, asking, first_price, first_listed, last_contract = [], [], None, None, None, None
    for r in rows:
        r["delta"] = 0
    for r in counted:
        if HISTORY_CHANGES[r["change"]] == "pending":  # CMA-214: the asking price when it last went under contract
            last_contract = (r["date"], r["price"] if r["price"] is not None else asking)
        if r["change"] in HISTORY_NEW:
            asking = r["price"] if r["price"] is not None else asking
            first_price, first_listed = first_price or r["price"], first_listed or r["date"]
            continue
        if r["price"] is None or HISTORY_CHANGES[r["change"]] == "sold":  # a sale price isn't an asking price
            continue
        if asking is not None and r["price"] != asking:
            r["delta"] = r["price"] - asking
            (cuts if r["delta"] < 0 else increases).append(abs(r["delta"]))
        asking = r["price"]
    listings, current = [], None
    for r in counted:
        if r["change"] in HISTORY_NEW or current is None or (r["mls"] and current["mls"] and r["mls"] != current["mls"]):
            current = {"mls": r["mls"], "rows": []}
            listings.append(current)
        current["mls"] = current["mls"] or r["mls"]
        current["rows"].append(r)
    end = date.fromisoformat(as_of)
    active_days, failed = 0, 0
    for n, lst in enumerate(listings):
        status, since, days, stop = None, None, 0, listings[n + 1]["rows"][0]["date"] if n + 1 < len(listings) else end
        for r in lst["rows"]:
            new = HISTORY_CHANGES[r["change"]]
            if status == "pending" and new not in (None, "pending", "sold"):
                failed += 1
            if new is None:
                continue
            if status == "active" and since:
                days += (r["date"] - since).days
            status, since = new, r["date"] if new == "active" else None
        if status == "active" and since:
            days += max((stop - since).days, 0)
        with_dom = [r for r in lst["rows"] if isinstance(r.get("dom"), (int, float))]
        with_cdom = [r for r in lst["rows"] if isinstance(r.get("cdom"), (int, float))]
        if not with_dom and with_cdom:  # CMA-212: on the first listing CDOM is its DOM; later it spans (and may reset)
            if n == 0:
                with_dom = [{**r, "dom": r["cdom"]} for r in with_cdom]
            else:
                warns.append(("history_cdom", f"history.events[{with_cdom[-1]['i']}] has a cdom, which spans earlier "
                              "listings and resets after a gap off the market: put that listing's own DOM in dom. Its "
                              "days were counted by the calendar."))
        if with_dom:  # the MLS's own count wins, plus the days since while it's still for sale
            last = with_dom[-1]
            days = last["dom"] + (max((stop - last["date"]).days, 0) if status == "active" else 0)
        else:  # CMA-229: the MLS's DOM already counts undated off/on pairs; the calendar needs days_off / days_on
            days = max(days - sum(r["days_off"] for r in lst["rows"]) + sum(r["days_on"] for r in lst["rows"]), 0)
            for r in lst["rows"]:
                if r["repeated"] and not (r["days_off"] or r["days_on"]):
                    warns.append(("history_repeat", f"history.events[{r['i']}]'s note says it happened more than once, "
                                  "but the undated off/on pairs aren't in the count: the calendar counts the whole stretch "
                                  "as off (or on), so its active days may be off. Add the listing's DOM from the grid as "
                                  "dom, each pair as dated off_market and back_on events, or the days in days_off / "
                                  "days_on (report-data.md)."))
        active_days += days
    active_days = fmt.half_up(active_days)
    total_cut, first_listed = sum(cuts), first_listed or counted[0]["date"]
    timeline = []
    flagged = {rows_by_i for g in out_of_order for rows_by_i in g}  # event indices (order_breaks ran before the sort)
    # oldest first, for the report's table, in the grid's own order: a row out of date order stays where the grid has
    # it, marked for the agent to check, never moved to where its date would put it (iteration 20)
    for r in sorted(rows, key=lambda r: r["i"], reverse=newest_first):
        kind = HISTORY_KIND.get(r["change"], r["change"])
        if kind == "price":
            kind = "price_cut" if r["delta"] < 0 else "price_increase" if r["delta"] > 0 else "price"
        timeline.append({"date": r["date"].isoformat(), "kind": kind, "price": r["price"], "delta": r["delta"],
                         "mls": r["mls"], "note": events[r["i"]].get("note"), "to_confirm": r["i"] in flagged})
    stats = {
        "events": len(rows), "first_listed": first_listed.isoformat(),
        "listings": sum(1 for lst in listings if any(HISTORY_CHANGES[r["change"]] == "active" for r in lst["rows"])),
        "first_list_price": first_price, "current_price": asking,
        "price_cuts": len(cuts), "price_increases": len(increases), "price_cut_total": total_cut,
        "price_cut_pct": round(total_cut / first_price, 4) if first_price and total_cut else 0,
        "price_increase_total": sum(increases), "failed_contracts": failed, "active_days": active_days,
        "out_of_order": out_of_order,  # CMA-216: event indices, grouped
        "counted_since_sale": rows[sale]["date"].isoformat() if sale is not None else None,
        "timeline": timeline,
    }
    ask_now = R["subject"].get("list_price") or asking
    if last_contract and last_contract[1] is not None and ask_now is not None:
        stats.update(last_contract_date=last_contract[0].isoformat(), last_contract_price=last_contract[1],
                     vs_last_contract=ask_now - last_contract[1])
    stats["display"] = {
        "price_cuts": plural(len(cuts), "p_price_cut", "p_price_cuts"),
        "price_increases": plural(len(increases), "p_increase", "p_increases"),
        "price_cut_total": money(total_cut), "price_cut_pct": fmt.pct(stats["price_cut_pct"], 1, fixed=True),
        "failed_contracts": plural(failed, "p_failed", "p_faileds"), "active_days": plural(active_days, "p_day", "p_days"),
        "first_listed": fmt.date_long(first_listed),
        "counted_since_sale": fmt.date_long(rows[sale]["date"]) if sale is not None else None,
    }
    if "vs_last_contract" in stats:  # CMA-214: "$400 above", "$2,000 below" or "equal to" the last contract's asking
        d = stats["vs_last_contract"]
        stats["display"].update(last_contract_price=money(stats["last_contract_price"]),
                                 vs_last_contract=t("vs_above" if d > 0 else "vs_below", amt=money(abs(d))) if d else L["vs_equal"])
    return stats, warns


def order_breaks(rows, newest_first):
    """CMA-216: the rows that break the grid's date order, as index groups into `rows`. Where dropping one row of an
    out-of-order pair puts its neighbors back in order and dropping the other doesn't, that row alone; where either
    would (or neither), both, since the dates can't say which one is mistyped."""
    def ok(a, b):
        return a["date"] >= b["date"] if newest_first else a["date"] <= b["date"]
    groups = []
    for j in range(len(rows) - 1):
        if ok(rows[j], rows[j + 1]):
            continue
        drop_a = j == 0 or ok(rows[j - 1], rows[j + 1])  # without rows[j]
        drop_b = j + 2 >= len(rows) or ok(rows[j], rows[j + 2])  # without rows[j + 1]
        group = [j] if drop_a and not drop_b else [j + 1] if drop_b and not drop_a else [j, j + 1]
        if not groups or not set(group) & set(groups[-1]):
            groups.append(group)
    return groups


def history_dates(dates, this_year):
    """Results_v5 case 03: 'Jul 10, 2026' on every row when the rows span more than one year (or their one year isn't
    the report's), so a bare 'Aug 14' never reads as another row's year; 'Jul 10' when all are this year."""
    years = {d.year for d in dates}
    short = len(years) == 1 and years == {this_year}
    return [fmt.date_short(d, year=not short) for d in dates]


def history_section(hist, as_of):
    """The history's heading, its counts as sentences and its table rows (oldest first), from history_stats."""
    if not hist:
        return None
    d = hist["display"]
    since = month_since(hist["first_listed"], as_of)
    if hist["price_cuts"]:
        cuts = t("sum_cuts_one") if hist["price_cuts"] == 1 else t("sum_cuts_many", n=fmt.num(hist["price_cuts"]))
        heading = t("h_history_cuts", cuts=cuts, since=since)
    else:
        heading = t("h_history", since=since)
    lines = [t("line_hist_listed", date=d["first_listed"], days=d["active_days"],
               across=t("line_hist_across", n=number_word(hist["listings"])) if hist["listings"] > 1 else "")]
    parts = []
    if hist["price_cuts"]:
        parts.append(t("line_hist_cut_total", cuts=d["price_cuts"], total=d["price_cut_total"], pct=d["price_cut_pct"]))
    if hist["price_increases"]:
        parts.append(d["price_increases"])
    if hist["failed_contracts"]:
        parts.append(d["failed_contracts"])
    lines.append(t("line_hist_changes", parts=cma._and(parts)) if parts else L["line_hist_none"])
    if "vs_last_contract" in hist:
        lines.append(t("line_hist_last_contract", vs=d["vs_last_contract"], price=d["last_contract_price"]))
    if hist["counted_since_sale"]:
        lines.append(t("line_hist_since_sale", date=d["counted_since_sale"]))
    timeline = hist["timeline"]
    year = fmt.to_date(as_of).year if as_of else date.today().year
    whens = history_dates([fmt.to_date(e["date"]) for e in timeline], year)
    rows, n_listed = [], 0
    for e, when in zip(timeline, whens):
        kind = e["kind"]
        if kind == "listed":
            n_listed += 1
            kind = "relisted" if n_listed > 1 else "listed"
        elif kind == "back_on" and e["delta"]:
            kind = "back_on_higher" if e["delta"] > 0 else "back_on_lower"
        elif kind == "sold":  # CMA-307: a listing after a sale is the next owner's, not a relisting
            n_listed = 0
        rows.append([t("hist_date_check", when=when) if e.get("to_confirm") else when, e.get("note") or L["hist_" + kind],
                     money(e["price"]) if e["price"] is not None else fmt.EMPTY])
    return {"heading": heading, "lines": lines, "rows": rows}


def subject_mls_number(s):
    """The listing's MLS number: `subject.mls_number`, else the "MLS #" part of `subject.locality`."""
    if s.get("mls_number"):
        return str(s["mls_number"]).strip().upper()
    m = re.search(r"\bMLS\s*#?\s*([A-Z]{0,3}\d{5,})", str(s.get("locality") or ""), re.I)
    return m.group(1).upper() if m else None


def export_mls_warning(R, homes):
    """CMA-208: the export's current (active or pending) row for the subject carries a different MLS number than the
    listing. An old sale or expired listing of the same home has its own number, so only a current row counts."""
    s, number = R["subject"], subject_mls_number(R["subject"])
    row = next((h for h in homes if h["status"] in ("ACTIVE", "PENDING")
                and mls.same_address(h["address"], s.get("mls_address", s["address"]))), None)
    theirs = str((row or {}).get("mls_number") or "").strip().upper()
    if number and theirs and theirs != number:
        return [f"The export's row for {s.get('mls_address', s['address'])} is MLS {theirs}, but the listing is MLS {number}: "
                "the export may predate the relist. Check its days on market and price against the listing before quoting them."]
    return []


# --- comps ------------------------------------------------------------------------------------------------------------

def median_rounded(median_adjusted, count):
    """CMA-234: an even number of comps has a midpoint median ($472,612.50): rounded to the nearest $100, as seller-cma
    does (CMA-265); an odd count's median is a comp's own adjusted value, kept to the dollar. Every figure quoted from
    the median (page 1, the payment at the median) uses this value, so the report shows one median."""
    return fmt.half_up(median_adjusted, 1 if count % 2 else 100)


def comp_count_warnings(cards):
    """No comps is an error; fewer than 3 is thin support and a warning."""
    if not cards:
        raise ReportError("comps.cards is empty: a CMA needs at least 3 closed comps (add them, or widen the search).")
    return [f"Only {len(cards)} comp{'s' if len(cards) > 1 else ''}: the range rests on thin support. Widen the search if "
            "you can, and say so in the report."] if len(cards) < 3 else []


def prepare_comps(R, homes, warn, market):
    """The comps by the shared pipeline (cma.settle_comps): the split and the market-shift rate by rule, the condition,
    roof and time adjustments, each adjusted value, and the used comps (outliers set aside for the next backup). Writes
    the used comps into the working copy. Returns (time info, the split, condition info, the pipeline's info)."""
    for i, c in enumerate(R["comps"]["cards"]):
        if not isinstance(c, dict) or not c.get("address") or not isinstance(c.get("adjustments"), list):
            raise ReportError(f"comps.cards[{i}] needs address, sold_price, seller_concessions and adjustments "
                              "([{label, amount}], empty when there are none): the script adds them up.")
    st, _ = export_stats(R, homes)
    try:
        errors, warns, info = cma.settle_comps(R, homes, market, st)
    except ValueError as e:
        raise ReportError(str(e)) from e
    if errors:
        raise ReportError(stop_message(errors))
    for key, text in warns:
        warn(key, text)
    return info["time"], info["split"], info["condition"], info


def supported_range(R, values, market):
    """The range by the shared rule (cma.choose_range), or the agent's range_override, written into the working copy's
    bottom_line so every figure after it uses the one range. Returns resolve_range's dict."""
    rng, errors = cma.resolve_range(values, market, R.get("range_override"))
    if errors:
        raise ReportError(stop_message(errors))
    bl = R.setdefault("bottom_line", {})
    bl["low"], bl["high"] = rng["low"], rng["high"]
    return rng


def export_row(homes, address):
    return next((h for h in homes or () if h.get("status") == "SOLD"
                 and mls.same_address(cma._street(h["address"]), cma._street(address))), None)


def comp_cards(cards, homes):
    """Each card as the report places it: its sale line (from the card and the export's row), its adjustments as a
    finance.Ledger (the sale price, seller-paid costs and each adjustment add up to the adjusted value) and its
    judgment bullets."""
    out = []
    for c in cards:
        row = export_row(homes, c["address"]) or {}
        closed = cma.comp_close_date(c, homes)
        led = finance.Ledger()
        led.add("sold", L["card_sold"], c["sold_price"])
        if c.get("seller_concessions"):
            led.cost("concessions", L["card_concessions"], c["seller_concessions"])
        for a in c.get("adjustments") or []:
            if a.get("amount"):
                led.add("adj", a["label"], a["amount"])
        if led.total() != fmt.half_up(c["adjusted"]):
            raise ReportError(f"{c['address']}: the adjustments don't add up to its adjusted value; itemize them as "
                              "plain numbers.")
        meta = [t("meta_sold", price=money(c["sold_price"]))]
        if closed:
            meta.append(fmt.date_short(closed))
        if row.get("living_area"):
            meta.append(t("meta_sqft", n=fmt.num(row["living_area"])))
        if row.get("beds") and row.get("full_baths"):
            meta.append(t("meta_beds", beds=fmt.num(row["beds"]), baths=fmt.num(row["full_baths"])))
        if row.get("private_pool"):
            meta.append(L["meta_pool"])
        if row.get("lot_acres"):
            meta.append(t("meta_lot", n=fmt.num(row["lot_acres"], 2)))
        if row.get("distance") is not None:
            meta.append(t("meta_dist", n=fmt.num(row["distance"], 1)))
        out.append({"address": cma.display_address(c["address"]), "adjusted": led.total(),
                    "adjusted_display": money(led.total()), "adjusted_k": fmt.k(led.total()),
                    "close_date": closed.isoformat() if closed else None, "meta": meta,
                    "lines": [[ln["label"], money(ln["amount"], style="signed") if ln["key"] != "sold" else money(ln["amount"])]
                              for ln in led],
                    "bullets": list(c.get("bullets") or [])})
    return out


def comps_count_line(cards, homes, split):
    dates = [d for d in (cma.comp_close_date(c, homes) for c in cards) if d]
    if not dates:
        return ""
    since = [d for d in dates if split and d >= split]
    dists = [r["distance"] for r in (export_row(homes, c["address"]) for c in cards) if r and r.get("distance") is not None]
    within = ""
    if dists and len(dists) == len(cards):
        far = max(dists)
        within = L["line_comps_within_one"] if far <= 1 else t("line_comps_within", dist=fmt.num(math.ceil(far * 10) / 10, 1))
    return t("line_comps_count", n=number_word(len(cards)), first=fmt.date_short(min(dates)),
             last=fmt.date_short(max(dates)),
             since=t("line_comps_since", k=number_word(len(since)), split=cma.day_words(split))
             if split and since and len(since) < len(dates) else "", within=within)


def range_position(value, low, high):
    """CMA-327: where a value sits against the supported range, as a labels.json key: below or above it, else near the
    bottom, in the middle or near the top (by thirds)."""
    if value < low:
        return "pos_below"
    if value > high:
        return "pos_above"
    third = (high - low) / 3
    return "pos_bottom" if value <= low + third else "pos_top" if value >= high - third else "pos_middle"


# --- where asking sits: facts, never a suggested price ----------------------------------------------------------------

JUST_OUTSIDE = 0.005  # asking within 0.5% of an end of the range (about $2,400 at $475,000) is "just" outside it


def asking_position(ask, low, high, median_shown):
    """Where the asking price sits against the supported range and the median adjusted value: above or below the range
    by how much, else above, below or at the median. {key, amount, line}: the line is page 1's sentence."""
    near = JUST_OUTSIDE * low  # a gap this small reads as at the edge, said with its amount, never as a real gap
    if ask > high:
        key, amt = ("sum_pos_just_above" if ask - high <= near else "sum_pos_above"), ask - high
    elif ask < low:
        key, amt = ("sum_pos_just_below" if low - ask <= near else "sum_pos_below"), low - ask
    elif ask > median_shown:
        key, amt = "sum_pos_over_median", ask - median_shown
    elif ask < median_shown:
        key, amt = "sum_pos_under_median", median_shown - ask
    else:
        key, amt = "sum_pos_at_median", 0
    return {"key": key, "amount": amt, "amount_display": money(amt), "line": t(key, amt=money(amt))}


def appraisal_line(ask, high):
    """When asking is above the supported range: the gap between asking and an appraisal at the range's top, which a
    financed buyer covers in cash or settles with the seller. A fact about the price, not advice. Empty otherwise."""
    return t("line_appraisal_gap", top=money(high), gap=money(ask - high)) if ask > high else ""


def _warner():
    """(warnings, keys, warn): warn(key, *texts) adds each text with a stable key, so a test can tell which warning
    fired without matching its sentence (TEST-2); `warning_keys` runs parallel to `warnings`."""
    texts, keys = [], []

    def warn(key, *items):
        texts.extend(items)
        keys.extend([key] * len(items))
    return texts, keys, warn


AS_IS = re.compile(r"\bas[\s-]+is\b", re.I)
AS_IS_SELLER = re.compile(r"\b(seller|owner|listing|prefer\w*|want\w*|wish\w*|requir\w*|insist\w*|offered|being sold)\b",
                          re.I)
CONDITIONAL = re.compile(r"\b(if|whether|unless)\b", re.I)
SENTENCE = re.compile(r"(?<=[.!?])[\"')\]]*\s+")


def private_field_warnings(R):
    """CMA-326: the seller's As-Is preference sits in the 360's Realtor Information and Realtor Remarks, which never go
    in a client file (listing-sheet.md). Warns `as_is_private` on a judgment sentence that states it (names the seller,
    the listing or a preference) without an "if", unless `subject.as_is_public` says the public remarks or the flyer
    say As-Is. Other listings (comps, competition) aren't checked."""
    if (R.get("subject") or {}).get("as_is_public"):
        return []
    out = []
    for pattern in JUDGMENT:
        if pattern.startswith(("comps.", "competition.")):
            continue
        for path, text in _walk(R, _parts(pattern), ""):
            if not isinstance(text, str):
                continue
            for sentence in SENTENCE.split(re.sub(r"<[^>]+>", "", text)):
                if AS_IS.search(sentence) and AS_IS_SELLER.search(sentence) and not CONDITIONAL.search(sentence):
                    out.append(("as_is_private", f"{path} says {sentence.strip()!r}: the seller's As-Is preference is "
                                "Realtor Information, for the agent only. Write it conditionally (\"If the offer is "
                                "written on the As-Is contract, ...\") and put the preference in the reply's for-you-only "
                                "line, or set subject.as_is_public when the public remarks or the flyer say As-Is."))
                    break
    return out


def end_sentence(text):
    """CMA-329: a final period for wording that completes a sentence ("This assumes: ..."), when it has none."""
    s = str(text or "").rstrip()
    return s if not s or re.search(r"[.!?][\"')\]]*$", re.sub(r"<[^>]+>", "", s)) else s + "."


def export_stats(R, homes):
    """(mls.market_stats or None, the market numbers the report and handoff quote) from the export: the recent sales'
    sale-to-original-list, days on market and seller-paid costs, months of supply and the active count. Both stages use
    it, so the gut check and the report see the same market."""
    if not homes:
        return None, {}
    s = R["subject"]
    address = s.get("mls_address", s["address"])
    st = mls.market_stats(homes, {**mls.subject_facts(homes, address), "address": address, "living_area": s.get("sqft"),
                                  "private_pool": bool(s.get("pool")), "subdivision": s.get("subdivision"),
                                  **({"property_type": s["property_type"]} if s.get("property_type") else {})},
                          split_date=cma.default_split(R, homes).isoformat(), as_of=R.get("as_of"),
                          exclude_address=address)
    recent = st["sold_recent"]
    return st, {k: v for k, v in {
        "split_date": st["window"]["split_date"],
        "sale_to_original_list_recent": recent.get("median_sale_to_original_list"),
        "median_days_recent": recent.get("median_days_on_market"),
        "share_with_seller_paid_costs_recent": recent.get("share_with_seller_paid_costs"),
        "median_seller_paid_recent": recent.get("median_seller_paid_when_paid"),
        "months_supply": st["months_supply_at_recent_pace"],
        "active_count": st["active_count"]}.items() if v is not None}


# --- the gut check ----------------------------------------------------------------------------------------------------

def comps_first(R, market, homes=()):
    """CMA-110: the adjusted comps alone, before the report, for a gut check or to set the range from: the median
    adjusted value, the spread, where asking sits and the outlier and adjustment warnings. Writes no handoff. With
    `history.events` it also counts the history (CMA-201). The gut check quotes this same supported range: one range,
    the full report's, never a second wording of it."""
    R = copy.deepcopy(R)
    _require(R, "subject.address", "subject.list_price", "comps.cards")
    errors = schema_errors(R)
    if errors:
        raise ReportError(stop_message(errors))
    warnings, warning_keys, warn = _warner()
    comp_info = prepare_comps(R, homes, warn, market)[3]
    warn("thin_comps", *comp_count_warnings(R["comps"]["cards"]))
    s, values = R["subject"], [c["adjusted"] for c in R["comps"]["cards"]]
    median_adjusted = statistics.median(values)
    rng = supported_range(R, values, market)
    for key, text in cma.range_warnings(rng, values, market):
        warn(key, text)
    shown = median_rounded(median_adjusted, len(values))
    hist, hwarn = history_stats(R, R.get("as_of") or date.today().isoformat())
    for key, text in hwarn:
        warn(key, text)
    warn("export_mls_mismatch", *export_mls_warning(R, homes))
    return {
        "ok": True, "stage": "comps",
        "next": "Write bottom_line.why and add costs, then run compute.py again for the payments and the handoff.",
        "range": {"low": rng["low"], "high": rng["high"], "display": fmt.range(rng["low"], rng["high"]),
                  "override": rng["override"]},
        "subject": {"address": s["address"], "list_price": s["list_price"], "list_price_display": money(s["list_price"])},
        "median_adjusted": median_adjusted, "median_adjusted_display": money(shown),
        "adjusted_min": min(values), "adjusted_max": max(values),
        "asking_vs_median": s["list_price"] - median_adjusted,
        "asking_vs_median_display": money(abs(s["list_price"] - shown)),
        "asking_position": asking_position(s["list_price"], rng["low"], rng["high"], shown),
        "history": hist,
        "comps_table": [{"address": cma.display_address(r[0]), "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in R["comps"].get("summary_rows", [])],
        "settled": cma.selection_lines(comp_info, t, money),  # each sale set aside or kept, as the report will say it
        "warnings": warnings,
        "warning_keys": warning_keys,
        "market_notes": market.notes,
    }


# --- the market ---------------------------------------------------------------------------------------------------

def market_section(st):
    """The market table (before and since the split) and its counts, from the export's stats (mls.market_stats)."""
    if not st:
        return None
    w, early, recent = st["window"], st["sold_early"], st["sold_recent"]
    cols = ["", *fmt.period_labels(w)]

    def row(key, f, field):
        vals = [p.get(field) for p in (early, recent)]
        return [L[key]] + [f(v) if v is not None and p.get("n") else fmt.EMPTY for v, p in zip(vals, (early, recent))]
    days = lambda v: t("mk_days_value", n=fmt.num(v))  # noqa: E731
    rows = [[L["th_mk_sold"], fmt.num(early.get("n", 0)), fmt.num(recent.get("n", 0))],
            row("th_mk_price", money, "median_price"),
            row("th_mk_ratio", lambda v: fmt.pct(v, 1, fixed=True), "median_sale_to_original_list"),
            row("th_mk_days", days, "median_days_on_market"),
            row("th_mk_paid_share", lambda v: fmt.pct(v, 0), "share_with_seller_paid_costs")]
    if any(p.get("median_seller_paid_when_paid") for p in (early, recent)):
        rows.append([L["th_mk_paid"]] + [money(p["median_seller_paid_when_paid"]) if p.get("median_seller_paid_when_paid")
                                         else fmt.EMPTY for p in (early, recent)])
    supply = st.get("months_supply_at_recent_pace")
    n_all = st["sold_all"]["n"]
    intro = t("line_market_intro", n=fmt.num(n_all), first=fmt.date_short(w["first_close"]),
              last=fmt.date_short(w["last_close"]), active=fmt.num(st["active_count"]),
              supply=t("line_market_supply", months=fmt.months(supply)) if supply is not None else "")
    intro = intro[:1].upper() + intro[1:]
    return {"intro": intro, "columns": cols, "rows": rows}


def key_stats(C, hist, stats, as_of):
    """Page 1's three key numbers, from what the report has, in this order: the recent sale-to-original-list, the
    history's active days, months of supply, the adjusted span (the median adjusted value is in page 1's hero)."""
    out = []
    if stats.get("sale_to_original_list_recent") is not None:
        out.append((fmt.pct(stats["sale_to_original_list_recent"], 1, fixed=True),
                    t("sum_tile_ratio", since=cma.day_words(fmt.to_date(stats["split_date"])))))
    if hist:
        cuts = (L["sum_cuts_none"] if not hist["price_cuts"] else L["sum_cuts_one"] if hist["price_cuts"] == 1
                else t("sum_cuts_many", n=fmt.num(hist["price_cuts"])))
        out.append((hist["display"]["active_days"], t("sum_tile_days", since=month_since(hist["first_listed"], as_of), cuts=cuts)))
    if stats.get("months_supply") is not None:
        out.append((fmt.months(stats["months_supply"]), L["sum_tile_supply"]))
    out.append((fmt.range(C["adjusted_min"], C["adjusted_max"], fmt.k), L["sum_tile_span"]))
    return [list(x) for x in out[:3]]


# --- notes ----------------------------------------------------------------------------------------------------------

def cost_notes(N, R, market, pay, tax_rows, insurance):
    """Every assumption and estimate behind the cost tables, each once, in the notes block (notes.Notes)."""
    rows = pay["rows"]
    assumed = [r["label"] for r in rows if r["assumed"]]
    if assumed:  # CMA-227: said once, here, never on a column header
        key = ("note_financing_assumed" if len(assumed) == 1 else
               "note_financing_assumed_all" if len(assumed) == len(rows) else "note_financing_assumed_some")
        N.add("financing_assumed", t(key, labels=cma._and(assumed)), "assumption")
    tb = pay["tax_basis"]
    tj = tax_rows[pay["tax_index"]]
    if tb["estimated"]:
        state_avg = market.source("property_tax.fallback_rate") == "state_average"
        N.add("tax_basis", t("note_tax_rate_state" if state_avg else "note_tax_rate",
                             pct=fmt.pct(market.get("property_tax.fallback_rate"), 1)), "estimate")
    elif tb["unconfirmed"]:
        N.add("tax_basis", t("note_tax_which_higher" if tb["higher"] else "note_tax_which", short=tb["short"]), "assumption")
    millage = [j for j in tax_rows if j["total_mills"] is not None]
    if millage:
        parts = [t("note_tax_millage_part", mills=fmt.num(j["total_mills"], 4, strip=False), label=j["label"]) for j in millage]
        N.add("tax_millage", t("note_tax_millage", parts=cma._and(parts)), "info")
    N.add("tax_assessed", L["note_tax_assessed"], "estimate")
    homestead = R["costs"]["taxes"].get("homestead", True)
    if homestead and market.get("property_tax.exemption_filing_deadline"):
        N.add("tax_file", t("note_tax_file", deadline=market.get("property_tax.exemption_filing_deadline")), "info")
    if homestead and market.get("property_tax.portability"):
        N.add("tax_portability", L["note_tax_portability"], "info")
    if insurance["estimated"]:
        N.add("insurance", t("note_insurance_est", amt=money(insurance["annual"])), "estimate")
    else:
        N.add("insurance", t("note_insurance_given", amt=money(insurance["annual"])), "info")
    mi = []
    progs = {(r["program"], r["down_pct"]) for r in rows}
    conv = sorted(d for p, d in progs if p == "conventional" and d < 0.2)
    if conv:
        mi.append(t("note_mi_pmi", rate=fmt.pct(finance.annual_mi_rate("conventional", conv[0]), 2),
                    down=fmt.pct(conv[0], 2)))
    for key in ("fha", "va", "usda"):
        if any(p == key for p, _ in progs):
            spec = finance.LOAN_PROGRAMS[key]
            mi.append(t("note_mi_" + key, rate=fmt.pct(spec["annual_mi"], 2), upfront=fmt.pct(finance.upfront_fee(
                key, min(d for p, d in progs if p == key)), 2)))
    if mi:
        N.add("mortgage_insurance", t("note_mi", parts=cma._and(mi)), "estimate")
    cs = R["costs"]
    given = _frac(cs, "closing_cost_pct", "costs")
    cash = finance.program(rows[0]["program"]) == "cash"
    prepaids = "" if given is not None or cash else L["note_prepaids"]
    tax_names = [x["label"].lower() for x in finance.loan_taxes(1, market)] if given is None and not cash else []
    taxes_part = t("note_loan_taxes", names=cma._and(tax_names)) if tax_names else ""
    pct = fmt.pct(given if given is not None else finance.buyer_closing_pct(market, cash), 2)
    lender = [r["label"] for r in rows if r["lender_closing_costs"]]
    if lender:
        others = len(lender) < len(rows)
        N.add("closing_costs", t("note_closing_lender", label=lender[0], amt=money(cs.get("closing_costs")),
                                 others=t("note_closing_lender_others", pct=pct, prepaids=prepaids, taxes=taxes_part)
                                 if others else ""), "estimate" if others else "info")
    elif given is not None:
        N.add("closing_costs", t("note_closing_given", pct=pct), "info")
    else:
        N.add("closing_costs", t("note_closing_est", pct=pct, prepaids=prepaids, taxes=taxes_part), "estimate")
    if R["costs"]["payment"].get("note"):  # CMA-226: the agent's note adds to the assumptions, never replaces them
        N.add("payment_note", R["costs"]["payment"]["note"], "info")
    N.add("flood", pay["flood"]["note"], "info")
    if not cash:  # a fact of the loan, not an offer term: what a seller credit may pay for and how much
        N.add("credit_limits", L["note_credit_limits"], "info")
    agreement = _frac(cs, "buyer_broker_agreement_pct", "costs")
    if any(r["bb_short"] for r in rows):
        N.add("buyer_broker", t("note_bb", agreement=fmt.pct(agreement, 2),
                                seller=fmt.pct(_frac(cs, "seller_pays_buyer_broker_pct", "costs", 0), 2)), "info")
    if pay["buyer_cash"]:
        N.add("buyer_cash", t("note_cash", cash=pay["buyer_cash_display"]), "info")


# --- the document model -------------------------------------------------------------------------------------------

def compute(R, market, homes):
    """The document model from report.json (never changed), the market and the export's homes."""
    R = copy.deepcopy(R)
    errors = schema_errors(R)
    if errors:
        raise ReportError(stop_message(errors))
    _require(R, "subject.address", "subject.list_price", "subject.sqft", "comps.cards", "costs.taxes",
             "costs.payment.rate")
    try:
        finance.check_units(R.get("costs") or {}, "costs")
    except ValueError as e:
        raise ReportError(str(e)) from e
    market = market.with_deal(R.get("costs"))  # this home's own numbers (the state's transfer tax, a tax rate)
    n_juris, ji = len(R["costs"]["taxes"].get("jurisdictions") or []), R["costs"]["payment"].get("tax_jurisdiction_index")
    if not n_juris:
        raise ReportError("costs.taxes.jurisdictions needs at least one entry.")
    if n_juris > 1 and not all(str(j.get("short") or "").strip() for j in R["costs"]["taxes"]["jurisdictions"]):
        raise ReportError("costs.taxes.jurisdictions: with two jurisdictions each needs a `short` name (\"City\", "
                          "\"County\"): it tells the two bills apart in the payment table and the notes.")
    if ji is not None and (not isinstance(ji, int) or isinstance(ji, bool) or not 0 <= ji < n_juris):
        raise ReportError(f"costs.payment.tax_jurisdiction_index is {ji!r}: it must be 0 to {n_juris - 1}, the "
                          "position of the jurisdiction the payment uses in costs.taxes.jurisdictions.")
    if not R["costs"]["payment"].get("scenarios"):
        raise ReportError("costs.payment.scenarios needs at least one {type, down_pct}.")
    s, bl = R["subject"], R.setdefault("bottom_line", {})
    as_of = R.get("as_of") or date.today().isoformat()
    warnings, warning_keys, warn = _warner()
    time_info, split, cond_info, comp_info = prepare_comps(R, homes, warn, market)
    warn("thin_comps", *comp_count_warnings(R["comps"]["cards"]))
    cards = R["comps"]["cards"]
    range_info = supported_range(R, [c["adjusted"] for c in cards], market)
    comp_rows = (R.get("competition") or {}).get("rows") or []
    for i, r in enumerate(comp_rows):
        if not isinstance(r, list) or len(r) < 7 or not all(isinstance(r[j], (int, float)) and not isinstance(r[j], bool)
                                                            for j in (2, 3)):
            raise ReportError(f"competition.rows[{i}] should be [address, status, price, sqft, pool, days, notes], "
                              "with price and sqft as plain numbers (474500, not \"$474,500\").")
    for key, text in private_field_warnings(R):  # CMA-326
        warn(key, text)
    values = [c["adjusted"] for c in cards]
    median_adjusted = statistics.median(values)
    median_shown = median_rounded(median_adjusted, len(values))
    scope = cma.adjustment_scope_warning(market, s.get("county"), s["list_price"])  # CMA-10
    if scope:
        warn("adjustment_scope", scope)
    hist, hwarn = history_stats(R, as_of)
    for key, text in hwarn:
        warn(key, text)
    warn("export_mls_mismatch", *export_mls_warning(R, homes))
    st, stats = export_stats(R, homes)

    default_prices(R)
    _require(R, "costs.taxes.purchase_price", "costs.payment.price")
    insurance = insurance_line(R, market)

    # taxes, payments
    tax_rows = taxes(R, market)
    if ji is None:  # CMA-204: with the district unconfirmed, the payment uses the higher bill (the conservative one)
        ji = max(range(n_juris), key=lambda i: (tax_rows[i]["annual"] or 0, -i))
    for j in tax_rows:
        if j["problem"]:
            warn("tax_problem", j["problem"])
        # a jurisdiction's label completes "if the home is …" (report-data.md), so every sentence naming one says that
        if j["annual"] is None:
            warn("tax_no_rate", f"No millage or tax rate if the home is {j['label']}: add school_mills and total_mills.")
        elif j["estimated"]:
            warn("tax_estimated", f"The tax if the home is {j['label']} is estimated from the market's average rate; "
                 "find the millage if you can.")
    if any(j["annual"] is None for j in tax_rows):
        raise ReportError("Taxes couldn't be estimated for every jurisdiction: add school_mills and total_mills (or a "
                          "district the market knows) for each.")
    pay = payments(R, market, tax_rows, ji, insurance, median_shown)
    for key, text in cma.range_warnings(bl, values, market):  # CMA-296
        warn(key, text)
    cash = R["costs"].get("buyer_cash")
    first = pay["rows"][0]
    if first["cash_short"]:
        warn("cash_short", f"At {money(pay['price'])}, cash to close in the {first['label']} column (down payment plus "
             f"closing costs) is about {money(first['cash_to_close'])}, {money(first['cash_short'])} more than the "
             f"buyer's {money(cash)}. Say so in the reply (another loan program may fit); a price and seller "
             "concessions that fit are the offer's to work out, not this report's.")
    elif first["cash_left"] is not None:
        warn("cash_tight", f"At {money(pay['price'])}, cash to close in the {first['label']} column is about "
             f"{money(first['cash_to_close'])}, leaving only {money(first['cash_left'])} of the buyer's {money(cash)}: "
             "say so, and have the lender confirm the closing costs before the offer.")
    for r in pay["rows"][1:]:  # CMA-217, CMA-236: a comparison the buyer can't afford is noise
        if r["cash_short"]:
            warn("scenario_over_cash", f"The {r['label']} scenario needs about {money(r['cash_to_close'])} to close "
                 f"({money(r['cash_down'])} down plus closing costs), more than the buyer's {money(cash)}: drop it or "
                 "replace it with a program that fits (costs.md).")

    # the export's chart points and trend (its market stats are above)
    address = s.get("mls_address", s["address"])
    pts = cma.scatter_points(homes, R.get("scatter") or {}, s["sqft"], address, [c["address"] for c in cards]) \
        if homes else None
    fit = pts[2] if pts else None

    # competition: a listing's price adjusted to this home, and where it sits in the range (CMA-327)
    cp = R.get("competition") or {}
    adjustments = cp.get("adjustments") or {}
    if not isinstance(adjustments, dict):
        raise ReportError("competition.adjustments should be {address as in competition.rows: [{label, amount}]}.")
    competing, comp_table = [], []
    for address_, items in adjustments.items():
        if not any(mls.same_address(r[0], address_) for r in comp_rows):
            raise ReportError(f"competition.adjustments names {address_!r}, which isn't in competition.rows.")
        if not isinstance(items, list) or not all(isinstance(a, dict) and isinstance(a.get("amount"), (int, float))
                                                  and not isinstance(a.get("amount"), bool) for a in items):
            raise ReportError(f"competition.adjustments[{address_!r}] should be a list of {{label, amount}}, the amount "
                              "a signed plain number (25000).")
    for r in comp_rows:
        note = str(r[6] or "")
        items = next((v for k, v in adjustments.items() if mls.same_address(r[0], k)), None)
        if items is not None:
            value = r[2] + sum(a["amount"] for a in items)
            pos = t("comp_position", position=L[range_position(value, bl["low"], bl["high"])])
            note = " ".join(x for x in (note, t("line_comp_adjusted", amount=money(value), position=pos)) if x)
            competing.append({"address": r[0], "price": r[2], "adjusted": value, "adjusted_display": money(value),
                              "range_position": pos})
        comp_table.append([cma.display_address(r[0]), r[1], money(r[2]), fmt.num(r[3]), r[4],
                           fmt.num(r[5]) if isinstance(r[5], (int, float)) and not isinstance(r[5], bool) else r[5], note])

    # the document model
    rng = {"low": bl["low"], "high": bl["high"], "width": bl["high"] - bl["low"],
           "midpoint": fmt.half_up((bl["low"] + bl["high"]) / 2), "display": fmt.range(bl["low"], bl["high"]),
           "display_k": fmt.range(bl["low"], bl["high"], fmt.k)}
    rng["midpoint_display"] = money(rng["midpoint"])
    rng["cap"] = cma.range_width(median_adjusted, market)["cap"]
    pos_key = range_position(s["list_price"], bl["low"], bl["high"])
    rng["asking_position"] = {"pos_above": "above the range", "pos_below": "below the range"}.get(pos_key, "inside the range")
    C = {"ok": True, "stage": "full", "sample": bool(R.get("sample")),
         "data_source": {"mls": market.mls, "as_of": as_of, "as_of_display": fmt.date_long(as_of), "export": bool(homes)},
         "prepared_date": prepared_date(R.get("prepared_date"), as_of),
         "range": rng, "median_adjusted": median_adjusted, "median_shown": median_shown,
         "median_adjusted_display": money(median_shown), "adjusted_min": min(values), "adjusted_max": max(values)}
    C["subject"] = subject_model(s)
    C["asking_position"] = asking_position(s["list_price"], bl["low"], bl["high"], median_shown)
    C["bottom_line"] = {"line": " ".join(x for x in (C["asking_position"]["line"],  # page 1's own words, never a second
                                                     t("line_bottom", median=C["median_adjusted_display"]),  # wording
                                                     appraisal_line(s["list_price"], bl["high"])) if x),
                        "why": bl.get("why", "")}
    rng["override"] = range_info["override"]
    if range_info["override"]:  # the agent's own range, said once beside it, with the rule's for comparison
        C["bottom_line"]["line"] += " " + t("line_range_override", rule=fmt.range(range_info["rule_low"],
                                            range_info["rule_high"]), reason=end_sentence(range_info["reason"]))
    C["history"] = hist
    C["history_section"] = history_section(hist, as_of)
    if C["history_section"]:
        C["history_section"]["takeaway"] = (R.get("history") or {}).get("takeaway", "")
    comps = R["comps"]
    C["comps"] = {
        "intro": comps.get("intro", ""),
        "count_line": comps_count_line(cards, homes, split),
        "settled": " ".join(cma.selection_lines(comp_info, t, money)),
        "method": cma.adjustment_summary(cards, time_info, money, cond_info), "method_note": comps.get("method_note", ""),
        "cards": comp_cards(cards, homes), "lean": comps.get("lean", ""),
        "table": [[cma.display_address(r[0]), money(r[1]), money(r[2]), money(r[3])] for r in comps["summary_rows"]],
        "subject_row": [L["subject_row"], money(s["list_price"]), fmt.EMPTY, f'{L["range_word"]} {rng["display_k"]}'],
        # owner decision (2026-10-13): this home's own card first in the grid, what every comp is adjusted to
        "subject_card": {**cma.subject_card(R["subject"], comp_info, t, as_of), "tag": L["sc_tag"],
                         "address": cma.display_address(s["address"]), "price": t("sc_price", price=money(s["list_price"])),
                         "note": L["sc_note"]}}
    C["comps_table"] = [{"address": cma.display_address(r[0]), "sold_display": money(r[1]), "adjusted_display": money(r[3])}
                        for r in comps["summary_rows"]]
    C["time_adjustment"] = time_info
    C["adjustment_summary"] = cma.adjustment_summary(cards, time_info, money, cond_info)
    C["condition"] = cond_info
    C["scatter"] = scatter_model(R, s, pts, fit, bl) if pts else None
    C["trend"] = ({"at_subject": fit["at_subject"], "at_subject_display": money(fit["at_subject"], 1000), "r2": fit["r2"],
                   "r2_key": mls.r2_key(fit["r2"])} if fit else None)
    C["competition"] = {"intro": cp.get("intro", ""), "rows": comp_table}
    C["competition_estimates"] = competing
    C["market"] = market_section(st)
    if C["market"]:
        C["market"]["bullets"] = list((R.get("market") or {}).get("bullets") or [])
    elif (R.get("market") or {}).get("bullets"):
        C["market"] = {"intro": "", "columns": [], "rows": [], "bullets": list(R["market"]["bullets"])}
    C["market_stats"] = stats
    C["taxes"] = tax_rows
    C["current_bill"] = R["costs"]["taxes"].get("current_bill")
    C["current_bill_display"] = money(C["current_bill"]) if C["current_bill"] else None
    C["payments"] = pay
    C["costs"] = costs_model(R, market, pay, tax_rows, C)
    N = notes.Notes()
    cost_notes(N, R, market, pay, tax_rows, insurance)
    if comp_info.get("national_rates"):  # owner decision 2026-10-13: national rates where none are built in, said once
        N.add("national_rates", t("note_national_rates", kinds=cma._and(comp_info["national_rates"])), "estimate")
    reply = [it for it in N.items("chat") if it[2] in REPLY_KINDS]
    C["notes"] = N.pdf()
    C["note_keys"] = [k for k, _, _ in N.items("chat")]
    C["assumptions"] = [text for _, text, _ in reply]
    C["assumption_keys"] = [k for k, _, _ in reply]
    C["chat_notes"] = [text for _, text, k in N.items("pdf") if k not in REPLY_KINDS]
    C["watch"] = {"items": list((R.get("watch") or {}).get("items") or []),
                  "questions": list((R.get("watch") or {}).get("questions") or [])}
    C["method"] = method_model(R, st, homes)
    C["notices"] = cma.report_notices(C)
    C["summary"] = summary_model(R, C, hist, stats, as_of)
    C["handoff"] = handoff.build(
        side="buyer", as_of=as_of, source="buyer-cma",
        subject={**{k: v for k, v in {"address": s["address"], "city": s.get("city"), "state": market.state,
                                      "county": s.get("county"), "sqft": s["sqft"], "beds": s.get("beds"),
                                      "baths": s.get("baths"), "year_built": s.get("year_built"), "pool": s.get("pool"),
                                      "list_price": s["list_price"]}.items() if v is not None},
                 # CMA-111: the tax this report computed for the buyer, so the offer's payment matches it
                 **handoff.subject_facts(annual_tax=R["costs"]["taxes"].get("current_bill"),
                                         school_mills=tax_rows[ji]["school_mills"], total_mills=tax_rows[ji]["total_mills"],
                                         homestead=R["costs"]["taxes"].get("homestead", True),
                                         flood_zone=R["costs"]["payment"].get("flood_zone") or s.get("flood_zone")
                                         or fact_value(s, "flood zone"),
                                         hoa_monthly=s.get("hoa_monthly"), hoa_frequency=s.get("hoa_frequency"),
                                         roof_year=s.get("roof_year"),
                                         # CMA-328: the history's counts since the last sale, for the offer's outlook
                                         dom=(hist or {}).get("active_days"), price_cuts=(hist or {}).get("price_cuts"),
                                         # the payment's premium and its price, so the offer's payment uses the same one;
                                         # the worksheet's legal description and tax ID
                                         insurance_annual=insurance["annual"], insurance_price=pay["price"],
                                         insurance_estimated=bool(insurance["estimated"]),
                                         rate=pay["rate"], rate_week=R["costs"]["payment"].get("rate_week"),
                                         legal_description=s.get("legal_description"), parcel_id=s.get("parcel_id"))},
        value={"low": bl["low"], "high": bl["high"], "midpoint": rng["midpoint"], "median_adjusted": median_adjusted},
        comps=[{"address": r[0], "sold_price": r[1], "seller_paid": r[2], "adjusted": r[3]} for r in comps["summary_rows"]],
        market=stats,
        market_profile={"state": market.state, "mls": market.mls},
    )
    problems = N.label_problems(all_labels(C))
    if problems:
        raise ReportError("These labels carry a note (a report says that once, in its notes): "
                          + "; ".join(f"{lbl!r} {why}" for lbl, why in problems) + ". Rename them.")
    C["warnings"], C["warning_keys"], C["market_notes"] = warnings, warning_keys, market.notes
    C["_homes"], C["_points"] = homes, pts
    return C


def prepared_date(value, as_of):
    """The date on the report: a YYYY-MM-DD date written out, a date already written out as given, else the as-of date."""
    if value in (None, ""):
        return fmt.date_long(as_of)
    return fmt.date_long(value) if fmt.to_date(value) else str(value)


def subject_model(s):
    """The home's facts: the script's (list price, price per sq ft, beds and baths, living area) then the listing's
    own (lot, built, pool, garage, HOA, flood zone) as written; the page-1 facts line."""
    facts = [[L["fact_list_price"], money(s["list_price"])],
             [L["fact_ppsf"], money(s["list_price"] / s["sqft"])]]
    if s.get("beds") is not None and s.get("baths") is not None:
        facts.append([L["fact_beds"], t("fact_beds_value", beds=fmt.num(s["beds"]), baths=fmt.num(s["baths"], 1))])
    facts.append([L["fact_area"], t("fact_area_value", sqft=fmt.num(s["sqft"]))])
    mine = {str(f[0]).lower() for f in facts}
    facts += [[str(a), str(v)] for a, v in (s.get("facts") or []) if str(a).lower() not in mine][:10 - len(facts)]
    line = []
    if s.get("beds") is not None:
        line.append(t("hf_beds", n=fmt.num(s["beds"])))
    if s.get("baths") is not None:
        line.append(t("hf_baths", n=fmt.num(s["baths"], 1)))
    line.append(t("hf_sqft", n=fmt.num(s["sqft"])))
    if s.get("pool"):
        line.append(L["hf_pool"])
    if s.get("year_built"):
        line.append(t("hf_built", year=s["year_built"]))
    return {"address": s["address"], "locality": s.get("locality", ""), "list_price": s["list_price"],
            "list_price_display": money(s["list_price"]), "facts": facts, "summary_facts": line,
            "summary": s.get("summary", ""), "mls_address": s.get("mls_address", s["address"]), "sqft": s["sqft"]}


def scatter_model(R, s, pts, fit, bl):
    """What the chart says in words: the script's intro and captions, the model's takeaway; the chart itself is
    drawn by render.py from these same points (cma.scatter_points)."""
    sc = R.get("scatter") or {}
    lo, hi = s["sqft"] * sc.get("min_size_ratio", 0.6), s["sqft"] * sc.get("max_size_ratio", 1.4)
    excluded = pts[1]
    parts = []
    for reason in ("size", "price"):
        n = sum(e[3] == reason for e in excluded)
        if n:
            parts.append(L[f"excluded_{reason}_one"] if n == 1 else t(f"excluded_{reason}_many", n=number_word(n).capitalize()
                                                                    if n < 13 else fmt.num(n)))
    out = {"heading": sc.get("heading") or L["h_scatter"],
           "intro": t("line_scatter_intro", lo=fmt.num(fmt.half_up(lo, 100)), hi=fmt.num(fmt.half_up(hi, 100))),
           "excluded": " ".join(parts), "takeaway": sc.get("takeaway", ""),
           "subject_label_pos": sc.get("subject_label_pos", "left"),
           "callouts": [{"address": c["address"], "label": cma.display_address(c["address"]), "side": c.get("side", "right")}
                        for c in sc.get("callouts") or []],
           "subject_label": cma.display_address(s["address"]),
           "ratios": {k: sc[k] for k in ("min_size_ratio", "max_size_ratio", "fit_size_ratio") if k in sc},
           "band_label": f'{L["band"]} {fmt.range(bl["low"], bl["high"], fmt.k)}', "trend": None, "r2_line": ""}
    if fit:
        side, gap = cma.trend_position(s["list_price"], fit["at_subject"])
        vals = {"price": money(s["list_price"]), "gap": money(gap, 1000)}
        out["trend"] = {"side": side, "head": t("trend_head_" + side, **vals),
                        "body": " ".join(x for x in (L["trend_caption"], L["trend_" + side]) if x)}
        if fit.get("r2") is not None:
            out["r2_line"] = t("line_r2", share=L[mls.r2_key(fit["r2"])])
    return out


def costs_model(R, market, pay, tax_rows, C):
    """The cost section's script wording and rows: taxes and the payment table."""
    tx = R["costs"]["taxes"]
    homestead = tx.get("homestead", True)
    bill, year = tx.get("current_bill"), tx.get("current_year")
    ji = pay["tax_index"]
    yours = tax_rows[ji]["annual"]
    higher = bool(bill) and market.get("property_tax.reassessed_on_sale") and yours > bill * 1.05
    intro = [t("line_tax_bill", bill=money(bill), year=year) if bill and year else
             t("line_tax_bill_no_year", bill=money(bill)) if bill else L["line_tax_no_bill"]]
    if market.get("property_tax.reassessed_on_sale") and market.state:
        intro.append(t("line_tax_resets", state=profiles.STATES.get(market.state, market.state)))
    if homestead and market.get("property_tax.primary_residence_exemptions"):
        intro.append(L["line_tax_homestead"])
    seller_row = t("seller_bill", year=year) if year else L["seller_bill_no_year"]
    trows = [[seller_row, money(bill), money(bill / 12)] if bill else [seller_row, L["not_available"], fmt.EMPTY]]
    trows += [[t("your_bill", label=j["label"]), "≈ " + j["annual_display"], "≈ " + j["monthly_display"]] for j in tax_rows]
    basis = price_basis(tx["purchase_price"], R, C["median_shown"])
    taxes_m = {"heading": L["h_taxes_higher"] if higher else L["h_taxes"], "intro": " ".join(intro),
               "header": t("tax_header", price=money(tx["purchase_price"]), homestead=homestead_label(homestead),
                           basis=basis_words(basis)),
               "rows": trows, "escrow_lead": L["line_escrow_lead"], "escrow": L["line_escrow"]}

    rows = pay["rows"]
    week = R["costs"]["payment"].get("rate_week")
    n = len(rows)
    intro = (t("line_pay_intro", n=number_word(n).capitalize(), rate=pay["rate_display"],
               week=t("line_pay_week", date=fmt.date_long(week)) if week else "") if n > 1 else
             t("line_pay_intro_one", rate=pay["rate_display"], week=t("line_pay_week", date=fmt.date_long(week)) if week else ""))
    table = [[L["pay_cash"]] + [money(r["cash_down"]) for r in rows],
             [L["pay_closing"]] + [money(r["closing_costs"]) for r in rows]]
    if any(r["bb_short"] for r in rows):
        table.append([L["pay_bb"]] + [money(r["bb_short"]) for r in rows])
    table.append([L["pay_cash_close"]] + [money(r["cash_to_close"]) for r in rows])
    cash_row = len(table) - 1
    table += [[L["pay_pi"]] + [money(r["pi"]) for r in rows],
              [pay["tax_label"]] + [money(r["tax"]) for r in rows],
              [L["pay_ins"]] + [money(r["ins"]) for r in rows],
              [L["pay_flood"]] + [money(r["flood"]) if r["flood"] is not None else L["pay_flood_quote"] for r in rows],
              [L["pay_mi"]] + [money(r["mi"]) for r in rows],
              [L["pay_hoa"]] + [money(r["hoa"]) for r in rows],
              [L["pay_total"]] + [money(r["total"]) for r in rows]]
    total_row = len(table) - 1
    if pay["at_median"]:
        table.append([t("pay_at_median", price=pay["at_median"]["price_display"])]
                     + [money(v) for v in pay["at_median"]["totals"]])
    if pay["alt_jurisdiction"]:
        table.append([t("pay_if", short=pay["alt_jurisdiction"]["short"])] + [money(v) for v in pay["alt_jurisdiction"]["totals"]])
    payment_m = {"intro": intro,
                 "header": [t("pay_header", price=pay["price_display"], basis=basis_words(pay["price_basis"]))]
                 + [r["label"] for r in rows],
                 "rows": table, "cash_row": cash_row, "total_row": total_row,
                 "alt_rows": list(range(total_row + 1, len(table))),
                 "cash_flags": [t("cash_short", amt=r["cash_short_display"], cash=pay["buyer_cash_display"])
                                if r["cash_short"] else "" for r in rows],
                 "per_10k": t("line_per10k", amt=money(pay["per_10k"], 5)),
                 "note": R["costs"]["payment"].get("note", "")}
    return {"taxes": taxes_m, "insurance": (R["costs"].get("insurance") or {}).get("drivers", ""),
            "payment": payment_m}


def method_model(R, st, homes):
    lines = []
    if st:
        w, counts = st["window"], st.get("status_counts") or {}
        ended = sum(v for k, v in counts.items() if k not in ("SOLD", "ACTIVE", "PENDING"))
        lines.append(t("line_sources_export", n=fmt.num(st["sold_all"]["n"]), first=fmt.date_short(w["first_close"]),
                       last=fmt.date_short(w["last_close"]),
                       listings=t("line_sources_listings", active=fmt.num(counts.get("ACTIVE", 0)),
                                  pending=fmt.num(counts.get("PENDING", 0)), ended=fmt.num(ended))))
    if R.get("sources"):
        lines.append(t("line_sources_other", list=cma._and([str(x) for x in R["sources"]])))
    lines.append(L["line_shelf_life"])
    return {"lines": lines}


def summary_model(R, C, hist, stats, as_of):
    """Page 1: the model's headline, reasons, checks and next step, with the script's key numbers and cost rows."""
    sp = R.get("summary_page") or {}
    pay = C["payments"]
    first = pay["rows"][0]
    tiles = key_stats(C, hist, stats, as_of)
    basis = basis_words(pay["price_basis"])
    if first["program"] == "cash":
        tile_label = t("sum_payment_tile_cash", price=pay["price_display"], basis=basis)
    else:
        tile_label = t("sum_payment_tile", price=pay["price_display"], basis=basis, down=fmt.pct(first["down_pct"], 2))
    tiles.append([first["total_display"], tile_label])
    tb = pay["tax_basis"]
    tax = C["taxes"][pay["tax_index"]]
    yours = t("sum_tax_yours_if" if tb["unconfirmed"] else "sum_tax_yours", short=tb["short"],
              homestead=homestead_label(tb["homestead"]))
    bill = C["current_bill"]
    rows = [[L["sum_tax_now"], money(bill) + L["per_year"] if bill else L["not_available"], ""],
            [yours, "≈ " + tax["annual_display"] + L["per_year"], ""],
            [t("sum_pay_row", label=first["label"]), first["total_display"] + L["per_month"], ""],
            [t("sum_cash_row", label=first["label"]), first["cash_to_close_display"],
             t("cash_short", amt=first["cash_short_display"], cash=pay["buyer_cash_display"]) if first["cash_short"] else ""]]
    if pay["at_median"]:  # the same payment at what the comps support, a fact beside asking
        rows.insert(3, [t("sum_pay_median_row", price=pay["at_median"]["price_display"]),
                        money(pay["at_median"]["totals"][0]) + L["per_month"], ""])
    return {"label": sp.get("label") or L["sum_label"], "headline": sp.get("headline", ""),
            "tiles": tiles, "why": list(sp.get("why") or []), "check_first": [list(x) for x in sp.get("check_first") or []],
            "next_step": sp.get("next_step", ""), "cost_rows": rows,
            "cost_note": t("line_costs_note", price=pay["price_display"], basis=basis),
            "value_line": t("sum_value_line", median=C["median_adjusted_display"],
                            ask=C["subject"]["list_price_display"]),
            "position_line": C["asking_position"]["line"],
            "dot_asking": t("dot_asking", price=C["subject"]["list_price_display"]),
            "dot_median": t("dot_median", price=C["median_adjusted_display"]),
            "comps": [{"address": c["address"], "adjusted": c["adjusted"], "adjusted_k": c["adjusted_k"]}
                      for c in C["comps"]["cards"]]}


def all_labels(C):
    """Every label the report prints (headings, headers, row names, tiles, legends), for N.label_problems."""
    out = [r[0] for r in C["subject"]["facts"]] + [x[1] for x in C["summary"]["tiles"]]
    out += [r[0] for r in C["summary"]["cost_rows"]]
    out += C["costs"]["payment"]["header"] + [r[0] for r in C["costs"]["payment"]["rows"]]
    out += [C["costs"]["taxes"]["header"], C["costs"]["taxes"]["heading"]] + [r[0] for r in C["costs"]["taxes"]["rows"]]
    if C["market"]:
        out += C["market"]["columns"] + [r[0] for r in C["market"]["rows"]]
    if C["history_section"]:
        out.append(C["history_section"]["heading"])
    for c in C["comps"]["cards"]:
        out += [ln[0] for ln in c["lines"]]
    return [x for x in out if x]


def load_inputs(R, mls_name=None, data_file=None):
    """Market and MLS records for a report.json (`export` is the path to the MLS export CSV, `export_columns` its
    header map for an MLS that isn't built in). The MLS is `--mls`, else the report's `mls`, else the one built-in MLS
    covering the county (CMA-15). The report itself is never changed."""
    s = R.get("subject") or {}
    market = profiles.load_market(state=s.get("state"), county=s.get("county"), mls=mls_name or R.get("mls"))
    homes = mls.load(mls.resolve_export(R["export"], data_file), market, R.get("export_columns")) if R.get("export") else []
    mls.fill_distances(homes, s.get("mls_address", s.get("address")),
                       (s["latitude"], s["longitude"]) if s.get("latitude") and s.get("longitude") else None)
    return market, homes


def comps_only(R):
    return not any(R.get(k) for k in ("bottom_line", "costs"))


def run(R, mls_name=None, data_file=None):
    """The document model (or the comps-only gut check) from a report dict: render.py's compute step."""
    market, homes = load_inputs(R, mls_name, data_file)
    return comps_first(R, market, homes) if comps_only(R) else compute(R, market, homes)


def public(C):
    """The model as JSON prints it: without the export's homes and chart points (render.py's own)."""
    return {k: v for k, v in C.items() if not k.startswith("_")}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("report")
    ap.add_argument("--out", help="where to write the .cma.json handoff (default: next to report.json, the working "
                                  "folder; never the outputs)")
    ap.add_argument("--mls", help="MLS name, as with stats.py (Stellar is built in)")
    a = ap.parse_args(argv)
    with open(a.report, encoding="utf-8") as f:
        R = json.load(f)
    try:
        result = run(R, a.mls, a.report)
        if result.get("stage") == "full":
            path = os.path.join(a.out or os.path.dirname(os.path.abspath(a.report)),
                                handoff.filename(R["subject"]["address"], "buyer"))
            with open(path, "w", encoding="utf-8") as f:
                json.dump(result["handoff"], f, indent=2)
            result["handoff_file"] = path
        result = public(result)
    except (ReportError, profiles.ProfileError, mls.ExportError, handoff.HandoffError, KeyError, ValueError) as e:
        result = {"ok": False, "problems": [str(e) if not isinstance(e, KeyError) else f"report.json is missing {e}"]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
