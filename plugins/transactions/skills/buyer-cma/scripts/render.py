"""Buyer CMA PDF: page 1 summary, then the full analysis in a fixed section order.

    python3 scripts/render.py report.json [--agent agent-profile.md] [--market market-profile.md] [--sample] [--out DIR]

report.json holds the written content and the few inputs the numbers come from (see
references/report-data.md); `export` in it is the path to the MLS export. Every number is computed
by compute.py, never typed. Prints the PDF path, then layout notes on stderr.
"""
import html
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import cma, design, finance, handoff, render  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
money, table, ul, k = finance.money, cma.table, cma.ul, cma.k
esc = html.escape


def agent_block(agent, L):
    """Wordmark (left) with only the fields the agent profile has."""
    name = agent.get("name")
    if not name:
        return ""
    org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
    left = f'<div class="wm-name">{esc(name)}</div><div class="wm-sub">{esc(org or L("wordmark_sub"))}</div>'
    return left


def footer_block(agent, R, L):
    if not agent.get("name"):
        return f'<footer>{L("prepared")} {esc(R["prepared_date"])}</footer>'
    lines = [f'<b>{esc(agent["name"])}</b>' + "".join(
        f" · {esc(str(agent[f]))}" for f in ("team", "brokerage") if agent.get(f)) +
        (f' · {L("lic")} {esc(str(agent["license"]))}' if agent.get("license") else "")]
    contact = " · ".join(esc(str(agent[f])) for f in ("phone", "email", "website") if agent.get(f))
    if contact:
        lines.append(contact)
    lines.append(f'{L("prepared")} {esc(R["prepared_date"])}')
    return "<footer>" + "<br>".join(lines) + "</footer>"


def summary_page(R, C, agent, L):
    s, bl, op = R["subject"], R["bottom_line"], R["offer_plan"]
    sp = cma.fill(R["summary_page"], cma.page_one_values(C))
    pay = C["payments"]
    first = pay["rows"][0]
    sc0 = R["costs"]["payment"]["scenarios"][0]
    stats = list(sp["key_stats"])[:3] + [[money(first["total"]),
                                           L("sum_payment_tile", price=money(pay["price"]), down=f"{sc0['down_pct'] * 100:g}")]]
    tgt = k(op["target_low"]) + (f"–{k(op['target_high'])}" if op.get("target_high") and op["target_high"] != op["target_low"] else "")
    left = agent_block(agent, L)
    o = ['<div class="onepage">',
         f'<header class="top"><div>{left}</div><div class="prep">'
         f'{esc(sp.get("label", L("sum_label")))}<br>{L("prepared")} {esc(R["prepared_date"])}</div></header>',
         cma.subject_heading(s),
         '<div class="sp-hero"><div class="sp-rec">'
         f'<div class="lbl">{L("sum_opening")}</div><div class="price">{money(op["opening"])}</div>'
         f'<div class="line">{L("sum_ladder_line", target=tgt, walk=money(op["walk_away"]))}</div>'
         f'<div class="line">{L("sum_range_line")} <b>{k(bl["low"])} – {k(bl["high"])}</b> · {L("sum_asking")} <b>{money(s["list_price"])}</b></div>'
         f'<div class="line" style="margin-top:6px">{sp["headline"]}</div></div>'
         '<div class="sp-stats">' + "".join(f'<div class="sp-stat"><b>{v}</b><span>{lbl}</span></div>' for v, lbl in stats) + "</div></div>",
         f'<div class="sp-h">{L("sum_comps_h")} <span style="font-weight:400;color:var(--muted)">· {L("sum_shaded")}</span></div>',
         '<div class="sp-dot">' + cma.dotplot(R["comps"]["cards"], bl["low"], bl["high"], s["list_price"],
                                             L("dot_asking", price=money(s["list_price"])),
                                             (op["opening"], L("dot_offer", price=money(op["opening"])))) + "</div>"]
    tax = C["taxes"][pay["tax_index"]]
    rows = [[L("sum_tax_now"), money(R["costs"]["taxes"]["current_bill"]) + L("per_year")],
            [L("sum_tax_yours"), "≈ " + money(tax["annual"], 100) + L("per_year")],
            [L("sum_pay_row", label=sc0["label"]), money(first["total"]) + L("per_month")],
            [L("sum_cash_row", label=sc0["label"]), money(first["cash_down"])]]
    trs = "".join(f'<tr class="{"rec" if i == 1 else ""}"><td>{a}</td><td class="n">{v}</td></tr>' for i, (a, v) in enumerate(rows))
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{L("sum_why")}</div>{ul(sp["why"], "")}</div>'
             f'<div class="sp-table"><div class="sp-h">{L("sum_costs")}</div><div class="tbl"><table><tbody>{trs}</tbody></table></div>'
             f'<div class="note">{L("sum_costs_note")}</div></div></div>')
    o.append(f'<div class="sp-h">{L("sum_check")}</div><div class="sp-steps">' +
             "".join(f'<div class="sp-step"><b>{h}</b>{d}</div>' for h, d in sp["check_first"]) + "</div>")
    o.append(f'<div class="sp-next"><span><b>{L("sum_next")}</b> {sp["next_step"]}</span></div>')
    o.append(f'<div class="note" style="margin-top:6px">{L("sum_disclaimer")}</div></div>')
    return "".join(o)


