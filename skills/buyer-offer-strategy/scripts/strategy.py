"""Build the buyer's offer: a recommended offer inside the buyer's limits, up to two alternatives, outlook bands, and
the one document model every output reads.

    python3 scripts/strategy.py buyer.json [--cma file.cma.json] [--option recommended|stronger|lower_cost]

Every option is scored by the shared offer engine the listing side uses (seller net, appraisal downside, certainty
score, likely counter), so "best" means best as a listing agent would judge it. Prints the document model as JSON, every
value already formatted (shared/fmt): the page-1 summary, the options side by side, the seller net sheet, the
scorecard, the buyer's cash, the market check, the pushback, the assumptions (What to Confirm), the notes (each once),
the worksheet for the chosen option and the chat lines. Or {"ok": false, "problems": [...]}. render.py places this same
model (render.main's compute step), so chat, markdown and both PDFs agree. See references/buyer-file.md for the input.

Every label and sentence this script writes is a template in assets/labels.json; text the model writes into the buyer
file (the value range's source) is checked for figures (prose.figures). The input is never changed.
"""
import argparse
import copy
import json
import math
import os
import re
import sys
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _shared import contract_forms as cf, dates, finance, fmt, handoff, notes, offer_engine as oe, profiles, prose  # noqa: E402

LABELS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "labels.json")
with open(LABELS_PATH, encoding="utf-8") as _f:
    L_ = json.load(_f)

money = fmt.money
# Competitiveness thresholds (strong / competitive / at risk) per competition level. Starting judgments.
BANDS = {0: (55, 40, 30), 1: (65, 55, 45), 2: (75, 60, 50), 3: (85, 72, 60)}
BAND_RANK = {"strong": 3, "comp": 2, "risk": 1, "unl": 0}
OPTIONS = ("recommended", "stronger", "lower_cost")
DEFAULT_RATE = 6.5  # national planning estimate, used only when neither the buyer file nor a lookup has a rate
DEFAULT_RESERVE = 2000
OFFER_QUESTIONS = ("contract_name", "escalation_accepted")  # OFR-222: shape the offer itself, so asked first in to_confirm
HIGHEST_AND_BEST = re.compile(r"highest\s*(?:and|&)\s*best", re.I)  # OFR-239: as the agent words it in competition.note
TIGHT_SUPPLY_MONTHS = 3  # OFR-331: under this a price cut alone doesn't read soft
SOFT_SUPPLY_MONTHS = 6  # over this the area's market reads soft (3 to 6 months reads balanced)
MIN_CONCESSION_ASK = 1000  # a smaller seller-concession ask isn't worth asking for: it drops to $0 or rounds up
TIGHT_RESERVE = (1000, 0.10)  # OFR-332: a cushion under $1,000 or 10% of the floor, whichever is more, is thin
# OFR-327: a costs.rate_source that names the buyer's lender or a quote is the lender's rate, not a looked-up average
LENDER_QUOTE = re.compile(r"lender|quot|loan officer|loan estimate|pre-?approv", re.I)
CONVENTIONAL_AVERAGE = re.compile(r"freddie|pmms", re.I)  # the weekly survey is conventional loans


def t(_key, **kw):
    """A labels.json template, filled."""
    return fmt.fill(L_[_key], **kw)


def cap(text):
    return text[:1].upper() + text[1:]


def low_first(text):
    return text[:1].lower() + text[1:]


def joined(items):
    """'a', 'a and b', 'a, b and c'."""
    items = [x for x in items if x]
    return items[0] if len(items) == 1 else ", ".join(items[:-1]) + f" {L_['and']} " + items[-1] if items else ""


def rnd(v, step=1000, how="round"):
    """A multiple of `step`: down, up, or the nearest (half-up, never Python's half-to-even)."""
    if how == "round":
        return int(fmt.half_up(v, step))
    return int({"up": math.ceil, "down": math.floor}[how](v / step) * step)


def _d(v):
    return v if isinstance(v, date) or v is None else datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def day(d):
    """'Nov 2' (the report's year is in its header)."""
    return fmt.date_short(d, year=False)


def wday(d):
    """'Mon Nov 2'."""
    return fmt.date_short(d, year=False, weekday=True)


def per_month(v):
    return t("per_month", amount=money(v))


def comp_label(lvl):
    return L_["comp_level"][lvl]


def comp_words(lvl):
    return L_["comp_words"][lvl]


def opt_name(k):
    return L_["option_name"][k]


def why(key, *adds, **kw):
    """A reason by label key, with its figures already formatted and any added clauses (why() dicts) after it."""
    out = {"key": key, **kw}
    if adds:
        out["adds"] = [a for a in adds if a]
    return out


def add_to(w, extra):
    return {**w, "adds": list(w.get("adds") or []) + [extra]}


def why_text(w):
    """A reason's sentence."""
    if not w:
        return ""
    kw = {k: v for k, v in w.items() if k not in ("key", "adds")}
    return t(w["key"], **kw) + "".join(why_text(a) for a in w.get("adds") or [])


# --- inputs ------------------------------------------------------------------

def load_cma(data, cma_path=None):
    """The CMA handoff: --cma file first, else a handoff stored in the buyer file under 'cma'."""
    if cma_path:
        return handoff.load(cma_path)
    if isinstance(data.get("cma"), dict):
        return handoff.validate(data["cma"])
    return None


MARKET_NUMBERS = ("sale_to_list", "months_supply", "median_dom", "share_with_seller_costs", "typical_seller_paid")


def text_problems(data):
    """What the model wrote into the buyer file that the report can't print as is, as `field: problem → fix` lines
    (every one at once). The script prints every figure itself: market facts are numbers, and the value range's
    source is a name in words (its date goes in value.as_of)."""
    probs = []
    for key in MARKET_NUMBERS:
        v = (data.get("market") or {}).get(key)
        if v is not None and (isinstance(v, bool) or not isinstance(v, (int, float))):
            probs.append(t("prob_market_number", field=f"market.{key}", value=json.dumps(v), fix=L_["fix_market"][key]))
    src = (data.get("value") or {}).get("source")
    if src and prose.figures(src):
        probs.append(t("prob_figure", field="value.source", value=json.dumps(src), found=", ".join(prose.figures(src)),
                       fix=L_["fix_value_source"]))
    return probs


def apply_cma(B, h):
    """Fill the buyer file from a cma-handoff v1 record. Only fills what the file doesn't already say."""
    B = copy.deepcopy(B)
    P, V, M = B.setdefault("property", {}), B.setdefault("value", {}), B.setdefault("market", {})
    K = B.setdefault("costs", {})
    s, v, mk = h.get("subject") or {}, h["value"], h.get("market") or {}
    B["_cma_address_note"] = oe.address_note(h, P.get("address"))  # CMA-102
    for key in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                "hoa_monthly", "hoa_frequency", "flood_zone", "dom", "price_cuts", "annual_tax"):
        if s.get(key) not in (None, "") and P.get(key) in (None, ""):
            P[key] = s[key]
            if key == "dom":  # OFR-242: the handoff's days on market were counted on its as_of date, so age them
                B["_dom_aged"] = age_dom(P, s["dom"], h.get("as_of"), _d(B.get("analysis_date")) or date.today())
    # CMA-111: the tax the CMA computed for the buyer (millage and homestead), so both reports show the same payment
    if K.get("tax_rate") is None and K.get("total_mills") is None and s.get("total_mills") is not None:
        for key in ("school_mills", "total_mills", "homestead"):
            if s.get(key) is not None and K.get(key) is None:
                K[key] = s[key]
    # the premium the buyer CMA's payment used, so the two reports show the same insurance and payment at the same
    # price; the buyer file's own premium or rate wins. An older handoff without it: the estimate at the CMA's target
    if K.get("insurance_annual") is None and K.get("insurance_rate") is None:
        if isinstance(s.get("insurance_annual"), (int, float)):
            K["insurance_annual"] = s["insurance_annual"]
            B["_cma_insurance"] = {"annual": s["insurance_annual"], "price": s.get("insurance_price"),
                                   "estimated": s.get("insurance_estimated", True)}
        elif (h.get("offer_plan") or {}).get("opening") is not None:
            B["_insurance_price"] = target_price(h["offer_plan"])
    W = B.setdefault("worksheet", {})  # the property report's legal description and tax ID, for paragraph 1
    for key in ("legal_description", "parcel_id"):
        if s.get(key) and not W.get(key):
            W[key] = s[key]
    mp = h.get("market_profile") or {}
    if mp.get("state") and not P.get("state"):
        P["state"] = mp["state"]
    if mp.get("mls") and not P.get("mls"):  # OFR-211: the MLS the CMA was built from
        P["mls"] = mp["mls"]
    for key, val in (("cma_low", v["low"]), ("cma_high", v["high"]), ("midpoint", v["midpoint"]),
                     ("median_adjusted", v.get("median_adjusted"))):
        if V.get(key) is None and val is not None:  # OFR-24: an explicit null in the file counts as missing
            V[key] = val
    if V.get("source") in (None, "") and V.get("as_of") in (None, ""):
        V["source"] = L_["src_cma"][h.get("side") or "buyer"] if (h.get("side") or "buyer") in L_["src_cma"] else None
        V["as_of"] = h.get("as_of")
    B["_cma_side_note"] = oe.side_note(h, "buyer")
    for ours, theirs in (("sale_to_list", ("sale_to_list", "sale_to_list_recent", "sale_to_original_list_recent")),
                         ("median_dom", ("median_dom", "median_days_recent", "median_days")),
                         ("months_supply", ("months_supply",)),
                         ("share_with_seller_costs", ("share_with_seller_costs", "share_with_seller_paid_costs_recent")),
                         ("typical_seller_paid", ("typical_seller_paid", "median_seller_paid_recent"))):
        src = next((k for k in theirs if mk.get(k) is not None), None)
        val = mk[src] if src else None
        if isinstance(val, (int, float)) and not isinstance(val, bool) and M.get(ours) is None:
            if src == "sale_to_original_list_recent":  # the ratio is against the original list price: labeled so
                M["sale_to_list_basis"] = "original"
            if ours == "typical_seller_paid" and not val:
                continue
            M[ours] = val
    if h.get("offer_plan") and not B.get("cma_offer_plan"):
        B["cma_offer_plan"] = h["offer_plan"]
    return B


def target_price(op):
    """The CMA offer plan's target, as the buyer CMA figures its payment: the middle of target_low to target_high, else
    the one given, else the opening."""
    lo, hi = op.get("target_low"), op.get("target_high")
    if lo is not None and hi is not None:
        return (lo + hi) / 2
    return lo if lo is not None else hi if hi is not None else op.get("opening")


def age_dom(P, dom, as_of, today):
    """OFR-242: days on market from a CMA handoff, moved forward by the days since its as_of date. Sets P['dom'] and
    returns (the handoff's figure, its date, days added) when it moved, else None."""
    try:
        since = (today - _d(as_of)).days if as_of else 0
    except ValueError:
        return None
    if since <= 0 or not isinstance(dom, (int, float)):
        return None
    P["dom"] = dom + since
    return dom, _d(as_of), since


def walk_away(B):
    return (B.get("cma_offer_plan") or {}).get("walk_away")


def prepare(B, A, market=None):
    """Defaults for everything missing, each one logged. Returns (B, costs)."""
    B = copy.deepcopy(B)
    today = _d(B.get("analysis_date")) or date.today()
    P, V, K = B.setdefault("property", {}), B.setdefault("value", {}), B.setdefault("costs", {})
    M, C, LS, BU = B.setdefault("market", {}), B.setdefault("competition", {}), B.setdefault("listing_side", {}), B.setdefault("buyer", {})
    if not P.get("list_price"):
        raise oe.OfferError(L_["err_list_price"])
    for D, key in ((M, "median_dom"), (P, "dom")):  # OFR-336: whole days ("23", never "23.0")
        if isinstance(D.get(key), float):
            D[key] = fmt.half_up(D[key])
    given_market = market
    city = city_of(P.get("address"))
    if market is None and not P.get("county") and city:  # OFR-213: the built-in tax districts name the city's county
        county = profiles.county_for_city(oe.state_of(P), city)
        if county:
            P["county"] = A.add("property", "county", county, t("as_county", county=county, city=city), "low")
    if market is None and P.get("mls"):  # OFR-211: the MLS from the buyer file or the CMA handoff
        market = profiles.load_market(state=oe.state_of(P), county=P.get("county"), mls=P["mls"])
    costs = oe.load_costs(P, market)
    if given_market is None and not oe.state_of(P):
        A.add("property", "state", None, L_["as_state"], "high")
    lp = P["list_price"]
    if not (V.get("cma_low") and V.get("cma_high")):
        A.add("value", "cma_low / cma_high", "list price", L_["as_value"], "high")
        V["cma_low"], V["cma_high"] = V.get("cma_low") or lp, V.get("cma_high") or lp
        V["assumed"] = True
    V["mid"] = V.get("midpoint") or (V["cma_low"] + V["cma_high"]) / 2
    V["point"] = V.get("median_adjusted") or V["mid"]  # best single value estimate, for the price anchor

    lux_at = BU.get("luxury_threshold") or (B.get("settings") or {}).get("luxury_threshold", 1_000_000)
    if lp >= lux_at:
        conv_down, why_down = 0.20, t("down_why_lux", amount=money(lux_at))
    elif BU.get("first_time_buyer"):
        conv_down, why_down = 0.03, L_["down_why_first"]
    else:
        conv_down, why_down = 0.05, L_["down_why_std"]
    fin = finance.ALIASES.get(str(BU.get("financing") or "").lower(), str(BU.get("financing") or "").lower())
    BU["financing_source"] = "input"
    if fin not in finance.LOAN_PROGRAMS:
        if BU.get("financing"):
            A.add("buyer", "financing_unknown", "conventional", L_["as_financing_unknown"], "high")
        fin = "conventional"
        BU["financing_source"] = "assumed"
        dp = BU.get("down_pct") if BU.get("down_pct") is not None else conv_down
        A.add("buyer", "financing", f"conventional {fmt.pct(dp, 1)}",
              t("as_financing_given_down", down=fmt.pct(dp, 1)) if BU.get("down_pct") is not None else
              t("as_financing", down=fmt.pct(dp, 1), why=why_down), "high")
    BU["financing"] = fin
    dflt_down = conv_down if fin == "conventional" else finance.LOAN_PROGRAMS[fin]["min_down"]
    if fin == "cash":
        BU["down_pct"] = 1.0
    elif BU.get("down_pct") is None:
        BU["down_pct"] = dflt_down
        if BU["financing_source"] == "input":
            A.add("buyer", "down_pct", dflt_down,
                  t("as_down", down=fmt.pct(dflt_down, 1), why=why_down) if fin == "conventional" else
                  t("as_down_program", down=fmt.pct(dflt_down, 1), prog=oe.FIN_LABEL[fin]), "med")
    if fin == "conventional" and BU["down_pct"] < 0.05 and not BU.get("first_time_buyer"):
        A.add("buyer", "down_pct", BU["down_pct"], L_["as_low_down"], "med")
    BU["max_price"] = oe.given(BU, "max_price", max(lp, V["cma_high"]), A, "buyer", L_["as_max_price"], "high")
    if BU.get("cash_available") is None:
        est = fmt.half_up(lp * (BU["down_pct"] + 0.04))
        BU["cash_available"] = A.add("buyer", "cash_available", est, t("as_cash", amount=money(est)), "high")
    BU["reserve_floor"] = oe.given(BU, "reserve_floor", DEFAULT_RESERVE, A, "buyer",
                                   t("as_reserve", amount=money(DEFAULT_RESERVE)), "med")
    if BU.get("closing_cost_pct") is None:
        # One rule with the buyer CMA (finance.buyer_closing_costs): the market's share plus prepaids, plus its loan
        # taxes on the loan (CORE-16); half the market's share for cash
        cash = fin == "cash"
        BU["closing_cost_pct"] = finance.buyer_closing_pct(costs, cash)
        B["loan_taxes"] = [] if cash else finance.loan_taxes(1, costs)
        market_src = costs.described("closing_costs.buyer_closing_cost_pct")
        src = t("cc_src_cash" if cash else "cc_src_financed", market=market_src)
        if B["loan_taxes"]:
            src += t("cc_src_loan_taxes", taxes=joined([t("cc_loan_tax", label=x["label"].lower(),
                                                            rate=fmt.pct(x["rate"], None)) for x in B["loan_taxes"]]))
        A.add("buyer", "closing_cost_pct", BU["closing_cost_pct"], t("as_closing_costs", basis=closing_cost_basis(B), src=src),
              "low")
    BU["approval"] = BU.get("approval") or ("pof_verified" if fin == "cash" else "preapproval")
    BU["lender_min_close_days"] = BU.get("lender_min_close_days") or (21 if fin == "cash" else 35)
    BU.setdefault("agent_track", "average")
    B["payment_assumed"] = []  # OFR-228: the payment inputs that are estimates, named when the payment limit sets the price
    # OFR-241: the skill looks up the latest Freddie Mac weekly 30-year rate when the agent gives none (costs.rate with
    # costs.rate_source naming the week); the built-in rate is only the offline fallback, said in the assumptions
    if K.get("rate") is None:
        B["payment_assumed"].append(t("pa_rate", rate=fmt.pct(DEFAULT_RATE / 100, None)))
    elif K.get("rate_source") and not LENDER_QUOTE.search(str(K["rate_source"])):  # OFR-327: a quote isn't assumed
        prog = oe.FIN_LABEL[fin] if fin in ("fha", "va", "usda") and CONVENTIONAL_AVERAGE.search(str(K["rate_source"])) else None
        rate = fmt.pct(K["rate"] / 100, None)
        B["payment_assumed"].append(t("pa_rate_source_prog" if prog else "pa_rate_source", rate=rate, source=K["rate_source"]))
        A.add("costs", "rate_source", K["rate"], t("as_rate_source_prog", rate=rate, source=K["rate_source"], prog=prog)
              if prog else t("as_rate_source", rate=rate, source=K["rate_source"]), "low")
    K["rate"] = oe.given(K, "rate", DEFAULT_RATE, A, "costs", t("as_rate", rate=fmt.pct(DEFAULT_RATE / 100, None)), "low")
    if not 1 <= K["rate"] < 20:
        raise oe.OfferError(t("err_rate", rate=K["rate"]))
    cma_ins = B.get("_cma_insurance")
    if K.get("insurance_annual") is not None and BU.get("insurance_quote") is None and not cma_ins:
        BU["insurance_quote"] = True  # OFR-217: a premium given for this address is a quote in hand
    if cma_ins and cma_ins["estimated"] and not quote_in_hand(BU):  # the buyer CMA's estimate, carried over
        at = t("at_price", price=money(cma_ins["price"])) if cma_ins.get("price") else ""
        B["payment_assumed"].append(t("pa_insurance", amount=money(K["insurance_annual"])))
        A.add("costs", "insurance_annual", K["insurance_annual"], t("as_ins_cma", amount=money(K["insurance_annual"]), at=at), "low")
    elif K.get("insurance_annual") is None:
        yb = P.get("year_built")
        basis = B.get("_insurance_price") or lp  # an older CMA handoff's target price, as its payment used
        est = finance.insurance_estimate(basis, costs, yb, K.get("insurance_rate"))
        src = (L_["ins_src_agent"] if est["source"] == "agent" else
               costs.described("buyer_costs.insurance_rate") if est["source"] == "market" else L_["ins_src_national"])
        K["insurance_annual"] = est["annual"]
        B["payment_assumed"].append(t("pa_insurance", amount=money(K["insurance_annual"])))
        A.add("costs", "insurance_annual", K["insurance_annual"], t(
            "as_ins_est", amount=money(K["insurance_annual"]), src=src,
            age=t("ins_age", factor=fmt.num(est["age_factor"], 2), year=yb) if est["age_factor"] > 1 else "",
            basis=t("ins_basis", price=money(basis)) if basis != lp else ""), "low")
    elif not quote_in_hand(BU):  # OFR-328: a premium typed in with no quote in hand (false or planned) is an estimate
        B["payment_assumed"].append(t("pa_insurance", amount=money(K["insurance_annual"])))
        A.add("costs", "insurance_annual", K["insurance_annual"], t("as_ins_typed", amount=money(K["insurance_annual"])), "low")
    P["hoa_monthly"] = P.get("hoa_monthly") or 0
    # OFR-26, CMA-6: flood insurance and CDD assessments are payment lines; a missing amount is left out and flagged, never 0
    B["flood"] = finance.flood_insurance(P.get("flood_zone"), K.get("flood_insurance_annual"), costs, today,
                                         condo_unit=finance.property_type(P.get("type")) == "condo")
    if B["flood"]["annual"] is None:
        A.add("costs", "flood_insurance_annual", "not included",
              t("as_flood", note=B["flood"]["note"].replace(" Get a quote; the total leaves it out until then.", "")),
              "med" if B["flood"]["required"] in ("lender", "citizens") else "low")
    if P.get("cdd") and P.get("cdd_annual") is None:
        A.add("property", "cdd_annual", "not included", L_["as_cdd"], "med")
    why_no_millage = find_millage(B, costs, A)
    tax = property_tax(B, costs, lp)
    if tax["annual"] is None:
        A.add("costs", "property_tax", "not included", L_["as_tax_none"], "high" if BU.get("max_payment") else "med")
    elif tax["estimated"]:
        A.add("costs", "property_tax", tax["basis"], t("as_tax_est", basis=tax["basis"].removeprefix("about "),
                                                       src=costs.described("property_tax.fallback_rate"),
                                                       why=f" {why_no_millage}" if why_no_millage else ""), "low")
    elif P.get("annual_tax") in (None, ""):
        # OFR-201: the seller's proration uses the same rate as the buyer's payment, never a second (fallback) rate
        B["seller_annual_tax"] = fmt.half_up(tax["annual"])
        A.add("property", "annual_tax", B["seller_annual_tax"],
              t("as_seller_tax", basis=tax["basis"], amount=money(B["seller_annual_tax"])), "med")
    if K.get("tax_rate") is None and tax["annual"] is not None and K.get("homestead") is None:  # OFR-124
        A.add("costs", "homestead", True, L_["as_homestead"], "low")
    elif K.get("tax_rate") is not None:  # OFR-237: a given rate is used as is; no exemption is taken off it
        A.add("costs", "homestead", "as given", t("as_tax_rate_given", rate=fmt.pct(K["tax_rate"], None)), "low")

    lvl = C.get("level")
    heat, basis = market_heat(P, M)
    C["inferred"] = lvl is None
    if lvl is None:
        lvl = {"hot": 2, "normal": 1, "soft": 0, "stale": 0}[heat]
        signals = P.get("dom") is not None or M.get("sale_to_list") or P.get("price_cuts")
        A.add("competition", "level", comp_label(lvl),
              t("as_competition", level=comp_words(lvl), read=heat_words(heat), basis=basis) if signals else
              t("as_competition_none", level=comp_words(lvl)), "med")
    C["level"], C["heat"], C["heat_basis"] = lvl, heat, basis
    LS["buyer_broker_offered_pct"] = LS.get("buyer_broker_offered_pct")
    LS["listing_fee_pct"] = LS.get("listing_fee_pct")
    B["analysis_date"] = today
    weekday_deadlines(B, today, A)  # OFR-244: "Friday 5 PM" to a date, before any date counts from it
    B["effective_date"] = effective_date(B, today, A)  # OFR-123: dates count from the expected acceptance
    # One contract form for the options, the listing-side scoring and the worksheet: AS IS and Standard math never mix.
    W = B.get("worksheet") or {}
    try:
        form = cf.normalize(W.get("contract_form") or BU.get("contract_form"))
    except cf.FormError as e:
        raise oe.OfferError(str(e)) from e
    if form is None:  # ENG-12: a missing form is a high-impact assumption (CLAUDE.md)
        form = A.add("buyer", "contract_form", cf.AS_IS, L_["as_contract_form"], "high") \
            if cf.farbar_market(costs.get("contract.forms")) else cf.OTHER
    B["contract_form"] = form
    B["words"] = cf.term_words(form)  # OFR-234: FAR/BAR's names on FAR/BAR, generic ones on any other contract
    B["repair_limits"] = W.get("repair_limits") or BU.get("repair_limits")
    # Buyer's broker pay requested from the seller, and how it's paid on a FAR/BAR offer: Rider GG (a separate
    # compensation agreement, the default) or Rider FF (a seller credit to the buyer, which uses the loan program's
    # concession room). contract_forms.buyer_broker_as_credit is the rule.
    B["bb_request"] = bb_request(B, costs)
    route = str(W.get("buyer_broker_form") or BU.get("buyer_broker_form") or "GG").upper()
    B["buyer_broker_form"] = route if form in cf.FARBAR and B["bb_request"][0] else None
    if BU.get("needs_sale") and not BU.get("sale_contingency_days"):
        A.add("buyer", "sale_contingency_days", 21, L_["as_sale_days"], "med")
    if BU.get("buyer_broker_agreement_pct") is None:
        A.add("buyer", "buyer_broker_agreement_pct", "not given", L_["as_bb_agreement"], "med")
    return B, costs


