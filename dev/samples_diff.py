"""Which regenerated samples really changed.

Every render stamps its build time (the PDF creation date, the calendar's DTSTAMP, the deck's core properties and
embedded chart workbooks), so `make samples` shows every file as modified even when nothing a reader sees moved.
This compares each modified file in samples/ with the committed copy by content: PDF page text, ICS lines without
DTSTAMP, and PPTX slide XML. With --revert, files whose content is unchanged are restored from git, so only real
changes are left to review and commit.

    python dev/samples_diff.py            # list real changes; exit 1 when any
    python dev/samples_diff.py --revert   # also restore the files that only differ in build time
"""
import io
import os
import re
import subprocess
import sys
import zipfile

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _git(*args, binary=False):
    out = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, check=True).stdout
    return out if binary else out.decode()


def content(path, data):
    """What a reader sees in a sample file, without build times."""
    if path.endswith(".pdf"):
        import pymupdf  # dev-only tool (dev/requirements-tools.txt)
        return [page.get_text() for page in pymupdf.open(stream=data, filetype="pdf")]
    if path.endswith(".ics"):
        return [line for line in data.decode().splitlines() if not line.startswith("DTSTAMP:")]
    if path.endswith(".pptx"):
        z = zipfile.ZipFile(io.BytesIO(data))
        return {n: z.read(n) for n in sorted(z.namelist())
                if n.startswith("ppt/slides/") or n.startswith("ppt/charts/") and n.endswith(".xml")}
    return data


def modified():
    return [line[3:] for line in _git("status", "--porcelain", "--", "samples").splitlines()
            if line[:2].strip() == "M" and re.search(r"\.(pdf|ics|pptx)$", line)]


def main(argv=None):
    revert = "--revert" in (argv if argv is not None else sys.argv[1:])
    real, same = [], []
    for path in modified():
        old = _git("show", f"HEAD:{path}", binary=True)
        with open(os.path.join(ROOT, path), "rb") as f:
            new = f.read()
        (same if content(path, old) == content(path, new) else real).append(path)
    if revert and same:
        _git("checkout", "--", *same)
    for path in real:
        print(f"changed: {path}")
    print(f"{len(real)} sample(s) changed; {len(same)} differ only in build time" + (" (restored)" if revert and same else ""))
    return 1 if real else 0


if __name__ == "__main__":
    sys.exit(main())
