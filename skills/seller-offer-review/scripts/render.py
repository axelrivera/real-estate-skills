"""Offer review PDF for the seller (listing side): one offer, or every active offer compared.

    python3 scripts/render.py listing.json [--cma file.cma.json] [--mode single|multi] [--offer ID] [--packet]
                              [--agent agent-profile.md] [--market market-profile.md] [--sample] [--out DIR]

Single review: page 1 is a self-contained executive summary (the recommendation, the counter, key
numbers, certainty and the seller's options); the pages after it hold the net sheet, contingency
timeline, terms review, scorecard, risk flags, checklist, questions and assumptions.
Comparison: a two-page landscape decision summary, one row per offer (plan and ranking, chart up to 6 offers,
key terms side by side). --packet renders the comparison plus a single review of every active offer.
Colors follow the agent's seller-side brand color.
"""
import html
import math
import os
import re
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import review  # noqa: E402
from _shared import design, handoff, offer_engine as oe, profiles, render  # noqa: E402

esc = html.escape
money, signed = oe.money, review.signed
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "offer-review.css")
PAGE1_LIMIT = 989  # px available on page 1 at the print viewport (portrait)
PAGE1_LIMIT_WIDE = 749  # the comparison prints landscape: 8.5in minus margins
PILL = {"good": "low", "caution": "med", "risk": "high"}
RATING = {"good": "Favorable", "caution": "Watch", "risk": "Weak"}


