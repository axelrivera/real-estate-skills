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


EHO = "Equal Housing Opportunity."
NOT_ADVICE = "Estimates only, not legal, lending or tax advice."


def notice_lines(agent, lines=(), marketing=False):
    """Closing notices for a client-facing file (CORE-3, FH-6): the skill's fixed lines, then the agent's
    disclaimers from their profile, verbatim, one paragraph each, then the brokerage's details when the profile has them. Marketing pieces (a listing presentation) add
    the Equal Housing Opportunity statement unless the agent's disclaimers already carry it."""
    disc = str((agent or {}).get("disclaimers") or "")
    paras = [" ".join(p.split()) for p in disc.replace("\r", "").split("\n\n") if p.strip()]
    out = [x for x in lines if x] + paras
    a = agent or {}
    extra = [f"Lic. {a['brokerage_license']}" if a.get("brokerage_license") else "", a.get("brokerage_address") or "",
             a.get("brokerage_phone") or ""]
    if a.get("brokerage") and any(extra):  # CORE-15: the brokerage's license, office and phone where a state requires them
        out.append(", ".join(str(x) for x in [a["brokerage"], *extra] if x) + ".")
    if marketing and "equal housing" not in disc.lower():
        out.append(EHO)
    return out


def notices(agent, lines=(), marketing=False):
    """The closing notices as an HTML block for the end of the document (empty when there are none)."""
    items = notice_lines(agent, lines, marketing)
    return ('<div class="notices">' + "".join(f"<p>{html.escape(x)}</p>" for x in items) + "</div>") if items else ""


def check_agent(agent):
    """CORE-4: an agent name on a client file needs the licensed brokerage name with it (Florida rule 61J2-10.025
    and most states' advertising rules). Raises ProfileError with what to ask for."""
    from . import profiles
    if str((agent or {}).get("name") or "").strip() and not str(agent.get("brokerage") or "").strip():
        raise profiles.ProfileError(
            "The agent profile has a name but no brokerage. Client files must show the brokerage's licensed name with "
            "the agent's name (Florida rule 61J2-10.025, and most states): ask for it (the licensed name, not a trade "
            "name), add it to the profile, then re-run.")


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


def html_to_pdf(doc, path, fmt="Letter", margins=None, footer_html=None, before_print=None, landscape=False):
    """Print HTML to PDF with Chromium (print media, backgrounds on).

    `before_print(page)` can measure or adjust layout first; its return value is returned.
    `landscape` turns the page (11in wide); layout is measured at the matching width.
    """
    from playwright.sync_api import sync_playwright

    margins = margins or {"top": "0.3in", "right": "0.3in", "bottom": "0.4in", "left": "0.3in"}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            width = 998 if landscape else 758  # page width minus margins, at 96 dpi
            pg = browser.new_page(viewport={"width": width, "height": 1000})
            pg.set_content(doc, wait_until="load")
            pg.emulate_media(media="print")
            info = before_print(pg) if before_print else None
            pg.pdf(path=path, format=fmt, landscape=landscape, print_background=True, margin=margins,
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
    red flags); a problem stops the run with the fields to rewrite. Allow-list entries it used go to stderr.
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
        for phrase, reason in prose.check(data):  # logged so the agent can see what was let through
            print(f'Fair-housing allow list: "{phrase}" ({reason})', file=sys.stderr)
        ctx = {"agent": profiles.load_agent(args.agent), "market": args.market, "sample": args.sample, "formats": todo,
               **{k: v for k, v in vars(args).items() if k not in base}}
        check_agent(ctx["agent"])
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
