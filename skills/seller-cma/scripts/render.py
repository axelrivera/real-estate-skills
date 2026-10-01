"""Seller CMA files: the report PDF (page 1 summary, then the full analysis) and the listing presentation PPTX
(with a PDF copy of the slides when LibreOffice is available).

    python3 scripts/render.py report.json [--format pdf|pptx|all] [--profile profile.md]
        [--sample] [--out DIR]

report.json holds the written content and the few inputs the numbers come from (see
references/report-data.md); `export` in it is the path to the MLS export, and `deck` holds the
listing presentation's wording (or a path to it, see references/deck-content.md). Every number is
computed by compute.py, never typed, so the PDF and the deck always agree. Prints the paths written,
then layout notes and checks on stderr.
"""
import html
import os
import sys
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compute  # noqa: E402
import deck  # noqa: E402
from _shared import cma, design, finance, render  # noqa: E402

ASSETS = compute.ASSETS
money, table, ul, k = finance.money, cma.table, cma.ul, cma.k
adj = compute.adjusted_money  # CMA-289: adjusted values to $100
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


def summary_page(R, C, agent, L):
    s, rec = R["subject"], R["recommendation"]
    sp = R["summary_page"]  # placeholders already filled (build_html)
    strats, ri = C["strategies"], C["recommended_index"]
    cash, free = C["net"]["cash_at_closing"], C["net"]["no_mortgage"]
    held = "_holding" if C["net_basis"] == "after_holding" else ""  # CMA-298: nets after holding costs, as the reply quotes them
    tile = L(("sum_cash_free_tile" if free else "sum_cash_tile" if cash else "sum_net_tile") + held, price=money(rec["list_price"]))
    if C["net"]["standard_terms"]:  # CMA-18: every place a net shows says the brokerage isn't the listing agreement's yet
        tile += f" ({L('sum_standard_terms')})"
    stats = list(sp.get("key_stats") or [])[:3]
    # CMA-261: without an export there's no sale-to-list ratio or days-on-market trend: the comps fill the empty tiles
    fallback = [[C["median_adjusted_display"], L("sum_stat_median", n=C["n_comps"])],
                [f'{k(C["adjusted_min"])}–{k(C["adjusted_max"])}', L("sum_stat_span")],
                [str(C["n_comps"]), L("sum_stat_comps")]]
    stats += [f for f in fallback if f[1] not in {x[1] for x in stats}][:3 - len(stats)]
    stats += [[C["recommended_net_display"], tile]]
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
    stay = (C.get("reprice") or {}).get("stay_index")  # CMA-273: the Stay row reads "Stay at $474,900", as in the full table
    rows = "".join(f'<tr class="{"rec" if x["recommended"] else ""}"><td>'
                   f'{L("sum_stay", price=x["list_price_display"]) if i == stay else x["list_price_display"]}{" ★" if x["recommended"] else ""}</td>'
                   f'<td>{x["time"]}</td><td class="n">{x["expected_sale_display"]}</td><td class="n">{x["net_after_holding_display"]}</td></tr>'
                   for i, x in enumerate(strats))
    opts = C["options_summary"]  # CMA-336: the net column's header and footnote, the same words the chat template quotes
    o.append(f'<div class="sp-cols"><div><div class="sp-h">{L("sum_why")}</div>{ul(sp["why"], "")}</div>'
             f'<div class="sp-table"><div class="sp-h">{L("sum_options")}</div><div class="tbl"><table><thead><tr>'
             f'<th>{L("th_list_at")}</th><th>{L("th_time_short")}</th><th class="n">{L("th_expected")}</th>'
             f'<th class="n">{opts["net_header"]}</th></tr></thead><tbody>{rows}</tbody></table></div>'
             f'<div class="note">{opts["note"]}</div></div></div>')
    o.append(f'<div class="sp-h">{L("sum_first")}</div><div class="sp-steps">' +
             "".join(f'<div class="sp-step"><b>{h}</b>{d}</div>' for h, d in sp["first_steps"]) + "</div>")
    o.append(f'<div class="sp-next"><span><b>{L("sum_next")}</b> {sp["next_step"]}</span></div>')
    note = L("sum_disclaimer") + (" " + L("sum_preliminary", reason=C["preliminary_reason"]) if C["preliminary"] else "")
    o.append(f'<div class="note" style="margin-top:6px">{note}</div></div>')
    return "".join(o)


