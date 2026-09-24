"""Analyze the offers on a listing: net sheets, downside, certainty, counter, ranking.

    python3 scripts/review.py listing.json [--cma file.cma.json] [--market market-profile.md] [--mode single|multi] [--offer ID]

Prints JSON with every value already formatted: the page-1 summary (the same one the PDF shows), the
net sheet for each offer, and the assumptions ranked by impact. Or {"ok": false, "problems": [...]}.
See references/listing-file.md for the input.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import handoff, offer_engine as oe, profiles  # noqa: E402

money = oe.money
STATUS = {"g": "good", "a": "caution", "r": "risk"}


def signed(v):
    return ("+" if v >= 0 else "−") + money(abs(v))


def cap(text):
    return text[:1].upper() + text[1:]


# --- inputs ------------------------------------------------------------------

def load_cma(data, cma_path=None):
    """The CMA handoff: --cma file first, else a handoff stored in the listing file under 'cma'."""
    if cma_path:
        return handoff.load(cma_path)
    if isinstance(data.get("cma"), dict):
        return handoff.validate(data["cma"])
    return None


def analyze(data, market=None, cma=None):
    return oe.analyze(data, market=market, cma=cma)


def pick(R, mode="auto", offer_id=None):
    """(mode, offer) for the report. Single mode on one offer keeps the multi-offer context."""
    mode = R["mode"] if mode in (None, "auto") else mode
    if mode == "multi" and len(R["active"]) < 2:
        raise oe.OfferError("A comparison needs at least 2 active offers whose contracts can be reviewed; use single mode.")
    if mode == "multi":
        return "multi", None
    if offer_id:
        o = next((x for x in R["offers"] if x["id"] == offer_id), None)
        if o is None:
            raise oe.OfferError(f"There's no offer with id {offer_id!r} in the listing file.")
    elif R["ranked"] or R["incomplete"]:
        o = (R["ranked"] or R["incomplete"])[0]
    else:
        raise oe.OfferError("No active offers to review: every offer in the file is declined, expired or withdrawn. "
                            "To show one anyway, name it with --offer.")
    if "action" not in o:  # declined / expired offer shown on request
        o["action"], o["action_reason"] = "DECLINE", f"Offer status: {o['status']}"
    return "single", o


# --- shared pieces -----------------------------------------------------------

def price_note(o):
    """Financing, plus how an escalating offer reached its price."""
    return fin_str(o) + (f" · {o['escalation_note']}" if o.get("escalation") else "")


def fin_str(o):
    return oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.1f}% down")


def preliminary(R, offer_id=None):
    need = oe.preliminary_inputs(R, offer_id)
    if not need:
        return None
    n = len(R["missing"])
    return (f"**Preliminary: based on limited data.** Add {', '.join(need)} to sharpen the numbers; "
            f"{n} input{'s are' if n != 1 else ' is'} assumed in total (listed at the end).")


def data_note(R):
    bits = []
    if not R["seller"]["payoff_known"]:
        bits.append("Nets are **before mortgage payoff**.")
    if not R["listing"]["cma_provided"]:
        bits.append("No CMA yet: appraisal risk is measured against list price.")
    n, hi = len(R["assumptions"]), sum(a["impact"] == "high" for a in R["assumptions"])
    bits.append(f"{n} input{'s' if n != 1 else ''} assumed ({hi} high-impact); see Assumptions & Data to Confirm."
                if n else "All key inputs provided.")
    return " ".join(bits)


def where(R, scope):
    """An assumption's scope for display: 'offer A' becomes the offer's label."""
    if scope.startswith("offer "):
        o = next((x for x in R["offers"] if x["id"] == scope[6:]), None)
        return o["label"] if o else scope.title()
    return scope.title()


def to_confirm(R, limit=4):
    """The inputs that would change the answer most (high and medium impact), for the chat reply."""
    return [a["why"] for a in R["missing"] if a["impact"] in ("high", "med")][:limit]


def threat(o):
    weights = {k: w for k, _, w in oe.CRITERIA}
    prio = ["appraisal", "contingency", "timeline", "approval", "financing", "deposit", "property", "agent"]
    s = o["score"]["scores"]
    worst = min(prio, key=lambda k: (-weights[k] * (5 - s[k]), prio.index(k)))
    if s[worst] >= 4:
        return "None major"
    return {"appraisal": "Appraisal", "contingency": "Contingencies", "timeline": "Closing date", "approval": "Loan approval",
            "financing": "Financing", "deposit": "Low deposit", "property": "Insurance / condition", "agent": "Buyer's agent"}[worst]


def certainty(o, S):
    dl = S["deadline"]
    return {
        "score": o["score"]["total"], "band": o["score"]["band"][1], "band_class": o["score"]["band"][0],
        "walk_away_until": f"{o['firm_date']:%a %b %-d} ({o['risk_days']} days)",
        "deposit": f"{money(o['deposit'])} ({o['deposit'] / o['price']:.1%})" if o["deposit"] is not None else "not provided",
        "closing": (f"{o['close']:%b %-d} vs. {dl:%b %-d} deadline" if dl else f"{o['close']:%b %-d} ({o['close_days']} days)"),
        "closing_ok": (o["close"] <= dl) if dl else True,
        "threat": threat(o),
    }


def row(term, offered, counter, why):
    return {"term": term, "offered": offered, "counter": counter, "why": why}


# --- single offer ------------------------------------------------------------

def incomplete_view(R, o):
    """A contract that can't be reviewed as written: what to fix, the numbers as written, and no recommendation."""
    S = R["seller"]
    issues = "; ".join(f["issue"].rstrip(".") for f in o["blocking"])
    fixes = [f for f in o["flags"] if f.get("contract") and f["sev"] in ("Blocking", "High")]
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": "INCOMPLETE", "headline": "CONTRACT INCOMPLETE",
        "why": (f"This contract can't be reviewed as written: {issues[:1].lower() + issues[1:]}. There is no recommendation, "
                "counter or ranking until the buyer's agent sends a corrected, fully signed contract. The numbers below are "
                "for reference only. For questions about whether the contract is binding, see a real estate attorney."),
        "offers_active": len(R["active"]) + len(R["incomplete"]),
        "respond_by": o.get("expires") or "See contract", "respond_by_offer": o["label"] if o.get("expires") else None,
        "priority": S.get("priority_note") or S["priority"].title(),
        "fixes": [{"sev": f["sev"], "issue": f["issue"], "fix": f["fix"]} for f in fixes],
        "counter": None, "compare": None,
        "kpis": [{"label": "Offer Price", "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
                 {"label": "Net as Written", "value": money(o["ns"]["net_adj"]), "note": "for reference only", "tone": ""},
                 {"label": "Downside Net", "value": money(o["ns_down"]["net_adj"]), "note": "if appraisal & inspection go badly", "tone": "risk"},
                 {"label": "Seller's Target Net", "value": money(o["target"]["net_adj"]), "note": "list price, clean terms", "tone": ""}],
        "certainty": certainty(o, S),
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in o["flags"] if not f.get("contract")][:3],  # contract issues are in fixes
        "options": [],
        "preliminary": None,
        "next_step": "ask the buyer's agent for a corrected, fully signed contract with every page and rider, then run the review again.",
        "data_note": data_note(R),
    }


