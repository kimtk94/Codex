#!/usr/bin/env python3
"""Offline regressions: genuine QQ key format, timezone-safe freshness, net-of-VAT BI."""
import datetime as dt
import unittest

from mail_checkpoint_health_audit import valid_ingest_key, live_source_unhealthy
from project_lifecycle_refresh import latest_source_timestamp
from bi_service_reconcile import net_summary_from_gross_fact, CATEGORIES


class IntegrityTests(unittest.TestCase):
    def test_real_qq_ingest_key_shapes(self):
        self.assertTrue(valid_ingest_key("INBOX|1790000001|42442"))
        self.assertTrue(valid_ingest_key("Sent Messages|1790000001|22777"))
        for key in ("INBOX|bad|123", "INBOX|42", "INBOX|42|7|8", ""):
            self.assertFalse(valid_ingest_key(key))

    def test_historical_mail_archive_does_not_fail_fresh_cursor(self):
        # Legacy mail may be 11+ days behind; only active QQ cursor age gates.
        self.assertFalse(live_source_unhealthy(0, 0, 1.1, 24))
        self.assertTrue(live_source_unhealthy(1, 0, 1.1, 24))
        self.assertTrue(live_source_unhealthy(0, 1, 1.1, 24))
        self.assertTrue(live_source_unhealthy(0, 0, 24.1, 24))
        self.assertTrue(live_source_unhealthy(0, 0, None, 24))

    def test_qq_latest_uses_instant_not_offset_string(self):
        rows=[["2026-10-30T23:43:52+09:00"],["2026-10-30T20:24:42+00:00"]]
        self.assertEqual(dt.datetime(2026,10,30,20,24,42,tzinfo=dt.timezone.utc),
                         latest_source_timestamp(rows))
        self.assertIsNone(latest_source_timestamp([]))

    def test_net_summary_retains_10_percent_vat_exclusion(self):
        result=net_summary_from_gross_fact([
            ("mRNA",1100, 1100/1500),
            ("mRNA",2200, 2200/1500),
            ("WGS/WES",5500, 5500/1500),
        ])
        d={r[0]:r for r in result}
        self.assertEqual(len(CATEGORIES),len(result))
        self.assertEqual(["mRNA",2,3000],d["mRNA"][:3])
        self.assertEqual(["WGS/WES",1,5000],d["WGS/WES"][:3])
        self.assertAlmostEqual(2.0,d["mRNA"][3],places=6)

    def test_vat_noninteger_and_bad_service_fail_closed(self):
        with self.assertRaisesRegex(RuntimeError,"VAT_NET_NOT_EXACT_INTEGER"):
            net_summary_from_gross_fact([("mRNA",1,0.001)])
        with self.assertRaisesRegex(RuntimeError,"INVALID_GROSS_FACT_RECORD"):
            net_summary_from_gross_fact([("Not a real category",1100,0.7)])


if __name__=="__main__":
    unittest.main()
