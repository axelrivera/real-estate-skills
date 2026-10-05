"""Contract timeline PDF (buyer or seller view) and closing calendar (.ics).

    python3 scripts/render.py deal.json [--format pdf|ics|all] [--profile profile.md] [--date YYYY-MM-DD] [--out DIR]
                              [--lender-dates]

The timeline is computed once (timeline.analyze, the document model); the PDF and the calendar only place it.
Page 1: the contract period, when the contingencies end, a timeline strip and every key date, then the Check lines.
Page 2: every deadline with its source, rule, action and consequence; amendment history; how the dates were computed.
Colors follow the agent's brand (buyer or seller side); text in the bundled font, measured with its metrics.
"""
import hashlib
import os
import sys
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline  # noqa: E402
from _shared import design, fmt, layout, render  # noqa: E402

esc = layout.esc
Raw = layout.Raw
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "timeline.css")

period_name, join_words, lbl = timeline.period_name, timeline.join_words, timeline.label


def sentence_case(label):
    """'HOA Disclosure' -> 'HOA disclosure': lower-case the words, keep acronyms (HOA, FHA/VA)."""
    return " ".join(w if w.isupper() else w.lower() for w in label.split())


def _when(row):
    return datetime.strptime(row["when"], "%Y-%m-%d %H:%M")


def _day(row):
    """The start of a deadline's day: the strip plots every deadline on its own day's tick, so 11:59 PM never reads as
    the next day."""
    return datetime.combine(_when(row).date(), time())


def page_one_rows(t):
    """The rows page 1 shows (the strip and Key Dates): every dated row except a cancel window that can no longer
    arise (Rider GG's once the agreement is signed, iteration 12). The Deadline Details table keeps it, marked done."""
    return [r for r in t["rows"] if not r.get("voided")]


def strip_span(t):
    """What the strip runs to: Closing when the closing is its last date, else its last deadline (a short sale waiting
    on approval runs to Contract Expires; a stay after closing to the possession date)."""
    last = max(page_one_rows(t), key=_when)
    if t["closing"] and _when(last).date() <= datetime.strptime(t["closing"]["date"], "%Y-%m-%d").date():
        return lbl("k_span")
    return f'Effective Date → {last["short"]}'


def day_label(row):
    return fmt.EMPTY if row.get("day") is None else lbl("day", n=row["day"])


# --- the timeline strip ----------------------------------------------------------------------

LABEL_PT = 8.6  # strip label size (timeline.css .strip .lbl), in the SVG's px
TICK_PT = 8  # tick label size (.strip .tk)


def _label_width(text):
    """A strip label's width in px (bold, the bundled font's metrics), plus room so labels never touch."""
    return layout.text_width(text, LABEL_PT, bold=True) + 8


