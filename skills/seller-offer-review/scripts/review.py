"""Analyze the offers on a listing: net sheets, downside, certainty, counter, ranking.

    python3 scripts/review.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID]

Prints JSON with every value already formatted: the page-1 summary (the same one the PDF shows), the
net sheet for each offer, and the assumptions ranked by impact. Or {"ok": false, "problems": [...]}.
See references/listing-file.md for the input.
"""
import argparse
import json
import os
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import handoff, offer_engine as oe, profiles  # noqa: E402

money = oe.money
STATUS = {"g": "good", "a": "caution", "r": "risk"}


def signed(v):
    return ("+" if v >= 0 else "−") + money(abs(v))


def cap(text):
    return text[:1].upper() + text[1:]


def low_first(text):
    return text[:1].lower() + text[1:]


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


def listed_assumptions(R, multi=False):
    """The assumptions a report lists: all of them in a single review; in the comparison, the listing's and seller's,
    each offer's high-impact ones and any shared by several offers (the rest are in each offer's single review).
    OFR-257: the counts in the Preliminary line and the data note come from this same list, so they match the table."""
    return [a for a in R["missing"] if not multi or not a["scope"].startswith("offer ") or a["impact"] == "high"
            or a.get("also")]


def preliminary(R, offer_id=None, multi=False):
    # OFR-266: an offer's missing input names the offers it's missing for
    need = oe.preliminary_inputs(R, offer_id, name_offer=lambda s: where(R, s))
    if not need:
        return None
    n = len(listed_assumptions(R, multi))
    return (f"**Preliminary: based on limited data.** Add {', '.join(need)} to sharpen the numbers; "
            f"{n} input{'s are' if n != 1 else ' is'} assumed in total (listed at the end).")


def data_note(R, multi=False):
    bits = []
    if not R["seller"]["payoff_known"]:
        bits.append("Nets are **before mortgage payoff**.")
    if not R["listing"]["cma_provided"]:
        bits.append("No CMA yet: appraisal risk is measured against list price.")
    shown = listed_assumptions(R, multi)
    n, hi = len(shown), sum(a["impact"] == "high" for a in shown)
    more = " (each offer's single review lists the rest)" if len(shown) < len(R["missing"]) else ""
    bits.append(f"{n} input{'s' if n != 1 else ''} assumed ({hi} high-impact); see Assumptions & Data to Confirm{more}."
                if n else "All key inputs provided.")
    return " ".join(bits)


def where(R, scope, also=()):
    """An assumption's scope for display: 'offer A' becomes the offer's label; an assumption shared by several offers
    (OFR-119) names each."""
    def one(s):
        if s.startswith("offer "):
            o = next((x for x in R["offers"] if x["id"] == s[6:]), None)
            return o["label"] if o else s.title()
        return s.title()
    return ", ".join(one(s) for s in [scope, *also])


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


def walk_away(o):
    """(until, note): when the buyer's last cancel right ends, counted from acceptance (the Effective Date isn't set
    yet): the longest open window (OFR-267), AGA-1's included. AGA-1's renegotiation window only opens when the
    valuation plus the gap is below the price, so the note says the days after the other windows close are that
    condition. OFR-121: when the inspection walk-away (AS IS, Rider K or L) ends sooner, the note says until when the
    buyer may cancel for any reason."""
    ex = o.get("risk_days_ex_appraisal", o["risk_days"])
    notes = []
    wd = o.get("walkaway_days") or 0
    if wd and wd < o["risk_days"]:
        start = o["firm_date"] - timedelta(days=o["risk_days"])
        notes.append(f"For any reason until {start + timedelta(days=wd):%b %-d} ({wd}-day inspection period"
                     + (f", {o['contract_label']}" if o["contract_form"] in oe.cf.FRBAR else "")
                     + "); after that only under the loan, appraisal or rider terms.")
    if o.get("appraisal_form") == "aga" and ex < o["risk_days"] == o["appraisal_days"]:
        first = o["firm_date"] - timedelta(days=o["risk_days"] - ex)
        notes.append(f"After {first:%b %-d} ({ex} days) only if the valuation plus the gap comes in below the price (AGA-1).")
    return f"{o['firm_date']:%a %b %-d} ({o['risk_days']} days from acceptance)", " ".join(notes) or None


