#!/usr/bin/env python3
"""Read-only CRM checkpoint audit regression."""
import unittest
from unittest import mock
import jiin_crm_checkpoint_health as h
from qq_mail_ingest import SafeError


def progress(scanned=200, saved=30, uid=90, validity="34"):
    return {"scanned": scanned, "saved": saved, "last_uid": uid,
            "uidvalidity": validity}


class CheckpointHealthTests(unittest.TestCase):
    def test_valid_progress_and_legacy_rows(self):
        output=h.assess(progress(),65,True)
        self.assertEqual(output["scanned_candidates_cumulative"],200)
        self.assertEqual(output["stored_exact_sender_rows"],65)
        self.assertEqual(output["full_scan_completion"],"NOT_DETERMINABLE_FROM_CHECKPOINT")
        self.assertEqual(output["feishu_writes"],0)

    def test_initial_no_checkpoint_allowed(self):
        output=h.assess(progress(0,0,0,""),65,False)
        self.assertFalse(output["checkpoint_present"])

    def test_checkpoint_save_exceeds_rows_fails(self):
        with self.assertRaisesRegex(SafeError,"SAVED_MORE_THAN_STORED"):
            h.assess(progress(200,90),65,True)

    def test_checkpoint_save_exceeds_scan_fails(self):
        with self.assertRaisesRegex(SafeError,"INVALID_NUMBERS"):
            h.assess(progress(50,80),100,True)

    def test_missing_validity_fails(self):
        with self.assertRaisesRegex(SafeError,"MISSING_UIDVALIDITY"):
            h.assess(progress(validity=""),100,True)

    def test_no_writes_and_only_validated_rows(self):
        tables=[{"name":h.c.TABLE,"table_id":"tblMAIL"},
                {"name":h.CHECKPOINT_TABLE,"table_id":"tblSTATE"}]
        with mock.patch.dict(h.os.environ,{"FEISHU_BASE_APP_TOKEN":h.EXPECTED_BASE}), \
             mock.patch.object(h,"auth",return_value=("token","root")), \
             mock.patch.object(h,"list_all",side_effect=[tables,[{"fields":{"Mail Key":"abc"}}]]), \
             mock.patch.object(h,"summarize",return_value=1) as summary, \
             mock.patch.object(h,"read_checkpoint",return_value=("recSTATE",progress(2,1))):
            result=h.main()
        self.assertEqual(result["stored_exact_sender_rows"],1)
        summary.assert_called_once()


if __name__ == "__main__":
    unittest.main()
