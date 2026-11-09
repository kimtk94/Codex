#!/usr/bin/env python3
import unittest
from unittest import mock
import quote_checkbox_refresh as q
from qq_mail_ingest import SafeError

def record(key,checked,reason):
    return {"fields":{"Source Key":"QUOTE_REVIEW:"+key,
            "합산 제외":checked,"제외 이유":reason}}

class CheckboxRefreshTests(unittest.TestCase):
    def test_changed_checkbox_detected_in_both_directions(self):
        sid="a0P"+"A"*12
        self.assertEqual(q.pending_manual_changes([record(sid,True,"")]),[
            "QUOTE_REVIEW:"+sid])
        self.assertEqual(q.pending_manual_changes([
            record(sid,False,"MANUAL_EXCLUDED")]),["QUOTE_REVIEW:"+sid])
        self.assertEqual(q.pending_manual_changes([record(sid,True,"MANUAL_EXCLUDED")]),[])
        self.assertEqual(q.pending_manual_changes([record(sid,False,"NOT_ACTIVE")]),[])
    def test_inactive_with_checkbox_triggers_record_sync_not_inclusion(self):
        sid="a0P"+"A"*12
        self.assertEqual(len(q.pending_manual_changes([record(sid,True,"NOT_ACTIVE")])),1)
    def test_missing_or_duplicate_is_fail_closed(self):
        with self.assertRaisesRegex(SafeError,"NO_REVIEW_ROWS"):
            q.pending_manual_changes([])
        sid="a0P"+"A"*12
        with self.assertRaisesRegex(SafeError,"DUPLICATE_SOURCE_KEY"):
            q.pending_manual_changes([record(sid,False,""),record(sid,True,"")])
    def test_check_only_sends_one_quote_scope_sync(self):
        sid="a0P"+"A"*12
        with (mock.patch.dict(q.os.environ,{"FEISHU_BASE_APP_TOKEN":q.metrics.EXPECTED_BASE}),
              mock.patch.object(q,"auth",return_value=("tok","root")),
              mock.patch.object(q.metrics,"table_catalog",return_value={
                q.metrics.QUOTE_REVIEW_TABLE:["tblFixture"]}),
              mock.patch.object(q,"list_all",return_value=[record(sid,True,"")]),
              mock.patch.object(q.metrics,"main") as write):
            q.main()
            write.assert_called_once()
        with (mock.patch.dict(q.os.environ,{"FEISHU_BASE_APP_TOKEN":q.metrics.EXPECTED_BASE}),
              mock.patch.object(q,"auth",return_value=("tok","root")),
              mock.patch.object(q.metrics,"table_catalog",return_value={
                q.metrics.QUOTE_REVIEW_TABLE:["tblFixture"]}),
              mock.patch.object(q,"list_all",return_value=[record(sid,True,"MANUAL_EXCLUDED")]),
              mock.patch.object(q.metrics,"main") as write):
            q.main()
            write.assert_not_called()

if __name__=="__main__":
    unittest.main()