def downside_hits(o):
    """OFR-258: what the downside case counts for this offer: 'appraisal' when a low appraisal cuts the price,
    'inspection' when there's a repair credit or repair limit."""
    return [k for k, on in (("appraisal", o["downside_price"] < o["price"]), ("inspection", bool(o["repair_reserve"]))) if on]


def downside_note(o):
    """'if the appraisal and inspection go badly', or only the part that applies to this offer."""
    hits = downside_hits(o)
    if hits == ["appraisal", "inspection"]:
        return "if the appraisal and inspection go badly"
    if hits == ["appraisal"]:
        return "if the appraisal comes in low"
    if hits == ["inspection"]:
        return "if the inspection goes badly"
    return "same as offered: no appraisal or inspection cost applies"


def title(action, o):
    """OFR-265: the recommendation as a heading that names the offer, "Counter the $382K FHA Offer", never
    "Counter: $382K FHA" (which reads like a counter at the offer's price)."""
    name = o["ref"][4:-6] if o["ref"].startswith("the ") and o["ref"].endswith(" offer") else o["label"]
    return {"ACCEPT": f"Accept the {name} Offer", "COUNTER": f"Counter the {name} Offer",
            "BACKUP": f"Hold the {name} Offer as Backup", "DECLINE": f"Decline the {name} Offer",
            "INCOMPLETE": f"Contract Incomplete: the {name} Offer"}.get(action, f"{action.title()}: the {name} Offer")


def respond_by(o):
    """The time for acceptance, or that it has passed (never a past date to beat)."""
    if not o.get("expires"):
        return "No time stated"  # OFR-120: a fact, not a place to look
    return f"Passed ({o['expires']})" if o.get("lapsed") == "passed" else \
        f"Likely passed ({o['expires']})" if o.get("lapsed") == "likely" else o["expires"]


def certainty(o, S):
    dl = S["deadline"]
    return {
        "score": o["score"]["total"], "band": o["score"]["band"][1], "band_class": o["score"]["band"][0],
        "walk_away_until": walk_away(o)[0], "walk_away_note": walk_away(o)[1],
        "deposit": f"{money(o['deposit'])} ({o['deposit'] / o['price']:.1%})" if o["deposit"] is not None else "not provided",
        "closing": (f"{o['close']:%b %-d} vs. {dl:%b %-d} deadline" if dl else f"{o['close']:%b %-d} ({o['close_days']} days)"),
        "closing_ok": (o["close"] <= dl) if dl else True,
        "threat": threat(o),
    }


def row(term, offered, counter, why):
    return {"term": term, "offered": offered, "counter": counter, "why": why}


# --- single offer ------------------------------------------------------------

def incomplete_view(R, o):
    """A contract that can't be reviewed as written: what to fix, the numbers as written, and no recommendation.

    An offer whose only Blocking issue is a passed time for acceptance can be revived by a seller counter, so the view
    also carries what that counter could look like (`revive`), labeled as reference, never as a recommendation."""
    S = R["seller"]
    issues = "; ".join(f["issue"].rstrip(".") for f in o["blocking"])
    fixes = [f for f in o["flags"] if f.get("contract") and f["sev"] in ("Blocking", "High")]
    expired_only = all(f.get("topic") == "expired" or "expired" in (f.get("agent_topics") or ()) for f in o["blocking"])
    revive = None
    if expired_only and o["counter_rows"]:
        cn = o["ns_counter"]["net_adj"]
        # FH-103: the facts (the offer's own deadline has passed), never a conclusion about whether it can be accepted
        revive = {"note": "The offer's time for acceptance has passed. A seller counter sets a new time for acceptance. "
                          "For reference only, this is what a counter could look like:",
                  "rows": [row(*r) for r in o["counter_rows"]],
                  "summary": f"net after holding {money(o['ns']['net_adj'])} as written → {money(cn)} with this counter"}
    nxt = ("ask the buyer's agent for a corrected, fully signed contract with every page and rider, then run the review again."
           if not expired_only else
           "the time for acceptance has passed. If the seller wants this buyer, approve a counter with a new time for "
           "acceptance, or I'll ask the buyer's agent to re-sign it with a new time for acceptance.")
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": "INCOMPLETE", "headline": "CONTRACT INCOMPLETE", "title": title("INCOMPLETE", o),
        "why": (f"This contract can't be reviewed as written: {issues[:1].lower() + issues[1:]}. There is no recommendation, "
                + ("counter or ranking until the buyer's agent sends a corrected, fully signed contract." if not expired_only else
                   "and it isn't ranked; a seller counter would set a new time for acceptance.")
                + " The numbers below are for reference only. For questions about whether the contract is binding, see a "
                "real estate attorney."),
        "offers_active": len(R["active"]) + len(R["incomplete"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": respond_by(o), "respond_by_offer": o["label"] if o.get("expires") else None,
        "priority": S.get("priority_note") or S["priority"].title(),
        "fixes":[{"sev": f["sev"], "issue": f["issue"], "fix": f["fix"]} for f in fixes],
        "counter": None, "compare": None, "revive": revive,
        "kpis": [{"label": "Offer Price", "value": money(o["price"]), "note": price_note(o), "tone": "brand"},
                 {"label": "Net as Written", "value": money(o["ns"]["net_adj"]), "note": "for reference only", "tone": ""},
                 {"label": "Downside Net", "value": money(o["ns_down"]["net_adj"]), "note": downside_note(o), "tone": "risk"},
                 {"label": "Seller's Target Net", "value": money(o["target"]["net_adj"]), "note": "list price, clean terms", "tone": ""}],
        "certainty": certainty(o, S),
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in o["flags"] if not f.get("contract")][:3],  # contract issues are in fixes
        "options": [],
        "preliminary": None,
        "next_step": cap(nxt),  # OFR-264: a sentence after "Next Step:"
        "data_note": data_note(R),
    }