def place_labels(marks, W, max_levels=4):
    """Places the strip labels: each (x, width) goes above or below the line at some level, never overlapping another
    label, and (when it can) without a leader line running through a nearer label. A label may slide sideways so its
    marker sits near one end. Uses the fewest levels that work. Returns ([(side, level, x0)], levels)."""
    for strict in (True, False):
        for levels in range(1, max_levels + 1):
            found = _place(marks, W, levels, strict)
            if found:
                return found, levels
    # still crowded at the most levels: labels overlap rather than a date being dropped
    return [(("up", "down")[i % 2], (i // 2) % max_levels, min(max(x - w / 2, 2), W - 2 - w))
            for i, (x, w) in enumerate(marks)], max_levels


def _place(marks, W, levels, strict, budget=20000):
    """Depth-first search over (side, level, shift) for each label in order, with a step budget."""
    slots = [(side, lv) for lv in range(levels) for side in ("up", "down")]
    placed, steps = [], [0]  # placed: (side, level, x0, x1, marker x)

    def fits(side, lv, x0, x1, x):
        for sd, l2, a, b, mx in placed:
            if sd != side:
                continue
            if l2 == lv and not (x1 + 4 < a or x0 > b + 4):
                return False
            # TL-228: leaders keep 6px clear of a label's ends, so a leader never looks like it runs into the text
            if strict and l2 < lv and a - 6 <= x <= b + 6:  # this leader would cross a nearer label
                return False
            if strict and l2 > lv and x0 - 6 <= mx <= x1 + 6:  # this label would sit on a farther leader
                return False
        return True

    def go(i):
        if i == len(marks):
            return True
        steps[0] += 1
        if steps[0] > budget:
            return False
        x, w = marks[i]
        pref = slots if i % 2 == 0 else [("down" if sd == "up" else "up", lv) for sd, lv in slots]
        for side, lv in pref:
            for shift in (0, -w / 2 + 5, w / 2 - 5, -w / 4, w / 4):
                x0 = min(max(x - w / 2 + shift, 2), W - 2 - w)
                if not x0 + 2 <= x <= x0 + w - 2 or not fits(side, lv, x0, x0 + w, x):
                    continue
                placed.append((side, lv, x0, x0 + w, x))
                if go(i + 1):
                    return True
                placed.pop()
        return False

    return [(sd, lv, x0) for sd, lv, x0, _, _ in placed] if go(0) else None


MIXED = "var(--text)"  # a strip label for deadlines owed by different parties on one day
DONE = "var(--muted)"  # every deadline on that day is done
PARTIES = ("Buyer", "Seller", "Both")


def strip_mixed(t):
    """True when some day on the strip names deadlines owed by different parties (the legend then explains the neutral
    color)."""
    groups = {}
    for r in page_one_rows(t):
        groups.setdefault(_when(r).date(), []).append(r)
    return any(len({r["party"] for r in g if not r.get("done")}) > 1 for g in groups.values())  # all done: gray


def strip(t, colors, chart=None):
    """Horizontal timeline from the Effective Date to the last date; labels in free slots above and below. Deadlines
    already done are drawn in gray. Each mark drawn is recorded on `chart` (a layout.Chart), so the legend names only
    what the strip shows."""
    chart = chart if chart is not None else layout.Chart()
    dated = page_one_rows(t)
    eff = datetime.strptime(t["effective"]["date"], "%Y-%m-%d")
    end = max(_day(x) for x in dated) + timedelta(days=1)
    W, L, R, STEP = 740, 30, 40, 13

    span = (end - eff).total_seconds()

    def X(dt):
        return L + (dt - eff).total_seconds() / span * (W - L - R)

    groups = {}  # deadlines on the same day share one marker and one label
    for row in dated:
        groups.setdefault(_when(row).date(), []).append(row)

    def label(rows, compact):
        """TL-228: a done deadline isn't named as if it were open: the label names the open rows on that day, or reads
        "Done" when every row is. `compact` names one row and counts the rest ("Loan Approval +1"). Returns the rows the
        label stands for too, which set its color."""
        open_rows = [r for r in rows if not r.get("done")]
        named = open_rows or rows
        row = (next((r for r in named if r["key"] == "closing"), None) or next((r for r in named if r["critical"]), None)
               or named[0])
        if not open_rows:
            return row, lbl("strip_done", name=row["short"]), named
        n = len(open_rows)
        names = row["short"] if n == 1 else f'{row["short"]} +{n - 1}' if n > 2 or compact else \
            " / ".join(r["short"] for r in open_rows)
        return row, lbl("strip_label", name=names, date=fmt.date_short(_when(row), year=False)), named

    def lay_out(compact):
        marks = []
        for rows in groups.values():
            row, text, named = label(rows, compact)
            marks.append(dict(rows=rows, named=named, row=row, x=X(_day(row)), text=text, w=_label_width(text)))
        return marks, place_labels([(m["x"], m["w"]) for m in marks], W)

    # full names when they fit on one level a side; a crowded strip names one deadline per day and counts the rest
    # when that takes fewer levels
    marks, (spots, levels) = lay_out(False)
    if levels > 1:
        tight = lay_out(True)
        if tight[1][1] < levels:
            marks, (spots, levels) = tight
    mid = 16 + levels * STEP
    H = mid + 26 + levels * STEP + 4
    s = [f'<svg viewBox="0 0 {W} {H}" class="strip"><line x1="{L}" x2="{W - R}" y1="{mid}" y2="{mid}" stroke="var(--grey-light)" stroke-width="3"/>']
    # TL-218: a leader running down to a label below the line crosses the tick labels' row; a tick label it would cross
    # is left out (the tick mark stays), so no date sits on a line
    crossed = []  # the x span of each such leader inside the tick labels' row (mid + 5 to mid + 15)
    for m, (side, lv, x0) in zip(marks, spots):
        if side == "down":
            x, ly = m["x"], mid + 21 + lv * STEP  # as drawn below: down to the label, bending halfway when it slid
            reach = min(max(x, x0 + 3), x0 + m["w"] - 3)
            if abs(x0 + m["w"] / 2 - x) > 1:
                knee = (ly + mid) / 2
                reach = x + (reach - x) * max(0.0, (mid + 15 - knee) / (ly - knee))
            else:
                reach = x
            crossed.append((min(x, reach), max(x, reach)))
    d = eff
    while d <= end:
        x = X(d)
        tick = fmt.date_short(d, year=False)
        tw = layout.text_width(tick, TICK_PT) / 2 + 2  # half the tick label's width, plus a gap
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mid - 4}" y2="{mid + 4}" stroke="var(--grey-light)"/>')
        if not any(a - tw <= x <= b + tw for a, b in crossed):
            s.append(f'<text x="{x:.1f}" y="{mid + 13}" class="tk" text-anchor="middle">{tick}</text>')
        d += timedelta(days=7)
    lines, dots, labels = [], [], []
    for m, (side, lv, x0) in zip(marks, spots):
        rows, row, x, w = m["rows"], m["row"], m["x"], m["w"]
        # the party of the deadlines the label names; deadlines owed by different parties on one day read neutral
        parties = {r["party"] for r in m["named"]}
        if all(r.get("done") for r in rows):
            series, name, col = "done", lbl("lg_done"), DONE
        elif len(parties) == 1:
            series = name = next(iter(parties)) if next(iter(parties)) in colors else "Both"
            col = colors[series]
        else:
            series, name, col = "mixed", lbl("lg_mixed"), MIXED
        chart.mark(series, name, "bar", col)
        y = mid - 10 - lv * STEP if side == "up" else mid + 30 + lv * STEP  # below the tick labels (mid + 13)
        cx = x0 + w / 2
        ly = y + (3 if side == "up" else -9)
        # the leader runs from the marker straight up or down, then bends to the label when it slid sideways
        lines.append(f'<polyline points="{x:.1f},{mid} {x:.1f},{(ly + mid) / 2 if abs(cx - x) > 1 else ly:.1f} '
                     f'{min(max(x, x0 + 3), x0 + w - 3):.1f},{ly:.1f}" fill="none" stroke="{col}" stroke-width=".7"/>')
        r = 6 if row["key"] == "closing" else 4.2
        critical = any(r_["critical"] and not r_.get("done") for r_ in rows)
        if critical:
            chart.mark("critical", lbl("lg_critical"), "dot", "var(--text)")
        else:
            chart.mark("other", lbl("lg_other"), "ring", "var(--text)")
        dots.append(f'<circle cx="{x:.1f}" cy="{mid}" r="{r}" fill="{col if critical else "#fff"}" stroke="{col}" stroke-width="1.6"/>')
        # a white copy under the label instead of an outline with paint-order, which some PDF viewers smear
        labels.append(f'<text x="{cx:.1f}" y="{y}" class="lbl halo" aria-hidden="true" text-anchor="middle">{esc(m["text"])}</text>'
                      f'<text x="{cx:.1f}" y="{y}" class="lbl" text-anchor="middle" style="fill:{col}">{esc(m["text"])}</text>')
    s += lines + dots + labels  # leaders under the dots and labels; labels carry a white halo (timeline.css)
    s.append("</svg>")
    return "".join(s)


def strip_legend_order(chart):
    """The legend's series in a fixed order (parties, then the neutral ones, then the dot kinds), only those drawn."""
    order = [*PARTIES, "mixed", "done", "critical", "other"]
    chart.series = {k: chart.series[k] for k in sorted(chart.series, key=order.index)}
    return chart


# --- the report ------------------------------------------------------------------------------

def pending_text(r):
    """What a pending row shows under its name: its rule, short ("10 days after short sale approval")."""
    rule = r["rule"] if len(r["rule"]) <= 64 else r["rule"].split(" (")[0]
    return rule if len(rule) <= 64 else "On event"


def party_pill(party, colors, ink=None):
    """DS-1: the raw party color for the border, a darkened one (4.5:1 on white) for the text."""
    col = colors.get(party, colors["Both"])
    text = (ink or colors).get(party, col)
    return f'<span class="party" style="border-color:{col};color:{text}">{esc(party)}</span>'


def prepared_lines(t, agent):
    # TL-265: the whole line stays together, so a separator never dangles at a line end
    lines = [Raw(f'<span class="nw">{lbl("prepared_for")} <b>{esc(t["client"])}</b> · {esc(t["report_date"]["long"])}</span>')]
    if agent.get("name"):
        lines.append(Raw(f'<b>{esc(agent["name"])}</b>'))
        org = " · ".join(str(agent[f]) for f in ("team", "brokerage") if agent.get(f))
        lic = f'Lic. {agent["license"]}' if agent.get("license") else ""
        if org or lic:
            lines.append(" · ".join(x for x in (org, lic) if x))
    return lines


# Key Dates and Deadline Details: widths by class (timeline.css), numbers right-aligned and never wrapped
KEY_COLS = [layout.Col("date", lbl("th_date"), align="num", cls="c-date"), layout.Col("day", lbl("th_day"), align="num", cls="c-day"),
            layout.Col("deadline", lbl("th_deadline"), cls="c-dl"), layout.Col("who", lbl("th_who"), cls="c-who")]
DETAIL_COLS = [layout.Col("date", lbl("th_date"), align="num", cls="c-ddate"),
               layout.Col("deadline", lbl("th_deadline_source"), cls="c-dsrc"), layout.Col("who", lbl("th_who"), cls="c-dwho"),
               layout.Col("rule", lbl("th_rule"), cls="c-drule"), layout.Col("action", lbl("th_action"), cls="c-dact"),
               layout.Col("missed", lbl("th_if_missed"), cls="c-dmiss")]
HISTORY_COLS = [layout.Col("n", lbl("th_n"), cls="c c-hn"), layout.Col("signed", lbl("th_signed"), cls="c-hdate"),
                layout.Col("what", lbl("th_amendment"), cls="c-hwhat"), layout.Col("changes", lbl("th_changes"), cls="c-hchg")]
METHOD_COLS = [layout.Col("term", lbl("th_term"), cls="c-mterm"), layout.Col("how", lbl("th_how"))]


def lead_sentence(t):
    """The hero's sentence: when the contingencies end and what that means, from the document model."""
    side, firm, first = t["side"], t["contingencies_end"], t["first_deadline"]
    still = t.get("open_rights") or []
    rights = esc(join_words([sentence_case(x) for x in still]))
    open_txt = " " + lbl("lead_open", rights=rights) if still else ""
    if t.get("contingencies_waiting"):  # Rider G before the approval: the contingency periods haven't started
        lead = lbl(f"lead_waiting_{side}", periods=esc(t["contingencies_waiting_text"]))
    elif firm:
        lead = lbl(f"lead_firm_{side}", date=f'<b>{esc(firm["display"])}</b>', day=day_label(firm),
                 period=esc(t["contingencies_end_period"]))
        # iteration 12 eval 14: another contract's report states no consequence (the deposit at risk, a firm deal) that
        # the deal file doesn't record from the contract. TL-202: one "after that", with the open rights as the exception
        lead += (open_txt if t.get("form_family") == "other" else
                 " " + (lbl(f"lead_after_{side}_open", rights=rights) if still else lbl(f"lead_after_{side}")))
    else:
        lead = lbl("lead_none_other" if t.get("form_family") == "other" else f"lead_none_{side}") + open_txt
    if first:  # TL-104: the full label, from the report date
        lead += " " + lbl("lead_next", label=esc(first["label"]), date=esc(first["date_display"]), day=day_label(first))
    return lead


def hero(t):
    side, firm = t["side"], t["contingencies_end"]
    closing, ss = t["closing"], t.get("short_sale")
    eff = t["effective"]["short"]
    if closing:
        big = lbl("big_span", eff=eff, closing=closing["long"], days=t["length_days"])
        closing_html = f'<b>{esc(closing["display"])}</b> <span class="sm">({day_label(closing)})</span>'
    else:  # Rider G: closing is a number of days after the approval
        days = ss["closing_days"] if ss else None
        big = lbl("big_awaiting" if days else "big_not_set", eff=eff)
        closing_html = (f'<b>{lbl("pending")}</b> <span class="sm">{lbl("pending_closing_days", days=days)}</span>' if days
                        else f'<b>{lbl("not_set")}</b>')
    firm_html = (f'<b>{esc(firm["display"])}</b> <span class=sm>({day_label(firm)})</span>' if firm else
                 f'<b>{lbl("pending")}</b> <span class="sm">{lbl("pending_approval")}</span>' if t.get("contingencies_waiting")
                 else f"<b>{fmt.EMPTY}</b>")
    return (f'<div class="hero"><div class="hl"><span class="k">{lbl("k_span")}</span>'
            f'<div class="big">{esc(big)}</div><div class="why">{lead_sentence(t)}</div></div>'
            f'<div class="hr"><span class="k">{lbl("k_firm_" + side)}</span>{firm_html}'
            f'<span class="k" style="margin-top:6px">{lbl("k_closing")}</span><div>{closing_html}</div></div></div>')


def build_html(t, agent, sample):
    side = t["side"]
    Side = side.title()
    theme = design.theme(agent.get("brand"), side)
    p = theme["party"]
    colors = {"Buyer": p["buyer"], "Seller": p["seller"], "Both": p["both"]}
    ink = {k.title(): v for k, v in theme["party_ink"].items()}

    # the dates live in the hero; the contract terms run in one fact row, and missing ones drop out
    n = len(t["history"])
    terms = [t["price"], t["financing"], t["contract_label"], lbl("fact_escrow", name=t["escrow_agent"]) if t["escrow_agent"] else None,
             lbl("fact_amendments", n=n, s="s" if n != 1 else "") if n else None]

    def status(r):
        if r.get("done"):
            return f' <span class="pill good">{esc(r["done_display"])}</span>'
        return f' <span class="pill caution">{esc(r["past_display"])}</span>' if r.get("past") else ""

    def star(r):
        return "&nbsp;<span class=crit>★</span>" if r["critical"] and not r.get("done") else ""

    def mine(r):
        return " ".join(c for c in ("mine" if r["party"] == Side else "", "done" if r.get("done") else "") if c)

    def was(r, sep=" "):
        return f'{sep}<span class="was">{esc(lbl("was", date=r["was"]))}</span>' if r["was"] else ""

    shown = page_one_rows(t)
    key_rows = [{"date": Raw(f'<b>{esc(r["display"])}</b>'), "day": day_label(r),
                 "deadline": Raw(f'{esc(r["label"])}{star(r)}{was(r)}{status(r)}'),
                 "who": Raw(party_pill(r["party"], colors, ink))} for r in shown]
    # dates that wait for an event (a receipt, the short sale approval) close the table: "Pending" in the narrow date
    # column, and what starts the clock under the deadline's name (TL-224)
    key_rows += [{"date": Raw(f'<i>{lbl("pending")}</i>'), "day": fmt.EMPTY,
                  "deadline": Raw(f'{esc(r["label"])}{star(r)} <i class="sm pr">· {esc(pending_text(r))}</i>'),
                  "who": Raw(party_pill(r["party"], colors, ink))} for r in t["pending"]]
    classes = {i: mine(r) for i, r in enumerate(shown)}
    classes.update({len(shown) + i: ("pend " + mine(r)).strip() for i, r in enumerate(t["pending"])})
    key_table = layout.table(KEY_COLS, key_rows, keep="brk", cls="kd", row_classes={i: c for i, c in classes.items() if c})

    chart = layout.Chart()
    svg = strip(t, colors, chart)
    legend = strip_legend_order(chart).legend()
    moved = any(r["was"] for r in t["rows"])
    # manual round 5 case 8: another contract's star states no FAR/BAR consequence; page 1 has no If Missed column
    meaning = lbl("critical_other" if t.get("form_family") == "other" else "critical_farbar")
    # the report's one notes block: the Check lines (the registry's report notes, in the script's words)
    checks = layout.notes_block(t["flags"], title=lbl("h_checks"), cls="tl-checks")
    sub = lbl("key_dates_sub", side=side) + (lbl("key_dates_moved") if moved else "")
    page1 = (hero(t)
             + f'<h2>{lbl("h_timeline")} <span class="h2s">{esc(strip_span(t))}</span></h2>'
             + layout.chart_frame(svg, legend, cls="tl-strip")
             + f'<h2>{lbl("h_key_dates")} <span class="h2s">{esc(sub)}</span></h2>'
             + key_table
             + f'<div class="sm" style="margin-top:3px"><span class="crit">★</span> {esc(lbl("critical_line", meaning=meaning))}</div>'
             + checks)

    def detail(r):
        date = (f'<b>{esc(r["display"])}</b><br><span class="sm">{day_label(r)}</span>' + was(r, "<br>")
                + (f"<br>{status(r).strip()}" if r.get("done") or r.get("past") else ""))
        return {"date": Raw(date), "deadline": Raw(f'<b>{esc(r["label"])}</b>{star(r)}<br><span class="sm">{esc(r["source"])}</span>'),
                "who": r["party"], "rule": Raw(esc(r["rule"]) + (f"<br><i>{esc(r['note'])}</i>" if r["note"] else "")),
                "action": r["action"], "missed": r["if_missed"]}
    all_rows = t["rows"] + t["pending"]
    details = layout.table(DETAIL_COLS, [detail(r) for r in all_rows], keep="brk", cls="det",
                           row_classes={i: "done" for i, r in enumerate(all_rows) if r.get("done")})
    if t["history"]:
        hist = layout.table(HISTORY_COLS, [
            {"n": f"#{i}", "signed": h.get("date_display") or fmt.EMPTY,
             "what": Raw((f'<b>{esc(h["name"])}</b><br>' if h.get("name") else "") + esc(h["description"])),
             "changes": h["summary"]} for i, h in enumerate(t["history"], 1)])
        hist_html = f'<h2>{lbl("h_history")} <span class="h2s">{esc(lbl("history_sub"))}</span></h2>' + hist
    else:
        hist_html = f'<h2>{lbl("h_history")}</h2><p class="sm">{lbl("no_amendments")}</p>'
    eff_source = t["effective"]["source"] or lbl("effective_unconfirmed")
    method = layout.table(METHOD_COLS, [{"term": Raw(f'<b>{lbl("row_effective")}</b>'), "how": f'{t["effective"]["display"]}: {eff_source}'}]
                          + [{"term": Raw(f"<b>{esc(x['label'])}</b>"), "how": x["text"]} for x in t["rules"]["lines"]],
                          cls="meth")
    # TL-262: the lender-estimate line only when the report shows a lender's target (insurance bound, Closing Disclosure)
    lender = lbl("fine_lender") if any(r.get("lender") for r in all_rows) else ""
    body = (f'<div class="pb"></div><div class="dh">{lbl("h_details")}</div>{details}'
            f'<div class="appx"><div class="dh" style="margin-top:10px">{lbl("h_appendix")}</div>'
            f'{hist_html}<h2>{lbl("h_method")}</h2>{method}'
            f'<div class="fine">{esc(lbl("fine", family=t["rules"]["family"], lender=lender, documents=join_words([lbl("doc_" + k) for k in t["documents"]])))}</div></div>')

    sub = Raw(header_line(t))
    tag = lbl("tag_what_if" if t.get("what_if") else "tag_view", side=Side)  # TL-119: a hypothetical timeline says so
    head = layout.header(lbl("doc_title"), sub, prepared_lines(t, agent), tag=tag, sample=sample)
    doc = head + layout.fact_row(terms) + f'<div class="p1">{page1}</div>' + body
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    return render.page(doc + render.notices(agent), css=css, title=lbl("doc_title"), theme_css=design.css_vars(theme),
                       body_class=f"{side} font-bundled")


# Page 1 fits in steps: the compact layout, then (a deal with many deadlines) the key dates run on and the details
# follow them on page 2, so no page is left half empty. Removing the .pb boundary is the last step.
RUN_ON = ("() => { const e = document.querySelector('.pb'); "
          "if (e) { e.classList.remove('pb'); e.classList.add('pb-run'); } }")
# A last page holding only the closing notices: the detail pages tighten (dense, then denser), then the details start
# right after page 1 instead of on a new page (runon); each kept only when it
# saves the page (layout.print_pdf's tail steps).
FIT = layout.Fit(steps=("compact", RUN_ON), tail=("dense", "denser", "runon"))


# --- the calendar ----------------------------------------------------------------------------

def _ics_text(s):
    return str(s).replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line):
    """RFC 5545 line folding at 75 octets."""
    out, raw = [], line.encode("utf-8")
    while len(raw) > 75:
        cut = 75 if not out else 74
        while cut and (raw[cut] & 0xC0) == 0x80:  # don't split a UTF-8 character
            cut -= 1
        out.append(raw[:cut].decode("utf-8"))
        raw = b" " + raw[cut:]
    out.append(raw.decode("utf-8"))
    return "\r\n".join(out)