def md(text):
    """Escape, then turn the summary's **bold** into <b>."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text or ""))


def acct(v):
    """Net-sheet style: costs in parentheses."""
    return money(v) if v >= 0 else f"({money(-v)})"


def pctx(v, d=1):
    return f"{v * 100:.{d}f}%"


# --- shared blocks -------------------------------------------------------------

def prepared_block(R, agent):
    lines = [f'Prepared for <b>{esc(R["seller"].get("name") or "Seller")}</b> · {R["listing"]["analysis_date"]:%B %-d, %Y}']
    if agent.get("name"):
        lines.append(f'<b>{esc(agent["name"])}</b>')
        org = " · ".join(esc(str(agent[f])) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {esc(str(agent["license"]))}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return "<br>".join(lines)


def header(R, title, sub, agent, sample):
    tag = '<span class="viewtag">Seller Side</span>' + ('<span class="sample">SAMPLE DATA</span>' if sample else "")
    return (f'<header><div><div class="t1">{title}{tag}</div><div class="t2">{sub}</div></div>'
            f'<div class="prep">{prepared_block(R, agent)}</div></header>')


def snapshot(R):
    """One divider row: the home, then the inputs the numbers rest on. Missing facts drop out; a missing
    input that makes the review Preliminary stays, in the risk color."""
    L, S = R["listing"], R["seller"]
    hoa = f"HOA ${L['hoa_monthly']:,}/mo" if L.get("hoa_monthly") else ("no HOA" if L.get("hoa_monthly") == 0 else None)
    facts = [f"{L['beds']} bed" if L.get("beds") else None, f"{L['baths']} bath" if L.get("baths") else None,
             f"{L['sqft']:,} sq ft" if L.get("sqft") else None, f"built {L['year_built']}" if L.get("year_built") else None,
             f"roof {L['roof_year']}" if L.get("roof_year") else None, hoa,
             f"flood zone {L['flood_zone']}" if L.get("flood_zone") else None]
    items = [esc(x) for x in facts if x]
    items.append(f"CMA {oe.short_price(L['cma_low'])}–{oe.short_price(L['cma_high'])}" if L["cma_provided"] else '<b class="rt">CMA not provided</b>')
    items.append(f"payoff {money(S['payoff'])}" if S["payoff_known"] else '<b class="rt">payoff not provided</b>')
    if S["deadline"]:
        items.append(f"seller's deadline {S['deadline']:%a %b %-d}")
    return '<div class="divrow factrow"><div>' + "".join(f"<span>{x}</span>" for x in items) + "</div></div>"


def state_name(R):
    st = R["listing"].get("state")
    return profiles.STATES.get(st or "", "your state")


def fine(R):
    L, S = R["listing"], R["seller"]
    costs = "; ".join(L["cost_notes"])
    tax = f"tax proration assumes {money(L['annual_tax'])}/yr paid in arrears" if L["annual_tax"] else "no tax proration included"
    ref = "top of the value range (CMA high)" if L["cma_provided"] else "list price"  # OFR-4: appraisal_line
    credit = (f" and an inspection credit of about {L['repair_reserve_pct'] * 100:.1f}% of price when the buyer has an inspection period"
              if L["repair_reserve_pct"] else "")
    return (f'<div class="fine">All figures are estimates for discussion only. {esc(costs)}. The {tax}; holding costs assume '
            f'{money(S["holding_monthly"])}/mo. The downside case assumes the appraisal lands at the {ref}{credit}. Actual costs come '
            "from the title company's settlement statement. Certainty scores reflect the listing agent's professional judgment, not a "
            f"guarantee of performance. This report is not legal or financial advice; consult a real estate attorney licensed in "
            f"{esc(state_name(R))} about contract terms.</div>")


def certainty_panel(c, subtitle="As Offered"):
    b = c["band_class"]
    t = {"hi": "hit", "mid": "midt", "lo": "lot"}[b]
    return f'''<div><h2>How Likely Is It to Close? <span class="h2s">{subtitle}</span></h2><div class="panel">
  <div class="gauge"><b class="{t}">{c["score"]}</b><span>/100 · <b class="{t}" style="font-size:inherit">{c["band"]}</b> certainty</span></div>
  <div class="meter"><div class="bar {b}" style="width:{c["score"]}%"></div></div>
  <table class="facts2">
   <tr><td>Buyer Can Walk Away Until</td><td class="n"><b>{esc(c["walk_away_until"])}</b></td></tr>
   <tr><td>Deposit at Risk After That</td><td class="n">{esc(c["deposit"]) if c["deposit"] != "not provided" else '<span class="rt">not provided</span>'}</td></tr>
   <tr><td>Closing</td><td class="n"><b class="{"" if c["closing_ok"] else "rt"}">{esc(c["closing"])}</b></td></tr>
   <tr><td>Biggest Threat</td><td class="n"><b class="rt">{esc(c["threat"])}</b></td></tr>
  </table></div></div>'''


def options_table(opts, widths=(24, 13, 15)):
    if not opts:
        return ""
    rows = "".join(
        f'<tr class="{"recrow" if x["recommended"] else ""}"><td><b>{esc(x["option"])}</b>'
        f'{" <span class=sm>(Recommended)</span>" if x["recommended"] else ""}</td><td class="n">{esc(x["net"])}</td>'
        f'<td class="c">{esc(x["certainty"])}</td><td class="{x["status"]}">{esc(x["what"])}</td></tr>' for x in opts)
    cols = "".join(f'<col style="width:{w}%">' for w in widths)
    return (f'<h2>Your Options</h2><div class="tbl"><table><colgroup>{cols}</colgroup>'
            f'<thead><tr><th>Option</th><th class="n">Net After Holding</th><th class="c">Certainty</th><th>What Happens</th></tr></thead>'
            f'<tbody>{rows}</tbody></table></div>')


def closing_block(v):
    pre = f'<div class="prelim">{md(v["preliminary"])}</div>' if v["preliminary"] else ""
    return (f'{pre}<div class="nextstep"><b>Next Step:</b> {esc(v["next_step"])} {"The detail follows on the next pages." if v["mode"] == "single" else "Key terms follow on the next page."}</div>'
            f'<div class="fine" style="margin-top:4px">{md(v["data_note"])} Estimates only; not legal or financial advice.</div>')


def hero(v):
    cls = {"DECLINE": "decline", "BACKUP": "backup", "INCOMPLETE": "decline"}.get(v["action"], "")
    ctx = f' · {v["offers_active"]} Offers Active' if v["offers_active"] > 1 else ""
    kicker = "Status" if v["action"] == "INCOMPLETE" else "Recommended Response"
    return (f'<div class="hero"><div class="hl {cls}"><span class="k">{kicker}{ctx}</span><div class="big">{esc(v["headline"])}</div>'
            + f'<div class="who">{esc(v["offer_label"])}</div>'
            + f'<div class="why">{md(v["why"])}</div></div>'
            f'<div class="hr"><span class="k">Respond By</span><b>{esc(v["respond_by"])}</b>'
            + (f'<span class="rbo">{esc(v["respond_by_offer"])}</span>' if v.get("respond_by_offer") else "")
            + f'<span class="k" style="margin-top:6px">Seller\'s Priority</span><div>{esc(v["priority"])}</div></div></div>')


def key_legend(offs):
    """Key for the places that show an offer's short key instead of its label (chart, timeline, flags). OFR-28: with
    several offers, the key carries the rank too ("B (#1)")."""
    rank = {o["id"]: f" (#{i + 1})" for i, o in enumerate(offs)} if len(offs) > 1 else {}
    return ('<div class="legend okey">' + "".join(
        f'<span><b>{esc(o["key"])}{rank.get(o["id"], "")}</b> {esc(o["label"])}</span>' for o in offs) + "</div>")


# --- detail tables -------------------------------------------------------------

def term_rows(o, R):
    """(label, offered, benchmark, status, note)"""
    L, S = R["listing"], R["seller"]
    rows = []
    ref = f"CMA {money(L['cma_low'])}–{money(L['cma_high'])}" if L["cma_provided"] else f"List {money(L['list_price'])}"
    exposed = o["appraisal_risk"] and o["price"] - (oe.appraisal_line(L) + o["gap_cover"]) > 0  # same line as the engine
    st = "risk" if o["price"] < L["cma_low"] else ("caution" if exposed or o["price"] < L["list_price"] else "good")
    notes = [o["escalation_note"]] if o.get("escalation") else []
    if exposed:
        notes.append("Above value range; appraisal may cut it")
    rows.append(("Price", money(o["price"]), ref, st, "; ".join(notes)))
    f = o["financing"]
    st = "good" if f == "cash" or (f == "conventional" and o["down_pct"] >= .20) else ("caution" if f in ("conventional", "va") else "risk")
    rows.append(("Financing", review.fin_str(o), "Cash or conv. ≥20% down", st, ""))
    if o["financed"]:
        ap = o["approval"]
        st = "good" if ap == "full_uw" else ("caution" if ap in ("du_approved", "preapproval") else "risk")
        rows.append(("Approval", oe.APPROVAL_LABEL.get(ap, ap), "Full underwriting", st,
                     "Verified with lender" if o.get("lender_called") else "Call the loan officer (section 8)"))
    else:
        ok = o["approval"] == "pof_verified"
        rows.append(("Proof of Funds", "Verified" if ok else "Not verified", "Verified with bank", "good" if ok else "risk", ""))
    N, est = L["norms"], "" if L["norms_source"] == "market" else " (national est.)"  # OFR-15: same norms as the counter
    dep = N["deposit_pct"] if o["financed"] else max(N["deposit_pct"], 0.05)
    if o["deposit"] is None:
        rows.append(("Escrow Deposit", "Not provided", f"≥{pctx(dep)} of price{est}", "caution", "Confirm amount and due date"))
    else:
        p = o["deposit"] / o["price"]
        rows.append(("Escrow Deposit", f"{money(o['deposit'])} ({pctx(p)})", f"≥{pctx(dep)} ({money(round(dep * o['price']))}){est}",
                     "good" if p >= dep - 1e-9 else ("caution" if p >= dep / 2 else "risk"), ""))
    c, cn = o["seller_concessions"], N["concessions_pct"]
    rows.append(("Seller Concessions", f"{money(c)} ({pctx(c / o['price'])})" if c else "$0", f"≤{pctx(cn)} of price{est}",
                 "good" if not c else ("caution" if c <= cn * o["price"] + 1 else "risk"), ""))
    ob = S["offered_buyer_broker_pct"]
    rows.append(("Buyer-Broker Comp.", f"{oe.pct(o['buyer_broker_pct'], 2)} ({money(round(o['price'] * o['buyer_broker_pct']))})",
                 f"{oe.pct(ob)} per listing agmt." if ob is not None else "Not set",
                 "caution" if ob is None else ("good" if o["buyer_broker_pct"] <= ob + 1e-9 else "risk"), ""))
    if o["home_warranty"]:
        rows.append(("Home Warranty", f"Seller pays {money(o['home_warranty'])}", "Buyer pays", "caution", ""))
    form = {"as_is": " (AS IS)", "standard": " (Standard)"}.get(o["contract_form"], "")
    rows.append(("Inspection Period", f"{o['inspection_days']} days{form}", f"≤{N['inspection_days']} days{est}",
                 "good" if o["inspection_days"] <= N["inspection_days"] else ("caution" if o["inspection_days"] <= 14 else "risk"),
                 "Buyer may cancel for any reason" if o["inspection_walkaway"] else "Repair notices only; seller pays repairs up to the limits"
                 if o["contract_form"] == "standard" else ""))
    if o["financed"]:
        la = N["loan_approval_days"]
        rows.append(("Loan Approval Period", f"{o['loan_approval_days']} days", f"≤{la} days{est}",
                     "good" if o["loan_approval_days"] <= la else ("caution" if o["loan_approval_days"] <= max(30, la) else "risk"), ""))
        if o["appraisal_days"]:
            rows.append(("Appraisal Gap Coverage", money(o["appraisal_gap"]) if o["appraisal_gap"] else "None",
                         "Covers price above value", "risk" if exposed else "good", ""))
        else:
            rows.append(("Appraisal Contingency", "Waived", "—", "good", ""))
    sc = o["sale_contingency_days"]
    rows.append(("Sale-of-Home Contingency", (f"{sc} days" + (" (kick-out)" if o["kickout"] else "")) if sc else "None", "None",
                 "risk" if sc else "good", ""))
    dl = S["deadline"]
    st = "risk" if dl and o["close"] > dl else ("caution" if o["close"].weekday() >= 5 else "good")
    rows.append(("Closing Date", f"{o['close']:%a %b %-d} ({o['close_days']} days)", f"On/before {dl:%b %-d}" if dl else "—", st,
                 "Weekend date; confirm funding" if o["close"].weekday() >= 5 else ""))
    tb, cust = o["title_by"], L["title_customary_payer"]
    if tb or cust:
        name = {"seller": "Seller's title co.", "buyer": "Buyer's title co."}
        rows.append(("Escrow / Title Agent", name.get(tb, "—"), name.get(cust, "—"), "good" if tb == cust else "caution", ""))
    for key, lab in (("personal_property", "Personal Property"), ("occupancy", "Occupancy"), ("other_terms", "Other Terms")):
        if o.get(key):
            rows.append((lab, esc(o[key]), "—", "caution", ""))
    if o.get("riders"):
        form = {"as_is": "AS IS · ", "standard": "Standard · "}.get(o["contract_form"], "")
        rows.append(("Contract / Riders", form + esc(", ".join(o["riders"])), "—", "good", ""))
    return rows


def questions(o, R):
    """Only what the contract, the counter and the loan officer can't answer. Terms the counter sets (price, gap,
    concessions, deposit, inspection, closing) aren't asked: sending the counter asks them."""
    L = R["listing"]
    Q = [f["request"] for f in o["flags"] if f.get("contract") and f.get("request")]  # contract fixes come first
    if o["financed"] and o.get("insurance_quote") is not True:
        roof = f", given the {L['roof_year']} roof?" if L.get("roof_year") else "?"
        Q.append("Has the buyer obtained a homeowners insurance quote for this address" + roof)
    if o["sale_contingency_days"]:
        Q.append("Is the buyer's current home listed or under contract? At what price?")
    if o["financed"] and o["approval"] in ("prequal", "none"):
        Q.append("When can the buyer provide a full pre-approval?")
    if o["financed"] and not o.get("lender_called"):
        Q.append("Who is the loan officer, so we can verify the approval directly?")
    if o.get("escalation"):
        Q.append("What proof of a competing offer does the escalation clause require?")
    return Q