def single_view(R, o):
    if o["action"] == "INCOMPLETE":
        return incomplete_view(R, o)
    L, S = R["listing"], R["seller"]
    tgt = o["target"]["net_adj"]
    ao, dn, cn = o["ns"]["net_adj"], o["ns_down"]["net_adj"], o["ns_counter"]["net_adj"]
    act = o["action"]
    top = R["ranked"][0] if R["ranked"] else o
    multi_ctx = R["mode"] == "multi"

    if act == "COUNTER":
        s = []
        if o["price"] > L["list_price"] and ao < tgt:
            s.append(f"The {money(o['price'])} offer is {money(o['price'] - L['list_price'])} over list, but after costs it nets "
                     f"**{money(tgt - ao)} less** than a clean full-price offer.")
        elif ao < tgt:
            s.append(f"This offer nets **{money(tgt - ao)} less** than a clean full-price offer.")
        if any("appraisal gap" in f["issue"] for f in o["flags"]):
            s.append("It's priced above the value range without enough appraisal gap coverage.")
        if o["sale_contingency_days"]:
            s.append("It depends on the sale of the buyer's home.")
        risk = "and cuts the risk" if o["counter_score"] > o["score"]["total"] else "at about the same certainty"
        s.append(f"The counter below lifts the net by {money(cn - ao)} {risk}." if cn >= ao
                 else f"The counter below protects the price: it nets {signed(cn - dn)} vs. the downside case.")
        why = " ".join(s)
    elif act == "ACCEPT":
        why = f"Strong offer: nets {money(ao)} with {o['score']['total']}/100 certainty. Nothing in the terms is worth risking the deal over."
    else:
        why = f"{o.get('action_reason', '')}. {cap(top['ref'])} is the recommended offer; see the comparison below."

    counter = None
    if act == "COUNTER" and o["counter_rows"]:
        tail = f", {signed(cn - dn)} vs. downside" if cn < ao else ""
        counter = {"rows": [row(*r) for r in o["counter_rows"]],
                   "summary": f"{len(o['counter_rows'])} change{'s' if len(o['counter_rows']) != 1 else ''} · net after holding "
                              f"{money(ao)} → **{money(cn)}** ({signed(cn - ao)} vs. as offered{tail})"}
    compare = None
    if act in ("BACKUP", "DECLINE") and top is not o:
        compare = {"this": o["label"], "vs": top["label"], "rows": [
            ["Price", money(o["price"]), money(top["price"])],
            ["Net After Holding", money(ao), money(top["ns"]["net_adj"])],
            ["Downside Net", money(dn), money(top["ns_down"]["net_adj"])],
            ["Certainty", f"{o['score']['total']}/100", f"{top['score']['total']}/100"],
            ["Closing", f"{o['close']:%b %-d}", f"{top['close']:%b %-d}"]]}

    pre = "" if S["payoff_known"] else " (Pre-Payoff)"
    kpis = [{"label": "Offer Price", "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
            {"label": f"Net as Offered{pre}", "value": money(ao), "note": f"{signed(ao - tgt)} vs. target",
             "tone": "risk" if ao < tgt else "good"},
            {"label": "Downside Net", "value": money(dn), "note": "if appraisal & inspection go badly", "tone": "risk"}]
    if act == "COUNTER":
        kpis.append({"label": "Net with Our Counter", "value": money(cn), "tone": "good",
                     "note": f"{signed(cn - ao)} vs. as offered" if cn >= ao else f"{signed(cn - dn)} vs. downside; protects the price"})
    else:
        kpis.append({"label": "Seller's Target Net", "value": money(tgt), "note": "list price, clean terms", "tone": ""})

    score = o["score"]["total"]
    opts = [{"option": "Accept as Written", "net": money(ao), "certainty": f"{score}/100", "status": "good" if score >= 80 else "risk",
             "what": "Deal as signed" if score >= 80 else f"Realistic net closer to {money(dn)} if the appraisal or inspection goes badly",
             "recommended": act == "ACCEPT"}]
    if o["counter_rows"]:
        opts.append({"option": "Counter", "net": money(cn), "certainty": f"≈{o['counter_score']}/100 if accepted",
                     "status": "good" if act == "COUNTER" else "caution", "recommended": act == "COUNTER",
                     "what": "Better net and lower walk-away risk" if act == "COUNTER"
                     else f"Only {signed(cn - ao)}, and it risks losing a strong offer"})
    opts.append({"option": "Decline", "net": "—", "certainty": "—", "status": "caution", "recommended": act == "DECLINE",
                 "what": f"Stay on market; each extra month costs about {money(S['holding_monthly'])} in holding costs"})
    if act == "BACKUP":
        opts.insert(0, {"option": "Hold as Backup", "net": money(ao), "certainty": f"{score}/100", "status": "caution",
                        "what": f"Steps in if {top['ref']} falls through", "recommended": True})

    expires = f" before {o['expires']}" if o.get("expires") else ""
    nxt = {"COUNTER": f"approve the counter terms and I'll send the counter to the buyer's agent{expires}.",
           "ACCEPT": "sign the contract and I'll open escrow and calendar every deadline.",
           "BACKUP": "once the primary contract is fully signed, approve offering this buyer a backup position on the "
                     "Back-Up Contract rider.",
           "DECLINE": "approve, and with your written OK I'll tell the buyer's agent the seller is moving forward with another offer."}[act]
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": act, "headline": "HOLD AS BACKUP" if act == "BACKUP" else act, "why": why,
        "offers_active": len(R["active"]) if multi_ctx else 1,
        "respond_by": o.get("expires") or "See contract", "respond_by_offer": o["label"] if o.get("expires") else None,
        "priority": S.get("priority_note") or S["priority"].title(),
        "counter": counter, "compare": compare, "kpis": kpis,
        "certainty": certainty(o, S),
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in o["flags"][:3]],
        "options": opts,
        "preliminary": preliminary(R, o["id"] if multi_ctx else None),
        "next_step": nxt,
        "data_note": data_note(R),
    }


