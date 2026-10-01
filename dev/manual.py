"""Build the PDF manual from the agent guide (REL-101).

    .venv/bin/python dev/manual.py            # make manual: writes dev/package/Real-Estate-Skills-Manual.pdf
    .venv/bin/python dev/manual.py --check    # fail when the manual is older than its sources (make package runs it)

The guide, dev/package/README.md, is the only text: the manual is that guide with a cover, a contents page and the
screenshots in dev/package/images/. A screenshot goes in the guide as an HTML comment on its own line,

    <!-- figure: images/export-settings.png | On the Settings page, open Custom Exports. -->

which markdown viewers hide; package.py strips these lines from the README copy in the release zip. Consecutive
figure lines sit side by side. Styles are in dev/package/manual.css (neutral grays, print-light). The markdown
reader covers what the guide uses: headings, paragraphs, nested lists, tables, bold, code and links.

The manual carries no version, so a release bump doesn't rebuild it. dev/package/manual.sha256 records the hash of
everything the PDF is built from; --check compares it, so a guide edit without `make manual` stops `make package`.
"""
import hashlib
import html
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
PKG = os.path.join(ROOT, "dev", "package")
GUIDE = os.path.join(PKG, "README.md")
CSS = os.path.join(PKG, "manual.css")
PDF = os.path.join(PKG, "Real-Estate-Skills-Manual.pdf")
STAMP = os.path.join(PKG, "manual.sha256")
TITLE = "Installation Manual and User Guide"
FIGURE = re.compile(r"^\s*<!--\s*figure:\s*(\S+)\s*\|\s*(.*?)\s*-->\s*$")
COMMENT = re.compile(r"^\s*<!--.*-->\s*$")
LIST_ITEM = re.compile(r"^(\s*)(\d+\.|-)\s+(.*)$")


def figures(text):
    """(path, caption) for every figure line in the guide, paths relative to dev/package/."""
    return [(m.group(1), m.group(2)) for m in map(FIGURE.match, text.splitlines()) if m]


