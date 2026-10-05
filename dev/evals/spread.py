"""Compare the repeat runs of each eval: what the skill computed and what the grader passed, run by run.

    .venv/bin/python dev/evals/spread.py 12                                  # every eval with two or more runs
    .venv/bin/python dev/evals/spread.py 12 seller-offer-review:5,6 buyer-cma

For each eval in out/evals/iteration-N/ with two or more run-<k>/ folders (dev/evals/setup.py --runs), it finds the
data file each run's reports were rendered from (deal.json, listing.json, buyer.json, report.json, net-sheet.json:
the newest one of that skill anywhere under with_skill/outputs/), runs it through the skill's compute step and keeps
the structured facts exactly as dev/golden.py does (facts()), with the clock frozen on the eval's day. Then it lists:

- Script-owned differences first, as bugs: fields the eval's inputs settle (a date, a tax bill, a count, a rate), so
  they never differ between runs with the same inputs. One often traces to a value the model typed differently into
  the data file; "Data the Model Wrote" shows those.
- Expectations in grading.json (one per run, GRADER.md) that passed in only some runs.
- Judgment differences: the value range, the comps, the list or offer price and what follows from them (nets,
  payments, taxes at the target), expected to vary within reason. A field that follows judgment counts as judgment
  only when a judgment field moved in the same eval; otherwise it is script-owned.

Writes out/evals/iteration-N/spread.md and spread.json.
"""
import copy
import datetime as _dt
import glob
import json
import os
import re
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "dev"))
import golden  # noqa: E402
from skill_import import load  # noqa: E402  (golden put dev/tests on the path)

DEFAULT_TODAY = "2026-09-26"  # setup.py's default day
MISSING = "(missing)"
MD_LIMIT = 40  # rows per table in spread.md; spread.json has every row

# The data file each skill's render.py reads (SKILL.md), and how to tell one from its content when it's named otherwise
DATA_FILES = {"contract-timeline": "deal.json", "seller-offer-review": "listing.json",
              "buyer-offer-strategy": "buyer.json", "buyer-cma": "report.json", "seller-cma": "report.json",
              "seller-net-sheet": "net-sheet.json"}


def detect(data):
    """The skill a data file belongs to, from its top-level keys, or None."""
    if not isinstance(data, dict):
        return None
    keys = set(data)
    if data.get("handoff"):
        return None
    if "scenarios" in keys:
        return "seller-net-sheet"
    if "offers" in keys and "listing" in keys:
        return "seller-offer-review"
    if "buyer" in keys and ("property" in keys or "competition" in keys):
        return "buyer-offer-strategy"
    if "contract" in keys and ("side" in keys or "deadlines" in keys):
        return "contract-timeline"
    if "subject" in keys and ({"pricing", "recommendation"} & keys):
        return "seller-cma"
    if "subject" in keys and ({"offer_plan", "bottom_line", "history"} & keys or "comps" in keys):
        return "buyer-cma"
    return None