def stl_label(M):
    """The sale-price ratio's name, as the number is measured: against the original list price (a buyer CMA's
    figure) or the list price at sale."""
    return L_["stl_original"] if M.get("sale_to_list_basis") == "original" else L_["stl"]


def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def tight_supply(M):
    return num(M.get("months_supply")) and M["months_supply"] < TIGHT_SUPPLY_MONTHS


def dom_words(dom, med):
    return t("sig_dom", dom=fmt.num(dom), med=fmt.num(med))


def stl_words(M):
    return t("sig_stl_original" if M.get("sale_to_list_basis") == "original" else "sig_stl",
             pct=fmt.pct(M["sale_to_list"], 1, fixed=True))


def market_heat(P, M):
    """OFR-226: (heat, the signals that decide it, in plain words), for inferring the competition. Hot when days on market
    are under half the median or the sale-price ratio is 99%+; soft when days on market are over 1.5x the median or the
    price was cut (soft wins). With under 3 months of supply the market isn't soft: a cut reads normal (OFR-331), and
    long days on market read "stale", this listing's own read (no competition on it, like soft), never the market's."""
    dom, med, stl = P.get("dom"), M.get("median_dom"), M.get("sale_to_list")
    tight = tight_supply(M)
    reads = []  # (the signal in words, what it reads)
    if dom is not None and med:
        reads.append((dom_words(dom, med),
                      "hot" if dom < 0.5 * med else ("stale" if tight else "soft") if dom > 1.5 * med else "normal"))
    if stl:
        reads.append((stl_words(M), "hot" if stl >= 0.99 else "normal"))
    if P.get("price_cuts"):
        reads.append((cuts_words(P["price_cuts"]), "normal" if tight else "soft"))
    got = {rd for _, rd in reads}
    heat = next((h for h in ("soft", "stale", "hot") if h in got), "normal")
    if not reads:
        return heat, None
    return heat, joined([sig for sig, rd in reads if rd == heat])


def heat_words(heat):
    """The inferred read: "the market reads soft", or for a stale listing in a tight market "this home reads stale", so a
    tight market is never called soft."""
    return t("heat_home" if heat == "stale" else "heat_market", heat=L_["heat"][heat])


def area_read(M):
    """The area's market on its own (tight, balanced, soft, hot), from the months of supply the CMA measured, else a
    99%+ sale-price ratio (hot); None with neither."""
    sup = M.get("months_supply")
    if num(sup):
        return "tight" if sup < TIGHT_SUPPLY_MONTHS else "soft" if sup > SOFT_SUPPLY_MONTHS else "balanced"
    return "hot" if M.get("sale_to_list") and M["sale_to_list"] >= 0.99 else None


def listing_read(P, M):
    """This listing on its own: "stale" (days on market over 1.5x the median, or a price cut), "fast" (under half the
    median), "on pace", or None with no days on market or cuts."""
    dom, med = P.get("dom"), M.get("median_dom")
    if (dom is not None and med and dom > 1.5 * med) or P.get("price_cuts"):
        return "stale"
    if dom is not None and med:
        return "fast" if dom < 0.5 * med else "on pace"
    return None


def cuts_words(n):
    if isinstance(n, int) and not isinstance(n, bool):
        return t("sig_cuts_one" if n == 1 else "sig_cuts", n=n)
    return L_["sig_cut"]


def market_read(B):
    """The Market Check's Market Read as (value, note): the market and this listing read apart, so a stale listing never
    makes a tight market read soft: "Tight market, stale listing" with one plain sentence, the market first (months of
    supply, the sale-price ratio), then this home (days on market, price cuts) and, when they disagree, where the
    leverage is."""
    P, M = B["property"], B["market"]
    area, home = area_read(M), listing_read(P, M)
    area_sig = []
    if num(M.get("months_supply")):
        area_sig.append(t("sig_supply", months=fmt.months(M["months_supply"])))
    if M.get("sale_to_list"):
        area_sig.append(stl_words(M))
    home_sig = []
    if P.get("dom") is not None and M.get("median_dom"):
        home_sig.append(dom_words(P["dom"], M["median_dom"]))
    if P.get("price_cuts"):
        home_sig.append(cuts_words(P["price_cuts"]))
    parts = []
    if area:
        parts.append(t("mr_area", area=L_["mr_area_word"][area]) + (t("paren", text=", ".join(area_sig)) if area_sig else ""))
    elif area_sig:
        parts.append(t("mr_nearby", what=joined(area_sig)))
    if home:
        parts.append(t("mr_home", home=L_["mr_home_word"][home]) + (t("paren", text=", ".join(home_sig)) if home_sig else ""))
    if not parts:
        return fmt.EMPTY, None
    note = "; ".join(parts)
    if area in ("tight", "hot") and home == "stale":
        note += L_["mr_leverage_home"]
    elif area == "soft" and home == "stale":
        note += L_["mr_leverage_both"]
    elif area in ("tight", "hot") and home == "fast":
        note += L_["mr_expect"]
    value = ", ".join(w for w in ((t("mr_value_area", area=L_["mr_area_word"][area]) if area else None),
                                  (L_["mr_value_home"][home] if home else None)) if w)
    return (cap(value) if value else fmt.EMPTY), cap(note) + "."


