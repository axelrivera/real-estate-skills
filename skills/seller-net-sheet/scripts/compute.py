"""Compute a seller net sheet (one to three prices) from net-sheet.json: the one document model the PDF and the
markdown sheet are both filled from.

    python3 scripts/compute.py net-sheet.json [--cma FILE.seller.cma.json] [--mls NAME]

Prints JSON: one column per price, the itemized rows in the page's order (brokerage, transfer taxes, title and
closing, prorations, concessions, payoffs), every amount already formatted, `notes` (the PDF's notes block),
`chat_notes` (the markdown sheet's: the notes the reply's assumption lines don't already say), `assumptions` (one
line each in the reply), `warnings` and `preliminary`. render.py places this same result, so chat and file agree.

Every cost comes from finance.seller_net (this sale's own numbers in `costs`, then the built-in local values, then
national estimates). Each column is a finance.Ledger: every line is rounded once, and every subtotal is the sum of
the printed lines. Every sentence and label is a template in assets/labels.json; notes go through one notes.Notes
registry, so each is said once, and no label carries one. The input is never changed.
"""
import argparse
import copy
import json
import os
import re
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import finance, fmt, handoff, notes, profiles, prose  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "labels.json")
with open(LABELS_PATH, encoding="utf-8") as _f:
    L = json.load(_f)

MAX_SCENARIOS = 3  # three columns still fit on one page
TAX_BILL_MONTH = 10  # when a market doesn't say (`property_tax.bill_month`): from October a year's bill may be out

# Row groups in page order: (group key, line keys from finance.seller_net)
GROUPS = (("brokerage", ("listing_fee", "buyer_broker_fee")),
          ("taxes", ("transfer_tax", "transfer_surtax")),
          ("title", ("owner_title", "title_fees", "estoppel")),
          ("prorations", ("tax_proration",)),
          ("concessions", ("credit", "other")))
COST_KEYS = {k for _, keys in GROUPS for k in keys}
SMALL_WORDS = {"a", "an", "and", "of", "on", "or", "the", "to", "for", "in"}
# The reply says these notes as its assumption lines; the markdown sheet's notes are the rest (said once)
REPLY_KINDS = ("assumption", "estimate", "chat_only")


class NetSheetError(ValueError):
    """Something net-sheet.json needs; the message is written for the agent."""


def t(key, **kw):
    """A labels.json template, filled."""
    return fmt.fill(L[key], **kw)


def title_case(text):
    """'municipal_lien_search' -> 'Municipal Lien Search', 'title company quote' -> 'Title Company Quote'."""
    words = str(text).replace("_", " ").split()
    return " ".join(w if i and w.lower() in SMALL_WORDS else w[:1].upper() + w[1:] for i, w in enumerate(words))


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


def _label(text, name):
    """A label the model typed: a name only. The sheet prints every price, amount and date itself, so a figure in a
    label could disagree with the column it names."""
    found = prose.figures(text)
    if found:
        raise NetSheetError(f"{name} ({text!r}) has a figure in it ({', '.join(found)}): the sheet prints the price, "
                            "amounts and dates itself. Name it in words (\"After a Price Cut\"), or leave a price's "
                            "label out to show the price.")
    return text


def _items(v, name):
    """A list of {label, amount} (other costs, other payoffs), checked."""
    if v in (None, []):
        return []
    if not isinstance(v, list) or not all(isinstance(o, dict) and o.get("label") for o in v):
        raise NetSheetError(f"{name} should be a list of {{label, amount}} items, like "
                            '[{"label": "Survey", "amount": 450}].')
    return [{"label": _label(title_case(o["label"]) if str(o["label"]).islower() else o["label"], f"{name} label"),
             "amount": _amount(o.get("amount") or 0, f"{name} ({o['label']})")} for o in v]