def strip_figures(text):
    """The guide without its figure lines (and the blank line each group leaves), for the release zip's README."""
    text = re.sub(r"(?m)^[ \t]*<!--\s*figure:.*-->[ \t]*\n", "", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def inline(text):
    """Bold, code spans and links; everything else escaped."""
    parts = re.split(r"(`[^`]+`)", text)
    out = []
    for part in parts:
        if part.startswith("`") and part.endswith("`") and len(part) > 1:
            out.append(f"<code>{html.escape(part[1:-1])}</code>")
            continue
        s = html.escape(part, quote=False)
        s = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", s)
        s = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', s)
        s = re.sub(r"(?<![\"'>])(https?://[^\s<]+)", r'<a href="\1">\1</a>', s)
        out.append(s)
    return "".join(out)


def _figure_row(figs):
    cells = "".join(f'<figure><img src="{html.escape(src)}" alt=""><figcaption>{inline(cap)}</figcaption></figure>'
                    for src, cap in figs)
    return f'<div class="figures n{len(figs)}">{cells}</div>'


def _table(rows):
    cells = [[c.strip() for c in r.strip().strip("|").split("|")] for r in rows]
    head, body = cells[0], [r for r in cells[1:] if not all(re.fullmatch(r":?-+:?", c) for c in r)]
    th = "".join(f"<th>{inline(c)}</th>" for c in head)
    trs = "".join("<tr>" + "".join(f"<td>{inline(c)}</td>" for c in r) + "</tr>" for r in body)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def _list(lines):
    """One list (ordered or not) from lines that start at its marker's indent; items may hold nested blocks."""
    first = LIST_ITEM.match(lines[0])
    indent, ordered = len(first.group(1)), first.group(2)[0].isdigit()
    items, cur = [], None
    for line in lines:
        m = LIST_ITEM.match(line)
        if m and len(m.group(1)) == indent:
            cur = [m.group(3)]
            items.append(cur)
        else:
            cur.append(line[indent:] if line.strip() else "")
    tag = "ol" if ordered else "ul"
    start = f' start="{first.group(2)[:-1]}"' if ordered and first.group(2) != "1." else ""
    lis = []
    for item in items:
        body = _dedent(item)
        inner = blocks(body)
        if inner.startswith("<p>") and inner.count("<p>") == 1:  # a tight item: no paragraph margins
            inner = inner[3:].replace("</p>", "", 1)
        lis.append(f"<li>{inner}</li>")
    return f"<{tag}{start}>{''.join(lis)}</{tag}>"


def _dedent(item):
    """An item's first line plus its continuation lines, dedented to the item's content column."""
    rest = item[1:]
    widths = [len(line) - len(line.lstrip()) for line in rest if line.strip()]
    cut = min(widths) if widths else 0
    return [item[0]] + [line[cut:] for line in rest]


def blocks(lines):
    """Markdown lines to HTML: headings, figure rows, tables, lists and paragraphs."""
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
        elif FIGURE.match(line):
            figs = []
            while i < len(lines) and FIGURE.match(lines[i]):
                figs.append(FIGURE.match(lines[i]).groups())
                i += 1
            out.append(_figure_row(figs))
        elif COMMENT.match(line):
            i += 1
        elif m := re.match(r"^(#{1,4})\s+(.*)$", line):
            level = len(m.group(1))
            text = m.group(2)
            slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            out.append(f'<h{level} id="{slug}">{inline(text)}</h{level}>')
            i += 1
        elif line.lstrip().startswith("|"):
            j = i
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                j += 1
            out.append(_table(lines[i:j]))
            i = j
        elif LIST_ITEM.match(line):
            indent = len(LIST_ITEM.match(line).group(1))
            j = i + 1
            while j < len(lines):
                nxt = lines[j]
                if not nxt.strip():
                    k = j
                    while k < len(lines) and not lines[k].strip():
                        k += 1
                    if k < len(lines) and (len(lines[k]) - len(lines[k].lstrip()) > indent
                                           or (LIST_ITEM.match(lines[k]) and len(LIST_ITEM.match(lines[k]).group(1)) == indent)):
                        j = k
                        continue
                    break
                if len(nxt) - len(nxt.lstrip()) <= indent and not LIST_ITEM.match(nxt):
                    break
                if LIST_ITEM.match(nxt) and len(LIST_ITEM.match(nxt).group(1)) < indent:
                    break
                j += 1
            out.append(_list(lines[i:j]))
            i = j
        else:
            j = i
            while j < len(lines) and lines[j].strip() and not (
                    COMMENT.match(lines[j]) or LIST_ITEM.match(lines[j]) or lines[j].lstrip().startswith(("|", "#"))):
                j += 1
            out.append(f"<p>{inline(' '.join(s.strip() for s in lines[i:j]))}</p>")
            i = j
    return "".join(out)


def split_guide(text):
    """(title, intro paragraph, [(heading, lines)]) from the guide; its own Contents section is dropped (the cover
    lists the sections) and the version placeholder is removed (the manual carries no version)."""
    lines = text.replace("{{PLUGIN_FILE}}", "real-estate-<version>.plugin").splitlines()
    title = re.sub(r"\s*\{\{VERSION\}\}", "", lines[0].lstrip("# ")).strip()
    sections = [("", [])]
    for line in lines[1:]:
        m = re.match(r"^## (.*)$", line)
        if m:
            sections.append((m.group(1), []))
        else:
            sections[-1][1].append(line)
    head = sections[0][1]
    intro = next((line for line in head if line.strip()), "")
    rest = head[head.index(intro) + 1:] if intro else head
    sections = [("", rest)] + [s for s in sections[1:] if s[0] != "Contents"]
    return title, intro, sections


def build_html(text):
    title, intro, sections = split_guide(text)
    plugin = json.load(open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8"))
    author = plugin.get("author", {})
    site = re.sub(r"^https?://", "", plugin.get("homepage", "")).rstrip("/")
    contact = " · ".join(x for x in (author.get("email"), site) if x)
    toc = "".join(f"<li>{inline(h)}</li>" for h, _ in sections if h)
    body = [f'<section class="cover"><p class="eyebrow">Claude Plugin for Real Estate Agents</p>'
            f"<h1>{inline(title)}</h1><p class=\"subtitle\">{TITLE}</p><p class=\"lead\">{inline(intro)}</p>"
            f'<div class="toc"><h2>Contents</h2><ul>{toc}</ul></div>'
            f'<div class="byline"><span>{html.escape(author.get("name", ""))}</span>'
            f"<span>{html.escape(contact)}</span></div></section>"]
    for heading, lines in sections:
        inner = blocks(lines)
        if heading:
            slug = re.sub(r"[^a-z0-9]+", "-", heading.lower()).strip("-")
            body.append(f'<section class="chapter"><h2 id="{slug}">{inline(heading)}</h2>{inner}</section>')
        elif inner:
            body.append(f'<section class="chapter first">{inner}</section>')
    with open(CSS, encoding="utf-8") as f:
        css = f.read()
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}: {TITLE}</title>"
            f"<style>{css}</style></head><body>{''.join(body)}</body></html>")


