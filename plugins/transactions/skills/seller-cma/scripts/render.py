"""Seller CMA files: the report PDF (page 1 summary, then the full analysis) and the listing presentation PPTX.

    python3 scripts/render.py report.json [--format pdf|pptx|all] [--agent agent-profile.md]
        [--market market-profile.md] [--sample] [--out DIR]

report.json holds the written content and the few inputs the numbers come from (see
references/report-data.md); `export` in it is the path to the MLS export, and `deck` holds the
listing presentation's wording (or a path to it, see references/deck-content.md). Every number is
computed by compute.py, never typed, so the PDF and the deck always agree. Prints the paths written,
then layout notes and checks on stderr.
"""
import html
import json
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
import deck  # noqa: E402
from _shared import cma, design, finance, handoff, render  # noqa: E402

ASSETS = compute.ASSETS
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
    s, rec = R["subject"], R["recommendation"]
    sp = cma.fill(R["summary_page"], cma.page_one_values(C))
    strats, ri = C["strategies"], C["recommended_index"]
    cash = C["net"]["cash_at_closing"]
    tile = L("sum_cash_tile" if cash else "sum_net_tile", price=money(rec["list_price"]))
    stats = list(sp["key_stats"])[:3] + [[C["recommended_net_display"], tile]]
    left = agent_block(agent, L)
    tags = f'<span class="tag prelim">{L("preliminary")}</span><br>' if C["preliminary"] else ""
    o = ['<div class="onepage">',
         f'<header class="top"><div>{left}</div><div class="prep">{tags}'
         f'{esc(sp.get("label", L("sum_label")))}<br>{L("prepared")} {esc(R["prepared_date"])}</div></header>',
         cma.subject_heading(s),
         '<div class="sp-hero"><div class="sp-rec">'
         f'<div class="lbl">{L("sum_rec")}</div><div class="price">{money(rec["list_price"])}</div>'
         f'<div class="line">{L("sum_range_line")} <b>{money(rec["low"])} – {money(rec["high"])}</b></div>'
         f'<div class="line">{L("sum_expected")} <b>{sp["expected_sale"]}</b></div>'
         f'<div class="line" style="margin-top:6px">{sp["headline"]}</div></div>'
         '<div class="sp-stats">' + "".join(f'<div class="sp-stat"><b>{v}</b><span>{lbl}</span></div>' for v, lbl in stats) + "</div></div>",
         f'<div class="sp-h">{L("sum_comps_h")} <span style="font-weight:400;color:var(--muted)">· {L("sum_shaded")}</span></div>',
         '<div class="sp-dot">' + cma.dotplot(R["comps"]["cards"], rec["low"], rec["high"], rec["list_price"],
                                             L("dot_rec", price=money(rec["list_price"]))) + "</div>"]
    rows = "".join(f'<tr class="{"rec" if x["recommended"] else ""}"><td>{x["list_price_display"]}{" ★" if x["recommended"] else ""}</td>'
                   f'<td>{x["time"]}</td><td class="n">{x["expected_sale_display"]}</td><td class="n">{x["net_display"]}</td></tr>'
                   for x in strats)
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{L("sum_why")}</div>{ul(sp["why"], "")}</div>'
             f'<div class="sp-table"><div class="sp-h">{L("sum_options")}</div><div class="tbl"><table><thead><tr>'
             f'<th>{L("th_list_at")}</th><th>{L("th_time_short")}</th><th class="n">{L("th_expected")}</th>'
             f'<th class="n">{L("th_est_cash" if cash else "th_est_net")}</th></tr></thead><tbody>{rows}</tbody></table></div>'
             f'<div class="note">{L("sum_options_note_cash" if cash else "sum_options_note")}</div></div></div>')
    o.append(f'<div class="sp-h">{L("sum_first")}</div><div class="sp-steps">' +
             "".join(f'<div class="sp-step"><b>{h}</b>{d}</div>' for h, d in sp["first_steps"]) + "</div>")
    o.append(f'<div class="sp-next"><span><b>{L("sum_next")}</b> {sp["next_step"]}</span></div>')
    note = L("sum_disclaimer") + (" " + L("sum_preliminary") if C["preliminary"] else "")
    o.append(f'<div class="note" style="margin-top:6px">{note}</div></div>')
    return "".join(o)


def pricing_section(R, C, L):
    p, strats, net = R["pricing"], C["strategies"], C["net"]
    cash = net["cash_at_closing"]
    b = [f'<h2>{L("h_pricing")}</h2>', f'<p>{p["intro"]}</p>',
         table([L("th_strategy"), L("th_time"), L("th_expected"), L("th_cash" if cash else "th_net"), L("th_expect")],
               [[f'<strong>{x["label"]}</strong>', x["time"], x["expected_sale_display"], x["net_display"], x["note"]] for x in strats],
               num_cols=(2, 3), row_classes={C["recommended_index"]: "total"}),
         f'<p class="note">{L("pricing_note_cash" if cash else "pricing_note")} {p.get("note", "")}</p>',
         f'<h3>{L("h_net")}</h3>', f'<p>{p.get("net_intro") or L("net_intro")}</p>']
    rows = [[r["label"]] + r["display"] for r in net["rows"]]
    b.append(table([L("th_at_closing")] + [x["label"] for x in strats], rows, num_cols=tuple(range(1, len(strats) + 1)),
                   row_classes={len(rows) - 1: "total"}))
    notes = net["notes"] + ([p["net_note"]] if p.get("net_note") else [])
    b.append(f'<p class="note">{" ".join(notes)}</p>')
    return b


