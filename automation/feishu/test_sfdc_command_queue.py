import unittest
from sfdc_command_queue import (HEAD,normalized,eligible,column_name,LAST_COLUMN,
    PRICE_INPUT_FIELDS,PRICE_RESULT_FIELDS,field_spec)
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
    def test_appended_price_fields_keep_old_positions(self):
        self.assertEqual(HEAD[0],"record_id")
        self.assertEqual(HEAD[21],"Checked At")
        self.assertEqual(HEAD[22:24],PRICE_INPUT_FIELDS)
        self.assertEqual(HEAD[24:],PRICE_RESULT_FIELDS)
        self.assertEqual(LAST_COLUMN,"AL")
        self.assertEqual(column_name(25),"Z")
        self.assertEqual(column_name(26),"AA")
    def test_currency_fields_are_numeric_in_feishu(self):
        self.assertEqual(field_spec("Product Unit KRW")["type"],2)
        self.assertEqual(field_spec("Product Unit KRW")["property"]["formatter"],"1,000")
        self.assertEqual(field_spec("Source Product Name")["type"],1)
    def test_request_numeric_overrides_are_source_fields(self):
        request=row(**{"Requested Product Unit KRW":"200000"})
        self.assertEqual(request[HEAD.index("Requested Product Unit KRW")],"200000")
    def test_field_encoding(self):
        r=normalized({"record_id":"rec1","fields":{"Action":"LEAD_CONVERT",
          "New Opportunity Name":[{"text":"Hello"}]}})
        self.assertEqual(r[0],"rec1")
        self.assertEqual(r[HEAD.index("New Opportunity Name")],"Hello")
if __name__=="__main__":unittest.main()
