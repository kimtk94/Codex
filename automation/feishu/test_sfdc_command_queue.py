import unittest
from unittest.mock import patch
from sfdc_command_queue import (HEAD,normalized,eligible,column_name,LAST_COLUMN,
    PRICE_INPUT_FIELDS,PRICE_RESULT_FIELDS,field_spec,ensure_mirror,SINK_FIELDS)
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
        self.assertEqual(HEAD[-1],"Product Price Items JSON")
        self.assertEqual(LAST_COLUMN,"AM")
        self.assertEqual(column_name(25),"Z")
        self.assertEqual(column_name(26),"AA")
    def test_currency_fields_are_numeric_in_feishu(self):
        self.assertEqual(field_spec("Product Unit KRW")["type"],2)
        self.assertEqual(field_spec("Product Unit KRW")["property"]["formatter"],"1,000")
        self.assertEqual(field_spec("Source Product Name")["type"],1)
    def test_request_numeric_overrides_are_source_fields(self):
        request=row(**{"Requested Product Unit KRW":"200000"})
        self.assertEqual(request[HEAD.index("Requested Product Unit KRW")],"200000")
    def test_existing_mirror_header_migration_is_append_only(self):
        old=HEAD[:22]
        props={"sheets":[{"properties":{"title":"CSS SFDC Command Queue",
             "sheetId":1234,"gridProperties":{"rowCount":2000,"columnCount":22}}}]}
        responses=[props,{},{"values":[old]},{},{"values":[HEAD]}]
        with patch("sfdc_command_queue.gs",side_effect=responses) as gs:
            ensure_mirror(object())
        self.assertEqual(gs.call_count,5)
        self.assertEqual(gs.call_args_list[1].args[1],"POST")
        self.assertEqual(gs.call_args_list[1].args[3]["requests"][0]
            ["updateSheetProperties"]["properties"]["gridProperties"]["columnCount"],len(HEAD))
        self.assertEqual(gs.call_args_list[3].args[3]["values"],[HEAD])
    def test_pricing_result_keys_are_sink_only(self):
        self.assertIn("Product Net KRW",SINK_FIELDS)
        self.assertIn("Price Status",SINK_FIELDS)
        self.assertIn("Product Price Items JSON",SINK_FIELDS)
        self.assertNotIn("Requested Product Unit KRW",SINK_FIELDS)
    def test_numeric_feishu_source_readback_is_integer(self):
        from sfdc_command_queue import plain
        self.assertEqual(plain(190000.0),"190000")
    def test_field_encoding(self):
        r=normalized({"record_id":"rec1","fields":{"Action":"LEAD_CONVERT",
          "New Opportunity Name":[{"text":"Hello"}]}})
        self.assertEqual(r[0],"rec1")
        self.assertEqual(r[HEAD.index("New Opportunity Name")],"Hello")
if __name__=="__main__":unittest.main()