def pricing_section(R, C, L):
    p, strats, net = R["pricing"], C["strategies"], C["net"]
    cash = net["cash_at_closing"]
    held = "_holding" if C["net_basis"] == "after_holding" else ""  # CMA-298: the same nets as page 1 and the reply
    cash_note = L(("pricing_note_free" if net["no_mortgage"] else "pricing_note_cash") + held)
    b = [f'<h2>{L("h_pricing")}</h2>', f'<p>{p["intro"]}</p>',
         table([L("th_strategy"), L("th_time"), L("th_expected"), L("th_cash" if cash and not held else "th_net"), L("th_expect")],  # CMA-317
               [[f'<strong style="white-space:nowrap">{x["label"]}</strong>', x["time"], x["expected_sale_display"], x["net_after_holding_display"], x["note"]] for x in strats],
               num_cols=(2, 3), row_classes={C["recommended_index"]: "total"}),
         f'<p class="note">{(cash_note if cash else L("pricing_note" + held))} {p.get("note", "")}</p>',
         f'<h3>{L("h_net")}</h3>', f'<p>{p.get("net_intro") or L("net_intro")}</p>']
    rows = [[r["label"]] + r["display"] for r in net["rows"]]
    b.append(table([L("th_at_closing")] + [x["label"] for x in strats], rows, num_cols=tuple(range(1, len(strats) + 1)),
                   row_classes={i: "total" for i, r in enumerate(net["rows"]) if r["key"] in ("total", "after_holding")}))
    notes = net["notes"] + ([p["net_note"]] if p.get("net_note") else [])
    b.append(f'<p class="note">{" ".join(notes)}</p>')
    return b


def payments_section(R, C, L):
    pay = C["payments"]
    note = pay["basis_note"] + " " + pay["flood"]["note"]  # CMA-338: compute.py's basis line, as the chat template quotes it
    return [f'<h3>{L("h_payments")}</h3>',
            f'<p>{L("pay_intro", per10k=pay["per_10k_display"], down10k=pay["down_per_10k_display"])}</p>',
            table([L("th_list_price"), L("th_down", down=f'{pay["down_pct"] * 100:g}'), L("th_payment")],
                  [[r["list_price_display"], r["down_display"], r["payment_display"]] for r in pay["rows"]], num_cols=(0, 1, 2),
                  row_classes={C["recommended_index"]: "total"}),
            f'<p class="note">{note}</p>']