def lender_questions(o, R):
    """The call before responding: what the letter can't show. At most five, asked the same way of every buyer's lender or bank."""
    L = R["listing"]
    if not o["financed"]:
        return ["Is the account in the name of the buyer (or the entity signing the contract)?",
                f"Are funds for {money(o['price'])} plus closing costs available now, not waiting on a sale, loan or transfer?",
                "Can the bank confirm the balance in writing to the escrow agent?"]
    fin = oe.FIN_LABEL[o["financing"]]
    fin = fin if fin.isupper() else fin.lower()  # "an FHA loan", "a conventional loan"
    Q = ["What conditions are left on the underwriting approval?" if o["approval"] == "full_uw" else
         "Has the file been through automated underwriting (DU or LP), and are income, assets and credit verified with documents?"]
    conc = f", with {money(o['seller_concessions'])} in seller concessions" if o["seller_concessions"] else ""
    Q.append(f"Is the approval good for {money(o['price'])} with {o['down_pct'] * 100:.1f}% down on "
             f"{'an' if fin[0] in 'AEFHILMNORSX' else 'a'} {fin} loan{conc}?")
    gap = max(o["appraisal_gap"], o["counter_terms"]["appraisal_gap"] if o.get("action") == "COUNTER" else 0)
    Q.append("Are funds verified for the down payment and closing costs"
             + (f", plus an appraisal gap of up to {money(gap)}?" if gap else "?"))
    if o["financing"] in ("fha", "va", "usda"):
        roof = f" (roof {L['roof_year']})" if L.get("roof_year") else ""
        Q.append(f"Any concern about the property meeting {fin} appraisal and condition rules{roof}?")
    if o["close"].weekday() >= 5:
        Q.append(f"The contract closes {o['close']:%a %b %-d}; can you close {oe.prior_weekday(o['close']):%a %b %-d} instead?")
    else:
        Q.append(f"Can you close by {o['close']:%a %b %-d} with your current workload?")
    return Q


