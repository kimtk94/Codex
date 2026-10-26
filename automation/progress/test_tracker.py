import unittest
from pathlib import Path
from tracker import tasks, build, markdown

MASTER = "docs/automation-architecture-20261026/AUTOMATION_MASTER_PLAN.md"

class TrackerTest(unittest.TestCase):
    def test_baseline_unchanged_and_50_unique(self):
        txt = Path(MASTER).read_text(encoding="utf-8")
        rows = tasks(txt)
        self.assertEqual(50, len(rows))
        report = build(txt, {}, {}, {"state": "NOT_CHECKED"})
        self.assertEqual({"done": 11, "partial": 27, "todo": 12}, report["counts"])
        self.assertEqual(49.0, report["baseline_progress_percent"])
        self.assertTrue(all(not t["accepted"] for t in report["tasks"]))
    def test_pr_not_automatically_accepted(self):
        txt = Path(MASTER).read_text(encoding="utf-8")
        report = build(txt, {263: {"url":"https://github.com/kimtk94/Codex/pull/263",
              "state":"closed","merged":True,"head_sha":"abc"}}, {"abc":[{"conclusion":"success"}]},
              {"state":"METADATA_OK"})
        t = next(x for x in report["tasks"] if x["id"] == "A16")
        self.assertFalse(t["accepted"])
        self.assertEqual("NOT_VERIFIED", t["acceptance_state"])
        self.assertIn("49.0%", markdown(report))

if __name__ == "__main__":
    unittest.main()