# TL-115: timed events carry the property's zone (timeline.ZONES), so a calendar in another zone shows the right hour.
# US rules since 2007; a zone with no daylight saving has only its standard offset.
VTIMEZONES = {
    "America/New_York": ("-0500", "-0400", "EST", "EDT"),
    "America/Chicago": ("-0600", "-0500", "CST", "CDT"),
    "America/Denver": ("-0700", "-0600", "MST", "MDT"),
    "America/Phoenix": ("-0700", None, "MST", None),
    "America/Los_Angeles": ("-0800", "-0700", "PST", "PDT"),
    "America/Anchorage": ("-0900", "-0800", "AKST", "AKDT"),
    "Pacific/Honolulu": ("-1000", None, "HST", None),
    "America/Puerto_Rico": ("-0400", None, "AST", None),
}


def _vtimezone(tzid):
    std, dst, std_name, dst_name = VTIMEZONES[tzid]
    if not dst:
        return ["BEGIN:VTIMEZONE", f"TZID:{tzid}", "BEGIN:STANDARD", f"TZOFFSETFROM:{std}", f"TZOFFSETTO:{std}",
                f"TZNAME:{std_name}", "DTSTART:19700101T000000", "END:STANDARD", "END:VTIMEZONE"]
    return ["BEGIN:VTIMEZONE", f"TZID:{tzid}",
            "BEGIN:DAYLIGHT", f"TZOFFSETFROM:{std}", f"TZOFFSETTO:{dst}", f"TZNAME:{dst_name}", "DTSTART:20070311T020000",
            "RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU", "END:DAYLIGHT",
            "BEGIN:STANDARD", f"TZOFFSETFROM:{dst}", f"TZOFFSETTO:{std}", f"TZNAME:{std_name}", "DTSTART:20071104T020000",
            "RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU", "END:STANDARD", "END:VTIMEZONE"]