def credit_section(R, C, L):
    cs, cr = R["costs"]["credit_scenarios"], C["credit"]
    cols = cr["columns"]

    def flag(c):
        key = "cr_over_cap" if c["over_cap"] else "cr_over_costs" if c["over_costs"] else None
        return f' <span class="flag">({L(key)})</span>' if key else ""

    prog = L("prog_" + {"conventional": "conv"}.get(cr["program"], cr["program"]))
    rows = [
        [L("cr_price")] + [money(c["price"]) for c in cols],
        [L("cr_credit")] + [(money(c["credit"]) if c["credit"] else L("cr_none")) + flag(c) for c in cols],
        [L("cr_net")] + [money(c["net"]) for c in cols],
        [L("cr_loan")] + [money(c["loan"]) for c in cols],
        [f'<strong>{L("cr_cash")}</strong>'] + [f'<strong>{money(c["cash"])}</strong>' for c in cols],
        [L("cr_pmt")] + [money(c["payment"]) for c in cols],
        [L("cr_extra")] + [("+" + money(c["extra"])) if c["extra"] > 0.5 else L("cr_none") for c in cols],
        [L("cr_payback")] + [L("cr_years", n=f"{c['payback_years']:.0f}") if c["payback_years"] else L("cr_none") for c in cols],
        [L("cr_cap", program=prog, down=f'{cr["down_pct"] * 100:g}')] + [money(c["cap"]) if c["cap"] is not None else L("cr_none") for c in cols],
        [L("cr_appr", median=money(C["median_adjusted"]))] + [money(c["appraisal_room"]) for c in cols],
    ]
    head = [L("cr_head")] + [money(c["price"]) + (" + " + money(c["credit"]) if c["credit"] else "") for c in cols]
    cc = L("cr_cc_est", amt=money(cs["closing_costs"])) if cr["closing_costs_given"] else L("cr_cc_pct", pct=f'{cr["closing_cost_pct"] * 100:g}')
    out = [f'<h3>{L("h_credit")}</h3>', f'<p>{cs["intro"]}</p>',
           table(head, rows, num_cols=tuple(range(1, len(head))), row_classes={4: "total"}),
           f'<p class="note">{L("cr_note", cc=cc)}</p>']
    if cs.get("after_paragraph"):
        out.append(f'<p>{cs["after_paragraph"]}</p>')
    b = cr.get("buydown")
    if b:
        key = "cr_buydown" if b["covered"] else "cr_buydown_short"
        out.append("<p>" + L(key, credit=money(b["credit"]), price=money(b["price"]), cost=money(b["cost"], 100),
                             y1=money(b["year1"]), y2=money(b["year2"]), full=money(b["full"])) + "</p>")
    return out


