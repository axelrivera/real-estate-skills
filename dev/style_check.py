"""Check rendered outputs against the writing rules: no em dashes, labels in title case.

Renders every fixture in dev/fixtures/ (like `make outputs`), capturing each report's HTML before it
is printed, then checks:
  - em dashes used in prose (touching a word) in report HTML, written text files (md, json, txt) or
    shipped files: always an error (exit 1). A lone em dash for an empty value is fine;
  - labels (headings, table headers, tiles, legends) that aren't Title Case: listed for review, since
    sentence-style finding headings and fragments are accepted exceptions.

Usage: .venv/bin/python dev/style_check.py [skill ...]
"""
import glob
import json
import os
import re
import subprocess
import sys
import tempfile

from bs4 import BeautifulSoup

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from shared.prose import PROSE_DASH  # noqa: E402

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# Lowercase inside a title unless first or last (Chicago-style short words).
MINOR = {"a", "an", "the", "and", "but", "or", "nor", "for", "so", "yet", "as", "at", "by", "in", "of",
         "off", "on", "per", "to", "up", "via", "vs", "vs.", "from", "into", "with", "than", "if"}
# Tags and classes whose text is a label. Sentences inside them are skipped by is_sentence().
LABEL_TAGS = {"h1", "h2", "h3", "h4", "th", "caption", "dt", "legend"}
LABEL_CLASSES = {"k", "lbl", "label", "tile-label", "side", "pill", "tag", "badge", "cap", "hd", "title", "key"}
# Captions set inside a heading (<h2>Title <span class="h2s">caption</span></h2>) are sentence case.
CAPTION_CLASSES = {"h2s", "h3s"}

BOOTSTRAP = r"""
import os, runpy, sys
scripts, capture = sys.argv[1], sys.argv[2]
sys.argv = [os.path.join(scripts, "render.py")] + sys.argv[3:]
sys.path.insert(0, scripts)
from _shared import render
real, n = render.html_to_pdf, [0]
def html_to_pdf(doc, path, *a, **k):
    n[0] += 1
    with open(os.path.join(capture, f"{n[0]}-{os.path.basename(path)}.html"), "w", encoding="utf-8") as f:
        f.write(doc)
    return real(doc, path, *a, **k)
render.html_to_pdf = html_to_pdf
runpy.run_path(sys.argv[0], run_name="__main__")
"""


def is_sentence(text):
    words = text.split()
    return text.rstrip().endswith((".", "?", "!", ":")) and len(words) > 3 or len(words) > 9


def title_case_errors(text):
    """Words that break title case in `text` (a label), or [] when it's fine."""
    text = re.sub(r"\{[^}]*\}", "X", text)  # placeholders count as capitalized words
    words = re.findall(r"[A-Za-z][A-Za-z'.]*|[$\d][\d,.%$]*", text)  # numbers count, so "at $474,900" isn't last
    bad = []
    for i, w in enumerate(words):
        if w.lower() in MINOR and 0 < i < len(words) - 1:
            continue
        if w[0].isalpha() and w[0].islower():
            bad.append(w)
    return bad


def label_texts(html):
    soup = BeautifulSoup(html, "html.parser")
    for el in soup.find_all(True):
        classes = set(el.get("class") or [])
        if el.name in LABEL_TAGS or classes & LABEL_CLASSES:
            if el.find(LABEL_TAGS):
                continue
            for cap in el.find_all(class_=lambda c: c in CAPTION_CLASSES):
                cap.extract()
            yield el.name + ("." + ".".join(sorted(classes)) if classes else ""), el.get_text(" ", strip=True)


def render_fixtures(skills, tmp):
    fixtures = [f for f in sorted(glob.glob(os.path.join(ROOT, "dev", "fixtures", "*", "*.json")))
                if os.path.basename(os.path.dirname(f)) != "_profiles"
                and (not skills or os.path.basename(os.path.dirname(f)) in skills)]
    agent = os.path.join(ROOT, "dev", "fixtures", "_profiles", "agent-profile.md")
    out = []
    for f in fixtures:
        skill, name = os.path.basename(os.path.dirname(f)), os.path.basename(f)[:-5]
        scripts = glob.glob(os.path.join(ROOT, "plugins", "*", "skills", skill, "scripts"))[0]
        cap, dest = os.path.join(tmp, skill, name, "html"), os.path.join(tmp, skill, name, "out")
        os.makedirs(cap)
        os.makedirs(dest)
        args = [sys.executable, "-c", BOOTSTRAP, scripts, cap, f, "--format", "all", "--out", dest]
        if os.path.exists(agent):
            args += ["--agent", agent]
        env = dict(os.environ, OUTPUT_DIR=dest, NODE_PATH=os.path.join(ROOT, "dev", "node_modules"))
        r = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"{skill}/{name} failed to render:\n{r.stderr}")
        out.append((f"{skill}/{name}", cap, dest))
    return out


def main(argv):
    findings = []
    shipped = [p for p in glob.glob(os.path.join(ROOT, "plugins", "**", "*"), recursive=True)
               if os.path.isfile(p) and "_shared" not in p and "__pycache__" not in p
               and p.endswith((".md", ".json", ".py", ".js", ".css"))]
    for p in shipped:
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if PROSE_DASH.search(line):
                    findings.append(f"em dash  {os.path.relpath(p, ROOT)}:{i}: {line.strip()[:120]}")
    for p in glob.glob(os.path.join(ROOT, "plugins", "*", "skills", "*", "assets", "labels.json")):
        with open(p, encoding="utf-8") as f:
            labels = json.load(f)
        for key, text in labels.items():
            if (key.startswith(("h_", "th_", "lg_", "sum_", "deck_", "net_", "pay_", "cr_")) and not is_sentence(text)
                    and title_case_errors(text)):
                findings.append(f"label    {os.path.relpath(p, ROOT)} {key}: {text!r}")
    with tempfile.TemporaryDirectory() as tmp:
        for name, cap, dest in render_fixtures(argv, tmp):
            seen = set()
            for h in sorted(glob.glob(os.path.join(cap, "*.html"))):
                with open(h, encoding="utf-8") as f:
                    doc = f.read()
                for node in BeautifulSoup(doc, "html.parser").find_all(string=PROSE_DASH):
                    findings.append(f"em dash  {name} {os.path.basename(h)}: {node.strip()[:100]}")
                for where, text in label_texts(doc):
                    if text and text not in seen and not is_sentence(text) and title_case_errors(text):
                        seen.add(text)
                        findings.append(f"label    {name} <{where}> {text!r}")
            for p in glob.glob(os.path.join(dest, "**", "*"), recursive=True):
                if p.endswith((".md", ".json", ".txt")):
                    with open(p, encoding="utf-8") as f:
                        if PROSE_DASH.search(f.read()):
                            findings.append(f"em dash  {name} {os.path.relpath(p, dest)}")
    for line in findings:
        print(line)
    dashes = sum(line.startswith("em dash") for line in findings)
    print(f"{dashes} em dash(es) (errors), {len(findings) - dashes} label(s) to review")
    return 1 if dashes else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
