"""Output helpers shared by every skill's scripts/render.py.

    from _shared import render
    def build(data, fmt, out_dir, ctx): ...     # returns the paths it wrote
    if __name__ == "__main__":
        render.main(build, formats=("pdf",))

ctx carries the agent profile (always a dict, empty fields when there's none), the market profile
path, and whether this is sample data.

Implements the render contract (docs/development.md#skill-render-contract) and the output
location rule (docs/architecture.md#output-location).
"""
import argparse
import html
import json
import os
import re
import sys
import unicodedata

SANDBOX_OUTPUTS = "/mnt/user-data/outputs"
SKILL_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))  # <skill>/scripts/_shared


def output_dir(explicit=None):
    """Where files go: explicit --out, then OUTPUT_DIR (local dev), then the sandbox outputs, then cwd.

    Never the skill's own folder, which is the working directory in claude.ai.
    """
    for d in (explicit, os.environ.get("OUTPUT_DIR")):
        if d:
            os.makedirs(d, exist_ok=True)
            return os.path.abspath(d)
    if os.path.isdir(SANDBOX_OUTPUTS):
        return SANDBOX_OUTPUTS
    cwd = os.getcwd()
    if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "_shared" and \
            os.path.commonpath([cwd, SKILL_DIR]) == SKILL_DIR:
        raise RuntimeError("Refusing to write outputs into the skill's own folder; set --out or OUTPUT_DIR.")
    return cwd


def filename(*parts, ext):
    """'517 Hickorywood Dr', 'Buyer CMA' -> '517-Hickorywood-Dr-Buyer-CMA.pdf'. ASCII, no spaces."""
    text = " ".join(str(p) for p in parts if p)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")
    return f"{slug or 'output'}.{ext.lstrip('.')}"


REPORT_CSS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "report.css")


def page(body, css="", title="", theme_css="", body_class=""):
    """A complete HTML document: shared report.css, then the theme's color variables, then skill CSS.

    `theme_css` is design.css_vars(theme).
    """
    with open(REPORT_CSS, encoding="utf-8") as f:
        base = f.read()
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{base}{theme_css}{css}</style></head><body class='{body_class}'>{body}</body></html>")


def footer(left, right_pages=True):
    """Chromium footer template: `left` text and 'Page X of Y'."""
    pages = ('Page <span class="pageNumber"></span> of <span class="totalPages"></span>'
             if right_pages else "")
    return ('<div style="font-size:7pt;color:#5A6672;width:100%;padding:0 0.3in;display:flex;'
            'justify-content:space-between;font-family:Helvetica,Arial,sans-serif">'
            f"<span>{html.escape(left)}</span><span>{pages}</span></div>")


def html_to_pdf(doc, path, fmt="Letter", margins=None, footer_html=None, before_print=None):
    """Print HTML to PDF with Chromium (print media, backgrounds on).

    `before_print(page)` can measure or adjust layout first; its return value is returned.
    """
    from playwright.sync_api import sync_playwright

    margins = margins or {"top": "0.3in", "right": "0.3in", "bottom": "0.4in", "left": "0.3in"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            pg = browser.new_page(viewport={"width": 758, "height": 1000})  # 8.5in minus margins, at 96 dpi
            pg.set_content(doc, wait_until="load")
            pg.emulate_media(media="print")
            info = before_print(pg) if before_print else None
            pg.pdf(path=path, format=fmt, print_background=True, margin=margins,
                   display_header_footer=bool(footer_html), header_template="<span></span>",
                   footer_template=footer_html or "<span></span>")
        finally:
            browser.close()
    return info


def write_text(text, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main(build, formats, argv=None, extra_args=None, errors=()):
    """Command line for scripts/render.py: DATA.json --format <fmt>|all --out DIR [--agent] [--market] [--sample].

    `build(data, fmt, out_dir, ctx)` renders one format and returns the list of paths written.
    `extra_args(parser)` adds the skill's own options (--cma, --mode...); their values arrive in `ctx` by name.
    `ctx["formats"]` lists every format this run renders, so work shared across formats can be done once.
    `errors` are exception types that mean bad input: they end the run with their message, not a traceback.
    Before anything is built, the data's text is checked (prose.check: no em dashes, no fair-housing
    red flags); a problem stops the run with the fields to rewrite.
    With several formats, one that fails doesn't stop the others: the files that were made are printed,
    then the run exits with a message naming what wasn't built.
    Prints each path, one per line, so Claude can present them.
    """
    from . import profiles, prose

    ap = argparse.ArgumentParser(description="Render this skill's files from its data file.")
    ap.add_argument("data", help="the skill's data JSON")
    ap.add_argument("--format", default="all", choices=[*formats, "all"])
    ap.add_argument("--out", help="output folder (default: sandbox outputs, or OUTPUT_DIR locally)")
    ap.add_argument("--agent", help="agent profile (name, brokerage, brand colors on the report)")
    ap.add_argument("--market", help="market profile")
    ap.add_argument("--sample", action="store_true", help="label the report SAMPLE DATA")
    base = {a.dest for a in ap._actions}
    if extra_args:
        extra_args(ap)
    args = ap.parse_args(argv)
    todo = list(formats) if args.format == "all" else [args.format]
    errors = (profiles.ProfileError, prose.ProseError, *errors)

    try:
        with open(args.data, encoding="utf-8") as f:
            data = json.load(f)
        prose.check(data)
        ctx = {"agent": profiles.load_agent(args.agent), "market": args.market, "sample": args.sample, "formats": todo,
               **{k: v for k, v in vars(args).items() if k not in base}}
    except (OSError, ValueError, *errors) as e:
        sys.exit(str(e))
    out_dir = output_dir(args.out)
    written, failed = [], []
    for fmt in todo:
        try:
            written += [p for p in build(data, fmt, out_dir, ctx) if p not in written]
        except errors as e:
            failed.append((fmt, str(e)))
    for path in written:
        print(path)
    if failed:
        if not written or len(todo) == 1:
            sys.exit(failed[0][1])
        sys.exit("\n".join(f"The {fmt} file wasn't built: {msg}" for fmt, msg in failed))
    return written


if __name__ == "__main__":
    sys.exit("Import this module from a skill's scripts/render.py.")