# Which fields are judgment, per skill (regexes over flattened fact paths like "strategies[1].net"):
#   script:  always script-owned, even under a judgment prefix (a rate, a millage, an assumed fee)
#   roots:   judgment: the comps, the range, the list or offer price
#   derived: judgment only when a root moved in the same eval (nets, payments and taxes at the chosen price)
#   text:    counts of sentences the model wrote (why, first steps): judgment
SPEC = {
    "buyer-cma": {
        "script": [r"^payments\.(rate|insurance_annual|flood)$",
                   r"^credit\.(closing_costs_given|program|down_pct)"],
        # the plan's prices follow the posture (the category the model picks) and the range: judgment only when a root
        # moved; an agent's plan_override shows as offer_plan.override
        "roots": [r"^comps_table\[", r"^adjusted_(min|max)$", r"^median_(adjusted|shown)$", r"^range\.",
                  r"^handoff\.(comps|value)", r"^handoff\.posture$", r"^payments\.price$", r"^comps\.",
                  r"^offer_plan\.(posture|override)\b"],
        "derived": [r"^offer_plan\.", r"^handoff\.offer_plan", r"^payments\.", r"^taxes\[", r"^credit\.", r"^credit_alt\.",
                    r"^cash_fit", r"^competition_estimates",
                    r"^warnings", r"^warning_keys", r"^handoff\.recommended_list_price", r"^costs\.", r"^summary\.",
                    r"^competition\.", r"^notes", r"^note_keys", r"^assumption", r"^chat_notes"],
        "text": [r"^summary\.(why|check_first)"],
    },
    "seller-cma": {
        "script": [r"^payments\.(rate|insurance_annual|flood|homestead|homestead_applied|loan_type|down_pct|school_mills|"
                   r"total_mills|tax_estimated)$",
                   r"^net\.(holding_rate|holding_rate_assumed|payoff|payoff_estimated|tax_assumed|has_tax|no_mortgage|"
                   r"standard_terms|assumed)"],
        # the comps and the pricing stance are judgment; the range, the list price and the options follow from them
        "roots": [r"^comps_table\[", r"^adjusted_(min|max)$", r"^median_adjusted$", r"^n_comps$", r"^max_distance$",
                  r"^stance\.value$", r"^handoff\.(comps|offer_plan)"],
        "derived": [r"^recommendation\.", r"^recommended_index$", r"^stance\.", r"^handoff\.(value|recommended_list_price)",
                    r"^strategies\[", r"^net\.", r"^net_basis$", r"^net_spread$", r"^payments\.",
                    r"^competing_offer_caveat$", r"^warnings", r"^warning_keys", r"^placeholders\."],
        "text": [r"^summary_page\.(why|first_steps)"],
    },
    "buyer-offer-strategy": {
        "script": [],
        "roots": [r"^B\.value", r"^B\.market"],
        "derived": [r"^(O|R|terms|cash|payment|bands|ci|limits|why|lc_why|reached|promoted_from|dropped_stronger|"
                    r"reserve_alt|cash_at_cap)\.", r"^(target|reached|promoted|promoted_from|cash_at_cap|chosen|framing|"
                    r"by_net|reserve_alt|dropped_stronger)$", r"^constraints", r"^reply_lines", r"^absent"],
        "text": [],
    },
    # The offers, list price and CMA range come from the eval's files and prompt, and the engine sets the counter:
    # nothing here is judgment (with no CMA, listing.cma_* is the list price, so it moves only when that was misread)
    "seller-offer-review": {"script": [], "roots": [], "derived": [], "text": []},
    "contract-timeline": {"script": [], "roots": [], "derived": [], "text": []},
    "seller-net-sheet": {"script": [], "roots": [], "derived": [], "text": []},
}


def classify(skill, path, roots_moved):
    """'script', 'judgment' or 'follows' (judgment because a root moved) for a differing fact path."""
    spec = SPEC.get(skill) or {}
    hit = lambda key: any(re.search(p, path) for p in spec.get(key) or [])  # noqa: E731
    if hit("script"):
        return "script"
    if hit("roots") or hit("text"):
        return "judgment"
    if hit("derived"):
        return "follows" if roots_moved else "script"
    return "script"


def flatten(v, path="", out=None):
    """{'a.b[0].c': value} for every leaf of a facts() tree."""
    out = {} if out is None else out
    if isinstance(v, dict) and v:
        for k, x in v.items():
            flatten(x, f"{path}.{k}" if path else str(k), out)
    elif isinstance(v, list) and v:
        for i, x in enumerate(v):
            flatten(x, f"{path}[{i}]", out)
    else:
        out[path] = v
    return out


def differences(flats):
    """{path: [value per run]} for every path whose value isn't the same in every run."""
    paths = sorted(set().union(*flats)) if flats else []
    out = {}
    for p in paths:
        vals = [f.get(p, MISSING) for f in flats]
        if any(v != vals[0] for v in vals[1:]):
            out[p] = vals
    return out


# --- runs, data files and compute ------------------------------------------------------------------------

def run_folders(eval_dir):
    """[(run label, folder with with_skill/)]: run-<k>/ folders, or the eval folder itself (iterations before --runs)."""
    runs = sorted((d for d in glob.glob(os.path.join(eval_dir, "run-*")) if os.path.isdir(d)),
                  key=lambda d: int(re.sub(r"\D", "", os.path.basename(d)) or 0))
    if runs:
        return [(os.path.basename(d), d) for d in runs]
    return [("run-1", eval_dir)] if os.path.isdir(os.path.join(eval_dir, "with_skill")) else []


def _rel(path):
    """A path relative to the repo when it's inside it."""
    rel = os.path.relpath(path, ROOT)
    return path if rel.startswith("..") else rel


