"""Copy shared/ into every skill that has a scripts/ folder, as scripts/_shared/.

    python3 dev/sync_shared.py           # sync (make sync)
    python3 dev/sync_shared.py --check   # exit 1 if any copy differs (make check-sync, pre-commit)

The copies are committed so each skill works on its own in claude.ai and Cowork.
Never edit scripts/_shared/ by hand; edit shared/ and sync.
"""
import argparse
import filecmp
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def source_files(src):
    out = set()
    for dirpath, dirnames, filenames in os.walk(src):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for f in filenames:
            if not (f.endswith(".pyc") or f == ".DS_Store"):
                out.add(os.path.relpath(os.path.join(dirpath, f), src))
    return out


def skills(root):
    base = os.path.join(root, "plugins")
    return sorted(
        os.path.join(base, plugin, "skills", name)
        for plugin in os.listdir(base) if os.path.isdir(os.path.join(base, plugin, "skills"))
        for name in os.listdir(os.path.join(base, plugin, "skills"))
        if os.path.isdir(os.path.join(base, plugin, "skills", name, "scripts"))
    ) if os.path.isdir(base) else []


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
            shutil.copytree(src, dest, ignore=IGNORE)
            print(f"synced {rel}")
    if check and failed:
        print("shared/ copies are out of date. Run `make sync` (and edit shared/, never scripts/_shared/).")
    return not failed


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="report drift without changing anything")
    ap.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    args = ap.parse_args(argv)
    return 0 if sync(args.root, args.check) else 1


if __name__ == "__main__":
    sys.exit(main())