def header_line(t):
    """The header's property and parties: each piece keeps its words together (TL-265), and each separator ends the
    piece before it, so a line breaks after a separator and never starts with one ("· Buyer", "/ Seller")."""
    pieces = (t["property"] + " ·", (t["buyer"] or "Buyer") + " /", t["seller"] or "Seller")
    return " ".join(f'<span class="nw">{esc(x)}</span>' for x in pieces)


def calendar_rows(t, lender_dates=False):
    """The rows the calendar holds: dated, not done or past (TL-104), and no lender target unless asked (TL-252)."""
    return [r for r in t["rows"] if not r.get("done") and not r.get("past") and (lender_dates or not r.get("lender"))]


def due_text(r):
    """What the report prints after a row's day, as the calendar title says it: "by 11:59 PM", "by 5:00 PM ET",
    "by Closing", "before Closing", or "" for a day alone. Taken from the row's display, so the two never differ."""
    tail = r["display"].split(" · ", 1)[1] if " · " in r["display"] else ""
    return tail if not tail or tail.startswith(("by ", "before ")) else "by " + tail


def ics(t, lender_dates=False):
    """TL-20: the closing calendar as an .ics file. A deadline is an all-day event on its due day, its title ending
    with the time it's due by as the report prints it ("by 11:59 PM", "by Closing"), so no calendar shows a deadline
    as an event that starts at that time. The closing and possession are appointments, timed in the property's time
    zone (TZID) when it's known. Critical deadlines get a reminder the day before (9:00 AM for an all-day event). SEQUENCE counts the amendments, so a re-imported calendar replaces the older events. Deadlines
    already done or past (TL-104) are left out, and so are the lender's targets (TL-252: insurance bound, the Closing
    Disclosure), which are estimates, not contract dates; `lender_dates` adds them, titled "Lender Target"."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # when the file was made, in UTC (RFC 5545)
    what_if = lbl("ics_what_if") if t.get("what_if") else ""  # TL-119: a hypothetical timeline says so in the calendar too
    tzid = timeline.ZONES[t["time_zone"]][0] if t.get("time_zone") in timeline.ZONES else None
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//real-estate-skills//contract-timeline//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_ics_text(what_if + lbl('ics_name', property=t['property']))}"]
    if tzid:
        lines += [f"X-WR-TIMEZONE:{tzid}", *_vtimezone(tzid)]
    at = f";TZID={tzid}" if tzid else ""
    for r in calendar_rows(t, lender_dates):
        lender = lbl("ics_lender") if r.get("lender") else ""
        when = _when(r)
        # one rule: only an appointment (the closing, possession) is timed; a deadline, a row due by the closing time and
        # an event on a day (the walk-through) are all-day items, the deadline's time in the title
        all_day = not (r.get("appointment") and not r.get("no_time"))
        due = "" if not all_day else due_text(r)
        start = f"DTSTART;VALUE=DATE:{when:%Y%m%d}" if all_day else f"DTSTART{at}:{when:%Y%m%dT%H%M%S}"
        end = (f"DTEND;VALUE=DATE:{(when + timedelta(days=1)):%Y%m%d}" if all_day
               else f"DTEND{at}:{(when + timedelta(minutes=30)):%Y%m%dT%H%M%S}")
        desc = " ".join(x for x in (lbl("ics_who", party=r["party"]), r["action"] and f"{r['action']}.",
                                    r["if_missed"] and lbl("ics_if_missed", text=r["if_missed"]),
                                    r["rule"] and lbl("ics_rule", text=r["rule"]), r["source"] and lbl("ics_source", text=r["source"]))
                if x)
        lines += ["BEGIN:VEVENT", f"UID:{r['key']}-{hashlib.sha1(t['property'].encode()).hexdigest()[:10]}@contract-timeline",
                  f"SEQUENCE:{len(t.get('history') or [])}", f"DTSTAMP:{now}", start, end,
                  f"SUMMARY:{_ics_text(what_if + lender + r['label'] + (' ★' if r['critical'] and not lender else '') + (lbl('ics_due', due=due) if due else ''))}",
                  f"DESCRIPTION:{_ics_text(desc)}"]
        if r["critical"] and not lender:  # the day before: 9:00 AM for an all-day event (its start is midnight), else 24 hours ahead
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(r['label'])}",
                      "TRIGGER:-PT15H" if all_day else "TRIGGER:-P1D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def calendar_lender_rows(t, lender_dates=False):
    """The lender's targets the calendar leaves out (dated, open), in date order; none with --lender-dates."""
    if lender_dates:
        return []
    return [r for r in calendar_rows(t, True) if r.get("lender")]