def _json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def data_files(outputs, skills):
    """{skill: path} of the data file each skill rendered from: its usual name first, else any file whose content is
    that skill's; the newest when there are several."""
    found = {}
    for path in glob.glob(os.path.join(outputs, "**", "*.json"), recursive=True):
        name = os.path.basename(path)
        if name.endswith(".cma.json") or name == "grading.json":
            continue
        data = _json(path)
        skill = detect(data)
        if skill not in skills:
            continue
        named = name == DATA_FILES[skill]
        rank = (named, os.path.getmtime(path))
        if skill not in found or rank > found[skill][0]:
            found[skill] = (rank, path)
    return {s: p for s, (_, p) in found.items()}


def find_handoff(run_dir, side):
    """The newest .cma.json in the run's outputs (else its inputs) for this side (else any side), or None."""
    for where in (os.path.join(run_dir, "with_skill", "outputs"), os.path.join(run_dir, "inputs")):
        files = sorted(glob.glob(os.path.join(where, "**", "*.cma.json"), recursive=True), key=os.path.getmtime,
                       reverse=True)
        for want in (side, None):
            for f in files:
                h = _json(f) or {}
                if want is None or h.get("side") == want:
                    return f
    return None


def resolve_export(R, data_path, run_dir, skill):
    """Point a CMA report's export at a file that exists: as written, beside the data file, from the skill folder
    (where the runner ran its scripts), or by name in the run's inputs or outputs."""
    path = R.get("export")
    if not path:
        return
    for cand in (path, os.path.join(os.path.dirname(data_path), path), os.path.join(ROOT, "skills", skill, path)):
        if os.path.isabs(cand) and os.path.exists(cand):
            R["export"] = cand
            return
    name = os.path.basename(path)
    for where in ("inputs", os.path.join("with_skill", "outputs")):
        hits = glob.glob(os.path.join(run_dir, where, "**", name), recursive=True)
        if hits:
            R["export"] = os.path.abspath(hits[0])
            return


def compute(skill, data_path, run_dir, today):
    """facts() of the skill's compute step on this run's data file, with the clock on the eval's day."""
    data = _json(data_path)
    if data is None:
        raise ValueError(f"{_rel(data_path)} isn't valid JSON")
    data = copy.deepcopy(data)
    golden.TODAY = _dt.date.fromisoformat(today)
    handoff = None
    if skill in ("buyer-offer-strategy", "seller-offer-review", "seller-net-sheet") and not isinstance(data.get("cma"), dict):
        handoff = find_handoff(run_dir, "seller" if skill != "buyer-offer-strategy" else "buyer")
        if handoff and skill != "seller-net-sheet":
            data["cma"] = _json(handoff)
    if skill in ("buyer-cma", "seller-cma"):
        resolve_export(data, data_path, run_dir, skill)
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, os.path.basename(data_path))
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
        if skill == "seller-net-sheet":
            (cs,) = load("seller-net-sheet", "compute")
            golden.freeze_clock()
            result = cs.run(data, handoff)
        else:
            result = golden.CASES[skill][0](path)
    return golden.facts(result), handoff


# --- grading ------------------------------------------------------------------------------------------------

def norm(text):
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def expectation_spread(gradings):
    """Per expectation text (as the grader wrote it in every run): passed per run, and the pass rate per run."""
    texts, results = [], {}
    for g in gradings:
        for x in (g or {}).get("expectations") or []:
            key = norm(x.get("text"))
            if key not in results:
                results[key] = {"text": x.get("text"), "passed": [None] * len(gradings)}
                texts.append(key)
    for i, g in enumerate(gradings):
        for x in (g or {}).get("expectations") or []:
            results[norm(x.get("text"))]["passed"][i] = bool(x.get("passed"))
    rows = [results[k] for k in texts]
    flaky = [r for r in rows if True in r["passed"] and False in r["passed"]]
    always = [r for r in rows if r["passed"] and all(p is False for p in r["passed"])]
    partial = [r for r in rows if None in r["passed"] and any(p is not None for p in r["passed"])]
    rates = [((g or {}).get("summary") or {}).get("pass_rate") if g else None for g in gradings]
    return {"flaky": flaky, "always_failed": always, "not_in_every_run": partial, "pass_rates": rates}


# --- one eval -----------------------------------------------------------------------------------------------

def eval_info(skill, eval_id):
    path = os.path.join(ROOT, "dev", "evals", skill, "evals.json")
    for e in (_json(path) or {}).get("evals") or []:
        if e.get("id") == eval_id:
            return e
    return {}