def payments_section(R, C, L):
    pay, bp = C["payments"], R["buyer_payment"]
    mi_rate = finance.LOAN_PROGRAMS[pay["loan_type"]]["annual_mi"]
    mi = L("pay_note_mi", mi=f"{mi_rate * 100:g}") if mi_rate and not (pay["loan_type"] == "conventional" and pay["down_pct"] >= 0.20) else ""
    note = bp.get("note") or L("pay_note", program=L("prog_" + pay["loan_type"]), down=f'{pay["down_pct"] * 100:g}', rate=f'{pay["rate"]:.2f}',
                               basis=pay["tax_basis"], ins=money(pay["insurance_annual"]), mi=mi)
    if pay["tax_estimated"]:
        note += " " + L("tax_estimated", basis=pay["tax_basis"])
    return [f'<h3>{L("h_payments")}</h3>',
            f'<p>{L("pay_intro", per10k=pay["per_10k_display"], down10k=pay["down_per_10k_display"])}</p>',
            table([L("th_list_price"), L("th_down", down=f'{pay["down_pct"] * 100:g}'), L("th_payment")],
                  [[r["list_price_display"], r["down_display"], r["payment_display"]] for r in pay["rows"]], num_cols=(0, 1, 2),
                  row_classes={C["recommended_index"]: "total"}),
            f'<p class="note">{note}</p>']