def body(R, C, homes, agent, L):
    """The report after page 1, as a list of top-level blocks (grouped for pagination afterwards)."""
    s, rec = R["subject"], R["recommendation"]
    # CMA-287: a reprice's or relist's price history (first price, the cut, days on market), named with the verdict
    history = (C.get("reprice") or C.get("relist") or {}).get("price_history")
    b = [f'<h2>{L("h_home")}</h2>',
         '<div class="facts">' + "".join(f"<div><span>{a}</span><b>{v}</b></div>" for a, v in s["facts"]) + "</div>",
         f'<p>{s["summary"]}</p>',
         f'<h2>{L("h_bottom")}</h2>',
         f'<div class="verdict"><div class="range">{L("verdict_price", price=money(rec["list_price"]))}</div>'
         f'<div class="mid">{L("verdict_caption", low=money(rec["low"]), high=money(rec["high"]))}</div>'
         + (f'<p class="note">{esc(history)}</p>' if history else "") + f'<p>{rec["paragraph"]}</p></div>']
    if R.get("means"):
        b += [f'<h3>{L("h_means")}</h3>', ul(R["means"])]

    c = R["comps"]
    b += [f'<h2>{L("h_compared")}</h2>', f'<p>{c["intro"]}</p>', f'<p class="note">{c["method_note"]}</p>',
          '<div class="comps2">' + "".join(
              f'<div class="comp"><div class="comp-h"><b>{esc(cma.display_address(cd["address"]))}</b><span class="adj">{L("adjusted")} {adj(cd["adjusted"])}</span></div>'
              f'<div class="meta">{cd["meta"]}</div>{ul(cd["bullets"], "")}</div>' for cd in c["cards"]) + "</div>"]
    rows = [[cma.display_address(r[0]), money(r[1]), money(r[2]), adj(r[3])] for r in c["summary_rows"]]
    rows.append([c.get("subject_row_label", L("subject_row")), money(rec["list_price"]), "—", f'{L("range_word")} {k(rec["low"])}–{k(rec["high"])}'])
    b += [table([L("th_sale"), L("th_sold_for"), L("th_seller_paid"), L("th_adjusted")], rows, num_cols=(1, 2, 3),
                row_classes={len(rows) - 1: "subj"}), f'<p>{c["summary_paragraph"]}</p>']

    sc = R.get("scatter")
    if sc and homes:
        sc = {"subject_label": L("subject_label"), **sc}
        svg, info = cma.scatter(homes, sc, s["sqft"], rec["list_price"], s.get("mls_address", s["address"]), (rec["low"], rec["high"]), L,
                                [cd["address"] for cd in R["comps"]["cards"]])
        checks, notes = scatter_checks(info)
        C.setdefault("render_checks", []).extend(checks)
        C.setdefault("render_check_keys", []).extend(["scatter_labels"] * len(checks))
        C.setdefault("render_notes", []).extend(notes)
        dropped = cma.callout_checks(info)  # CMA-299
        C["render_checks"].extend(dropped)
        C["render_check_keys"].extend(["callout_not_plotted"] * len(dropped))
        b += [f'<h3>{sc.get("heading", L("h_scatter"))}</h3>', f'<p>{sc["intro"]}</p>',
              '<div class="chart-box">' + cma.scatter_legend(L, sc["subject_label"], info["counts"]) + svg + "</div>"]
        b += [n for n in (cma.excluded_note(info["excluded"], L), cma.trend_caption(info, rec["list_price"], L)) if n]
        if sc.get("after_paragraph"):
            b.append(f'<p>{sc["after_paragraph"]}</p>')

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
          f'<h3>{L("h_needs")}</h3>', '<ol class="qs">' + "".join(f"<li>{q}</li>" for q in R["needs"]) + "</ol>"]
    return b


def closing(R, C, agent, L):
    """CMA-276: How This Was Prepared, the footer and the closing notices kept together, so the notices never sit
    alone on a last page."""
    return ('<div class="kg sec">' + f'<h2>{L("h_method")}</h2>' + "".join(f"<p>{x}</p>" for x in R["method"])
            + footer_block(agent, R, L) + render.notices(agent, cma.report_notices(C)) + "</div>")


def scatter_checks(info):
    """CMA-267: (checks, information): chart labels that still cover a marker (the subject's included) or another
    label, and labels placed on another side than asked because that side was crowded."""
    checks, notes = [], []
    if info.get("labels_overlapping") or info.get("crowded_labels"):
        names = list(dict.fromkeys([*(info.get("labels_overlapping") or []), *(info.get("crowded_labels") or [])]))
        checks.append("Scatter labels still cover a marker or another label (" + ", ".join(names) + "): drop that "
                      "callout or shorten its label, then render again.")
    moved = [m for m in info.get("labels_moved") or [] if m[0] not in (info.get("labels_overlapping") or [])]
    if moved:
        notes.append("Scatter labels moved to stay clear of markers (information; the side is a preference): "
                     + "; ".join(f"{t} ({_moved_words(a, u)})" for t, a, u in moved) + ".")
    return checks, notes


