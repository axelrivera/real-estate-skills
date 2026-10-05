"""Output helpers shared by every skill's scripts/render.py.

    from _shared import render
    def build(data, fmt, out_dir, ctx): ...     # returns the paths it wrote
    if __name__ == "__main__":
        render.main(build, formats=("pdf",))

ctx carries the agent's details from the profile (always a dict, empty fields when there's none), the
MLS name, and whether this is sample data.

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
    """'1438 Buttonbush Dr', 'Buyer CMA' -> '1438-Buttonbush-Dr-Buyer-CMA.pdf'. ASCII, no spaces."""
    def slug(text):
        text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode()
        return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")

    words = [w for w in (slug(p) for p in parts if p) if w]
    # Long names would pass the filesystem's 255-byte limit: shorten the leading parts, keep the last (the file type).
    while len("-".join(words)) > MAX_NAME and len(words) > 1:
        over = len("-".join(words)) - MAX_NAME
        # The address (first) goes last: middle parts such as a buyer's name are cut first.
        i = max(range(len(words) - 1), key=lambda k: (len(words[k]) > 24 and (k > 0 or len(words) == 2), len(words[k])))
        cut = words[i][:max(len(words[i]) - over, 24)].rstrip("-")
        if cut == words[i]:
            break
        words[i] = cut
    return f"{'-'.join(words) or 'output'}.{ext.lstrip('.')}"


MAX_NAME = 120


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
            "The profile has a name but no brokerage. Client files must show the brokerage's licensed name with "
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
    """Chromium footer template: `left` text and 'Page X of Y'. A long left text wraps; the page count never does."""
    pages = ('Page <span class="pageNumber"></span> of <span class="totalPages"></span>'
             if right_pages else "")
    from .design import NEUTRALS  # the footer can't read the page's CSS variables: the muted gray, true gray
    return (f'<div style="font-size:7pt;color:{NEUTRALS["muted"]};width:100%;padding:0 0.3in;display:flex;'
            'justify-content:space-between;font-family:Helvetica,Arial,sans-serif">'
            f'<span style="min-width:0">{html.escape(left)}</span>'
            f'<span style="white-space:nowrap;padding-left:12px">{pages}</span></div>')


# OFR-329: a table box (.tbl) taller than this (about a seventh of a printed Letter page, six or seven rows) may run
# across pages: report.css lets a .tbl.brk break between rows and repeats its header row. Shorter ones stay whole.
LONG_TABLE_PX = 150
MARK_LONG_TABLES = ("px => { for (const t of document.querySelectorAll('.tbl')) "
                    "if (t.getBoundingClientRect().height > px) t.classList.add('brk'); }")


# A page wider than the printable width (a long name in a piece kept on one line, white-space: nowrap) prints shrunk or
# cut off: release those pieces, the widest first, until the page fits. It runs before and after before_print, so a
# report that fits at its normal widths is untouched. Returns how many it released.
RELEASE_NOWRAP = r"""() => {
  const doc = document.documentElement, over = () => doc.scrollWidth > window.innerWidth + 1;
  if (!over()) return 0;
  const kept = [...document.body.querySelectorAll('*')].filter(e => !e.closest('svg') &&
    getComputedStyle(e).whiteSpace === 'nowrap' && (e.innerText || '').trim().includes(' '))
    .sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width);
  let n = 0;
  for (const e of kept) {
    if (!over()) break;
    e.style.whiteSpace = 'normal';
    n++;
  }
  return n;
}"""


# Content the print would cut off, measured after before_print at the layout it prints: a box that hides its overflow
# (overflow hidden or clip) with content wider or taller than the box, text cut to an ellipsis, and a page whose
# content runs wider than the printable width. [(where, text)]; `where` is "tag.class", or "page" for the page width.
FIND_CLIPPED = r"""() => {
  const out = [], seen = new Set();
  const where = e => e.tagName.toLowerCase() + [...e.classList].map(c => '.' + c).join('');
  const text = e => (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60);
  for (const e of document.body.querySelectorAll('*')) {
    if (e.closest('svg')) continue;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') continue;
    const hides = v => v === 'hidden' || v === 'clip';
    const wide = hides(s.overflowX) && e.scrollWidth > e.clientWidth + 1;
    const tall = hides(s.overflowY) && e.scrollHeight > e.clientHeight + 1;
    const ellipsis = s.textOverflow === 'ellipsis' && e.scrollWidth > e.clientWidth + 1;
    if ((wide || tall || ellipsis) && text(e) && ![...seen].some(p => p.contains(e))) {
      seen.add(e);
      out.push([where(e), text(e)]);
    }
  }
  const doc = document.documentElement;
  if (doc.scrollWidth > window.innerWidth + 1) {
    const over = [...document.body.querySelectorAll('*')].filter(e => !e.closest('svg') && e.children.length === 0 &&
      e.getBoundingClientRect().right > window.innerWidth + 1 && text(e));
    out.push(['page', over.length ? text(over[0]) : `content ${doc.scrollWidth - window.innerWidth}px wider than the page`]);
  }
  return out;
}"""


def clip_warnings(name, clipped):
    """One stderr line per clipped box, in the same style as the page-1 overflow warnings."""
    out = []
    for where, text in clipped:
        if where == "page":
            out.append(f"Check: {name}: clipped: text runs past the page's right edge (\"{text}\"), so the print "
                       "shrinks or cuts it. Shorten it.")
        else:
            out.append(f"Check: {name}: clipped: {where} \"{text}\". Shorten the text that fills it.")
    return out


def html_to_pdf(doc, path, fmt="Letter", margins=None, footer_html=None, before_print=None, landscape=False):
    """Print HTML to PDF with Chromium (print media, backgrounds on).

    Long tables are marked .brk first (LONG_TABLE_PX), so they can run across pages.
    `before_print(page)` can measure or adjust layout first; its return value is returned.
    `landscape` turns the page (11in wide); layout is measured at the matching width.
    A page wider than the printable width first lets its one-line pieces wrap (RELEASE_NOWRAP). After before_print,
    content the print would still cut off (FIND_CLIPPED) is reported on stderr ("Check: ... clipped").
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
            pg.evaluate(MARK_LONG_TABLES, LONG_TABLE_PX)
            pg.evaluate(RELEASE_NOWRAP)
            info = before_print(pg) if before_print else None
            pg.evaluate(RELEASE_NOWRAP)
            for line in clip_warnings(os.path.basename(path), pg.evaluate(FIND_CLIPPED)):
                print(line, file=sys.stderr)
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