def apply_cma(R, h):
    """A copy of the data with what it doesn't say filled from a seller-cma handoff for the same home: the location,
    the tax bill, HOA dues, and the recommended list price when no price was given."""
    if h.get("side") != "seller":
        raise NetSheetError("That CMA was made for a buyer. Use the seller CMA for this home, or leave it out.")
    R = copy.deepcopy(R)
    s, p = h["subject"], R.setdefault("property", {})
    slug = lambda a: re.sub(r"[^a-z0-9]", "", str(a or "").split(",")[0].lower())  # noqa: E731
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
        R["scenarios"] = [{"price": h["recommended_list_price"], "label": L["col_recommended"]}]
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
    for i, x in enumerate(xs):
        price = x.get("price")
        if isinstance(price, bool) or not isinstance(price, (int, float)) or price <= 0:
            raise NetSheetError(f"scenarios[{i}].price should be the sale price as a number, not {price!r}.")
        own = x.get("closing_date")  # a vague date ("mid-December") is marked assumed
        out.append({"price": price, "label": _label(x["label"], f"scenarios[{i}].label") if x.get("label") else None,
                    "credit": _amount(x.get("seller_credit"), f"scenarios[{i}].seller_credit") or 0,
                    "warranty": _amount(x.get("home_warranty"), f"scenarios[{i}].home_warranty") or 0,
                    "repairs": _amount(x.get("repairs"), f"scenarios[{i}].repairs") or 0,
                    "closing": _date(own or R.get("closing_date"), "closing_date"),
                    "closing_assumed": bool(x.get("closing_date_assumed") if own else R.get("closing_date_assumed"))})
    # a label in pieces that each stay on one line: the price, then "with $6,000 Credit", so a header that wraps breaks
    # between them, never inside one. The default label names the price, so the tile under it doesn't repeat it.
    parts = [[x["label"]] if x["label"] else [fmt.money(x["price"])]
             + ([t("col_credit_tail", credit=fmt.money(x["credit"]))] if x["credit"] else []) for x in out]
    labels = [" ".join(p) for p in parts]
    for i, x in enumerate(out):  # two columns may not share a name
        x["names_price"] = not x["label"]
        x["label_parts"] = parts[i] + ([] if labels.count(labels[i]) == 1 else [t("col_option_tail", n=i + 1)])
        x["label"] = " ".join(x["label_parts"])
    return out


def payoffs(costs):
    """([{label, amount}], first mortgage known?, estimated from a balance?). A stated payoff is used as given; a
    statement balance gets a month's interest (finance.payoff_from_balance)."""
    rows, known, est = [], False, False
    first, balance = _amount(costs.get("mortgage_payoff"), "costs.mortgage_payoff"), costs.get("mortgage_balance")
    if first is None and balance is not None:
        _amount(balance, "costs.mortgage_balance")
        first = finance.payoff_from_balance(balance, costs.get("mortgage_rate")) if balance else 0
        est = bool(balance)
    if first is not None:
        known = True
        if first:
            rows.append({"label": L["row_mortgage_payoff"], "amount": first})
    for o in _items(costs.get("other_payoffs"), "costs.other_payoffs"):
        if o["amount"]:
            rows.append({"label": o["label"], "amount": o["amount"]})
    return rows, known, est


def title_fee_items(market, line):
    """The title company fees line, itemized by the fees it adds up (Florida: settlement, title search, municipal lien
    search, recording). A single quote stays one line."""
    fees = market.get("closing_costs.seller_title_fees") or {}
    items = [(k, v) for k, v in fees.items() if v]
    if len(items) < 2 or abs(sum(v for _, v in items) - line["amount"]) > 0.5:
        return [(line["label"], line["amount"])]
    return [(title_case(k), v) for k, v in items]


def column_ledger(x, net, market, pay_rows, label):
    """One price's money as a finance.Ledger: the price, each cost (title fees itemized), then the payoffs. Every
    line is rounded once; every total the page prints is a sum of these lines."""
    led = finance.Ledger()
    led.add("price", L["row_price"], x["price"])
    for ln in net["lines"]:
        if ln["key"] == "title_fees":
            for name, amount in title_fee_items(market, ln):
                led.cost("title_fees", name, amount)
        else:
            led.cost(ln["key"], label(ln), ln["amount"], rate=ln.get("rate"))
    for r in pay_rows:
        led.cost("payoff", r["label"], r["amount"])
    return led