def source_hash():
    """sha256 over the guide, the styles, this script and every image the guide shows."""
    with open(GUIDE, encoding="utf-8") as f:
        text = f.read()
    h = hashlib.sha256()
    for path in [GUIDE, CSS, os.path.abspath(__file__)] + [os.path.join(PKG, src) for src, _ in figures(text)]:
        h.update(os.path.relpath(path, ROOT).encode())
        with open(path, "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def missing_images(text):
    return [src for src, _ in figures(text) if not os.path.isfile(os.path.join(PKG, src))]


def stale():
    """Why the committed manual doesn't match its sources, or None when it does."""
    if not os.path.isfile(PDF):
        return f"no manual at {os.path.relpath(PDF, ROOT)}"
    try:
        with open(STAMP, encoding="utf-8") as f:
            recorded = f.read().strip()
    except OSError:
        return f"no {os.path.relpath(STAMP, ROOT)}"
    return None if recorded == source_hash() else "the guide, its images or the manual styles changed since the last build"


def build():
    from playwright.sync_api import sync_playwright

    with open(GUIDE, encoding="utf-8") as f:
        text = f.read()
    missing = missing_images(text)
    if missing:
        sys.exit("missing images: " + ", ".join(missing))
    doc = build_html(text)
    page_html = os.path.join(PKG, ".manual.html")  # beside the images so their relative paths resolve
    footer = ('<div style="font-size:7pt;color:#6B6B6B;width:100%;padding:0 0.6in;display:flex;'
              'justify-content:space-between;font-family:Helvetica,Arial,sans-serif">'
              f"<span>Real Estate Skills · {TITLE}</span>"
              '<span><span class="pageNumber"></span> / <span class="totalPages"></span></span></div>')
    try:
        with open(page_html, "w", encoding="utf-8") as f:
            f.write(doc)
        with sync_playwright() as p:
            browser = p.chromium.launch()
            try:
                pg = browser.new_page()
                pg.goto("file://" + page_html, wait_until="load")
                pg.emulate_media(media="print")
                pg.pdf(path=PDF, format="Letter", print_background=True, display_header_footer=True,
                       header_template="<span></span>", footer_template=footer,
                       margin={"top": "0.6in", "right": "0.6in", "bottom": "0.7in", "left": "0.6in"})
            finally:
                browser.close()
    finally:
        if os.path.exists(page_html):
            os.remove(page_html)
    with open(STAMP, "w", encoding="utf-8") as f:
        f.write(source_hash() + "\n")
    print(os.path.relpath(PDF, ROOT))


if __name__ == "__main__":
    if sys.argv[1:] == ["--check"]:
        why = stale()
        if why:
            sys.exit(f"The PDF manual is out of date ({why}): run make manual and commit the PDF.")
        print("manual: OK")
    elif sys.argv[1:]:
        sys.exit(f"usage: {sys.argv[0]} [--check]")
    else:
        build()