def body(R, C, homes, agent, L):
    """The report after page 1, as a list of top-level blocks (grouped for pagination afterwards)."""
    s, rec = R["subject"], R["recommendation"]
    b = [f'<h2>{L("h_home")}</h2>',
         '<div class="facts">' + "".join(f"<div><span>{a}</span><b>{v}</b></div>" for a, v in s["facts"]) + "</div>",
         f'<p>{s["summary"]}</p>',
         f'<h2>{L("h_bottom")}</h2>',
         f'<div class="verdict"><div class="range">{L("verdict_price", price=money(rec["list_price"]))}</div>'
         f'<div class="mid">{L("verdict_caption", low=money(rec["low"]), high=money(rec["high"]))}</div><p>{rec["paragraph"]}</p></div>']
    if R.get("means"):
        b += [f'<h3>{L("h_means")}</h3>', ul(R["means"])]

    c = R["comps"]
    b += [f'<h2>{L("h_compared")}</h2>', f'<p>{c["intro"]}</p>', f'<p class="note">{c["method_note"]}</p>',
          '<div class="comps2">' + "".join(
              f'<div class="comp"><div class="comp-h"><b>{esc(cd["address"])}</b><span class="adj">{L("adjusted")} {money(cd["adjusted"])}</span></div>'
              f'<div class="meta">{cd["meta"]}</div>{ul(cd["bullets"], "")}</div>' for cd in c["cards"]) + "</div>"]
    rows = [[r[0], money(r[1]), money(r[2]), money(r[3])] for r in c["summary_rows"]]
    rows.append([c.get("subject_row_label", L("subject_row")), money(rec["list_price"]), "—", f'{L("range_word")} {k(rec["low"])}–{k(rec["high"])}'])
    b += [table([L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")], rows, num_cols=(1, 2, 3),
                row_classes={len(rows) - 1: "subj"}), f'<p>{c["summary_paragraph"]}</p>']

    sc = R.get("scatter")
    if sc and homes:
        sc = {"subject_label": L("subject_label"), **sc}
        svg, info = cma.scatter(homes, sc, s["sqft"], rec["list_price"], s.get("mls_address", s["address"]), (rec["low"], rec["high"]), L)
        trend = money(info["trend_at_subject"], 1000) if info["trend_at_subject"] else "N/A"
        share = L(compute.mls.r2_key(info["r2"])) if info["r2"] is not None else ""
        b += [f'<h3>{sc.get("heading", L("h_scatter"))}</h3>', f'<p>{sc["intro"].replace("{trend_at_subject}", trend)}</p>',
              '<div class="chart-box">' + cma.scatter_legend(L, sc["subject_label"]) + svg + "</div>"]
        note = cma.excluded_note(info["excluded"], L)
        if note:
            b.append(note)
        if sc.get("after_paragraph"):
            b.append(f'<p>{sc["after_paragraph"].replace("{trend_at_subject}", trend).replace("{r2_share}", share)}</p>')

    cp = R["competition"]
    b += [f'<h2>{L("h_competition")}</h2>', f'<p>{cp["intro"]}</p>',
          table([L("th_address"), L("th_status"), L("th_price"), L("th_sqft"), L("th_pool"), L("th_days"), L("th_notes")],
                [[r[0], r[1], money(r[2]), f"{int(r[3]):,}", r[4], r[5], r[6]] for r in cp["rows"]], num_cols=(2, 3, 5))]
    m = R["market"]
    b += [f'<h2>{L("h_market")}</h2>', f'<p>{m["intro"]}</p>',
          table(m["columns"], m["rows"], num_cols=tuple(range(1, len(m["columns"])))), ul(m["bullets"])]

    b += pricing_section(R, C, L)
    b += payments_section(R, C, L)

    b += [f'<h2>{L("h_prep")}</h2>', f'<p>{R["prep"]["intro"]}</p>', ul(R["prep"]["items"], "plain watch"),
          f'<h3>{L("h_needs")}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in R["needs"]) + "</ol>",
          f'<h2>{L("h_method")}</h2>'] + [f"<p>{x}</p>" for x in R["method"]]
    b.append(footer_block(agent, R, L))
    return b


def theme_css(agent):
    """Seller palette from the agent's brand; the subject home uses the palette's neutral 'both' party color, never the brand."""
    t = design.theme(agent.get("brand"), "seller")
    extra = (":root{--subject:var(--party-both);--subject-bg:var(--party-both-bg)}"
             ".prep .tag.prelim{color:var(--caution-strong);border-color:var(--caution-strong)}")
    return design.css_vars(t) + extra, t


def build_html(R, C, homes, agent):
    L = cma.Labels(ASSETS, R.get("labels"))
    R.setdefault("prepared_date", f"{date.today():%B %-d, %Y}")
    vars_css, _ = theme_css(agent)
    content = ('<div class="wrap">' + summary_page(R, C, agent, L) + '<div class="pb"></div>' +
               cma.group_blocks(body(R, C, homes, agent, L)) + "</div>")
    title = f'{L("doc_label")}: {R["subject"]["address"]}'
    doc = render.page(content, css=cma.css(), title=title, theme_css=vars_css)
    return doc.replace("<html>", '<html lang="en">', 1), L


def footer_label(R, C, agent, L, doc_label, sample):
    label = " · ".join(x for x in (R["subject"]["address"], doc_label,
                                   ", ".join(str(agent[f]) for f in ("name", "brokerage") if agent.get(f))) if x)
    if C["preliminary"]:
        label = L("preliminary").upper() + " · " + label
    if sample:
        label = "SAMPLE DATA · " + label
    return label


def build(R, fmt, out_dir, ctx):
    try:
        return _build(R, fmt, out_dir, ctx)
    except KeyError as e:
        raise compute.ReportError(f"report.json is missing {e}") from e


def _build(R, fmt, out_dir, ctx):
    market, homes = compute.load_inputs(R, ctx.get("market"))
    C = compute.compute(R, market, homes)
    if C["payments"] is None:
        raise compute.ReportError("Buyer payments need a property tax rate: " + "; ".join(C["warnings"]))
    if C["net"]["incomplete"]:
        raise compute.ReportError("The net sheet needs brokerage terms: ask the agent for the listing fee and the buyer's agent "
                                  "compensation (0 is fine) and put them in costs. Without them every net overstates the seller's proceeds.")
    agent, sample = ctx["agent"], ctx.get("sample") or R.get("sample")
    L = cma.Labels(ASSETS, R.get("labels"))
    first = fmt == (ctx.get("formats") or [fmt])[0]  # --format all builds each format: write the handoff and warn once
    written = []
    if first:
        hpath = os.path.join(out_dir, handoff.filename(R["subject"]["address"]))
        with open(hpath, "w", encoding="utf-8") as f:
            json.dump(C["handoff"], f, indent=2)
        for w in C["warnings"]:
            print(f"Check: {w}", file=sys.stderr)
    if fmt == "pdf":
        doc, L = build_html(R, C, homes, agent)
        path = os.path.join(out_dir, render.filename(R["subject"]["address"], "Seller CMA", ext="pdf"))
        info = render.html_to_pdf(doc, path, margins=cma.PAGE_MARGINS, footer_html=render.footer(footer_label(R, C, agent, L, L("doc_label"), sample)),
                                  before_print=cma.paginate)
        written.append(path)
        if not info["summary_page"]["fits"]:
            print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
        elif info["summary_page"]["fit_level"]:
            print(f"Page 1 ran long and was tightened (step {info['summary_page']['fit_level']} of 3) to fit.", file=sys.stderr)
        if info["moved"]:
            print("Kept together on a new page (information; check that page for a large empty gap): " + "; ".join(info["moved"]), file=sys.stderr)
    elif fmt == "pptx":
        path = os.path.join(out_dir, render.filename(R["subject"]["address"], "Listing Presentation", ext="pptx"))
        D = deck.deck_data(R, C, homes, agent, L, footer_label(R, C, agent, L, "", sample))
        deck.build_pptx(D, path)  # a DeckError keeps the PDF and names the problem (render.main)
        written.append(path)
    return written + ([hpath] if first else [])


def main(argv=None):
    return render.main(build, formats=("pdf", "pptx"), argv=argv,
                       errors=(compute.ReportError, deck.DeckError, compute.mls.ExportError))


if __name__ == "__main__":
    main()
