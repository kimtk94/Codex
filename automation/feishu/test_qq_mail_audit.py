#!/usr/bin/env python3
"""Offline tests for read-only Feishu mail ledger integrity."""
import unittest

import qq_mail_audit as audit
import qq_mail_ingest as q


def record(n, direction="INBOUND", **fields):
    values = {"Mail Key": f"{n:064x}", "Direction": direction, **fields}
    return {"record_id": "rec" + str(n), "fields": values}


class AuditTests(unittest.TestCase):
    def test_counts_real_mail_and_ignores_smoke(self):
        rows = [
            record(1, "INBOUND", **{"Message ID": "<a@x>", "Body Excerpt": "hi", "AMEA": "AMEA1234567"}),
            record(2, "OUTBOUND", **{"Message ID": "<b@x>", "H Project": "H209SC26065705"}),
            {"record_id": "smoke", "fields": {"Mail Key": q.SMOKE_KEY, "Direction": "SYSTEM"}},
        ]
        self.assertEqual(audit.summarize(rows), {
            "mail_total": 2, "inbound": 1, "outbound": 1, "smoke": 1,
            "message_ids": 2, "body_excerpts": 1, "amea": 1,
            "h_project": 1, "duplicate": 0,
        })

    def test_duplicate_key_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_DUPLICATE_MAIL_KEY"):
            audit.summarize([record(1), record(1)])

    def test_malformed_id_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_UNEXPECTED_MAIL_KEY_FORMAT"):
            audit.summarize([{"record_id": "recx", "fields": {
                "Mail Key": "bad", "Direction": "INBOUND"}}])

    def test_unexpected_direction_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_UNKNOWN_MAIL_DIRECTION"):
            audit.summarize([record(1, "SYSTEM")])

    def test_missing_key_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_MISSING_RECORD_ID_OR_MAIL_KEY"):
            audit.summarize([{"record_id": "recx", "fields": {"Direction": "INBOUND"}}])


if __name__ == "__main__":
    unittest.main()
