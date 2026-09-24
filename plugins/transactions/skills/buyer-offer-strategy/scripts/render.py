"""Buyer offer PDFs: the Offer Options report (for the buyer) and the Offer Package Worksheet (for the agent).

    python3 scripts/render.py buyer.json [--format options|worksheet|all] [--cma file.cma.json] [--option recommended|stronger|lower_cost]
                              [--agent agent-profile.md] [--market market-profile.md] [--sample] [--out DIR]

Options report, page 1: the recommended offer with a reason for every term, the alternatives, the outlook at
four competition levels and the buyer's cash exposure; the pages after it hold the detail.
Worksheet: contract entries, riders with suggested inputs, draft additional terms and the package checklist
for the chosen option. It prints offer terms only, never the buyer's max, cash or reserve.
Colors follow the agent's buyer-side brand color.
"""
import html
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import strategy as ST  # noqa: E402
from _shared import design, handoff, offer_engine as oe, profiles, render  # noqa: E402

esc = html.escape
money = oe.money
HERE = os.path.dirname(os.path.abspath(__file__))
CSS = {"options": os.path.join(HERE, "..", "assets", "offer-options.css"), "worksheet": os.path.join(HERE, "..", "assets", "worksheet.css")}
PAGE1_LIMIT = 989  # px available on page 1 at the print viewport


def md(text):
    """Escape, then **bold** -> <b> and [blank] -> red fill-in."""
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc(text or ""))
    return re.sub(r"\[([^\]]+)\]", r'<span class="fill">[\1]</span>', out)


def acct(v):
    return money(v) if v >= 0 else f"({money(-v)})"


def css(kind):
    with open(CSS[kind], encoding="utf-8") as f:
        return f.read()


def agent_lines(agent):
    if not agent.get("name"):
        return ""
    out = f'<br><b>{esc(agent["name"])}</b>'
    org = " · ".join(esc(str(agent[f])) for f in ("team", "brokerage") if agent.get(f))
    lic = f'Lic. {esc(str(agent["license"]))}' if agent.get("license") else ""
    if org or lic:
        out += "<br>" + " · ".join(x for x in (org, lic) if x)
    return out


def header(title, sub, prep, sample):
    tag = '<span class="viewtag">Buyer Side</span>' + ('<span class="sample">SAMPLE DATA</span>' if sample else "")
    return f'<header><div><div class="t1">{title}{tag}</div><div class="t2">{sub}</div></div><div class="prep">{prep}</div></header>'


def band_pill(b):
    return f'<span class="pill b-{b["class"]}">{esc(b["band"])}</span>'


# --- Offer Options report --------------------------------------------------------

def snapshot(r):
    """Home facts in a divider row, then the market and deadline strip: one value per cell."""
    B = r["B"]
    P, M, C = B["property"], B["market"], B["competition"]
    facts = [f"{P['beds']} bed" if P.get("beds") else None, f"{P['baths']} bath" if P.get("baths") else None,
             f"{P['sqft']:,} sq ft" if P.get("sqft") else None, f"built {P['year_built']}" if P.get("year_built") else None,
             f"roof {P['roof_year']}" if P.get("roof_year") else None]
    facts = [x for x in facts if x]
    row = f'<div class="divrow factrow"><div>{"".join(f"<span>{esc(x)}</span>" for x in facts)}</div></div>' if facts else ""
    cells = [("Sale-to-List", f"{M['sale_to_list'] * 100:.1f}%" if M.get("sale_to_list") else None),
             ("Months Supply", M.get("months_supply")), ("Days on Market", P.get("dom")),
             ("Median DOM", M.get("median_dom")), ("Offers Due", esc(C["deadline"]) if C.get("deadline") else None)]
    cells = [(a, b) for a, b in cells if b is not None and b != ""]  # missing values drop out rather than show a dash
    if not cells:
        return row
    cols = " ".join("1.6fr" if a == "Offers Due" else "1fr" for a, _ in cells)
    return (row + f'<div class="snap" style="grid-template-columns:{cols}">'
            + "".join(f"<div><span>{a}</span><b>{b}</b></div>" for a, b in cells) + "</div>")


def value_note(V):
    """Second line under the offer price: the value range it sits in."""
    if V.get("assumed"):
        return '<small>Value range not provided</small>'
    return f'<small>Value range ${V["cma_low"] / 1000:,.0f}K–${V["cma_high"] / 1000:,.0f}K</small>'