def _moved_words(asked, used):
    """CMA-285: 'left to right', 'right to left, a line lower', or 'still left, a line lower' when only the line moved
    (the placer gives the side used, plus any line shift after a comma)."""
    side, _, shift = used.partition(", ")
    if side == asked:
        return f"still {side}" + (f", {shift}" if shift else "")
    return f"{asked} to {used}"


def theme_css(agent):
    """Seller palette from the agent's brand; the subject home is black (shared/cma.css), never a second hue."""
    t = design.theme(agent.get("brand"), "seller")
    extra = ".prep .tag.prelim{color:var(--caution-strong);border-color:var(--caution-strong)}"
    return design.css_vars(t) + extra, t


def build_html(R, C, homes, agent):
    L = compute.labels(R)
    # CMA-265: every {placeholder} in the wording, filled in every field (compute.py warns on any it can't fill)
    R = {**cma.fill({key: v for key, v in R.items() if key != "labels"}, C["placeholders"]), "labels": R.get("labels")}
    R.setdefault("prepared_date", f"{date.today():%B %-d, %Y}")
    vars_css, _ = theme_css(agent)
    content = ('<div class="wrap">' + summary_page(R, C, agent, L) + '<div class="pb"></div>' +
               cma.group_blocks(body(R, C, homes, agent, L)) + closing(R, C, agent, L) + "</div>")
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


def profile_check(agent):
    """CMA-263: a chat reminder when the name or brokerage is missing, or None. Never printed in the files: they
    simply leave the missing parts out."""
    gaps = [w for w, f in (("agent name", "name"), ("brokerage", "brokerage")) if not agent.get(f)]
    if not gaps:
        return None
    return (f"{'no profile' if len(gaps) == 2 else 'profile incomplete'}: {' and '.join(gaps)} missing, so the files "
            "carry none. Ask the agent for them (or use their saved profile with --profile) and render again.")


def build(R, fmt, out_dir, ctx):
    try:
        return _build(R, fmt, out_dir, ctx)
    except KeyError as e:
        raise compute.ReportError(f"report.json is missing {e}") from e


