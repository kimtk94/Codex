"""Offline guards: live QQ staging is authoritative after verified archive handoff."""
import datetime as dt
import unittest
from unittest.mock import patch

import mail_checkpoint_health_audit as m


class CheckpointAuditTests(unittest.TestCase):
    def run_case(self, *, key="INBOX|1776302013|41009", legacy_days=10,
                 staging_hours=1, fetch_hours=0.5, gap=False):
        now=dt.datetime.now(dt.timezone.utc)
        stamp=lambda delta:(now-delta).isoformat()
        legacy=stamp(dt.timedelta(days=legacy_days))
        if gap:
            staged=stamp(dt.timedelta(days=legacy_days-2))
        else:
            staged=stamp(dt.timedelta(hours=staging_hours))
        data={
            ("CSS Git Ingest","A1:A50000"):[["ingest_key"],[key]],
            ("CSS Git Ingest","O1:O50000"):[["last_fetch_utc"],[stamp(dt.timedelta(hours=fetch_hours))]],
            ("CSS Git Ingest","F1:F50000"):[["received_at"],[staged]],
            ("All Emails","A1:A45000"):[["uid"],["inbox:39999"]],
            ("All Emails","C1:C45000"):[["received_at"],[legacy]]
        }
        with patch.dict(m.os.environ,{"CKD_DRIVE_SA_JSON":"{}"}), \\
             patch.object(m.service_account.Credentials,"from_service_account_info",return_value=object()), \\
             patch.object(m,"AuthorizedSession",return_value=object()), \\
             patch.object(m,"read",side_effect=lambda sess,tab,area:data[(tab,area)]):
            return m.audit()

    def test_live_stage_passes_when_archive_intentionally_old(self):
        # Stage starts before/at the archive boundary in a real backfill.
        self.assertEqual(self.run_case(legacy_days=10,staging_hours=1),0)

    def test_bad_ingest_key_still_fails(self):
        self.assertEqual(self.run_case(key="bad-key"),2)

    def test_stale_live_ingest_fails(self):
        self.assertEqual(self.run_case(staging_hours=50,fetch_hours=50),2)

    def test_uncovered_archive_to_stage_gap_fails(self):
        self.assertEqual(self.run_case(legacy_days=10,gap=True),2)


if __name__=="__main__":
    unittest.main()