def page1(r, s):
    labels = s["option_labels"]
    hero = (f'<div class="hero"><div class="hl"><span class="k">Recommended Offer · Outlook with {esc(s["competition"])}</span>'
            f'<div class="big2">{esc(s["outlook"].upper())}</div><div class="why">{md(s["why"])}</div></div>'
            f'<div class="hr"><span class="k">Submit By</span><b>{esc(s["submit_by"])}</b><dl>'
            + "".join(f"<dt>{a}</dt><dd>{esc(b)}</dd>" for a, b in (("Competition", s["signal"]), ("Financing", s["financing"]),
                                                                  ("Your Limits", s["limits"])))
            + "</dl></div></div>")
    agent_pill = ' <span class="pill vyes">Agent</span>'
    vnote = value_note(r["B"]["value"])
    rows = "".join(f'<tr><td><b>{esc(t["term"])}</b></td><td class="val">{esc(t["offer"])}{vnote if t["term"] == "Price" else ""}</td><td class="why2">{esc(t["why"])}'
                   f'{agent_pill if t["agent"] else ""}</td></tr>' for t in s["terms"])
    box = (f'<div class="ctr"><div class="ctrh"><span>RECOMMENDED OFFER</span><em>Strength <b>{s["strength"]}</b> · Seller Net <b>{s["seller_net"]}</b>'
           f' · Your Worst-Case Cash <b>{s["worst_cash"]}</b></em></div><table><colgroup><col style="width:20%"><col style="width:24%"><col></colgroup>'
           f'<thead><tr><th>Term</th><th>Offer</th><th>Why</th></tr></thead><tbody>{rows}</tbody></table></div>')
    opts = "".join(f'<tr class="{"recrow" if x["key"] == "recommended" else ""}"><td><b>{esc(x["option"])}</b></td><td class="n">{x["price"]}</td>'
                   f'<td class="c">{band_pill({"band": x["outlook"], "class": x["outlook_class"]})}</td><td class="n">{x["seller_net"]}</td>'
                   f'<td class="n">{x["worst_cash"]}</td><td class="n">{x["reserve"]}</td><td class="{x["status"]}">{esc(x["what"])}</td></tr>'
                   for x in s["options"])
    bands = "".join(f"<tr><td>{esc(b['level'])}</td>" + "".join(f"<td>{band_pill(v)}</td>" for v in b["values"]) + "</tr>" for b in s["bands"])
    exp = "".join(f'<tr><td>{esc(a)}</td><td class="n"><b class="{"rt" if a == "Left in Reserve" and s["reserve_short"] else ("gt" if a == "Left in Reserve" else "")}">'
                  f'{esc(b)}</b></td></tr>' for a, b in s["exposure"])
    limits = "".join(f'<div class="limit"><b>Limit:</b> {esc(c)}</div>' for c in s["constraints"])
    pre = f'<div class="prelim">{md(s["preliminary"])}</div>' if s["preliminary"] else ""
    return f'''{hero}{box}
<h2>Your Options <span class="h2s">Outlook with {esc(ST.COMP_LABEL[r["B"]["competition"]["level"]])}</span></h2><div class="tbl"><table><colgroup><col style="width:13%"><col style="width:10%"><col style="width:11%"><col style="width:10%"><col style="width:10%"><col style="width:9%"></colgroup>
<thead><tr><th>Option</th><th class="n">Price</th><th class="c">Outlook</th><th class="n">Seller Net*</th><th class="n">Worst Cash</th><th class="n">Reserve</th><th>What Changes</th></tr></thead><tbody>{opts}</tbody></table></div>
<div class="two">
 <div><h2>How It Stacks Up <span class="h2s">By Competition Level</span></h2><div class="tbl"><table class="bandt"><colgroup><col style="width:36%"></colgroup>
 <thead><tr><th>If the Seller Has…</th>{"".join(f'<th class="c">{esc(x)}</th>' for x in labels)}</tr></thead><tbody>{bands}</tbody></table></div>
 <div class="legend"><span>Bands combine strength score and seller net vs. a clean offer at list. An estimate, not a probability.</span></div></div>
 <div><h2>Your Exposure <span class="h2s">Recommended Offer</span></h2><div class="panel"><table class="exp">{exp}</table></div></div></div>
{limits}{pre}<div class="nextstep"><b>Next Step:</b> {esc(s["next_step"])}</div>
<div class="fine" style="margin-top:4px">*Seller net before mortgage payoff, as a listing agent would calculate it. Outlook is an estimate from the offer's terms and market signals; other offers and the seller's priorities are unknown. Not legal or financial advice.</div>'''


