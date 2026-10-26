import unittest
from publish_evidence import payload, EXPECTED_IDS

class PublisherTest(unittest.TestCase):
    def report(self):
        return {"tasks":[{"id":s,"pr_candidates":[]} for s in EXPECTED_IDS]}
    def test_no_evidence_no_mutation(self):
        self.assertEqual([],payload(self.report(),EXPECTED_IDS,"2026-10-26"))
    def test_one_task_only_evidence_columns(self):
        r=self.report()
        r["tasks"][0]["pr_candidates"]=[{"url":"https://github.com/kimtk94/Codex/pull/263",
          "recent_runs":[{"url":"https://github.com/kimtk94/Codex/actions/runs/1"}]}]
        updates=payload(r,EXPECTED_IDS,"2026-10-26")
        self.assertEqual({"F6","H6","J6"},{c for c,_ in updates})
    def test_reordered_destination_fail_closed(self):
        ids=EXPECTED_IDS.copy()
        ids[0],ids[1]=ids[1],ids[0]
        with self.assertRaises(ValueError): payload(self.report(),ids,"x")
    def test_missing_task_fail_closed(self):
        r=self.report()
        r["tasks"].pop()
        with self.assertRaises(ValueError): payload(r,EXPECTED_IDS,"x")

if __name__=="__main__":
    unittest.main()