def counter_what(vs_offer, vs_downside, certainty, act):
    """OFR-16: the Counter row says what actually changes: net up or down, certainty up or down."""
    net = (f"{signed(vs_offer)} net vs. as offered" if vs_offer >= 0 else
           f"{signed(vs_offer)} on paper, {signed(vs_downside)} vs. the realistic downside")
    sure = ("more certain to close" if certainty > 0 else "less certain to close" if certainty < 0 else "same certainty")
    text = f"{net}; {sure} ({certainty:+d} points)" if certainty else f"{net}; {sure}"
    return text if act == "COUNTER" else text + ", and it risks losing a strong offer"

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
        sc = o["score"]["total"]  # OFR-23: the wording follows the score band
        why = (f"Strong offer: nets {money(ao)} with {sc}/100 certainty. Nothing in the terms is worth risking the deal over."
               if sc >= 80 else f"Nets {money(ao)} with {sc}/100 certainty. No counter would improve it, so accept it with its risks "
               "in view (see the risk flags).")
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
            {"label": "Downside Net", "value": money(dn), "note": downside_note(o), "tone": "risk"}]
    if act == "COUNTER":
        kpis.append({"label": "Net with Our Counter", "value": money(cn), "tone": "good",
                     "note": f"{signed(cn - ao)} vs. as offered" if cn >= ao else f"{signed(cn - dn)} vs. downside; protects the price"})
    else:
        kpis.append({"label": "Seller's Target Net", "value": money(tgt), "note": "list price, clean terms", "tone": ""})

    score = o["score"]["total"]
    opts = [{"option": "Accept as Written", "net": money(ao), "certainty": f"{score}/100", "status": "good" if score >= 80 else "risk",
             "what": "Deal as signed" if score >= 80 else f"Realistic net closer to {money(dn)} {downside_note(o)}" if dn < ao
             else "Deal as signed, with its risks in view (see the risk flags)",  # OFR-258: never "closer to" the same net
             "recommended": act == "ACCEPT"}]
    if o["counter_rows"]:
        opts.append({"option": "Counter", "net": money(cn), "certainty": f"≈{o['counter_score']}/100 if accepted",
                     "status": "good" if act == "COUNTER" else "caution", "recommended": act == "COUNTER",
                     "what": counter_what(cn - ao, cn - dn, o["counter_score"] - score, act)})
    opts.append({"option": "Decline", "net": "—", "certainty": "—", "status": "caution", "recommended": act == "DECLINE",
                 "what": f"Stay on market; each extra month costs about {money(S['holding_monthly'])} in holding costs"})
    if act == "BACKUP":
        opts.insert(0, {"option": "Hold as Backup", "net": money(ao), "certainty": f"{score}/100", "status": "caution",
                        "what": f"Steps in if {top['ref']} falls through; until then the backup buyer can cancel "
                                "(Back-Up Contract Rider W)", "recommended": True})

    expires = f" before {o['expires']}" if o.get("expires") and not o.get("lapsed") else ""
    nxt = {"COUNTER": f"approve the counter terms and I'll send the counter to the buyer's agent{expires}.",
           "ACCEPT": "sign the contract and I'll open escrow and calendar every deadline.",
           "BACKUP": "once the primary contract is fully signed, approve offering this buyer a backup position on the "
                     "Back-Up Contract rider, with a short notice date: the backup buyer can cancel until the seller's notice.",
           "DECLINE": "approve, and with your written OK I'll tell the buyer's agent the seller is moving forward with another offer."}[act]
    return {
        "mode": "single", "offer": o["id"], "offer_label": o["label"], "buyer": o["buyer"],
        "action": act, "headline": "HOLD AS BACKUP" if act == "BACKUP" else act, "title": title(act, o), "why": why,
        "offers_active": len(R["active"]) if multi_ctx else 1,
        "respond_by": respond_by(o), "respond_by_offer": o["label"] if o.get("expires") else None,
        "priority": S.get("priority_note") or S["priority"].title(),
        "counter": counter, "compare": compare, "kpis": kpis,
        "certainty": certainty(o, S),
        "risks": [{"sev": f["sev"], "issue": f["issue"]} for f in o["flags"][:3]],
        "options": opts,
        "preliminary": preliminary(R, o["id"] if multi_ctx else None),
        "next_step": cap(nxt),  # OFR-264
        "data_note": data_note(R),
    }