def lender_calendar_note(rows):
    names = timeline.join_words([f'{r["label"].replace(" (Lender Target)", "")} ({r["date_display"]})' for r in rows])
    return (f"The calendar leaves out the lender's targets, {names}: they're estimates, not contract dates. "
            "Say so in one line and offer to add them (render with --lender-dates, titled Lender Target).")


# --- the run ---------------------------------------------------------------------------------

def compute(deal, ctx):
    """The document model, once per run: the timeline every format places. Its notes for the agent go to stderr here,
    once, whichever formats the run builds."""
    if ctx.get("date"):
        deal = {**deal, "report_date": ctx["date"]}
    t = timeline.analyze(deal)
    for w in t["warnings"]:  # a misspelled field the script ignored: fix the deal file, never pass this on
        print(f"Deal file warning (fix it; not for the agent): {w}", file=sys.stderr)
    for flag in t["flags"]:
        print(f"Check (on the report): {flag}", file=sys.stderr)
    for note in t["agent_notes"] + t["chat_notes"]:
        print(f"For the agent, in chat only (not in the PDF): {note}", file=sys.stderr)
    return t


def build(t, fmt_, out_dir, ctx):
    base = t["property"].split(",")[0]
    if fmt_ == "ics":
        path = os.path.join(out_dir, render.filename(base, "Contract Timeline", t["side"], ext="ics"))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(ics(t, ctx.get("lender_dates")))
        left_out = calendar_lender_rows(t, ctx.get("lender_dates"))
        if left_out:  # manual round 5 case 6: the reply says in one line which estimates the calendar leaves out
            print("For the agent, in chat only: " + lender_calendar_note(left_out), file=sys.stderr)
        return [path]
    if not t["closing"] and not t.get("short_sale"):  # a short sale before approval has no closing date yet
        raise timeline.DealError("The report needs the closing date: add contract.closing_date and re-run.")
    doc = build_html(t, ctx["agent"], ctx.get("sample") or t["sample"])
    path = os.path.join(out_dir, render.filename(base, "Contract Timeline", t["side"], ext="pdf"))
    info = layout.print_pdf(doc, path, FIT, footer_html=render.footer(lbl("footer", property=t["property"])))
    if RUN_ON in info["steps"]:
        print("Layout (information): the key-dates table runs onto page 2 and the details follow it there.", file=sys.stderr)
    for line in info["checks"]:
        print(f"Check: {line}", file=sys.stderr)
    return [path]


def extra_args(ap):
    ap.add_argument("--date", help="the report's Prepared date, YYYY-MM-DD (default: the deal file's report_date, else today)")
    ap.add_argument("--lender-dates", action="store_true",
                    help="add the lender's targets (insurance bound, Closing Disclosure) to the calendar, titled Lender Target")


def main(argv=None):
    return render.main(build, formats=("pdf", "ics"), argv=argv, errors=(timeline.DealError,), extra_args=extra_args,
                       labels=("deadlines[].label", "deadlines[].short"), compute=compute)


if __name__ == "__main__":
    main()