def body(R, C, homes, agent, L):
    """The report after page 1, as a list of top-level blocks (grouped for pagination afterwards)."""
    s, bl, op = R["subject"], R["bottom_line"], R["offer_plan"]
    b = [f'<h2>{L("h_home")}</h2>',
         '<div class="facts">' + "".join(f"<div><span>{a}</span><b>{v}</b></div>" for a, v in s["facts"]) + "</div>",
         f'<p>{s["summary"]}</p>',
         f'<h2>{L("h_bottom")}</h2>',
         f'<div class="verdict"><div class="range">{money(bl["low"])} – {money(bl["high"])}</div>'
         f'<div class="mid">{L("range_caption", mid=money(bl.get("midpoint", (bl["low"] + bl["high"]) / 2)))}</div><p>{bl["paragraph"]}</p></div>']
    if R.get("history"):
        h = R["history"]
        b += [f'<h3>{h["heading"]}</h3>', f'<p>{h["intro"]}</p>',
              table([L("th_date"), L("th_event"), L("th_price")], h["rows"], num_cols=(2,))]
        if h.get("after"):
            b.append(f'<p>{h["after"]}</p>')
    target = money(op["target_low"]) + (f"–{money(op['target_high'])}" if op.get("target_high") and op["target_high"] != op["target_low"] else "")
    b += [f'<h3>{L("h_offer_plan")}</h3>', f'<p>{op["intro"]}</p>',
          table([L("th_step"), L("th_amount"), L("th_why")],
                [[f'<strong>{L("ladder_opening")}</strong>', f'<strong>{money(op["opening"])}</strong>', op["why_opening"]],
                 [L("ladder_target"), target, op["why_target"]],
                 [L("ladder_walk"), money(op["walk_away"]), op["why_walk_away"]]], num_cols=(1,), row_classes={0: "total"})]
    if op.get("credit_alt"):
        ca = op["credit_alt"]
        b.append("<p>" + L("credit_alt", price=money(ca["price"]), credit=money(ca["credit"]), equiv=money(ca["price"] - ca["credit"])) + "</p>")
    b.append(f'<p class="note">{L("offer_conditions", conditions=op["conditions"])}</p>')
    b += [f'<h3>{R["offer"].get("heading", L("h_offer"))}</h3>', ul(R["offer"]["bullets"])]

    c = R["comps"]
    b += [f'<h2>{L("h_compared")}</h2>', f'<p>{c["intro"]}</p>', f'<p class="note">{c["method_note"]}</p>',
          '<div class="comps2">' + "".join(
              f'<div class="comp"><div class="comp-h"><b>{esc(cd["address"])}</b><span class="adj">{L("adjusted")} {money(cd["adjusted"])}</span></div>'
              f'<div class="meta">{cd["meta"]}</div>{ul(cd["bullets"], "")}</div>' for cd in c["cards"]) + "</div>"]
    rows = [[r[0], money(r[1]), money(r[2]), money(r[3])] for r in c["summary_rows"]]
    rows.append([c.get("subject_row_label", L("subject_row")), money(s["list_price"]), "—", f'{L("range_word")} {k(bl["low"])}–{k(bl["high"])}'])
    b += [table([L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")], rows, num_cols=(1, 2, 3),
                row_classes={len(rows) - 1: "subj"}), f'<p>{c["summary_paragraph"]}</p>']

    sc = R.get("scatter")
    if sc and homes:
        svg, info = cma.scatter(homes, sc, s["sqft"], s["list_price"], s.get("mls_address", s["address"]), (bl["low"], bl["high"]), L)
        trend = money(info["trend_at_subject"], 1000) if info["trend_at_subject"] else "N/A"
        share = L(compute.mls.r2_key(info["r2"])) if info["r2"] is not None else ""
        b += [f'<h3>{sc.get("heading", L("h_scatter"))}</h3>', f'<p>{sc["intro"].replace("{trend_at_subject}", trend)}</p>',
              '<div class="chart-box">' + cma.scatter_legend(L, sc.get("subject_label", s["address"])) + svg + "</div>"]
        note = cma.excluded_note(info["excluded"], L)
        if note:
            b.append(note)
        b.append(f'<p>{sc["after_paragraph"].replace("{trend_at_subject}", trend).replace("{r2_share}", share)}</p>')

    cp = R["competition"]
    b += [f'<h2>{L("h_competition")}</h2>', f'<p>{cp["intro"]}</p>',
          table([L("th_address"), L("th_status"), L("th_price"), L("th_sqft"), L("th_pool"), L("th_days"), L("th_notes")],
                [[r[0], r[1], money(r[2]), f"{int(r[3]):,}", r[4], r[5], r[6]] for r in cp["rows"]], num_cols=(2, 3, 5))]
    m = R["market"]
    b += [f'<h2>{L("h_market")}</h2>', f'<p>{m["intro"]}</p>',
          table(m["columns"], m["rows"], num_cols=tuple(range(1, len(m["columns"])))), ul(m["bullets"])]

    t, pay = R["costs"]["taxes"], C["payments"]
    b += [f'<h2>{L("h_costs")}</h2>']
    if t.get("heading"):
        b.append(f'<h3>{t["heading"]}</h3>')
    b.append(f'<p>{t["intro"]}</p>')
    trows = [[L("seller_bill", year=t["current_year"]), money(t["current_bill"]), money(t["current_bill"] / 12)]]
    trows += [[L("your_bill", label=j["label"]), "≈ " + money(j["annual"], 100), "≈ " + money(j["annual"] / 12)] for j in C["taxes"]]
    homestead = L("with_homestead") if t.get("homestead", True) else L("no_homestead")
    b.append(table([L("tax_header", price=money(t["purchase_price"]), homestead=homestead), L("th_yearly"), L("th_monthly")],
                   trows, num_cols=(1, 2), row_classes={i: "tax-jump" for i in range(1, len(trows))}))
    note = t["note"]
    if any(j["estimated"] for j in C["taxes"]):
        note += " " + L("tax_estimated", basis=C["taxes"][0]["basis"])
    b.append(f'<p class="note">{note}</p>')
    if t.get("after_paragraph"):
        b.append(f'<p>{t["after_paragraph"]}</p>')
    b += [f'<h3>{L("h_insurance")}</h3>', f'<p>{R["costs"]["insurance"]["paragraph"]}</p>']

    rows_p = pay["rows"]
    short = C["taxes"][pay["tax_index"]]["short"]
    prow = [[L("pay_cash")] + [money(r["cash_down"]) for r in rows_p],
            [L("pay_pi")] + [money(r["pi"]) for r in rows_p],
            [L("pay_tax", short=short)] + [money(r["tax"]) for r in rows_p],
            [L("pay_ins")] + [money(r["ins"]) for r in rows_p],
            [L("pay_mi")] + [money(r["mi"]) for r in rows_p],
            [L("pay_hoa")] + [money(r["hoa"]) for r in rows_p],
            [L("pay_total")] + [money(r["total"]) for r in rows_p]]
    classes = {6: "total"}
    if pay["alt_jurisdiction"]:
        prow.append([L("pay_if", short=pay["alt_jurisdiction"]["short"])] + [money(r["total"] + pay["alt_jurisdiction"]["delta_monthly"]) for r in rows_p])
        classes[7] = "alt"
    progs = finance.LOAN_PROGRAMS
    pay_note = R["costs"]["payment"].get("note") or L(
        "pay_note", rate=f'{pay["rate"]:.2f}', ins=money(pay["insurance_annual"]), pmi=f'{progs["conventional"]["annual_mi"] * 100:.1f}',
        mip=f'{progs["fha"]["annual_mi"] * 100:.2f}', ufmip=f'{progs["fha"]["upfront_fee"] * 100:.2f}', per10k=money(pay["per_10k"], 5))
    b += [f'<h3>{L("h_payment")}</h3>', f'<p>{R["costs"]["payment"]["intro"]}</p>',
          table([L("pay_header", price=money(pay["price"]))] + [r["label"] for r in rows_p], prow,
                num_cols=tuple(range(1, len(rows_p) + 1)), row_classes=classes),
          f'<p class="note">{pay_note}</p>']
    if C["credit"]:
        b += credit_section(R, C, L)

    w = R["watch"]
    b += [f'<h2>{L("h_watch")}</h2>', ul(w["items"], "plain watch"),
          f'<h3>{L("h_questions")}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in w["questions"]) + "</ol>",
          f'<h2>{L("h_method")}</h2>'] + [f"<p>{p}</p>" for p in R["method"]]
    b.append(footer_block(agent, R, L))
    return b


def theme_css(agent):
    t = design.theme(agent.get("brand"), "buyer")
    subject = t["status"]["risk"]
    return design.css_vars(t) + f":root{{--subject:{subject['base']};--subject-bg:{subject['bg']}}}", t


def build_html(R, C, homes, agent):
    L = cma.Labels(ASSETS, R.get("labels"))
    R.setdefault("prepared_date", f"{date.today():%B %-d, %Y}")
    vars_css, _ = theme_css(agent)
    content = ('<div class="wrap">' + summary_page(R, C, agent, L) + '<div class="pb"></div>' +
               cma.group_blocks(body(R, C, homes, agent, L)) + "</div>")
    title = f'{L("doc_label")}: {R["subject"]["address"]}'
    doc = render.page(content, css=cma.css(), title=title, theme_css=vars_css)
    return doc.replace("<html>", '<html lang="en">', 1), L


def build(R, fmt, out_dir, ctx):
    market, homes = compute.load_inputs(R, ctx.get("market"))
    C = compute.compute(R, market, homes)
    if C["payments"] is None:
        raise compute.ReportError("Taxes couldn't be estimated for every jurisdiction: " + "; ".join(C["warnings"]))
    doc, L = build_html(R, C, homes, ctx["agent"])
    agent = ctx["agent"]
    label = " · ".join(x for x in (R["subject"]["address"], L("doc_label"),
                                   ", ".join(str(agent[f]) for f in ("name", "brokerage") if agent.get(f))) if x)
    if ctx.get("sample") or R.get("sample"):
        label = "SAMPLE DATA · " + label
    path = os.path.join(out_dir, render.filename(R["subject"]["address"], "Buyer CMA", ext="pdf"))
    info = render.html_to_pdf(doc, path, margins=cma.PAGE_MARGINS, footer_html=render.footer(label), before_print=cma.paginate)
    hpath = os.path.join(out_dir, handoff.filename(R["subject"]["address"]))
    with open(hpath, "w", encoding="utf-8") as f:
        json.dump(C["handoff"], f, indent=2)
    if not info["summary_page"]["fits"]:
        print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
    elif info["summary_page"]["fit_level"]:
        print(f"Page 1 ran long and was tightened (step {info['summary_page']['fit_level']} of 3) to fit.", file=sys.stderr)
    if info["moved"]:
        print("Kept together on a new page (information; check that page for a large empty gap): " + "; ".join(info["moved"]), file=sys.stderr)
    for w in C["warnings"]:
        print(f"Check: {w}", file=sys.stderr)
    return [path, hpath]


if __name__ == "__main__":
    try:
        render.main(build, formats=("pdf",), errors=(compute.ReportError, compute.mls.ExportError))
    except KeyError as e:
        sys.exit(f"report.json is missing {e}")