# --- multiple offers ---------------------------------------------------------

def first_expiry(R):
    """(when, offer label) of the first offer to expire."""
    ex = [o for o in R["active"] + R["incomplete"] if o.get("expires_raw") and not o.get("lapsed")]
    if not ex:  # OFR-120: no deadline in the files is a fact to state, not a place to look
        return "No time stated", None
    def when(o):  # OFR-263: a date alone is the end of that day
        s = str(o["expires_raw"]).strip()
        return s if len(s) > 10 else f"{s} 23:59"
    o = min(ex, key=when)
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
            # OFR-251: the backup keeps its own price; a counter price would read as an ask. Only an escalated price
            # differs from what the buyer wrote, and then the note says why.
            t = (f"After {top['label']}'s contract is fully signed, offer a backup position on the Back-Up Contract rider"
                 + (f" (at {money(o['price'])}: {low_first(o['escalation_note'])})" if o.get("escalated") else ""))
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

    ranked = [{"rank": i + 1, "offer": o["label"], "key": o["key"],
               "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
               "price": money(o["price"]) + (" (escalated)" if o.get("escalated") else ""), "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]),
               "score": o["score"]["total"], "band_class": o["score"]["band"][0], "risk_days": o["risk_days"],
               "close": f"{o['close']:%b %-d}", "action": "Hold as Backup" if o["action"] == "BACKUP" else o["action"].title(),
               "status": {"ACCEPT": "good", "COUNTER": "good", "BACKUP": "caution", "DECLINE": "risk"}[o["action"]],
               "terms": terms[o["id"]]} for i, o in enumerate(rk)]
    ranked += [{"rank": "—", "offer": o["label"], "key": o["key"],
                "financing": oe.FIN_LABEL[o["financing"]] + ("" if not o["financed"] else f" · {o['down_pct'] * 100:.{0 if o['down_pct'] >= .1 else 1}f}%"),
                "price": money(o["price"]), "net": "—", "downside": "—", "score": "—", "band_class": "na", "risk_days": "—",
                "close": f"{o['close']:%b %-d}", "action": "Incomplete", "status": "risk",
                # OFR-120: only the first letter goes lowercase, so dates and times keep their case
                "terms": "Contract can't be reviewed as written: " + low_first(o["blocking"][0]["issue"].rstrip("."))}
               for o in R["incomplete"]]

    most_certain = max(R["active"], key=lambda o: (o["score"]["total"], o["ns_down"]["net_adj"]))
    first = f"{'Counter' if act == 'COUNTER' else 'Accept'} {top['label']}" + (f", Hold {backup['label']} as Backup" if backup else "")
    opts = [{"option": first, "net": money(top_net), "recommended": True, "status": "good",
             "certainty": f"≈{top['counter_score']}/100" if act == "COUNTER" else f"{top['score']['total']}/100",
             "what": "Best net with manageable risk" + (f"; {backup['ref']} is a safety net" if backup else "")}]
    g = top["ns_counter"]["net_adj"] - top["ns"]["net_adj"]
    if act == "ACCEPT" and top["counter_rows"] and g > 0:  # OFR-116: never "Only +$0"
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
        "mode": "multi", "offer": top["id"], "offer_label": top["label"], "action": act, "headline": act, "title": title(act, top), "why": lead,
        "offers_active": len(R["active"]) + len(R["incomplete"]), "offers_incomplete": len(R["incomplete"]),
        "respond_by": first_expiry(R)[0], "respond_by_offer": first_expiry(R)[1],
        "priority": S.get("priority_note") or S["priority"].title(),
        "plan_summary": summary, "plan_note": note, "ranked": ranked, "options": opts,
        "preliminary": preliminary(R, top["id"], multi=True), "next_step": cap(nxt), "data_note": data_note(R, multi=True),
        "target_net": money(R["target"]["net_adj"]),
    }


