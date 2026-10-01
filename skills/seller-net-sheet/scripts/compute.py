"""Compute a seller net sheet (one to three prices) from net-sheet.json.

    python3 scripts/compute.py net-sheet.json [--cma FILE.seller.cma.json] [--mls NAME]

Prints JSON: one column per price, the itemized rows in the PDF's order (brokerage, transfer taxes, title and
closing, prorations, concessions, payoffs), each amount already formatted for the markdown template, plus `notes`
(printed under the table), `assumptions` (tell the agent), `warnings` (fix or tell the agent) and `preliminary`.
render.py builds the PDF from the same result, so chat and file always agree. Every cost comes from
finance.seller_net: this sale's own numbers in `costs`, then the built-in local values, then national estimates.
"""
import argparse
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import finance, handoff, profiles  # noqa: E402

money = finance.money
MAX_SCENARIOS = 3  # three columns still fit on one page
PAYOFF_CUSHION = 500  # a month's interest is added to a statement balance, plus this for payoff and release fees
TAX_BILL_MONTH = 10  # when a market doesn't say (`property_tax.bill_month`): from October a year's bill may be out

# Row groups in page order: (key, label, line keys from finance.seller_net)
GROUPS = (("brokerage", "Brokerage", ("listing_fee", "buyer_broker_fee")),
          ("taxes", "Transfer Taxes", ("transfer_tax", "transfer_surtax")),
          ("title", "Title and Closing", ("owner_title", "title_fees", "estoppel")),
          ("prorations", "Prorations", ("tax_proration",)),
          ("concessions", "Concessions and Other Costs", ("credit", "other")))
SMALL_WORDS = {"a", "an", "and", "of", "on", "or", "the", "to", "for", "in"}
PROPERTY_TYPES = {"single_family": "Single-Family", "condo": "Condo", "townhouse": "Townhouse",
                  "multifamily": "Multifamily", "land": "Land"}
MISSING_WORDS = {"deed transfer tax": "transfer tax (or confirmation there is none)", "HOA estoppel fee": "HOA documents fee",
                 "who pays owner's title": "who customarily pays the owner's title policy", "listing fee": "listing brokerage fee",
                 "buyer's agent fee": "buyer's agent compensation"}


class NetSheetError(ValueError):
    """Something net-sheet.json needs; the message is written for the agent."""


