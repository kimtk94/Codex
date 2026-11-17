#!/usr/bin/env python3
"""Offline tests for read-only Feishu mail ledger integrity."""
import unittest
import io
from contextlib import redirect_stdout
from unittest import mock

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


    @staticmethod
    def run_readonly_audit(table_names, rows, fields=None):
        tables = [{"name": name, "table_id": "tbl" + str(i)}
                  for i, name in enumerate(table_names)]
        field_data = fields if fields is not None else [
            {"field_name": name, "type": 1} for name in q.FIELDS
        ]
        def list_records(path, token, action):
            if action == "audit_tables":
                return tables
            if action == "audit_records":
                return rows
            raise AssertionError("Unexpected query")
        output = io.StringIO()
        with mock.patch.object(q, "auth", return_value=("token", "/base")), \
             mock.patch.object(q, "list_all", side_effect=list_records), \
             mock.patch.object(q, "get_fields", return_value=field_data), \
             mock.patch.object(q, "api") as any_write, \
             redirect_stdout(output):
            audit.main()
            any_write.assert_not_called()
        return output.getvalue()

    def test_missing_business_tables_does_not_block_mail_integrity(self):
        result = self.run_readonly_audit(["QQ Mail Intake"], [record(1)])
        self.assertIn("MAIL_SINK_READBACK_PASS records=1", result)
        self.assertIn("BASE_SCHEMA_BLOCK missing_required=6 duplicated_required=0", result)
        self.assertIn("FEISHU_MAIL_AUDIT_PASS mail_only=1 business_catalog=BLOCK", result)

    def test_complete_business_catalog_passes_independently(self):
        result = self.run_readonly_audit(
            ["QQ Mail Intake", *sorted(audit.EXPECTED_BUSINESS_TABLES)], [record(1)])
        self.assertIn("BASE_SCHEMA_PASS missing_required=0 duplicated_required=0", result)
        self.assertIn("MAIL_SINK_READBACK_PASS records=1", result)

    def test_duplicated_business_table_fails_catalog_only(self):
        result = self.run_readonly_audit(["QQ Mail Intake", "Accounts", "Accounts"], [record(1)])
        self.assertIn("BASE_SCHEMA_BLOCK missing_required=5 duplicated_required=1", result)
        self.assertIn("MAIL_SINK_READBACK_PASS records=1", result)

    def test_missing_staging_table_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_STAGING_TABLE_MISSING"):
            self.run_readonly_audit(["Accounts"], [])

    def test_duplicate_staging_table_fails_closed(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_STAGING_TABLE_DUPLICATE"):
            self.run_readonly_audit(["QQ Mail Intake", "QQ Mail Intake"], [])

    def test_wrong_field_schema_fails_closed(self):
        fields = [{"field_name": name, "type": 1} for name in q.FIELDS
                  if name != "Mail Key"]
        with self.assertRaisesRegex(q.SafeError, "AUDIT_STAGING_FIELD_SCHEMA_MISMATCH"):
            self.run_readonly_audit(["QQ Mail Intake"], [record(1)], fields)

    def test_duplicate_staging_field_name_fails_closed(self):
        fields = [{"field_name": name, "type": 1} for name in q.FIELDS]
        fields.append({"field_name": "Mail Key", "type": 1})
        with self.assertRaisesRegex(q.SafeError, "AUDIT_STAGING_FIELD_SCHEMA_MISMATCH"):
            self.run_readonly_audit(["QQ Mail Intake"], [record(1)], fields)

    def test_duplicate_mail_key_still_blocks_even_when_catalog_missing(self):
        with self.assertRaisesRegex(q.SafeError, "AUDIT_DUPLICATE_MAIL_KEY"):
            self.run_readonly_audit(["QQ Mail Intake"], [record(1), record(1)])

    def test_ledger_fetch_error_not_a_false_pass(self):
        def fail_query(path, token, action):
            if action == "audit_tables":
                return [{"name": "QQ Mail Intake", "table_id": "tblA"}]
            raise q.SafeError("AUDIT_RECORD_SOURCE_UNAVAILABLE")
        with mock.patch.object(q, "auth", return_value=("token", "/base")), \
             mock.patch.object(q, "list_all", side_effect=fail_query), \
             mock.patch.object(q, "get_fields", return_value=[
                 {"field_name": name, "type": 1} for name in q.FIELDS
             ]):
            with self.assertRaisesRegex(q.SafeError, "AUDIT_RECORD_SOURCE_UNAVAILABLE"):
                audit.main()


if __name__ == "__main__":
    unittest.main()