_MONTHS = {m: i for i, m in enumerate(("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1)}


def deadline_date(text, today):
    """The date in an offer deadline as the listing agent gave it ("2026-09-25 17:00", "Fri Sep 25 · 5 PM"), or None."""
    s = str(text or "")
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(\d{1,2})\b", s, re.I)
    if not m:
        return None
    try:
        d = date(today.year, _MONTHS[m.group(1).lower()], int(m.group(2)))
    except ValueError:
        return None
    return d if d >= today - timedelta(days=31) else date(today.year + 1, d.month, d.day)  # a January deadline in December


_WEEKDAY = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)(?:day|s|sday|nesday|rsday|urday|r|rs)?\b\.?", re.I)
_WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\b\.?", re.I)
_CLOCK = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")


def clock_of(text):
    """(hour, minute) in "5 PM", "5:30pm" or "17:00", else None."""
    m = _TIME.search(str(text or ""))
    if m:
        return int(m.group(1)) % 12 + (12 if m.group(3).lower() == "p" else 0), int(m.group(2) or 0)
    m = _CLOCK.search(str(text or ""))
    return (int(m.group(1)), int(m.group(2))) if m else None


def weekday_date(text, today):
    """OFR-244: a deadline given only as a weekday ("Friday 5pm", "Fri 6 PM") as (date, (hour, minute) or None): the
    next such day from `today` (today counts). None when the text has a full date, or no weekday."""
    s = str(text or "")
    if deadline_date(s, today) or not _WEEKDAY.search(s):
        return None
    wd = _WEEKDAYS.index(_WEEKDAY.search(s).group(1).lower())
    return today + timedelta(days=(wd - today.weekday()) % 7), clock_of(s)


def deadline_iso(text, today):
    """A deadline as "YYYY-MM-DD HH:MM" (or "YYYY-MM-DD"), whatever way it was written; None when it has no date."""
    d = deadline_date(text, today)
    if not d:
        return None
    m = re.search(r"\d{4}-\d{2}-\d{2}[ T](\d{1,2}):(\d{2})", str(text))
    tm = (int(m.group(1)), int(m.group(2))) if m else clock_of(re.sub(r"\d{4}-\d{2}-\d{2}", "", str(text)))
    return f"{d}" + (f" {tm[0]:02d}:{tm[1]:02d}" if tm else "")


def weekday_deadlines(B, today, A):
    """OFR-244: a weekday-only offer deadline or Time for Acceptance becomes "YYYY-MM-DD HH:MM". When the day it resolves
    to is more than 5 days out (so today is the day after that weekday), the agent may have meant the one just passed:
    the resolved date is recorded as an assumption to confirm."""
    for scope, holder, key, name in (("competition", B.get("competition") or {}, "deadline", L_["name_deadline"]),
                                     ("worksheet", B.get("worksheet") or {}, "acceptance_deadline", L_["name_acceptance"])):
        hit = weekday_date(holder.get(key), today)
        if not hit:
            continue
        (d, tm), given_ = hit, holder[key]
        holder[key] = f"{d}" + (f" {tm[0]:02d}:{tm[1]:02d}" if tm else "")
        ahead = (d - today).days
        if ahead > 5:
            A.add(scope, "deadline", holder[key], t("as_deadline_weekday", name=name, when=fmt.when(holder[key], "deadline"),
                                                    days=ahead, last=wday(d - timedelta(days=7))), "med")


def effective_date(B, today, A):
    """OFR-123: the expected Effective Date the closing and deposit dates count from: `expected_effective_date`, else the
    day after the offer deadline, else the day after the analysis date (recorded as an assumption)."""
    given_ = B.get("expected_effective_date")
    if given_:
        return _d(given_)
    due = deadline_date((B.get("worksheet") or {}).get("acceptance_deadline") or (B.get("competition") or {}).get("deadline"), today)
    eff = (due or today) + timedelta(days=1)
    # the worksheet's Time for Acceptance is a business day at 5:00 PM, so the dates count from that same day
    moved = not dates.is_business_day(eff)
    if moved:
        eff = dates.next_business_day(eff)
    A.add("buyer", "expected_effective_date", str(eff), t("as_effective", date=wday(eff),
                                                          which=L_["eff_business" if moved else "eff_day"],
                                                          after=L_["eff_after_deadline" if due else "eff_after_today"]), "low")
    return eff


def city_of(address):
    """The city in a one-line address ("…, Casselberry, FL 32707" -> "Casselberry"), or None."""
    parts = [x.strip() for x in str(address or "").split(",")]
    return (parts[-2] or None) if len(parts) >= 3 else None


def find_millage(B, costs, A):
    """OFR-124: the built-in millage for the property's taxing district, as the CMA skills do: `costs.district` (a name
    or the appraiser's tax-area code), else the address's city. Returns why no district was used (it goes in the
    fallback rate's assumption), or None."""
    K, P = B["costs"], B["property"]
    if K.get("tax_rate") is not None or K.get("total_mills") is not None:
        return None
    district = K.get("district")
    by_city = not district
    district = district or city_of(P.get("address"))
    if not district or not costs.get("property_tax.millage"):
        return None
    if not P.get("county"):  # OFR-213: prepare() fills the county from the city when a built-in district names it
        return t("millage_no_county", district=district)
    rows = finance.millage(costs, county=P["county"], district=district)
    if not rows:
        return t("millage_not_built_in", district=district, county=P["county"])
    names = [str(r.get("district")) for r in rows]
    if len({n.split(" (")[0] for n in names}) > 1:  # different places: never a guess
        return finance.millage_row(costs, P["county"], district)[1]
    # One place in several districts (Orlando spans two water-management districts): the higher millage, so the payment
    # isn't understated, flagged with both names
    row = max(rows, key=lambda x: x["total"])
    K["school_mills"], K["total_mills"] = row["school"], row["total"]
    A.add("costs", "total_mills", row["total"], t("as_millage", district=row["district"], year=row.get("year", ""))
          + (L_["as_millage_city"] if by_city else "")
          + (t("as_millage_spans", city=district, n=len(rows), names=joined(names)) if len(rows) > 1 else ""),
          "med" if by_city or len(rows) > 1 else "low")
    return None


# --- money for the buyer -----------------------------------------------------

def closing_cost_basis(B):
    """OFR-215: how the closing costs are figured, in words that match the math ("3% of price plus loan taxes")."""
    return t("cc_basis_taxes" if B.get("loan_taxes") else "cc_basis", pct=fmt.pct(B["buyer"]["closing_cost_pct"], 1))


def quote_in_hand(BU):
    """An insurance quote the buyer has (True, or a premium in costs.insurance_annual: OFR-217); "planned" isn't one."""
    q = BU.get("insurance_quote")
    return bool(q) and q != "planned"


def closing_costs(B, price):
    """The buyer's closing costs at `price`, by the shared rule (finance.buyer_closing_costs): the share of price, plus
    the market's loan taxes when that share is the market's own (a given share already includes them)."""
    BU = B["buyer"]
    loan = finance.loan_amount(price, BU["financing"], BU["down_pct"], bool(BU.get("va_later_use")), bool(BU.get("va_exempt")))
    rates = B.get("loan_taxes") or []
    # finance.buyer_closing_costs' arithmetic: each loan tax rounded, then the total rounded once (half-up)
    return fmt.half_up(price * BU["closing_cost_pct"] + sum(fmt.half_up(loan * x["rate"]) for x in rates))


def cash_ledger(B, t_):
    """The buyer's cash to close at the terms `t_` as a finance.Ledger: down payment, closing costs, any buyer's broker
    fee the seller doesn't pay, less the seller's concessions (never more than the closing costs). Every line is rounded
    once; cash to close is their sum."""
    BU = B["buyer"]
    led = finance.Ledger()
    led.cost("down", L_["cr_down"], t_["price"] * BU["down_pct"])
    cc = led.cost("cc", L_["cr_cc"], closing_costs(B, t_["price"]))
    # CMA-4: what the buyer's own broker agreement charges beyond what the seller pays is the buyer's cost
    led.cost("bb_short", L_["cr_bb_short"],
             finance.buyer_broker_shortfall(t_["price"], BU.get("buyer_broker_agreement_pct"), t_.get("buyer_broker_pct")) or 0)
    led.credit("conc", L_["cr_conc"], min(t_.get("seller_concessions", 0), -cc))
    return led


def buyer_cash(B, t_):
    """{down, cc, bb_short, conc (negative), to_close, gap, worst, reserve, wasted_conc}: cash to close from cash_ledger,
    then the appraisal gap on top (the worst case) and what's left of the buyer's cash."""
    BU, fin = B["buyer"], B["buyer"]["financing"]
    led = cash_ledger(B, t_)
    to_close = -led.total()
    gap = fmt.half_up(t_.get("appraisal_gap", 0)) if fin != "cash" else 0
    worst = to_close + gap
    return {"down": -led.amount("down"), "cc": -led.amount("cc"), "conc": -led.amount("conc"),
            "bb_short": -led.amount("bb_short"), "to_close": to_close, "gap": gap, "worst": worst,
            "reserve": BU["cash_available"] - worst, "wasted_conc": max(0, t_.get("seller_concessions", 0) + led.amount("cc"))}


def property_tax(B, costs, price):
    """The buyer's tax at `price`: a plain `costs.tax_rate` (share of price) when given, else millage or the market's rate."""
    K = B["costs"]
    if K.get("tax_rate") is not None:
        return {"annual": price * K["tax_rate"], "basis": t("tax_basis_rate", rate=fmt.pct(K["tax_rate"], None)), "estimated": False}
    return finance.property_tax(price, costs, school_mills=K.get("school_mills"), total_mills=K.get("total_mills"),
                                homestead=K.get("homestead", True))


def monthly_payment(B, costs, price):
    BU, K, P = B["buyer"], B["costs"], B["property"]
    tax = property_tax(B, costs, price)["annual"] or 0
    p = finance.monthly_payment(price, BU["financing"], BU["down_pct"], K["rate"], tax, K["insurance_annual"],
                                P["hoa_monthly"] + (P.get("cdd_annual") or 0) / 12, flood_annual=B["flood"]["annual"],
                                va_later_use=bool(BU.get("va_later_use")), va_exempt=bool(BU.get("va_exempt")))
    return fmt.half_up(p["total"])


def bb_as_credit(B):
    """True when the buyer's broker is paid as a seller credit (Rider FF): contract_forms decides (ENG-11)."""
    return cf.buyer_broker_as_credit(B.get("contract_form"), {"buyer_broker_form": B.get("buyer_broker_form")})


def concession_cap(B, price):
    """What the loan program lets the seller pay toward the buyer's costs. A buyer's broker credit under Rider FF uses the
    same room, so it comes off the top (contract_forms.buyer_broker_as_credit)."""
    room = (finance.concession_cap(B["buyer"]["financing"], B["buyer"]["down_pct"]) or 0) * price
    if bb_as_credit(B):
        room = max(0, room - (B.get("bb_request") or (0,))[0] * price)
    return room


def bb_request(B, costs):
    """(share of price, the reason) the buyer asks the seller to pay toward the buyer's broker."""
    LS, BU = B["listing_side"], B["buyer"]
    if LS.get("buyer_broker_offered_pct") is not None:
        return LS["buyer_broker_offered_pct"], why("why_bb_offered")
    if BU.get("buyer_broker_agreement_pct") is not None:
        return BU["buyer_broker_agreement_pct"], why("why_bb_agreement")
    if costs.get("brokerage.buyer_broker_fee_pct") is not None:
        p = costs.get("brokerage.buyer_broker_fee_pct")
        return p, why("why_bb_default", pct=fmt.pct(p, None))
    return 0, why("why_bb_none")


# --- engine bridge -------------------------------------------------------------

def engine_data(B, variants):
    P, V, LS, BU = B["property"], B["value"], B["listing_side"], B["buyer"]
    listing = {k: P.get(k) for k in ("address", "state", "county", "list_price", "beds", "baths", "sqft", "year_built", "roof_year",
                                     "hoa_monthly", "flood_zone", "annual_tax", "costs")}
    listing["property_type"] = P.get("type")  # CMA-5: the engine's condo checks
    if listing.get("annual_tax") in (None, "") and B.get("seller_annual_tax"):
        listing["annual_tax"] = B["seller_annual_tax"]  # OFR-201: one tax rate for the payment and the proration
    if not V.get("assumed"):  # without a value range the engine measures appraisal risk against list price
        listing.update(cma_low=V["cma_low"], cma_high=V["cma_high"], cma_mid=V["mid"])
    seller = {"listing_fee_pct": LS["listing_fee_pct"], "offered_buyer_broker_pct": LS["buyer_broker_offered_pct"]}
    if P.get("seller_deadline"):
        seller["deadline"] = P["seller_deadline"]
    offers = []
    for vid, t_ in variants:
        o = {"id": vid, "price": t_["price"], "financing": BU["financing"], "down_pct": BU["down_pct"], "approval": BU["approval"],
             "lender_called": BU.get("lender_called", False), "insurance_quote": t_.get("insurance_quote", BU.get("insurance_quote")),
             "agent_track": BU.get("agent_track"), "buyer": "Buyer",
             "same_buyer": "buyer"}  # OFR-101: the options are one buyer's alternatives, never each other's competition
        for k in ("deposit", "seller_concessions", "buyer_broker_pct", "home_warranty", "inspection_days", "loan_approval_days",
                  "appraisal_gap", "closing_days", "sale_contingency_days", "kickout", "escalation", "contract_form"):
            if t_.get(k) is not None:
                o[k] = t_[k]
        if B.get("repair_limits"):
            o["repair_limits"] = B["repair_limits"]
        fin = BU["financing"]
        riders = [B["buyer_broker_form"]] if B.get("buyer_broker_form") and t_.get("buyer_broker_pct") else []
        kind = appraisal_kind(B, t_)
        if kind == "aga":
            o["appraisal_form"] = "aga"
            o["aga_valuation_days"] = aga_valuation(t_, fin)
        elif kind == "F":
            riders.append("F")
        elif fin != "cash":
            o["appraisal_contingency"] = t_.get("appraisal_days", 21)
        if riders:
            o["riders"] = riders
        offers.append(o)
    # OFR-123: the engine counts closing and "days until firm" from the expected Effective Date
    return {"analysis_date": str(B["effective_date"]), "listing": listing, "seller": seller, "offers": offers}


def appraisal_kind(B, t_):
    """How a FAR/BAR option protects the appraisal: 'aga' (a gap offer on the Appraisal Gap Addendum, only where AGA-1
    fits the loan: contract_forms.aga_fits), 'F' (the Appraisal Contingency Rider, conventional or USDA), or None
    (FHA/VA's own rider, cash, or another contract). ENG-10: a USDA gap is written in Additional Terms with Rider F."""
    fin = B["buyer"]["financing"]
    if B["contract_form"] not in cf.FARBAR:
        return None
    if t_.get("appraisal_gap") and cf.aga_fits(fin):
        return "aga"
    return "F" if fin in ("conventional", "usda") else None


def aga_valuation(t_, fin):
    """OFR-106: AGA-1's valuation blank, filled so its whole window ends with the Loan Approval Period (financed) or by
    closing (cash)."""
    limit = t_.get("loan_approval_days") if fin != "cash" else t_.get("closing_days")
    return cf.aga_valuation_days(limit or cf.AGA_VALUATION_DAYS + cf.AGA_DELIVERY_DAYS + cf.AGA_RENEGOTIATE_DAYS)


def run_engine(B, costs, variants):
    R = oe.analyze(engine_data(B, variants), market=costs.market)
    return R, {o["id"]: o for o in R["offers"]}


def ci(o, target_net, lp):
    """Competitiveness index = strength score + 5 points per 1% of list price the seller nets above a clean offer at list."""
    return o["score"]["total"] + 5 * (o["ns"]["net_adj"] - target_net) / (0.01 * lp)


def band_of(v, level):
    s, c, r = BANDS[level]
    k = "strong" if v >= s else "comp" if v >= c else "risk" if v >= r else "unl"
    return k, L_["band_name"][k]


# --- limits ----------------------------------------------------------------------

def limits_broken(B, costs, t_, walk=False):
    """OFR-214: the buyer's limits the terms `t_` would break, as [(key, words)]: max price, max payment, cash, reserve
    floor; with `walk`, the CMA's walk-away too (a price past it is held: the buyer CMA's ceiling for this home)."""
    BU, c = B["buyer"], buyer_cash(B, t_)
    out = []
    w = walk_away(B)
    if walk and w and t_["price"] > w:
        out.append(("walk_away", t("lim_walk", walk=money(w))))
    if t_["price"] > BU["max_price"]:
        out.append(("max_price", t("lim_max", max=money(BU["max_price"]))))
    if BU.get("max_payment"):
        pay = monthly_payment(B, costs, t_["price"])
        if pay > BU["max_payment"]:
            out.append(("max_payment", t("lim_payment", limit=money(BU["max_payment"]), pay=money(pay))))
    if c["reserve"] < 0:
        out.append(("cash", t("lim_cash", cash=money(BU["cash_available"]), short=money(-c["reserve"]))))
    elif c["reserve"] < BU["reserve_floor"]:
        out.append(("reserve_floor", t("lim_reserve", floor=money(BU["reserve_floor"]), left=money(c["reserve"]))))
    return out


def within_limits(B, costs, t_):
    BU = B["buyer"]
    c = buyer_cash(B, t_)
    return (t_["price"] <= BU["max_price"] and c["reserve"] >= BU["reserve_floor"] and not c["wasted_conc"]
            and not (BU.get("max_payment") and monthly_payment(B, costs, t_["price"]) > BU["max_payment"])
            and t_.get("seller_concessions", 0) <= concession_cap(B, t_["price"]) + 1)


def price_ceiling(B):
    """The highest price a Stronger option or the band search may go to, with what sets it: the lowest of the top of the
    value range (above it the appraisal needs gap coverage), the CMA's walk-away, the buyer's max and, with one competing
    offer or fewer, list. Returns (price, the binding cap in words)."""
    P, V, BU, lvl = B["property"], B["value"], B["buyer"], B["competition"]["level"]
    w = walk_away(B)
    caps = [(V["cma_high"], t("ceil_top", price=money(V["cma_high"]))),
            (w, t("ceil_walk", price=money(w)) if w else ""),
            (BU["max_price"], t("ceil_max", price=money(BU["max_price"]))),
            (P["list_price"] if lvl <= 1 else None, t("ceil_list", price=money(P["list_price"])))]
    p, words = min(((x, wd) for x, wd in caps if x), key=lambda c: c[0])
    return rnd(p, 1000, "down"), words


# --- offer builder -------------------------------------------------------------

def build_offer(B, costs):
    """Rule-based best offer inside the buyer's limits (references/offer-rules.md). Returns (terms, reasons): each reason
    a why() dict; `price_by` names what set the price ("payment", "max_price", or the rule)."""
    P, V, BU, C = B["property"], B["value"], B["buyer"], B["competition"]
    lp, lvl, fin = P["list_price"], C["level"], BU["financing"]
    w = {}
    anchor = min(lp, V["point"])
    # OFR-7: with little competition the offer never goes above list, even when the value range starts above it
    price = {0: min(lp, max(V["cma_low"], anchor * 0.98)), 1: anchor, 2: min(max(lp, V["mid"]), V["cma_high"]),
             3: V["cma_high"]}[lvl]
    w["price"], by = why(f"why_price_{lvl}"), "rule"
    if lvl == 0 and V["cma_low"] > lp:
        w["price"] = why("why_price_0_list")
    low_down = fin in ("fha", "va", "usda") or (fin == "conventional" and BU["down_pct"] < 0.05)
    if low_down and lvl >= 2 and price > V["mid"]:  # OFR-10: low down payment competes on terms, not price
        price = rnd(V["mid"], 1000, "down")
        w["price"] = why("why_price_low_down", down=fmt.pct(BU["down_pct"], 1))
    if price > BU["max_price"]:
        price, w["price"], by = BU["max_price"], why("why_price_max"), "max_price"
    price = lp if abs(price - lp) < 1000 and not (low_down and lvl >= 2 and lp > V["mid"]) \
        else rnd(price, 1000, "down" if price > lp else "round")
    if V.get("assumed") and price == lp:  # OFR-212: with no CMA the price stays at list, never called "at value"
        w["price"] = why("why_price_no_range")
    if BU.get("max_payment") and monthly_payment(B, costs, price) > BU["max_payment"]:
        while price > 1000 and monthly_payment(B, costs, price) > BU["max_payment"]:
            price -= 1000
        est = B.get("payment_assumed") or []  # OFR-228: a cap that rests on an assumed rate or insurance says so
        w["price"], by = why("why_price_payment", pay=money(BU["max_payment"]), at=t("at_assumed", what=joined(est)) if est else "",
                             below=L_["below_range"] if price < V["cma_low"] else ""), "payment"
    t_ = {"price": price, "price_by": by}
    cc = closing_costs(B, price)
    down = fmt.half_up(price * BU["down_pct"])
    spare = BU["cash_available"] - BU["reserve_floor"] - down - cc
    room = concession_cap(B, price)
    need = max(0, -spare)
    want = {0: cc, 1: max(need, cc * 0.5), 2: need, 3: need}[lvl]
    conc = min(rnd(min(room, want), 500, "up"), int(cc // 100 * 100), int(room // 100 * 100)) if want > 0 else 0
    conc = meaningful_ask(B, costs, t_, conc)
    t_["seller_concessions"] = conc
    w["seller_concessions"] = why("why_conc_0" if lvl == 0 else "why_conc_1" if lvl == 1 and conc > need else
                                  "why_conc_need" if conc else "why_conc_none")
    if need > room:
        w["seller_concessions"] = add_to(w["seller_concessions"], why("add_conc_cap", cap=money(room)))
    spare_after = BU["cash_available"] - BU["reserve_floor"] - (down + cc - min(conc, cc))
    line = V["cma_high"]  # appraisal risk starts at the top of the value range, as on the listing side (oe.appraisal_line)
    gap = 0
    if fin != "cash" and price > line:
        gap = min(rnd(price - line, 1000, "up"), max(0, rnd(spare_after, 500, "down")))
    t_["appraisal_gap"] = gap
    if fin == "cash":
        w["appraisal_gap"] = why("why_gap_cash")
    elif V.get("assumed") and not gap:  # OFR-212: with no value range the gap can't be sized: a question for the buyer
        w["appraisal_gap"] = why("why_gap_unknown")
    elif price < V["cma_low"]:
        w["appraisal_gap"] = why("why_gap_below")
    elif price <= line:
        w["appraisal_gap"] = why("why_gap_inside")
    elif gap >= price - line:
        w["appraisal_gap"] = why("why_gap_covers")
    elif gap:
        w["appraisal_gap"] = why("why_gap_partial")
    else:
        w["appraisal_gap"] = why("why_gap_no_room", reserve=money(BU["reserve_floor"]))
    if gap and fin in ("fha", "va"):
        w["appraisal_gap"] = add_to(w["appraisal_gap"], why("add_gap_fha", prog=oe.FIN_LABEL[fin]))
    dep_pct = {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.03}[lvl] if fin != "cash" else {0: 0.03, 1: 0.05, 2: 0.10, 3: 0.10}[lvl]
    t_["deposit"] = int(min(rnd(price * dep_pct, 500, "up"), max(1000, down + cc - conc)))
    w["deposit"] = why("why_deposit", pct=fmt.pct(dep_pct, 0), refund=B["words"]["deposit_refund"])
    yb = P.get("year_built")
    old = yb is None or (B["analysis_date"].year - yb) > 25  # unknown age: allow the full window
    t_["inspection_days"] = 7 if (lvl >= 2 and not old) else 10
    if t_["inspection_days"] == 10:
        w["inspection_days"] = why("why_insp_full", reports=L_["insp_four_point"] if costs.state == "FL" else "",
                                   age=L_["insp_older"] if yb and old else L_["insp_unknown_age"] if not yb else "")
    else:
        w["inspection_days"] = why("why_insp_short")
    if B["contract_form"] not in cf.FARBAR:  # OFR-315: no other state's periods are built in, so the length is assumed
        w["inspection_days"] = add_to(w["inspection_days"], why("add_insp_generic"))
    if fin != "cash":
        t_["loan_approval_days"] = 21 if (fin == "conventional" and lvl >= 2) else 30
        w["loan_approval_days"] = why("why_loan_30" if t_["loan_approval_days"] == 30 else "why_loan_21")
        t_["appraisal_days"] = 21
    t_["closing_days"] = BU["lender_min_close_days"] + (0 if lvl >= 1 else 10)
    while not dates.is_business_day(B["effective_date"] + timedelta(days=t_["closing_days"])):
        t_["closing_days"] += 1  # OFR-219: a business day (no weekend or federal holiday), never before the lender's minimum
    w["closing_days"] = why(("why_close_cash" if fin == "cash" else "why_close_fast") if lvl >= 1 else "why_close_easy")
    t_["home_warranty"] = 0
    w["home_warranty"] = why("why_warranty")
    t_["buyer_broker_pct"], w["buyer_broker_pct"] = B["bb_request"]
    if bb_as_credit(B):
        w["buyer_broker_pct"] = add_to(w["buyer_broker_pct"], why("add_bb_ff"))
    if BU.get("needs_sale"):  # Rider V with a kick-out (Rider X): the listing side scores it that way too
        t_["sale_contingency_days"], t_["kickout"] = BU.get("sale_contingency_days") or 21, True
        w["sale_contingency_days"] = why("why_sale")
    t_["contract_form"] = B["contract_form"]
    # OFR-18: only a quote in hand is scored. OFR-216: "planned" only when the agent said so; otherwise no quote yet
    t_["insurance_quote"] = True if quote_in_hand(BU) else "planned" if BU.get("insurance_quote") == "planned" else None
    w["insurance_quote"] = why("why_ins_quote" if quote_in_hand(BU) else "why_ins_get")
    if lvl >= 2 and fin in ("cash", "conventional") and BU["down_pct"] >= 0.10:
        # Cap = the lowest of the buyer's max, the CMA's walk-away, and the price whose appraisal gap (above the same
        # risk line the listing side uses) the buyer can still fund with the reserve intact (OFR-5).
        walk = walk_away(B)
        capv = rnd(min(BU["max_price"], walk or BU["max_price"]), 1000, "down")
        by_walk = bool(walk) and walk < BU["max_price"]

        def gap_at(p):
            return max(gap, rnd(p - line, 1000, "up")) if fin != "cash" and p > line else gap

        if BU.get("max_payment"):
            while capv > price and monthly_payment(B, costs, capv) > BU["max_payment"]:
                capv, by_walk = capv - 1000, False
        while capv > price and buyer_cash(B, {"price": capv, "seller_concessions": conc,
                                              "appraisal_gap": gap_at(capv)})["reserve"] < BU["reserve_floor"]:
            capv, by_walk = capv - 1000, False
        if capv > price:
            t_["escalation"] = {"increment": 1000, "cap": capv, "gap_at_cap": gap_at(capv)}
            if gap_at(capv) > gap:  # OFR-105: the package's gap coverage is written at the cap's gap, and scored that way
                t_["appraisal_gap"] = gap = gap_at(capv)
                w["appraisal_gap"] = why("why_gap_at_cap", cap=money(capv))
            support = (L_["esc_inside"] if capv <= line or fin == "cash" else t("esc_above", above=money(capv - line)))
            w["escalation"] = why("why_esc", inc=money(1000), cap=money(capv), support=support,
                                  walk=L_["esc_held_walk"] if by_walk else "")
        elif price >= BU["max_price"]:
            w["escalation"] = why("why_esc_at_max", max=money(BU["max_price"]))
        elif by_walk:  # OFR-205: what going on to the buyer's max would cost, not only where the walk-away stopped it
            above = BU["max_price"] - line
            w["escalation"] = why("why_esc_walk", walk=money(walk), max=money(BU["max_price"]),
                                  rest=t("esc_walk_above", above=money(above), top=money(line))
                                  if above > 0 and fin != "cash" else L_["esc_walk_ceiling"])
        else:
            w["escalation"] = why("why_esc_no_room")
    elif lvl >= 2:
        w["escalation"] = why("why_esc_low_down")
    return t_, w


def stronger(B, t_):
    """Next step up: a 3% deposit, plus gap coverage where the listing side credits it (never beyond the buyer's actual
    cash; may dip below the reserve)."""
    s = dict(t_)
    if buyer_cash(B, t_)["reserve"] < 0:
        return None  # can't afford the base offer: a stronger one is meaningless
    uncovered = t_["price"] - B["value"]["cma_high"] - t_.get("appraisal_gap", 0)  # above the listing side's risk line
    if B["buyer"]["financing"] not in ("cash", "fha", "va") and uncovered > 0:  # an FHA/VA gap clause earns no credit
        c = buyer_cash(B, t_)
        room = max(0, rnd(B["buyer"]["cash_available"] - c["worst"], 500, "down"))
        s["appraisal_gap"] = t_.get("appraisal_gap", 0) + min(rnd(uncovered, 1000, "up"), room)
    s["deposit"] = max(t_.get("deposit", 0), rnd(0.03 * t_["price"], 500, "up"))
    return None if s == t_ else s


def smallest_ask(B, costs, t_, p):
    """The smallest seller-concession ask at price `p` that keeps every limit of the offer `t_`, or None."""
    cc = closing_costs(B, p)
    most = int(min(cc, concession_cap(B, p)) // 100 * 100)
    for c in [0] + list(range(MIN_CONCESSION_ASK, most + 1, 500)) + [most]:
        if within_limits(B, costs, dict(t_, price=p, seller_concessions=c)):
            return c
    return None


def stronger_net(B, costs, t_):
    """When stronger() has nothing to add (the deposit is at 3% and no appraisal gap needs covering), the terms inside
    every limit the listing agent would rank highest: a higher price up to price_ceiling() with the smallest concession
    ask the buyer's cash allows at it, scored by the engine (a higher price can lower the appraisal score, so more net
    isn't always stronger). None when nothing ranks higher. An escalating offer, one with no value range or one already
    past the reserve floor is left as is."""
    V, BU = B["value"], B["buyer"]
    if t_.get("escalation") or V.get("assumed") or buyer_cash(B, t_)["reserve"] < BU["reserve_floor"]:
        return None
    top = max(price_ceiling(B)[0], t_["price"])
    tries = []
    for p in range(int(t_["price"]), int(top) + 1, 1000):
        c = smallest_ask(B, costs, t_, p)
        if c is not None and p - c > t_["price"] - t_.get("seller_concessions", 0):
            tries.append((f"try{len(tries)}", dict(t_, price=p, seller_concessions=c)))
    if not tries:
        return None
    _, O = run_engine(B, costs, [("recommended", t_)] + tries)
    lp, tgt = B["property"]["list_price"], O["recommended"]["target"]["net_adj"]
    k, s = max(tries, key=lambda kt: (ci(O[kt[0]], tgt, lp), -kt[1]["price"]))
    return s if ci(O[k], tgt, lp) > ci(O["recommended"], tgt, lp) else None


def lower_cost(B, costs, rec):
    """The recommended offer (with the agent's overrides) softened toward one competition level lower: never a higher
    price, deposit or gap, no escalation (OFR-8). None if nothing changes."""
    lvl = B["competition"]["level"]
    if lvl == 0:
        return None, {}
    B2 = copy.deepcopy(B)
    B2["competition"]["level"] = lvl - 1
    soft, w = build_offer(B2, costs)
    t_ = dict(rec)
    t_.pop("escalation", None)
    for k in ("price", "deposit", "appraisal_gap"):
        t_[k] = min(rec.get(k, 0), soft.get(k, 0))
    for k in ("inspection_days", "loan_approval_days", "closing_days"):
        if k in rec and k in soft:
            t_[k] = max(rec[k], soft[k])
    cc = closing_costs(B, t_["price"])
    t_["seller_concessions"] = min(max(rec.get("seller_concessions", 0), soft.get("seller_concessions", 0)),
                                   int(cc // 100 * 100), int(concession_cap(B, t_["price"]) // 100 * 100))
    t_["price_by"] = soft.get("price_by", "rule") if t_["price"] != rec["price"] else rec.get("price_by", "rule")
    w = {k: v for k, v in w.items() if t_.get(k) != rec.get(k)}
    # OFR-326: build_offer worded the price and concessions for one competition level lower; the deal has the expected
    # level, so these reasons say what the softer terms are written for instead of calling the competition "little"
    written = {"lower": comp_words(lvl - 1), "expected": comp_words(lvl)}
    if t_["price"] < rec["price"]:
        w["price"] = why("why_lc_price", amount=money(rec["price"] - t_["price"]), **written)
    if t_["seller_concessions"] > rec.get("seller_concessions", 0):
        w["seller_concessions"] = why("why_lc_conc", ask=L_["ask_all" if t_["seller_concessions"] >= int(cc // 100 * 100)
                                                             else "ask_more"], **written)
    return (None, {}) if strip(t_) == strip(rec) else (t_, w)


def strip(t_):
    """The terms without bookkeeping keys, for comparing two offers."""
    return {k: v for k, v in t_.items() if k != "price_by"}


def meaningful_ask(B, costs, t_, conc):
    """A seller-concession ask of at least MIN_CONCESSION_ASK: a smaller one drops to $0 when every buyer limit still
    holds without it (the offer is cleaner), otherwise it rounds up to the minimum (never past the closing costs or the
    loan program's cap)."""
    if not 0 < conc < MIN_CONCESSION_ASK:
        return conc
    if within_limits(B, costs, dict(t_, seller_concessions=0)):
        return 0
    most = min(closing_costs(B, t_["price"]), concession_cap(B, t_["price"]))
    return MIN_CONCESSION_ASK if most >= MIN_CONCESSION_ASK else conc


def conc_need(B, price):
    """The seller concessions the buyer's cash can't do without at `price`: what closing takes beyond cash after the
    reserve."""
    BU = B["buyer"]
    return max(0, fmt.half_up(price * BU["down_pct"]) + closing_costs(B, price) - (BU["cash_available"] - BU["reserve_floor"]))


def reach_band(B, costs, rec):
    """OFR-325: when the rule-built offer reads At Risk or Unlikely, the lowest-cost offer inside every limit that reaches
    a better band, with that band and the same-band offer that keeps the most cash (OFR-332); else (None, None, None). It
    tries a price anywhere in the value range up to price_ceiling() (never past the CMA's walk-away, the buyer's max or,
    with little competition, list), smaller concessions down to what the buyer's cash can't cover with the reserve kept,
    a 3% deposit and the lender's fastest close. Lowest cost: the price net of concessions, then the smaller deposit,
    then the longer close. An escalating offer is left as built."""
    P, V, BU, lvl = B["property"], B["value"], B["buyer"], B["competition"]["level"]
    if rec.get("escalation") or V.get("assumed"):
        return None, None, None
    top = price_ceiling(B)[0]
    low = min(rnd(V["cma_low"], 1000, "up"), top)
    fast = BU["lender_min_close_days"]
    while not dates.is_business_day(B["effective_date"] + timedelta(days=fast)):
        fast += 1  # OFR-219: a business day, as build_offer counts it
    closes = sorted({rec["closing_days"], min(fast, rec["closing_days"])})
    tries = []
    step = max(1000, int(rnd((top - low) / 30, 1000, "up")))  # at most about 30 prices and 20 concession amounts
    for p in sorted(set(range(int(low), int(top) + 1, step)) | {int(top)} | ({rec["price"]} if rec["price"] <= top else set())):
        cc, need = closing_costs(B, p), conc_need(B, p)
        most = min(rec.get("seller_concessions", 0), int(cc // 100 * 100), int(concession_cap(B, p) // 100 * 100))
        room = fmt.half_up(p * BU["down_pct"]) + cc  # build_offer's rule: the deposit never exceeds the cash to close
        first = int(rnd(need, 500, "up")) if need else 0
        cstep = max(500, int(rnd((most - first) / 20, 500, "up"))) if most > first else 500
        asks = {meaningful_ask(B, costs, {"price": p}, c) for c in set(range(first, most + 1, cstep)) | {most}}
        for conc in sorted(a for a in asks if a <= max(most, MIN_CONCESSION_ASK if most else 0)):
            deps = {rec["deposit"], int(min(max(rec["deposit"], rnd(0.03 * p, 500, "up")), max(1000, room - conc)))}
            for dep in sorted(deps):
                for days in closes:
                    # every price tried is inside the value range, so no appraisal gap is needed
                    t_ = dict(rec, price=p, seller_concessions=conc, deposit=dep, closing_days=days, appraisal_gap=0,
                              price_by="reach")
                    if conc >= need and strip(t_) != strip(rec) and within_limits(B, costs, t_):
                        tries.append((f"try{len(tries)}", t_))
    if not tries:
        return None, None, None
    _, O = run_engine(B, costs, [("recommended", rec)] + tries)
    # each offer against its own clean offer at list (the same closing date), as it's scored once recommended
    bands = {k: band_of(ci(O[k], O[k]["target"]["net_adj"], P["list_price"]), lvl) for k in O}
    best = max(BAND_RANK[b[0]] for b in bands.values())
    if bands["recommended"][0] not in ("risk", "unl") or best <= BAND_RANK[bands["recommended"][0]]:
        return None, None, None
    same = [(k, t2) for k, t2 in tries if BAND_RANK[bands[k][0]] == best]
    k, t_ = min(same, key=lambda kt: (kt[1]["price"] - kt[1]["seller_concessions"], kt[1]["deposit"], -kt[1]["closing_days"]))
    # OFR-332: the same-band offer that keeps the most cash, for when the cheapest one leaves a thin cushion
    roomy = max((t2 for _, t2 in same), key=lambda t2: buyer_cash(B, t2)["reserve"])
    return t_, bands[k], roomy


def against(B, band):
    """'At Risk against one competing offer', or 'Strong as the only offer'."""
    lvl = B["competition"]["level"]
    return t("vs_level", band=band, comp=comp_words(lvl)) if lvl else t("vs_only", band=band)


def smaller_than(B, t_, was):
    """What a smaller concession ask is smaller than: the area's typical seller-paid amount when the ask is under it,
    else the first draft's ask."""
    typ = B["market"].get("typical_seller_paid")
    if num(typ) and t_["seller_concessions"] < typ:
        return t("than_typical", amount=money(typ))
    return money(was.get("seller_concessions", 0))


def reach_why(B, w, t_, was, band):
    """OFR-325: the reasons for the terms reach_band changed, against the competition the deal expects."""
    w = dict(w)
    BU, V = B["buyer"], B["value"]
    walk = walk_away(B)
    if t_["price"] != was["price"]:
        where = (L_["where_top"] if t_["price"] >= V["cma_high"] else L_["where_walk"] if walk and t_["price"] >= walk else
                 L_["where_inside"])
        w["price"] = why("why_reach_price", against=against(B, band[1]), where=where)
    if t_["seller_concessions"] < was.get("seller_concessions", 0):
        keep = money(BU["reserve_floor"])
        w["seller_concessions"] = (why("why_reach_conc_none", reserve=keep) if not t_["seller_concessions"] else
                                   why("why_reach_conc_need", reserve=keep)
                                   if t_["seller_concessions"] < conc_need(B, t_["price"]) + 500 else
                                   why("why_reach_conc_smaller", than=smaller_than(B, t_, was)))
    if t_["deposit"] > was.get("deposit", 0):
        w["deposit"] = why("why_deposit", pct=fmt.pct(t_["deposit"] / t_["price"], 0), refund=B["words"]["deposit_refund"])
    if t_["closing_days"] < was.get("closing_days", 0):
        w["closing_days"] = why("why_reach_close")
    if was.get("appraisal_gap") and not t_.get("appraisal_gap"):
        w["appraisal_gap"] = why("why_gap_inside")
    return w


def option_set(B, costs, rec):
    """The options to score: (variants, the lower-cost reasons, whether the Stronger option is stronger_net()'s)."""
    variants = [("recommended", rec)]
    st, by_net = stronger(B, rec), False
    if not st:  # a higher price or a smaller concession ask, inside every limit
        st = stronger_net(B, costs, rec)
        by_net = bool(st)
    if st:
        variants.append(("stronger", st))
    lc, lc_why = lower_cost(B, costs, rec)
    if lc:
        variants.append(("lower_cost", lc))
    return variants, lc_why, by_net


def better_option(B, costs, terms, O, lvl, promote_stronger=True):
    """The option to recommend instead, if the rule-built offer isn't the best by the skill's own rule, else None. A
    Stronger option that only pays more (stronger_net) stays the buyer's choice, never promoted: the search for the
    lowest-cost offer that reaches a better band is reach_band's."""
    if B.get("overrides"):
        return None  # the agent decided the terms
    lp = B["property"]["list_price"]
    tgt = O["recommended"]["target"]["net_adj"]
    rank = {k: BAND_RANK[band_of(ci(O[k], tgt, lp), lvl)[0]] for k in terms}
    if promote_stronger and "stronger" in terms and rank["stronger"] > rank["recommended"] \
            and within_limits(B, costs, terms["stronger"]):
        return "stronger"
    # OFR-9: "best" is the strongest outlook at the lowest cost that reaches it, so a cheaper option in the same band wins;
    # never an option the lower-cost rule drops (Unlikely against the expected competition at level 2+)
    if "lower_cost" in terms and rank["lower_cost"] >= rank["recommended"] \
            and not (lvl >= 2 and rank["lower_cost"] == BAND_RANK["unl"]) and within_limits(B, costs, terms["lower_cost"]) \
            and buyer_cash(B, terms["lower_cost"])["worst"] < buyer_cash(B, terms["recommended"])["worst"]:
        return "lower_cost"
    return None


def promote_why(w, lc_why, pick, t_, was=None, words=None):
    """The reasons for a promoted option. CMA-103: the Stronger option names only what it actually raised."""
    w = dict(w)
    was = was or {}
    if pick == "lower_cost":
        w.update(lc_why)
        w.pop("escalation", None)
        # OFR-326: worded for the competition the deal expects, never the softer level the option was built for
        if was.get("price", 0) > t_["price"]:
            w["price"] = why("why_promo_price", amount=money(was["price"] - t_["price"]))
        if lc_why.get("seller_concessions"):
            w["seller_concessions"] = why("why_promo_conc", ask=lc_why["seller_concessions"]["ask"])
    if pick == "stronger":
        if t_.get("appraisal_gap", 0) > was.get("appraisal_gap", 0):
            w["appraisal_gap"] = why("why_promo_gap")
        if t_.get("deposit", 0) > was.get("deposit", 0):
            w["deposit"] = why("why_deposit", pct=fmt.pct(t_["deposit"] / t_["price"], 0),
                               refund=(words or cf.term_words(None))["deposit_refund"])
    return w


def raised(t_, was):
    """What the Stronger option raised over the offer it replaced, as label keys ('raised_gap', 'raised_deposit')."""
    return [f"raised_{name}" for key, name in (("appraisal_gap", "gap"), ("deposit", "deposit"))
            if t_.get(key, 0) > (was or {}).get(key, 0)]


def raised_words(keys):
    return joined([L_[k] for k in keys])


# --- top level -----------------------------------------------------------------

def analyze(B_in, market=None, cma=None):
    """The engine: the buyer file (with the CMA handoff) prepared, the offer built, its options scored. Returns the
    internal result every view reads; the input is never changed."""
    oe.check_fractions(B_in)
    probs = text_problems(B_in)
    if probs:
        raise oe.OfferError("\n".join(probs))
    B0 = apply_cma(B_in, cma) if cma else copy.deepcopy(B_in)
    A = oe.Assume()
    if B0.get("_cma_side_note"):
        A.add("value", "cma_side", "other side", B0["_cma_side_note"], "high")
    if B0.get("_cma_address_note"):  # CMA-102
        A.add("value", "cma_address", "another property", B0["_cma_address_note"], "high")
    if B0.get("_dom_aged"):  # OFR-242
        was, as_of, since = B0["_dom_aged"]
        A.add("property", "dom", B0["property"]["dom"], t("as_dom_aged", dom=fmt.num(B0["property"]["dom"]), was=fmt.num(was),
                                                         date=day(as_of), since=since,
                                                         days=L_["day_one" if since == 1 else "day_many"]), "low")
    B, costs = prepare(B0, A, market)
    lvl = B["competition"]["level"]
    rec, w = build_offer(B, costs)
    ov = B.get("overrides") or {}
    for k, v in ov.items():  # the agent's judgment wins; the report marks it
        rec[k] = v
        w[k] = why("why_agent")
    if "price" in ov:
        rec["price_by"] = "agent"
    if B["contract_form"] not in cf.FARBAR:  # OFR-222: a best-effort contract's own questions, asked before cost details
        if not (B.get("worksheet") or {}).get("contract_name"):
            A.add("worksheet", "contract_name", None, L_["as_contract_name"], "med")
        if "inspection_days" not in ov:  # OFR-315: the chat carries it as a reply line; the report lists it here
            A.add("worksheet", "inspection_days", rec["inspection_days"], t("as_inspection_generic", days=rec["inspection_days"]),
                  "low")
        # OFR-316: the deposit's risk date is counted from this offer's own periods, never from another form's rules
        A.add("worksheet", "deposit_risk", None, L_["as_deposit_risk"], "low")
    if rec.get("price_by") == "payment":  # the payment limit sets the price, so its inputs matter most
        for a in A.items:
            if a["field"] == "property_tax" and a["impact"] == "low":
                a["impact"] = "med"
            if a["field"] in ("rate", "rate_source", "insurance_annual"):  # asked right after the deadline
                a["caps_price"] = True
                # an estimated rate or premium moves the price itself, so it's high impact (the report reads Preliminary
                # and its line names them first), whether assumed or looked up
                a["impact"] = "high"
    reached = None
    if not ov:  # OFR-325: the rule-built offer is a first draft; the strongest outlook inside the limits wins
        t_, band, roomy = reach_band(B, costs, rec)
        if t_:
            w, reached = reach_why(B, w, t_, rec, band), {"from": rec, "band": band[1], "band_key": band[0], "roomy": roomy}
            rec = t_
    promoted = fuller = None
    for _ in range(2):  # "best" = strongest outlook inside the limits at the lowest cost that reaches it
        variants, lc_why, by_net = option_set(B, costs, rec)
        R, O = run_engine(B, costs, variants)
        pick = better_option(B, costs, dict(variants), O, lvl, promote_stronger=not by_net)
        if not pick or promoted:
            break
        promoted, fuller = pick, rec
        rec = dict(variants)[pick]
        w = promote_why(w, lc_why, pick, rec, fuller, B["words"])
        if pick == "lower_cost":  # OFR-9: the fuller offer stays on the table as the stronger alternative
            variants, lc_why, by_net = [("recommended", rec), ("stronger", fuller)], {}, False
            R, O = run_engine(B, costs, variants)
            break
    # OFR-240: the escalation question only when the offer escalates; with one flat number it would contradict the advice
    if B["contract_form"] not in cf.FARBAR and rec.get("escalation"):
        A.add("competition", "escalation_accepted", None, L_["as_escalation_accepted"], "med")
    lp = B["property"]["list_price"]
    tgt = O["recommended"]["target"]["net_adj"]
    limits = profiles.loan_limits()  # OFR-11: jumbo and FHA limits
    BU0, P0 = B["buyer"], B["property"]
    loan_notes = {k: finance.loan_limit_note(finance.loan_amount(t2["price"], BU0["financing"], BU0["down_pct"]),
                                             BU0["financing"], limits, P0.get("state"), P0.get("county")) for k, t2 in variants}
    if loan_notes.get("recommended"):
        A.add("buyer", "loan_limit", "check", loan_notes["recommended"], "high")
    engine_assumed = [tax_bill(B, costs, O, a) for a in R["assumptions"] if not a["scope"].startswith("offer")
                      and a["scope"] != "seller" and a["field"] not in ("cma_low / cma_high", "state")]
    res = {"B": B, "R": R, "O": O, "why": w, "lc_why": lc_why, "terms": dict(variants), "target": tgt, "overrides": list(ov),
           "promoted": promoted, "promoted_from": fuller if promoted else None, "reached": reached, "by_net": by_net,
           "assumptions": A.items + engine_assumed, "costs": costs, "sample": bool(B_in.get("sample"))}
    res["cash"] = {k: buyer_cash(B, t2) for k, t2 in variants}
    res["payment"] = {k: monthly_payment(B, costs, t2["price"]) for k, t2 in variants}
    esc_ = rec.get("escalation")
    res["cash_at_cap"] = buyer_cash(B, dict(rec, price=esc_["cap"], appraisal_gap=esc_.get("gap_at_cap", rec.get("appraisal_gap", 0)))) \
        if esc_ else None
    res["ci"] = {k: ci(O[k], tgt, lp) for k, _ in variants}
    res["bands"] = {k: {lv: band_of(res["ci"][k], lv) for lv in range(4)} for k, _ in variants}
    saves_nothing = "lower_cost" in res["terms"] and res["cash"]["lower_cost"]["worst"] >= res["cash"]["recommended"]["worst"]
    unlikely = "lower_cost" in res["terms"] and lvl >= 2 and res["bands"]["lower_cost"][lvl][0] == "unl"
    already_unlikely = res["bands"]["recommended"][lvl][0] == "unl"  # nothing lower to drop to
    if saves_nothing or unlikely:  # OFR-30
        for d in (res["terms"], res["cash"], res["payment"], res["ci"], res["bands"], O):
            d.pop("lower_cost", None)
        res["lower_cost_dropped"] = True
    # OFR-218: a Stronger option that gains nothing (same outlook, no higher score) isn't worth offering. What it would
    # have changed is kept, measured by the engine (the seller-net change), so the reason states the real difference.
    no_gain = "stronger" in res["terms"] and res["bands"]["stronger"][lvl] == res["bands"]["recommended"][lvl] \
        and O["stronger"]["score"]["total"] <= O["recommended"]["score"]["total"]
    dropped = None
    if no_gain:
        dropped = {"terms": res["terms"]["stronger"], "by_net": by_net, "raised": raised(res["terms"]["stronger"], rec),
                   "net_change": O["stronger"]["ns"]["net_adj"] - O["recommended"]["ns"]["net_adj"]}
        for d in (res["terms"], res["cash"], res["payment"], res["ci"], res["bands"], O):
            d.pop("stronger", None)
        res["stronger_dropped"] = True
    res["dropped_stronger"] = dropped
    for k in O:  # OFR-216: the scorecard says what's known about the quote, never that one is planned when it isn't
        if res["terms"][k].get("insurance_quote") is None:
            sw = O[k]["score"]["why"]
            sw["property"] = (L_["sc_no_issues"] if sw["property"] == "No known condition or insurance issues"
                              else sw["property"]) + L_["sc_no_quote"]
    res["absent"] = absent_reasons(res, B, costs, rec, saves_nothing, unlikely, already_unlikely)
    res["limits"] = {k: limit_issues(B, costs, t2, res["cash"][k], fha_over_limit(B, t2["price"], limits))
                     for k, t2 in res["terms"].items()}
    res["constraints"] = constraints(B, costs, rec, res["cash"]["recommended"])
    res["reserve_tight"], res["reserve_alt"] = tight_reserve(B, costs, res, res["cash"]["recommended"])
    res["missing"] = sorted(res["assumptions"], key=lambda a: oe.IMPACT_ORDER[a["impact"]])
    res["chosen"] = B.get("chosen_option") if B.get("chosen_option") in res["terms"] else "recommended"
    res["reply_lines"] = reply_lines(B, rec) + ([{"key": "tight_reserve", "text": res["reserve_tight"]}]
                                                 if res["reserve_tight"] else [])
    res["framing"] = framing(res)
    return res


def absent_reasons(res, B, costs, rec, saves_nothing, unlikely, already_unlikely):
    """OFR-205, OFR-208: every option that isn't on the page says why, from the model's own fields."""
    lvl, promoted, dropped = B["competition"]["level"], res["promoted"], res.get("dropped_stronger")
    out = {}
    if "stronger" not in res["terms"]:
        if promoted == "stronger":
            out["stronger"] = L_["absent_promoted_stronger"]
        elif dropped and dropped["by_net"]:
            out["stronger"] = net_no_gain(B, rec, dropped)
        elif dropped:
            out["stronger"] = (t("absent_more", what=raised_words(dropped["raised"])) if dropped["raised"] else
                               L_["absent_fuller"])
        else:
            out["stronger"] = no_stronger_reason(B, rec, costs)
    if "lower_cost" not in res["terms"]:
        out["lower_cost"] = L_["absent_lc_promoted" if promoted == "lower_cost" else "absent_lc_level0" if lvl == 0 else
                               "absent_lc_saves_nothing" if saves_nothing else
                               "absent_lc_still_unlikely" if unlikely and already_unlikely else
                               "absent_lc_unlikely" if unlikely else "absent_lc_same"]
    return out


def net_no_gain(B, rec, dropped):
    """Why the terms the listing agent would rank highest inside the buyer's limits aren't offered: the terms they take,
    what the seller would net (the engine's change, not a price difference), and what bounds them (price_ceiling())."""
    st = dropped["terms"]
    parts = []
    if st["price"] > rec["price"]:
        parts.append(t("nn_price", price=money(st["price"])))
    c0, c1 = rec.get("seller_concessions", 0), st.get("seller_concessions", 0)
    if c1 != c0:
        parts.append(t("nn_conc", ask=money(c1), was=money(c0)) if c1 else t("nn_conc_none", was=money(c0)))
    delta = dropped["net_change"]
    key = "absent_net_more" if delta > 0 else "absent_net_same"
    return t(key, terms=cap(joined(parts)), ceiling=price_ceiling(B)[1], delta=money(delta))


def no_stronger_reason(B, t_, costs=None):
    """OFR-205, OFR-208: why stronger() has nothing to add to the offer `t_`: two plain sentences, the second naming the
    limit (or cap) that stops a higher price or a smaller concession ask."""
    if buyer_cash(B, t_)["reserve"] < 0:
        return L_["absent_none_affordable"]
    fin = B["buyer"]["financing"]
    uncovered = t_["price"] - B["value"]["cma_high"] - t_.get("appraisal_gap", 0)
    gap = (L_["gap_cash"] if fin == "cash" else
           t("gap_fha", prog=oe.FIN_LABEL[fin]) if fin in ("fha", "va") else
           (L_["gap_inside"] if t_["price"] >= B["value"]["cma_low"] else L_["gap_below"])
           if t_["price"] <= B["value"]["cma_high"] else
           L_["gap_covered"] if uncovered <= 0 else L_["gap_no_cash"])
    # OFR-231: the deposit as the report prints it ("$11,000 (3.1%)"), never a rounder percent beside it
    first = t("absent_deposit", deposit=term_val("deposit", t_, B), gap=gap)
    if costs is None or B["value"].get("assumed") or t_.get("escalation"):
        return first
    return first + t("absent_limits", limits=joined(no_stronger_limits(B, costs, t_)))


def no_stronger_limits(B, costs, t_):
    """Why no higher price or smaller concession ask fits, by the limit (or cap) it would cross, named."""
    top, top_words = price_ceiling(B)
    out = []
    if t_["price"] >= top:
        out.append(t("lim_at_ceiling", ceiling=top_words))
    else:
        broken = limits_broken(B, costs, dict(t_, price=t_["price"] + 1000), walk=True)
        out.append(t("lim_price_breaks", limits=joined([wd for _, wd in broken])) if broken else L_["lim_price_no_rank"])
    conc = t_.get("seller_concessions", 0)
    if conc:
        less = conc - 500 if conc - 500 >= MIN_CONCESSION_ASK else 0
        broken = limits_broken(B, costs, dict(t_, seller_concessions=less))
        out.append(t("lim_ask_breaks", limits=joined([wd for _, wd in broken])) if broken else L_["lim_ask_no_rank"])
    return out


def fha_over_limit(B, price, limits):
    """True when an FHA loan at `price` is over the program's limit here, so the offer can't be FHA (a hard program
    limit). A jumbo conventional loan, or an FHA loan over the floor in a county with no built-in limit, is a question
    for the lender: the loan_limit assumption, never a broken limit."""
    BU, P = B["buyer"], B["property"]
    if BU["financing"] != "fha" or not limits:
        return False
    loan = finance.loan_amount(price, "fha", BU["down_pct"])
    own = ((limits.get("counties") or {}).get(P.get("state") or "") or {}).get(str(P.get("county") or "").removesuffix(" County"), {})
    return bool(own.get("fha") and loan > own["fha"] or loan > limits["fha"]["ceiling"])


def limit_issues(B, costs, t_, c, over_fha):
    """The limits an option breaks, by key, with its words: [(key, words)] (empty when it's inside every limit)."""
    BU = B["buyer"]
    out = []
    if t_["price"] > BU["max_price"]:
        out.append(("max_price", L_["iss_max"]))
    if c["reserve"] < 0:
        out.append(("cash", L_["iss_cash"]))
    elif c["reserve"] < BU["reserve_floor"]:
        out.append(("reserve_floor", t("iss_reserve", left=money(c["reserve"]), floor=money(BU["reserve_floor"]))))
    if BU.get("max_payment") and monthly_payment(B, costs, t_["price"]) > BU["max_payment"]:
        out.append(("max_payment", L_["iss_payment"]))
    room = concession_cap(B, t_["price"])
    if t_.get("seller_concessions", 0) > room + 1:
        out.append(("program_cap", t("iss_program_cap", cap=money(room))))
    if c["wasted_conc"]:
        out.append(("wasted_conc", t("iss_wasted", amount=money(c["wasted_conc"]))))
    if over_fha:
        out.append(("loan_limit", L_["iss_loan_over"]))
    return out


def constraints(B, costs, rec, rc):
    """Page 1's Limit lines: the cash shortfall, a reserve below the floor, and a price capped below the value range by
    the payment limit or the max price, each with what would change it."""
    BU, V = B["buyer"], B["value"]
    out = []
    if rc["reserve"] < 0:
        out.append(t("lim_short", need=money(rc["worst"]), have=money(BU["cash_available"]), short=money(-rc["reserve"])))
    elif rc["reserve"] < BU["reserve_floor"]:
        out.append(t("lim_tight", left=money(rc["reserve"]), floor=money(BU["reserve_floor"])))
    if rec["price"] < V["cma_low"] and rec.get("price_by") == "payment":
        out.append(t("lim_payment_below", pay=money(BU["max_payment"]), price=money(rec["price"]),
                     range=fmt.range(V["cma_low"], V["cma_high"]), need=money(monthly_payment(B, costs, V["cma_low"]))))
    elif rec["price"] < V["cma_low"] and rec.get("price_by") == "max_price":
        out.append(t("lim_max_below", max=money(BU["max_price"]), low=money(V["cma_low"])))
    return out


def framing(res):
    """One name for what the recommended offer is, from the model's own facts, so the hero, the options table and the
    price reason can't disagree: 'breaks' (past a limit), 'override' (the agent's terms), 'reached' (the lowest-cost
    offer that reaches its band, reach_band), 'same_for_less' (the lower-cost terms promoted), 'stronger_better' (a
    Stronger option inside the limits reaches a better band), 'least_cash' (a Stronger option inside the limits scores
    higher in the same band), else 'best'."""
    B, O, lvl = res["B"], res["O"], res["B"]["competition"]["level"]
    if res["limits"]["recommended"]:
        return "override_breaks" if res["overrides"] else "breaks"
    if res["overrides"]:
        return "override"
    if res["reached"]:
        return "reached"
    if res["promoted"] == "lower_cost":
        return "same_for_less"
    if "stronger" in O and not res["limits"].get("stronger") \
            and res["cash"]["stronger"]["reserve"] >= B["buyer"]["reserve_floor"]:
        if BAND_RANK[res["bands"]["stronger"][lvl][0]] > BAND_RANK[res["bands"]["recommended"][lvl][0]]:
            return "stronger_better"
        if O["stronger"]["score"]["total"] > O["recommended"]["score"]["total"]:
            return "least_cash"
    return "best"


def stronger_fits(r):
    """The Stronger option is inside every limit (reserve floor kept) and the listing agent would score it higher."""
    return r["framing"] in ("least_cash", "stronger_better")


def tax_bill(B, costs, O, a):
    """The engine asks whether the seller has paid this year's tax bill when the closing falls after the bills go out
    (Florida: Nov 1). Before the bills are out nobody can have paid one, so the question can't be answered yet: it's a
    low-impact assumption (not asked), in this skill's words, saying what the proration assumes and what changes it."""
    if a["field"] != "current_tax_bill_paid":
        return a
    today = _d(B.get("analysis_date")) or date.today()
    closes = [O[k]["close"] for k in O if O[k].get("close")]
    month = costs.get("property_tax.bill_month") or oe.TAX_BILL_MONTH
    if not closes or today >= date(min(closes).year, month, 1):
        return a  # the bills are out: the seller may have paid, so ask
    close = min(closes)
    return {**a, "impact": "low", "why": t("as_tax_bill_unpaid", close=day(close), bill=fmt.date_long(date(close.year, month, 1)))}


def highest_and_best(C):
    """OFR-239: the listing agent called for highest and best (`competition.highest_and_best`, or said so in the note)."""
    hb = C.get("highest_and_best")
    return bool(hb) if hb is not None else bool(HIGHEST_AND_BEST.search(str(C.get("note") or "")))


def reserve_status(B, reserve):
    """The status mark on a Left in Reserve figure, agreeing with the page's warnings: "risk" below the reserve floor,
    "caution" for a thin cushion above it (tight_reserve's test), else "" (no status color)."""
    floor = B["buyer"]["reserve_floor"]
    if reserve < floor:
        return "risk"
    return "caution" if reserve - floor < max(TIGHT_RESERVE[0], TIGHT_RESERVE[1] * floor) else ""


def tight_reserve(B, costs, res, rc):
    """OFR-332: (one line when the recommended offer keeps the reserve floor with a thin cushion, naming the same-outlook
    offer that keeps more cash when the search found one; the alternative's figures) or (None, None). OFR-334: the line
    is neutral and carries the trade-off, so the chat quotes it and never computes or picks between them."""
    floor = B["buyer"]["reserve_floor"]
    over = rc["reserve"] - floor
    if not 0 <= over < max(TIGHT_RESERVE[0], TIGHT_RESERVE[1] * floor):
        return None, None
    line = t("tr_line", left=money(rc["reserve"]), over=money(over), floor=money(floor))
    roomy = (res.get("reached") or {}).get("roomy")
    alt = None
    if roomy:
        keep = buyer_cash(B, roomy)["reserve"]
        if keep - rc["reserve"] >= TIGHT_RESERVE[0]:
            rec = res["terms"]["recommended"]
            dpay = monthly_payment(B, costs, roomy["price"]) - monthly_payment(B, costs, rec["price"])
            alt = {"price": roomy["price"], "seller_concessions": roomy["seller_concessions"], "payment_more": dpay,
                   "cash_kept": keep - rc["reserve"]}
            pay = t("tr_pay_more" if dpay > 0 else "tr_pay_less", amount=money(abs(dpay))) if dpay else L_["tr_pay_same"]
            line += t("tr_alt", price=money(roomy["price"]),
                      conc=money(roomy["seller_concessions"]) if roomy["seller_concessions"] else L_["tr_no"],
                      pay=pay, kept=money(keep - rc["reserve"]), left=money(keep))
    return line, alt


def reply_lines(B, rec):
    """OFR-239: lines the chat reply must carry outside its length cap, as [{key, text}]: `seller_timeline` (the seller is
    flexible on the closing date: ask whether another date helps), `flat_number` (a highest-and-best round with no
    escalation: why one flat number), `contract_terms` (a contract that isn't FAR/BAR: the form-specific terms come from
    the agent's contract) and `inspection_period` (that contract with the period's length not set by the agent)."""
    out = []
    P = B["property"]
    if P.get("seller_flexible_close") and not P.get("seller_deadline"):
        out.append({"key": "seller_timeline", "text": L_["rl_seller_timeline"]})  # chat only, never in the report
    if highest_and_best(B["competition"]) and not rec.get("escalation"):
        out.append({"key": "flat_number", "text": t("rl_flat_number", price=money(rec["price"]))})
    if B["contract_form"] not in cf.FARBAR:
        out.append({"key": "contract_terms", "text": L_["rl_contract_terms"]})
        if "inspection_days" not in (B.get("overrides") or {}) and rec.get("inspection_days"):
            out.append({"key": "inspection_period", "text": t("rl_inspection_period", days=rec["inspection_days"])})
    return out


# --- formatted views (one document model: the PDFs, the markdown template and the chat read it) -------------------

TERM_KEYS = ("price", "seller_concessions", "deposit", "inspection_days", "loan_approval_days", "appraisal_gap",
             "closing_days", "buyer_broker_pct", "home_warranty", "escalation")


def term_val(k, t_, B):
    v = t_.get(k)
    if k == "price":
        return money(v)
    if k == "seller_concessions":
        return money(v) if v else L_["tv_none"]
    if k == "deposit":
        return t("tv_deposit", amount=money(v), pct=fmt.pct(v / t_["price"], 1, fixed=True))
    if k in ("inspection_days", "loan_approval_days"):
        return t("tv_days", n=v) if v else fmt.EMPTY
    if k == "appraisal_gap":
        return (money(v) if v else L_["tv_none"]) if B["buyer"]["financing"] != "cash" else fmt.EMPTY
    if k == "closing_days":
        return t("tv_closing", n=v, date=day(B["effective_date"] + timedelta(days=v)))
    if k == "buyer_broker_pct":
        return t("tv_bb", pct=fmt.pct(v, 2)) if v else L_["tv_not_requested"]
    if k == "home_warranty":
        return L_["tv_not_requested"] if not v else t("tv_warranty", amount=money(v))
    if k == "escalation":
        return t("tv_escalation", inc=money(v["increment"]), cap=money(v["cap"])) if v else L_["tv_none"]
    return str(v)


def term_label(k, B):
    """A term's name as the contract names it (OFR-234: contract_forms.term_words)."""
    if k == "inspection_days":
        return B["words"]["inspection_label"]
    if k == "deposit":
        return B["words"].get("deposit_label") or L_["term"]["deposit"]
    return L_["term"][k]


def shown_terms(r, keys):
    """The term keys a table shows: no loan approval or gap for cash, no escalation row unless one is used or reasoned."""
    B, cash = r["B"], r["B"]["buyer"]["financing"] == "cash"
    out = []
    for k in TERM_KEYS:
        if k in ("loan_approval_days", "appraisal_gap") and cash:
            continue
        if k == "escalation" and not any(r["terms"][x].get("escalation") for x in keys) and not r["why"].get("escalation"):
            continue
        out.append(k)
    return out


def diff_text(r, k):
    """What's different from the recommended offer, in short phrases."""
    B = r["B"]
    a, b = r["terms"]["recommended"], r["terms"][k]
    out = [t("diff", term=term_label(key, B).lower(), value=term_val(key, b, B)) for key in TERM_KEYS
           if a.get(key) != b.get(key)]
    return cap("; ".join(out)) or L_["same_terms"]


def deposit_risk(o):
    """OFR-210: (the date the deposit is at risk for anything but a low appraisal, the date the appraisal protection
    runs to or None). The engine's windows already follow the form and riders (contract_forms)."""
    ex = o.get("risk_days_ex_appraisal", o["risk_days"])
    first = o["firm_date"] - timedelta(days=o["risk_days"] - ex)
    return first, (o["firm_date"] if o["risk_days"] > ex else None)


rolled = oe.rolled  # OFR-219: the contract's weekend and holiday rule, shared with seller-offer-review (OFR-300)


def risk_after(o, costs):
    """OFR-219: (the date the deposit is at risk after, rolled per the contract rule; a short note or None). OFR-316: on
    a contract that isn't FAR/BAR the date is counted from the offer's own periods; the deposit_risk assumption asks the
    agent to confirm it, once, in What to Confirm."""
    d, was = rolled(deposit_risk(o)[0], costs)
    parts = []
    if was:
        parts.append(t("risk_rolled", date=wday(was)))
    elif not dates.is_business_day(d):
        parts.append(t("risk_check", what=dates.holiday_name(d) or fmt.weekday(d)))
    parts = [n for n in parts if n]
    return d, "; ".join(parts) or None


def risk_after_text(o, costs):
    d, note = risk_after(o, costs)
    return t("risk_after", date=wday(d), amount=money(o["deposit"]), note=f"; {note}" if note else "")


def appraisal_until(o, B, costs):
    """How long a low appraisal alone still protects the deposit: to closing (an FHA/VA rider), until a date, or None."""
    _, until = deposit_risk(o)
    if until is None:
        return None
    if o.get("appraisal_protected"):
        return t("protect_closing", prog=oe.FIN_LABEL[B["buyer"]["financing"]])
    return t("protect_until", date=wday(rolled(until, costs)[0]))


def appraisal_protection(o, B, costs):
    """The cash table's Low-Appraisal Protection cell: appraisal_until's text when a low appraisal alone protects the
    deposit longer, else, when the offer has an appraisal contingency whose window ends inside the deposit-at-risk
    window, that date marked "before the deposit is at risk"; None without one."""
    longer = appraisal_until(o, B, costs)
    if longer or not (o.get("appraisal_risk") and o.get("appraisal_days")):
        return longer
    eff = o["firm_date"] - timedelta(days=o["risk_days"])
    return t("protect_before", date=wday(rolled(eff + timedelta(days=o["appraisal_days"]), costs)[0]))


def downside_label(O):
    """The net sheet's downside row, named from what actually applies: the appraisal only for an option priced above the
    value range (its downside price is lower), the repair cost only when there is one."""
    appraisal = any(o["downside_price"] < o["price"] for o in O.values())
    repairs = [o for o in O.values() if o.get("repair_reserve")]
    repair = L_["dl_repair_limit" if any(o.get("repairs_owed") for o in repairs) else "dl_repair_credit"]
    if appraisal and repairs:
        return t("dl_both", repair=repair)
    if appraisal:
        return L_["dl_appraisal"]
    if repairs:
        return t("dl_inspection", repair=repair)
    return L_["dl_none"]


def fin_line(B):
    BU, f = B["buyer"], B["buyer"]["financing"]
    if f == "cash":
        return oe.FIN_LABEL["cash"]
    txt = t("fin_line", prog=oe.FIN_LABEL[f], down=fmt.pct(BU["down_pct"], 1))
    return txt + ("" if BU.get("financing_source") == "assumed" else L_["fin_given"])  # assumed: in the assumptions


def preliminary(r, listed):
    """The Preliminary line when a high-impact input is assumed: what to add, by name (the payment inputs that set the
    price first), and how many inputs were assumed (the What to Confirm table's count)."""
    hi = sorted([a for a in r["missing"] if a["impact"] == "high"], key=lambda a: not a.get("caps_price"))
    if not hi:
        return None
    B = r["B"]
    names = []
    for a in hi:
        f = a["field"]
        if f == "max_price":  # OFR-233: say what the max was assumed to be, so the reply never has to infer it
            mx, lp = B["buyer"]["max_price"], B["property"]["list_price"]
            names.append(t("pn_max_list" if mx == lp else "pn_max_top", amount=money(mx)))
        else:
            names.append(L_["pn"].get(f) or f.replace("_", " "))
    n = len(listed)
    return t("prelim", need=", ".join(dict.fromkeys(names)), n=n, inputs=L_["input_one" if n == 1 else "input_many"])


def summary(r, package_ready=False):
    """Page 1 of the Offer Options report, formatted. The markdown template and the chat use the same values."""
    B, O, lvl = r["B"], r["O"], r["B"]["competition"]["level"]
    BU, C, V = B["buyer"], B["competition"], B["value"]
    rec, rc = O["recommended"], r["cash"]["recommended"]
    br = r["bands"]["recommended"][lvl]
    broken = [w for _, w in r["limits"]["recommended"]]
    fr = r["framing"]
    band_vs = against(B, br[1])
    st_band = r["bands"]["stronger"][lvl][1] if "stronger" in O else ""
    lead = t(f"fr_{fr}", against=band_vs, limits="; ".join(broken), band=st_band)
    hero = [lead]
    if r.get("promoted") == "stronger":  # CMA-103: only what the stronger terms actually raised
        what = raised(r["terms"]["recommended"], r.get("promoted_from"))
        hero.append(t("hero_promoted", what=raised_words(what)) if what else L_["hero_promoted_any"])
    if BU["financing"] in ("fha", "va", "usda") and lvl >= 2:
        hero.append(t("hero_low_down_limit" if r.get("constraints") else "hero_low_down", prog=oe.FIN_LABEL[BU["financing"]]))
    if rc["reserve"] < 0:
        hero.insert(0, t("hero_short", short=money(-rc["reserve"])))
    terms = []
    t_, w = r["terms"]["recommended"], r["why"]
    for key in shown_terms(r, ["recommended"]):
        terms.append({"key": key, "term": term_label(key, B), "offer": term_val(key, t_, B), "why": cap(why_text(w.get(key))),
                      "agent": key in r["overrides"]})
    options = []
    for k in O:
        o, c = O[k], r["cash"][k]
        if k == "recommended":
            what = t(f"fr_{fr}_short", against=band_vs, limits=broken[0] if broken else "", band=st_band)
            status = "risk" if broken else ""  # no green beside an At Risk outlook: status only on a break
        elif k == "stronger":
            same = r["bands"][k][lvl] == br
            extra = c["worst"] - rc["worst"]
            gain = (t("opt_reaches", band=r["bands"][k][lvl][1]) if not same else
                    t("opt_same_more", score=o["score"]["total"], rec=rec["score"]["total"], amount=money(extra)) if extra > 0 else
                    t("opt_same_deposit", score=o["score"]["total"], rec=rec["score"]["total"]))
            what = diff_text(r, k) + gain + (f"; {r['limits'][k][0][1]}" if r["limits"][k] else "")
            status = "caution"
        else:
            what = diff_text(r, k) + t("opt_saves", amount=money(rc["worst"] - c["worst"])) + (
                "" if r["bands"][k][lvl] == br else t("opt_outlook", band=r["bands"][k][lvl][1]))
            status = "caution"
        options.append({"key": k, "option": opt_name(k), "price": money(o["price"]), "outlook": r["bands"][k][lvl][1],
                        "outlook_class": r["bands"][k][lvl][0], "seller_net": money(o["ns"]["net_adj"]),
                        "worst_cash": money(c["worst"]), "reserve": money(c["reserve"]), "what": what, "status": status})
    bands = [{"level": comp_label(lv) + (L_["expected_tag"] if lv == lvl else ""), "expected": lv == lvl,
              "values": [{"band": r["bands"][k][lv][1], "class": r["bands"][k][lv][0]} for k in O]} for lv in range(4)]
    exposure = [{"label": L_["ex_to_close"], "value": money(rc["to_close"])},
                {"label": L_["ex_gap"], "value": money(rc["gap"])},
                {"label": L_["ex_payment"], "value": per_month(r["payment"]["recommended"])
                 + (t("ex_of", amount=money(BU["max_payment"])) if BU.get("max_payment") else "")},
                {"label": L_["ex_risk_after"], "value": risk_after_text(rec, r["costs"])}]
    if appraisal_until(rec, B, r["costs"]):  # OFR-210: a low appraisal alone protects the deposit longer
        exposure.append({"label": L_["ex_protection"], "value": appraisal_until(rec, B, r["costs"])})
    if r.get("cash_at_cap"):
        cc = r["cash_at_cap"]
        exposure.append({"label": t("ex_at_cap", cap=money(t_["escalation"]["cap"])),
                         "value": t("ex_at_cap_value", worst=money(cc["worst"]), reserve=money(cc["reserve"]))})
    due = deadline_text(C.get("deadline"), B["analysis_date"])
    reserve_cls = reserve_status(B, rc["reserve"])
    tiles = [{"key": "strength", "label": L_["tile_strength"], "value": t("score", n=rec["score"]["total"]),
              "sub": rec["score"]["band"][1]},
             {"key": "seller_net", "label": L_["tile_net"], "value": money(rec["ns"]["net_adj"]),
              "sub": t("vs_clean", amount=money(rec["ns"]["net_adj"] - r["target"], style="signed"))},
             {"key": "worst", "label": L_["tile_worst"], "value": money(rc["worst"]),
              "sub": t("of_cash", amount=money(BU["cash_available"]))},
             {"key": "reserve", "label": L_["tile_reserve"], "value": money(rc["reserve"]),
              "sub": t("floor", amount=money(BU["reserve_floor"])), "status": reserve_cls}]
    absent = [{"key": k, "option": opt_name(k), "label": t("absent_label", option=opt_name(k)), "why": why_}
              for k, why_ in (r.get("absent") or {}).items()]
    return {
        "outlook": br[1], "outlook_class": br[0], "framing": fr,
        "competition": comp_label(lvl), "competition_inferred": bool(C.get("inferred")),
        "kicker": t("kicker", comp=comp_label(lvl) + (L_["inferred_tag"] if C.get("inferred") else "")),
        "why": " ".join(hero), "lead": lead,
        "submit_by": due or L_["submit_default"], "signal": signal(B),
        "financing": fin_line(B), "financing_assumed": BU.get("financing_source") == "assumed",
        "limits": your_limits(B),
        "strength": rec["score"]["total"], "seller_net": money(rec["ns"]["net_adj"]), "worst_cash": money(rc["worst"]),
        "tiles": tiles,
        "price_note": (L_["vr_not_provided"] if V.get("assumed") else t("vr_note", range=fmt.range(V["cma_low"], V["cma_high"], fmt.k))),
        "reserve_short": rc["reserve"] < BU["reserve_floor"], "reserve_status": reserve_cls,
        "terms": terms, "options": options, "bands": bands, "option_labels": [opt_name(k) for k in O],
        # OFR-208: one option is "Your Offer", and each option that isn't offered says why
        "options_title": L_["h_options" if len(O) > 1 else "h_offer"], "options_sub": t("h_options_sub", comp=comp_label(lvl)),
        "absent": absent, "exposure": exposure, "constraints": r["constraints"],
        "cautions": [r["reserve_tight"]] if r.get("reserve_tight") else [],  # OFR-338: within the limits, not a Limit line
        "breaks_limits": broken,
        "next_step": next_step(B, due, len(O), package_ready, opt_name(r["chosen"])),
    }


def deadline_text(text, today, style="deadline"):
    """An offer deadline in the report's words ("Fri Sep 25 · 5 PM"); text with no date in it prints as given."""
    if not text:
        return ""
    iso = deadline_iso(text, today)
    return fmt.when(iso, style) if iso else str(text)


def signal(B):
    """The page-1 Competition line, in the script's words: the listing agent's read (the level), or the inferred read
    with the signals it rests on, then this listing's days on market when known."""
    C, P, M = B["competition"], B["property"], B["market"]
    lvl = C["level"]
    if C.get("inferred"):
        s = (t("sig_inferred", level=comp_words(lvl), read=heat_words(C["heat"]), basis=C["heat_basis"])
             if C["heat_basis"] else t("sig_inferred_none", level=comp_words(lvl)))
    else:
        s = t("sig_agent", level=comp_words(lvl))
        if highest_and_best(C):
            s += L_["sig_hb"]
    if not C.get("inferred") and P.get("dom") is not None and M.get("median_dom"):
        s += f"; {dom_words(P['dom'], M['median_dom'])}"
    return s


def your_limits(B):
    BU = B["buyer"]
    return t("limits_line", max=money(BU["max_price"]), cash=money(BU["cash_available"]), keep=money(BU["reserve_floor"])) + (
        t("limits_pay", pay=money(BU["max_payment"])) if BU.get("max_payment") else "")


def next_step(B, deadline, n_options=2, package_ready=False, option=""):
    """What to do next: the documents to get, then the package: offered (a quick answer) or already made with the report
    (render.py builds both files), so the page never offers what it delivered."""
    BU = B["buyer"]
    if BU["financing"] == "cash":
        todo = (L_["nx_ins_and"] if not quote_in_hand(BU) else "") + L_["nx_pof"]
    else:
        todo = L_["nx_get"] + (L_["nx_ins_and_get"] if not quote_in_hand(BU) else "") + L_["nx_letter"]
    due = t("nx_before", when=deadline) if deadline else ""
    if package_ready:
        pick = t("nx_pick_ready", option=low_first(option)) if n_options > 1 else ""
        return cap(t("nx_ready", todo=todo, due=due)) + pick
    pick = L_["nx_pick"] if n_options > 1 else ""
    return cap(t("nx_prepare", pick=pick, todo=todo, due=due))


# The listing agent's likely counter, term by term, and the buyer's answer when it stays inside the buyer's limits
PUSHBACK_KEYS = {"Price": "price", "Seller Concessions": "seller_concessions", "Appraisal Gap Coverage": "appraisal_gap",
                 "Escrow Deposit": "deposit"}


def pushback(r):
    """OFR-214: the Likely Pushback rows on the recommended offer: [{term, yours, ask, response, breaks}]. An ask that
    would break one of the buyer's limits (price, payment, cash, reserve) or go past the CMA's walk-away is answered
    "hold" with that limit, by key."""
    B, costs, V = r["B"], r["costs"], r["B"]["value"]
    o, t_ = r["O"]["recommended"], r["terms"]["recommended"]
    ct = o.get("counter_terms") or {}
    # appraisal gap coverage is asked only for a price above the value range: the offer's own, or the countered price
    # when the buyer could take it (one that breaks a limit is held, so its gap never comes up)
    price_held = "price" in ct and bool(limits_broken(B, costs, dict(t_, price=ct["price"]), walk=True))
    final = t_["price"] if price_held else ct.get("price", t_["price"])
    no_gap = not V.get("assumed") and V.get("cma_high") is not None and final <= V["cma_high"]
    rows = []
    for term, yours, ask, _ in o.get("counter_rows") or []:
        if term == "Time for Acceptance" or term == "Appraisal Gap Coverage" and no_gap:
            continue
        key = PUSHBACK_KEYS.get(term)
        broken = limits_broken(B, costs, dict(t_, **{key: ct[key]}), walk=True) if key and key in ct else []
        if broken:
            # a term the offer leaves out (no gap coverage) has nothing to hold at: the template drops "at …"
            resp = t("pb_hold", yours=yours if t_.get(key) else None, ask=ask, limits=joined([wd for _, wd in broken]))
        elif term == "Price" and V.get("assumed"):
            resp = L_["pb_no_range"]
        elif term == "Price" and t_["price"] < V["cma_low"]:
            resp = t("pb_below", ask=ask)
        else:
            resp = fmt.fill(L_["pb_resp"].get(term) or L_["pb_resp_default"], **B["words"])
        label = term_label("inspection_days", B) if term == "Inspection Period" else \
            term_label("deposit", B) if term == "Escrow Deposit" else L_["pb_term"].get(term, term)
        rows.append({"term": label, "yours": yours, "ask": ask, "response": resp, "breaks": [k for k, _ in broken]})
    return rows


# --- the detail pages ---------------------------------------------------------------

def side_by_side(r):
    """The options side by side, one row per term ({key, term, values, differs}), then the payment row (key "payment",
    OFR-360): it follows from the terms, so it's never marked as a term that differs."""
    B, O = r["B"], r["O"]
    rows = []
    for key in shown_terms(r, list(O)):
        vals = [term_val(key, r["terms"][k], B) for k in O]
        rows.append({"key": key, "term": term_label(key, B), "values": vals,
                     "differs": [i > 0 and v != vals[0] for i, v in enumerate(vals)]})
    pay = L_["sbs_payment_no_flood" if B["flood"]["annual"] is None else "sbs_payment"]
    rows.append({"key": "payment", "term": pay, "values": [per_month(r["payment"][k]) for k in O], "differs": [False] * len(O)})
    return rows


def net_sheet(r):
    """The seller net sheet as the listing agent sees it: one column per option and a clean offer at list. Every line
    is the engine's Ledger line (rounded once); the net before payoff is their sum, the holding cost is added to it,
    so each column adds up. Lines that are zero in every column are left out (the sums don't change)."""
    O = r["O"]
    cols = [(opt_name(k), O[k]["ns"]) for k in O] + [(L_["col_clean"], O["recommended"]["target"])]
    labels = {}
    for _, c in cols:  # by line key, not position: a rider line can be on one column and not another
        for key, label, _ in c["lines"]:
            labels.setdefault(key, label)

    def cell(v):
        return {"amount": v, "text": money(v, style="accounting")}
    rows = []
    for key, label in labels.items():
        vals = [next((amt for k, _, amt in c["lines"] if k == key), 0) for _, c in cols]
        if all(v == 0 for v in vals):
            continue
        rows.append({"key": key, "label": label, "cells": [cell(v) for v in vals]})
    down = [cell(O[k]["ns_down"]["net_adj"]) for k in O] + [{"amount": None, "text": fmt.EMPTY}]
    return {"columns": [c for c, _ in cols], "rows": rows,
            "net": {"label": L_["ns_net"], "cells": [cell(c["net"]) for _, c in cols]},
            "holding": {"label": L_["ns_holding"], "cells": [cell(c["holding"]) for _, c in cols]},
            "net_adj": {"label": L_["ns_net_adj"], "cells": [cell(c["net_adj"]) for _, c in cols]},
            "downside": {"label": downside_label(O), "cells": down}}


def scorecard(r):
    O, rec = r["O"], r["O"]["recommended"]
    rows = [{"key": key, "label": label, "weight": t("weight", n=wt),
             "scores": [O[k]["score"]["scores"][key] for k in O], "why": cap(str(rec["score"]["why"][key]))}
            for key, label, wt in oe.CRITERIA]
    total = {"label": L_["sc_total"], "weight": t("weight", n=100), "scores": [O[k]["score"]["total"] for k in O],
             "bands": [O[k]["score"]["band"][0] for k in O]}
    return {"rows": rows, "total": total}


def cash_table(r):
    """The buyer's cash per option: each option's cash_ledger lines, cash to close (their sum), the gap, the worst case,
    what's left of the buyer's cash, then the deposit and appraisal dates."""
    B, O = r["B"], r["O"]
    K = list(O)
    led = {k: cash_ledger(B, r["terms"][k]) for k in K}

    def cell(v):
        return {"amount": v, "text": money(v, style="accounting")}
    keys = [k for k in ("down", "cc", "bb_short", "conc") if k != "bb_short" or any(led[x].amount(k) for x in K)]
    # costs print as positive amounts and the concessions credit as a negative one, so the column adds to cash to close
    rows = [{"key": k, "label": L_[f"cr_{k}"], "cells": [cell(-led[x].amount(k)) for x in K]} for k in keys]
    out = {"columns": [opt_name(k) for k in K], "rows": rows,
           "to_close": {"label": L_["cr_to_close"], "cells": [cell(r["cash"][k]["to_close"]) for k in K]},
           "gap": {"label": L_["cr_gap"], "cells": [cell(r["cash"][k]["gap"]) for k in K]},
           "worst": {"label": L_["cr_worst"], "cells": [cell(r["cash"][k]["worst"]) for k in K]},
           "reserve": {"label": t("cr_reserve", cash=money(B["buyer"]["cash_available"])),
                       "cells": [{**cell(r["cash"][k]["reserve"]), "status": reserve_status(B, r["cash"][k]["reserve"])} for k in K]},
           "risk_after": {"label": L_["cr_risk_after"],
                          "cells": [t("cr_risk_cell", date=day(risk_after(O[k], r["costs"])[0]), amount=money(O[k]["deposit"]))
                                    for k in K]}}
    if any(appraisal_until(O[k], B, r["costs"]) for k in K):  # OFR-210: the appraisal protection on its own row
        out["protection"] = {"label": L_["cr_protection"],
                             "cells": [appraisal_protection(O[k], B, r["costs"]) or fmt.EMPTY for k in K]}
    return out


def market_check(B):
    """OFR-359: the Market Check rows as [{label, value, note}], the same for the PDF and the markdown answer."""
    M, V = B["market"], B["value"]
    src = None
    if not V.get("assumed") and (V.get("source") or V.get("as_of")):
        src = t("vr_source_dated", source=V.get("source") or L_["src_cma"]["buyer"], date=fmt.date_short(V["as_of"])) \
            if fmt.to_date(V.get("as_of")) else V.get("source")
    rows = [(L_["mc_range"], fmt.range(V["cma_low"], V["cma_high"]) if not V.get("assumed") else L_["vr_not_provided"], src),
            (stl_label(M), fmt.pct(M["sale_to_list"], 1, fixed=True) if M.get("sale_to_list") else fmt.EMPTY, None),
            (L_["mc_supply"], fmt.months(M["months_supply"]) if num(M.get("months_supply")) else fmt.EMPTY, None),
            (L_["mc_median_dom"], t("days", n=fmt.num(M["median_dom"])) if num(M.get("median_dom")) else fmt.EMPTY, None),
            (L_["mc_share"], fmt.pct(M["share_with_seller_costs"], 0) if num(M.get("share_with_seller_costs")) else fmt.EMPTY, None),
            (L_["mc_typical"], money(M["typical_seller_paid"]) if num(M.get("typical_seller_paid")) else fmt.EMPTY, None),
            (L_["mc_read"], *market_read(B))]
    if V.get("median_adjusted"):
        rows.insert(1, (L_["mc_median_adjusted"], money(V["median_adjusted"]), None))
    plan = B.get("cma_offer_plan") or {}
    if plan.get("target_low") and plan.get("target_high"):
        rows.append((L_["mc_plan"], t("mc_plan_value", target=fmt.range(plan["target_low"], plan["target_high"]))
                     + (t("mc_plan_walk", walk=money(plan["walk_away"])) if plan.get("walk_away") else ""), None))
    return [{"label": a, "value": str(b), "note": c} for a, b, c in rows]


def snapshot(B):
    """The home facts under the header and the market strip below them, one value per cell (missing ones left out)."""
    P, M, C = B["property"], B["market"], B["competition"]
    facts = [t("f_beds", n=P["beds"]) if P.get("beds") else None, t("f_baths", n=P["baths"]) if P.get("baths") else None,
             t("f_sqft", n=fmt.num(P["sqft"])) if P.get("sqft") else None,
             t("f_built", year=P["year_built"]) if P.get("year_built") else None,
             t("f_roof", year=P["roof_year"]) if P.get("roof_year") else None]
    due = deadline_text(C.get("deadline"), B["analysis_date"]) or None
    cells = [(stl_label(M), fmt.pct(M["sale_to_list"], 1, fixed=True) if M.get("sale_to_list") else None),
             (L_["mc_supply_short"], fmt.num(M["months_supply"], 1) if num(M.get("months_supply")) else None),
             (L_["snap_dom"], fmt.num(P["dom"]) if P.get("dom") is not None else None),
             (L_["mc_median_dom"], fmt.num(M["median_dom"]) if num(M.get("median_dom")) else None),
             (L_["snap_due"], due)]
    return {"facts": [x for x in facts if x], "cells": [{"label": a, "value": b} for a, b in cells if b not in (None, "")]}


# --- offer package worksheet -------------------------------------------------------

def blank(x):
    """A blank the agent must fill in (rendered red in the PDF)."""
    return f"[{x}]"


HOA_PERIODS = {"monthly": 1, "quarterly": 3, "semiannual": 6, "semi-annual": 6, "annual": 12, "annually": 12, "yearly": 12}


def hoa_dues(P):
    """Rider B's dues as the association bills them ("$105 per quarter"): `hoa_monthly` times the billing period in
    `hoa_frequency`; without a frequency, a blank for the billed amount beside the monthly figure."""
    m = P.get("hoa_monthly") or 0
    months = HOA_PERIODS.get(str(P.get("hoa_frequency") or "").strip().lower())
    if months:
        return t("hoa_billed", amount=money(m * months), per=L_["hoa_per"][str(months)])
    return t("hoa_blank", blank=blank(L_["bl_hoa"]), monthly=money(m))


def para_key(row):
    """Contract entries in paragraph order: 1, 2, 2(a)…2(d), 3, 4… ("2(c) / 8" sorts as 2(c)); a row with no paragraph
    (another state's contract) keeps its place."""
    m = re.match(r"(\d+)(?:\(([a-z])\))?", str(row[0]))
    return (int(m.group(1)), m.group(2) or "") if m else (0, "")


def legal_entry(W):
    """The worksheet's Legal Description / Parcel ID entry, both in the Enter column; a missing part prints as a red
    blank, never invented."""
    legal, pid = W.get("legal_description"), W.get("parcel_id")
    if not legal and not pid:
        return blank(L_["bl_appraiser"])
    return t("ws_legal", legal=legal or blank(L_["bl_legal"]), pid=pid or blank(L_["bl_appraiser"]))


def worksheet(r, variant=None):
    """Contract entries, riders, additional terms, documents to request and the package checklist for one option.

    Built from the option's terms and the property only: never the buyer's max price, cash, reserve or payment limit.
    """
    variant = variant or r["chosen"]
    if variant not in r["terms"]:
        raise oe.OfferError(t("err_option", option=opt_name(variant) if variant in OPTIONS else variant,
                              have=", ".join(opt_name(k) for k in r["terms"])))
    B, costs = r["B"], r["costs"]
    P, BU, C, W = B["property"], B["buyer"], B["competition"], B.get("worksheet") or {}
    t_, o = r["terms"][variant], r["O"][variant]
    form = B["contract_form"]  # resolved once in prepare(), the same form the options were scored on
    farbar = form in cf.FARBAR
    terms = cf.terms(form, {"riders": [], "contract_name": W.get("contract_name")})  # ENG-11: the form's rules, one place
    fin = BU["financing"]
    financed = fin != "cash"
    price = t_["price"]
    loan = fmt.half_up(price * (1 - BU["down_pct"])) if financed else 0
    eff = B["effective_date"]  # OFR-123: every date counts from the expected Effective Date
    close = oe.prior_weekday(eff + timedelta(days=t_["closing_days"]) if t_.get("closing_days") else o["close"])
    if farbar:
        form_name = cf.FORM_TITLES[form]
        form_why = L_["ws_form_as_is" if terms["walkaway"] else "ws_form_standard"]
    else:
        form_name = W.get("contract_name") or L_["ws_form_other_name"]
        form_why = L_["ws_form_other"]
    offer_due = deadline_date(W.get("acceptance_deadline") or C.get("deadline"), B["analysis_date"])
    # OFR-123: the offer stays open past the listing agent's deadline, so the seller can answer (the Effective Date)
    accept = eff if dates.is_business_day(eff) else dates.next_business_day(eff)  # never a weekend or holiday 5:00 PM
    deadline = deadline_text(W.get("acceptance_deadline"), B["analysis_date"], "long") or (
        fmt.when(f"{accept} 17:00", "long") if offer_due or not C.get("deadline") else None)
    para = (lambda p: p) if farbar else (lambda p: "")
    title_payer = costs.get("closing_costs.owner_title.payer")
    title_src = costs.described("closing_costs.owner_title.payer")
    fl = costs.state == "FL"
    E = L_["ws_field"]
    rows = [  # (paragraph, field, entry, note)
        (para("1"), E["buyers"], W.get("buyer_names") or blank(L_["bl_buyers"]), L_["wn_buyers"]),
        (para("1"), E["sellers"], blank(L_["bl_sellers"]), ""),
        (para("1"), E["address"], P.get("address") or blank(L_["bl_address"]), ""),
        (para("1"), E["legal"], legal_entry(W), L_["wn_legal"] if W.get("legal_description") or W.get("parcel_id") else ""),
        (para("1"), E["personal"], W.get("personal_property") or blank(L_["bl_personal"]), L_["wn_personal"]),
        (para("2"), E["price"], f"**{money(price)}**", ""),
        (para("2(a)"), E["deposit"], t("we_deposit_farbar" if farbar else "we_deposit", amount=money(t_["deposit"])),
         "" if farbar else L_["wn_deposit_due"]),
        (para("2(a)"), E["escrow"], W.get("escrow_agent") or blank(L_["bl_escrow"]), ""),
        (para("2(b)"), E["additional"], L_["tv_none"], L_["wn_additional"]),
    ]
    if financed:
        rows.append((para("2(c) / 8"), E["financing"], t("we_financing", prog=oe.FIN_LABEL[fin], loan=money(loan),
                                                        ltv=fmt.pct(1 - BU["down_pct"], 1, fixed=True)),
                     L_["wn_financing"] + (L_["wn_financing_confirm"] if BU.get("financing_source") == "assumed" else "")))
        rows.append((para("8(b)"), E["loan_approval"], t("we_days", n=t_.get("loan_approval_days", 30)),
                     L_["wn_loan_app"] if farbar else ""))
    else:
        rows.append((para("8"), E["financing"], L_["we_cash"], L_["wn_pof"]))
    rows += [
        (para("2(d)"), E["balance"], t("we_balance", amount=money(price - t_["deposit"] - loan)), L_["wn_balance"]),
        (para("3"), E["acceptance"], deadline or blank(L_["bl_date_time"]),
         L_["wn_acceptance_past"] if C.get("deadline") and not W.get("acceptance_deadline") else L_["wn_acceptance"]),
        # OFR-227: a lender who confirmed the financing (lender_called) hasn't confirmed this date; only
        # lender_confirmed_timeline does, and it ticks the checklist's closing box too
        (para("4"), E["closing"], f"**{fmt.date_long(close)}**",
         L_["wn_close_cash"] if not financed else L_["wn_close_confirmed"] if BU.get("lender_confirmed_timeline") else
         L_["wn_close_financing"] if BU.get("lender_called") else L_["wn_close_confirm"]),
        (para("6"), E["occupancy"], L_["we_occupancy"], ""),
    ]
    if title_payer in ("seller", "buyer"):
        rows.append((para("9"), E["title"], L_[f"we_title_{title_payer}"], t("wn_title", src=title_src)))
    else:
        rows.append((para("9"), E["title"], blank(L_["bl_title"]), L_["wn_title_ask"]))
    rows += [
        (para("9"), E["seller_costs"], t("we_seller_costs", amount=money(t_["seller_concessions"]))
         if t_.get("seller_concessions") else L_["tv_none"], L_["wn_seller_costs"]),
        (para("9"), E["warranty"], L_["we_warranty_none"] if not t_.get("home_warranty") else
         t("we_warranty", amount=money(t_["home_warranty"])), ""),
        (para("9"), E["survey"], L_["we_survey"], L_["wn_survey"]),
    ]
    rows.append((para("12"), B["words"]["inspection_label"], t("we_days", n=t_["inspection_days"]),
                 t("wn_inspector_farbar", four=L_["wn_four_point"] if fl else "") if farbar else
                 L_["wn_inspector_other"] + ("" if "inspection_days" in (B.get("overrides") or {}) else L_["wn_inspector_generic"])))
    if terms["repairs_owed"]:
        lim = cf.repair_limits(price, {"repair_limits": B.get("repair_limits")})
        rows.append((para("9"), E["repairs"], t("we_repairs", general=money(lim["general"]), wdo=money(lim["wdo"]),
                                                permit=money(lim["permit"])), L_["wn_repairs"]))

    names = L_["rider_farbar"] if farbar else dict(L_["rider_generic"], appraisal=B["words"]["appraisal_addendum"])
    riders = []  # (name, inputs, why)
    yb, roof, fz = P.get("year_built"), P.get("roof_year"), (P.get("flood_zone") or "").upper()
    if fin in ("fha", "va"):
        # OFR-209: the Para. 2 cap on seller-paid appraisal repairs has no default (farbar-riders.md, Rider E)
        repair_cap = t("ri_e_cap_farbar" if farbar else "ri_e_cap", blank=blank(L_["bl_amount_no_default" if farbar else "bl_amount"]))
        cap_note = (L_["ri_e_note_new"] if not terms["repairs_owed"] else L_["ri_e_note_extra"]) if farbar else ""
        riders.append((names["fha_va"], t("ri_e", prog=oe.FIN_LABEL[fin], price=money(price), cap=repair_cap),
                       L_["ri_e_why"] + cap_note))
    # FAR/BAR: the Appraisal Gap Addendum is for conventional or cash offers and isn't used with the Appraisal Contingency
    # Rider (AGA-1's own instructions), so a gap offer uses AGA-1 and no rider F (appraisal_kind, the same rule scored).
    aga = appraisal_kind(B, t_) == "aga"
    if aga:
        vd = aga_valuation(t_, fin)  # OFR-106: filled so AGA-1's periods end with loan approval (cash: by closing)
        riders.append((names["gap"], t("ri_aga", gap=money(t_["appraisal_gap"]), days=vd,
                                       how=L_["ri_aga_default" if vd == cf.AGA_VALUATION_DAYS else
                                              "ri_aga_loan" if financed else "ri_aga_close"]), L_["ri_aga_why"]))
    elif fin in ("conventional", "usda"):
        due = L_["ri_f_due_farbar"] if farbar else t("ri_f_due", days=t_.get("appraisal_days", 21))
        riders.append((names["appraisal"], t("ri_f", price=money(price), due=due),
                       L_["ri_f_why"] + (L_["ri_f_pair"] if t_.get("appraisal_gap") else "")))
    if (P.get("hoa_monthly") or 0) > 0 or W.get("hoa_name"):
        riders.append((names["hoa"], t("ri_b", name=W.get("hoa_name") or blank(L_["bl_name"]), dues=hoa_dues(P),
                                       yn=blank(L_["bl_yes_no"]), ask=blank(L_["bl_ask"])), L_["ri_b_why"]))
    if P.get("type") == "condo":
        riders.append((names["condo"], t("ri_a", name=blank(L_["bl_name"])), L_["ri_a_why"]))
    if yb and yb < 1978:
        riders.append((names["lead"], L_["ri_p"], t("ri_p_why", year=yb)))
    ins_reason = []
    if roof and B["analysis_date"].year - roof >= 15:
        ins_reason.append(t("ri_h_roof", years=B["analysis_date"].year - roof))
    if fz[:1] in ("A", "V"):
        ins_reason.append(t("ri_h_flood", zone=fz))
    if not quote_in_hand(BU):
        ins_reason.append(L_["ri_h_no_quote"])
    if ins_reason and financed:
        due = L_["ri_h_due_farbar"] if farbar else t("ri_h_due", blank=blank(L_["bl_per_form"]))
        riders.append((names["insurance"], t("ri_h", due=due, blank=blank(L_["bl_per_year"])),
                       t("ri_h_why", reasons=", ".join(ins_reason))))
    if BU.get("needs_sale"):
        riders.append((names["sale"], t("ri_v", address=blank(L_["bl_address"]), days=blank(L_["bl_days_21"])), L_["ri_v_why"]))
        riders.append((names["kickout"], L_["ri_x"], L_["ri_x_why"]))
    if C.get("backup"):
        riders.append((names["backup"], fmt.EMPTY, L_["ri_w_why"]))
    if t_.get("escalation"):
        e = t_["escalation"]
        # OFR-105: no promise of rising gap coverage; the package's gap is written at the cap's gap (build_offer)
        riders.append((names["escalation"], t("ri_esc", inc=money(e["increment"]), cap=money(e["cap"])),
                       L_["ri_esc_inside"] if e["cap"] <= B["value"]["cma_high"] else
                       t("ri_esc_above", gap=money(t_.get("appraisal_gap") or 0))))
    if P.get("cdd"):
        riders.append((names["cdd"], t("ri_cdd", blank=blank(L_["bl_amount"])), L_["ri_cdd_why"]))
    if P.get("short_sale"):
        riders.append((names["short_sale"], t("ri_g", blank=blank(L_["bl_days"])), L_["ri_g_why"]))
    if farbar and B.get("buyer_broker_form") and t_.get("buyer_broker_pct"):
        bb = money(t_["buyer_broker_pct"] * price)
        if bb_as_credit(B):
            riders.append((names["bb_FF"], t("ri_ff", pct=fmt.pct(t_["buyer_broker_pct"], 2, fixed=True), amount=bb), L_["ri_ff_why"]))
        else:
            riders.append((names["bb_GG"], t("ri_gg", amount=bb, blank=blank(L_["bl_signer"])), L_["ri_gg_why"]))

    if farbar:  # numeric paragraph order (2(c), 2(d), 3, ... 8(b)), stable within a paragraph
        rows.sort(key=para_key)
    order = cf.rider_order([x[0] for x in riders])  # the forms' letter order: B, F, H, then GG; addenda after
    riders.sort(key=lambda x: order.index(x[0]))

    clauses = []
    if t_.get("seller_concessions"):
        clauses.append((L_["cl_costs"], t("cl_costs_text", amount=money(t_["seller_concessions"]))))
    if financed and t_.get("appraisal_gap") and not aga:
        rider = names["fha_va"] if fin in ("fha", "va") else names["appraisal"]
        # OFR-234: another contract's appraisal right lives in its own addendum, so the clause points to it generically
        rights = t("cl_rights_rider", rider=rider) if farbar or fin in ("fha", "va") else L_["cl_rights_generic"]
        clauses.append((L_["cl_gap"], t("cl_gap_text", gap=money(t_["appraisal_gap"]), rights=rights)))
    clauses.append((L_["cl_reports"], t("cl_reports_text", reports=L_["cl_reports_fl" if fl else "cl_reports_other"])))
    if t_.get("escalation") and not any(x[0] == names["escalation"] for x in riders):
        e = t_["escalation"]
        clauses.append((L_["cl_escalation"], t("cl_escalation_text", inc=money(e["increment"]), cap=money(e["cap"]))))

    docs = [L_["doc_disclosure"], L_["doc_permits"], t("doc_inspections", fl=L_["doc_fl_reports"] if fl else ""), L_["doc_survey"]]
    fd = costs.get("flood.seller_disclosure")
    if fd:  # CMA-6: given at or before signing
        docs.insert(1, t("doc_flood", statute=fd.get("statute") or L_["doc_state_form"]))
    if finance.property_type(P.get("type")) == "condo":  # CMA-5
        docs.insert(1, L_["doc_condo"])
    elif (P.get("hoa_monthly") or 0) > 0:
        docs.insert(1, L_["doc_hoa"])
    if yb and yb < 1978:
        docs.append(L_["doc_lead"])
    if P.get("cdd"):
        docs.append(L_["doc_cdd"])

    CK = BU.get("checklist") or {}
    esc = t_.get("escalation")  # letters and proof of funds cover the price the offer can reach (OFR-27)
    worst = (buyer_cash(B, dict(t_, price=esc["cap"], appraisal_gap=esc.get("gap_at_cap", t_.get("appraisal_gap", 0))))["worst"]
             if esc else r["cash"][variant]["worst"])
    # FAR/BAR riders keep their CR-7 letter or form code, as in section 2; another contract's generic names drop their hints
    rider_list = ", ".join(x[0] if farbar else x[0].split(" (")[0] for x in riders) or L_["none_word"]
    G = L_["pk_group"]
    package = [  # (group, item, status, note)
        (G["contract"], t("pk_contract", form=terms["title"] if farbar else L_["pk_contract_word"]), CK.get("contract", "Pending"), ""),
        (G["contract"], t("pk_riders", riders=rider_list), CK.get("riders", "Pending"), ""),
        (G["contract"], L_["pk_terms"], CK.get("terms", "Pending"), ""),
        (G["buyer"], L_["pk_letter"] if financed else L_["pk_pof_cash"], CK.get("pre_approval", "Pending"),
         (t("pk_letter_cap", cap=money(esc["cap"])) if esc else t("pk_letter_at", price=money(price))) if financed else ""),
        (G["buyer"], (L_["pk_funds_gap"] if t_.get("appraisal_gap") else L_["pk_funds"]) if financed else L_["pk_source"],
         CK.get("funds", "Pending"), t("pk_funds_note", amount=money(worst), cap=L_["pk_at_cap"] if esc else "") if financed else ""),
        (G["buyer"], L_["pk_insurance"], CK.get("insurance", "Yes" if quote_in_hand(BU) else "Pending"), L_["pk_before"]),
        (G["disclosures"], L_["pk_agency_fl" if fl else "pk_agency"], CK.get("agency", "Pending"),
         L_["pk_agency_fl_note" if fl else "pk_agency_note"]),
        (G["disclosures"], L_["pk_bb"], CK.get("bb", "Pending"),
         t("pk_bb_note", pct=fmt.pct(t_["buyer_broker_pct"], 2)) if t_.get("buyer_broker_pct") else L_["pk_bb_none"]),
        (G["disclosures"], L_["pk_wire"], CK.get("wire", "Pending"), L_["pk_wire_note"]),
    ]
    if yb and yb < 1978:
        package.append((G["disclosures"], L_["pk_lead"], CK.get("lead", "Pending"), t("ri_p_why", year=yb)))
    package += [
        (G["timing"], t("pk_inspector", four=L_["wn_four_point"] if fl else "", days=t_["inspection_days"],
                        period=B["words"]["inspection"]), CK.get("inspector", "Pending"), ""),
        # OFR-126: a call to the lender isn't a confirmed closing date: the box is the agent's to tick, or ticked when the
        # agent says the lender confirmed the timeline (OFR-227), matching the Closing Date note
        (G["timing"], t("pk_lender", days=(close - eff).days) if financed else L_["pk_funds_by"],
         CK.get("lender_close", "Yes" if financed and BU.get("lender_confirmed_timeline") else "Pending"),
         t("pk_closing", date=day(close))),
        # OFR-206: a thing to leave out, so its box is never ticked (the renderer prints a cross, not a check)
        (G["never"], L_["pk_never"], "Never", L_["pk_never_note"]),
    ]
    return {"variant": variant, "option": opt_name(variant), "price": money(price), "farbar": farbar, "form_name": form_name,
            "form_why": form_why, "software": L_["ws_software_farbar" if farbar else "ws_software_other"],
            "rows": [{"para": a, "field": b, "entry": c, "note": d} for a, b, c, d in rows],
            "riders": [{"rider": a, "inputs": b, "why": c} for a, b, c in riders],
            "clauses": [{"title": a, "text": b} for a, b in clauses], "docs": docs,
            "package": [{"group": a, "item": b, "status": c, "note": d} for a, b, c, d in package],
            "blanks": sum(x.count("[") for x in [c for _, _, c, _ in rows] + [b for _, b, _ in riders])}


# --- assumptions, notes and the chat lines ---------------------------------------------

NOTE_KEY = {"rate_source": "rate"}  # one key per fact, whichever way it falls


def akey(a):
    """An assumption's note key: its field (one key per fact)."""
    return NOTE_KEY.get(a["field"], a["field"])


def report_notes(r, listed):
    """The document's one notes registry (shared/notes.py). The assumptions the report lists (What to Confirm) come
    first, keyed by field, so a note that says the same thing under that key is never added again; then the seller net
    sheet's cost notes (keyed like the engine's assumptions), how payments and closing costs are figured, and the fixed
    lines, each once."""
    B, R = r["B"], r["R"]
    N = notes.Notes()
    for a in listed:
        N.add(akey(a), a["why"], "assumption")
    lf = R["seller"]["listing_fee_pct"]
    N.add("listing_fee_pct", t("note_listing_fee", pct=fmt.pct(lf, 2)) if lf else L_["note_listing_fee_none"], "estimate")
    for n in R["listing"]["cost_notes"]:
        N.add(getattr(n, "key", None) or str(n), str(n) + ("" if str(n).endswith((".", ")")) and str(n).endswith(".") else "."),
              "estimate")
    N.add("closing_cost_pct", t("note_closing_costs", basis=closing_cost_basis(B)), "info")
    N.add("rate", t("note_rate", rate=fmt.pct(B["costs"]["rate"] / 100, None)), "info")
    N.add("loan_estimate", L_["note_loan_estimate"], "info")
    N.add("worst_case", L_["note_worst_case"], "info")
    N.add("scoring", L_["note_scoring"], "info")
    N.add("loan_limits", L_["note_loan_limits"], "info")
    N.add("legal", t("note_legal", state=profiles.STATES.get(R["listing"].get("state") or "", L_["your_state"])), "info")
    return N


def to_confirm(r):
    """OFR-212: what to ask first, in the order the chat's one question uses: the listing agent's competition read when
    it was inferred, a weekday deadline that may already have passed, the payment inputs when the payment limit sets the
    price, then the rest by impact (OFR-222: within an impact, the questions that shape the offer come first)."""
    return [a for a in sorted(r["missing"], key=lambda a: (confirm_tier(a), oe.IMPACT_ORDER[a["impact"]],
                                                           a["field"] not in OFFER_QUESTIONS))
            if a["impact"] in ("high", "med")][:4]


def confirm_tier(a):
    if (a["scope"], a["field"]) == ("competition", "level"):
        return 0
    return 1 if a["field"] == "deadline" else 2 if a.get("caps_price") else 3


ASSUMED_WORDS = ("closing_cost_pct", "rate", "rate_source", "insurance_annual", "flood_insurance_annual", "property_tax",
                 "expected_effective_date", "current_tax_bill_paid")


def assumed_line(r, asked=()):
    """One line for the chat naming the assumptions the numbers rest on (closing costs, rate, insurance, flood, the
    acceptance date, the tax proration, the tax estimate), so the reply never leaves them out. The ones the reply's
    question already asks (`asked`, the first two of to_confirm) aren't repeated. None when nothing applies."""
    B = r["B"]
    skip = {(a["scope"], a["field"]) for a in asked}
    fill = {"basis": closing_cost_basis(B), "rate": fmt.pct(B["costs"]["rate"] / 100, None),
            "amount": money(B["costs"].get("insurance_annual") or 0), "date": wday(B["effective_date"])}
    out = []
    for a in r["missing"]:
        f = a["field"]
        if f in ASSUMED_WORDS and (a["scope"], f) not in skip:
            key = "aw_insurance_none" if f == "insurance_annual" and not B["costs"].get("insurance_annual") else f"aw_{f}"
            w = t(key, **fill)
            if w not in out:
                out.append(w)
    return t("assumed_line", items=joined(out)) if out else None


def labels_of(M):
    """Every label the report prints (headings, column headers, row names, tiles), for notes.check_labels."""
    s, d = M["summary"], M["detail"]
    found = [x["label"] for x in s["tiles"]] + [x["term"] for x in s["terms"]] + [e["label"] for e in s["exposure"]]
    found += [x["term"] for x in d["side_by_side"]] + [r_["label"] for r_ in d["net_sheet"]["rows"]]
    found += [d["net_sheet"][k]["label"] for k in ("net", "holding", "net_adj", "downside")]
    found += [r_["label"] for r_ in d["scorecard"]["rows"]] + [r_["label"] for r_ in d["cash"]["rows"]]
    found += [d["cash"][k]["label"] for k in ("to_close", "gap", "worst", "reserve", "risk_after", "protection") if k in d["cash"]]
    found += [m["label"] for m in d["market_check"]] + [x["field"] for x in M["worksheet"]["rows"]]
    found += [x["rider"] for x in M["worksheet"]["riders"]] + [c["title"] for c in M["worksheet"]["clauses"]]
    found += [v for k, v in L_.items() if k.startswith(("h_", "th_", "lg_", "dh_")) and isinstance(v, str)]
    return found


def result(r, variant=None, package_ready=False):
    """The document model: the summary page 1 and the chat read, the detail pages, the worksheet for the chosen option,
    the assumptions (What to Confirm), the notes (each once), and the chat-only lines. Every figure is formatted here,
    once; render.py and the markdown template only place it."""
    B = r["B"]
    V = B["value"]
    listed = r["missing"]
    asks = to_confirm(r)
    N = report_notes(r, listed)
    s = summary(r, package_ready)
    s["preliminary"] = preliminary(r, listed)
    assumed = assumed_line(r, asked=asks[:2])
    out = {
        "ok": True, "property": B["property"].get("address") or "", "list_price": money(B["property"]["list_price"]),
        "street": (B["property"].get("address") or L_["property_word"]).split(",")[0],
        "prepared_for": B["buyer"].get("name") or L_["buyer_word"], "date": fmt.date_long(B["analysis_date"]),
        "financing_label": oe.FIN_LABEL[B["buyer"]["financing"]],
        # OFR-356: null when no CMA gave a range (list price stands in for value)
        "value_range": None if V.get("assumed") else fmt.range(V["cma_low"], V["cma_high"]),
        "summary": s,
        "snapshot": snapshot(B),
        "detail": {"side_by_side": side_by_side(r), "net_sheet": net_sheet(r), "scorecard": scorecard(r), "cash": cash_table(r),
                   "market_check": market_check(B), "pushback": pushback(r), "pushback_none": L_["pb_none"],
                   "one_option": len(r["O"]) == 1},
        "worksheet": worksheet(r, variant),
        "to_confirm": [a["why"] for a in asks],
        # OFR-239: lines the chat reply carries outside its length cap ([{key, text}]); `assumptions`, the assumptions
        # behind the numbers that the reply's question doesn't ask about, in one line
        "reply_lines": (r.get("reply_lines") or []) + ([{"key": "assumptions", "text": assumed}] if assumed else []),
        "assumptions": [{"key": akey(a), "impact": a["impact"], "impact_label": L_["impact"][a["impact"]],
                         "where": L_["where"].get(a["scope"], a["scope"].title()), "what": a["why"]} for a in listed],
        "notes": N.texts("estimate") + N.texts("info"),  # the PDF's notes block (the assumptions are the table)
        "note_keys": [k for k, _, _ in N.items("chat", grouped=False)],
        "market_notes": list(r["costs"].notes),
        "sample": bool(r.get("sample")),
        # chat only: the best-effort line for a contract that isn't FAR/BAR, worded for an offer being written (OFR-314)
        **cf.support([B["contract_form"]], drafting=True),
    }
    # the markdown template's and the older readers' names for the detail tables
    for k in ("side_by_side", "market_check", "pushback"):
        out[k] = out["detail"][k]
    N.check_labels(labels_of(out))
    return out


def compute(data, ctx):
    """render.main's compute step: the engine once, then the document model every file and the chat read, and the
    lines for the agent (stderr)."""
    r = analyze(data, cma=load_cma(data, ctx.get("cma")))
    M = result(r, ctx.get("option"), package_ready="worksheet" in (ctx.get("formats") or ()))
    lines = [f"For the agent (chat only, never on the report): {n}" for n in M["chat_notes"]]
    return {"model": M, "agent_lines": lines, "sample": M["sample"]}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("buyer")
    ap.add_argument("--cma", help="CMA handoff: a .cma.json file or markdown with a cma-handoff block")
    ap.add_argument("--option", choices=list(OPTIONS), help="option for the worksheet (default: the file's chosen_option)")
    a = ap.parse_args(argv)
    try:
        with open(a.buyer, encoding="utf-8") as f:
            data = json.load(f)
        out = result(analyze(data, cma=load_cma(data, a.cma)), a.option)
    except (oe.OfferError, handoff.HandoffError, profiles.ProfileError, notes.NotesError, ValueError, KeyError, OSError) as e:
        out = {"ok": False, "problems": str(e).split("\n")}
    print(json.dumps(out, indent=2, ensure_ascii=False, default=str))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
