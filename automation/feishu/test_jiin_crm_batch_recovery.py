#!/usr/bin/env python3
"""Feishu HTTP-400 recovery must never silently skip a CRM message."""
import unittest
from unittest import mock
import jiin_crm_full_scan as f


class BatchRecoveryTests(unittest.TestCase):
    @staticmethod
    def row(uid, body="normal"):
        return {"Mail Key": "hash-%d" % uid, "Subject": "Contract Created",
                "Body Excerpt": body, "From": "crm@novogene.com"}

    def test_rejected_large_batches_are_bisected_and_all_persisted(self):
        stored = {}
        def api(method, path, token, data=None, action=""):
            rows = [r["fields"] for r in data["records"]]
            if len(rows) > 2:
                raise f.SafeError("crm_scan_batch_create_HTTP_400")
            result = []
            for row in rows:
                key = row["Mail Key"]
                self.assertNotIn(key, stored)
                stored[key] = "rec-" + key
                result.append({"record_id": stored[key]})
            return {"records": result}
        def readback(path, token, label):
            return [{"record_id": ident, "fields": {"Mail Key": key}}
                    for key, ident in stored.items()]
        indexed = {}
        rows = [self.row(i) for i in range(1, 26)]
        with mock.patch.object(f, "api", side_effect=api), mock.patch.object(
                f, "list_all", side_effect=readback):
            saved = f.persist_batch("tok", "path", rows, indexed)
        self.assertEqual(saved, 25)
        self.assertEqual(len(indexed), 25)
        self.assertEqual(len(stored), 25)

    def test_400_with_committed_row_is_reconciled_before_retry(self):
        stored = {}
        called = 0
        def api(method, path, token, data=None, action=""):
            nonlocal called
            called += 1
            rows = [r["fields"] for r in data["records"]]
            if called == 1:
                stored[rows[0]["Mail Key"]] = "rec-first"
                raise f.SafeError("crm_scan_batch_create_HTTP_400")
            self.assertEqual([x["Mail Key"] for x in rows], ["hash-2"])
            stored["hash-2"] = "rec-second"
            return {"records": [{"record_id": "rec-second"}]}
        def readback(path, token, label):
            return [{"record_id": v, "fields": {"Mail Key": k}} for k, v in stored.items()]
        indexed = {}
        with mock.patch.object(f, "api", side_effect=api), mock.patch.object(
                f, "list_all", side_effect=readback):
            created = f.persist_batch("tok", "path", [self.row(1), self.row(2)], indexed)
        self.assertEqual(created, 1)
        self.assertEqual(len(indexed), 2)
        self.assertEqual(called, 2)

    def test_invalid_singleton_control_char_only_is_repaired(self):
        row = self.row(1, "a\x00b")
        def api(method, path, token, data=None, action=""):
            if action == "crm_scan_batch_create":
                raise f.SafeError("crm_scan_batch_create_HTTP_400")
            self.assertEqual(action, "crm_scan_control_fallback")
            self.assertEqual(data["records"][0]["fields"]["Body Excerpt"], "a b")
            return {"records": [{"record_id": "stored-1"}]}
        indexed = {}
        with mock.patch.object(f, "api", side_effect=api), mock.patch.object(
                f, "list_all", return_value=[]):
            count = f.persist_batch("tok", "path", [row], indexed)
        self.assertEqual(count, 1)
        self.assertEqual(indexed["hash-1"], "stored-1")

    def test_singleton_without_invalid_controls_fails_closed(self):
        with mock.patch.object(f, "api", side_effect=f.SafeError(
                "crm_scan_batch_create_HTTP_400")), mock.patch.object(
                f, "list_all", return_value=[]):
            with self.assertRaisesRegex(f.SafeError, "SINGLE_ROW_400_REQUIRES_REVIEW"):
                f.persist_batch("tok", "path", [self.row(1)], {})
    
    def test_unrelated_write_error_is_not_masked(self):
        with mock.patch.object(f, "api", side_effect=f.SafeError(
                "crm_scan_batch_create_CODE_1254291")), mock.patch.object(
                f, "list_all") as list_all:
            with self.assertRaisesRegex(f.SafeError, "1254291"):
                f.persist_batch("tok", "path", [self.row(1)], {})
            list_all.assert_not_called()

    def test_duplicate_record_in_readback_refused(self):
        duplicates = [{"record_id": "r1", "fields": {"Mail Key": "hash-1"}},
                      {"record_id": "r2", "fields": {"Mail Key": "hash-1"}}]
        with mock.patch.object(f, "api", side_effect=f.SafeError(
                "crm_scan_batch_create_HTTP_400")), mock.patch.object(
                f, "list_all", return_value=duplicates):
            with self.assertRaisesRegex(f.SafeError, "DUPLICATE_OR_MISSING_ID"):
                f.persist_batch("tok", "path", [self.row(1)], {})

    def test_no_recreate_when_all_keys_previously_saved(self):
        with mock.patch.object(f, "api") as api:
            result = f.persist_batch("tok", "path", [self.row(1)], {"hash-1": "rec"})
        self.assertEqual(result, 0)
        api.assert_not_called()

    def test_valid_tab_newline_carriage_return_preserved(self):
        cleaned, changed = f._remove_invalid_controls(self.row(1, "a\tb\nc\rd"))
        self.assertEqual(changed, 0)
        self.assertEqual(cleaned["Body Excerpt"], "a\tb\nc\rd")


if __name__ == "__main__":
    unittest.main()