def spread_eval(skill, eval_id, eval_dir):
    info = eval_info(skill, eval_id)
    skills = info.get("skills") or [skill]
    today = info.get("today") or DEFAULT_TODAY
    runs = run_folders(eval_dir)
    out = {"skill": skill, "eval": eval_id, "runs": [r for r, _ in runs], "today": today, "problems": [],
           "data_files": {}, "fields": [], "inputs": [], "expectations": None}
    if len(runs) < 2:
        return out
    by_skill = {}
    for label, run_dir in runs:
        files = data_files(os.path.join(run_dir, "with_skill", "outputs"), skills)
        for s in skills:
            if s not in golden.CASES:
                continue
            path = files.get(s)
            out["data_files"].setdefault(s, []).append(_rel(path) if path else None)
            entry = by_skill.setdefault(s, {"facts": [], "inputs": [], "labels": []})
            if not path:
                out["problems"].append(f"{label}: no {DATA_FILES[s]} for {s} under with_skill/outputs/")
                continue
            try:
                facts, _ = compute(s, path, run_dir, today)
            except Exception as exc:  # a run's data file the compute step rejects: report it, compare the others
                out["problems"].append(f"{label}: {s} compute failed on {_rel(path)}: "
                                       f"{type(exc).__name__}: {str(exc)[:300]}")
                continue
            entry["facts"].append(flatten(facts))
            entry["inputs"].append(flatten(golden.facts(_json(path))))
            entry["labels"].append(label)
    for s, entry in by_skill.items():
        if len(entry["facts"]) < 2:
            continue
        diffs = differences(entry["facts"])
        roots_moved = any(classify(s, p, False) == "judgment" for p in diffs if not _is_text(s, p))
        prefix = f"{s}: " if len(skills) > 1 else ""
        for p, vals in diffs.items():
            out["fields"].append({"skill": s, "field": prefix + p, "kind": classify(s, p, roots_moved),
                                  "runs": entry["labels"], "values": vals})
        for p, vals in differences(entry["inputs"]).items():
            out["inputs"].append({"skill": s, "field": prefix + p, "runs": entry["labels"], "values": vals})
    gradings = [_json(os.path.join(d, "with_skill", "grading.json")) for _, d in runs]
    if any(gradings):
        out["expectations"] = expectation_spread(gradings)
        missing = [label for (label, _), g in zip(runs, gradings) if not g]
        if missing:
            out["problems"].append(f"no grading.json in {', '.join(missing)}")
    return out


def _is_text(skill, path):
    return any(re.search(p, path) for p in (SPEC.get(skill) or {}).get("text") or [])


# --- report -------------------------------------------------------------------------------------------------

def _cell(v):
    s = json.dumps(v) if not isinstance(v, str) else v
    return (s[:60] + "...") if len(s) > 63 else s


def _table(rows, nruns_labels):
    head = "| Field | " + " | ".join(nruns_labels) + " |"
    lines = [head, "|---|" + "---|" * len(nruns_labels)]
    for r in rows[:MD_LIMIT]:
        lines.append(f"| `{r['field']}` | " + " | ".join(_cell(v) for v in r["values"]) + " |")
    if len(rows) > MD_LIMIT:
        lines.append(f"\n{len(rows) - MD_LIMIT} more in spread.json.")
    return lines


def _mark(p):
    return {True: "pass", False: "FAIL", None: "—"}[p]


