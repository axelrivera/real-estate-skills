"""Rendered-layout check: every fixture of every PDF skill, printed and read back.

Renders each dev/fixtures/<skill>/*.json the way `make outputs` does (stress-*.json fixtures with the long-name
profile, dev/fixtures/_profiles/stress.md), then fails on:
  - a page-1 overflow warning ("... overflows by ...px") or a clip warning ("Check: ... clipped", from
    shared/render.py html_to_pdf) on stderr;
  - a near-empty page, read from the PDF with cma.page_fill: a page between the first and the last under half full
    (MIDDLE), or a last page after page 1 under 15% full (TAIL);
  - a table split against the rule (fewer than 3 of its rows on a page, a total apart from the 2 rows above it, a
    table under 8 rows split at all), read back from the printed PDF by the layout probe (LAYOUT_PROBE=1, on here).
ALLOW lists the few pages a fixture leaves near-empty on purpose, each with its reason.

    .venv/bin/python dev/layout_check.py [skill ...]     # renders into out/layout/, exits 1 on any problem
"""
import concurrent.futures
import glob
import os
import shutil
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
from shared import cma  # noqa: E402

PROFILES = os.path.join(ROOT, "dev", "fixtures", "_profiles")
MIDDLE, TAIL = cma.HALF_EMPTY, cma.LONE_TAIL
CMA_MARGINS, DEFAULT_MARGINS = (0.45, 0.55), (0.3, 0.4)  # top and bottom, inches: cma.PAGE_MARGINS, render.html_to_pdf
# skill -> (--format, page margins). The seller CMA's deck is slides, not a report page: only its report is checked.
SKILLS = {
    "buyer-cma": ("pdf", CMA_MARGINS),
    "seller-cma": ("pdf", CMA_MARGINS),
    "buyer-offer-strategy": ("all", DEFAULT_MARGINS),
    "seller-offer-review": ("pdf", DEFAULT_MARGINS),
    "seller-net-sheet": ("pdf", DEFAULT_MARGINS),
    "contract-timeline": ("pdf", DEFAULT_MARGINS),
}
# (skill/fixture, PDF file name, page) -> why that page may be near-empty. Only for fixtures that are extreme on purpose.
ALLOW = {}
WARNINGS = ("overflows by", "clipped", "doesn't fit on one page", "split table")


def fixtures(skills=None):
    for skill in skills or SKILLS:
        for f in sorted(glob.glob(os.path.join(ROOT, "dev", "fixtures", skill, "*.json"))):
            yield skill, f


def profile_for(fixture):
    stress = os.path.join(PROFILES, "stress.md")
    if os.path.basename(fixture).startswith("stress-") and os.path.exists(stress):
        return stress
    return os.path.join(PROFILES, "profile.md")


def page_problems(pages, name, allow=()):
    """Near-empty pages in [(fill, first line)], as text; pages listed in `allow` are let through."""
    out = []
    for i, (fill, first) in enumerate(pages):
        n = i + 1
        if i == 0 or n in allow:
            continue
        if i < len(pages) - 1 and fill < MIDDLE:
            out.append(f"{name}: page {n} is only {fill:.0%} full (the next page starts \"{pages[i + 1][1]}\")")
        elif i == len(pages) - 1 and fill < TAIL:
            out.append(f"{name}: the last page (page {n}) is only {fill:.0%} full (\"{first}\")")
    return out


def check(skill, fixture, out_root):
    """Render one fixture and return (id, PDFs written, problems)."""
    fmt, (top, bottom) = SKILLS[skill]
    ident = f"{skill}/{os.path.basename(fixture)[:-5]}"
    dest = os.path.join(out_root, ident)
    shutil.rmtree(dest, ignore_errors=True)
    os.makedirs(dest)
    args = [sys.executable, os.path.join(ROOT, "skills", skill, "scripts", "render.py"), fixture, "--format", fmt,
            "--out", dest, "--profile", profile_for(fixture)]
    env = dict(os.environ, OUTPUT_DIR=dest, NODE_PATH=os.path.join(ROOT, "dev", "node_modules"), LAYOUT_PROBE="1")
    r = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
    if r.returncode:
        return ident, [], [f"{ident}: didn't render: {r.stderr.strip()[-400:]}"]
    problems = [f"{ident}: {line.strip()}" for line in r.stderr.splitlines()
                if any(w in line for w in WARNINGS)]
    pdfs = sorted(p for p in r.stdout.splitlines() if p.endswith(".pdf"))
    for pdf in pdfs:
        pages = cma.page_fill(pdf, top, bottom)
        if pages is None:
            problems.append(f"{ident}: pdftotext isn't installed, so the pages can't be read")
            break
        name = os.path.basename(pdf)
        allow = {page for (i, n, page) in ALLOW if i == ident and n == name}
        problems += [f"{ident}: {p}" for p in page_problems(pages, name, allow)]
    return ident, pdfs, problems


def run(skills=None, out_root=None, workers=4):
    """Check every fixture; returns [(id, PDFs, problems)] in fixture order."""
    out_root = out_root or os.path.join(ROOT, "out", "layout")
    todo = list(fixtures(skills))
    with concurrent.futures.ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda sf: check(*sf, out_root), todo))


def main(argv=None):
    skills = (argv if argv is not None else sys.argv[1:]) or None
    unknown = [s for s in skills or [] if s not in SKILLS]
    if unknown:
        sys.exit(f"Not a PDF skill: {', '.join(unknown)} (one of {', '.join(SKILLS)})")
    results = run(skills)
    problems = [p for _, _, ps in results for p in ps]
    for ident, pdfs, ps in results:
        print(f"{'FAIL' if ps else 'ok  '} {ident} ({len(pdfs)} PDF{'s' if len(pdfs) != 1 else ''})")
    for p in problems:
        print("  " + p)
    stale = [k for k in ALLOW if not any(k[0] == ident for ident, _, _ in results)]
    if not skills and stale:
        print("ALLOW entries with no fixture: " + ", ".join(map(str, stale)))
        return 1
    print(f"{len(results)} fixtures, {len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
