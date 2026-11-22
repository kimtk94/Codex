"""Synthetic-only redaction and readiness tests; never use live credentials."""
import json
import unittest
from automation.css_mail.qq_preview_diagnostic import classify_preview, summarize_uid_search_reply


class SafePreviewDiagnosticTests(unittest.TestCase):
    def test_pre_seed_failure_classifies_phase_and_known_error(self):
        raw="QQ_SAFE_STAGE=START\nQQ_SAFE_STAGE=SHEETS_AUTH_READY\n"
        stderr='Traceback:\nRuntimeError: BACKFILL_HEADER_MISMATCH invoice=SECRET_CUSTOMER-9019\n'
        report=classify_preview(1,raw,stderr)
        self.assertEqual(report["last_completed_stage"],"SHEETS_AUTH_READY")
        self.assertEqual(report["exception_code"],"BACKFILL_HEADER_MISMATCH")
        self.assertEqual(report["status"],"HOLD")
        self.assertNotIn("SECRET_CUSTOMER",json.dumps(report))

    def test_valid_preview_requires_exact_zero_write_marker(self):
        output="\n".join([
            "QQ_SAFE_STAGE=SOURCE_SCAN_FINISHED",
            "QQ_BACKFILL_PARSER_DIAGNOSTIC {\"KNOWN_UID_WITH_VALID_EVIDENCE\": 3, \"CLIENT_ID\": \"ACME\"} fallback_verified=0",
            "QQ_BACKFILL_PROOF_FIRST_PREVIEW year=2026 scanned=2 new_in_memory=0 would_update_cursor_folders=1 blocked=0 sheet_writes=0 cursor_writes=0",
            "QQ_BACKFILL_PREVIEW_ONLY_NOT_COMMITTED"])
        r=classify_preview(2,output,"")
        self.assertEqual(r["status"],"PASS")
        self.assertEqual(r["preview_counts"]["scanned"],2)
        self.assertEqual(r["reason_counts"],{"KNOWN_UID_WITH_VALID_EVIDENCE":3})
        self.assertEqual(r["exception_code"],"NONE")
        self.assertNotIn("CLIENT_ID",json.dumps(r))
        self.assertNotIn("ACME",json.dumps(r))

    def test_returncode_2_without_preview_never_passes(self):
        r=classify_preview(2,"QQ_SAFE_STAGE=IMAP_MAILBOXES_LISTED","")
        self.assertEqual(r["status"],"HOLD")
        self.assertEqual(r["exception_code"],"UNCLASSIFIED")

    def test_preview_marked_blocked_cannot_pass(self):
        txt="QQ_BACKFILL_PROOF_FIRST_PREVIEW year=2026 scanned=3 new_in_memory=0 would_update_cursor_folders=0 blocked=1 sheet_writes=0 cursor_writes=0\nQQ_BACKFILL_PREVIEW_ONLY_NOT_COMMITTED"
        self.assertEqual(classify_preview(2,txt,"")["status"],"HOLD")

    def test_known_sheet_http_error_is_abstracted(self):
        r=classify_preview(1,"QQ_SAFE_STAGE=SHEETS_AUTH_READY",
            'RuntimeError: SHEETS_403 { "customer":"PERSON_PRIVATE", "email":"person@sample.invalid" }')
        self.assertEqual(r["exception_code"],"SHEETS_HTTP_ERROR")
        self.assertNotIn("PERSON_PRIVATE",json.dumps(r))
        self.assertNotIn("sample.invalid",json.dumps(r))

    def test_unknown_exception_does_not_escape(self):
        r=classify_preview(1,"QQ_SAFE_STAGE=IMAP_AUTHENTICATED",
            "ValueError: User password SECRET123 and client bank 200053")
        self.assertEqual(r["exception_code"],"UNCLASSIFIED")
        self.assertEqual(r["exception_type"],"ValueError")
        self.assertNotIn("SECRET123",json.dumps(r))
        self.assertNotIn("200053",json.dumps(r))

    def test_invalid_stage_marker_not_reflected(self):
        r=classify_preview(1,"QQ_SAFE_STAGE=PRIVATE_EMAIL_customer@example.com\nQQ_SAFE_STAGE=START","")
        self.assertEqual(r["last_completed_stage"],"START")
        self.assertNotIn("customer@example.com",json.dumps(r))

    def test_unknown_reason_is_not_exposed(self):
        r=classify_preview(1,"QQ_BACKFILL_PARSER_DIAGNOSTIC "+
            json.dumps({"UNKNOWN_PRIVATE_VALUE":"SAMPLE_NAME",
                        "FETCH_FAILED":2, "AMOUNT_CONFLICT":1, "READ_UID":433}),
            "")
        self.assertEqual(r["reason_counts"],{"FETCH_FAILED":2,"AMOUNT_CONFLICT":1})
        self.assertNotIn("READ_UID",json.dumps(r))
        self.assertNotIn("SAMPLE_NAME",json.dumps(r))

    def test_cannot_pass_if_writes_detected_or_missing(self):
        for vals in ("sheet_writes=1 cursor_writes=0","sheet_writes=0",
                     "sheet_writes=0 cursor_writes=1"):
            txt=("QQ_BACKFILL_PROOF_FIRST_PREVIEW year=2026 scanned=1 new_in_memory=0 "
                 "would_update_cursor_folders=0 blocked=0 "+vals+
                 "\nQQ_BACKFILL_PREVIEW_ONLY_NOT_COMMITTED")
            self.assertEqual(classify_preview(2,txt,"")["status"],"HOLD")


    def test_search_response_uses_allowlisted_status_and_shape(self):
        cases = [
            ("OK", [b""], {"status_class":"OK","row_class":"BYTES"}),
            ("NO", None, {"status_class":"NO","row_class":"NON_SEQUENCE"}),
            ("BAD", [], {"status_class":"BAD","row_class":"EMPTY_SEQUENCE"}),
            ("CUSTOMER_private@invalid.example", [b"AMOUNT_1234"],
             {"status_class":"OTHER","row_class":"BYTES"}),
            ("OK", ["UID customer@example.com"],
             {"status_class":"OK","row_class":"FIRST_NOT_BYTES"}),
        ]
        for status, rows, expected in cases:
            observed = summarize_uid_search_reply(status, rows)
            self.assertEqual(observed, expected)
            payload = json.dumps(observed)
            self.assertNotIn("CUSTOMER", payload)
            self.assertNotIn("AMOUNT", payload)
            self.assertNotIn("customer@example.com", payload)


    def test_search_failure_is_reported_without_raw_identifiers(self):
        payload = {"folder_role":"OTHER", "folder_ordinal":3,
                   "criterion":"TAX", "status_class":"BAD",
                   "row_class":"EMPTY_SEQUENCE",
                   "folder":"SECRET_PERSONAL_FOLDER", "uid":9981,
                   "invoice":"SECRET_INVOICE"}
        text = "QQ_SAFE_STAGE=IMAP_MAILBOXES_LISTED\nQQ_SAFE_SEARCH_FAILURE " + json.dumps(payload)
        report = classify_preview(1, text, "RuntimeError: QQ_BACKFILL_SEARCH_UNAVAILABLE")
        self.assertEqual(report["search_failure"], {
            "folder_role":"OTHER", "folder_ordinal":3,
            "criterion":"TAX", "status_class":"BAD",
            "row_class":"EMPTY_SEQUENCE"})
        self.assertEqual(report["status"], "HOLD")
        self.assertNotIn("SECRET", json.dumps(report))
        self.assertNotIn("9981", json.dumps(report))

    def test_malformed_search_failure_is_not_echoed(self):
        for payload in (
            {"folder_role":"client@example.com", "folder_ordinal":2,
             "criterion":"ISSUED", "status_class":"NO", "row_class":"BYTES"},
            {"folder_role":"INBOX", "folder_ordinal":"PRIVATE_UID",
             "criterion":"ISSUED", "status_class":"NO", "row_class":"BYTES"},
        ):
            result=classify_preview(1,"QQ_SAFE_SEARCH_FAILURE "+json.dumps(payload),"")
            self.assertNotIn("search_failure", result)
            self.assertEqual(result["status"],"HOLD")

if __name__=="__main__":
    unittest.main()
