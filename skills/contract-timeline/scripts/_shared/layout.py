"""The report layout kit: HTML components every PDF builds from, text measurement with the bundled font, and one
page-fit pipeline.

    from _shared import layout, notes
    cols = [layout.Col("item", "Item"), layout.Col("amount", "Amount", align="num")]
    layout.table(cols, rows, total={"item": "Net", "amount": "$412,300"})
    layout.tiles([("List Price", "$475,000"), ("Net", "$412,300")], n=4)     # always four slots
    layout.fact_row(["3 Beds", "2 Baths", "1,850 Sq Ft"])
    layout.notes_block(N)                                                    # a notes.Notes registry, printed once
    chart = layout.Chart(); chart.mark("sold", "Sold", "dot")               # as each series is drawn
    layout.chart_frame(svg, chart.legend(), title="Price vs. Size")
    layout.text_width("$474,900", 9, bold=True)                              # in the units of `size`
    info = layout.print_pdf(doc, path, layout.Fit(steps=("compact", "tight")), footer_html=render.footer("..."))

Cell text is escaped; pass layout.Raw("<b>…</b>") for markup a renderer built itself. Classes are report.css's
(.tbl, .n, .brk, .whole, .factrow, .divrow) plus the kit's own (kit-*). Colors are theme variables only.
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass

HERE = os.path.dirname(os.path.abspath(__file__))
METRICS = os.path.join(HERE, "fonts", "metrics.json")
esc = html.escape


def classes(*names):
    return " ".join(n for n in names if n)


class Raw(str):
    """Markup a renderer built itself: placed as is, never escaped."""


def cell(v):
    if v is None or v == "":
        return ""
    return str(v) if isinstance(v, Raw) else esc(str(v))


# --- text measurement ---------------------------------------------------------

_metrics = None
FALLBACK_EM = 0.62  # a character the font doesn't have: about a wide letter in a fallback font


def metrics():
    global _metrics
    if _metrics is None:
        with open(METRICS, encoding="utf-8") as f:
            _metrics = json.load(f)
    return _metrics


def text_width(text, size, bold=False, tnum=False):
    """How wide `text` draws in the bundled font at font size `size`, in the same units as `size` (px in, px out;
    pt in, pt out). `tnum`: digits at their tabular width (tables print digits tabular). No kerning: a measure, a hair
    on the wide side, never narrow."""
    m = metrics()
    widths = m["bold" if bold else "regular"]
    digits = m["tnum"]["bold" if bold else "regular"] if tnum else {}
    units = m["units_per_em"]
    total = sum(digits.get(ch) or widths.get(ch) or FALLBACK_EM * units for ch in str(text))
    return total * size / units


def wrap_lines(text, width, size, bold=False):
    """The lines `text` breaks into at `width` (same units as `size`), greedy at spaces as a browser breaks them;
    a word wider than the line stands alone on its line."""
    words, lines, cur = str(text).split(), [], ""
    for w in words:
        trial = f"{cur} {w}" if cur else w
        if cur and text_width(trial, size, bold) > width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    return lines + ([cur] if cur else [])


def fits(text, width, size, bold=False, lines=1):
    return len(wrap_lines(text, width, size, bold)) <= lines and all(
        text_width(w, size, bold) <= width for w in str(text).split())


# --- tables ---------------------------------------------------------------------

@dataclass
class Col:
    """One table column.

    key: the row field (a row is a dict) or index (a row is a list). label: the header text (wraps when long).
    align: "text" or "num" (numbers right-aligned, tabular, never wrapped). min / max: CSS widths ("9em", "120px",
    "18%") the column keeps. wrap: "auto" (text wraps, numbers don't), "wrap" or "nowrap" for the body cells; a
    header always wraps at spaces, so a long label never widens a number column past its figures.
    """
    key: object
    label: str = ""
    align: str = "text"
    min: str = None
    max: str = None
    wrap: str = "auto"
    cls: str = ""

    def _style(self):
        s = [f"min-width:{self.min}" if self.min else "", f"max-width:{self.max}" if self.max else ""]
        return ";".join(x for x in s if x)

    def classes(self, head=False):
        c = ["n" if self.align == "num" else ""]
        nowrap = self.wrap == "nowrap" or (self.wrap == "auto" and self.align == "num")
        if not head:
            c.append("kit-nw" if nowrap else "kit-wrap")
        else:
            c.append("kit-th")
        c.append(self.cls)
        return " ".join(x for x in c if x)


def _get(row, key):
    if isinstance(row, dict):
        return row.get(key)
    return row[key] if isinstance(key, int) and key < len(row) else None


def table(cols, rows, total=None, keep="auto", cls="", row_classes=None, caption=None, head=True):
    """A boxed table. `rows`: dicts keyed by Col.key or lists in column order. `total`: one more row, set off as
    the total (bold, a rule above). keep: "auto" (short tables stay whole, long ones run on across pages, whole rows
    only, header repeated: render.html_to_pdf marks them .brk), "brk" (always may run on) or "whole" (never splits).
    `row_classes`: {row index: class}. `caption`: a small note under the table. `head=False` leaves out the header
    row (a short list whose columns explain themselves)."""
    def tr(r, extra=""):
        tds = []
        for c in cols:
            st = c._style()
            tds.append(f'<td class="{c.classes()}"' + (f' style="{st}"' if st else "") + f">{cell(_get(r, c.key))}</td>")
        return f'<tr class="{extra}">' + "".join(tds) + "</tr>" if extra else "<tr>" + "".join(tds) + "</tr>"

    head_html = "".join(f'<th class="{c.classes(True)}"' + (f' style="{c._style()}"' if c._style() else "") +
                        f">{cell(c.label)}</th>" for c in cols)
    body = [tr(r, (row_classes or {}).get(i, "")) for i, r in enumerate(rows)]
    if total is not None:
        body.append(tr(total, "total"))
    box = classes("tbl", "kit-tbl", {"brk": "brk", "whole": "whole"}.get(keep, ""), cls)
    cap = f'<p class="kit-cap">{cell(caption)}</p>' if caption else ""
    thead = f"<thead><tr>{head_html}</tr></thead>" if head else ""
    return f'<div class="{box}"><table>{thead}<tbody>{"".join(body)}</tbody></table></div>{cap}'


# --- tiles, fact row, notes, header -------------------------------------------------

def tiles(items, n=None, cls=""):
    """A row of labeled figures in exactly `n` equal slots (len(items) by default): fewer items leave the last slots
    empty, so tiles keep their width from one report to the next. items: (label, value), (label, value, sub) or
    (label, value, sub, cls): `cls` is one more class on that tile (a skill styles a kind of tile, never a color)."""
    n = n or len(items)
    if len(items) > n:
        raise ValueError(f"{len(items)} tiles for {n} slots")
    out = []
    for it in list(items) + [None] * (n - len(items)):
        if it is None:
            out.append('<div class="kit-tile kit-empty"></div>')
            continue
        label, value, sub, cls_ = (list(it) + [None, None])[:4]
        out.append(f'<div class="{classes("kit-tile", cls_)}"><span class="kit-k">{cell(label)}</span><b class="kit-v">{cell(value)}</b>'
                   + (f'<span class="kit-sub">{cell(sub)}</span>' if sub else "") + "</div>")
    return (f'<div class="{classes("kit-tiles", cls)}" style="grid-template-columns:repeat({n},minmax(0,1fr))">'
            + "".join(out) + "</div>")


def fact_row(items, cls=""):
    """Short facts on one line, joined by thin rules (report.css .divrow); wraps whole items when it must."""
    spans = "".join(f"<span>{cell(i)}</span>" for i in items if i not in (None, ""))
    return f'<div class="{classes("factrow divrow", cls)}"><div>{spans}</div></div>'


def notes_block(notes, title="Notes", cls=""):
    """The report's one notes block, from a notes.Notes registry (its pdf() texts) or a list of texts. Empty when
    there are none."""
    texts = notes.pdf() if hasattr(notes, "pdf") else [t for t in notes if t]
    if not texts:
        return ""
    head = f'<h3 class="kit-nh">{cell(title)}</h3>' if title else ""
    return (f'<div class="{classes("kit-notes", cls)}">' + head + "<ul>" +
            "".join(f"<li>{cell(t)}</li>" for t in texts) + "</ul></div>")


def header(title, subtitle="", prepared=(), tag="", sample=False):
    """The report header (report.css header): title, subtitle, an outlined side tag, SAMPLE when it's sample data,
    and the prepared-for lines on the right (each wraps inside the block)."""
    t1 = f'<div class="t1">{cell(title)}' + (f'<span class="viewtag">{cell(tag)}</span>' if tag else "") + \
         ('<span class="sample">SAMPLE DATA</span>' if sample else "") + "</div>"
    t2 = f'<div class="t2">{cell(subtitle)}</div>' if subtitle else ""
    prep = '<div class="prep">' + "<br>".join(cell(p) for p in prepared if p) + "</div>" if prepared else ""
    return f"<header><div>{t1}{t2}</div>{prep}</header>"


def footer(left, right_pages=True):
    """The running footer (render.footer): `left` text and 'Page X of Y'."""
    from . import render
    return render.footer(left, right_pages)


# --- charts ---------------------------------------------------------------------------

SWATCHES = {
    "dot": '<circle cx="7" cy="7" r="5" style="fill:{c}"/>',
    "ring": '<circle cx="7" cy="7" r="4.5" style="fill:var(--bg,#fff);stroke:{c};stroke-width:2"/>',
    "diamond": '<path d="M7,1 L13,7 L7,13 L1,7 Z" style="fill:{c}"/>',
    "bar": '<rect x="1" y="3" width="12" height="8" rx="1.5" style="fill:{c}"/>',
    "line": '<line x1="0" y1="7" x2="14" y2="7" style="stroke:{c};stroke-width:2"/>',
    "dash": '<line x1="0" y1="7" x2="14" y2="7" style="stroke:{c};stroke-width:1.5;stroke-dasharray:4 3"/>',
}


class Chart:
    """The series a chart actually drew, so its legend can only name what's on it. Call mark() once per mark drawn
    (or with count=n); legend() lists each series with at least one mark, in the order first drawn."""

    def __init__(self):
        self.series = {}

    def mark(self, key, label, swatch="dot", color="var(--brand)", count=1):
        if swatch not in SWATCHES and not swatch.startswith("<"):
            raise ValueError(f"unknown swatch {swatch!r}")
        s = self.series.setdefault(key, {"label": label, "swatch": swatch, "color": color, "count": 0})
        s["count"] += count
        return key

    def drawn(self):
        return [k for k, s in self.series.items() if s["count"] > 0]

    def legend(self, cls=""):
        spans = []
        for k in self.drawn():
            s = self.series[k]
            mark = s["swatch"] if s["swatch"].startswith("<") else SWATCHES[s["swatch"]].format(c=s["color"])
            spans.append(f'<span data-series="{esc(str(k))}"><svg viewBox="0 0 14 14">{mark}</svg>{cell(s["label"])}</span>')
        return f'<div class="{classes("legend kit-legend", cls)}">' + "".join(spans) + "</div>" if spans else ""


def chart_frame(svg, legend="", title="", takeaway="", cls=""):
    """A chart in its outlined box: an optional title, the drawing, its legend, and at most one takeaway line (the one
    box allowed the faint --brand-callout tint)."""
    return (f'<div class="{classes("chart-box kit-chart", cls)}">' +
            (f'<div class="kit-ct">{cell(title)}</div>' if title else "") + Raw(svg) + (legend or "") +
            (f'<div class="kit-take">{cell(takeaway)}</div>' if takeaway else "") + "</div>")


# --- keep-together groups and pagination (moved from cma.py; cma re-exports them) ----------------

FIGURES = ("tbl", "chart-box", "comps2", "verdict", "facts")
_TAG = re.compile(r"\s*<(\w+)([^>]*)>")


def _tag(el):
    m = _TAG.match(el)
    if not m:
        return None, set()
    cls = re.search(r'class="([^"]*)"', m.group(2))
    return m.group(1), set(cls.group(1).split()) if cls else set()


def group_blocks(elements):
    """Wrap each heading with its intro paragraphs and following figure (and notes) in a keep-together div.

    `elements` is the report body as a list of top-level HTML strings. Mirrors the prototype's rules:
    a heading keeps up to three paragraphs and one figure; a paragraph directly before a figure stays with it.
    """
    info = [(_tag(e), e) for e in elements]

    def is_fig(i):
        (tag, cls), _ = info[i]
        return tag in ("ul", "ol", "footer") or (tag == "div" and bool(cls & set(FIGURES)))

    def is_note(i):
        (tag, cls), _ = info[i]
        return (tag == "p" and "note" in cls) or (tag == "div" and "chart-read" in cls)

    out, i = [], 0
    while i < len(info):
        (tag, _), _ = info[i]
        group, j = [i], i + 1
        if tag in ("h2", "h3"):
            while j < len(info) and info[j][0][0] == "h3":
                group.append(j); j += 1
            n = 0
            while j < len(info) and info[j][0][0] == "p" and n < 3:
                group.append(j); j += 1; n += 1
            if j < len(info) and is_fig(j):
                group.append(j); j += 1
                while j < len(info) and is_note(j):
                    group.append(j); j += 1
        elif tag == "p" and j < len(info) and is_fig(j):
            group.append(j); j += 1
            while j < len(info) and is_note(j):
                group.append(j); j += 1
        elif is_fig(i):
            while j < len(info) and is_note(j):
                group.append(j); j += 1
        html_parts = [info[g][1] for g in group]
        if len(group) > 1 or is_fig(i):
            out.append(f'<div class="kg{" sec" if tag == "h2" else ""}">' + "".join(html_parts) + "</div>")
        elif tag == "h2":
            out.append(re.sub(r"^\s*<h2", '<h2 class="sec"', html_parts[0], count=1))
        else:
            out.append(html_parts[0])
        i = j
    return "".join(out)


# --- where a table may split -------------------------------------------------------------------------------------
# One rule for every table in every PDF: a table splits across pages only with at least SPLIT_MIN_ROWS body rows on each
# side; a summary row (a total, a subtotal, the final line) stays with the SPLIT_MIN_ROWS - 1 rows above it; a small
# table never splits: fewer than SPLIT_MIN_TABLE body rows that together take less than SMALL_TABLE_SHARE of the page.
# A table that tall in fewer rows (offers side by side, each row a paragraph) is as tall as a section: it runs on rather
# than leave the page before it half empty, with at least TALL_MIN_ROWS rows a side when it has under 2 * SPLIT_MIN_ROWS
# (each such row is several lines), and never with fewer than 2 * TALL_MIN_ROWS rows. TABLE_BREAKS_JS sets it on the rows
# themselves (break-before: avoid where a break isn't allowed, break-inside: avoid on a small table) and marks each
# table data-split="whole" or "rows", before anything is measured, so the print keeps it for any data; PAGINATE_JS
# lets a table run on only when it's "rows", and the probe (table_split_problems) checks the printed PDF by the marks.
SPLIT_MIN_ROWS = 3
SPLIT_MIN_TABLE = 8
TALL_MIN_ROWS = 2
SMALL_TABLE_SHARE = 0.25
SUMMARY_ROWS = ("total", "total2", "subtotal", "final")  # row classes that sum up the rows above them
TABLE_BREAKS_JS = r"""([minRows, minTable, summary, wholePx, tallRows]) => {
  const isSum = r => summary.some(c => r.classList.contains(c));
  let n = 0;
  for (const tb of document.querySelectorAll('table')) {
    if (tb.closest('svg')) continue;
    const rows = Array.from(tb.tBodies).flatMap(b => Array.from(b.rows));
    if (!rows.length) continue;
    n++;
    const box = tb.closest('.tbl') || tb;
    rows.forEach(r => { r.style.breakInside = 'avoid'; });
    const tall = tb.getBoundingClientRect().height > wholePx;
    const side = rows.length >= 2 * minRows ? minRows : tallRows;
    if (rows.length < 2 * side || (rows.length < minTable && !tall)) {
      for (const e of [box, tb]) { e.style.breakInside = 'avoid'; e.dataset.split = 'whole'; }
      continue;
    }
    for (const e of [box, tb]) { if (e === box) e.style.breakInside = 'auto'; e.dataset.split = 'rows'; e.dataset.side = side; }
    if (box !== tb) box.classList.add('brk');  // its outline moves to the table (report.css): no empty band at a break
    const avoid = new Set();
    for (let i = 1; i < side; i++) avoid.add(i);
    for (let i = rows.length - side + 1; i < rows.length; i++) avoid.add(i);
    rows.forEach((r, i) => { if (isSum(r)) for (let k = Math.max(1, i - minRows + 2); k <= i; k++) avoid.add(k); });
    avoid.forEach(i => { rows[i].style.breakBefore = 'avoid'; });
  }
  return n;
}"""


def table_break_rules(pg, page_px):
    """Apply the table-split rule (TABLE_BREAKS_JS) to every table on the page; `page_px` is the printable height.
    Returns how many tables it set."""
    return pg.evaluate(TABLE_BREAKS_JS, [SPLIT_MIN_ROWS, SPLIT_MIN_TABLE, list(SUMMARY_ROWS), SMALL_TABLE_SHARE * page_px,
                                         TALL_MIN_ROWS])


# The layout probe (dev only: LAYOUT_PROBE=1, set by make layout-check and the generated tests): before printing, a
# tiny marker in each table row's first cell (PROBE_MARK, nearly transparent, positioned so it moves nothing); after
# printing, the markers read back from the PDF say which page each row printed on, and table_split_problems checks
# the split rule against them. A client PDF never carries a marker: the probe is off unless the variable is set.
PROBE_ENV = "LAYOUT_PROBE"
PROBE_WORD = re.compile(r"qq(\d+)x(\d+)qq")
PROBE_JS = r"""([summary]) => {
  const out = [];
  for (const tb of document.querySelectorAll('table')) {
    if (tb.closest('svg')) continue;
    const rows = Array.from(tb.tBodies).flatMap(b => Array.from(b.rows));
    if (!rows.length || !tb.getClientRects().length) continue;
    const t = out.length;
    rows.forEach((r, i) => {
      const td = r.cells[0]; if (!td) return;
      td.style.position = 'relative';
      const s = document.createElement('span');
      s.textContent = `qq${t}x${i}qq`;
      s.style.cssText = 'position:absolute;left:0;top:0;font-size:1px;line-height:1px;color:rgba(255,255,255,0.01);' +
                        'white-space:nowrap;pointer-events:none';
      td.appendChild(s);
    });
    out.push({n: rows.length, whole: tb.dataset.split !== 'rows', side: parseInt(tb.dataset.side || '0', 10),
              summary: rows.map((r, i) => summary.some(c => r.classList.contains(c)) ? i : -1).filter(i => i >= 0),
              first: (rows[0].innerText || '').replace(/\s+/g, ' ').trim().slice(0, 40)});
  }
  return out;
}"""


def probing():
    return bool(os.environ.get(PROBE_ENV))


def probe_rows(pg):
    """Mark every table row for the read-back (PROBE_JS). Returns the tables: [{n, whole, summary, first}]."""
    return pg.evaluate(PROBE_JS, [list(SUMMARY_ROWS)])


def row_pages(pdf):
    """{(table, row): page} from the probe's markers in a printed PDF (pages from 1). {} without pdftotext."""
    tool = shutil.which("pdftotext")
    if not tool:
        return {}
    try:
        text = subprocess.run([tool, pdf, "-"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return {}
    out = {}
    for page, chunk in enumerate(text.split("\f"), 1):
        for t, r in PROBE_WORD.findall(chunk):
            out.setdefault((int(t), int(r)), page)
    return out


def table_split_problems(tables, pages, name=""):
    """Where a printed table broke the split rule, as sentences: a small table (TABLE_BREAKS_JS marked it whole) split
    at all, a page holding fewer rows of a split table than its side minimum, or a summary row printed apart from the
    rows above it. `tables` is probe_rows' list, `pages` row_pages' map."""
    out = []
    for t, tb in enumerate(tables or []):
        where = [pages.get((t, i)) for i in range(tb["n"])]
        if None in where or len(set(where)) < 2:
            continue
        label = f"{name}: the table starting \"{tb['first']}\""
        if tb["whole"]:
            out.append(f"{label} is small ({tb['n']} rows) yet is a split table (pages {where[0]} to {where[-1]}); "
                       "a small table never splits")
            continue
        for p in sorted(set(where)):
            k = where.count(p)
            if k < (tb.get("side") or SPLIT_MIN_ROWS):
                out.append(f"{label}: page {p} holds only {k} row{'s' if k != 1 else ''} of a split table")
        for i in tb["summary"]:
            lo = max(0, i - SPLIT_MIN_ROWS + 1)
            if len(set(where[lo:i + 1])) > 1:
                out.append(f"{label}: its summary row {i + 1} printed apart from the rows above it in a split table")
    return out


PAGINATE_JS = """([pageH, starts, minRows = 3]) => {
  // Page 1 fits itself: tighten in steps (fit1 → fit3, cumulative) until it clears the page with a small margin.
  const one = document.querySelector('.onepage'); let fit = 0;
  while (one && fit < 3 && one.getBoundingClientRect().height > pageH - 16) one.classList.add('fit' + (++fit));
  const wrap = document.querySelector('.wrap');
  const base = wrap.getBoundingClientRect().top;
  let shift = 0; const moved = [];
  // Print layout runs a few pixels taller than this screen estimate, so a block must fit with room to spare;
  // otherwise it splits or moves at print time and leaves a gap the shrink rule never saw (CMA-274).
  // Results_v5: a table or list runs on once a fifth of the page is left (it was a third: whole pages went 35-60% empty)
  const SAFE = 16, FLOW_ROOM = 0.2, PLAIN_WHOLE = 0.15;
  const squash = s => (s || '').replace(/\\s+/g, ' ').trim().toLowerCase();
  // A kept group that runs on: each of `units` stays whole and starts the next page when it doesn't fit this one
  const split = (el, units) => {
    el.classList.add('split');
    for (const u of units) {
      const ur = u.getBoundingClientRect(), tt = ur.top - base + shift, pp = ((tt % pageH) + pageH) % pageH;
      if (pp > 5 && pp + ur.height > pageH - SAFE) shift += pageH - pp;
    }
  };
  for (const el of Array.from(wrap.children)) {
    const r = el.getBoundingClientRect();
    const mt = parseFloat(getComputedStyle(el).marginTop) || 0;
    let t = r.top - base - mt + shift; const h = r.height + mt;
    let pos = ((t % pageH) + pageH) % pageH;
    // A block the print read-back saw starting a page that this estimate put lower on the page before (drift from an
    // earlier block that printed taller): it starts the next page here too, so what follows is placed as it prints
    const text = squash(el.innerText);
    if (pos > 5 && text && (starts || []).some(s => text.startsWith(s))) { shift += pageH - pos; t += pageH - pos; pos = 0; }
    if (el.classList.contains('onepage')) window.__onepageH = h;
    if (el.classList.contains('pb')) { if (pos > 5) shift += pageH - pos; continue; }
    const isKeep = el.classList.contains('kg');
    // A short plain block (a paragraph between groups) that would reach the page's bottom margin starts the next page:
    // the print moves it whole (a split paragraph keeps whole lines and at least two of them a side) where this
    // estimate would let it run on, so what follows printed lower than placed here
    if (pos > 5 && !isKeep && !el.classList.contains('onepage') && h > 0 && h <= PLAIN_WHOLE * pageH
        && pos + h > pageH - SAFE) {
      el.classList.add('pb'); shift += pageH - pos; continue;
    }
    if (isKeep && h > 0.8 * pageH) el.classList.add('big');
    const keepOK = isKeep && !el.classList.contains('big');
    if (el.classList.contains('big')) {
      const rows = {};
      el.querySelectorAll('.comp').forEach(c => { const cr = c.getBoundingClientRect(); const k = Math.round(cr.top);
        rows[k] = Math.max(rows[k] || 0, cr.height); });
      Object.keys(rows).map(Number).sort((a, b) => a - b).forEach(top => {
        const tt = top - base + shift, pp = ((tt % pageH) + pageH) % pageH;
        if (pp > 5 && pp + rows[top] > pageH - SAFE) shift += pageH - pp;
      });
      continue;
    }
    let brk = false;
    // A group that opts in (.runon: the seller CMA's How This Was Prepared) runs on to the next page block by block
    // instead of moving whole and leaving the page before part empty (Results_v4 case 02), once its heading and first
    // block fit here.
    // Results_v5: so does a group of headings and paragraphs only (no table, chart or list to keep whole), from a fifth
    const textOnly = isKeep && Array.from(el.children).every(c => /^(H2|H3|P)$/.test(c.tagName));
    const runon = el.classList.contains('runon') || textOnly;
    if (pos > 5 && isKeep && runon && pos + h > pageH - SAFE && pageH - pos >= (textOnly ? FLOW_ROOM : 0.25) * pageH) {
      const units = Array.from(el.children).slice(1);
      if (units.length && pos + units[0].getBoundingClientRect().bottom - r.top + mt <= pageH - SAFE) {
        split(el, units);
        continue;
      }
    }
    // a section never starts in the bottom quarter of a page, unless all of it fits there (Results_v5: a short section
    // that fits stays, rather than leave the page a quarter empty)
    if (pos > 5 && el.classList.contains('sec') && pos > 0.75 * pageH && !(keepOK && pos + h <= pageH - SAFE)) brk = true;
    else if (pos > 5 && keepOK && pos + h > pageH - SAFE) {
      // CMA-252: a scatter that almost fits the rest of a page shrinks (to 80% at most, or what its data-shrink
      // allows) rather than move and leave half the page empty; it moves only when less than 40% of the page is left
      // or it would need to shrink more.
      const svg = el.querySelector('svg.scatter'), over = pos + h - pageH + SAFE;
      const sr = svg ? svg.getBoundingClientRect() : null;
      const most = svg ? (parseFloat(svg.dataset.shrink) || 0.2) : 0.2;
      const shrink = by => { svg.style.width = (sr.width * (sr.height - by) / sr.height) + 'px'; el.classList.add('shrunk'); };
      // The notes after a group's figure (an excluded-homes note, a chart's read-out box) may follow it to the next
      // page: when the heading, intro and figure fit here (the scatter shrinking within its limit), only the notes
      // move, rather than the whole group leaving half the page empty
      const kids = Array.from(el.children); let k = kids.length;
      while (k > 1 && kids[k - 1].matches('p.note, .chart-read')) k--;
      const tailUnits = kids.slice(k);
      const headOver = tailUnits.length ? pos + kids[k - 1].getBoundingClientRect().bottom - r.top + mt - pageH + SAFE : 0;
      if (sr && pageH - pos >= 0.4 * pageH && over <= most * sr.height) {
        shrink(over);
      } else if (tailUnits.length && pageH - pos >= 0.4 * pageH && (headOver <= 0 || (sr && headOver <= most * sr.height))) {
        if (headOver > 0) shrink(headOver);
        split(el, tailUnits);
      } else if (!svg && !el.querySelector('.tbl.whole') && pageH - pos >= FLOW_ROOM * pageH) {
        // A table or list block that would leave this much of the page empty runs on instead, whole rows or items
        // only, once its heading, intro and first few rows fit here (the table's header row repeats on the next page).
        // A table marked .whole (the buyer CMA's Price vs. Seller Credit: its columns read across every row) never
        // runs on: its block moves whole (iteration 12)
        const tb = el.querySelector('.tbl'), rows = tb ? tb.querySelectorAll('tbody tr') : [];
        const items = tb ? [] : el.querySelectorAll(':scope > ul > li, :scope > ol > li');
        // A table runs on only when the split rule lets it (TABLE_BREAKS_JS marked it data-split="rows"), with
        // SPLIT_MIN_ROWS of its rows here; the rows' own break rules keep as many for the next page
        const parts = tb ? rows : items, keep = tb ? (parseInt(tb.dataset.side, 10) || minRows) : 2;
        const enough = tb ? tb.dataset.split === 'rows' : parts.length >= keep + 2;
        if (enough && pos + parts[keep - 1].getBoundingClientRect().bottom - r.top + mt <= pageH - SAFE) {
          el.classList.add('flow');
          if (tb) tb.classList.add('brk');
          const th = tb ? tb.querySelector('thead') : null;
          // the gap left at the break and the repeated header row, roughly
          shift += (th ? th.getBoundingClientRect().height : 0) + parts[keep].getBoundingClientRect().height;
        } else brk = true;
      } else brk = true;
    }
    if (brk) { el.classList.add('pb'); shift += pageH - pos; moved.push((el.innerText || '').split('\\n')[0].slice(0, 50)); }
  }
  return { moved, onepageH: window.__onepageH || 0, pageH, fit };
}"""


# --- reading the printed pages back ---------------------------------------------------------

# CMA-274, CMA-276: how full each printed page is, read back from the PDF (the layout measured before printing can
# drift a few pixels from Chromium's print layout, enough to push a block to the next page)
HALF_EMPTY = 0.5  # a page before a kept-together block that ends above half the page leaves a gap worth fixing
LONE_TAIL = 0.15  # a last page this empty holds only a few closing lines
_WORD = re.compile(r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="[\d.]+" yMax="([\d.]+)">([^<]*)</word>')
_PAGE = re.compile(r'width="[\d.]+" height="([\d.]+)"')


def page_fill(pdf, top_in=0.45, bottom_in=0.55):
    """[(fill, first line)] per page: how far down the content area the text reaches (0 to 1) and the page's first
    line, from pdftotext -bbox. None when pdftotext isn't available. The content area is the page less the top and
    bottom margins in inches (cma.PAGE_MARGINS by default; 0.3 and 0.4 for render.html_to_pdf's default), on a page of
    any height (a landscape page too)."""
    tool = shutil.which("pdftotext")
    if not tool:
        return None
    try:
        out = subprocess.run([tool, "-bbox", pdf, "-"], capture_output=True, text=True, timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return None
    pages = []
    for chunk in out.split("<page ")[1:]:
        height = _PAGE.match(chunk)
        top_pt, bottom_pt = top_in * 72, (float(height.group(1)) if height else 792) - bottom_in * 72
        words = [(float(x), float(y0), float(y1), html.unescape(t)) for x, y0, y1, t in _WORD.findall(chunk)
                 if float(y1) <= bottom_pt + 1  # the running footer sits below the content area
                 and not PROBE_WORD.fullmatch(html.unescape(t))]  # the layout probe's row markers aren't content
        if not words:
            pages.append((0.0, ""))
            continue
        bottom = max(w[2] for w in words)
        top = min(w[1] for w in words)
        first = " ".join(w[3] for w in sorted((w for w in words if w[1] - top < 3), key=lambda w: w[0]))
        pages.append((max(0.0, (bottom - top_pt) / (bottom_pt - top_pt)), first[:60]))
    return pages


def squash(text):
    return " ".join(str(text).split()).lower()


def page_checks(pages, tail_hint="the last sections"):
    """Checks for pages 2 onward: one that ends above half the page before a block that moved on, and a last page
    holding only a few closing lines."""
    checks = []
    for i in range(1, len(pages) - 1):
        fill, _ = pages[i]
        if fill < HALF_EMPTY:
            checks.append(f"Page {i + 1} is only {fill:.0%} full: the next block (\"{pages[i + 1][1]}\") didn't fit and "
                          f"starts page {i + 2}. Shorten the wording before it on page {i + 1} or in that block (its intro, "
                          "a comp bullet, a note) so it fits, then render again.")
    if len(pages) > 2 and pages[-1][0] < LONE_TAIL:
        checks.append(f"The last page (page {len(pages)}) holds only a few closing lines (\"{pages[-1][1]}\"): shorten "
                      f"{tail_hint} so they fit on the page before, then render again.")
    return checks


# --- the page-fit pipeline -------------------------------------------------------------------------

PAGE1_LIMIT = 989  # px page 1 holds at the print viewport with render.html_to_pdf's margins (portrait)
PAGE1_LIMIT_WIDE = 749  # the same, landscape
SPILL_RETRY_PX = 40  # Chromium's print layout can run a little longer than the measured one (CMA-274): refit this tighter
DEFAULT_MARGINS = {"top": "0.3in", "right": "0.3in", "bottom": "0.4in", "left": "0.3in"}


def _inches(v):
    v = str(v).strip()
    return float(v[:-2]) if v.endswith("in") else float(v.rstrip("px")) / 96


@dataclass
class Fit:
    """How one document fits its pages. Every PDF prints through print_pdf with one of these.

    limit: px page 1 may fill; None for the whole printable height (PAGE1_LIMIT portrait, PAGE1_LIMIT_WIDE
        landscape, at the default margins).
    end: the selector whose top is where page 1 ends (".pb"); None when there is no page-1 boundary to fit (a
        paginated report whose page 1 fits itself, .onepage in PAGINATE_JS).
    one_page: the whole document is one page: page 1 is the body's height (end is ignored).
    steps: tried in order, cumulative, until page 1 fits: a body class name ("compact") or a JS function
        ("() => ..."). Each is applied only while page 1 is still over the limit.
    tail: body class names tried when the last page is under `tail_below` full (a denser detail section), each
        kept only when it saves a page without pushing page 1 over its limit. Every Fit then tries KEEP_TAIL when the
        last page still holds only a few closing lines (under LONE_TAIL), with or without tail steps of its own.
    tail_below: how empty a last page must be before the tail steps are tried (LONE_TAIL; 1.0 tries them always).
    blocks: (selector, name) of page 1's data-driven blocks, named tallest first when page 1 still overflows.
    paginate: the later pages keep heading groups together and let long tables run on (group_blocks markup inside a
        .wrap, PAGINATE_JS), with a second print when the read-back shows a block printed lower than estimated.
    landscape, margins: the page (render.html_to_pdf's defaults when None).
    """
    limit: float = None
    end: str = ".pb"
    one_page: bool = False
    steps: tuple = ()
    tail: tuple = ()
    tail_below: float = LONE_TAIL
    blocks: tuple = ()
    paginate: bool = False
    landscape: bool = False
    margins: dict = None
    tail_hint: str = "the last sections"

    def __post_init__(self):
        bad = [t for t in self.tail if not re.fullmatch(r"[\w-]+", str(t))]
        if bad:
            raise ValueError(f"tail steps are body class names: {bad}")

    def page_margins(self):
        return self.margins or DEFAULT_MARGINS

    def page_limit(self):
        return self.content_px()[1] if self.limit is None else self.limit

    def content_px(self):
        """(width, height) of the printable area in CSS px."""
        m = self.page_margins()
        w, h = (11, 8.5) if self.landscape else (8.5, 11)
        return (round((w - _inches(m["left"]) - _inches(m["right"])) * 96),
                round((h - _inches(m["top"]) - _inches(m["bottom"])) * 96))


def _js(step):
    return step if "=>" in step or step.lstrip().startswith("function") else \
        f"() => document.body.classList.add({json.dumps(step)})"


_MEASURE = """([end, one]) => { if (one) return document.body.getBoundingClientRect().height;
  const e = end ? document.querySelector(end) : null; return e ? e.getBoundingClientRect().top : 0; }"""
_FIRST_LINE = """(end) => { const e = end ? document.querySelector(end) : null;
  return e ? (e.innerText || '').trim().split('\\n')[0] : ''; }"""
_PAGES = re.compile(rb"/Type\s*/Page(?![a-zA-Z])")
# The tail step every Fit tries last, after its own: when the last page would still hold only a few closing lines,
# the document's last block (the closing notices) keeps with the block before it, so that block moves on with it and
# the last page holds both. A last block that starts a page on purpose (break-before: page, a .pb section) is left as
# it is. Kept only when the last page then fills past LONE_TAIL with no page added and no page between the first and
# the last left under half full that wasn't before.
KEEP_TAIL = "keep-tail"
_KEEP_TAIL_JS = """(on) => { const e = document.body.lastElementChild; if (!e) return false;
  if (!on) { if (e.dataset.keepTail) { e.style.breakBefore = ''; delete e.dataset.keepTail; } return false; }
  if (getComputedStyle(e).breakBefore !== 'auto') return false;
  e.style.breakBefore = 'avoid'; e.dataset.keepTail = '1'; return true; }"""


def _print(pg, fit):
    return pg.pdf(format="Letter", landscape=fit.landscape, print_background=True, margin=fit.page_margins())


def _page_count(pg, fit):
    return len(_PAGES.findall(_print(pg, fit)))


def _fills(pg, fit):
    """The page_fill read-back of the page as it prints now (None without pdftotext)."""
    m = fit.page_margins()
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "fit.pdf")
        with open(path, "wb") as f:
            f.write(_print(pg, fit))
        return page_fill(path, _inches(m["top"]), _inches(m["bottom"]))


def _lone_tail(pages):
    return bool(pages) and len(pages) > 1 and pages[-1][0] < LONE_TAIL


def _keep_tail(pg, fit):
    """Try KEEP_TAIL on a last page holding only a few closing lines; True when it's kept."""
    before = _fills(pg, fit)
    if not _lone_tail(before):
        return False
    if not pg.evaluate(_KEEP_TAIL_JS, True):
        return False
    after = _fills(pg, fit)
    gaps = lambda pages: sum(f < HALF_EMPTY for f, _ in pages[1:-1])
    if after and len(after) <= len(before) and not _lone_tail(after) and gaps(after) <= gaps(before):
        return True
    pg.evaluate(_KEEP_TAIL_JS, False)
    return False


def fit_page(pg, fit, limit=None, starts=(), tail=False):
    """The before_print step: fit page 1 (fit.steps), lay out the later pages (fit.paginate), then, with `tail`, try
    the tail steps (kept only when they save a page). Returns {top, limit, steps, blocks, end_line, paginate}."""
    limit = fit.page_limit() if limit is None else limit
    width, height = fit.content_px()
    pg.set_viewport_size({"width": width, "height": 1000})
    table_break_rules(pg, height)
    top, used = pg.evaluate(_MEASURE, [fit.end, fit.one_page]), []
    for step in fit.steps:
        if top <= limit:
            break
        pg.evaluate(_js(step))
        used.append(step)
        top = pg.evaluate(_MEASURE, [fit.end, fit.one_page])
    info = {"top": top, "limit": limit, "steps": used, "blocks": [], "tail": [],
            "end_line": "" if fit.one_page else pg.evaluate(_FIRST_LINE, fit.end)}
    if fit.paginate:
        res = pg.evaluate(PAGINATE_JS, [height, list(starts), SPLIT_MIN_ROWS])
        info["paginate"] = {"moved": res["moved"], "page1_px": round(res["onepageH"]), "fit_level": res["fit"]}
    if tail:
        pages = _page_count(pg, fit) if fit.tail else 0
        for step in fit.tail:
            pg.evaluate(f"() => document.body.classList.add({json.dumps(step)})")
            now = _page_count(pg, fit)
            if now < pages and pg.evaluate(_MEASURE, [fit.end, fit.one_page]) <= max(limit, top):
                info["tail"].append(step)
                pages = now
            else:
                pg.evaluate(f"() => document.body.classList.remove({json.dumps(step)})")
        if _keep_tail(pg, fit):
            info["tail"].append(KEEP_TAIL)
    if top > limit and fit.blocks:
        heights = pg.evaluate("(sels) => sels.map(s => { const e = document.querySelector(s);"
                              " return e ? e.getBoundingClientRect().height : 0; })", [s for s, _ in fit.blocks])
        info["blocks"] = sorted(((h, name) for h, (_, name) in zip(heights, fit.blocks) if h), reverse=True)
    return info


def problems(pages, info, fit):
    """What the printed pages show: "spill" (page 1 ran onto page 2 although the measure said it fit), "tail" (a last
    page after the detail pages' first under fit.tail_below full, which tail steps may save, or any last page after the
    first under LONE_TAIL full, which KEEP_TAIL may fill), "gap" (with
    fit.paginate, a page between the first and the last under half full). [] when fine or when the pages couldn't be
    read."""
    if not pages:
        return []
    out = []
    fitted = info["top"] <= info["limit"]
    if fit.one_page:
        if len(pages) > 1 and fitted:
            out.append("spill")
    elif fitted and len(pages) > 1 and info["end_line"] and \
            not squash(pages[1][1]).startswith(squash(info["end_line"])[:20]):
        out.append("spill")
    if (fit.tail and len(pages) > (1 if fit.one_page else 2) and pages[-1][0] < fit.tail_below) or _lone_tail(pages):
        out.append("tail")
    if fit.paginate and any(f < HALF_EMPTY for f, _ in pages[1:-1]):
        out.append("gap")
    return out


def print_pdf(doc, path, fit=None, footer_html=None):
    """Print `doc` to `path`, fitted by `fit` (a Fit), then read the pages back and print once more when they show a
    spill (refit SPILL_RETRY_PX tighter), a short last page the tail steps may save, or (fit.paginate) a page left
    under half full by a block that printed lower than estimated. The second print is kept only when it's better
    (fewer pages, or fewer problems). Returns the fit info plus "pages" ([(fill, first line)] or None),
    "problems" and "checks" (sentences for stderr)."""
    from . import render
    fit = fit or Fit()
    margins = fit.page_margins()
    top_in, bottom_in = _inches(margins["top"]), _inches(margins["bottom"])

    probe = probing()

    def before(pg, limit, starts, tail):
        info = fit_page(pg, fit, limit, starts, tail)
        if probe:  # last, after every measurement: the markers move nothing, but nothing measures them either
            info["probe_tables"] = probe_rows(pg)
        return info

    def once(target, limit=None, starts=(), tail=False):
        info = render.html_to_pdf(doc, target, margins=margins, footer_html=footer_html, landscape=fit.landscape,
                                  before_print=lambda pg: before(pg, limit, starts, tail))
        return info, page_fill(target, top_in, bottom_in)

    info, pages = once(path)
    found = problems(pages, info, fit)
    if found:
        limit = fit.page_limit() - SPILL_RETRY_PX if "spill" in found else None
        starts = [squash(pages[i][1])[:30] for i in range(1, len(pages) - 1)
                  if pages[i][0] < HALF_EMPTY and pages[i][1].strip()] if "gap" in found else ()
        with tempfile.TemporaryDirectory() as tmp:
            second = os.path.join(tmp, os.path.basename(path))
            info2, pages2 = once(second, limit, starts, tail="tail" in found)
            found2 = problems(pages2, info2, fit) if pages2 is not None else found
            better = pages2 is not None and (
                (len(pages2) < len(pages) and "spill" not in found2) or
                (len(found2) < len(found) and len(pages2) <= len(pages)) or
                ("spill" in found and "spill" not in found2))
            if better:
                shutil.move(second, path)
                info, pages, found = info2, pages2, found2
    checks = []
    if info["top"] > info["limit"]:
        what = ", ".join(f"{n} ({h:.0f}px)" for h, n in info["blocks"][:2]) or "page 1's content"
        checks.append(f"{os.path.basename(path)}: page 1 overflows by {info['top'] - info['limit']:.0f}px; the tallest "
                      f"blocks are {what}. Shorten the text that fills them.")
    if fit.paginate and pages:
        checks += page_checks(pages, fit.tail_hint)
    splits = table_split_problems(info.get("probe_tables"), row_pages(path), os.path.basename(path)) if probe else []
    for line in splits:  # dev only (LAYOUT_PROBE): make layout-check and the generated tests read stderr
        print(f"Check: {line}.", file=sys.stderr)
    return {**info, "pages": pages, "problems": found, "checks": checks, "table_splits": splits}

