"""Set up an eval iteration: one folder per run of each eval with the prompt, its input files and an empty outputs folder.

    .venv/bin/python dev/evals/setup.py 12                                   # every eval of every skill, one run each
    .venv/bin/python dev/evals/setup.py 12 --runs 3                          # three runs of each (to measure the spread)
    .venv/bin/python dev/evals/setup.py 12 seller-offer-review               # one skill
    .venv/bin/python dev/evals/setup.py 12 --runs 3 seller-offer-review:1,4 buyer-offer-strategy:2

Writes out/evals/iteration-N/<skill>/eval-<id>/run-<k>/ (k = 1..runs, always, even for one run) with task.md (the
prompt, always led by a "Today is" line: the eval's `today`, else the runner's default day, so every run counts dates
from the same day; a prompt given as a list becomes "## Message 1", "## Message 2"... in one chat), inputs/ (its
files; a mock package must be built first with `make mock-contracts ARGS="--answer-key"`, a manual-kit file with
`make manual-kit`, and answer keys and expected.md are never copied) and with_skill/outputs/. Existing run folders are
kept (their outputs too), so a later call with a higher --runs only adds runs.

Also writes out/evals/iteration-N/runs.json: one entry per run folder with the skill folder(s) to install (an eval's
`skills`, else its own skill), for starting one runner subagent per run with dev/evals/RUNNER.md. Grade each run with
dev/evals/GRADER.md and compare the runs with dev/evals/spread.py (development.md#evals).
"""
import json
import os
import shutil
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
EVALS = os.path.join(ROOT, "dev", "evals")
DEFAULT_TODAY = "2026-09-26"  # RUNNER.md's default day: the eval files assume late September 2026
HINTS = {"out/mock-contracts/": "build the mock packages first: make mock-contracts ARGS=\"--answer-key\"",
         "out/manual-test/": "build the manual kit first: make manual-kit"}


def selection(args):
    """{skill: set of ids or None for all} from the command line."""
    skills = sorted(d for d in os.listdir(EVALS) if os.path.isfile(os.path.join(EVALS, d, "evals.json")))
    if not args:
        return {s: None for s in skills}
    out = {}
    for a in args:
        name, _, ids = a.partition(":")
        if name not in skills:
            sys.exit(f"Unknown skill {name!r}: one of {', '.join(skills)}")
        out[name] = {int(i) for i in ids.split(",")} if ids else None
    return out


def parse(argv):
    """(iteration, runs, selection args) from the command line."""
    args, runs = [], 1
    it = iter(argv)
    for a in it:
        if a == "--runs" or a.startswith("--runs="):
            v = a.partition("=")[2] or next(it, "")
            if not v.isdigit() or int(v) < 1:
                sys.exit("--runs takes a whole number, 1 or more")
            runs = int(v)
        else:
            args.append(a)
    if not args or not args[0].isdigit():
        sys.exit(__doc__)
    return args[0], runs, args[1:]


def task_text(e):
    """task.md: the "Today is" line, then the prompt (a list of prompts is one chat, message by message)."""
    head = f"(Today is {e.get('today') or DEFAULT_TODAY}.)\n\n"
    prompt = e["prompt"]
    if isinstance(prompt, str):
        return head + prompt + "\n"
    parts = [f"## Message {i}\n\n{p}" for i, p in enumerate(prompt, 1)]
    return head + ("This chat has several messages from the agent. Answer each in order, as separate replies in one "
                   "conversation (RUNNER.md, Several Messages).\n\n") + "\n\n".join(parts) + "\n"


def check_file(skill, e, path):
    src = os.path.join(ROOT, path)
    if "/key/" in path or os.path.basename(path) == "expected.md":
        sys.exit(f"{skill} eval {e['id']}: {path} holds the answers; never give it to a runner")
    if not os.path.exists(src):
        hint = next((h for p, h in HINTS.items() if path.startswith(p)), None)
        if hint and "-Scanned" in path:
            hint = hint.replace('--answer-key"', '--answer-key --scanned"')
        sys.exit(f"{skill} eval {e['id']}: {path} is missing" + (f" ({hint})" if hint else ""))
    return src


def main(argv):
    number, runs, rest = parse(argv)
    base = os.path.join(ROOT, "out", "evals", f"iteration-{number}")
    manifest_path = os.path.join(base, "runs.json")
    manifest = {}
    if os.path.exists(manifest_path):
        with open(manifest_path, encoding="utf-8") as f:
            manifest = {r["folder"]: r for r in json.load(f)["runs"]}
    n = 0
    for skill, ids in selection(rest).items():
        with open(os.path.join(EVALS, skill, "evals.json"), encoding="utf-8") as f:
            evals = json.load(f)["evals"]
        for e in evals:
            if ids is not None and e["id"] not in ids:
                continue
            sources = [check_file(skill, e, p) for p in e.get("files") or []]
            skills = e.get("skills") or [skill]
            for k in range(1, runs + 1):
                folder = os.path.join(base, skill, f"eval-{e['id']}", f"run-{k}")
                os.makedirs(os.path.join(folder, "inputs"), exist_ok=True)
                os.makedirs(os.path.join(folder, "with_skill", "outputs"), exist_ok=True)
                with open(os.path.join(folder, "task.md"), "w", encoding="utf-8") as f:
                    f.write(task_text(e))
                for src in sources:
                    shutil.copy(src, os.path.join(folder, "inputs"))
                rel = os.path.relpath(folder, ROOT)
                manifest[rel] = {"folder": rel, "skill": skill, "eval": e["id"], "run": k,
                                 "skill_folders": [f"skills/{s}" for s in skills],
                                 "task": f"{rel}/task.md", "inputs": f"{rel}/inputs",
                                 "outputs": f"{rel}/with_skill/outputs"}
                n += 1
    os.makedirs(base, exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump({"iteration": int(number), "runs": sorted(manifest.values(), key=lambda r: (r["skill"], r["eval"], r["run"]))}, f, indent=1)
        f.write("\n")
    print(f"{n} run folder(s) in {os.path.relpath(base, ROOT)} ({runs} per eval); runner list in "
          f"{os.path.relpath(manifest_path, ROOT)}")


if __name__ == "__main__":
    main(sys.argv[1:])
