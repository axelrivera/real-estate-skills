#!/usr/bin/env python3
"""Write samples/README.md from dev/samples/readme-template.md (make samples).

The text lives in the template. Each {{pattern}} in it is a glob under samples/ that must match
exactly one file; it becomes a link to that file with its page, slide or event count, so the page
stays right when a sample's file name or length changes.
"""
import glob
import os
import re
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SAMPLES = os.path.join(ROOT, "samples")
TEMPLATE = os.path.join(ROOT, "dev", "samples", "readme-template.md")


def count(path):
    if path.endswith(".pdf"):
        with open(path, "rb") as f:
            n, unit = len(re.findall(rb"/Type\s*/Page(?![s\w])", f.read())), "page"
    elif path.endswith(".pptx"):
        with zipfile.ZipFile(path) as z:
            n, unit = sum(bool(re.fullmatch(r"ppt/slides/slide\d+\.xml", name)) for name in z.namelist()), "slide"
    elif path.endswith(".ics"):
        with open(path, encoding="utf-8") as f:
            n, unit = f.read().count("BEGIN:VEVENT"), "event"
    else:
        return ""
    return f" ({n} {unit}{'' if n == 1 else 's'})"


def link(match):
    pattern = match.group(1)
    found = glob.glob(os.path.join(SAMPLES, pattern))
    if len(found) != 1:
        sys.exit(f"samples_readme: {{{{{pattern}}}}} matched {len(found)} files in samples/, expected 1")
    rel = os.path.relpath(found[0], SAMPLES)
    return f"[{os.path.basename(rel)}]({rel}){count(found[0])}"


def main():
    with open(TEMPLATE, encoding="utf-8") as f:
        text = re.sub(r"\A<!--.*?-->\n", "", f.read(), flags=re.S)
    with open(os.path.join(SAMPLES, "README.md"), "w", encoding="utf-8") as f:
        f.write(re.sub(r"\{\{([^}]+)\}\}", link, text))
    print("samples/README.md")


if __name__ == "__main__":
    main()
