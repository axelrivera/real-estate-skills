"""Contract timeline PDF (buyer or seller view).

    python3 scripts/render.py deal.json [--format pdf|ics|all] [--profile profile.md] [--date YYYY-MM-DD] [--out DIR]
                              [--lender-dates]

Page 1: the contract period, when the contingencies end, a timeline strip and every key date.
Page 2: every deadline with its source, rule, action and consequence; amendment history; how the
dates were computed. Colors follow the agent's brand (buyer or seller side).
"""
import hashlib
import html
import os
import sys
from datetime import datetime, time, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import timeline  # noqa: E402
from _shared import design, render  # noqa: E402

esc = html.escape
CSS_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "assets", "timeline.css")
PAGE1_LIMIT = 989  # px available on page 1 at the print viewport



def sentence_case(label):
    """'HOA Disclosure' -> 'HOA disclosure': lower-case the words, keep acronyms (HOA, FHA/VA)."""
    return " ".join(w if w.isupper() else w.lower() for w in label.split())


period_name, join_words = timeline.period_name, timeline.join_words

def _when(row):
    return datetime.strptime(row["when"], "%Y-%m-%d %H:%M")


def _day(row):
    """The start of a deadline's day: the strip plots every deadline on its own day's tick, so 11:59 PM never reads as
    the next day."""
    return datetime.combine(_when(row).date(), time())


def strip_span(t):
    """What the strip runs to: Closing when the closing is its last date, else its last deadline (a short sale waiting
    on approval runs to Contract Expires; a stay after closing to the possession date)."""
    last = max(t["rows"], key=_when)
    if t["closing"] and _when(last).date() <= datetime.strptime(t["closing"]["date"], "%Y-%m-%d").date():
        return "Effective Date → Closing"
    return f'Effective Date → {last["short"]}'


def day_label(row):
    return "—" if row.get("day") is None else f"Day {row['day']}"


def _label_width(text):
    """Estimated width in px of a strip label (8.6px bold): wide enough that labels never touch."""
    return sum(3.0 if ch in " .,:;·/|il1'" else 6.2 if ch.isupper() or ch in "mwMW" else 5.0 for ch in text) + 8


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


def strip_mixed(t):
    """True when some day on the strip names deadlines owed by different parties (the legend then explains the neutral
    color)."""
    groups = {}
    for r in t["rows"]:
        groups.setdefault(_when(r).date(), []).append(r)
    return any(len({r["party"] for r in g if not r.get("done")}) > 1 for g in groups.values())  # all done: gray


