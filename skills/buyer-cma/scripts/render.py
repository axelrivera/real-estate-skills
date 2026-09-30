"""Buyer CMA PDF: page 1 summary, then the full analysis in a fixed section order.

    python3 scripts/render.py report.json [--profile profile.md] [--sample] [--out DIR]

report.json holds the written content and the few inputs the numbers come from (see
references/report-data.md); `export` in it is the path to the MLS export. Every number is computed
by compute.py, never typed. Prints the PDF path, then layout notes on stderr.
"""
import html
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
from _shared import cma, design, finance, render  # noqa: E402

ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets")
money, table, ul, k = finance.money, cma.table, cma.ul, cma.k
esc = html.escape


def agent_block(agent, L):
    """Wordmark (left) with only the fields the profile has."""
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


def seller_cost_note(cr, L):
    """CMA-11: what each $10,000 of price costs the seller in the percentage costs we know, plus the listing fee."""
    cost = (L("cr_seller_cost_known", amt=money(cr["seller_cost_per_10k"]), what=" and ".join(cr["seller_cost_parts"]))
            if cr["seller_cost_per_10k"] else L("cr_seller_cost_fee"))
    return L("cr_seller_cost", cost=cost)


def homestead_label(R, L):
    """CMA-14: "With Homestead" only when the estimate applies it (not for an investor or a second home)."""
    return L("with_homestead") if R["costs"]["taxes"].get("homestead", True) else L("no_homestead")


def basis_label(pay, L):
    """CMA-204: " (Target)" or " (Asking)": which of the plan's prices the payment is figured at."""
    return L("basis_" + pay["price_basis"]) if pay.get("price_basis") else ""


def cash_flag(short, pay, L):
    """CMA-204: beside a cash figure that's more than the buyer has."""
    return (f'<br><span class="flag" style="font-size:8.5pt">{L("cash_short", amt=money(short), cash=pay["buyer_cash_display"])}'
            '</span>' if short else "")


def cash_fit_note(first, C, L):
    """CMA-295: under page 1's cash-to-close row, when the buyer's own program runs over their cash, the credit table's
    option that fits (compute.py's cash_fit), so the flag carries its answer."""
    fit = C.get("cash_fit")
    if not (first.get("cash_short") and fit):
        return ""
    key = "sum_cash_fit" if fit["credit"] else "sum_cash_fit_price"
    return ('<div class="note">' + L(key, cash=C["payments"]["buyer_cash_display"], price=money(fit["price"]),
                                     credit=money(fit["credit"]), amt=money(fit["cash"])) + "</div>")


def pay_closing_note(pay, L):
    """CMA-223: what the payment table's closing costs are, on the credit table's basis."""
    cl = pay["closing"]
    cc = L("cr_cc_pct", pct=f'{cl["pct"] * 100:g}')
    if cl["loan_tax_labels"]:
        cc += L("pay_cc_taxes", names=" and ".join(x.lower() for x in cl["loan_tax_labels"]))
    lender = [r["label"] for r in pay["rows"] if r.get("lender_closing_costs")]
    if lender:
        cc += L("pay_cc_lender", label=lender[0], amt=money(cl["lender_amount"]))
    return L("pay_cc_note", cc=cc)


def tax_row_label(R, pay, L):
    """CMA-204: the payment's tax row, labeled Estimate when the district is unconfirmed or the rate is a fallback."""
    key = "pay_tax_est" if pay["tax_basis"]["label_estimate"] else "pay_tax"
    return L(key, short=pay["tax_basis"]["short"], homestead=homestead_label(R, L))


def tax_which_note(pay, L):
    """CMA-204: which tax the payment uses, when that isn't settled (local-costs.md: say what's estimated)."""
    tb = pay["tax_basis"]
    if tb["estimated"]:
        return " " + L("pay_tax_which_rate", basis=tb["basis"])
    if tb["unconfirmed"]:
        return " " + L("pay_tax_which_higher" if tb["higher"] else "pay_tax_which", short=tb["short"])
    return ""