def checklist(o):
    C = o.get("checklist") or {}
    found = {}  # contract problems noted on the matching line ("signed", "riders", "terms")
    for f in o["flags"]:
        if f.get("contract"):
            found.setdefault(f["check"], []).append(f["issue"].rstrip("."))
    fin = o["financed"]
    items = [("signed", "All parties signed & initialed; dates filled", "Pending"),
             ("lender", "Loan officer called (questions in section 8)" if fin else "Proof of funds confirmed with the bank (questions in section 8)",
              "Yes" if o.get("lender_called") or (not fin and o["approval"] == "pof_verified") else "No"),
             ("deposit", "Deposit amount, due date & escrow agent confirmed", "Pending"),
             ("riders", "All riders attached and consistent", "Pending"),
             ("insurance", "Buyer has insurance quote on this address", "N/A" if not fin else ({True: "Yes", False: "No"}.get(o.get("insurance_quote"), "Unknown"))),
             ("bb", "Buyer-broker compensation request reviewed with seller", "Pending"),
             ("net", "Seller's net sheet reviewed with seller", "Pending")]
    out = []
    for k, lab, dflt in items:
        v = C.get(k, dflt)
        v, note = (v.get("status", dflt), v.get("note", "")) if isinstance(v, dict) else (v, "")
        note = "; ".join([note] * bool(note) + found.get(k, []))
        if v != "N/A":
            out.append((lab, v, note))
    return out


def checkbox(v):
    """The report is printed once: a box to tick by hand, already ticked when the file says it's done."""
    return '<span class="cb on">✓</span>' if v == "Yes" else '<span class="cb"></span>'

def assumptions_table(R, multi=False):
    """Every assumption; in the comparison, only the listing's and each offer's high-impact ones (the rest are in the single reviews)."""
    items = [a for a in R["missing"] if not multi or not a["scope"].startswith("offer ") or a["impact"] == "high"]
    if not items:
        return '<p class="sm">No assumptions: every key input was provided.</p>'
    lab = {"high": "High", "med": "Med", "low": "Low"}
    rows = "".join(f'<tr><td class="c"><span class="pill {a["impact"]}">{lab[a["impact"]]}</span></td><td>{esc(review.where(R, a["scope"]))}</td>'
                   f'<td>{esc(a["why"])}</td></tr>' for a in items)
    return ('<div class="tbl"><table><colgroup><col style="width:9%"><col style="width:20%"></colgroup><thead><tr><th class="c">Impact</th>'
            f'<th>Where</th><th>What Was Assumed: Provide the Real Value to Sharpen the Analysis</th></tr></thead><tbody>{rows}</tbody></table></div>')