# --- multiple offers ---------------------------------------------------------

def first_expiry(R):
    """(when, offer label) of the first offer to expire."""
    ex = [o for o in R["active"] + R["incomplete"] if o.get("expires_raw")]
    if not ex:
        return "See contracts", None
    o = min(ex, key=lambda o: str(o["expires_raw"]))
    return o["expires"], o["label"]


def multi_view(R):
    S = R["seller"]
    rk = R["ranked"]
    top = rk[0]
    act = top["action"]
    backup = next((o for o in rk if o["action"] == "BACKUP"), None)
    hi_price = max(R["active"], key=lambda o: o["price"])
    lead = f"{cap(top['ref'])} has the best net once risk is counted and closes {top['close']:%b %-d}"
    lead += ", before the seller's deadline." if S["deadline"] and top["close"] <= S["deadline"] else "."
    if hi_price is not top:
        reason = hi_price["action_reason"]
        reason = (reason[:1].lower() + reason[1:]) if reason else "more risk"
        lead += f" The highest price ({hi_price['label']}, {money(hi_price['price'])}) ranks #{rk.index(hi_price) + 1}: {reason}."
    if backup:
        lead += f" Keep {backup['ref']} as backup."
    if R["incomplete"]:
        n = len(R["incomplete"])
        names = ", ".join(x["label"] for x in R["incomplete"])
        lead += (f" {n} more offer{'s' if n != 1 else ''} ({names}) can't be reviewed until the contract is corrected, "
                 + ("so it isn't ranked." if n == 1 else "so they aren't ranked."))
    top_net = top["ns_counter"]["net_adj"] if act == "COUNTER" else top["ns"]["net_adj"]

    terms = {}
    for o in rk:
        a = o["action"]
        if o is top and a == "COUNTER":
            t = "Counter: " + " · ".join(f"{r[0].lower()} {r[2]}" for r in o["counter_rows"][:5])
        elif o is top:
            t = "Accept as written"
        elif a == "BACKUP":
            t = (f"After {top['label']}'s contract is fully signed, offer a backup position on the Back-Up Contract rider"
                 f" (at {money(o['counter_terms']['price'])} if needed)")
        else:
            t = o["action_reason"]
        terms[o["id"]] = t
    summary = f"Net after holding with {top['ref']} {'counter' if act == 'COUNTER' else 'as written'}: **{money(top_net)}**"
    if act == "COUNTER":
        summary += f" ({signed(top_net - top['ns']['net_adj'])} vs. as offered"
        summary += f", {signed(top_net - top['ns_down']['net_adj'])} vs. downside)" if top_net < top["ns"]["net_adj"] else ")"
    note = ("Only one counter goes out at a time, so the seller can't end up with two accepted contracts. " if act == "COUNTER" else "")
    note += ("With the seller's written authorization, other buyers' agents are told the seller is "
             f"{'responding to' if act == 'COUNTER' else 'moving forward with'} another offer (NAR Standard of Practice 1-15); "
             "nothing is declined until the seller approves.")

    ranked = [{"rank": i + 1, "offer": o["label"],
               "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
               "price": money(o["price"]) + (" (escalated)" if o.get("escalated") else ""), "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]),
               "score": o["score"]["total"], "band_class": o["score"]["band"][0], "risk_days": o["risk_days"],
               "close": f"{o['close']:%b %-d}", "action": "Hold as Backup" if o["action"] == "BACKUP" else o["action"].title(),
               "status": {"ACCEPT": "good", "COUNTER": "good", "BACKUP": "caution", "DECLINE": "risk"}[o["action"]],
               "terms": terms[o["id"]]} for i, o in enumerate(rk)]
    ranked += [{"rank": "—", "offer": o["label"],
                "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
                "price": money(o["price"]), "net": "—", "downside": "—", "score": "—", "band_class": "na", "risk_days": "—",
                "close": f"{o['close']:%b %-d}", "action": "Incomplete", "status": "risk",
                "terms": "Contract can't be reviewed as written: " + o["blocking"][0]["issue"].rstrip(".").lower()}
               for o in R["incomplete"]]

    most_certain = max(R["active"], key=lambda o: (o["score"]["total"], o["ns_down"]["net_adj"]))
    first = f"{'Counter' if act == 'COUNTER' else 'Accept'} {top['label']}" + (f", Hold {backup['label']} as Backup" if backup else "")
    opts = [{"option": first, "net": money(top_net), "recommended": True, "status": "good",
             "certainty": f"≈{top['counter_score']}/100" if act == "COUNTER" else f"{top['score']['total']}/100",
             "what": "Best net with manageable risk" + (f"; {backup['ref']} is a safety net" if backup else "")}]
    if act == "ACCEPT" and top["counter_rows"]:
        g = top["ns_counter"]["net_adj"] - top["ns"]["net_adj"]
        opts.append({"option": f"Counter {top['label']} Anyway", "net": money(top["ns_counter"]["net_adj"]), "recommended": False,
                     "certainty": f"≈{top['counter_score']}/100", "status": "caution",
                     "what": f"Only {signed(g)}, and it risks losing the strongest offer"})
    if most_certain is not top:
        opts.append({"option": f"Accept {most_certain['label']} Now", "net": money(most_certain["ns"]["net_adj"]), "recommended": False,
                     "certainty": f"{most_certain['score']['total']}/100", "status": "caution",
                     "what": f"Closes {most_certain['close']:%b %-d}, most certain, but {money(top_net - most_certain['ns']['net_adj'])} less than the plan"})
    opts.append({"option": "Call for Highest & Best", "net": "Unknown", "certainty": "Varies", "status": "caution", "recommended": False,
                 "what": "May lift prices, but adds ~2 days and weak terms usually stay weak"})
    verb = "send the counter to" if act == "COUNTER" else "accept"
    nxt = f"approve the plan and I'll {verb} {top['ref']}" + (
        f"; once that contract is fully signed, I'll offer {backup['ref']} a backup position" if backup else "") + "."
    return {
        "mode": "multi", "offer": top["id"], "offer_label": top["label"], "action": act, "headline": act, "why": lead,
        "offers_active": len(R["active"]) + len(R["incomplete"]), "respond_by": first_expiry(R)[0], "respond_by_offer": first_expiry(R)[1],
        "priority": S.get("priority_note") or S["priority"].title(),
        "plan_summary": summary, "plan_note": note, "ranked": ranked, "options": opts,
        "preliminary": preliminary(R, top["id"]), "next_step": nxt, "data_note": data_note(R),
        "target_net": money(R["target"]["net_adj"]),
    }