# --- detail for the markdown template ------------------------------------------

def net_sheet_rows(cols):
    """[{label, values[]}] for columns of net sheets; rows that are zero everywhere are skipped (except price and concessions)."""
    # Rows by line key, not position: a rider money line (rent-back, seller financing, an assessment payoff) can be on
    # one column and not another (the Seller's Target never has one), and a missing line reads as 0.
    order, labels = [], {}
    for _, c in cols:
        for key, label, _ in c["lines"]:
            if key not in labels:
                labels[key] = label
                order.append(key)
    rows = []
    for key in order:
        vals = [next((amt for k, _, amt in c["lines"] if k == key), 0) for _, c in cols]
        if key not in ("price", "conc") and all(v == 0 for v in vals):
            continue
        rows.append({"key": key, "label": labels[key], "values": vals})
    return rows


def offer_detail(o):
    cols = [("As Offered", o["ns"]), ("Downside", o["ns_down"])]
    if o["counter_rows"]:
        cols.append(("Counter", o["ns_counter"]))
    return {
        "id": o["id"], "label": o["label"], "buyer": o["buyer"], "buyer_agent": o.get("buyer_agent") or "", "price": money(o["price"]), "financing": fin_str(o),
        "net": money(o["ns"]["net_adj"]), "downside": money(o["ns_down"]["net_adj"]), "counter_net": money(o["ns_counter"]["net_adj"]),
        "downside_note": downside_note(o), "downside_counts": downside_hits(o),  # OFR-258
        "score": o["score"]["total"], "band": o["score"]["band"][1], "action": o.get("action"),
        "close": f"{o['close']:%a %b %-d}", "firm_date": f"{o['firm_date']:%a %b %-d}",
        "flags": [f"{f['sev']}: {f['issue']} {f['fix']}" for f in o["flags"]],
        "flag_keys": [f["topic"] for f in o["flags"] if f.get("topic")],
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
    checked = offers if mode == "single" else R["ranked"] + R["incomplete"]  # OFR-114: a blocked offer still gets its chat notes
    return {
        "ok": True, "mode": mode, "property": L.get("address") or "", "list_price": money(L["list_price"]),
        "value_range": f"{money(L['cma_low'])}–{money(L['cma_high'])}" if L["cma_provided"] else "not provided",
        "summary": view,
        "offers": [offer_detail(x) for x in offers],
        "to_confirm": to_confirm(R),
        "assumptions": [{"impact": a["impact"], "where": where(R, a["scope"], a.get("also") or ()), "what": a["why"]} for a in R["missing"]],
        "cost_notes": L["cost_notes"],
        "market_notes": R["market_notes"],
        # chat only (never on the report): the best-effort line for a contract that isn't FR/BAR, and revision notes
        **oe.cf.support([x["contract_form"] for x in checked], [(x["contract_form"], x.get("form_revision")) for x in checked]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("listing")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single-offer report")
    a = ap.parse_args(argv)
    try:
        with open(a.listing, encoding="utf-8") as f:
            data = json.load(f)
        R = analyze(data, cma=load_cma(data, a.cma))
        out = result(R, a.mode, a.offer)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": [str(e)]}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
