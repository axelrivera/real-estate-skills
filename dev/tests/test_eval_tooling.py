"""The eval tooling: dev/evals/setup.py makes one folder per run (--runs), and dev/evals/spread.py compares the runs of
an eval (compute facts and grading.json), on a tiny synthetic iteration built from the fixtures."""
import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "dev", "evals"))
import setup as eval_setup  # noqa: E402
import spread  # noqa: E402


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


class Setup(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        evals = os.path.join(self.tmp, "dev", "evals")
        os.makedirs(os.path.join(evals, "demo-skill", "files"))
        with open(os.path.join(evals, "demo-skill", "files", "notes.md"), "w") as f:
            f.write("notes\n")
        write_json(os.path.join(evals, "demo-skill", "evals.json"), {"skill_name": "demo-skill", "evals": [
            {"id": 1, "prompt": "One message.", "expected_output": "x", "files": ["dev/evals/demo-skill/files/notes.md"]},
            {"id": 2, "today": "2026-10-02", "skills": ["other-skill", "demo-skill"],
             "prompt": ["First message.", "Second message."], "expected_output": "y", "files": []},
        ]})
        self.patch = [(eval_setup, "ROOT", self.tmp), (eval_setup, "EVALS", evals)]
        self.saved = [(m, k, getattr(m, k)) for m, k, _ in self.patch]
        for m, k, v in self.patch:
            setattr(m, k, v)
        self.addCleanup(lambda: [setattr(m, k, v) for m, k, v in self.saved])
        self.base = os.path.join(self.tmp, "out", "evals", "iteration-7")

    def run_setup(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()):
            eval_setup.main(list(argv))

    def test_runs_make_one_folder_per_run(self):
        self.run_setup("7", "--runs", "2")
        for eid in (1, 2):
            for k in (1, 2):
                run = os.path.join(self.base, "demo-skill", f"eval-{eid}", f"run-{k}")
                self.assertTrue(os.path.isfile(os.path.join(run, "task.md")), run)
                self.assertTrue(os.path.isdir(os.path.join(run, "with_skill", "outputs")), run)
        self.assertTrue(os.path.isfile(os.path.join(self.base, "demo-skill", "eval-1", "run-2", "inputs", "notes.md")))
        manifest = read_json(os.path.join(self.base, "runs.json"))["runs"]
        self.assertEqual(len(manifest), 4)
        chain = [r for r in manifest if r["eval"] == 2][0]
        self.assertEqual(chain["skill_folders"], ["skills/other-skill", "skills/demo-skill"])
        self.assertTrue(chain["outputs"].endswith("eval-2/run-1/with_skill/outputs"))

    def test_one_run_is_run_1(self):
        self.run_setup("7", "demo-skill:1")
        self.assertTrue(os.path.isdir(os.path.join(self.base, "demo-skill", "eval-1", "run-1", "with_skill", "outputs")))
        self.assertFalse(os.path.exists(os.path.join(self.base, "demo-skill", "eval-1", "run-2")))
        self.assertFalse(os.path.exists(os.path.join(self.base, "demo-skill", "eval-2")))

    def test_task_has_today_and_messages(self):
        self.run_setup("7", "demo-skill:2")
        with open(os.path.join(self.base, "demo-skill", "eval-2", "run-1", "task.md")) as f:
            text = f.read()
        self.assertTrue(text.startswith("(Today is 2026-10-02.)"))
        self.assertIn("## Message 1\n\nFirst message.", text)
        self.assertIn("## Message 2\n\nSecond message.", text)

    def test_more_runs_later_keep_earlier_outputs(self):
        self.run_setup("7", "demo-skill:1")
        kept = os.path.join(self.base, "demo-skill", "eval-1", "run-1", "with_skill", "outputs", "response.md")
        with open(kept, "w") as f:
            f.write("done\n")
        self.run_setup("7", "--runs", "3", "demo-skill:1")
        self.assertTrue(os.path.isfile(kept))
        self.assertTrue(os.path.isdir(os.path.join(self.base, "demo-skill", "eval-1", "run-3")))
        self.assertEqual(len(read_json(os.path.join(self.base, "runs.json"))["runs"]), 3)

    def test_answers_are_never_copied(self):
        evals = read_json(os.path.join(eval_setup.EVALS, "demo-skill", "evals.json"))
        evals["evals"][0]["files"] = ["out/manual-test/05-seller-offer-review/expected.md"]
        write_json(os.path.join(eval_setup.EVALS, "demo-skill", "evals.json"), evals)
        with self.assertRaises(SystemExit) as cm:
            self.run_setup("7", "demo-skill:1")
        self.assertIn("holds the answers", str(cm.exception))

    def test_missing_kit_file_names_the_make_target(self):
        evals = read_json(os.path.join(eval_setup.EVALS, "demo-skill", "evals.json"))
        evals["evals"][0]["files"] = ["out/manual-test/03-buyer-cma/flyer.pdf"]
        write_json(os.path.join(eval_setup.EVALS, "demo-skill", "evals.json"), evals)
        with self.assertRaises(SystemExit) as cm:
            self.run_setup("7", "demo-skill:1")
        self.assertIn("make manual-kit", str(cm.exception))

    def test_bad_runs_value_stops(self):
        with self.assertRaises(SystemExit):
            self.run_setup("7", "--runs", "0")


class EvalFiles(unittest.TestCase):
    """Every eval in dev/evals/ can be set up: committed files exist, built ones come from a make target, chains name
    real skills, and manual-kit mirrors name a kit case."""

    def test_evals_are_well_formed(self):
        evals_dir = os.path.join(ROOT, "dev", "evals")
        with open(os.path.join(ROOT, "dev", "manual_kit", "build.py"), encoding="utf-8") as f:
            kit = f.read()
        for skill in sorted(os.listdir(evals_dir)):
            path = os.path.join(evals_dir, skill, "evals.json")
            if not os.path.isfile(path):
                continue
            ids = set()
            for e in read_json(path)["evals"]:
                where = f"{skill} eval {e['id']}"
                self.assertNotIn(e["id"], ids, where)
                ids.add(e["id"])
                prompt = e["prompt"]
                self.assertTrue(isinstance(prompt, str) or (isinstance(prompt, list) and len(prompt) > 1
                                                            and all(isinstance(p, str) for p in prompt)), where)
                for s in e.get("skills") or []:
                    self.assertTrue(os.path.isfile(os.path.join(ROOT, "skills", s, "SKILL.md")), f"{where}: {s}")
                if e.get("manual_case"):
                    self.assertIn(f'"{e["manual_case"]}"', kit, where)
                for f in e.get("files") or []:
                    if f.startswith(("out/mock-contracts/", "out/manual-test/")):
                        self.assertNotIn("/key/", f, where)
                        self.assertNotEqual(os.path.basename(f), "expected.md", where)
                        if f.startswith("out/manual-test/"):  # the smoke kit builds the case that holds it
                            self.assertIn(f'"{f.split("/")[2]}"', kit, f"{where}: {f}")
                    else:
                        self.assertTrue(os.path.isfile(os.path.join(ROOT, f)), f"{where}: {f}")


class Spread(unittest.TestCase):
    """A synthetic iteration: two or three runs of one eval, each with the data file it rendered from."""

    def setUp(self):
        self.base = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.base)

    def run_dir(self, skill, eid, k):
        return os.path.join(self.base, skill, f"eval-{eid}", f"run-{k}")

    def add_run(self, skill, eid, k, data, name, grading=None, inputs=()):
        run = self.run_dir(skill, eid, k)
        write_json(os.path.join(run, "with_skill", "outputs", "_work", name), data)
        for src in inputs:
            os.makedirs(os.path.join(run, "inputs"), exist_ok=True)
            shutil.copy(src, os.path.join(run, "inputs"))
        if grading is not None:
            write_json(os.path.join(run, "with_skill", "grading.json"), grading)
        return run

    def spread(self, *args):
        with contextlib.redirect_stdout(io.StringIO()):
            code = spread.main(["99", *args], base_dir=self.base)
        return code, read_json(os.path.join(self.base, "spread.json"))

    @staticmethod
    def grading(*passed):
        ex = [{"text": f"Expectation {i}", "passed": p, "evidence": ""} for i, p in enumerate(passed, 1)]
        n = sum(passed)
        return {"expectations": ex, "summary": {"passed": n, "failed": len(ex) - n, "total": len(ex),
                                                 "pass_rate": n / len(ex)}}

    def test_same_data_no_differences(self):
        deal = read_json(os.path.join(ROOT, "dev", "fixtures", "contract-timeline", "buyer-fha.json"))
        for k in (1, 2):
            self.add_run("contract-timeline", 990, k, deal, "deal.json", self.grading(True, True))
        code, out = self.spread()
        (r,) = out["evals"]
        self.assertEqual(code, 0)
        self.assertEqual(r["fields"], [])
        self.assertEqual(r["expectations"]["flaky"], [])
        self.assertEqual(r["problems"], [])

    def test_script_owned_difference_and_flaky_expectation(self):
        deal = read_json(os.path.join(ROOT, "dev", "fixtures", "contract-timeline", "buyer-fha.json"))
        self.add_run("contract-timeline", 990, 1, deal, "deal.json", self.grading(True, True))
        moved = json.loads(json.dumps(deal))
        moved["contract"]["inspection_days"] = (deal["contract"].get("inspection_days") or 10) + 5
        self.add_run("contract-timeline", 990, 2, moved, "deal.json", self.grading(True, False))
        code, out = self.spread()
        (r,) = out["evals"]
        self.assertEqual(code, 1)  # a script-owned difference fails the command
        self.assertTrue(r["fields"])
        self.assertTrue(all(f["kind"] == "script" for f in r["fields"]))
        self.assertIn("contract.inspection_days", [f["field"] for f in r["inputs"]])
        (flaky,) = r["expectations"]["flaky"]
        self.assertEqual(flaky["text"], "Expectation 2")
        self.assertEqual(flaky["passed"], [True, False])
        with open(os.path.join(self.base, "spread.md")) as f:
            md = f.read()
        self.assertLess(md.index("## Script-Owned Differences (Bugs)"), md.index("## Judgment Differences"))
        self.assertIn("| Expectation 2 | pass | FAIL |", md)

    def test_cma_comp_change_is_judgment_and_export_is_found_in_inputs(self):
        report = read_json(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json"))
        export = os.path.join(ROOT, report["export"])
        report["export"] = os.path.basename(export)  # as a runner writes it: found in the run's inputs/
        self.add_run("buyer-cma", 991, 1, report, "report.json", inputs=[export])
        other = json.loads(json.dumps(report))
        other["comps"]["cards"][0]["sold_price"] += 7000
        self.add_run("buyer-cma", 991, 2, other, "report.json", inputs=[export])
        _, out = self.spread("buyer-cma")
        (r,) = out["evals"]
        self.assertEqual(r["problems"], [])
        kinds = {f["field"]: f["kind"] for f in r["fields"]}
        self.assertEqual(kinds.get("adjusted_max"), "judgment")
        self.assertEqual(kinds.get("handoff.comps[0].adjusted"), "judgment")
        self.assertFalse([p for p in kinds if p.startswith("history.")])  # the listing history is the same
        self.assertFalse([p for p, k in kinds.items() if k == "script"], kinds)

    def test_cma_posture_is_judgment_and_its_prices_follow(self):
        """The buyer CMA's posture is the model's pick (judgment); the plan's prices are the script's from it."""
        report = read_json(os.path.join(ROOT, "dev", "fixtures", "buyer-cma", "hickorywood.json"))
        export = os.path.join(ROOT, report["export"])
        report["export"] = os.path.basename(export)
        self.add_run("buyer-cma", 994, 1, report, "report.json", inputs=[export])
        other = json.loads(json.dumps(report))
        other["offer_plan"].update(posture="standard", posture_reason="The buyer would rather not test the seller.")
        self.add_run("buyer-cma", 994, 2, other, "report.json", inputs=[export])
        _, out = self.spread("buyer-cma")
        (r,) = out["evals"]
        kinds = {f["field"]: f["kind"] for f in r["fields"]}
        self.assertEqual(kinds.get("offer_plan.posture"), "judgment")
        self.assertEqual(kinds.get("offer_plan.opening"), "follows")
        self.assertEqual(kinds.get("handoff.offer_plan.opening"), "follows")

    def test_one_run_is_not_compared_and_missing_data_is_a_problem(self):
        deal = read_json(os.path.join(ROOT, "dev", "fixtures", "contract-timeline", "buyer-fha.json"))
        self.add_run("contract-timeline", 992, 1, deal, "deal.json")
        self.add_run("contract-timeline", 993, 1, deal, "deal.json")
        os.makedirs(os.path.join(self.run_dir("contract-timeline", 993, 2), "with_skill", "outputs"))
        _, out = self.spread()
        by_id = {r["eval"]: r for r in out["evals"]}
        self.assertEqual(by_id[992]["fields"], [])
        self.assertEqual(len(by_id[992]["runs"]), 1)
        self.assertTrue(any("no deal.json" in p for p in by_id[993]["problems"]))

    def test_data_file_found_by_content_when_named_otherwise(self):
        deal = read_json(os.path.join(ROOT, "dev", "fixtures", "contract-timeline", "buyer-fha.json"))
        run = self.add_run("contract-timeline", 994, 1, deal, "cypress-deal.json")
        found = spread.data_files(os.path.join(run, "with_skill", "outputs"), ["contract-timeline"])
        self.assertTrue(found["contract-timeline"].endswith("cypress-deal.json"))

    def test_offer_strategy_uses_the_runs_cma_handoff(self):
        buyer = read_json(os.path.join(ROOT, "dev", "samples", "buyer-offer-strategy.json"))
        buyer.pop("value")  # the range comes from the handoff the runner passed with --cma
        handoff = os.path.join(ROOT, "dev", "evals", "buyer-offer-strategy", "files", "1532-Cypress-Bend-Dr.cma.json")
        run = self.add_run("buyer-offer-strategy", 995, 1, buyer, "buyer.json", inputs=[handoff])
        facts, used = spread.compute("buyer-offer-strategy", os.path.join(run, "with_skill", "outputs", "_work",
                                                                          "buyer.json"), run, "2026-09-26")
        self.assertTrue(used.endswith("1532-Cypress-Bend-Dr.cma.json"))
        flat = spread.flatten(facts)
        self.assertIn(355000, [v for p, v in flat.items() if p.startswith("B.value")])

    def test_follows_judgment_only_when_a_root_moved(self):
        self.assertEqual(spread.classify("seller-cma", "strategies[0].net", True), "follows")
        self.assertEqual(spread.classify("seller-cma", "strategies[0].net", False), "script")
        self.assertEqual(spread.classify("seller-cma", "strategies[0].list_price", False), "script")  # by the stance
        self.assertEqual(spread.classify("seller-cma", "strategies[0].list_price", True), "follows")
        self.assertEqual(spread.classify("seller-cma", "stance.value", False), "judgment")
        self.assertEqual(spread.classify("seller-cma", "payments.rate", True), "script")
        self.assertEqual(spread.classify("contract-timeline", "rows[3].when", True), "script")


if __name__ == "__main__":
    unittest.main()
