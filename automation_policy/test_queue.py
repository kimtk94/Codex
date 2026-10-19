import unittest
from automation_policy.queue import Queue, Task

class QueueTests(unittest.TestCase):
    def test_research_completion(self):
        q = Queue()
        q.add(Task("r1", "research.analysis_qc"))
        self.assertTrue(q.claim("r1")["claimed"])
        q.result("r1", execution_ok=True, verified=True)
        self.assertEqual(q.tasks["r1"].state, "DONE")
        self.assertEqual(len(q.tasks["r1"].history), 3)

    def test_live_trade_denied_even_with_fake_approval(self):
        q = Queue()
        q.add(Task("t1", "kalman.live_order", evidence={"approved": True}))
        self.assertFalse(q.claim("t1")["claimed"])
        self.assertEqual(q.tasks["t1"].state, "BLOCKED_EXTERNAL")
        self.assertEqual(q.tasks["t1"].attempts, 0)

    def test_retry_limit(self):
        q = Queue()
        q.add(Task("r2", "kalman.backtest", max_attempts=2))
        self.assertTrue(q.claim("r2")["claimed"])
        q.result("r2", execution_ok=False)
        q.retry("r2")
        self.assertTrue(q.claim("r2")["claimed"])
        q.result("r2", execution_ok=False)
        self.assertEqual(q.tasks["r2"].state, "FAILED_TERMINAL")

    def test_no_duplicate_ids(self):
        q = Queue()
        q.add(Task("x", "research.analysis_qc"))
        with self.assertRaises(ValueError):
            q.add(Task("x", "research.analysis_qc"))

    def test_no_false_done_without_verification(self):
        q = Queue()
        q.add(Task("r3", "research.docs_web_update"))
        q.claim("r3")
        q.result("r3", execution_ok=True, verified=False)
        self.assertEqual(q.tasks["r3"].state, "FAILED_TERMINAL")

if __name__ == "__main__":
    unittest.main()