def markdown(number, results):
    compared = [r for r in results if len(r["runs"]) >= 2]
    lines = [f"# Spread: Iteration {number}", "",
             "Each eval's runs compared field by field (compute step facts, as dev/golden.py keeps them) and "
             "expectation by expectation (grading.json). Script-owned differences are bugs: the eval's inputs settle "
             "them. Judgment differences are expected within reason.", "",
             "| Skill | Eval | Runs | Script-Owned | Judgment | Expectations Passing in Some Runs | Pass Rate per Run |",
             "|---|---|---|---|---|---|---|"]
    for r in compared:
        script = sum(1 for f in r["fields"] if f["kind"] == "script")
        judg = len(r["fields"]) - script
        ex = r["expectations"] or {}
        rates = " / ".join("—" if x is None else f"{x:.0%}" for x in ex.get("pass_rates") or [])
        lines.append(f"| {r['skill']} | {r['eval']} | {len(r['runs'])} | {script} | {judg} | "
                     f"{len(ex.get('flaky') or [])} | {rates or '—'} |")
    single = [f"{r['skill']} {r['eval']}" for r in results if len(r["runs"]) < 2]
    if single:
        lines += ["", f"Not compared (fewer than two runs): {', '.join(single)}."]

    lines += ["", "## Script-Owned Differences (Bugs)", ""]
    any_script = False
    for r in compared:
        rows = [f for f in r["fields"] if f["kind"] == "script"]
        if rows:
            any_script = True
            lines += [f"### {r['skill']} Eval {r['eval']}", ""] + _table(rows, r["runs"]) + [""]
    if not any_script:
        lines += ["None.", ""]

    lines += ["## Expectations That Pass in Only Some Runs", ""]
    any_flaky = False
    for r in compared:
        ex = r["expectations"] or {}
        if ex.get("flaky") or ex.get("not_in_every_run"):
            any_flaky = True
            lines += [f"### {r['skill']} Eval {r['eval']}", "", "| Expectation | " + " | ".join(r["runs"]) + " |",
                      "|---|" + "---|" * len(r["runs"])]
            for x in (ex.get("flaky") or []) + (ex.get("not_in_every_run") or []):
                lines.append(f"| {x['text']} | " + " | ".join(_mark(p) for p in x["passed"]) + " |")
            lines.append("")
    if not any_flaky:
        lines += ["None.", ""]

    lines += ["## Expectations Failed in Every Run", ""]
    fails = [(r, x) for r in compared for x in ((r["expectations"] or {}).get("always_failed") or [])]
    lines += [f"- {r['skill']} {r['eval']}: {x['text']}" for r, x in fails] or ["None."]

    lines += ["", "## Judgment Differences", "",
              "Judgment fields (the comps, the range, the list or offer price) and what follows from them when they "
              "moved.", ""]
    any_j = False
    for r in compared:
        rows = [f for f in r["fields"] if f["kind"] != "script"]
        if rows:
            any_j = True
            lines += [f"### {r['skill']} Eval {r['eval']}", ""] + _table(rows, r["runs"]) + [""]
    if not any_j:
        lines += ["None.", ""]

    lines += ["## Data the Model Wrote That Differs", "",
              "Numbers, dates and keys in each run's data file (facts() of the file itself), to trace a difference "
              "above to the value the model typed.", ""]
    any_in = False
    for r in compared:
        if r["inputs"]:
            any_in = True
            lines += [f"### {r['skill']} Eval {r['eval']}", ""] + _table(r["inputs"], r["runs"]) + [""]
    if not any_in:
        lines += ["None.", ""]

    probs = [(r, p) for r in results for p in r["problems"]]
    lines += ["## Problems", ""] + ([f"- {r['skill']} {r['eval']}: {p}" for r, p in probs] or ["None."])
    return "\n".join(lines) + "\n"


def selection(base, args):
    skills = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    if not args:
        return {s: None for s in skills}
    out = {}
    for a in args:
        name, _, ids = a.partition(":")
        if name not in skills:
            sys.exit(f"No runs for {name!r} in {base}")
        out[name] = {int(i) for i in ids.split(",")} if ids else None
    return out


def main(argv=None, base_dir=None):
    argv = sys.argv[1:] if argv is None else argv
    if not argv or not argv[0].isdigit():
        sys.exit(__doc__)
    number = argv[0]
    base = base_dir or os.path.join(ROOT, "out", "evals", f"iteration-{number}")
    if not os.path.isdir(base):
        sys.exit(f"No iteration folder {base}")
    results = []
    for skill, ids in selection(base, argv[1:]).items():
        evals = sorted(glob.glob(os.path.join(base, skill, "eval-*")), key=lambda d: int(d.rsplit("-", 1)[1]))
        for d in evals:
            eid = int(d.rsplit("-", 1)[1])
            if ids is None or eid in ids:
                results.append(spread_eval(skill, eid, d))
    with open(os.path.join(base, "spread.json"), "w", encoding="utf-8") as f:
        json.dump({"iteration": int(number), "evals": results}, f, indent=1, default=str)
        f.write("\n")
    with open(os.path.join(base, "spread.md"), "w", encoding="utf-8") as f:
        f.write(markdown(number, results))
    script = sum(1 for r in results for x in r["fields"] if x["kind"] == "script")
    flaky = sum(len((r["expectations"] or {}).get("flaky") or []) for r in results)
    print(f"{len(results)} eval(s): {script} script-owned difference(s), {flaky} expectation(s) passing in only some "
          f"runs. Report: {_rel(os.path.join(base, 'spread.md'))}")
    return 1 if script else 0


if __name__ == "__main__":
    sys.exit(main())
