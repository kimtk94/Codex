"""Offline guards: live QQ staging after verified legacy archive handoff."""
import datetime as dt
import unittest
from contextlib import ExitStack
from unittest.mock import patch

import mail_checkpoint_health_audit as m


class CheckpointAuditTests(unittest.TestCase):
    def run_case(self, *, key="INBOX|1776302013|41009", legacy_days=10,
                 staging_hours=1, fetch_hours=0.5, gap=False):
        now=dt.datetime.now(dt.timezone.utc)
        stamp=lambda delta:(now-delta).isoformat()
        legacy=stamp(dt.timedelta(days=legacy_days))
        earliest=stamp(dt.timedelta(days=legacy_days+1 if not gap else legacy_days-2))
        latest=stamp(dt.timedelta(hours=staging_hours))
        data={
            ("CSS Git Ingest","A1:A50000"):[["ingest_key"],[key],["INBOX|1776302013|41010"]],
            ("CSS Git Ingest","O1:O50000"):[["last_fetch_utc"],[stamp(dt.timedelta(hours=fetch_hours))]],
            ("CSS Git Ingest","F1:F50000"):[["received_at"],[earliest],[latest]],
            ("All Emails","A1:A45000"):[["uid"],["inbox:39999"]],
            ("All Emails","C1:C45000"):[["received_at"],[legacy]]
        }
        with ExitStack() as stack:
            stack.enter_context(patch.dict(m.os.environ,{"CKD_DRIVE_SA_JSON":"{}"}))
            stack.enter_context(patch.object(m.service_account.Credentials,
                "from_service_account_info",return_value=object()))
            stack.enter_context(patch.object(m,"AuthorizedSession",return_value=object()))
            stack.enter_context(patch.object(m,"read",
                side_effect=lambda sess,tab,area:data[(tab,area)]))
            return m.audit()

    def test_archive_old_live_stage_recent_with_overlap_passes(self):
        self.assertEqual(self.run_case(),0)

    def test_malformed_uid_fails(self):
        self.assertEqual(self.run_case(key="bad-key"),2)

    def test_stale_live_stage_fails(self):
        self.assertEqual(self.run_case(staging_hours=50,fetch_hours=50),2)

    def test_gap_from_archive_to_live_stage_fails(self):
        self.assertEqual(self.run_case(gap=True),2)


if __name__=="__main__":
    unittest.main()
