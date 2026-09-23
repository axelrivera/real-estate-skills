"""Output helpers shared by every skill's scripts/render.py.

    from _shared import render
    def build(data, fmt, out_dir): ...          # returns the paths it wrote
    if __name__ == "__main__":
        render.main(build, formats=("md", "pdf"))

Implements the render contract (docs/development.md#skill-render-contract) and the output
location rule (docs/architecture.md#output-location).
"""
import argparse
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


def page(body, css="", title="", theme_css=""):
    """A complete HTML document for the PDF renderer. `theme_css` is design.css_vars(theme)."""
    return (f"<!doctype html><html><head><meta charset='utf-8'><title>{title}</title>"
            f"<style>{theme_css}{css}</style></head><body>{body}</body></html>")


def html_to_pdf(html, path, margins="0.3in", fmt="Letter", before_print=None):
    """Print HTML to PDF with Chromium. `before_print(page)` can run layout JS (pagination) first."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch()
        try:
            pg = browser.new_page()
            pg.set_content(html, wait_until="load")
            if before_print:
                before_print(pg)
            pg.pdf(path=path, format=fmt, print_background=True,
                   margin={side: margins for side in ("top", "right", "bottom", "left")})
        finally:
            browser.close()
    return path


def write_text(text, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main(build, formats, argv=None):
    """Command line for scripts/render.py: DATA.json --format <fmt>|all --out DIR.

    `build(data, fmt, out_dir)` renders one format and returns the list of paths written.
    Prints each path, one per line, so Claude can present them.
    """
    ap = argparse.ArgumentParser(description="Render this skill's outputs from its data file.")
    ap.add_argument("data", help="the skill's data JSON")
    ap.add_argument("--format", default="all", choices=[*formats, "all"])
    ap.add_argument("--out", help="output folder (default: sandbox outputs, or OUTPUT_DIR locally)")
    args = ap.parse_args(argv)

    with open(args.data, encoding="utf-8") as f:
        data = json.load(f)
    out_dir = output_dir(args.out)
    written = []
    for fmt in formats if args.format == "all" else [args.format]:
        written += build(data, fmt, out_dir)
    for path in written:
        print(path)
    return written


if __name__ == "__main__":
    sys.exit("Import this module from a skill's scripts/render.py.")
