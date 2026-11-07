#!/usr/bin/env python3
"""No network/credentials required for SFDC report freshness regression tests."""
import datetime as dt
import unittest
from zoneinfo import ZoneInfo
from source_freshness_guard import HEADER, KST, inspect, latest_due

def stamp(t):
    return t + " KST"

def sheet(received="2026-11-07 12:00:15", checked="2026-11-07 15:35:04"):
    rows=[list(HEADER)]
    for name in ("Leads","Opportunities","Quotation"):
        rows.append([name,stamp(received),stamp(checked),"100","90","10","0",
                     "a"*64,"STAGED_NOT_PROMOTED","QQ IMAP"])
    return rows

def now(hour,minute,date=7):
    return dt.datetime(2026,11,date,hour,minute,tzinfo=KST)

class FreshnessGateTests(unittest.TestCase):
    def test_noon_report_is_good_before_evening_due(self):
        self.assertEqual(inspect(sheet(),now(16,0))["stale"],[])
    def test_noon_report_is_stale_after_evening_slot(self):
        self.assertEqual(inspect(sheet(),now(20,35))["stale"],
                         ["Leads","Opportunities","Quotation"])
    def test_17h_report_restores_all_entities(self):
        self.assertEqual(inspect(sheet(received="2026-11-07 17:00:05",checked="2026-11-07 18:01:00"),
                                 now(20,35))["stale"],[])
    def test_missing_one_entity_is_not_silently_ok(self):
        rows=sheet();rows[3][1]=stamp("2026-11-07 12:00:00")
        rows[1][1]=rows[2][1]=stamp("2026-11-07 17:00:00")
        self.assertEqual(inspect(rows,now(20,35))["stale"],["Quotation"])
    def test_slot_grace_prevents_false_alarm(self):
        self.assertEqual(inspect(sheet(),now(17,34))["stale"],[])
        self.assertEqual(len(inspect(sheet(),now(17,36))["stale"]),3)
    def test_overnight_targets_prior_17h(self):
        self.assertEqual(latest_due(now(8,0,date=8)).strftime("%Y-%m-%d %H:%M"),
                         "2026-11-07 17:00")
    def test_future_timestamp_is_rejected(self):
        with self.assertRaisesRegex(ValueError,"FUTURE"):
            inspect(sheet(received="2026-11-08 12:00:00"),now(20,35))
    def test_duplicate_or_missing_entity_is_rejected(self):
        rows=sheet();rows.append(rows[1][:])
        with self.assertRaisesRegex(ValueError,"DUPLICATE"):
            inspect(rows,now(20,35))
        rows=sheet()[:-1]
        with self.assertRaisesRegex(ValueError,"INCOMPLETE"):
            inspect(rows,now(20,35))
    def test_preserved_no_new_report_still_must_be_recent(self):
        rows=sheet()
        for row in rows[1:]:
            row[8]="PRESERVED_NO_NEW_REPORT"
        self.assertEqual(len(inspect(rows,now(20,35))["stale"]),3)
    def test_schema_change_is_rejected(self):
        rows=sheet();rows[0][1]="Last Checked KST"
        with self.assertRaisesRegex(ValueError,"SCHEMA"):
            inspect(rows,now(20,35))
    def test_naive_now_rejected(self):
        with self.assertRaisesRegex(ValueError,"AWARE"):
            latest_due(dt.datetime(2026,11,7,20,35))

if __name__=="__main__":
    unittest.main()
