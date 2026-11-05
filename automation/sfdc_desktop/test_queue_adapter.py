import unittest
from queue_adapter import assemble

class AdapterTests(unittest.TestCase):
    def test_only_approved_entries(self):
        rows = [
          {"source_id":"uid-1","account_key":"account-a","subject":"Follow up","decision":"READY_FOR_SFDC"},
          {"source_id":"uid-2","account_key":"account-b","subject":"Ignore","decision":"PENDING"},
        ]
        staged, skipped = assemble(rows)
        self.assertEqual(len(staged), 1)
        self.assertEqual(staged[0]["object_type"], "Task")
        self.assertEqual(skipped["not_approved"], 1)

    def test_duplicates_and_required_account(self):
        rows = [
          {"source_id":"uid-1","account_key":"account-a","subject":"Follow up","decision":"APPROVED_FOR_SFDC"},
          {"source_id":"uid-1","account_key":"account-a","subject":"Follow up","decision":"APPROVED_FOR_SFDC"},
          {"source_id":"uid-3","account_key":"","subject":"Missing account","decision":"APPROVED_FOR_SFDC"},
        ]
        staged, skipped = assemble(rows)
        self.assertEqual(len(staged), 1)
        self.assertEqual(skipped["duplicate_source"], 1)
        self.assertEqual(skipped["missing_required"], 1)

    def test_deterministic_key(self):
        row = {"source_id":"css-123","account_key":"A","subject":"Hi","decision":"READY_FOR_SFDC"}
        a, _ = assemble([row])
        b, _ = assemble([row])
        self.assertEqual(a[0]["record_key"], b[0]["record_key"])

if __name__ == "__main__":
    unittest.main()