def gantt(o, R):
    S, L = R["seller"], R["listing"]
    dl = (S["deadline"] - L["analysis_date"]).days if S["deadline"] else 0
    span = max(o["close_days"], dl, o["risk_days"]) + 5
    step = max(1, math.ceil(span / 56))
    ncell = math.ceil(span / step)
    per_wk = max(1, 7 // step)
    hdr = '<tr><th style="width:22%">Contingency</th><th class="n" style="width:6%">Days</th><th class="n" style="width:9%">Ends</th>'
    for i in range(0, ncell, per_wk):
        hdr += f'<th colspan="{min(per_wk, ncell - i)}" class="c">{(L["analysis_date"] + timedelta(days=i * step)):%b %-d}</th>'
    hdr += "</tr>"

    def gx(i):
        c = "wk " if i % per_wk == 0 else ""
        if dl and i == (dl - 1) // step:
            c += "dl"
        return c

    def line(name, d, kind):
        if not d:
            return f'<tr><td>{name}</td><td class="n">—</td><td class="n">—</td>' + "".join(f'<td class="gantt {gx(i)}"></td>' for i in range(ncell)) + "</tr>"
        cells = "".join(f'<td class="gantt {gx(i)} {"on-" + kind if i * step < d else ""}"><div></div></td>' for i in range(ncell))
        return f'<tr><td>{name}</td><td class="n">{d}</td><td class="n">{(L["analysis_date"] + timedelta(days=d)):%b %-d}</td>{cells}</tr>'

    body = line("Inspection (Right to Cancel)" if o["inspection_walkaway"] else "Inspection (Repair Notices)", o["inspection_days"],
                "hot" if o["inspection_walkaway"] else "warm")
    if o["financed"]:
        body += line("Appraisal", o["appraisal_days"], "warm") + line("Loan Approval", o["loan_approval_days"], "warm")
    body += line("Sale of Buyer's Home", o["sale_contingency_days"], "hot")
    ci = (o["close_days"] - 1) // step
    dtxt = f" <span class=sm>(Deadline {S['deadline']:%b %-d})</span>" if S["deadline"] else ""
    body += (f'<tr><td><b>Closing</b>{dtxt}</td><td class="n">{o["close_days"]}</td><td class="n">{o["close"]:%b %-d}</td>'
             + "".join(f'<td class="gantt {gx(i)} {"on-close" if i == ci else ""}"><div></div></td>' for i in range(ncell)) + "</tr>")
    legend = ('<div class="legend"><span><i class="hot"></i>Cancel for Any Reason</span><span><i class="warm"></i>Cancel if Financing/Appraisal Fails</span>'
              '<span><i class="closei"></i>Closing</span>' + ('<span><i class="dl"></i>Seller Deadline</span>' if dl else "")
              + f'<span>Firm after day <b>{o["risk_days"]}</b> ({o["firm_date"]:%b %-d}).</span></div>')
    return f'<div class="tbl"><table style="table-layout:fixed"><thead>{hdr}</thead><tbody>{body}</tbody></table></div>{legend}'


def scorecard_single(o):
    rows = ""
    for k, lab, w in oe.CRITERIA:
        s = o["score"]["scores"][k]
        src = "" if o["score"]["src"][k] == "auto" else ' <span class="pill vyes">Agent</span>'
        rows += f'<tr><td>{lab}</td><td class="n">{w}%</td><td class="c s{s}">{s}</td><td>{esc(o["score"]["why"][k])}{src}</td></tr>'
    b = o["score"]["band"]
    t = {"hi": "hit", "mid": "midt", "lo": "lot"}[b[0]]
    rows += (f'<tr class="total"><td>Certainty Score</td><td class="n">100%</td><td class="c {t}"><b>{o["score"]["total"]}</b></td>'
             f'<td class="{t}"><b>{b[1]}</b> · 80+ strong · 60–79 workable · under 60 weak</td></tr>')
    return ('<div class="tbl"><table><colgroup><col style="width:28%"><col style="width:8%"><col style="width:7%"></colgroup>'
            f'<thead><tr><th>Criterion</th><th class="n">Weight</th><th class="c">Score</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>'
            '<div class="legend"><span>Scores are drafted automatically from the contract; <span class="pill vyes">Agent</span> marks scores the agent set.</span></div>')


def netsheet_body(cols, hl=0):
    body = ""
    for r in review.net_sheet_rows(cols):
        body += f"<tr><td>{esc(r['label'])}</td>" + "".join(
            f'<td class="n {"hl" if j == hl else ""} {"neg" if v < 0 else ""}">{acct(v)}</td>' for j, v in enumerate(r["values"])) + "</tr>"
    body += '<tr class="total"><td>Estimated Net Proceeds</td>' + "".join(f'<td class="n">{acct(c["net"])}</td>' for _, c in cols) + "</tr>"
    body += '<tr><td>Holding Costs Until Closing</td>' + "".join(f'<td class="n neg">{acct(c["holding"])}</td>' for _, c in cols) + "</tr>"
    return body


# --- single offer --------------------------------------------------------------

def single_html(R, o, v):
    L = R["listing"]
    tgt = o["target"]["net_adj"]
    act = v["action"]
    if v["counter"]:
        ck = "".join(f'<tr><td><b>{esc(r["term"])}</b></td><td class="was">{esc(r["offered"])}</td><td class="arr">→</td>'
                     f'<td class="now">{esc(r["counter"])}</td><td class="why2">{esc(r["why"])}</td></tr>' for r in v["counter"]["rows"])
        box = (f'<div class="ctr"><div class="ctrh"><span>OUR COUNTER</span><em>{md(v["counter"]["summary"])}</em></div>'
               '<table><colgroup><col style="width:18%"><col style="width:15%"><col style="width:3%"><col style="width:17%"><col></colgroup>'
               f'<thead><tr><th>Term</th><th>Buyer Offered</th><th></th><th>We Counter</th><th>Why</th></tr></thead><tbody>{ck}</tbody></table></div>')
    elif act == "INCOMPLETE":
        rows = "".join(f'<tr><td class="c"><span class="cb"></span></td><td><span class="pill {f["sev"].lower()}">{f["sev"]}</span> '
                       f'<b>{esc(f["issue"])}</b></td><td class="why2">{esc(f["fix"])}</td></tr>' for f in v["fixes"])
        box = ('<div class="ctr stop"><div class="ctrh"><span>FIX BEFORE REVIEW</span><em>No recommendation until the contract is corrected</em></div>'
               '<table><colgroup><col style="width:5%"><col style="width:50%"></colgroup>'
               f'<thead><tr><th></th><th>Issue</th><th>How to Fix</th></tr></thead><tbody>{rows}</tbody></table></div>')
    elif act == "ACCEPT":
        keys = [r for r in term_rows(o, R) if r[0] in ("Price", "Financing", "Escrow Deposit", "Seller Concessions", "Inspection Period", "Closing Date")]
        rows = "".join(f'<tr><td><b>{t}</b></td><td class="now">{val}</td><td class="why2">{b}</td></tr>' for t, val, b, _, _ in keys)
        box = (f'<div class="ctr"><div class="ctrh"><span>ACCEPT AS WRITTEN</span><em>Net After Holding <b>{money(o["ns"]["net_adj"])}</b></em></div>'
               f'<table><tbody>{rows}</tbody></table></div>')
    elif v["compare"]:
        c = v["compare"]
        rows = "".join(f'<tr><td><b>{a}</b></td><td>{b}</td><td class="now">{d}</td></tr>' for a, b, d in c["rows"])
        box = (f'<div class="ctr cmp"><div class="ctrh"><span>HOW IT COMPARES</span><em>vs. {esc(c["vs"])} (Recommended)</em></div>'
               f'<table><thead><tr><th>Measure</th><th>{esc(c["this"])}</th><th>{esc(c["vs"])}</th></tr></thead><tbody>{rows}</tbody></table></div>')
    else:
        box = ""
    kp = "".join(f'<div class="{"kgood" if k["tone"] == "good" and "counter" in k["label"].lower() else ""}"><span>{esc(k["label"])}</span>'
                 f'<b class="{k["tone"] if k["tone"] in ("brand", "good") and k is not v["kpis"][1] else ""}">{esc(k["value"])}</b>'
                 f'<i class="{k["tone"] if k["tone"] in ("good", "risk") else ""}">{esc(k["note"])}</i></div>' for k in v["kpis"])
    risks = "".join(f'<tr><td class="c"><span class="pill {r["sev"].lower()}">{r["sev"]}</span></td><td>{esc(r["issue"])}</td></tr>'
                    for r in v["risks"]) or "<tr><td>No significant risks found.</td></tr>"
    page1 = (f'{hero(v)}{box}<div class="kpis">{kp}</div>'
             f'<div class="two">{certainty_panel(v["certainty"])}<div><h2>Top Risks in the Offer as Written</h2>'
             f'<div class="tbl"><table><colgroup><col style="width:17%"></colgroup><tbody>{risks}</tbody></table></div></div></div>'
             f'{options_table(v["options"])}{closing_block(v)}')

    cols = [("As Offered", o["ns"]), ("Downside Case", o["ns_down"])]
    if o["counter_rows"]:
        cols.append(("Proposed Counter", o["ns_counter"]))
    target_label = "Seller's Target"
    cols.append((target_label, o["target"]))
    ns = netsheet_body(cols)
    ns += '<tr class="total2"><td>Net After Holding Costs</td>' + "".join(
        f'<td class="n {"best" if c["net_adj"] >= tgt else ("worst" if c["net_adj"] < tgt - 5000 else "")}">{acct(c["net_adj"])}</td>' for _, c in cols) + "</tr>"
    ns += "<tr class=\"alt\"><td>vs. Seller's Target Net</td>" + "".join(
        f'<td class="n">{"—" if n == target_label else signed(c["net_adj"] - tgt)}</td>' for n, c in cols) + "</tr>"
    ref = f"the top of the value range ({money(round(oe.appraisal_line(L)))})" if L["cma_provided"] else "list price"
    who = " · ".join(esc(x) for x in (o["buyer"], o.get("buyer_agent")) if x)
    tr = (f'<tr><td>Buyer / Agent</td><td colspan="4">{who}</td></tr>' if who else "") + "".join(
        f'<tr><td>{t}</td><td class="{st}">{val}</td><td>{b}</td><td class="c"><span class="pill {PILL[st]}">{RATING[st]}</span></td>'
        f'<td class="sm" style="color:var(--text)">{esc(n)}</td></tr>' for t, val, b, st, n in term_rows(o, R))
    fl = "".join(f'<tr><td class="c"><span class="pill {f["sev"].lower()}">{f["sev"]}</span></td><td>{esc(f["issue"])}</td><td>{esc(f["fix"])}</td></tr>'
                 for f in o["flags"]) or '<tr><td colspan="3">No significant risks found.</td></tr>'
    vf = "".join(f'<tr><td class="c">{checkbox(b)}</td><td>{esc(a)}</td><td class="sm" style="color:var(--text)">{esc(c)}</td></tr>'
                 for a, b, c in checklist(o))
    lq = "".join(f"<tr><td>{i + 1}</td><td>{esc(q)}</td></tr>" for i, q in enumerate(lender_questions(o, R)))
    qs = "".join(f"<tr><td>{i + 1}</td><td>{esc(q)}</td></tr>" for i, q in enumerate(questions(o, R))) or f'<tr><td></td><td>None: the contract{" and the counter" if v["counter"] else ""} cover{"" if v["counter"] else "s"} it.</td></tr>'
    gap = f" with {money(o['appraisal_gap'])} gap coverage" if o["appraisal_gap"] else ""
    credit = f" + {money(o['repair_reserve'])} inspection credit" if o["repair_reserve"] else ""
    heads = "".join(f'<th class="n {"hl" if i == 0 else ""}">{n}</th>' for i, (n, _) in enumerate(cols))
    details = f'''<div class="pb"></div><div class="dh">Detailed Analysis</div>
<h2>1 · Seller Net Sheet <span class="h2s">As Offered vs. Downside{", Counter" if o["counter_rows"] else ""} and the Seller's Target Terms</span></h2>
<div class="tbl"><table><colgroup><col style="width:{36 if len(cols) <= 4 else 30}%"></colgroup><thead><tr><th>Line Item</th>{heads}</tr></thead><tbody>{ns}</tbody></table></div>
<div class="legend"><span><b>Downside</b>: appraisal at {ref}{gap}{credit}.</span>
<span><b>Seller's Target</b>: list price, no concessions, agreed buyer-broker comp., same closing date.</span></div>
<h2>2 · Contingency Timeline <span class="h2s">Shaded = Buyer Can Still Cancel · Days from {L["analysis_date"]:%b %-d}</span></h2>{gantt(o, R)}
<h2 class="pb">3 · Terms Review <span class="h2s">Each Term Against the Seller's Preference or Local Norm</span></h2>
<div class="tbl"><table><colgroup><col style="width:17%"><col style="width:23%"><col style="width:20%"><col style="width:9%"></colgroup>
<thead><tr><th>Term</th><th>Offered</th><th>Benchmark</th><th class="c">Rating</th><th>Note</th></tr></thead><tbody>{tr}</tbody></table></div>
<h2>4 · Certainty Scorecard <span class="h2s">1 = Weak · 5 = Strong · Weighted</span></h2>{scorecard_single(o)}
<h2 class="pb">5 · Risk Flags</h2><div class="tbl"><table><colgroup><col style="width:8%"><col style="width:50%"></colgroup>
<thead><tr><th class="c">Level</th><th>Issue</th><th>Mitigation</th></tr></thead><tbody>{fl}</tbody></table></div>
<h2>6 · Verification Checklist</h2><div class="tbl"><table class="ck"><colgroup><col style="width:5%"><col style="width:45%"></colgroup>
<thead><tr><th class="c">Done</th><th>Item</th><th>Notes</th></tr></thead><tbody>{vf}</tbody></table></div>
<div class="two" style="margin-top:0">
 <div><h2>7 · Questions for the Buyer's Agent</h2><div class="tbl"><table class="qs"><colgroup><col style="width:7%"></colgroup>
 <thead><tr><th class="c">#</th><th>Question</th></tr></thead><tbody>{qs}</tbody></table></div></div>
 <div><h2>8 · Questions for the {"Loan Officer" if o["financed"] else "Bank"}</h2><div class="tbl"><table class="qs"><colgroup><col style="width:7%"></colgroup>
 <thead><tr><th class="c">#</th><th>Question</th></tr></thead><tbody>{lq}</tbody></table></div></div></div>
<h2>9 · Assumptions &amp; Data to Confirm</h2>{assumptions_table(R)}
{fine(R)}'''
    sub = f"{esc(L.get('address') or '')} · List {money(L['list_price'])} · Offer from {esc(o['label'])}"
    snap = snapshot(R)
    return "Single Offer Review", sub, snap + f'<div class="p1">{page1}</div>' + details


# --- multiple offers -----------------------------------------------------------

def scatter(R, W=300, H=230):
    offs = R["active"]
    vals = [x for o in offs for x in (o["ns"]["net_adj"], o["ns_down"]["net_adj"])] + [R["target"]["net_adj"]]
    lo, hi = min(vals), max(vals)
    pad = max(2000, (hi - lo) * .12)
    step = 5000 if hi - lo < 40000 else 10000 if hi - lo < 90000 else 25000
    y0, y1 = math.floor((lo - pad) / step) * step, math.ceil((hi + pad) / step) * step
    xmin = max(0, min(40, (min(o["score"]["total"] for o in offs) // 10) * 10))
    Lm, Rm, T, B = 42, 10, 10, 28

    def xs(val):
        return Lm + (val - xmin) / (100 - xmin) * (W - Lm - Rm)

    def ys(val):
        return T + (1 - (val - y0) / (y1 - y0)) * (H - T - B)

    tgt = R["target"]["net_adj"]
    col = {"ACCEPT": "var(--good-base)", "COUNTER": "var(--good-base)", "BACKUP": "var(--caution-base)", "DECLINE": "var(--risk-base)"}
    ink = {k: v.replace("-base)", "-strong)") for k, v in col.items()}  # DS-4: the base colors are for marks, never text
    svg = [f'<svg viewBox="0 0 {W} {H}" class="scat">',
           f'<rect x="{xs(70)}" y="{ys(y1)}" width="{xs(100) - xs(70)}" height="{max(0, ys(tgt - (y1 - y0) * .1) - ys(y1))}" fill="var(--good-base)" opacity=".07"/>',
           f'<text x="{xs(99)}" y="{ys(y1) + 10}" text-anchor="end" class="q">Sweet Spot</text>']
    val = y0
    while val <= y1:
        svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{ys(val)}" y2="{ys(val)}" class="gl"/>'
                   f'<text x="{Lm - 4}" y="{ys(val) + 3}" text-anchor="end" class="ax">${val // 1000:,.0f}K</text>')
        val += step
    for x in range(int(xmin), 101, 10):
        svg.append(f'<text x="{xs(x)}" y="{H - B + 12}" text-anchor="middle" class="ax">{x}</text>')
    svg.append(f'<text x="{(Lm + W - Rm) / 2}" y="{H - 3}" text-anchor="middle" class="ax">Certainty Score →</text>')
    svg.append(f'<line x1="{Lm}" x2="{W - Rm}" y1="{ys(tgt)}" y2="{ys(tgt)}" stroke="var(--good-base)" stroke-dasharray="4 3"/>'
               f'<text x="{Lm + 3}" y="{ys(tgt) - 3}" class="ax" style="fill:var(--good-strong)">Target {money(tgt)} (Clean Offer at List)</text>')
    rank = {r["id"]: i + 1 for i, r in enumerate(R["ranked"])}
    for o in offs:
        c = col[o["action"]]
        x, a, b = xs(o["score"]["total"]), ys(o["ns"]["net_adj"]), ys(o["ns_down"]["net_adj"])
        right = o["score"]["total"] > 90
        svg.append(f'<line x1="{x}" x2="{x}" y1="{a}" y2="{b}" stroke="{c}" stroke-width="2" opacity=".5"/>'
                   f'<circle cx="{x}" cy="{a}" r="5" fill="#fff" stroke="{c}" stroke-width="2"/><circle cx="{x}" cy="{b}" r="5" fill="{c}"/>'
                   f'<text x="{x - 9 if right else x + 9}" y="{(a + b) / 2 + 4}" text-anchor="{"end" if right else "start"}" class="pl" style="fill:{ink[o["action"]]}">{esc(o["key"])} #{rank.get(o["id"], "")}</text>')
    svg.append("</svg>")
    return "".join(svg)


STATUS_WORD = {"caution": "Watch", "risk": "Weak"}
CHART_MAX = 6  # past this many offers the chart crowds; the decision table stands alone
KEY_TERMS = [("Financing", ("Financing",)), ("Approval / Funds", ("Approval", "Proof of Funds")), ("Deposit", ("Escrow Deposit",)),
             ("Concessions", ("Seller Concessions",)), ("Inspection", ("Inspection Period",)),
             ("Appraisal Gap", ("Appraisal Gap Coverage", "Appraisal Contingency")), ("Sale of Home", ("Sale-of-Home Contingency",)),
             ("Closing", ("Closing Date",))]


def multi_html(R, v):
    """The decision summary: one row per offer, so it reads the same with 2 offers or 12. Detail lives in each single review."""
    L = R["listing"]
    rk = R["ranked"]
    top = rk[0]
    band = {"hi": "hit", "mid": "midt", "lo": "lot", "na": ""}
    pill = {"Accept": "rec", "Counter": "rec", "Hold as Backup": "med", "Decline": "high", "Incomplete": "blocking"}
    rows = "".join(
        f'<tr class="{"top" if r["rank"] == 1 else ""}"><td class="rk">{r["rank"]}</td><td class="nw"><b>{esc(r["key"])}</b> · <b>{esc(r["offer"])}</b></td>'
        f'<td>{esc(r["financing"])}</td><td class="c"><span class="pill {pill[r["action"]]}">{esc(r["action"])}</span></td>'
        f'<td class="n">{r["price"]}</td><td class="n">{r["net"]}</td><td class="n"><b>{r["downside"]}</b></td>'
        f'<td class="c {band[r["band_class"]]}"><b>{r["score"]}</b></td><td class="n">{r["risk_days"]}{"" if r["risk_days"] == "—" else " d"}</td><td class="n">{r["close"]}</td>'
        f'<td class="why2">{esc(r["terms"])}</td></tr>' for r in v["ranked"])
    decision = f'''<div class="ctr"><div class="ctrh"><span>OUR PLAN</span><em>{md(v["plan_summary"])}</em></div>
 <table class="rank"><colgroup><col style="width:3%"><col style="width:19%"><col style="width:10%"><col style="width:9%"><col style="width:6.5%"><col style="width:6.5%"><col style="width:7%"><col style="width:4%"><col style="width:4%"><col style="width:5%"></colgroup>
 <thead><tr><th></th><th>Offer</th><th>Financing</th><th class="c">Action</th><th class="n">Price</th><th class="n">Net</th><th class="n">Downside</th><th class="c">Cert.</th><th class="n">Walk</th><th class="n">Close</th><th>Terms / Reason</th></tr></thead><tbody>{rows}</tbody></table>
 <div class="note"><b>Net</b> = after all costs &amp; holding, as offered. <b>Downside</b> = if the appraisal and inspection go badly. <b>Walk</b> = days the buyer can still walk away. {esc(v["plan_note"])}</div></div>'''
    if len(R["active"]) <= CHART_MAX:
        chart = (f'<div><h2>Net vs. Certainty</h2><div class="panel">{scatter(R, 420, 200)}<div class="legend" style="margin:0">'
                 '<span><i style="background:#fff;border:1.5px solid var(--grey);border-radius:50%"></i>As Offered</span>'
                 f'<span><i style="background:var(--grey);border-radius:50%"></i>Downside</span></div>{key_legend(rk)}</div></div>')
        lower = f'<div class="two" style="grid-template-columns:1.35fr 1fr"><div>{options_table(v["options"], (26, 13, 11))}</div>{chart}</div>'
    else:
        lower = options_table(v["options"], (28, 12, 10))
    page1 = f"{hero(v)}{decision}{lower}{closing_block(v)}"

    head = "".join(f"<th>{lab}</th>" for lab, _ in KEY_TERMS)
    body = ""
    for o in rk + R["incomplete"]:  # incomplete contracts: their terms as written, not ranked
        t = {r[0]: r for r in term_rows(o, R)}
        cells = ""
        for _, keys in KEY_TERMS:
            hit = next((t[k] for k in keys if k in t), None)
            word = STATUS_WORD.get(hit[3], "") if hit else ""  # OFR-28: the status in words, not only by color
            cells += (f'<td class="{hit[3]}">{hit[1]}' + (f' <span class="sm">({word})</span>' if word else "") + "</td>") if hit else "<td>—</td>"
        risk = o["flags"][0] if o["flags"] else None
        risk = (f'<span class="pill {risk["sev"].lower()}">{risk["sev"]}</span> {esc(risk["issue"])}' if risk else "None major")
        body += f'<tr><td><b>{esc(o["key"])}</b> · <b>{esc(o["label"])}</b></td>{cells}<td class="sm" style="color:var(--text)">{risk}</td></tr>'
    ctr = ""
    if v["action"] == "COUNTER" and top["counter_rows"]:
        ctr = (f'<h2>Counter to {esc(top["label"])} <span class="h2s">Full Terms</span></h2><div class="tbl"><table><colgroup><col style="width:20%"><col style="width:17%"><col style="width:17%"></colgroup>'
               '<thead><tr><th>Term</th><th>Offered</th><th>Counter</th><th>Why</th></tr></thead><tbody>'
               + "".join(f'<tr><td>{esc(a)}</td><td>{esc(b)}</td><td class="good"><b>{esc(c)}</b></td><td>{esc(d)}</td></tr>' for a, b, c, d in top["counter_rows"])
               + "</tbody></table></div>")
    details = f'''<div class="pb"></div><div class="dh">Key Terms Side by Side</div>
{snapshot(R)}
<h2>Key Terms <span class="h2s">Favorable · Watch · Weak</span></h2>
<div class="tbl"><table class="kt"><colgroup><col style="width:12%"><col style="width:9%"><col style="width:10%"><col style="width:8%"><col style="width:8%"><col style="width:8%"><col style="width:7%"><col style="width:8%"><col style="width:9%"></colgroup><thead><tr><th>Offer</th>{head}<th>Biggest Risk</th></tr></thead><tbody>{body}</tbody></table></div>
<div class="legend"><span>Each offer's single review has its full net sheet, contingency timeline, terms review, certainty scorecard, risk flags and checklist.</span></div>
{ctr}
<h2>Assumptions &amp; Data to Confirm</h2>{assumptions_table(R, multi=True)}
{fine(R)}'''
    sub = f"{esc(L.get('address') or '')} · List {money(L['list_price'])} · {v['offers_active']} active offers"
    return "Multiple Offer Review", sub, f'<div class="p1">{page1}</div>' + details


# --- document ------------------------------------------------------------------

def build_html(R, agent, sample=False, mode="auto", offer_id=None):
    mode, o = review.pick(R, mode, offer_id)
    v = review.single_view(R, o) if mode == "single" else review.multi_view(R)
    title, sub, body = single_html(R, o, v) if mode == "single" else multi_html(R, v)
    theme = design.theme(agent.get("brand"), "seller")
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    if mode == "multi":
        css += "@page{size:Letter landscape}"  # the comparison is two wide tables; after report.css's portrait rule
    doc = render.page(header(R, title, sub, agent, sample) + body + render.notices(agent), css=css, title=title, theme_css=design.css_vars(theme),
                      body_class="wide" if mode == "multi" else "")
    return doc, mode, o


def fit_page_one(pg, limit=PAGE1_LIMIT):
    """Measure page 1; switch to the compact layout when it would spill onto page 2."""
    top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > limit:
        pg.evaluate("() => document.body.classList.add('compact')")
        top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    return top


def write_pdf(R, agent, sample, mode, offer_id, out_dir):
    doc, mode, o = build_html(R, agent, sample, mode, offer_id)
    street = (R["listing"].get("address") or "Listing").split(",")[0]
    name = render.filename(street, f"{o['label']} Offer Review" if mode == "single" else "Multiple Offer Review", ext="pdf")
    path = os.path.join(out_dir, name)
    label = f"Single Offer Review · Seller Side · {street} · {o['label']}" if mode == "single" else f"Multiple Offer Review · Seller Side · {street}"
    limit = PAGE1_LIMIT_WIDE if mode == "multi" else PAGE1_LIMIT
    top = render.html_to_pdf(doc, path, footer_html=render.footer(label), landscape=mode == "multi",
                             before_print=lambda pg: fit_page_one(pg, limit))
    if top > limit:
        print(f"{name}: page 1 overflows by {top - limit:.0f}px; shorten the counter notes or custom flags.", file=sys.stderr)
    return path


def build(data, fmt, out_dir, ctx):
    """One PDF; with --packet and 2+ active offers, the comparison plus a single review of each active offer, in rank order."""
    R = review.analyze(data, ctx.get("market"), review.load_cma(data, ctx.get("cma")))
    sample = ctx.get("sample") or R["sample"]
    if ctx.get("packet") and len(R["active"]) >= 2:
        paths = [write_pdf(R, ctx["agent"], sample, "multi", None, out_dir)]
        paths += [write_pdf(R, ctx["agent"], sample, "single", o["id"], out_dir) for o in R["ranked"]]
    else:
        paths = [write_pdf(R, ctx["agent"], sample, ctx.get("mode") or "auto", ctx.get("offer"), out_dir)]
    for a in R["missing"][:6]:
        print(f"Assumed [{a['impact']}] {a['why']}", file=sys.stderr)
    return paths


def options(ap):
    ap.add_argument("--cma", help="cma-handoff v1 file (.cma.json or markdown with the block)")
    ap.add_argument("--mode", choices=["auto", "single", "multi"], default="auto")
    ap.add_argument("--offer", help="offer id for a single review while others are active")
    ap.add_argument("--packet", action="store_true", help="with 2+ offers: the comparison plus a single review of every active offer")


def main(argv=None):
    return render.main(build, formats=("pdf",), argv=argv, extra_args=options, errors=(oe.OfferError, handoff.HandoffError))


if __name__ == "__main__":
    main(sys.argv[1:])
