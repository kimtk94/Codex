#!/usr/bin/env python3
"""Offline tests: mail event-time vs import-time segregation in Feishu."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from unittest import mock

import qq_mail_feed_periods as feed
from qq_mail_ingest import SMOKE_KEY, SafeError

KST = ZoneInfo("Asia/Seoul")
NOW = dt.datetime(2026, 11, 5, 21, 0, tzinfo=KST)


def record(key, received, captured="2026-11-05T12:00:00Z", **added):
    fields = {"Mail Key": key, "Received At": received,
              "Captured UTC": captured, **added}
    return {"record_id": "rec_" + key, "fields": fields}


class FeedPeriodTests(unittest.TestCase):
    def test_old_received_today_imported_stays_history(self):
        r = record("old", "2026-02-11T08:00:00+09:00")
        self.assertEqual(feed.segment(r["fields"]["Received At"], NOW), "HISTORY_2026")
        changed = feed.changes(r, NOW, 30)
        self.assertEqual(changed["Feed Lane"], "HISTORY_2026")
        self.assertEqual(changed["Imported KST"], "2026-11-05 21:00:00")
        self.assertEqual(changed["Received KST"], "2026-02-11 08:00:00")

    def test_recent_30d_boundary(self):
        lower = NOW - dt.timedelta(days=30)
        self.assertEqual(feed.segment(lower.isoformat(), NOW), "CURRENT_30D")
        self.assertEqual(feed.segment((lower - dt.timedelta(seconds=1)).isoformat(), NOW),
                         "HISTORY_2026")

    def test_2026_calendar_cutoff(self):
        self.assertEqual(feed.segment("2025-12-31T23:59:59+09:00", NOW), "PRE_2026")
        self.assertEqual(feed.segment("2026-01-01T00:00:00+09:00", NOW), "HISTORY_2026")
        self.assertEqual(feed.segment("2025-12-31T15:00:00Z", NOW), "HISTORY_2026")

    def test_future_and_missing_dates_do_not_become_current(self):
        self.assertEqual(feed.segment("2026-12-30T01:00:00+09:00", NOW), "DATE_REVIEW")
        self.assertEqual(feed.segment("", NOW), "DATE_REVIEW")
        self.assertEqual(feed.segment("2026-11-01", NOW), "DATE_REVIEW")

    def test_old_feed_lane_reclassifies_as_time_passes(self):
        mail = record("aging", "2026-10-20T15:00:00+09:00",
                      **{"Feed Lane": "CURRENT_30D",
                         "Received KST": "2026-10-20 15:00:00",
                         "Imported KST": "2026-11-05 21:00:00"})
        older = NOW + dt.timedelta(days=20)
        change = feed.changes(mail, older, 30)
        self.assertEqual(change, {"Feed Lane": "HISTORY_2026"})

    def test_idempotence_does_not_rewrite_record(self):
        mail = record("current", "2026-11-04T09:00:00+09:00",
                      **{"Feed Lane": "CURRENT_30D",
                         "Received KST": "2026-11-04 09:00:00",
                         "Imported KST": "2026-11-05 21:00:00"})
        self.assertEqual(feed.changes(mail, NOW, 30), {})

    def test_smoke_skipped_and_no_duplicate_mail_key(self):
        good = record("one", "2026-11-01T00:00:00Z")
        smoke = record(SMOKE_KEY, "")
        updates, counts = feed.compute_updates([good, smoke], NOW, 30)
        self.assertEqual(counts["CURRENT_30D"], 1)
        self.assertEqual(len(updates), 1)
        with self.assertRaisesRegex(SafeError, "DUPLICATE_FEED_MAIL_KEY"):
            feed.compute_updates([good, good], NOW, 30)

    def test_apply_batch_verifies_ids(self):
        rows = [{"record_id": "rec1", "fields": {"Feed Lane": "CURRENT_30D"}}]
        with mock.patch.object(feed, "api",
                               return_value={"records": [{"record_id": "rec1"}]}) as api, \
             mock.patch.object(feed.time, "sleep"):
            self.assertEqual(feed.apply_updates("token", "/table", rows, 5), 1)
            self.assertTrue(api.call_args.args[1].endswith("/records/batch_update"))
        with mock.patch.object(feed, "api", return_value={"records": []}), \
             mock.patch.object(feed.time, "sleep"):
            with self.assertRaisesRegex(SafeError, "FEED_BATCH_RESULT_UNVERIFIED"):
                feed.apply_updates("token", "/table", rows, 5)


if __name__ == "__main__":
    unittest.main()
