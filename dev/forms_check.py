"""Check the FR/BAR form PDFs in sources/ against the committed manifest, so a revised form is never missed.

    python dev/forms_check.py                    # report new, removed and changed forms (make forms-check)
    python dev/forms_check.py --accept CR-7_L    # after updating the references: record that form's new text
    python dev/forms_check.py --accept-all       # record every form (first run, or after a full review)

The manifest (dev/forms/frbar-forms.json) is the list of fully supported forms: one entry per form family with
the revision printed in its footer, a hash of its text and the references and code that depend on it. It holds no
form text (the forms are Florida Realtors' copyright). Text snapshots for diffs live next to the PDFs in
sources/Contracts/_snapshots/, which is git-ignored like the rest of sources/.

It also checks that every "Verified Against" table in shared/references/frbar-*.md and the VERIFIED map in
shared/contract_forms.py cite the manifest's revisions. See docs/development.md#updating-a-contract-form.
"""
import argparse
import difflib
import hashlib
import json
import os
import re
import subprocess
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FORMS = os.path.join(ROOT, "sources", "Contracts", "FARBAR")
SNAPSHOTS = os.path.join(ROOT, "sources", "Contracts", "_snapshots")
MANIFEST = os.path.join(ROOT, "dev", "forms", "frbar-forms.json")
REFERENCES = os.path.join(ROOT, "shared", "references")
sys.path.insert(0, ROOT)


def family(filename):
    """The form's family key from the file name's code in parentheses: "K. As Is Rider (CR-7 K).pdf" -> "CR-7_K",
    "Counter Offer (CO-3).pdf" -> "CO". Revision digits are dropped for everything but the CR-7 riders (whose
    letter is the identity), so ASIS-7 and a later ASIS-8 are the same family."""
    codes = re.findall(r"\(([^()]*)\)", filename)
    code = codes[-1].strip() if codes else os.path.splitext(filename)[0]
    rider = re.match(r"CR-\d+x?\s+([A-Z]{1,2})$", code)
    if rider:
        return f"CR-7_{rider.group(1)}"
    if re.fullmatch(r"\d+x?", code):  # "Residential Contract for Sale And Purchase (7).pdf"
        return "FRBAR-STANDARD"
    if code.upper().startswith("ASIS"):
        return "FRBAR-ASIS"
    return re.sub(r"-\d+x?$", "", code).upper()


def extract(path):
    return subprocess.run(["pdftotext", "-layout", path, "-"], capture_output=True, text=True, check=True).stdout


def normalized(text):
    """Text with whitespace collapsed, so a pdftotext spacing change isn't a new revision."""
    return "\n".join(" ".join(line.split()) for line in text.splitlines() if line.strip())


def revision(text):
    """The revision as printed in the footer: the text before the copyright mark on the first footer line
    ("CR-7 Rev. 10/21", "EDRV-1 4 /09"), or "© 2014" when the footer prints no revision."""
    for line in text.splitlines():
        if "©" not in line:
            continue
        before = " ".join(line.split("©")[0].split())
        m = re.search(r"(\S.*?\d+x?)[_ ]*((?:Rev\.?\s*)?\d{1,2}\s*/\s*\d{2,4})\s*$", before)
        if m:
            return f"{' '.join(m.group(1).replace('_', ' ').split())} {' '.join(m.group(2).split())}".replace("/ ", "/")
        year = re.search(r"©\s*(\d{4})", line)
        if year:
            return f"© {year.group(1)}"
    return "unknown"


def scan():
    """{family: {file, revision, sha256, text}} for every PDF under sources/Contracts/FARBAR/."""
    found = {}
    for dirpath, _, files in os.walk(FORMS):
        for name in sorted(files):
            if not name.lower().endswith(".pdf"):
                continue
            path = os.path.join(dirpath, name)
            text = normalized(extract(path))
            key = family(name)
            if key in found:
                sys.exit(f"Two files for form {key}: {found[key]['file']} and {os.path.relpath(path, FORMS)}. Keep one.")
            found[key] = {"file": os.path.relpath(path, FORMS), "revision": revision(text),
                          "sha256": hashlib.sha256(text.encode()).hexdigest(), "text": text}
    return found


