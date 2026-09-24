"""Contract timeline PDF (buyer or seller view).

    python3 scripts/render.py deal.json [--agent agent-profile.md] [--market market-profile.md] [--sample] [--out DIR]

Page 1: the contract period, when the contingencies end, a timeline strip and every key date.
Page 2: every deadline with its source, rule, action and consequence; amendment history; how the
dates were computed. Colors follow the agent's brand (buyer or seller side).
"""
import html
import os
import sys
from datetime import datetime, time, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline  # noqa: E402
from _shared import design, render  # noqa: E402

esc = html.escape
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "timeline.css")
PAGE1_LIMIT = 989  # px available on page 1 at the print viewport


def _when(row):
    return datetime.strptime(row["when"], "%Y-%m-%d %H:%M")


def day_label(row):
    return "—" if row.get("day") is None else f"Day {row['day']}"


def strip(t, colors):
    """Horizontal timeline from the Effective Date to the last date; labels in free slots above/below."""
    dated = t["rows"]
    eff = datetime.strptime(t["effective"]["date"], "%Y-%m-%d")
    end = max(_when(x) for x in dated) + timedelta(days=1)
    W, L, R, LV, STEP = 740, 30, 40, 3, 15
    mid = 18 + LV * STEP + 6
    H = mid + 24 + LV * STEP + 14
    span = (end - eff).total_seconds()

    def X(dt):
        return L + (dt - eff).total_seconds() / span * (W - L - R)

    groups = {}  # deadlines on the same day share one marker and one label
    for row in dated:
        groups.setdefault(_when(row).date(), []).append(row)
    s = [f'<svg viewBox="0 0 {W} {H}" class="strip"><line x1="{L}" x2="{W - R}" y1="{mid}" y2="{mid}" stroke="var(--grey-light)" stroke-width="3"/>']
    d = eff
    while d <= end:
        x = X(d)
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mid - 4}" y2="{mid + 4}" stroke="var(--grey-light)"/>'
                 f'<text x="{x:.1f}" y="{mid + 13}" class="tk" text-anchor="middle">{d:%b %-d}</text>')
        d += timedelta(days=7)
    placed = {}
    slots = [(side, lv) for lv in range(LV) for side in ("up", "down")]
    for i, rows in enumerate(groups.values()):
        row = next((r for r in rows if r["key"] == "closing"), None) or next((r for r in rows if r["critical"]), rows[0])
        when = _when(row)
        x = X(when)
        parties = {r["party"] for r in rows}
        col = colors.get(parties.pop(), colors["Both"]) if len(parties) == 1 else colors["Both"]
        names = row["short"] if len(rows) == 1 else f'{row["short"]} +{len(rows) - 1}' if len(rows) > 2 else \
            " / ".join(r["short"] for r in rows)
        text = f'{names} · {when:%-m/%-d}'
        w = len(text) * 4.75 + 8
        x0 = min(max(x - w / 2, 2), W - 2 - w)
        x1 = x0 + w
        pref = slots if i % 2 == 0 else [("down" if sd == "up" else "up", lv) for sd, lv in slots]
        slot = next((sl for sl in pref if all(x1 < a or x0 > b for a, b in placed.get(sl, []))), pref[-1])
        placed.setdefault(slot, []).append((x0, x1))
        side, lv = slot
        y = mid - 12 - lv * STEP if side == "up" else mid + 32 + lv * STEP  # below the tick labels (mid + 13)
        r = 6 if row["key"] == "closing" else 4.2
        critical = any(r_["critical"] for r_ in rows)
        s.append(f'<g><line x1="{x:.1f}" x2="{x:.1f}" y1="{mid}" y2="{y + (3 if side == "up" else -9)}" stroke="{col}" stroke-width=".7"/>'
                 f'<circle cx="{x:.1f}" cy="{mid}" r="{r}" fill="{col if critical else "#fff"}" stroke="{col}" stroke-width="1.6"/>'
                 f'<text x="{x0 + w / 2:.1f}" y="{y}" class="lbl" text-anchor="middle" style="fill:{col}">{esc(text)}</text></g>')
    s.append("</svg>")
    return "".join(s)


def party_pill(party, colors):
    col = colors.get(party, colors["Both"])
    return f'<span class="party" style="border-color:{col};color:{col}">{esc(party)}</span>'


