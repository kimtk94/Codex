import unittest
from sfdc_command_queue import HEAD,normalized,eligible
def row(**updates):
    d={k:"" for k in HEAD}
    d.update({"record_id":"recTest","Request ID":"R001","Action":"OPPO_QUOTE_PAIR",
      "Approval":"PREFLIGHT","Run Mode":"CHECK","Status":"NEW"})
    d.update(updates)
    return [d[k] for k in HEAD]
class QueueGuard(unittest.TestCase):
    def test_preview(self):self.assertTrue(eligible(row()))
    def test_approval(self):
        self.assertFalse(eligible(row(**{"Run Mode":"SAVE"})))
        self.assertFalse(eligible(row(**{"Run Mode":"SAVE","Approval":"APPROVED"})))
        self.assertTrue(eligible(row(**{"Run Mode":"SAVE","Approval":"APPROVED",
          "Duplicate Checked":"YES","Price Checked":"YES"})))
    def test_no_replay(self):self.assertFalse(eligible(row(Status="PASS")))
    def test_unrecognized_action(self):self.assertFalse(eligible(row(Action="UNKNOWN")))
    def test_field_encoding(self):
        r=normalized({"record_id":"rec1","fields":{"Action":"LEAD_CONVERT",
          "New Opportunity Name":[{"text":"Hello"}]}})
        self.assertEqual(r[0],"rec1")
        self.assertEqual(r[HEAD.index("New Opportunity Name")],"Hello")
if __name__=="__main__":unittest.main()
