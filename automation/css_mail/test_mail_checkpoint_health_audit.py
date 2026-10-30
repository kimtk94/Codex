"""Offline QQ live-checkpoint and archive separation tests, no client data."""
import datetime as dt
import pathlib
import sys
import unittest
sys.path.insert(0,str(pathlib.Path(__file__).parent))
from mail_checkpoint_health_audit import CHECKPOINT,evaluate,parse_time

UTC=dt.timezone.utc
NOW=dt.datetime(2026,10,30,1,0,tzinfo=UTC)
def rows(*values):return [[x] for x in values]
def audit(keys=None,fetch=None,mail=None,legacy=None):
 return evaluate(keys or ["INBOX|1776302013|40939","INBOX|1776302013|40940","INBOX|1776302013|40941"],
   rows(fetch or "2026-10-30T00:11:44+00:00"),
   rows(mail or "2026-10-30T00:02:30+00:00"),
   rows(legacy or "2026-10-19T11:02:13+00:00"),NOW)

class CheckpointAuditTests(unittest.TestCase):
 def test_actual_source_format_matches_uidvalidity_and_imap_uid(self):
  self.assertIsNotNone(CHECKPOINT.fullmatch("INBOX|1776302013|40941"))
  self.assertIsNone(CHECKPOINT.fullmatch("INBOX|abc|40941"))
  self.assertIsNone(CHECKPOINT.fullmatch("INBOX|1776302013|not_a_uid"))
  self.assertIsNone(CHECKPOINT.fullmatch("INBOX|1776302013|40941|extra"))
 def test_recovered_live_ingest_does_not_hide_legacy_archive_backfill(self):
  a=audit()
  self.assertEqual(a["ingest_rows"],3)
  self.assertEqual(a["malformed_ingest_keys"],0)
  self.assertEqual(a["status"],"PASS_WITH_ARCHIVE_REVIEW")
  self.assertEqual(a["nonblocking_archive_reviews"],["LEGACY_ARCHIVE_STALE_REVIEW"])
  self.assertEqual(a["blocking_issues"],[])
 def test_current_fetch_but_outdated_message_must_fail(self):
  a=audit(mail="2026-10-24T00:00:00+00:00")
  self.assertIn("ACTIVE_MAIL_NOT_FRESH",a["blocking_issues"])
  self.assertEqual(a["status"],"BLOCKED")
 def test_duplicate_ingest_uid_must_fail_closed(self):
  a=audit(keys=["INBOX|5|7","INBOX|5|7"])
  self.assertIn("DUPLICATE_ACTIVE_CHECKPOINT_KEYS",a["blocking_issues"])
 def test_malformed_ingest_uid_must_fail_closed(self):
  a=audit(keys=["INBOX|5|7","INBOX\\|5\\|8"])
  self.assertIn("MALFORMED_ACTIVE_CHECKPOINT_KEYS",a["blocking_issues"])
 def test_genuinely_stale_fetch_still_fails(self):
  a=audit(fetch="2026-10-26T00:00:00+00:00")
  self.assertIn("ACTIVE_FETCH_NOT_FRESH",a["blocking_issues"])
 def test_behind_archive_is_a_blocker_even_with_recent_fetch(self):
  a=audit(mail="2026-10-24T00:00:00+00:00",
          legacy="2026-10-29T00:00:00+00:00")
  self.assertIn("ACTIVE_MAIL_BEHIND_LEGACY_ARCHIVE",a["blocking_issues"])
 def test_no_legacy_timestamp_is_visible_as_review_not_fake_pass(self):
  a=evaluate(["INBOX|5|7"],rows("2026-10-30T00:00:00Z"),
    rows("2026-10-30T00:00:00Z"),[],NOW)
  self.assertIn("LEGACY_ARCHIVE_DATE_UNVERIFIED",a["nonblocking_archive_reviews"])
 def test_mixed_timezone_and_naive_timestamp(self):
  self.assertEqual(parse_time("2026-10-30T08:02:30+08:00"),
      parse_time("2026-10-30T00:02:30+00:00"))
  self.assertEqual(parse_time("2026-10-30T00:02:30"),
      parse_time("2026-10-30T00:02:30+00:00"))
 def test_empty_ingest_is_critical(self):
  a=evaluate([],[],[],rows("2026-10-19T00:00:00Z"),NOW)
  self.assertEqual(a["status"],"BLOCKED")
  self.assertIn("ACTIVE_INGEST_EMPTY",a["blocking_issues"])

if __name__=="__main__":unittest.main()