RESP = {"Price": "Inside the value range; the appraisal won't support much more",
        "Seller Concessions": "These cover closing costs your cash can't; could trade part of them for price",
        "Escrow Deposit": "Can go higher: refundable during the inspection period and adds no cost",
        "Inspection Period": "Needed for a full inspection; offer to share reports quickly",
        "Appraisal Gap Coverage": "Limited by your reserve; any more is your call",
        "Loan Approval": "Provide the full pre-approval letter", "Closing Date": "Match it if the lender confirms",
        "Buyer-Broker Compensation": "Per the buyer-broker agreement; discuss before submitting",
        "Home Warranty": "Already not requested", "Escrow / Title Agent": "Fine: seller's title company"}


def details(r, res):
    B, O = r["B"], r["O"]
    K = list(O)
    rec = O["recommended"]
    tgt = rec["target"]
    labels = [ST.OPTION_LABEL[k] for k in K]
    hdr = "".join(f"<th>{x}</th>" for x in labels)
    hdrn = "".join(f'<th class="n">{x}</th>' for x in labels)
    side = ""
    for row in res["side_by_side"]:
        vals = row["values"]
        side += f"<tr><td>{esc(row['term'])}</td>" + "".join(f'<td class="{"" if i == 0 or v == vals[0] else "caution"}">{esc(v)}</td>' for i, v in enumerate(vals)) + "</tr>"
    side += "<tr><td>Est. Monthly Payment</td>" + "".join(f'<td>${r["payment"][k]:,}</td>' for k in K) + "</tr>"
    cols = [(ST.OPTION_LABEL[k], O[k]["ns"]) for k in K] + [("Clean Offer at List", tgt)]
    ns = ""
    for i, (key, label, _) in enumerate(cols[0][1]["lines"]):
        if key == "payoff":
            continue
        vals = [c["lines"][i][2] for _, c in cols]
        if all(v == 0 for v in vals):
            continue
        ns += f"<tr><td>{esc(label)}</td>" + "".join(f'<td class="n {"neg" if v < 0 else ""}">{acct(v)}</td>' for v in vals) + "</tr>"
    ns += '<tr class="total"><td>Seller Net Before Payoff</td>' + "".join(f'<td class="n">{acct(c["net"])}</td>' for _, c in cols) + "</tr>"
    ns += '<tr><td>Seller Holding Cost to Closing (Est.)</td>' + "".join(f'<td class="n neg">{acct(c["holding"])}</td>' for _, c in cols) + "</tr>"
    ns += '<tr class="total2"><td>Net as the Listing Agent Sees It</td>' + "".join(
        f'<td class="n {"best" if c["net_adj"] >= tgt["net_adj"] else ("worst" if c["net_adj"] < tgt["net_adj"] - 5000 else "")}">{acct(c["net_adj"])}</td>'
        for _, c in cols) + "</tr>"
    ns += '<tr class="alt"><td>If the Appraisal and Inspection Go Badly (Value Midpoint, Typical Repair Credit)</td>' + "".join(f'<td class="n">{acct(O[k]["ns_down"]["net_adj"])}</td>' for k in K) + '<td class="n">—</td></tr>'
    sc = ""
    for key, label, w in oe.CRITERIA:
        sc += f'<tr><td>{label}</td><td class="n">{w}%</td>' + "".join(f'<td class="c s{O[k]["score"]["scores"][key]}">{O[k]["score"]["scores"][key]}</td>' for k in K) \
              + f'<td class="sm" style="color:var(--text)">{esc(rec["score"]["why"][key])}</td></tr>'
    sc += '<tr class="total"><td>Strength Score</td><td class="n">100%</td>' + "".join(
        f'<td class="c {({"hi": "hit", "mid": "midt", "lo": "lot"})[O[k]["score"]["band"][0]]}"><b>{O[k]["score"]["total"]}</b></td>' for k in K) + "<td></td></tr>"
    cr = ""
    for label, key in [("Down Payment", "down"), ("Closing Costs & Prepaids (Est.)", "cc"), ("Seller Concessions Credit", "conc"),
                       ("Cash to Close (Deposit Counts Toward This)", "to_close"), ("Appraisal Gap if the Appraisal Is Low", "gap"), ("Worst-Case Cash Needed", "worst")]:
        cr += f'<tr{" class=total" if key in ("to_close", "worst") else ""}><td>{label}</td>' + "".join(f'<td class="n">{acct(r["cash"][k][key])}</td>' for k in K) + "</tr>"
    floor = B["buyer"]["reserve_floor"]
    cr += f'<tr class="total2"><td>Left in Reserve (of {money(B["buyer"]["cash_available"])})</td>' + "".join(
        f'<td class="n {"worst" if r["cash"][k]["reserve"] < floor else "best"}">{acct(r["cash"][k]["reserve"])}</td>' for k in K) + "</tr>"
    cr += '<tr><td>Deposit at Risk After</td>' + "".join(f'<td class="n">{O[k]["firm_date"]:%b %-d} · {money(O[k]["deposit"])}</td>' for k in K) + "</tr>"
    M, V = B["market"], B["value"]
    mk = [("Value Range", f'{money(V["cma_low"])}–{money(V["cma_high"])}' + (f' ({V["source"]})' if V.get("source") else "") if not V.get("assumed") else "Not provided"),
          ("Sale-to-List", f'{M["sale_to_list"] * 100:.1f}%' if M.get("sale_to_list") else "—"), ("Months of Supply", M.get("months_supply") or "—"),
          ("Median Days on Market", M.get("median_dom") or "—"), ("Sales with Seller-Paid Buyer Costs", M.get("share_with_seller_costs") or "—"),
          ("Typical Seller-Paid Amount", M.get("typical_seller_paid") or "—"), ("Market Read", B["competition"]["heat"].title())]
    if V.get("median_adjusted"):
        mk.insert(1, ("Median Adjusted Comp", money(V["median_adjusted"])))
    plan = B.get("cma_offer_plan") or {}
    if plan.get("target_low") and plan.get("target_high"):
        mk.append(("CMA Offer Plan", f'target {money(plan["target_low"])}–{money(plan["target_high"])}'
                   + (f' · walk away {money(plan["walk_away"])}' if plan.get("walk_away") else "")))
    mkt = "".join(f"<tr><td>{a}</td><td><b>{esc(str(b))}</b></td></tr>" for a, b in mk)
    pb = "".join(f'<tr><td>{esc(t)}</td><td>{esc(a)}</td><td class="caution">{esc(b)}</td><td>{esc(RESP.get(t, "Discuss with the buyer"))}</td></tr>'
                 for t, a, b, _ in rec["counter_rows"]) or '<tr><td colspan="4">Nothing obvious: the offer already meets the listing-side benchmarks.</td></tr>'
    if r["missing"]:
        asum = ('<div class="tbl"><table><colgroup><col style="width:9%"><col style="width:12%"></colgroup><thead><tr><th class="c">Impact</th><th>Where</th><th>What Was Assumed</th></tr></thead><tbody>'
                + "".join(f'<tr><td class="c"><span class="pill {a["impact"]}">{a["impact"].title()}</span></td><td>{esc(a["scope"].title())}</td><td>{esc(a["why"])}</td></tr>'
                          for a in r["missing"]) + "</tbody></table></div>")
    else:
        asum = '<p class="sm">All key inputs provided.</p>'
    L = r["R"]["listing"]
    lf = r["R"]["seller"]["listing_fee_pct"]
    cost_basis = (f"Assumes a {oe.pct(lf)} listing fee" if lf else "Listing fee unknown") + "; " + "; ".join(L["cost_notes"]) + "."
    state = profiles.STATES.get(L.get("state") or "", "your state")
    return f'''<div class="pb"></div><div class="dh">Detailed Analysis</div>
<h2>1 · Options Side by Side <span class="h2s">Amber = Differs from the Recommended Offer</span></h2>
<div class="tbl"><table><colgroup><col style="width:22%"></colgroup><thead><tr><th>Term</th>{hdr}</tr></thead><tbody>{side}</tbody></table></div>
<h2>2 · How the Listing Agent Will See Each Option <span class="h2s">Seller Net Sheet, Before Mortgage Payoff</span></h2>
<div class="tbl"><table><colgroup><col style="width:32%"></colgroup><thead><tr><th>Line Item</th>{hdrn}<th class="n">Clean Offer at List</th></tr></thead><tbody>{ns}</tbody></table></div>
<div class="legend"><span>{esc(cost_basis)}</span></div>
<h2 class="pb">3 · Strength Scorecard <span class="h2s">The Same Criteria a Listing Agent Uses · 1 = Weak · 5 = Strong</span></h2>
<div class="tbl"><table><colgroup><col style="width:27%"><col style="width:7%">{"".join('<col style="width:8%">' for _ in K)}</colgroup>
<thead><tr><th>Criterion</th><th class="n">Weight</th>{"".join(f'<th class="c">{x}</th>' for x in labels)}<th>Recommended: Why</th></tr></thead><tbody>{sc}</tbody></table></div>
<h2>4 · Your Cash &amp; Risk</h2>
<div class="tbl"><table><colgroup><col style="width:38%"></colgroup><thead><tr><th>Item</th>{hdrn}</tr></thead><tbody>{cr}</tbody></table></div>
<div class="legend"><span>Worst case: the appraisal comes in low and you cover the gap. Payment uses {B["costs"]["rate"]}% and post-purchase taxes; your lender's Loan Estimate governs.</span></div>
<div class="two" style="margin-top:0">
 <div><h2>5 · Market Check</h2><div class="tbl"><table><tbody>{mkt}</tbody></table></div></div>
 <div><h2>6 · Likely Pushback <span class="h2s">On the Recommended Offer</span></h2><div class="tbl"><table><colgroup><col style="width:24%"><col style="width:19%"><col style="width:19%"></colgroup>
 <thead><tr><th>Term</th><th>Yours</th><th>They May Ask</th><th>Response</th></tr></thead><tbody>{pb}</tbody></table></div></div></div>
<h2>7 · Assumptions &amp; Data to Confirm</h2>{asum}
<div class="fine">Strength scores use the same rubric as the listing-side offer review. Outlook bands are estimates: the number and terms of other offers and the seller's priorities are unknown, and a seller may choose any offer. Closing costs are estimated at {B["buyer"]["closing_cost_pct"]:.1%} of price; loan program limits change, so confirm with the lender. Not legal or financial advice; for contract questions, consult a real estate attorney licensed in {esc(state)}.</div>'''