def history_rows(h, hist, L):
    """The history table: the rows as written, else built from history.events (CMA-201), so no price is typed."""
    if h.get("rows"):
        return h["rows"]
    out, year, n_listed = [], None, 0
    for e in (hist or {}).get("timeline", []):
        d = date.fromisoformat(e["date"])
        when = f"{d:%b %-d, %Y}" if d.year != year else f"{d:%b %-d}"
        year = d.year
        kind = e["kind"]
        if kind == "listed":
            n_listed += 1
            kind = "relisted" if n_listed > 1 else "listed"
        elif kind == "back_on" and e["delta"]:
            kind = "back_on_higher" if e["delta"] > 0 else "back_on_lower"
        out.append([when, e.get("note") or L("hist_" + kind), money(e["price"]) if e["price"] is not None else "—"])
    return out


def summary_page(R, C, agent, L):
    s, bl, op = R["subject"], R["bottom_line"], R["offer_plan"]
    sp = cma.fill(R["summary_page"], cma.page_one_values(C))
    pay = C["payments"]
    first = pay["rows"][0]
    sc0 = R["costs"]["payment"]["scenarios"][0]
    stats = list(sp["key_stats"])[:3] + [[money(first["total"]),
                                           L("sum_payment_tile", price=money(pay["price"]), basis=basis_label(pay, L),
                                             down=f"{sc0['down_pct'] * 100:g}")
                                           + (L("assumed_suffix") if first.get("assumed") else "")]]  # CMA-227
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
    bill = R["costs"]["taxes"].get("current_bill")
    yours = L("sum_tax_yours_est" if pay["tax_basis"]["label_estimate"] else "sum_tax_yours",
              short=pay["tax_basis"]["short"], homestead=homestead_label(R, L))  # CMA-204
    rows = [[L("sum_tax_now"), money(bill) + L("per_year") if bill else L("not_available")],
            [yours, "≈ " + money(tax["annual"], 100) + L("per_year")],
            [L("sum_pay_row", label=first["label"]), money(first["total"]) + L("per_month")],
            [L("sum_cash_row", label=first["label"]),  # CMA-223: cash to close, with its closing costs
             money(first["cash_to_close"]) + cash_flag(first.get("cash_short"), pay, L)]]
    trs = "".join(f'<tr class="{"rec" if i == 1 else ""}"><td>{a}</td><td class="n">{v}</td></tr>' for i, (a, v) in enumerate(rows))
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{L("sum_why")}</div>{ul(sp["why"], "")}</div>'
             f'<div class="sp-table"><div class="sp-h">{L("sum_costs")}</div><div class="tbl"><table><tbody>{trs}</tbody></table></div>'
             + cash_fit_note(first, C, L)
             + f'<div class="note">{L("sum_costs_note", price=money(pay["price"]))}</div></div></div>')
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
        *([[L("cr_bb_short")] + [money(c["bb_short"]) for c in cols]] if any(c["bb_short"] for c in cols) else []),
        [f'<strong>{L("cr_cash")}</strong>'] + [f'<strong>{money(c["cash"])}</strong>' + cash_flag(c.get("cash_short"), C["payments"], L) for c in cols],
        [L("cr_pmt")] + [money(c["payment"]) for c in cols],
        [L("cr_extra")] + [("+" + money(c["extra"])) if c["extra"] > 0.5 else L("cr_none") for c in cols],
        [L("cr_payback")] + [L("cr_years", n=f"{c['payback_years']:.0f}") if c["payback_years"] else L("cr_none") for c in cols],
        [L("cr_cap", program=prog, down=f'{cr["down_pct"] * 100:g}')] + [money(c["cap"]) if c["cap"] is not None else L("cr_none") for c in cols],
        [L("cr_appr", median=C["median_adjusted_display"])] + [money(c["appraisal_room"]) for c in cols],
    ]
    head = [L("cr_head")] + [money(c["price"]) + (" + " + money(c["credit"]) if c["credit"] else "") for c in cols]
    cc = L("cr_cc_est", amt=money(cs["closing_costs"])) if cr["closing_costs_given"] else L("cr_cc_pct", pct=f'{cr["closing_cost_pct"] * 100:g}')
    if cr["loan_tax_labels"]:  # CORE-16
        cc += L("cr_cc_taxes", amt=money(cols[0]["loan_taxes"]), price=money(cols[0]["price"]),
                names=" and ".join(x.lower() for x in cr["loan_tax_labels"]))
    out = [f'<h3>{L("h_credit")}</h3>', f'<p>{cs["intro"]}</p>',
           table(head, rows, num_cols=tuple(range(1, len(head))), row_classes={4: "total"}),
           f'<p class="note">{L("cr_note", cc=cc)}{seller_cost_note(cr, L)}'
           + (" " + L("cash_note", cash=C["payments"]["buyer_cash_display"]) if C["payments"].get("buyer_cash") else "") + "</p>"]
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
              table([L("th_date"), L("th_event"), L("th_price")], history_rows(h, C.get("history"), L), num_cols=(2,))]
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
              f'<div class="comp"><div class="comp-h"><b>{esc(cma.display_address(cd["address"]))}</b><span class="adj">{L("adjusted")} {money(cd["adjusted"])}</span></div>'
              f'<div class="meta">{cd["meta"]}</div>{ul(cd["bullets"], "")}</div>' for cd in c["cards"]) + "</div>"]
    rows = [[cma.display_address(r[0]), money(r[1]), money(r[2]), money(r[3])] for r in c["summary_rows"]]  # CMA-233
    rows.append([c.get("subject_row_label", L("subject_row")), money(s["list_price"]), "—", f'{L("range_word")} {k(bl["low"])}–{k(bl["high"])}'])
    b += [table([L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")], rows, num_cols=(1, 2, 3),
                row_classes={len(rows) - 1: "subj"}), f'<p>{c["summary_paragraph"]}</p>']

    sc = R.get("scatter")
    if sc and homes:
        svg, info = cma.scatter(homes, sc, s["sqft"], s["list_price"], s.get("mls_address", s["address"]), (bl["low"], bl["high"]), L,
                                [cd["address"] for cd in R["comps"]["cards"]])
        C["scatter_labels"] = {"moved": info["labels_moved"], "overlapping": info["labels_overlapping"],  # CMA-205
                               "leader": info["labels_leader"], "dropped": info["labels_dropped"]}  # CMA-218
        trend =money(info["trend_at_subject"], 1000) if info["trend_at_subject"] else "N/A"
        share = L(compute.mls.r2_key(info["r2"])) if info["r2"] is not None else ""
        b += [f'<h3>{sc.get("heading", L("h_scatter"))}</h3>', f'<p>{sc["intro"].replace("{trend_at_subject}", trend)}</p>',
              '<div class="chart-box">' + cma.scatter_legend(L, sc.get("subject_label", s["address"]), info["counts"]) + svg + "</div>"]
        b += [n for n in (cma.excluded_note(info["excluded"], L), cma.trend_caption(info, s["list_price"], L)) if n]
        b.append(f'<p>{sc["after_paragraph"].replace("{trend_at_subject}", trend).replace("{r2_share}", share)}</p>')

    cp = R["competition"]
    b += [f'<h2>{L("h_competition")}</h2>', f'<p>{cp["intro"]}</p>',
          table([L("th_address"), L("th_status"), L("th_price"), L("th_sqft"), L("th_pool"), L("th_days"), L("th_notes")],
                [[cma.display_address(r[0]), r[1], money(r[2]), f"{int(r[3]):,}", r[4], r[5], r[6]] for r in cp["rows"]], num_cols=(2, 3, 5))]
    m = R["market"]
    b += [f'<h2>{L("h_market")}</h2>', f'<p>{m["intro"]}</p>',
          table(m["columns"], m["rows"], num_cols=tuple(range(1, len(m["columns"])))), ul(m["bullets"])]

    t, pay = R["costs"]["taxes"], C["payments"]
    b += [f'<h2>{L("h_costs")}</h2>']
    if t.get("heading"):
        b.append(f'<h3>{t["heading"]}</h3>')
    b.append(f'<p>{t["intro"]}</p>')
    bill = t.get("current_bill")  # optional: new construction and land-only bills have none
    seller_row = L("seller_bill", year=t["current_year"]) if t.get("current_year") else L("seller_bill_no_year")
    trows = [[seller_row, money(bill), money(bill / 12)] if bill else [seller_row, L("not_available"), "—"]]
    trows += [[L("your_bill", label=j["label"]), "≈ " + money(j["annual"], 100), "≈ " + money(j["annual"] / 12)] for j in C["taxes"]]
    homestead = homestead_label(R, L)
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
    prow = [[L("pay_cash")] + [money(r["cash_down"]) for r in rows_p],
            [L("pay_closing")] + [money(r["closing_costs"]) for r in rows_p],  # CMA-223
            [L("pay_cash_close")] + [money(r["cash_to_close"]) + cash_flag(r.get("cash_short"), pay, L) for r in rows_p],
            [L("pay_pi")] + [money(r["pi"]) for r in rows_p],
            [tax_row_label(R, pay, L)] + [money(r["tax"]) for r in rows_p],
            [L("pay_ins")] + [money(r["ins"]) for r in rows_p],
            [L("pay_flood")] + [money(r["flood"]) if r["flood"] is not None else L("pay_flood_quote") for r in rows_p],
            [L("pay_mi")] + [money(r["mi"]) for r in rows_p],
            [L("pay_hoa")] + [money(r["hoa"]) for r in rows_p],
            [L("pay_total")] + [money(r["total"]) for r in rows_p]]
    classes = {len(prow) - 1: "total"}
    if pay["alt_jurisdiction"]:
        prow.append([L("pay_if", short=pay["alt_jurisdiction"]["short"])] + [money(r["total"] + pay["alt_jurisdiction"]["delta_monthly"]) for r in rows_p])
        classes[len(prow) - 1] = "alt"
    progs = finance.LOAN_PROGRAMS
    conv_down = next((sc["down_pct"] for sc in R["costs"]["payment"]["scenarios"]
                      if finance.program(sc["type"]) == "conventional" and sc["down_pct"] < 0.2), 0.05)  # OFR-25
    pay_note = L(
        "pay_note", rate=f'{pay["rate"]:.2f}', ins=money(pay["insurance_annual"]),
        pmi=f'{finance.annual_mi_rate("conventional", conv_down) * 100:g}', pmi_down=f"{conv_down * 100:g}",
        mip=f'{progs["fha"]["annual_mi"] * 100:.2f}', ufmip=f'{progs["fha"]["upfront_fee"] * 100:.2f}', per10k=money(pay["per_10k"], 5))
    pay_note += " " + pay_closing_note(pay, L)
    if R["costs"]["payment"].get("note"):  # CMA-226: the agent's note adds to the assumptions, never replaces them
        pay_note += " " + R["costs"]["payment"]["note"]
    pay_note += tax_which_note(pay, L) + " " + pay["flood"]["note"]  # CMA-6: the flood rule, and "get a quote" until there is one
    b += [f'<h3>{L("h_payment")}</h3>', f'<p>{R["costs"]["payment"]["intro"]}</p>',
          table([L("pay_header", price=money(pay["price"]), basis=basis_label(pay, L))] + [r["label"] for r in rows_p], prow,
                num_cols=tuple(range(1, len(rows_p) + 1)), row_classes=classes),
          f'<p class="note">{pay_note}</p>']
    if C["credit"]:
        b += credit_section(R, C, L)

    w = R["watch"]
    b += [f'<h2>{L("h_watch")}</h2>', ul(w["items"], "plain watch"),
          f'<h3>{L("h_questions")}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in w["questions"]) + "</ol>"]
    return b


def closing(R, C, agent, L):
    """How This Was Prepared, the footer and the closing notices kept together, so the notices never sit alone on a
    last page (CMA-276, as seller-cma)."""
    return ('<div class="kg sec">' + f'<h2>{L("h_method")}</h2>' + "".join(f"<p>{p}</p>" for p in R["method"])
            + footer_block(agent, R, L) + render.notices(agent, cma.report_notices(C)) + "</div>")


def theme_css(agent):
    """Buyer palette from the agent's brand; the subject home is black (shared/cma.css), never a second hue or a status
    color (DS-3)."""
    t = design.theme(agent.get("brand"), "buyer")
    return design.css_vars(t), t


def fill_values(C, L):
    """CMA-203: every {placeholder} the report's wording may use, filled in every field, not just page 1."""
    values = dict(C.get("placeholders") or cma.page_one_values(C))
    if C.get("trend"):
        values.update(trend_at_subject=C["trend"]["at_subject_display"], r2_share=L(C["trend"]["r2_key"]))
    return values


def build_html(R, C, homes, agent):
    L = cma.Labels(ASSETS, R.get("labels"))
    R = {**cma.fill({k: v for k, v in R.items() if k != "labels"}, fill_values(C, L)), "labels": R.get("labels")}
    R.setdefault("prepared_date", f"{date.today():%B %-d, %Y}")
    vars_css, _ = theme_css(agent)
    content = ('<div class="wrap">' + summary_page(R, C, agent, L) + '<div class="pb"></div>' +
               cma.group_blocks(body(R, C, homes, agent, L)) + closing(R, C, agent, L) + "</div>")
    title = f'{L("doc_label")}: {R["subject"]["address"]}'
    doc = render.page(content, css=cma.css(), title=title, theme_css=vars_css)
    return doc.replace("<html>", '<html lang="en">', 1), L


def profile_check(agent):
    """CMA-221 (as seller-cma's CMA-263): a chat reminder when the name or brokerage is missing, or None. Never printed
    in the PDF: it simply leaves the missing parts out."""
    gaps = [w for w, f in (("agent name", "name"), ("brokerage", "brokerage")) if not agent.get(f)]
    if not gaps:
        return None
    return (f"{'no profile' if len(gaps) == 2 else 'profile incomplete'}: {' and '.join(gaps)} missing, so the PDF "
            "carries none. Ask the agent for them (or use their saved profile with --profile) and render again.")


def build(R, fmt, out_dir, ctx):
    market, homes = compute.load_inputs(R, ctx.get("mls"), ctx.get("data_file"))
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
    if not info["summary_page"]["fits"]:
        print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
    elif info["summary_page"]["fit_level"]:
        print(f"Page 1 ran long and was tightened (step {info['summary_page']['fit_level']} of 3) to fit.", file=sys.stderr)
    pages = cma.page_fill(path)  # CMA-274: how full each printed page is, from the PDF
    if pages is None and info["moved"]:  # no pdftotext here: the old information line
        print("Kept together on a new page (information; check that page for a large empty gap): " + "; ".join(info["moved"]), file=sys.stderr)
    for c in cma.page_checks(pages or [], "the watch items, the questions or the method"):
        print(f"Check: {c}", file=sys.stderr)
    labels = C.get("scatter_labels") or {}
    for text, asked, used in labels.get("moved", []):
        where = f"still {used}" if used.split(",")[0] == asked else f"placed {used}, not {asked},"
        print(f"Chart label {text!r}: {where} to clear the markers (information).", file=sys.stderr)
    for text, side in labels.get("leader", []):
        print(f"Chart label {text!r}: no clear spot beside its point, so it sits farther off to the {side} with a thin "
              "line to it (information).", file=sys.stderr)
    for text in labels.get("dropped", []):
        print(f"Chart label {text!r} left off: no clear spot even on a line, and the legend names the home "
              "(information).", file=sys.stderr)
    for text in labels.get("overlapping", []):
        print(f"Check: chart label {text!r} still overlaps a marker or another label: shorten it or pick another side.",
              file=sys.stderr)
    for w in C["warnings"]:
        print(f"Check: {w}", file=sys.stderr)
    if profile_check(agent):
        print(f"Check: {profile_check(agent)}", file=sys.stderr)
    return [path]


if __name__ == "__main__":
    try:
        render.main(build, formats=("pdf",), errors=(compute.ReportError, compute.mls.ExportError))
    except KeyError as e:
        sys.exit(f"report.json is missing {e}")