def line_amount(led, key, label):
    return sum(ln["amount"] for ln in led if ln["key"] == key and ln["label"] == label)


def summary_tiles(columns, payoff_known):
    """The boxes next to one or two price tiles (the tile row keeps three slots; a spare one stays empty): one price
    adds its payoffs when they're known (its costs are on its own tile), two prices the difference between their nets."""
    if len(columns) == 1:
        a = columns[0]
        return [{"label": L["tile_payoffs"], "display": fmt.money(a["payoff_total"]),
                 "note": L["tile_payoffs_sub"] if a["payoff_total"] else L["tile_no_payoffs_sub"]}] if payoff_known else []
    if len(columns) == 2:
        a, b = columns
        diff = abs(a["net"] - b["net"])
        if diff == 0:
            return [{"label": L["tile_difference"], "display": fmt.money(0), "note": L["tile_same_sub"]}]
        hi = a if a["net"] > b["net"] else b
        return [{"label": L["tile_difference"], "display": fmt.money(diff),
                 "note": t("tile_less_sub" if a["short"] and b["short"] else "tile_more_sub", label=hi["label"])}]
    return []


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
    payoff_total = sum(fmt.half_up(r["amount"]) for r in pay_rows)
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
    types = L["property_types"]

    nets = []
    for x in xs:
        extra = list(others)
        if x["warranty"]:
            extra.append({"label": L["row_home_warranty"], "amount": x["warranty"]})
        if x["repairs"]:
            extra.append({"label": L["row_repairs"], "amount": x["repairs"]})
        nets.append(finance.seller_net(x["price"], market, credit=x["credit"], payoff=None,
                                       listing_fee_pct=lf, buyer_broker_fee_pct=bf, has_hoa=has_hoa, other_costs=extra,
                                       annual_tax=annual_tax, closing=x["closing"], bill_paid=bill_paid,
                                       prop_type=p.get("property_type"), tax_due_date=due_date))
    first = nets[0]
    assumed = {a["key"] for a in first["assumed"]}
    bill_month = market.get("property_tax.bill_month") or TAX_BILL_MONTH
    has_tax = any(ln["key"] == "tax_proration" for n in nets for ln in n["lines"])
    # a closing after this year's bill is due assumes it paid (finance.tax_proration)
    paid_assumed = [bool(x["closing"]) and finance.tax_bill_assumed_paid(x["closing"], market, bill_paid, due_date) for x in xs]
    tax_assumed = has_tax and bill_paid is None and any(x["closing"] and x["closing"].month >= bill_month and not pa
                                                        for x, pa in zip(xs, paid_assumed))
    tax_mixed = has_tax and any(paid_assumed) and not all(paid_assumed)  # one closing before the due date, one after

    def label(line):
        key, rate = line["key"], line.get("rate")
        if key in ("listing_fee", "buyer_broker_fee"):  # a default commission is a default: no label, no note
            return t("row_" + key, pct=fmt.pct(rate, 2))
        if key == "tax_proration" and tax_mixed:  # one row, though one closing is charged and another credited
            return L["row_tax_mixed"]
        return line["label"]

    ledgers = [column_ledger(x, n, market, pay_rows, label) for x, n in zip(xs, nets)]

    # Rows: one per line (key and label) across every column (a seller credit may exist in only one), as on the page
    rows = [{"kind": "price", "key": "price", "label": L["row_price"], "amounts": [led.amount("price") for led in ledgers]}]
    if len({x["closing"] for x in xs}) > 1:  # different closing dates move the proration: show them
        rows.append({"kind": "info", "key": "closing", "label": L["row_closing"],
                     "display": [fmt.date_short(x["closing"]) if x["closing"] else L["row_not_set"] for x in xs]})
    for gkey, keys in GROUPS:
        group = []
        for key in keys:
            names = list(dict.fromkeys(ln["label"] for led in ledgers for ln in led if ln["key"] == key))
            group += [{"kind": "line", "key": key, "label": name, "amounts": [line_amount(led, key, name) for led in ledgers]}
                      for name in names]
        if group:
            rows.append({"kind": "group", "key": gkey, "label": L["grp_" + gkey]})
            rows += group
    cost_lines = lambda ln: ln["key"] in COST_KEYS  # noqa: E731
    rows.append({"kind": "subtotal", "key": "total_costs", "label": L["row_total_costs"],
                 "amounts": [led.total(where=cost_lines) for led in ledgers]})
    if pay_rows:
        rows.append({"kind": "subtotal", "key": "net_before_payoff", "label": L["row_net_before_payoff"],
                     "amounts": [led.total(where=lambda ln: ln["key"] != "payoff") for led in ledgers]})
        rows.append({"kind": "group", "key": "payoffs", "label": L["grp_payoffs"]})
        rows += [{"kind": "line", "key": "payoff", "label": r["label"],
                  "amounts": [line_amount(led, "payoff", r["label"]) for led in ledgers]}
                 for r in {r["label"]: r for r in pay_rows}.values()]
    final_label = L["row_net"] if payoff_known else L["row_net_no_payoff"]
    rows.append({"kind": "final", "key": "net", "label": final_label, "amounts": [led.total() for led in ledgers]})
    for r in rows:  # a line one column doesn't have (a seller credit in one option) is an empty cell, not $0
        if "amounts" in r:
            r["display"] = [fmt.EMPTY if r["kind"] == "line" and not a else fmt.money(a) for a in r["amounts"]]

    columns = []
    for x, led in zip(xs, ledgers):
        total_costs = -led.total(where=cost_lines)
        net_before = led.total(where=lambda ln: ln["key"] != "payoff")
        net = led.total()
        span = max(x["price"], total_costs + payoff_total)  # the bar's full width: the price, or more when short
        price = led.amount("price")
        columns.append({"label": x["label"], "label_parts": x["label_parts"], "names_price": x["names_price"],
                        "price": price, "price_display": fmt.money(price),
                        "closing_date": x["closing"].isoformat() if x["closing"] else None,
                        "total_costs": total_costs, "total_costs_display": fmt.money(total_costs),
                        "costs_pct": total_costs / price, "costs_pct_display": fmt.pct(total_costs / price, 1, fixed=True),
                        "net_before_payoff": net_before, "net_before_payoff_display": fmt.money(net_before),
                        "payoff_total": payoff_total, "net": net, "net_display": fmt.money(net), "short": net < 0,
                        # a negative net reads as the cash the seller brings, a positive amount
                        "tile_label": L["tile_cash_to_bring"] if net < 0 else final_label,
                        "tile_display": fmt.money(abs(net)),
                        "bar": {"costs": max(total_costs, 0) / span, "payoffs": payoff_total / span,
                                "net": max(net, 0) / span}})

    # Fact row: the property, then the inputs the numbers rest on. What's missing drops out (the Preliminary line
    # says what the sheet is waiting for).
    facts = []
    st = market.state
    if st:
        place = t("fact_county", county=title_case(str(p["county"]).removesuffix(" County")), state=st) if p.get("county") \
            else profiles.STATES.get(st, st)
        facts.append(place)
    if kind in types:
        facts.append(types[kind])
    if hoa_monthly:
        facts.append(t("fact_hoa", amount=fmt.money(hoa_monthly)))
    elif has_hoa:
        facts.append(L["fact_hoa_unknown"])
    elif p.get("hoa") is False or hoa_monthly == 0:
        facts.append(L["fact_no_hoa"])
    if len({x["closing"] for x in xs}) == 1 and xs[0]["closing"]:
        facts.append(t("fact_closing", date=fmt.date_short(xs[0]["closing"])))
    if payoff_known and payoff_total:
        facts.append(t("fact_payoffs" if len(pay_rows) > 1 else "fact_payoff", amount=fmt.money(payoff_total)))
    elif payoff_known:
        facts.append(L["fact_no_mortgage"])
    if annual_tax:
        facts.append(t("fact_taxes_paid" if bill_paid else "fact_taxes", amount=fmt.money(annual_tax)))
    if lf is not None and bf is not None:
        facts.append(t("fact_commission", pct=fmt.pct(lf + bf, 2)))

    # Notes: one registry, each said once. Labels and facts never say Assumed or Estimate: it's said here.
    N = notes.Notes()
    if kind in types and p.get("property_type_assumed"):  # a condo from a unit number
        N.add("property_type", t("note_property_type_unit" if kind == "condo" else "note_property_type",
                                 type=types[kind].lower()), "assumption")
    dated = [x for x in xs if x["closing"] and x["closing_assumed"]]
    if dated:  # a vague closing date ("mid-December") is an assumption
        N.add("closing_date", t("note_closing_date", dates=" and ".join(dict.fromkeys(fmt.date_short(x["closing"]) for x in dated))),
              "assumption")
    brokerage = any(ln["key"] in ("listing_fee", "buyer_broker_fee") for n in nets for ln in n["lines"])
    commission_assumed = bool(assumed & {"listing_fee", "buyer_broker_fee"})
    if commission_assumed:  # a default, not an assumption on the page: the reply asks for the listing agreement
        rate = sum(ln["rate"] for ln in first["lines"] if ln["key"] in ("listing_fee", "buyer_broker_fee"))
        N.add("commission_default", t("note_commission_default", pct=fmt.pct(rate, 2)), "chat_only")
    if brokerage:
        N.add("commission", finance.COMMISSION_NOTE, "info")
    tax_missing = False
    if has_tax:
        closing = next(x["closing"] for x in xs if x["closing"])
        basis = finance.tax_proration(annual_tax, closing, market, bill_paid)["basis"]
        due = finance.tax_due_date(closing, market, due_date)
        due = fmt.date_short(due, year=False) if due else ""
        # one proration note (key "tax"), whichever way the bill falls; a mixed sheet adds the unpaid assumption once
        if bill_paid:
            N.add("tax", t("note_tax_paid", basis=basis), "info")
        elif all(paid_assumed):
            N.add("tax", t("note_tax_bill_paid", basis=basis, due=due), "assumption")
        elif any(paid_assumed):
            N.add("tax", t("note_tax_mixed", basis=basis, due=due), "assumption")
            if tax_assumed:
                N.add("tax_bill_unpaid", L["note_tax_bill_unpaid"], "assumption")
        elif tax_assumed:
            N.add("tax", t("note_tax_unpaid", basis=basis), "assumption")
        else:
            N.add("tax", t("note_tax", basis=basis), "info")
    elif market.get("property_tax.paid") == "arrears":
        missing_bits = [w for w, gone in (("the tax bill", not annual_tax), ("the closing date", not any(x["closing"] for x in xs)))
                        if gone]
        tax_missing = " and ".join(missing_bits)

    def typical(path):
        """Whose typical charge a built-in value is: a county's own figure is "local"; a statewide one names the
        state, never the county."""
        return "local" if market.source(path) == "county" or not st else profiles.STATES.get(st, "local")
    if "title_fees" in assumed and market.source("closing_costs.seller_title_fees") != "estimate":
        N.add("title_fees", t("note_title_fees", whose=typical("closing_costs.seller_title_fees")), "estimate")
    if any(ln["key"] == "estoppel" for ln in first["lines"]) and \
            market.source("closing_costs.hoa_estoppel_fee") not in ("estimate", "deal"):
        N.add("estoppel", t("note_estoppel", whose=typical("closing_costs.hoa_estoppel_fee")), "estimate")
    estimates = [a["text"] for a in first["assumed"] if a.get("estimate") and a["key"] not in ("listing_fee", "buyer_broker_fee")]
    if estimates:
        N.add("national", t("note_national", items=", ".join(estimates)), "estimate")
    if market.get("closing_costs.owner_title.payer") == "buyer":  # say why there's no owner's title line
        N.add("owner_title", L["note_owner_title"], "info")
    if "no_transfer_tax" in market.note_codes:  # a no-transfer-tax state: say why there's no line
        N.add("transfer_tax", t("note_transfer_tax", state=profiles.STATES.get(st, st)), "info")
    missing = [L["missing_words"].get(m, m) for m in first["missing"]]
    if payoff_known and payoff_total:
        N.add("payoff", L["note_payoff_balance"] if payoff_est else L["note_payoff"], "assumption" if payoff_est else "info")
    N.add("not_included", L["note_not_included"], "info")
    if R.get("foreign_seller"):
        N.add("firpta", L["note_firpta"], "info")
    if not has_hoa and p.get("hoa") is None and hoa_monthly is None and kind != "condo":
        N.add("no_hoa", L["note_no_hoa"], "chat_only")  # its estoppel fee and dues would come off the net

    warnings = list(dict.fromkeys(w for n in nets for w in n["warnings"]))
    for c in columns:  # the costs and payoffs exceed the price: said first in the reply; the tile shows it on the page
        if c["short"]:
            warnings.append(t("warn_short", price=c["price_display"], amount=fmt.money(-c["net"], 100)))

    # Why the sheet is Preliminary: said once, in its own line (never again as a note or a fact)
    reasons = [L["reason_state"]] if not st else []
    if not payoff_known:
        reasons.append(L["reason_payoff"])
    if missing:
        reasons.append(t("reason_missing", items=", ".join(missing)))
    if tax_missing:
        reasons.append(t("reason_tax", items=tax_missing))

    tiles = summary_tiles(columns, payoff_known)
    labels = ([r["label"] for r in rows] + [c["label"] for c in columns] + facts + [c["tile_label"] for c in columns]
              + [s["label"] for s in tiles])
    problems = N.label_problems(labels)
    if problems:
        raise NetSheetError("These labels carry a note (a report says that once, in its notes): "
                            + "; ".join(f"{lbl!r} {why}" for lbl, why in problems) + ". Rename them.")

    street = p["address"].split(",")[0].strip()
    place = ", ".join(x for x in (p.get("city"), st) if x)
    prepared = _date(R.get("prepared_date"), "prepared_date") if re.match(r"^\d{4}-\d{2}-\d{2}", str(R.get("prepared_date") or "")) else None
    reply = [it for it in N.items("chat") if it[2] in REPLY_KINDS]
    return {
        "ok": True,
        "sample": bool(R.get("sample")),
        "address": street,
        "address_line": f"{street}, {place}" if place else street,
        "prepared_date": fmt.date_long(prepared or date.today()) if not R.get("prepared_date") or prepared else str(R["prepared_date"]),
        "prepared_for": R.get("prepared_for"),
        "state": st,
        "facts": facts,
        "columns": columns,
        "summary_tiles": tiles,
        "rows": rows,
        "final_label": final_label,
        "cash_at_closing": payoff_known,
        "commission_assumed": commission_assumed,
        "has_tax_proration": has_tax,
        "tax_assumed_unpaid": tax_assumed,
        "tax_assumed_paid": has_tax and all(paid_assumed),
        "closing_date_assumed": bool(dated),
        # the notes block on the PDF (assumptions, estimates, then the rest), each said once
        "notes": N.pdf(),
        "note_keys": [k for k, _, _ in N.items("chat")],
        # the reply's assumption lines; the markdown sheet's notes are the rest, so nothing is said twice
        "assumptions": [text for _, text, _ in reply],
        "assumption_keys": [k for k, _, _ in reply],
        "chat_notes": [text for _, text, k in N.items("pdf") if k not in REPLY_KINDS],
        "warnings": warnings,
        # a net sheet reads no MLS export, so the MLS / --columns notes don't apply
        "market_notes": [n for n in market.notes if "MLS" not in n],
        "preliminary": bool(reasons),
        "preliminary_reason": "; ".join(reasons),
    }


def run(R, cma_path=None, mls_name=None):
    """The document model from a data dict and an optional seller CMA handoff file (render.py's compute step)."""
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