def options_html(r, agent, sample):
    res = ST.result(r)
    s = res["summary"]
    B = r["B"]
    P = B["property"]
    sub = f'{esc(P.get("address") or "")} · List {money(P["list_price"])} · {oe.FIN_LABEL[B["buyer"]["financing"]]} offer'
    prep = f'Prepared for <b>{esc(B["buyer"].get("name") or "Buyer")}</b> · {B["analysis_date"]:%B %-d, %Y}{agent_lines(agent)}'
    body = header("Offer Options", sub, prep, sample) + snapshot(r) + f'<div class="p1">{page1(r, s)}</div>' + details(r, res)
    theme = design.theme(agent.get("brand"), "buyer")
    return render.page(body, css=css("options"), title="Offer Options", theme_css=design.css_vars(theme))


# --- Offer Package Worksheet -----------------------------------------------------

def worksheet_html(r, agent, sample, variant=None):
    W = ST.worksheet(r, variant)
    B = r["B"]
    rows = "".join(f'<tr><td class="c">{esc(x["para"]) or "—"}</td><td>{esc(x["field"])}</td><td class="ent">{md(x["entry"])}</td>'
                   f'<td class="src">{esc(x["note"])}</td></tr>' for x in W["rows"])
    riders = "".join(f'<tr><td><b>{esc(x["rider"])}</b></td><td>{md(x["inputs"])}</td><td class="src">{esc(x["why"])}</td></tr>' for x in W["riders"]) \
        or '<tr><td colspan="3">No riders needed.</td></tr>'
    clauses = "".join(f'<div class="clause"><b class="t">{esc(x["title"])}</b>{esc(x["text"])}</div>' for x in W["clauses"])
    docs = "".join(f"<tr><td>☐ {esc(d)}</td></tr>" for d in W["docs"])
    def hint(note):
        return f'<span class="hint">{esc(note)}</span>' if note else ""

    done = ("yes", "done", "true", "✓")
    pk = "".join(f'<tr><td class="c"><span class="cb{" on" if str(x["status"]).lower() in done else ""}"></span></td><td class="src">{esc(x["group"])}</td><td>{esc(x["item"])}{hint(x["note"])}</td>'
                 '<td class="write"></td><td class="write"></td></tr>' for x in W["package"])
    verify = ("verify every paragraph and rider against the current FR/BAR form version" if W["frbar"]
              else "match each entry to your contract by name (paragraph numbers vary by form)")
    prep = f'Draft prepared {B["analysis_date"]:%B %-d, %Y}{agent_lines(agent)}'
    sub = f'{esc(B["property"].get("address") or "")} · {oe.FIN_LABEL[B["buyer"]["financing"]]} · {W["price"]} · {W["option"].lower()} offer'
    body = f'''{header("Offer Package Worksheet", sub, prep, sample)}
<div class="draftbar"><b>DRAFT FOR THE AGENT.</b> Enter in {esc(W["software"])} and {verify}. Red brackets = fill in. Suggested language is for broker review, not legal advice.</div>
<div class="goal"><b>Contract Form:</b> {esc(W["form_name"])}. {esc(W["form_why"])}</div>
<h2>1 · Contract Entries</h2>
<div class="tbl"><table class="ws"><colgroup><col style="width:8%"><col style="width:22%"><col style="width:40%"></colgroup>
<thead><tr><th class="c">Para.</th><th>Field</th><th>Enter</th><th>Note</th></tr></thead><tbody>{rows}</tbody></table></div>
<h2>2 · Riders to Attach <span class="h2s">With Suggested Inputs</span></h2>
<div class="tbl"><table class="ws"><colgroup><col style="width:27%"><col style="width:43%"></colgroup>
<thead><tr><th>Rider</th><th>Suggested Inputs</th><th>Why</th></tr></thead><tbody>{riders}</tbody></table></div>
<h2>3 · Additional Terms <span class="h2s">Draft Language</span></h2>{clauses}
<h2>4 · Offer Package Checklist</h2>
<div class="tbl pk"><table class="ws"><colgroup><col style="width:5%"><col style="width:11%"><col style="width:48%"><col style="width:12%"></colgroup>
<thead><tr><th class="c">✓</th><th>Group</th><th>Item</th><th>Date</th><th>Notes</th></tr></thead><tbody>{pk}</tbody></table></div>
<h2>5 · Request from the Seller After Acceptance</h2><div class="tbl"><table><tbody>{docs}</tbody></table></div>
<div class="fine">Generated from the same analysis as the Offer Options report. {"Paragraph numbers follow the FR/BAR AS IS contract and may differ by form version. " if W["frbar"] else ""}Rider availability depends on your form set. Draft clause language must be reviewed by the agent and broker; consult a real estate attorney for legal questions.</div>'''
    theme = design.theme(agent.get("brand"), "buyer")
    return render.page(body, css=css("worksheet"), title="Offer Package Worksheet", theme_css=design.css_vars(theme)), W


