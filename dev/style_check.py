"""Check rendered outputs against the writing rules: no em dashes, labels in title case.

Renders every fixture in dev/fixtures/ (like `make outputs`), capturing each report's HTML before it
is printed, then checks:
  - em dashes used in prose (touching a word) in report HTML, written text files (md, json, txt) or
    shipped files: always an error (exit 1). A lone em dash for an empty value is fine;
  - `--` or a spaced en dash between words used as a dash, in shipped markdown (number ranges are fine);
  - labels (headings, table headers, tiles, legends) that aren't Title Case: listed for review, since
    sentence-style finding headings and fragments are accepted exceptions;
  - markdown headings in SKILL.md, references and templates that aren't Title Case (file names, field keys and
    `code` keep their own spelling);
  - client wording (shared/prose.py wording_issues: tool words, unfilled {placeholders}, data keys, ISO dates in a
    sentence, jargon) in report HTML, so text the scripts write gets the check the data file gets at run time: an error;
  - the legacy form name (FR/BAR, frbar, FRBAR) in any tracked text file or report HTML: always an error. The forms are
    FAR/BAR (farbar, FARBAR); a line that reads the old name as legacy input says "legacy" and is allowed.

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
from shared import prose  # noqa: E402
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
    words = re.findall(r"[^\W\d_][\w'.]*|[$\d][\d,.%$]*", text)  # any letters, so "Díaz" is one word  # numbers count, so "at $474,900" isn't last
    bad = []
    for i, w in enumerate(words):
        if w.lower() in MINOR and 0 < i < len(words) - 1:
            continue
        if w[0].isalpha() and w[0].islower() and not any(c.isupper() for c in w[1:]):  # "eXp": a brand, kept as written
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
    profile = os.path.join(ROOT, "dev", "fixtures", "_profiles", "profile.md")
    out = []
    for f in fixtures:
        skill, name = os.path.basename(os.path.dirname(f)), os.path.basename(f)[:-5]
        scripts = os.path.join(ROOT, "skills", skill, "scripts")
        cap, dest = os.path.join(tmp, skill, name, "html"), os.path.join(tmp, skill, name, "out")
        os.makedirs(cap)
        os.makedirs(dest)
        args = [sys.executable, "-c", BOOTSTRAP, scripts, cap, f, "--format", "all", "--out", dest]
        if os.path.exists(profile):
            args += ["--profile", profile]
        env = dict(os.environ, OUTPUT_DIR=dest, NODE_PATH=os.path.join(ROOT, "dev", "node_modules"))
        r = subprocess.run(args, cwd=ROOT, env=env, capture_output=True, text=True)
        if r.returncode:
            sys.exit(f"{skill}/{name} failed to render:\n{r.stderr}")
        out.append((f"{skill}/{name}", cap, dest))
    return out


WORD_DASH = re.compile(r"[A-Za-z,)] (?:--|\u2013) [A-Za-z(]")  # DOC-12: "--" or a spaced en dash between words
HEADING = re.compile(r"^(#{1,4})\s+(.*)$")
OLD_NAME = re.compile(r"\bfr ?/ ?bar\b|\bfrbar", re.I)  # the forms are FAR/BAR; "legacy" lines read the old name


def old_name_errors():
    """Tracked text files that still use the old form name outside a line marked legacy."""
    out = []
    files = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, text=True, check=True).stdout
    for rel in filter(None, files.split("\0")):
        try:
            with open(os.path.join(ROOT, rel), encoding="utf-8") as f:
                lines = f.readlines()
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue  # binaries (regenerated) and files deleted in the working tree
        out += [f"old name {rel}:{i}: {line.strip()[:120]}" for i, line in enumerate(lines, 1)
                if OLD_NAME.search(line) and "legacy" not in line.lower()]
    return out


def heading_errors(text):
    """Title Case errors in a markdown heading, ignoring `code`, file names and field-key headings (`## listing`)."""
    if re.match(r"^[a-z_]+(\[\])?(,|\s|$)", text) or "{{" in text:
        return []
    return title_case_errors(re.sub(r"`[^`]*`|\b[\w-]+\.(?:json|md|py|csv|js|ics)\b", "X", text))


def html_wording(soup):
    """Client-wording problems (shared/prose.py: tool words, unfilled {placeholders}, data keys, ISO dates, jargon) in a
    rendered report's text, script-written text included: the data file is checked at run time, the scripts' own
    wording only here. Each problem once per file, with the text around it. A draft for the agent (the offer package
    worksheet, marked by its draft bar) may use jargon agents use (LTV), as `agent_only` data text may."""
    out, seen = [], set()
    jargon = soup.find(class_="draftbar") is None
    for el in soup.find_all(["style", "script"]):
        el.extract()
    for node in soup.find_all(string=True):
        text = " ".join(node.split())
        for problem in prose.wording_issues(text, jargon=jargon) if text else ():
            if problem not in seen:
                seen.add(problem)
                out.append(f"{problem} in {text[:90]!r}")
    return out


def ics_wording(text):
    """Client-wording problems in a calendar file's event titles, descriptions and locations (unfolded, unescaped)."""
    text = re.sub(r"\r?\n[ \t]", "", text)  # RFC 5545 line folding
    out, seen = [], set()
    for m in re.finditer(r"^(?:SUMMARY|DESCRIPTION|LOCATION)[^:]*:(.*)$", text, re.M):
        value = re.sub(r"\\([,;\\])", r"\1", m.group(1)).replace("\\n", " ").replace("\\N", " ")
        for problem in prose.wording_issues(value):
            if problem not in seen:
                seen.add(problem)
                out.append(f"{problem} in {value[:90]!r}")
    return out


