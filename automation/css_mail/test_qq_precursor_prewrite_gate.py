"""Synthetic-only readback, duplicate, stale source and cursor tests."""
import json
import unittest
from automation.css_mail.qq_precursor_prewrite_gate import (
    fingerprint,prewrite_readback,verify_staged_readback
)

INV="209126000001"

def target(num=INV,amount="900"):
    e={"invoice_number":num,"amount_krw":amount,
       "imap_uid":"410","validation_status":"FILENAME_PARSED"}
    return {"number":num,"category":"PRE_CURSOR_MISSING","extract":e}

def snap(t=None):
    t=t or target()
    return {"qq":[],"css":[],"extract":[t["extract"].copy()],
            "cursor":[{"year":"2026","folder":"INBOX","uidvalidity":"123",
                       "last_uid":"500"}],
            "audit":[{"year":"2026","status":"SCAN_COMPLETE",
                      "last_run_utc":"2026-11-22T00:00:00+00:00"}]}

class SnapshotGateTests(unittest.TestCase):
    def test_two_stable_reads_are_hold_not_cas_or_approval(self):
        t=target()
        out=prewrite_readback(snap(t),snap(t),[t])
        self.assertEqual(out["replay_prewrite_stable_readback_count"],1)
        self.assertEqual(out["replay_prewrite_approval_required"],1)
        self.assertEqual(out["replay_prewrite_atomic_cas_verified"],0)
        self.assertEqual(out["replay_prewrite_write_authorized"],0)
        self.assertEqual(out["replay_postwrite_verified"],0)
        self.assertEqual(out["replay_prewrite_status"],"HOLD")
        self.assertNotIn(INV,json.dumps(out))
        self.assertNotIn("900",json.dumps(out))
    def test_replay_when_sink_inserted_between_reads_is_blocked(self):
        t=target()
        before=snap(t); after=snap(t)
        after["qq"]=[{"invoice_number":INV,"amount_krw":"900"}]
        x=prewrite_readback(before,after,[t])
        self.assertEqual(x["replay_prewrite_stable_readback_count"],0)
        self.assertEqual(x["replay_prewrite_existing_sink_record"],1)
        self.assertEqual(x["replay_prewrite_qq_staging_drift"],1)
    def test_changed_amount_source_epoch_or_audit_blocks(self):
        t=target()
        for tab,key,val in (
            ("extract","amount_krw","901"),
            ("cursor","uidvalidity","124"),
            ("audit","status","PARTIAL_SCAN")):
            first=snap(t);second=snap(t)
            second[tab][0][key]=val
            x=prewrite_readback(first,second,[t])
            self.assertEqual(x["replay_prewrite_stable_readback_count"],0)
            self.assertEqual(x["replay_prewrite_snapshot_changed"],1)
    def test_duplicate_rows_missing_tabs_and_duplicate_targets_fail(self):
        t=target()
        a=snap(t);a["qq"]=[{"invoice_number":INV},{"invoice_number":INV}]
        with self.assertRaisesRegex(ValueError,"REPLAY_QQ_DUPLICATE"):
            prewrite_readback(a,a,[t])
        a=snap(t);del a["cursor"]
        with self.assertRaisesRegex(ValueError,"REPLAY_SNAPSHOT_INCOMPLETE"):
            prewrite_readback(a,snap(t),[t])
        with self.assertRaisesRegex(ValueError,"REPLAY_SCOPE_OR_DUPLICATE_INVALID"):
            prewrite_readback(snap(t),snap(t),[t,t])
    def test_readback_full_row_contract_and_zero_issued_month(self):
        expected={"invoice_number":INV,"issued_month":"","amount_krw":"900",
                  "amea_project_id":"A","h_project_id":"H","po_reference":"P",
                  "imap_folder":"INBOX","imap_uid":"410",
                  "filename":"x.pdf","evidence":"OFFICIAL",
                  "backfill_utc":"2026-11-23T00:00:00+00:00"}
        cursor=snap()["cursor"]
        self.assertTrue(verify_staged_readback(expected,[expected],cursor,cursor))
        self.assertFalse(verify_staged_readback(expected,[expected,expected],cursor,cursor))
        modified={**expected,"amount_krw":"901"}
        self.assertFalse(verify_staged_readback(expected,[modified],cursor,cursor))
        modified={**expected,"issued_month":"2026-11"}
        self.assertFalse(verify_staged_readback(expected,[modified],cursor,cursor))
        for variant in (
            {k:v for k,v in expected.items() if k!="backfill_utc"},
            {**expected,"backfill_utc":""},
            {**expected,"backfill_utc":"2026-11-23 00:00:00"},
            {**expected,"backfill_utc":"invalid"},
        ):
            self.assertFalse(verify_staged_readback(variant,[variant],cursor,cursor))
        self.assertFalse(verify_staged_readback(
            expected,[{**expected,"backfill_utc":"2026-11-23T00:00:01+00:00"}],
            cursor,cursor))
        moved=[{**cursor[0],"last_uid":"501"}]
        self.assertFalse(verify_staged_readback(expected,[expected],cursor,moved))
        self.assertFalse(verify_staged_readback({**expected,"issued_month":"2026-11"},
                                              [expected],cursor,cursor))
    def test_hashes_are_private_bytes_and_input_order_independent(self):
        rows=[{"invoice_number":"1","x":"a"},{"invoice_number":"2","x":"b"}]
        self.assertEqual(fingerprint(rows),fingerprint(list(reversed(rows))))
        self.assertIsInstance(fingerprint(rows),bytes)

if __name__=="__main__":
    unittest.main()