# --- files -----------------------------------------------------------------------

def fit_page_one(pg):
    top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > PAGE1_LIMIT:
        pg.evaluate("() => document.body.classList.add('compact')")
        top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    return top


def build(data, fmt, out_dir, ctx):
    r = ST.analyze(data, ctx.get("market"), ST.load_cma(data, ctx.get("cma")))
    option = ctx.get("option")
    sample = ctx.get("sample") or r["sample"]
    street = (r["B"]["property"].get("address") or "Property").split(",")[0]
    if fmt == "options":
        path = os.path.join(out_dir, render.filename(street, "Offer Options", ext="pdf"))
        top = render.html_to_pdf(options_html(r, ctx["agent"], sample), path, before_print=fit_page_one,
                                 footer_html=render.footer(f"Offer Options · Buyer Side · {street}"))
        if top > PAGE1_LIMIT:
            print(f"Page 1 overflows by {top - PAGE1_LIMIT:.0f}px; shorten override notes.", file=sys.stderr)
    else:
        doc, W = worksheet_html(r, ctx["agent"], sample, option)
        path = os.path.join(out_dir, render.filename(street, "Offer Package", ext="pdf"))
        render.html_to_pdf(doc, path, footer_html=render.footer(f"Offer Package Worksheet · Buyer Side · {street} · Draft"))
        print(f"Worksheet ({W['option'].lower()} offer): {len(W['riders'])} rider(s), {len(W['clauses'])} clause draft(s), {W['blanks']} blank(s) to fill",
              file=sys.stderr)
    return [path]


def options(ap):
    ap.add_argument("--cma", help="cma-handoff v1 file (.cma.json or markdown with the block)")
    ap.add_argument("--option", choices=list(ST.OPTION_LABEL), help="option for the worksheet (default: the file's chosen_option)")


def main(argv=None):
    return render.main(build, formats=("options", "worksheet"), argv=argv, extra_args=options,
                       errors=(oe.OfferError, handoff.HandoffError))


if __name__ == "__main__":
    main(sys.argv[1:])