def main(argv):
    findings = old_name_errors()
    shipped = [p for p in glob.glob(os.path.join(ROOT, "skills", "**", "*"), recursive=True)
               if os.path.isfile(p) and "_shared" not in p and "__pycache__" not in p
               and p.endswith((".md", ".json", ".py", ".js", ".css"))]
    shipped += glob.glob(os.path.join(ROOT, ".claude-plugin", "*.json"))
    shipped.append(os.path.join(ROOT, "dev", "package", "README.md"))  # ships in the release zip
    shipped += glob.glob(os.path.join(ROOT, "shared", "**", "*.md"), recursive=True)  # DOC-12: markets and references ship
    for p in shipped:
        in_code = False
        with open(p, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                if PROSE_DASH.search(line):
                    findings.append(f"em dash  {os.path.relpath(p, ROOT)}:{i}: {line.strip()[:120]}")
                if not p.endswith(".md"):
                    continue
                if line.startswith("```"):
                    in_code = not in_code
                if in_code:
                    continue
                if WORD_DASH.search(line):
                    findings.append(f"em dash  {os.path.relpath(p, ROOT)}:{i}: '--' or spaced en dash: {line.strip()[:100]}")
                m = HEADING.match(line)
                if m and (p.endswith("SKILL.md") or "/references/" in p or "/assets/" in p) and heading_errors(m.group(2).strip()):
                    findings.append(f"label    {os.path.relpath(p, ROOT)}:{i}: heading {m.group(2).strip()!r}")
    for p in glob.glob(os.path.join(ROOT, "skills", "*", "assets", "labels.json")):
        with open(p, encoding="utf-8") as f:
            labels = json.load(f)
        prose = set(labels.pop("_prose", []))  # CMA-26: sentences and table values that happen to share a label prefix
        for key, text in labels.items():
            if key not in prose and (key.startswith(("h_", "th_", "lg_", "sum_", "deck_", "net_", "pay_", "cr_")) and not is_sentence(text)
                    and title_case_errors(text)):
                findings.append(f"label    {os.path.relpath(p, ROOT)} {key}: {text!r}")
    with tempfile.TemporaryDirectory() as tmp:
        for name, cap, dest in render_fixtures(argv, tmp):
            seen = set()
            for h in sorted(glob.glob(os.path.join(cap, "*.html"))):
                with open(h, encoding="utf-8") as f:
                    doc = f.read()
                if OLD_NAME.search(doc):
                    findings.append(f"old name {name} {os.path.basename(h)}")
                soup = BeautifulSoup(doc, "html.parser")
                for node in soup.find_all(string=PROSE_DASH):
                    findings.append(f"em dash  {name} {os.path.basename(h)}: {node.strip()[:100]}")
                findings += [f"wording  {name} {os.path.basename(h)}: {w}" for w in html_wording(soup)]
                for where, text in label_texts(doc):
                    if text and text not in seen and not is_sentence(text) and title_case_errors(text):
                        seen.add(text)
                        findings.append(f"label    {name} <{where}> {text!r}")
            for p in glob.glob(os.path.join(dest, "**", "*"), recursive=True):
                if p.endswith((".md", ".json", ".txt")):
                    with open(p, encoding="utf-8") as f:
                        if PROSE_DASH.search(f.read()):
                            findings.append(f"em dash  {name} {os.path.relpath(p, dest)}")
                elif p.endswith(".ics"):
                    with open(p, encoding="utf-8") as f:
                        findings += [f"wording  {name} {os.path.relpath(p, dest)}: {w}" for w in ics_wording(f.read())]
    for line in findings:
        print(line)
    dashes = sum(line.startswith("em dash") for line in findings)
    names = sum(line.startswith("old name") for line in findings)
    wording = sum(line.startswith("wording") for line in findings)
    print(f"{dashes} em dash(es), {names} old form name(s) and {wording} client-wording problem(s) (errors), "
          f"{len(findings) - dashes - names - wording} label(s) to review")
    return 1 if dashes or names or wording else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
