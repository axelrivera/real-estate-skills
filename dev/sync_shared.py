"""Copy shared/ into every skill that has a scripts/ folder, as scripts/_shared/, and shared reference files
into the skills that use them.

    python3 dev/sync_shared.py           # sync (make sync)
    python3 dev/sync_shared.py --check   # exit 1 if any copy differs (make check-sync, pre-commit)

The copies are committed so each skill works on its own in claude.ai and Cowork.
Never edit scripts/_shared/ by hand; edit shared/ and sync.

shared/references/<name>.md is not code: it is copied to references/<name>.md of every skill whose SKILL.md
mentions `references/<name>.md` (so a skill opts in by pointing to the file). Edit it in shared/references/ only.
"""
import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
REFERENCES = "references"  # shared/references/ goes to each skill's references/, not scripts/_shared/


def source_files(src):
    out = set()
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not (dirpath == src and d == REFERENCES)]
        for f in filenames:
            if not (f.endswith(".pyc") or f == ".DS_Store"):
                out.add(os.path.relpath(os.path.join(dirpath, f), src))
    return out


def skills(root, need_scripts=True):
    base = os.path.join(root, "plugins")
    return sorted(
        os.path.join(base, plugin, "skills", name)
        for plugin in os.listdir(base) if os.path.isdir(os.path.join(base, plugin, "skills"))
        for name in os.listdir(os.path.join(base, plugin, "skills"))
        if os.path.isdir(os.path.join(base, plugin, "skills", name, "scripts" if need_scripts else ""))
    ) if os.path.isdir(base) else []


def reference_copies(root):
    """[(source, dest)] for each shared reference a skill's SKILL.md points to."""
    src_dir = os.path.join(root, "shared", REFERENCES)
    names = sorted(f for f in os.listdir(src_dir) if f.endswith(".md")) if os.path.isdir(src_dir) else []
    out = []
    for skill in skills(root, need_scripts=False):
        try:
            with open(os.path.join(skill, "SKILL.md"), encoding="utf-8") as f:
                text = f.read()
        except OSError:
            continue
        out += [(os.path.join(src_dir, n), os.path.join(skill, REFERENCES, n)) for n in names if f"{REFERENCES}/{n}" in text]
    return out


def drift(src, dest):
    """Problems with one copy, as readable strings. Empty when in sync."""
    if not os.path.isdir(dest):
        return ["missing"]
    want, have = source_files(src), source_files(dest)
    problems = [f"missing {f}" for f in sorted(want - have)]
    problems += [f"extra {f}" for f in sorted(have - want)]
    problems += [f"edited {f}" for f in sorted(want & have)
                 if not filecmp.cmp(os.path.join(src, f), os.path.join(dest, f), shallow=False)]
    return problems


def sync(root, check=False):
    src = os.path.join(root, "shared")
    failed = False
    for skill in skills(root):
        dest = os.path.join(skill, "scripts", "_shared")
        rel = os.path.relpath(dest, root)
        problems = drift(src, dest)
        if not problems:
            continue
        if check:
            failed = True
            print(f"{rel}: " + "; ".join(problems))
        else:
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(src, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store", REFERENCES))
            print(f"synced {rel}")
    for ref, dest in reference_copies(root):
        rel = os.path.relpath(dest, root)
        if os.path.exists(dest) and filecmp.cmp(ref, dest, shallow=False):
            continue
        if check:
            failed = True
            print(f"{rel}: {'edited' if os.path.exists(dest) else 'missing'}")
        else:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copyfile(ref, dest)
            print(f"synced {rel}")
    if check and failed:
        print("shared/ copies are out of date. Run `make sync` (and edit shared/, never the copies).")
    return not failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report drift without changing anything")
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    return 0 if sync(args.root, args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