def prepared_block(t, agent):
    lines = [f'Prepared for <b>{esc(t["client"])}</b> · {datetime.now():%B %-d, %Y}']
    if agent.get("name"):
        lines.append(f'<b>{esc(agent["name"])}</b>')
        org = " · ".join(esc(str(agent[f])) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {esc(str(agent["license"]))}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return "<br>".join(lines)


def build_html(t, agent, sample):
    side = t["side"]
    Side = side.title()
    theme = design.theme(agent.get("brand"), side)
    p = theme["party"]
    colors = {"Buyer": p["buyer"], "Seller": p["seller"], "Both": p["both"]}

    # the dates live in the hero; the contract terms run in one divider row, and missing ones drop out
    n = len(t["history"])
    terms = [t["price"], t["financing"], t["contract_label"], f'Escrow: {t["escrow_agent"]}' if t["escrow_agent"] else None,
             f'{n} amendment{"s" if n != 1 else ""}' if n else "No amendments"]
    snap_html = ('<div class="divrow factrow"><div>' + "".join(f"<span>{esc(str(x))}</span>" for x in terms if x) + "</div></div>")

    firm, first = t["contingencies_end"], t["first_deadline"]
    if side == "buyer":
        firm_label = "Your Contingencies End"
        lead = (f'Your protections run through <b>{esc(firm["display"])}</b> ({day_label(firm)}, {esc(firm["short"].lower())}). '
                "After that the deposit is at risk." if firm else "No buyer contingencies: the deposit is at risk from the start.")
    else:
        firm_label = "Buyer Can Cancel Until"
        lead = (f'The buyer can cancel under a contingency until <b>{esc(firm["display"])}</b> ({day_label(firm)}, '
                f'{esc(firm["short"].lower())}). After that the deal is firm unless the buyer defaults.'
                if firm else "No buyer contingencies: the deal is firm once the deposit is in.")
    if first:
        lead += f' {esc(first["short"])} due {esc(first["date_display"])} ({day_label(first)}).'
    hero = (f'<div class="hero"><div class="hl"><span class="k">Effective Date → Closing</span>'
            f'<div class="big">{t["effective"]["short"]} → {t["closing"]["long"]} · {t["length_days"]} days</div>'
            f'<div class="why">{lead}</div></div>'
            f'<div class="hr"><span class="k">{firm_label}</span><b>{esc(firm["display"]) if firm else "—"}</b>'
            f'{f" <span class=sm>({day_label(firm)})</span>" if firm else ""}'
            f'<span class="k" style="margin-top:6px">Closing</span><div><b>{esc(t["closing"]["display"])}</b> '
            f'<span class="sm">({day_label(t["closing"])})</span></div></div></div>')

    key_rows = "".join(
        f'<tr class="{"mine" if r["party"] == Side else ""}"><td class="n"><b>{esc(r["display"])}</b></td><td class="n">{day_label(r)}</td>'
        f'<td>{esc(r["label"])}{"&nbsp;<span class=crit>★</span>" if r["critical"] else ""}'
        f'{(" <span class=was>was " + esc(r["was"]) + "</span>") if r["was"] else ""}</td>'
        f'<td>{party_pill(r["party"], colors)}</td></tr>' for r in t["rows"])
    pending = "".join(f'<div class="note-caution"><b>{esc(r["label"])}:</b> {esc(r["rule"])}. {esc(r["action"])}.</div>'
                      for r in t["pending"])
    flags = "".join(f'<div class="note-caution"><b>Check:</b> {esc(f)}</div>' for f in t["flags"])
    amended = (f'<div class="note-good"><b>Includes {len(t["history"])} amendment(s).</b> Dates that moved show "was". '
               "See the amendment history for details.</div>") if t["history"] else ""
    legend = "".join(f'<span><i style="background:{colors[k]};border-radius:50%"></i>{k}</span>' for k in ("Buyer", "Seller", "Both"))

    page1 = f'''{hero}
<h2>Timeline <span class="h2s">Effective Date → Closing</span></h2>
<div class="panel" style="padding:2px 6px">{strip(t, colors)}</div>
<div class="legend">{legend}<span>Filled Dot = Critical Deadline</span></div>
<h2>All Key Dates <span class="h2s">Day = calendar days after the Effective Date · ★ = Critical · {side} items highlighted</span></h2>
<div class="tbl"><table class="kd"><colgroup><col style="width:22%"><col style="width:9%"><col style="width:57%"></colgroup>
<thead><tr><th class="n">Date</th><th class="n">Day</th><th>Deadline</th><th>Who</th></tr></thead><tbody>{key_rows}</tbody></table></div>
<div class="sm" style="margin-top:3px"><span class="crit">★</span> Critical = missing it can cost a contract right (such as the right to cancel) or put the deposit at risk.</div>
{pending}{amended}{flags}'''

    detail_rows = "".join(
        f'<tr><td class="n"><b>{esc(r["display"])}</b><br><span class="sm">{day_label(r)}</span>'
        f'{("<br><span class=was>was " + esc(r["was"]) + "</span>") if r["was"] else ""}</td>'
        f'<td><b>{esc(r["label"])}</b>{"&nbsp;<span class=crit>★</span>" if r["critical"] else ""}<br><span class="sm">{esc(r["source"])}</span></td>'
        f'<td>{esc(r["party"])}</td><td class="sm">{esc(r["rule"])}{("<br><i>" + esc(r["note"]) + "</i>") if r["note"] else ""}</td>'
        f'<td class="sm">{esc(r["action"])}</td><td class="sm">{esc(r["if_missed"])}</td></tr>' for r in t["rows"] + t["pending"])
    if t["history"]:
        hist = "".join(f'<tr><td class="c"><b>#{i}</b></td><td>{esc(str(h["date"] or "—"))}</td><td>{esc(h["description"])}</td>'
                       f'<td class="sm">{esc(h["summary"])}</td></tr>' for i, h in enumerate(t["history"], 1))
        hist_html = ('<h2>Amendment History <span class="h2s">moved dates show the original as "was"</span></h2>'
                     '<div class="tbl"><table><colgroup><col style="width:5%"><col style="width:12%"><col style="width:33%"></colgroup>'
                     f'<thead><tr><th class="c">#</th><th>Signed</th><th>Amendment</th><th>Changes</th></tr></thead><tbody>{hist}</tbody></table></div>')
    else:
        hist_html = ('<h2>Amendment History</h2><p class="sm">No amendments recorded. When an amendment or extension is signed, '
                     "add it to the deal file and re-run this report.</p>")
    eff_source = t["effective"]["source"] or "confirm: date the last party signed or initialed and delivered the final counteroffer"
    method_rows = [("Effective Date", f'{t["effective"]["display"]}: {eff_source}')] + \
                  [(x["label"], x["text"]) for x in t["rules"]["lines"]]
    method = ('<div class="tbl"><table class="meth"><tbody>' +
              "".join(f"<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>" for a, b in method_rows) + "</tbody></table></div>")
    details = f'''<div class="pb"></div><div class="dh">Deadline Details</div>
<div class="sm" style="margin-bottom:4px"><span class="crit">★</span> Critical = missing it can cost a contract right or put the deposit at risk.</div>
<div class="tbl"><table class="det"><colgroup><col style="width:14%"><col style="width:20%"><col style="width:7%"><col style="width:19%"><col style="width:22%"></colgroup>
<thead><tr><th class="n">Date</th><th>Deadline · Source</th><th>Who</th><th>Rule</th><th>Action</th><th>If Missed</th></tr></thead><tbody>{detail_rows}</tbody></table></div>
{hist_html}
<h2>How the Dates Were Computed</h2>{method}
<div class="fine">Computed from the executed contract, riders and counteroffers as recorded in the deal file. Verify every date against the documents and with the escrow or title agent; the form version and any handwritten changes control. Time rules follow {esc(t["rules"]["family"])}. Lender dates are estimates. Not legal advice.</div>'''

    title = (f'Contract Timeline <span class="viewtag">{Side} View</span>'
             f'{"<span class=sample>SAMPLE DATA</span>" if sample else ""}')
    parties = " / ".join(x for x in (t["buyer"] or "Buyer", t["seller"] or "Seller"))
    body = (f'<header><div><div class="t1">{title}</div><div class="t2">{esc(t["property"])} · {esc(parties)}</div></div>'
            f'<div class="prep">{prepared_block(t, agent)}</div></header>{snap_html}<div class="p1">{page1}</div>{details}')
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    return render.page(body + render.notices(agent), css=css, title="Contract Timeline", theme_css=design.css_vars(theme),
                       body_class=side)


def fit_page_one(pg):
    """Measure page 1; switch to the compact layout when it would spill onto page 2."""
    top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > PAGE1_LIMIT:
        pg.evaluate("() => document.body.classList.add('compact')")
        top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    return top


def build(deal, fmt, out_dir, ctx):
    t = timeline.analyze(deal, ctx.get("market"))
    if not t["closing"]:
        raise timeline.DealError("The report needs the closing date: add contract.closing_date and re-run.")
    doc = build_html(t, ctx["agent"], ctx.get("sample") or t["sample"])
    name = render.filename(t["property"].split(",")[0], "Contract Timeline", t["side"], ext="pdf")
    path = os.path.join(out_dir, name)
    top = render.html_to_pdf(doc, path, footer_html=render.footer(f'Contract Timeline · {t["property"]}'),
                             before_print=fit_page_one)
    if top > PAGE1_LIMIT:
        print(f"Page 1 overflows by {top - PAGE1_LIMIT:.0f}px; the key-dates table continues on page 2.", file=sys.stderr)
    for flag in t["flags"]:
        print(f"Check (on the report): {flag}", file=sys.stderr)
    for note in t["agent_notes"]:
        print(f"For the agent (not printed): {note}", file=sys.stderr)
    return [path]


if __name__ == "__main__":
    render.main(build, formats=("pdf",), errors=(timeline.DealError,))
