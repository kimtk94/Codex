import unittest
from ops_live_collector import github_records, WORKFLOWS
class LiveOpsTest(unittest.TestCase):
    def test_actual_event_preserved(self):
        def fake(url,token):
            return {"workflow_runs":[{"id":1,"event":"schedule","conclusion":"success","status":"completed","html_url":"https://github.com/example/1","created_at":"2026-10-26T00:00:00Z"}]}
        got=github_records(fake)
        self.assertEqual(set(WORKFLOWS),set(got))
        self.assertEqual("schedule",got["progress_audit"][0]["event"])
    def test_zero_runs_not_invented(self):
        got=github_records(lambda url,token:{"workflow_runs":[]})
        self.assertTrue(all(not v for v in got.values()))
if __name__=="__main__":unittest.main()