def strip(t, colors):
    """Horizontal timeline from the Effective Date to the last date; labels in free slots above and below. Deadlines
    already done are drawn in gray."""
    dated = t["rows"]
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
        when = _when(row)
        if not open_rows:
            return row, f'{row["short"]} · Done', named
        n = len(open_rows)
        names = row["short"] if n == 1 else f'{row["short"]} +{n - 1}' if n > 2 or compact else \
            " / ".join(r["short"] for r in open_rows)
        return row, f'{names} · {when:%-m/%-d}', named

    def layout(compact):
        marks = []
        for rows in groups.values():
            row, text, named = label(rows, compact)
            marks.append(dict(rows=rows, named=named, row=row, x=X(_day(row)), text=text, w=_label_width(text)))
        return marks, place_labels([(m["x"], m["w"]) for m in marks], W)

    # full names when they fit on one level a side; a crowded strip names one deadline per day and counts the rest
    # when that takes fewer levels
    marks, (spots, levels) = layout(False)
    if levels > 1:
        tight = layout(True)
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
        tw = len(f"{d:%b %-d}") * 4.4 / 2 + 2  # half the tick label's width at 8px, plus a gap
        s.append(f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{mid - 4}" y2="{mid + 4}" stroke="var(--grey-light)"/>')
        if not any(a - tw <= x <= b + tw for a, b in crossed):
            s.append(f'<text x="{x:.1f}" y="{mid + 13}" class="tk" text-anchor="middle">{d:%b %-d}</text>')
        d += timedelta(days=7)
    lines, dots, labels = [], [], []
    for m, (side, lv, x0) in zip(marks, spots):
        rows, row, x, w = m["rows"], m["row"], m["x"], m["w"]
        # the party of the deadlines the label names; deadlines owed by different parties on one day read neutral
        parties = {r["party"] for r in m["named"]}
        col = colors.get(next(iter(parties)), colors["Both"]) if len(parties) == 1 else MIXED
        if all(r.get("done") for r in rows):
            col = "var(--muted)"
        y = mid - 10 - lv * STEP if side == "up" else mid + 30 + lv * STEP  # below the tick labels (mid + 13)
        cx = x0 + w / 2
        ly = y + (3 if side == "up" else -9)
        # the leader runs from the marker straight up or down, then bends to the label when it slid sideways
        lines.append(f'<polyline points="{x:.1f},{mid} {x:.1f},{(ly + mid) / 2 if abs(cx - x) > 1 else ly:.1f} '
                     f'{min(max(x, x0 + 3), x0 + w - 3):.1f},{ly:.1f}" fill="none" stroke="{col}" stroke-width=".7"/>')
        r = 6 if row["key"] == "closing" else 4.2
        critical = any(r_["critical"] and not r_.get("done") for r_ in rows)
        dots.append(f'<circle cx="{x:.1f}" cy="{mid}" r="{r}" fill="{col if critical else "#fff"}" stroke="{col}" stroke-width="1.6"/>')
        labels.append(f'<text x="{cx:.1f}" y="{y}" class="lbl" text-anchor="middle" style="fill:{col}">{esc(m["text"])}</text>')
    s += lines + dots + labels  # leaders under the dots and labels; labels carry a white halo (timeline.css)
    s.append("</svg>")
    return "".join(s)


def pending_text(r):
    """What a pending row shows under its name: its rule, short ("10 days after short sale approval")."""
    rule = r["rule"] if len(r["rule"]) <= 64 else r["rule"].split(" (")[0]
    return rule if len(rule) <= 64 else "On event"


def party_pill(party, colors, ink=None):
    """DS-1: the raw party color for the border, a darkened one (4.5:1 on white) for the text."""
    col = colors.get(party, colors["Both"])
    text = (ink or colors).get(party, col)
    return f'<span class="party" style="border-color:{col};color:{text}">{esc(party)}</span>'


def prepared_block(t, agent):
    # TL-265: the whole line stays together, so a separator never dangles at a line end
    lines = [f'<span class="nw">Prepared for <b>{esc(t["client"])}</b> · {esc(t["report_date"]["long"])}</span>']
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
    ink = {k.title(): v for k, v in theme["party_ink"].items()}

    # the dates live in the hero; the contract terms run in one divider row, and missing ones drop out
    n = len(t["history"])
    terms = [t["price"], t["financing"], t["contract_label"], f'Escrow: {t["escrow_agent"]}' if t["escrow_agent"] else None,
             f'{n} amendment{"s" if n != 1 else ""}' if n else "No amendments"]
    snap_html = ('<div class="divrow factrow"><div>' + "".join(f"<span>{esc(str(x))}</span>" for x in terms if x) + "</div></div>")

    firm, first = t["contingencies_end"], t["first_deadline"]
    waiting = t.get("contingencies_waiting") or []
    ss = t.get("short_sale")
    still = t.get("open_rights") or []
    still_txt = esc(join_words([sentence_case(x) for x in still]))
    open_txt = f" These rights stay open: {still_txt}." if still else ""
    if waiting:  # Rider G before the approval: the contingency periods haven't started
        firm_label = "Your Contingencies End" if side == "buyer" else "Buyer Can Cancel Until"
        whose = "Your" if side == "buyer" else "The buyer's"
        lead = (f'{whose} contingency periods ({esc(t["contingencies_waiting_text"])}) start when the buyer '
                "receives the short sale approval; until then, only the dates counted from the Effective Date are set.")
    elif side == "buyer":
        firm_label = "Your Contingencies End"
        # TL-202: one "after that", with the rights that stay open as the exception
        lead = (f'Your main protections run through <b>{esc(firm["display"])}</b> ({day_label(firm)}, '
                f'{esc(t["contingencies_end_period"])}).'
                + (f" After that the deposit is at risk, except under the rights that stay open: {still_txt}." if still
                   else " After that the deposit is at risk.")
                if firm else "No buyer contingencies: the deposit is at risk from the start." + open_txt)
    else:
        firm_label = "Buyer Can Cancel Until"
        lead = (f'The buyer\'s main contingencies end <b>{esc(firm["display"])}</b> ({day_label(firm)}, '
                f'{esc(t["contingencies_end_period"])}).'
                + (f" After that the deal is firm unless the buyer defaults, except for the rights that stay open: {still_txt}."
                   if still else " After that the deal is firm unless the buyer defaults.")
                if firm else "No buyer contingencies: the deal is firm once the deposit is in." + open_txt)
    if first:  # TL-104: the full label, from the report date
        lead += f' Next deadline: {esc(first["label"])}, {esc(first["date_display"])} ({day_label(first)}).'
    closing = t["closing"]
    if closing:
        big = f'{t["effective"]["short"]} → {closing["long"]} · {t["length_days"]} days'
        closing_html = f'<b>{esc(closing["display"])}</b> <span class="sm">({day_label(closing)})</span>'
    else:  # Rider G: closing is a number of days after the approval
        days = ss["closing_days"] if ss else None
        big = f'{t["effective"]["short"]} → ' + ("Awaiting Approval" if days else "Closing Not Set")
        closing_html = (f'<b>Pending</b> <span class="sm">({days} days after short sale approval)</span>' if days
                        else "<b>Not set</b>")
    firm_html = (f'<b>{esc(firm["display"])}</b> <span class=sm>({day_label(firm)})</span>' if firm else
                 '<b>Pending</b> <span class="sm">(after short sale approval)</span>' if waiting else "<b>—</b>")
    hero = (f'<div class="hero"><div class="hl"><span class="k">Effective Date → Closing</span>'
            f'<div class="big">{big}</div>'
            f'<div class="why">{lead}</div></div>'
            f'<div class="hr"><span class="k">{firm_label}</span>{firm_html}'
            f'<span class="k" style="margin-top:6px">Closing</span><div>{closing_html}</div></div></div>')

    def done_pill(r):
        if r.get("done"):
            return f' <span class="pill good">{esc(r["done_display"])}</span>'
        return f' <span class="pill caution">{esc(r["past_display"])}</span>' if r.get("past") else ""

    def star(r):
        return "&nbsp;<span class=crit>★</span>" if r["critical"] and not r.get("done") else ""

    def row_class(r):
        return " ".join(c for c in ("mine" if r["party"] == Side else "", "done" if r.get("done") else "") if c)

    key_rows = "".join(
        f'<tr class="{row_class(r)}"><td class="n"><b>{esc(r["display"])}</b></td><td class="n">{day_label(r)}</td>'
        f'<td>{esc(r["label"])}{star(r)}'
        f'{(" <span class=was>was " + esc(r["was"]) + "</span>") if r["was"] else ""}{done_pill(r)}</td>'
        f'<td>{party_pill(r["party"], colors, ink)}</td></tr>' for r in t["rows"])
    # dates that wait for an event (a receipt, the short sale approval) close the table: "Pending" in the narrow date
    # column, and what starts the clock under the deadline's name (TL-224)
    key_rows += "".join(
        f'<tr class="pend {row_class(r)}"><td class="n"><i>Pending</i></td><td class="n">—</td>'
        f'<td>{esc(r["label"])}{star(r)} <i class="sm pr">· {esc(pending_text(r))}</i></td>'
        f'<td>{party_pill(r["party"], colors, ink)}</td></tr>' for r in t["pending"])
    pending = ""
    flags = "".join(f'<div class="note-caution"><b>Check:</b> {esc(f)}</div>' for f in t["flags"])
    amended = (f'<div class="note-brand"><b>Includes {n} amendment{"s" if n != 1 else ""}.</b> Dates that moved show '
               '"was". See the amendment history for details.</div>') if n else ""
    legend = "".join(f'<span><i style="background:{colors[k]};border-radius:50%"></i>{k}</span>' for k in ("Buyer", "Seller", "Both"))
    if strip_mixed(t):
        legend += f'<span><i style="background:{MIXED};border-radius:50%"></i>Different Parties, Same Day</span>'

    page1 = f'''{hero}{amended}
<h2>Timeline <span class="h2s">{esc(strip_span(t))}</span></h2>
<div class="panel" style="padding:2px 6px">{strip(t, colors)}</div>
<div class="legend">{legend}<span>Filled Dot = Critical Deadline</span></div>
<h2>All Key Dates <span class="h2s">Day = calendar days after the Effective Date · ★ = Critical · {side} items highlighted</span></h2>
<div class="tbl brk"><table class="kd"><colgroup><col style="width:22%"><col style="width:9%"><col style="width:57%"></colgroup>
<thead><tr><th class="n">Date</th><th class="n">Day</th><th>Deadline</th><th>Who</th></tr></thead><tbody>{key_rows}</tbody></table></div>
<div class="sm" style="margin-top:3px"><span class="crit">★</span> Critical = missing it can cost a contract right (such as the right to cancel) or put the deposit at risk.</div>
{pending}{flags}'''

    detail_rows = "".join(
        f'<tr class="{"done" if r.get("done") else ""}"><td class="n"><b>{esc(r["display"])}</b><br><span class="sm">{day_label(r)}</span>'
        f'{("<br><span class=was>was " + esc(r["was"]) + "</span>") if r["was"] else ""}'
        f'{("<br>" + done_pill(r).strip()) if r.get("done") or r.get("past") else ""}</td>'
        f'<td><b>{esc(r["label"])}</b>{star(r)}<br><span class="sm">{esc(r["source"])}</span></td>'
        f'<td>{esc(r["party"])}</td><td class="sm">{esc(r["rule"])}{("<br><i>" + esc(r["note"]) + "</i>") if r["note"] else ""}</td>'
        f'<td class="sm">{esc(r["action"])}</td><td class="sm">{esc(r["if_missed"])}</td></tr>' for r in t["rows"] + t["pending"])
    if t["history"]:
        hist = "".join(f'<tr><td class="c"><b>#{i}</b></td><td>{esc(h.get("date_display") or "—")}</td>'
                       f'<td>{"<b>" + esc(h["name"]) + "</b><br>" if h.get("name") else ""}{esc(h["description"])}</td>'
                       f'<td class="sm">{esc(h["summary"])}</td></tr>' for i, h in enumerate(t["history"], 1))
        hist_html = ('<h2>Amendment History <span class="h2s">moved dates show the original as "was"</span></h2>'
                     '<div class="tbl"><table><colgroup><col style="width:5%"><col style="width:12%"><col style="width:33%"></colgroup>'
                     f'<thead><tr><th class="c">#</th><th>Signed</th><th>Amendment</th><th>Changes</th></tr></thead><tbody>{hist}</tbody></table></div>')
    else:
        hist_html = ('<h2>Amendment History</h2><p class="sm">No amendments recorded. When an amendment or extension is signed, '
                     "ask for an updated timeline: every date it moves is shown with the original.</p>")
    eff_source = t["effective"]["source"] or "confirm: date the last party signed or initialed and delivered the final counteroffer"
    method_rows = [("Effective Date", f'{t["effective"]["display"]}: {eff_source}')] + \
                  [(x["label"], x["text"]) for x in t["rules"]["lines"]]
    method = ('<div class="tbl"><table class="meth"><tbody>' +
              "".join(f"<tr><td><b>{esc(a)}</b></td><td>{esc(b)}</td></tr>" for a, b in method_rows) + "</tbody></table></div>")
    # TL-262: the lender-estimate line only when the report shows a lender's target (insurance bound, Closing Disclosure)
    lender_line = " Lender dates are estimates." if any(r.get("lender") for r in t["rows"] + t["pending"]) else ""
    details = f'''<div class="pb"></div><div class="dh">Deadline Details</div>
<div class="sm" style="margin-bottom:4px"><span class="crit">★</span> Critical = missing it can cost a contract right or put the deposit at risk.</div>
<div class="tbl brk"><table class="det"><colgroup><col style="width:14%"><col style="width:20%"><col style="width:7%"><col style="width:19%"><col style="width:22%"></colgroup>
<thead><tr><th class="n">Date</th><th>Deadline · Source</th><th>Who</th><th>Rule</th><th>Action</th><th>If Missed</th></tr></thead><tbody>{detail_rows}</tbody></table></div>
<div class="appx"><div class="dh" style="margin-top:10px">Appendix: Amendments and Date Rules</div>
{hist_html}
<h2>How the Dates Were Computed</h2>{method}
<div class="fine">Computed from the executed contract, riders, counteroffers and amendments. Verify every date against the documents and with the escrow or title agent; the form version and any handwritten changes control. Time rules follow {esc(t["rules"]["family"])}.{lender_line} Not legal advice.</div></div>'''

    title = (f'Contract Timeline <span class="viewtag">{Side} View</span>'
             f'{" <span class=viewtag>What-If</span>" if t.get("what_if") else ""}'  # TL-119: a hypothetical timeline
             f'{"<span class=sample>SAMPLE DATA</span>" if sample else ""}')
    # TL-265: each piece keeps its words together and a line breaks only before a separator, never mid-name
    pieces = (t["property"], "· " + (t["buyer"] or "Buyer"), "/ " + (t["seller"] or "Seller"))
    sub = " ".join(f'<span class="nw">{esc(x)}</span>' for x in pieces)
    body = (f'<header><div><div class="t1">{title}</div><div class="t2">{sub}</div></div>'
            f'<div class="prep">{prepared_block(t, agent)}</div></header>{snap_html}<div class="p1">{page1}</div>{details}')
    with open(CSS_PATH, encoding="utf-8") as f:
        css = f.read()
    return render.page(body + render.notices(agent), css=css, title="Contract Timeline", theme_css=design.css_vars(theme),
                       body_class=side)


def fit_page_one(pg):
    """Measure page 1; switch to the compact layout when it would spill onto page 2."""
    # TL-265: a fact row that runs onto a second line (a long form name) tightens its spacing and type to fit one
    pg.evaluate("""() => { const s = [...document.querySelectorAll('.factrow span')];
        if (s.length > 1 && s[s.length - 1].offsetTop > s[0].offsetTop) document.body.classList.add('tightfacts'); }""")
    # the header's property and parties line tightens the same way when it would wrap (long names)
    pg.evaluate("""() => { const s = [...document.querySelectorAll('.t2 .nw')];
        if (s.length > 1 && s[s.length - 1].offsetTop > s[0].offsetTop) document.body.classList.add('tighthead'); }""")
    top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > PAGE1_LIMIT:
        pg.evaluate("() => document.body.classList.add('compact')")
        top = pg.evaluate("() => document.querySelector('.pb').getBoundingClientRect().top")
    if top > PAGE1_LIMIT:  # page 1 spills anyway: let the details follow on page 2 instead of leaving it nearly empty
        pg.evaluate("() => document.querySelector('.pb').classList.add('flow')")
    return top


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


def ics(t, lender_dates=False):
    """TL-20: the closing calendar as an .ics file. End-of-day deadlines are all-day events; the rest are timed in the
    property's time zone (TZID) when it's known; critical ones get a reminder the day before (at 9:00 AM for an
    all-day event). SEQUENCE counts the amendments, so a re-imported calendar replaces the older events. Deadlines
    already done or past (TL-104) are left out, and so are the lender's targets (TL-252: insurance bound, the Closing
    Disclosure), which are estimates, not contract dates; `lender_dates` adds them, titled "Lender Target"."""
    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")  # when the file was made, in UTC (RFC 5545)
    what_if = "What-If: " if t.get("what_if") else ""  # TL-119: a hypothetical timeline says so in the calendar too
    tzid = timeline.ZONES[t["time_zone"]][0] if t.get("time_zone") in timeline.ZONES else None
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//real-estate-skills//contract-timeline//EN", "CALSCALE:GREGORIAN",
             f"X-WR-CALNAME:{_ics_text(what_if + 'Contract Timeline: ' + t['property'])}"]
    if tzid:
        lines += [f"X-WR-TIMEZONE:{tzid}", *_vtimezone(tzid)]
    at = f";TZID={tzid}" if tzid else ""
    for r in t["rows"]:
        if r.get("done") or r.get("past"):  # already met, or to confirm: nothing to remind anyone about
            continue
        if r.get("lender") and not lender_dates:
            continue
        lender = "Lender Target: " if r.get("lender") else ""
        when = datetime.strptime(r["when"], "%Y-%m-%d %H:%M")
        event = r.get("no_time")  # an event on a day (the walk-through), not a deadline at a time
        # a row due by the closing time is an all-day item on closing day, never a second event at the closing's hour
        all_day = event or r.get("by_closing") or when.strftime("%H:%M") == "23:59"
        start = f"DTSTART;VALUE=DATE:{when:%Y%m%d}" if all_day else f"DTSTART{at}:{when:%Y%m%dT%H%M%S}"
        end = (f"DTEND;VALUE=DATE:{(when + timedelta(days=1)):%Y%m%d}" if all_day
               else f"DTEND{at}:{(when + timedelta(minutes=30)):%Y%m%dT%H%M%S}")
        desc = " ".join(x for x in (f"Who: {r['party']}.", r["action"] and f"{r['action']}.", r["if_missed"] and
                                    f"If missed: {r['if_missed']}.", r["rule"] and f"Rule: {r['rule']}.",
                                    r["source"] and f"Source: {r['source']}.",
                                    "Ends at 11:59 PM." if all_day and not event and not r.get("by_closing") else "",
                                    "Due by Closing." if r.get("by_closing") else "") if x)
        lines += ["BEGIN:VEVENT", f"UID:{r['key']}-{hashlib.sha1(t['property'].encode()).hexdigest()[:10]}@contract-timeline",
                  f"SEQUENCE:{len(t.get('history') or [])}", f"DTSTAMP:{now}", start, end,
                  f"SUMMARY:{_ics_text(what_if + lender + r['label'] + (' ★' if r['critical'] and not lender else ''))}",
                  f"DESCRIPTION:{_ics_text(desc)}"]
        if r["critical"] and not lender:  # the day before: 9:00 AM for an all-day event (its start is midnight), else 24 hours ahead
            lines += ["BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{_ics_text(r['label'])}",
                      "TRIGGER:-PT15H" if all_day else "TRIGGER:-P1D", "END:VALARM"]
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def build(deal, fmt, out_dir, ctx):
    if ctx.get("date"):
        deal = {**deal, "report_date": ctx["date"]}
    t = timeline.analyze(deal)
    if fmt == (ctx.get("formats") or [fmt])[0]:  # once per run, whichever formats it builds
        for w in t["warnings"]:  # a misspelled field the script ignored: fix the deal file, never pass this on
            print(f"Deal file warning (fix it; not for the agent): {w}", file=sys.stderr)
    if fmt == "ics":
        path = os.path.join(out_dir, render.filename(t["property"].split(",")[0], "Contract Timeline", t["side"], ext="ics"))
        with open(path, "w", encoding="utf-8", newline="") as f:
            f.write(ics(t, ctx.get("lender_dates")))
        return [path]
    if not t["closing"] and not t.get("short_sale"):  # a short sale before approval has no closing date yet
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
    for note in t["agent_notes"] + t.get("chat_notes", []):
        print(f"For the agent, in chat only (not in the PDF): {note}", file=sys.stderr)
    return [path]


def extra_args(ap):
    ap.add_argument("--date", help="the report's Prepared date, YYYY-MM-DD (default: the deal file's report_date, else today)")
    ap.add_argument("--lender-dates", action="store_true",
                    help="add the lender's targets (insurance bound, Closing Disclosure) to the calendar, titled Lender Target")


if __name__ == "__main__":
    render.main(build, formats=("pdf", "ics"), errors=(timeline.DealError,), extra_args=extra_args)
