"""Synthetic-only tests. No Google API, mailbox, credentials, or business writes."""
import datetime as dt
import json
import unittest
from automation.css_mail import invoice_source_freshness_monitor as monitor

NOW = dt.datetime(2026, 11, 22, 12, 0, tzinfo=dt.timezone.utc)
SCAN = "2026-11-22T08:35:12+00:00"
OLD = "2026-10-29T15:29:50+00:00"
NEW = "2026-11-22T11:20:36+00:00"


def qq(number, month="2026-11"):
    return {"invoice_number":number,"issued_month":month,"amount_krw":"1100"}


def css(number, month="2026-11"):
    return {"invoice_number":number,"invoice_month":month,"amount_krw":"1,100 KRW"}


def extracted(number, collected=OLD, received="2026-10-20T10:00:00+00:00"):
    return {"invoice_number":number,"received_at":received,
            "extracted_at_utc":collected,"validation_status":"FILENAME_PARSED",
            "ingest_key":"synthetic-only"}


def audit(status="SCAN_COMPLETE",time=SCAN):
    return [{"year":"2026","status":status,"last_run_utc":time}]


class InvoiceFreshnessTests(unittest.TestCase):
    def test_classifies_2026_gap_blank_month_and_new_after_scan(self):
        q=[qq("209126000001"),qq("209126000002","")]
        c=[css("209126000003")]
        x=[extracted("209126000001"),extracted("209126000002"),
           extracted("209126000004"),extracted("209126000005",NEW,
                  received="2026-11-22T18:01:37+08:00")]
        r=monitor.summarize(q,c,x,audit(),now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["qq_to_css_gap_count"],1)
        self.assertEqual(r["qq_gap_in_extract_count"],1)
        self.assertEqual(r["extract_not_in_any_qq_or_css_count"],2)
        self.assertEqual(r["extract_unlinked_before_last_scan"],1)
        self.assertEqual(r["extract_unlinked_after_last_scan"],1)
        self.assertEqual(r["qq_blank_month_with_extract"],1)
        self.assertEqual(r["extract_linked_to_qq_non_2026_scope"],1)
        self.assertEqual(r["source_event_at"],"2026-11-22T10:01:37+00:00")
        self.assertIsNone(r["sink_updated_at"])
        self.assertEqual(r["business_writes"],0)
        self.assertFalse(r["canonical_writer_enabled"])

    def test_post_scan_new_record_is_pending_not_sink_lag(self):
        q=[qq("209126000001")]
        c=[css("209126000001")]
        x=[extracted("209126000003", NEW,
                  received="2026-11-22T18:01:37+08:00")]
        r=monitor.summarize(q,c,x,audit(),now=NOW)
        self.assertEqual(r["status"],"NOT_VERIFIED")
        self.assertEqual(r["extract_unlinked_before_last_scan"],0)
        self.assertEqual(r["extract_unlinked_after_last_scan"],1)
        self.assertNotEqual(r["status"],"SINK_LAG")

    def test_matching_sources_pass_without_inventing_sink_update(self):
        q=[qq("209126000001")]
        c=[css("209126000001")]
        x=[extracted("209126000001")]
        r=monitor.summarize(q,c,x,audit(),now=NOW)
        self.assertEqual(r["status"],"PASS")
        self.assertIsNone(r["sink_updated_at"])
        self.assertFalse(r["original_proof_per_invoice_persisted"])
        self.assertFalse(r["canonical_owner_approved"])

    def test_stale_backfill_is_separate_from_real_sink_lag(self):
        q=[qq("209126000001")]
        c=[css("209126000001")]
        x=[extracted("209126000001")]
        r=monitor.summarize(q,c,x,audit(time="2026-11-20T00:00:00+00:00"),now=NOW)
        self.assertEqual(r["status"],"STALE")

    def test_invalid_scan_or_header_fail_closed(self):
        with self.assertRaisesRegex(ValueError,"BACKFILL_SCAN_INCOMPLETE"):
            monitor.summarize([qq("209126000001")],[css("209126000001")],
                              [extracted("209126000001")],
                              audit(status="SCAN_PARTIAL"),now=NOW)
        with self.assertRaisesRegex(ValueError,"BACKFILL_AUDIT_SCHEMA_UNAVAILABLE"):
            monitor.summarize([qq("209126000001")],[css("209126000001")],
                              [extracted("209126000001")],[{}],now=NOW)

    def test_duplicate_source_id_is_blocked(self):
        with self.assertRaisesRegex(ValueError,"EXTRACT_DUPLICATE_NUMBER_REVIEW"):
            monitor.summarize([qq("209126000001")],[css("209126000001")],
                              [extracted("209126000001"),extracted("209126000001")],
                              audit(),now=NOW)

    def test_no_identifiers_or_amounts_in_aggregate_report(self):
        r=monitor.summarize([qq("209126000001")],[css("209126000002")],
                            [extracted("209126000003")],audit(),now=NOW)
        dump=json.dumps(r)
        self.assertNotIn("209126000001",dump)
        self.assertNotIn("209126000002",dump)
        self.assertNotIn("209126000003",dump)
        self.assertNotIn("1100",dump)
        self.assertNotIn("synthetic-only",dump)

    def test_invalid_or_future_collection_time_blocks(self):
        with self.assertRaisesRegex(ValueError,"SOURCE_TIMESTAMP_INVALID"):
            monitor.summarize([qq("209126000001")],[css("209126000001")],
                              [extracted("209126000001",collected="NA")],
                              audit(),now=NOW)
        with self.assertRaisesRegex(ValueError,"EXTRACT_CLOCK_SKEW"):
            monitor.summarize([qq("209126000001")],[css("209126000001")],
                              [extracted("209126000003",
                                         collected="2026-11-23T01:00:00+00:00")],
                              audit(),now=NOW)

    def test_source_older_than_last_scan_not_assumed_full_scan(self):
        r=monitor.summarize([qq("209126000001")],[css("209126000001")],
                            [extracted("209126000003", OLD)],audit(),now=NOW)
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["missing_count"],1)
        self.assertTrue(any("review" in x.lower() for x in r["notes"]))
        self.assertFalse(r["original_proof_per_invoice_persisted"])


if __name__ == "__main__":
    unittest.main()
