#!/usr/bin/env python3
"""Read-only direct historical Feishu table ID probe tests."""
import io
import unittest
from contextlib import redirect_stdout
from unittest import mock

import sales_base_historic_direct_probe as probe
import qq_mail_ingest as q
from setup_sales_web import EXPECTED_BASE


class HistoricDirectProbeTests(unittest.TestCase):
    def test_legacy_id_fingerprints_verified(self):
        probe.validate_ids()

    def test_missing_code_classified_without_declaring_deletion(self):
        self.assertEqual(probe.classify_error("metadata_CODE_1254041"),
                         "API_TABLE_ID_NOT_FOUND")
        self.assertEqual(probe.classify_error("metadata_CODE_1254004"),
                         "API_TABLE_ID_NOT_FOUND")

    def test_permission_distinct_from_missing(self):
        self.assertEqual(probe.classify_error("metadata_CODE_1254302"),
                         "API_PERMISSION_DENIED")
        self.assertEqual(probe.classify_error("metadata_HTTP_403"),
                         "HTTP_PERMISSION_OR_POLICY")
        self.assertEqual(probe.classify_error("metadata_HTTP_404"),
                         "HTTP_NOT_FOUND_OR_ROUTE")
        self.assertEqual(probe.classify_error("metadata_NETWORK_ERROR"),
                         "OTHER_API_ERROR")

    def test_direct_request_metadata_only_and_bounded(self):
        seen = []
        def read_fields(token, path):
            seen.append(path)
            return [{"field_name": "fake"}]
        with mock.patch.object(q, "get_fields", side_effect=read_fields), \
             mock.patch.object(q, "api") as api:
            result = probe.probe_field_metadata("token", "/base")
            api.assert_not_called()
        self.assertEqual(len(seen), 7)
        self.assertTrue(all("/tables/" in path for path in seen))
        self.assertTrue(all("/records" not in path for path in seen))
        self.assertTrue(all(s == "API_FIELDS_ACCESSIBLE" for s in result.values()))

    def test_direct_api_missing_is_fail_closed(self):
        def fetch_fields(token, path):
            if path.endswith(probe.HISTORIC_IDS["MAIL"]):
                return [{"field_name": "Mail Key"}]
            raise q.SafeError("field_list_CODE_1254041")
        out = io.StringIO()
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": EXPECTED_BASE}), \
             mock.patch.object(q, "auth", return_value=("token", "/base")), \
             mock.patch.object(q, "get_fields", side_effect=fetch_fields), \
             redirect_stdout(out):
            with self.assertRaisesRegex(q.SafeError, "HISTORIC_BUSINESS_TABLES_DIRECT_ACCESS_BLOCK"):
                probe.main()
        self.assertIn("HISTORIC_TABLE_DIRECT_MAIL=API_FIELDS_ACCESSIBLE", out.getvalue())
        self.assertIn("HISTORIC_TABLE_DIRECT_ACCOUNTS=API_TABLE_ID_NOT_FOUND", out.getvalue())
        self.assertIn("writes=0", out.getvalue())

    def test_wrong_base_refused_prior_to_auth(self):
        with mock.patch.dict("os.environ", {"FEISHU_BASE_APP_TOKEN": "INVALID"}), \
             mock.patch.object(q, "auth") as auth:
            with self.assertRaisesRegex(q.SafeError, "HISTORIC_DIRECT_PROBE_WRONG_BASE"):
                probe.main()
            auth.assert_not_called()


if __name__ == "__main__":
    unittest.main()