def _build(R, fmt, out_dir, ctx):
    R.setdefault("prepared_date", f"{date.today():%B %-d, %Y}")  # the deck alone (--format pptx) needs it too
    market, homes = compute.load_inputs(R, ctx.get("mls"), ctx.get("data_file"))
    C = compute.compute(R, market, homes)
    if C["payments"] is None:
        raise compute.ReportError("Buyer payments need a property tax rate: " + "; ".join(C["warnings"]))
    if C["net"]["incomplete"]:
        raise compute.ReportError("The net sheet needs brokerage terms: ask the agent for the listing fee and the buyer's agent "
                                  "compensation (0 is fine) and put them in costs. Without them every net overstates the seller's proceeds.")
    agent, sample = ctx["agent"], ctx.get("sample") or R.get("sample")
    L = compute.labels(R)
    first = fmt == (ctx.get("formats") or [fmt])[0]  # --format all builds each format: warn once
    written = []
    if first:
        for w in C["warnings"]:
            print(f"Check: {w}", file=sys.stderr)
        if profile_check(agent):
            print(f"Check: {profile_check(agent)}", file=sys.stderr)
    if fmt == "pdf":
        doc, L = build_html(R, C, homes, agent)
        path = os.path.join(out_dir, render.filename(R["subject"]["address"], "Seller CMA", ext="pdf"))
        info = render.html_to_pdf(doc, path, margins=cma.PAGE_MARGINS, footer_html=render.footer(footer_label(R, C, agent, L, L("doc_label"), sample)),
                                  before_print=cma.paginate)
        written.append(path)
        for c in C.get("render_checks", []):
            print(f"Check: {c}", file=sys.stderr)
        for n in C.get("render_notes", []):
            print(n, file=sys.stderr)
        if not info["summary_page"]["fits"]:
            print("Page 1 doesn't fit on one page: shorten the summary wording (never drop an element).", file=sys.stderr)
        elif info["summary_page"]["fit_level"]:
            print(f"Page 1 ran long and was tightened (step {info['summary_page']['fit_level']} of 3) to fit.", file=sys.stderr)
        pages = page_fill(path)
        if pages is None and info["moved"]:  # no pdftotext here: the old information line
            print("Kept together on a new page (information; check that page for a large empty gap): " + "; ".join(info["moved"]), file=sys.stderr)
        for c in page_checks(pages or [], L):
            print(f"Check: {c}", file=sys.stderr)
    elif fmt == "pptx":
        path = os.path.join(out_dir, render.filename(R["subject"]["address"], "Listing Presentation", ext="pptx"))
        D = deck.deck_data(R, C, homes, agent, L, footer_label(R, C, agent, L, "", sample))
        checks = deck.build_pptx(D, path)  # a DeckError keeps the PDF and names the problem (render.main)
        written.append(path)
        for c in checks:
            print(f"Check: {c}", file=sys.stderr)
        pdf = deck.pptx_to_pdf(path, os.path.join(out_dir, render.filename(R["subject"]["address"], "Listing Presentation", ext="pdf")))
        if pdf:
            written.append(pdf)
        else:
            print("Check: the presentation PDF couldn't be made here (no LibreOffice); the PPTX is unaffected.", file=sys.stderr)
    return written


# CMA-274, CMA-276: page fill read back from the printed PDF (shared/cma.py)
page_fill = cma.page_fill


METHOD_ALONE = 0.5  # CMA-285: a last page this empty that starts at How This Was Prepared holds only the method
METHOD_CUT = 0.2  # ... flagged when cutting at most this share of a page would bring it back to the page before


def page_checks(pages, L=None):
    """The shared page checks, plus two for this report (CMA-285): the comp summary table starting a page apart from its
    comp cards, and a last page that holds only the method section."""
    checks = cma.page_checks(pages, "the needs list, the launch steps or the method")
    if not L or not pages:
        return checks
    squash = lambda t: " ".join(str(t).split()).lower()
    table_head = squash(" ".join(L(k) for k in ("th_sale", "th_sold_for", "th_seller_paid", "th_adjusted")))
    for i, (_, first) in enumerate(pages[1:], start=1):
        if squash(first).startswith(table_head):
            checks.append(f"The comp summary table starts page {i + 1}, apart from its comp cards on page {i}. Shorten the "
                          "comp cards' bullets or the comps intro so the table fits under the cards, then render again.")
    fill, first = pages[-1]
    over = pages[-2][0] + fill - 1 if len(pages) > 2 else 1  # how much the two pages hold beyond one page
    # only when a modest cut brings the method back: a full page before it can't take a third of a page more
    if cma.LONE_TAIL <= fill < METHOD_ALONE and over <= METHOD_CUT and squash(first).startswith(squash(L("h_method"))):
        checks.append(f"The last page (page {len(pages)}) holds only How This Was Prepared ({fill:.0%} full), and page "
                      f"{len(pages) - 1} is {pages[-2][0]:.0%} full. Cut about {max(over, 0.03) + 0.03:.0%} of a page from the "
                      "needs list, the before-we-list steps or the method paragraphs so it fits on the page before, then "
                      "render again.")
    return checks


def main(argv=None):
    return render.main(build, formats=("pdf", "pptx"), argv=argv, default="pdf",  # the deck only when asked for
                       errors=(compute.ReportError, deck.DeckError, compute.mls.ExportError))


if __name__ == "__main__":
    main()
