import unittest
import json
from pathlib import Path
from tracker import tasks, build, markdown, validate_manifest

MASTER = "docs/automation-architecture-20261026/AUTOMATION_MASTER_PLAN.md"

class TrackerTest(unittest.TestCase):
    def test_evidence_reviewed_progress_and_50_unique(self):
        txt = Path(MASTER).read_text(encoding="utf-8")
        rows = tasks(txt)
        self.assertEqual(50, len(rows))
        report = build(txt, {}, {}, {"state": "NOT_CHECKED"})
        self.assertEqual({"done": 11, "partial": 29, "todo": 10}, report["counts"])
        self.assertEqual(51.0, report["baseline_progress_percent"])
        for task_id in ("A28", "A40"):
            task = next(t for t in report["tasks"] if t["id"] == task_id)
            self.assertEqual("partial", task["baseline"])
            self.assertFalse(task["accepted"])
            self.assertEqual("NOT_VERIFIED", task["acceptance_state"])
        self.assertTrue(all(not t["accepted"] for t in report["tasks"]))
    def test_acceptance_manifest_maps_every_task_once(self):
        txt = Path(MASTER).read_text(encoding="utf-8")
        manifest = json.loads(Path("automation/progress/acceptance_manifest.json").read_text(encoding="utf-8"))
        mapping = validate_manifest(manifest, {x["id"] for x in tasks(txt)})
        self.assertEqual(50, len(mapping))
        self.assertEqual("RPA-02", mapping["A22"])
        with self.assertRaises(ValueError):
            bad = json.loads(json.dumps(manifest))
            bad["gates"]["RPA-02"]["tasks"].append("A16")
            validate_manifest(bad, {x["id"] for x in tasks(txt)})

    def test_pr_not_automatically_accepted(self):
        txt = Path(MASTER).read_text(encoding="utf-8")
        report = build(txt, {263: {"url":"https://github.com/kimtk94/Codex/pull/263",
              "state":"closed","merged":True,"head_sha":"abc"}}, {"abc":[{"conclusion":"success"}]},
              {"state":"METADATA_OK"})
        t = next(x for x in report["tasks"] if x["id"] == "A16")
        self.assertFalse(t["accepted"])
        self.assertEqual("NOT_VERIFIED", t["acceptance_state"])
        self.assertIn("51.0%", markdown(report))

if __name__ == "__main__":
    unittest.main()