# --- detail for the markdown template ------------------------------------------

def net_sheet_rows(cols):
    """[{label, values[]}] for columns of net sheets; rows that are zero everywhere are skipped (except price and concessions)."""
    rows = []
    for i, (key, label, _) in enumerate(cols[0][1]["lines"]):
        vals = [c["lines"][i][2] for _, c in cols]
        if key not in ("price", "conc") and all(v == 0 for v in vals):
            continue
        rows.append({"key": key, "label": label, "values": vals})
    return rows


def offer_detail(o):
    cols = [("As Offered", o["ns"]), ("Downside", o["ns_down"])]
    if o["counter_rows"]:
        cols.append(("Counter", o["ns_counter"]))
    return {
        "id": o["id"], "label": o["label"], "buyer": o["buyer"], "buyer_agent": o.get("buyer_agent") or "", "price": money(o["price"]), "financing": fin_str(o),
        "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]), "counter_net": money(o["ns_counter"]["net_adj"]),
        "score": o["score"]["total"], "band": o["score"]["band"][1], "action": o.get("action"),
        "close": f"{o['close']:%a %b %-d}", "firm_date": f"{o['firm_date']:%a %b %-d}",
        "flags": [f"{f['sev']}: {f['issue']} {f['fix']}" for f in o["flags"]],
        "net_sheet": {"columns": [c for c, _ in cols],
                      "rows": [{"label": r["label"], "values": [money(v) for v in r["values"]]} for r in net_sheet_rows(cols)]
                      + [{"label": "Holding Costs Until Closing", "values": [money(c["holding"]) for _, c in cols]},
                         {"label": "Net After Holding Costs", "values": [money(c["net_adj"]) for _, c in cols]}]},
    }


def result(R, mode="auto", offer_id=None):
    mode, o = pick(R, mode, offer_id)
    view = single_view(R, o) if mode == "single" else multi_view(R)
    L = R["listing"]
    offers = [o] if mode == "single" else R["ranked"]
    return {
        "ok": True, "mode": mode, "property": L.get("address") or "", "list_price": money(L["list_price"]),
        "value_range": f"{money(L['cma_low'])}–{money(L['cma_high'])}" if L["cma_provided"] else "not provided",
        "summary": view,
        "offers": [offer_detail(x) for x in offers],
        "to_confirm": to_confirm(R),
        "assumptions": [{"impact": a["impact"], "where": where(R, a["scope"]), "what": a["why"]} for a in R["missing"]],
        "cost_notes": L["cost_notes"],
        "market_notes": R["market_notes"],
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("listing")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--market", help="market profile (built in for Florida)")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single-offer report")
    a = ap.parse_args(argv)
    try:
        with open(a.listing, encoding="utf-8") as f:
            data = json.load(f)
        R = analyze(data, a.market, load_cma(data, a.cma))
        out = result(R, a.mode, a.offer)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