def load_manifest():
    if not os.path.exists(MANIFEST):
        return {"forms": {}}
    with open(MANIFEST, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(manifest):
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    manifest["forms"] = dict(sorted(manifest["forms"].items()))
    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")


def snapshot_path(key):
    return os.path.join(SNAPSHOTS, f"{key}.txt")


def cited_revisions():
    """{family: [(file, revision)]} from the "Verified Against" tables in shared/references/frbar-*.md, whose rows
    are | `FAMILY` | revision | ... |."""
    out = {}
    for name in sorted(os.listdir(REFERENCES)) if os.path.isdir(REFERENCES) else []:
        if not (name.startswith("frbar-") and name.endswith(".md")):
            continue
        with open(os.path.join(REFERENCES, name), encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\|\s*`([A-Z0-9_-]+)`\s*\|\s*([^|]+?)\s*\|", line)
                if m:
                    out.setdefault(m.group(1), []).append((name, m.group(2)))
    return out


def check(found, manifest):
    """Print what changed; return the number of problems."""
    forms = manifest["forms"]
    problems = 0
    for key in sorted(set(found) - set(forms)):
        problems += 1
        print(f"NEW       {key}: {found[key]['file']} ({found[key]['revision']}). Write its references, then --accept {key}.")
    for key in sorted(set(forms) - set(found)):
        problems += 1
        print(f"MISSING   {key}: {forms[key]['file']} is in the manifest but not in sources/.")
    for key in sorted(set(found) & set(forms)):
        now, then = found[key], forms[key]
        if now["sha256"] == then["sha256"]:
            continue
        problems += 1
        print(f"CHANGED   {key}: {then['revision']} -> {now['revision']} ({now['file']})")
        for dep in then.get("used_by", []):
            print(f"            update: {dep}")
        if os.path.exists(snapshot_path(key)):
            with open(snapshot_path(key), encoding="utf-8") as f:
                old = f.read().splitlines()
            diff = list(difflib.unified_diff(old, now["text"].splitlines(), "before", "after", n=1, lineterm=""))
            print("\n".join("            " + line for line in diff[:200]))
            if len(diff) > 200:
                print(f"            ... {len(diff) - 200} more diff lines")
        else:
            print("            (no local snapshot to diff against)")
    for key, cites in sorted(cited_revisions().items()):
        want = forms.get(key, {}).get("revision")
        for ref, rev in cites:
            if want is None:
                problems += 1
                print(f"STALE     {ref} cites {key}, which isn't in the manifest.")
            elif rev != want:
                problems += 1
                print(f"STALE     {ref} cites {key} as {rev!r}; the manifest has {want!r}.")
    try:
        from shared import contract_forms
        for key, rev in getattr(contract_forms, "VERIFIED", {}).items():
            if forms.get(key, {}).get("revision") != rev:
                problems += 1
                print(f"STALE     contract_forms.VERIFIED[{key!r}] is {rev!r}; the manifest has "
                      f"{forms.get(key, {}).get('revision')!r}.")
    except ImportError:
        pass
    return problems


def accept(found, manifest, keys):
    for key in keys:
        if key not in found:
            sys.exit(f"No form {key} in sources/. Known: {', '.join(sorted(found))}")
        entry = manifest["forms"].setdefault(key, {"used_by": []})
        entry.update({k: found[key][k] for k in ("file", "revision", "sha256")})
        os.makedirs(SNAPSHOTS, exist_ok=True)
        with open(snapshot_path(key), "w", encoding="utf-8") as f:
            f.write(found[key]["text"] + "\n")
        print(f"accepted  {key}: {found[key]['revision']}")
    save_manifest(manifest)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--accept", nargs="+", metavar="FAMILY", help="record these forms' current text and revision")
    ap.add_argument("--accept-all", action="store_true", help="record every form")
    args = ap.parse_args()
    if not os.path.isdir(FORMS):
        sys.exit(f"No forms folder at {os.path.relpath(FORMS, ROOT)}: the PDFs are local only (sources/ is git-ignored).")
    found, manifest = scan(), load_manifest()
    if args.accept_all or args.accept:
        accept(found, manifest, sorted(found) if args.accept_all else args.accept)
        return
    problems = check(found, manifest)
    print(f"{len(found)} forms checked, {problems} to review." if problems else f"{len(found)} forms match the manifest.")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