def main(build, formats, argv=None, extra_args=None, errors=(), default="all", *, placeholders=False, labels=(),
         agent_only=(), linked=None):
    """Command line for scripts/render.py: DATA.json --format <fmt>|all --out DIR [--profile] [--mls] [--sample].

    `build(data, fmt, out_dir, ctx)` renders one format and returns the list of paths written.
    `extra_args(parser)` adds the skill's own options (--cma, --mode...); their values arrive in `ctx` by name.
    `ctx["formats"]` lists every format this run renders, so work shared across formats can be done once;
    `ctx["data_file"]` is the data file's path (relative paths inside it can resolve beside it).
    `errors` are exception types that mean bad input: they end the run with their message, not a traceback.
    `default` is the --format used when none is given ("all", or one format a skill builds unless asked for more).
    Before anything is built, the data's text is checked (prose.issues: no em dashes, no fair-housing red flags, no
    tool words, data keys, ISO dates or jargon in client text), and so are the other files the run reads (`linked`)
    and the profile's voice and disclaimers; every problem stops the run at once, listed as `field: problem → fix`.
    Allow-list entries it used go to stderr. Missing data never stops it here: only wrong wording does.
    `placeholders`: the skill fills {name} placeholders in its wording itself (and names any it can't).
    `labels`: label fields the model types (prose.title_labels patterns), put in Title Case before the build.
    `agent_only`: top-level keys whose text only the agent sees (jargon allowed there).
    `linked(data, args)`: [(name, object)] for the other JSON the render reads (a deck file, a CMA handoff), each
    checked like the data file.
    With several formats, one that fails doesn't stop the others: the files that were made are printed,
    then the run exits with a message naming what wasn't built.
    Prints each path, one per line, so Claude can present them.
    """
    from . import profiles, prose

    ap = argparse.ArgumentParser(description="Render this skill's files from its data file.")
    ap.add_argument("data", help="the skill's data JSON")
    ap.add_argument("--format", default=default, choices=[*formats, "all"])
    ap.add_argument("--out", help="output folder (default: sandbox outputs, or OUTPUT_DIR locally)")
    ap.add_argument("--profile", help="the agent's profile.md (name, brokerage, contact, brand colors, disclaimers)")
    ap.add_argument("--mls", help="MLS name (Stellar is built in; assumed from the county when it's the only one)")
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
        agent = profiles.load_agent(args.profile)
        used, allow = [], prose.allow_list(data)
        wording = {"placeholders": placeholders, "agent_only": agent_only}
        found = prose.issues(data, used, **wording)
        for name, obj in (linked(data, vars(args)) if linked else ()):
            found += prose.issues(obj, used, root=name, allow=allow + prose.allow_list(obj), **wording)
        found += prose.issues({"voice": agent["voice"], "disclaimers": agent["disclaimers"]}, used, root="profile",
                              rules=prose.PROFILE_RULES, allow=allow)
        prose.report(found)
        for phrase, reason in used:  # logged so the agent can see what was let through
            print(f'Fair-housing allow list: "{phrase}" ({reason})', file=sys.stderr)
        data = prose.title_labels(data, labels)
        ctx = {"agent": agent, "mls": args.mls, "sample": args.sample,
               "formats": todo, "data_file": args.data,
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