def title_case(text):
    """'municipal_lien_search' -> 'Municipal Lien Search', 'title company quote' -> 'Title Company Quote'."""
    words = str(text).replace("_", " ").split()
    return " ".join(w if i and w.lower() in SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


def pct_text(rate):
    return f"{rate * 100:.2f}".rstrip("0").rstrip(".")


def _date(v, name):
    if v in (None, ""):
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        raise NetSheetError(f"{name} should be a date like 2026-12-15, not {v!r}.") from None


def _amount(v, name):
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v < 0:
        raise NetSheetError(f"{name} should be a dollar amount (a number, no $ or commas), not {v!r}.")
    return v


def _items(v, name):
    """A list of {label, amount} (other costs, other payoffs), checked."""
    if v in (None, []):
        return []
    if not isinstance(v, list) or not all(isinstance(o, dict) and o.get("label") for o in v):
        raise NetSheetError(f"{name} should be a list of {{label, amount}} items, like "
                            '[{"label": "Survey", "amount": 450}].')
    return [{"label": title_case(o["label"]) if str(o["label"]).islower() else o["label"],
             "amount": _amount(o.get("amount") or 0, f"{name} ({o['label']})")} for o in v]


def long_date(d):
    return f"{d:%B} {d.day}, {d.year}"


def short_date(d):
    return f"{d:%b} {d.day}, {d.year}"


def apply_cma(R, h):
    """Fill what the sheet doesn't say from a seller-cma handoff for the same home: the location, the tax bill, HOA dues,
    and the recommended list price when no price was given."""
    if h.get("side") != "seller":
        raise NetSheetError("That CMA was made for a buyer. Use the seller CMA for this home, or leave it out.")
    s, p = h["subject"], R.setdefault("property", {})
    slug = lambda a: re.sub(r"[^a-z0-9]", "", str(a or "").split(",")[0].lower())
    if p.get("address") and slug(p["address"]) != slug(s.get("address")):
        raise NetSheetError(f"The CMA is for {s.get('address')}, not {p['address']}: use a CMA for the same home.")
    for k in ("address", "city", "county", "state"):
        if p.get(k) is None and s.get(k) is not None:
            p[k] = s[k]
    costs = R.setdefault("costs", {})
    if costs.get("annual_tax") is None and s.get("annual_tax"):
        costs["annual_tax"] = s["annual_tax"]
    if p.get("hoa_monthly") is None and s.get("hoa_monthly") is not None:
        p["hoa_monthly"] = s["hoa_monthly"]
    if not R.get("scenarios") and h.get("recommended_list_price"):
        R["scenarios"] = [{"price": h["recommended_list_price"], "label": "Recommended List Price"}]
    if not R.get("mls") and (h.get("market_profile") or {}).get("mls"):
        R["mls"] = h["market_profile"]["mls"]
    return R


def load_market(R, mls_name=None):
    p = R.get("property") or {}
    market = profiles.load_market(state=p.get("state"), county=p.get("county"), mls=mls_name or R.get("mls"))
    return market.with_deal(R.get("costs"))


def scenarios(R):
    xs = R.get("scenarios") or []
    if not xs:
        raise NetSheetError("Give at least one sale price (scenarios: [{\"price\": 450000}]).")
    if len(xs) > MAX_SCENARIOS:
        raise NetSheetError(f"A net sheet compares at most {MAX_SCENARIOS} prices on one page; this one has {len(xs)}. "
                            "Pick the three that matter most.")
    out = []
    for i, x in enumerate(xs, 1):
        price = x.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
            raise NetSheetError(f"scenarios[{i - 1}].price should be the sale price as a number, not {price!r}.")
        own = x.get("closing_date")  # iteration 9 evals 1, 4: a vague date ("mid-December") is marked assumed
        out.append({"price": price, "label": x.get("label"),
                    "credit": _amount(x.get("seller_credit"), f"scenarios[{i - 1}].seller_credit") or 0,
                    "warranty": _amount(x.get("home_warranty"), f"scenarios[{i - 1}].home_warranty") or 0,
                    "repairs": _amount(x.get("repairs"), f"scenarios[{i - 1}].repairs") or 0,
                    "closing": _date(own or R.get("closing_date"), "closing_date"),
                    "closing_assumed": bool(x.get("closing_date_assumed") if own else R.get("closing_date_assumed"))})
    labels = [x["label"] or (money(x["price"]) + (f" with {money(x['credit'])} Credit" if x["credit"] else "")) for x in out]
    for i, x in enumerate(out):  # two columns may not share a name
        x["label"] = labels[i] if labels.count(labels[i]) == 1 else f"{labels[i]} (Option {i + 1})"
    return out


def payoffs(costs):
    """([{key, label, amount}], first mortgage known?, estimated from a balance?)."""
    rows, known, est = [], False, False
    first, balance = _amount(costs.get("mortgage_payoff"), "costs.mortgage_payoff"), costs.get("mortgage_balance")
    if first is None and balance is not None:
        _amount(balance, "costs.mortgage_balance")
        if balance:  # a balance isn't a payoff: add a month's interest and the release fees
            first = round(balance * (1 + (costs.get("mortgage_rate") or 7) / 100 / 12) + PAYOFF_CUSHION)
            est = True
        else:
            first = 0
    if first is not None:
        known = True
        if first:
            rows.append({"key": "payoff", "label": "Mortgage Payoff" + (" (Estimate from Balance)" if est else ""), "amount": first})
    for o in _items(costs.get("other_payoffs"), "costs.other_payoffs"):
        if o["amount"]:
            rows.append({"key": "payoff", "label": o["label"], "amount": o["amount"]})
    return rows, known, est


def title_fee_rows(market, line):
    """The title company fees line, itemized by the fees it adds up (Florida: settlement, title search, municipal lien
    search, recording). A single quote stays one line."""
    fees = market.get("closing_costs.seller_title_fees") or {}
    items = [(k, v) for k, v in fees.items() if v]
    if len(items) < 2 or abs(sum(v for _, v in items) - line["amount"]) > 0.5:
        return [(line["label"], line["amount"])]
    est = " (Estimate)" if market.source("closing_costs.seller_title_fees") == "estimate" else ""
    return [(title_case(k) + est, v) for k, v in items]


def compute(R, market):
    p = R.get("property") or {}
    if not p.get("address"):
        raise NetSheetError("The property's address is needed (property.address).")
    costs = R.get("costs") or {}
    try:
        finance.check_units(costs, "costs")
    except ValueError as e:
        raise NetSheetError(str(e)) from None
    xs = scenarios(R)
    lf = finance.fraction(costs.get("listing_fee_pct"), "costs.listing_fee_pct")
    bf = finance.fraction(costs.get("buyer_broker_fee_pct"), "costs.buyer_broker_fee_pct")
    others = _items(costs.get("other"), "costs.other")
    pay_rows, payoff_known, payoff_est = payoffs(costs)
    payoff_total = sum(r["amount"] for r in pay_rows)
    annual_tax = _amount(costs.get("annual_tax"), "costs.annual_tax")
    bill_paid = costs.get("current_tax_bill_paid")
    due_date = costs.get("tax_bill_due_date")
    try:  # checked before the math: "10-15" or "2026-10-15"
        finance.tax_due_date(date.today(), None, due_date)
    except ValueError as e:
        raise NetSheetError(str(e).replace("The tax bill's due date", "costs.tax_bill_due_date")) from None
    hoa_monthly = _amount(p.get("hoa_monthly"), "property.hoa_monthly")
    has_hoa = bool(p.get("hoa", bool(hoa_monthly)))
    kind = finance.property_type(p.get("property_type"))

    nets = []
    for x in xs:
        extra = list(others)
        if x["warranty"]:
            extra.append({"label": "Home Warranty", "amount": x["warranty"]})
        if x["repairs"]:
            extra.append({"label": "Repairs", "amount": x["repairs"]})
        nets.append(finance.seller_net(x["price"], market, credit=x["credit"], payoff=payoff_total if payoff_known else None,
                                       listing_fee_pct=lf, buyer_broker_fee_pct=bf, has_hoa=has_hoa, other_costs=extra,
                                       annual_tax=annual_tax, closing=x["closing"], bill_paid=bill_paid, prop_type=p.get("property_type"),
                                       tax_due_date=due_date))
    first = nets[0]
    assumed = {a["key"] for a in first["assumed"]}
    bill_month = market.get("property_tax.bill_month") or TAX_BILL_MONTH
    has_tax = any(l["key"] == "tax_proration" for n in nets for l in n["lines"])
    # iteration 9 eval 4: a closing after this year's bill is due assumes it paid (finance.tax_proration)
    paid_assumed = [bool(x["closing"]) and finance.tax_bill_assumed_paid(x["closing"], market, bill_paid, due_date) for x in xs]
    tax_paid_assumed = has_tax and all(paid_assumed)
    tax_assumed = has_tax and bill_paid is None and any(x["closing"] and x["closing"].month >= bill_month and not pa
                                                        for x, pa in zip(xs, paid_assumed))
    tax_mixed = has_tax and any(paid_assumed) and not all(paid_assumed)  # one closing before the due date, one after

    def label(line):
        key, rate = line["key"], line["rate"]
        if key == "listing_fee":
            return f"Listing Brokerage ({pct_text(rate)}%{', Assumed' if key in assumed else ''})"
        if key == "buyer_broker_fee":
            return f"Buyer's Agent Compensation ({pct_text(rate)}%{', Assumed' if key in assumed else ''})"
        if key == "tax_proration" and tax_mixed:
            return "Property Tax Proration (Charge or Credit by Closing Date)"
        if key == "tax_proration" and tax_assumed:
            return "Property Tax Proration (Jan 1 to Closing, Bill Assumed Unpaid)"
        return line["label"]

    # Rows: one per line key across every column (a seller credit may exist in only one), grouped as on the page
    rows = [{"kind": "price", "key": "price", "label": "Sale Price", "amounts": [x["price"] for x in xs]}]
    if len({x["closing"] for x in xs}) > 1:  # different closing dates move the proration: show them
        rows.append({"kind": "info", "key": "closing", "label": "Closing Date",
                     "display": [(short_date(x["closing"]) + (" (Assumed)" if x["closing_assumed"] else "")) if x["closing"]
                                 else "Not set" for x in xs]})
    for gkey, glabel, keys in GROUPS:
        group = []
        for key in keys:
            if key == "other":
                names = list(dict.fromkeys(l["label"] for n in nets for l in n["lines"] if l["key"] == "other"))
                for name in names:
                    group.append({"kind": "line", "key": "other", "label": name,
                                  "amounts": [-sum(l["amount"] for l in n["lines"] if l["key"] == "other" and l["label"] == name)
                                              for n in nets]})
                continue
            line = next((l for n in nets for l in n["lines"] if l["key"] == key), None)
            if line is None:
                continue
            if key == "title_fees":
                for name, amount in title_fee_rows(market, line):
                    group.append({"kind": "line", "key": "title_fees", "label": name, "amounts": [-amount for _ in nets]})
                continue
            group.append({"kind": "line", "key": key, "label": label(line),
                          "amounts": [-next((l["amount"] for l in n["lines"] if l["key"] == key), 0) for n in nets]})
        if group:
            rows.append({"kind": "group", "key": gkey, "label": glabel})
            rows += group
    rows.append({"kind": "subtotal", "key": "total_costs", "label": "Total Seller Costs", "amounts": [-n["total_costs"] for n in nets]})
    finals = [n["net_before_payoff"] - payoff_total for n in nets]
    cash = payoff_known
    if pay_rows:
        rows.append({"kind": "subtotal", "key": "net_before_payoff", "label": "Net Before Payoff",
                     "amounts": [n["net_before_payoff"] for n in nets]})
        rows.append({"kind": "group", "key": "payoffs", "label": "Payoffs"})
        rows += [{"kind": "line", "key": r["key"], "label": r["label"], "amounts": [-r["amount"] for _ in nets]} for r in pay_rows]
    final_label = "Estimated Net to Seller" if cash else "Estimated Net Before Mortgage Payoff"
    rows.append({"kind": "final", "key": "net", "label": final_label, "amounts": finals})
    for r in rows:  # a line one column doesn't have (a seller credit in one option) is an empty cell, not $0
        if "amounts" in r:
            r["display"] = ["—" if r["kind"] == "line" and not a else money(a) for a in r["amounts"]]

    columns = []
    for x, n, final in zip(xs, nets, finals):
        span = max(x["price"], n["total_costs"] + payoff_total)  # the bar's full width: the price, or more when short
        columns.append({"label": x["label"], "price": x["price"], "price_display": money(x["price"]),
                        "closing_date": x["closing"].isoformat() if x["closing"] else None,
                        "total_costs": n["total_costs"], "total_costs_display": money(n["total_costs"]),
                        "costs_pct": n["total_costs"] / x["price"], "costs_pct_display": f"{n['total_costs'] / x['price'] * 100:.1f}%",
                        "net_before_payoff": n["net_before_payoff"], "net_before_payoff_display": money(n["net_before_payoff"]),
                        "payoff_total": payoff_total, "net": final, "net_display": money(final), "short": final < 0,
                        # iteration 9 eval 4: a negative net reads as the cash the seller brings, a positive amount
                        "tile_label": "Cash to Bring to Closing" if final < 0 else final_label,
                        "tile_display": money(-final) if final < 0 else money(final),
                        "bar": {"costs": max(n["total_costs"], 0) / span, "payoffs": payoff_total / span, "net": max(final, 0) / span}})

    # Fact row: the property first, then the inputs the numbers rest on. Missing items drop out, except the ones
    # that make the sheet Preliminary (shown in the risk color).
    facts = []
    st = market.state
    if st:
        place = f"{title_case(str(p['county']).removesuffix(' County'))} County, {st}" if p.get("county") else profiles.STATES.get(st, st)
        facts.append({"text": place})
    else:
        facts.append({"text": "State Not Provided", "risk": True})
    type_assumed = kind in PROPERTY_TYPES and bool(p.get("property_type_assumed"))  # iteration 9 eval 5: from a unit number
    if kind in PROPERTY_TYPES:
        facts.append({"text": PROPERTY_TYPES[kind] + (" (Assumed)" if type_assumed else "")})
    if hoa_monthly:
        facts.append({"text": f"HOA {money(hoa_monthly)}/mo"})
    elif has_hoa:
        facts.append({"text": "HOA Dues Not Provided"})  # iteration 10 eval 5: a bare "HOA" read like a missing value
    elif p.get("hoa") is False or hoa_monthly == 0:
        facts.append({"text": "No HOA"})
    closings = {x["closing"] for x in xs}
    if len(closings) == 1 and xs[0]["closing"]:
        facts.append({"text": f"Closing {short_date(xs[0]['closing'])}" + (" (Assumed)" if xs[0]["closing_assumed"] else "")})
    if not payoff_known:
        facts.append({"text": "Payoff Not Provided", "risk": True})
    elif payoff_total:
        facts.append({"text": f"Payoffs {money(payoff_total)}" if len(pay_rows) > 1 else
                      f"Payoff {money(payoff_total)}" + (" (Estimated)" if payoff_est else "")})
    else:
        facts.append({"text": "No Mortgage"})
    if annual_tax:
        facts.append({"text": f"Taxes {money(annual_tax)}/yr" + (", Paid" if bill_paid else "")})
    if lf is not None and bf is not None:
        facts.append({"text": f"Commission {pct_text(lf + bf)}% Total"})

    # Notes under the table, in sentence case. Assumptions go to the agent in the reply.
    notes, assumptions, warnings = [], [], list(dict.fromkeys(w for n in nets for w in n["warnings"]))
    tax_missing = False
    if type_assumed:
        assumptions.append(f"The property type is assumed {PROPERTY_TYPES[kind].lower()}"
                           + (" from the unit number" if kind == "condo" else "") + ": say if it's something else.")
    dated = [x for x in xs if x["closing"] and x["closing_assumed"]]
    if dated:  # iteration 9 evals 1, 4: a vague closing date is an assumption, said in the reply and marked on the page
        when = " and ".join(dict.fromkeys(short_date(x["closing"]) for x in dated))
        assumptions.append(f"Closing on {when} is assumed: the actual date replaces it (it moves the tax proration).")
    brokerage = any(l["key"] in ("listing_fee", "buyer_broker_fee") for n in nets for l in n["lines"])
    commission_assumed = bool(assumed & {"listing_fee", "buyer_broker_fee"})
    if commission_assumed:
        total = sum(l["rate"] for l in first["lines"] if l["key"] in ("listing_fee", "buyer_broker_fee"))
        notes.append(f"Brokerage is assumed at {pct_text(total)}% in total until the listing agreement sets it.")
        assumptions.append(f"Commission {pct_text(total)}% in total (listing and buyer's agent), assumed: send the listing "
                           "agreement's terms to replace it.")
    if brokerage:
        notes.append(finance.COMMISSION_NOTE)
    if has_tax:
        tax_basis = finance.tax_proration(annual_tax, next(x["closing"] for x in xs if x["closing"]), market, bill_paid)["basis"]
        due = finance.tax_due_date(next(x["closing"] for x in xs if x["closing"]), market, due_date)
        due_text = f"{due:%b} {due.day}" if due else ""
        if bill_paid:
            notes.append(f"Property tax: the seller paid this year's bill ({tax_basis}), so the buyer credits back closing to Dec 31.")
        elif any(paid_assumed):
            notes.append(f"Assumed: this year's tax bill ({tax_basis}) is paid by its {due_text} due date, before closing, so "
                         "the buyer credits back closing to Dec 31. If it's still unpaid at closing, the seller is charged "
                         "from Jan 1 instead.")
            assumptions.append(f"This year's tax bill is assumed paid, since closing is after its {due_text} due date: say "
                               "if it's still unpaid.")
        else:
            notes.append(f"Property tax prorated from Jan 1 to the day before closing ({tax_basis}).")
        if tax_assumed:
            notes.append("Assumed: this year's tax bill is still unpaid at closing. If the seller pays it first, the buyer "
                         "credits back the rest of the year instead.")
            assumptions.append("This year's tax bill is assumed unpaid at closing: say if the seller has paid it.")
    elif market.get("property_tax.paid") == "arrears":
        missing_bits = [w for w, gone in (("the tax bill", not annual_tax), ("the closing date", not any(x["closing"] for x in xs))) if gone]
        notes.append("Not included: this year's property tax proration. Taxes here are paid in arrears, so the seller "
                     f"credits the buyer from Jan 1; add {' and '.join(missing_bits)} to include it.")
        assumptions.append(f"No property tax proration yet: send {' and '.join(missing_bits)} to include it.")
        tax_missing = True
    if "title_fees" in assumed and market.source("closing_costs.seller_title_fees") != "estimate":
        notes.append("Title company fees are typical local charges; the title company's quote replaces them.")
        assumptions.append("Title company fees are the typical local charges: a title quote replaces them.")
    # iteration 11: a built-in estoppel fee is a typical local charge too (a national estimate is labeled on its line)
    if (any(l["key"] == "estoppel" for l in first["lines"]) and market.source("closing_costs.hoa_estoppel_fee") not in ("estimate", "deal")):
        notes.append("The HOA estoppel fee is a typical local charge; the association's fee schedule replaces it.")
    estimates = [a["text"] for a in first["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimates:
        notes.append(f"Estimates, not local figures: {', '.join(estimates)}. Local rates or a title quote replace them.")
        assumptions.append(f"National estimates (no local figures built in): {', '.join(estimates)}.")
    if market.get("closing_costs.owner_title.payer") == "buyer":  # say why there's no owner's title line
        notes.append("The buyer customarily pays the owner's title policy here, so it isn't a seller cost.")
    if "no_transfer_tax" in market.note_codes:  # a no-transfer-tax state: say why there's no line, not just leave it out
        notes.append(f"No state transfer tax in {profiles.STATES.get(st, st)}; a few cities and counties add their own, "
                     "so confirm with the title company.")
    missing = [MISSING_WORDS.get(m, m) for m in first["missing"]]
    if missing:
        notes.append(f"Not yet included, with no local figure: {', '.join(missing)}.")
    if payoff_known and payoff_total:
        notes.append("Payoffs are estimates until the lender's payoff letter, which adds interest through the closing date.")
        if payoff_est:
            assumptions.append("The mortgage payoff is estimated from the statement balance: the lender's payoff letter replaces it.")
    elif not payoff_known:
        notes.append("Not included: the mortgage payoff. Add it to see the cash at closing.")
    notes.append("Not included: liens or judgments, HOA dues owed or prorated, and utility bills.")
    if R.get("foreign_seller"):
        notes.append("The seller is a foreign person: FIRPTA may require the buyer to withhold up to 15% of the price at "
                     "closing. Confirm with the title company or a CPA.")
    shortfalls = []
    for c in columns:  # the costs and payoffs exceed the price: said first, on the page and in the reply
        if c["short"]:
            text = (f"At {c['price_display']} the costs and payoffs exceed the sale price: the seller would bring about "
                    f"{money(-c['net'], 100)} to closing.")
            shortfalls.append(text)
            warnings.append(text + " Say so plainly in the reply.")
    notes[:0] = shortfalls  # iteration 9 eval 4: in column order
    if not st:
        assumptions.append("The property's state wasn't given, so every cost is a national estimate: ask for the city and county.")

    reasons = []
    if not st:
        reasons.append("the property's state isn't known, so every cost is a national estimate")
    if not payoff_known:
        reasons.append("the mortgage payoff isn't included")
    if missing:
        reasons.append(f"there's no local figure for {', '.join(missing)}")
    if tax_missing:  # iteration 9 eval 2: in Texas the proration can run to thousands
        reasons.append("this year's property tax proration isn't included")
    street = p["address"].split(",")[0].strip()
    place = ", ".join(x for x in (p.get("city"), st) if x)
    prepared = _date(R.get("prepared_date"), "prepared_date") if re.match(r"^\d{4}-\d{2}-\d{2}", str(R.get("prepared_date") or "")) else None
    return {
        "ok": True,
        "address": street,
        "address_line": f"{street}, {place}" if place else street,
        "prepared_date": long_date(prepared or date.today()) if not R.get("prepared_date") or prepared else str(R["prepared_date"]),
        "prepared_for": R.get("prepared_for"),
        "state": st,
        "facts": facts,
        "columns": columns,
        "rows": rows,
        "final_label": final_label,
        "cash_at_closing": cash,
        "commission_assumed": commission_assumed,
        "has_tax_proration": has_tax,
        "tax_assumed_unpaid": tax_assumed,
        "tax_assumed_paid": tax_paid_assumed,
        "closing_date_assumed": bool(dated),
        "notes": notes,
        "assumptions": assumptions,
        "warnings": warnings,
        # iteration 9 evals 2, 5: a net sheet reads no MLS export, so the MLS / --columns notes don't apply
        "market_notes": [n for n in market.notes if "MLS" not in n],
        "preliminary": bool(reasons),
        "preliminary_reason": "; ".join(reasons),
    }


def run(R, cma_path=None, mls_name=None):
    """compute() from a data dict and an optional seller CMA handoff file (the same steps render.py takes)."""
    if cma_path:
        R = apply_cma(R, handoff.load(cma_path))
    return compute(R, load_market(R, mls_name))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("data", help="net-sheet.json")
    ap.add_argument("--cma", help="a seller CMA handoff (.seller.cma.json) for the same home")
    ap.add_argument("--mls", help="MLS name (Stellar is built in)")
    a = ap.parse_args(argv)
    try:
        with open(a.data, encoding="utf-8") as f:
            R = json.load(f)
        result = run(R, a.cma, a.mls)
    except (NetSheetError, profiles.ProfileError, handoff.HandoffError, ValueError, OSError) as e:
        result = {"ok": False, "problems": [str(e)]}
    print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
