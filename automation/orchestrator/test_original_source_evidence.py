"""Offline tests for authenticated QQ/Feishu artifact routing. Never access the network."""
import datetime as dt
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import urllib.request
import zipfile

import original_source_evidence as ose
import priority

NOW = dt.datetime(2026, 11, 16, 12, 57, tzinfo=dt.timezone.utc)


def sample(checked="2026-11-16T12:45:00+00:00"):
    return {
        "checked_utc": checked,
        "no_original_message_content_logged": True,
        "domain_business_pass": False,
        "sfdc_object_readback": "NOT_CHECKED",
        "qq_mail": {
            "status": "SOURCE_PROBED", "uid_coverage_state": "PASS_UID_ONLY",
            "recent_3d_state": "PASS_UID_ONLY", "scan_60d_state": "PASS_UID_ONLY",
            "mime_body_verified": False,
            "private_subject": "NEVER_EXPORT_THIS",
        },
        "feishu_sheets": {
            "status": "SOURCE_PROBED", "source_probe": "PASS_ORIGINAL_READ",
            "scope": "ORIGINAL_FEISHU_SHEETS_VS_GOOGLE_MIRROR_ONLY",
            "mirror_projection_status": "PASS", "live_base_payment_certified": False,
            "private_customer_name": "NEVER_EXPORT_THIS",
        },
    }


def zipped(payload):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("audit-results/css-authenticated-original-probes.json",
                         json.dumps(payload))
    return out.getvalue()


def mock_fetch(outcome="success", probe=None, *, created_at="2026-11-16T12:40:00Z"):
    calls = []
    def json_get(url, token):
        calls.append(url)
        if "/actions/workflows/" in url:
            return {"workflow_runs": [
                {"id": 55, "head_branch": "main", "event": "schedule",
                 "created_at": created_at, "status": "completed",
                 "conclusion": outcome},
                {"id": 56, "head_branch": "feature", "event": "pull_request",
                 "created_at": "2026-11-16T13:00:00Z", "status": "completed",
                 "conclusion": "success"},
            ]}
        if "/actions/runs/" in url:
            return {"artifacts": [{"id": 88, "name": ose.ARTIFACT, "expired": False}]}
        raise AssertionError("Out of scope request: " + url)
    def zip_get(url, token):
        calls.append(url)
        return zipped(probe or sample())
    return json_get, zip_get, calls


def priority_report():
    def fake(url, token):
        return {"workflow_runs": [{
            "id": 40, "head_branch": "main", "event": "schedule",
            "created_at": "2026-11-16T10:00:00Z",
            "status": "completed", "conclusion": "success",
        }]}
    return priority.build_priority(priority.load_policy(), fetch=fake)


class OriginalEvidenceTests(unittest.TestCase):
    def test_valid_source_probe_remains_narrow_scope_not_full_business_pass(self):
        j, z, calls = mock_fetch()
        receipt = ose.original_probe_receipt(token="dummy", fetch_json=j,
                                              fetch_zip=z, observed_at=NOW)
        self.assertEqual("SOURCE_AUDIT_SCOPED", receipt["signal"])
        self.assertEqual("UID_SCOPED_PASS", receipt["qq_signal"])
        self.assertEqual("PROJECTION_SCOPED_PASS", receipt["feishu_signal"])
        self.assertFalse(receipt["customer_data_writes"])
        self.assertEqual("NOT_VERIFIED", receipt["business_source_sink_verification"])
        self.assertEqual(3, len(calls))
        self.assertEqual("https://github.com/kimtk94/Codex/actions/runs/55", receipt["run_url"])
        self.assertNotIn("NEVER_EXPORT_THIS", json.dumps(receipt))

    def test_recent_qq_uid_gap_is_prioritized_over_ci_success(self):
        s = sample()
        s["qq_mail"]["recent_3d_state"] = "SINK_LAG"
        receipt = ose.summarize_probe(s, observed_at=NOW)
        report = ose.annotate_priority(priority_report(), receipt)
        self.assertEqual("mail", report["next_review"]["domain"])
        self.assertEqual("INSPECT_QQ_RECENT_3D_UID_GAP", report["next_review"]["next_safe_action"])
        self.assertEqual("NOT_VERIFIED", report["business_source_sink_verification"])

    def test_feishu_original_source_outage_is_prioritized(self):
        s = sample()
        s["feishu_sheets"] = {"status": "SOURCE_UNAVAILABLE", "error_type": "RuntimeError"}
        report = ose.annotate_priority(priority_report(), ose.summarize_probe(s, observed_at=NOW))
        self.assertEqual("feishu_bi", report["next_review"]["domain"])
        self.assertEqual("RESTORE_FEISHU_ORIGINAL_SHEETS_PROBE", report["next_review"]["next_safe_action"])

    def test_source_failure_is_not_zero_new_data(self):
        s = sample()
        s["qq_mail"] = {"status": "SOURCE_UNAVAILABLE"}
        out = ose.summarize_probe(s, observed_at=NOW)
        self.assertEqual("SOURCE_UNAVAILABLE", out["qq_signal"])
        self.assertEqual("RESTORE_QQ_ORIGINAL_PROBE",
                         ose.annotate_priority(priority_report(), out)["next_review"]["next_safe_action"])

    def test_stale_report_blocks_scoped_uid_success(self):
        s = sample(checked="2026-11-15T00:00:00Z")
        out = ose.summarize_probe(s, observed_at=NOW)
        self.assertEqual("SOURCE_AUDIT_STALE", out["signal"])
        self.assertEqual("monitor", ose.annotate_priority(priority_report(), out)["next_review"]["domain"])
        self.assertEqual("NOT_VERIFIED", out["qq_signal"])

    def test_no_latest_main_run_is_missing_not_pass(self):
        def fetch(url, token):
            return {"workflow_runs": []}
        report = ose.original_probe_receipt(token="dummy", fetch_json=fetch,
                                            observed_at=NOW)
        self.assertEqual("SOURCE_AUDIT_NOT_FOUND", report["signal"])
        self.assertEqual("monitor", ose.annotate_priority(priority_report(), report)["next_review"]["domain"])

    def test_latest_run_failed_not_hidden_by_old_success(self):
        j, z, calls = mock_fetch(outcome="failure")
        report = ose.original_probe_receipt(token="dummy", fetch_json=j, fetch_zip=z,
                                            observed_at=NOW)
        self.assertEqual("SOURCE_AUDIT_RUN_FAILED", report["signal"])
        self.assertEqual(1, len(calls))

    def test_api_failure_cannot_become_no_new_data(self):
        def failure(url, token):
            raise OSError("SECRET_ERROR_STRING")
        report = ose.original_probe_receipt(token="dummy", fetch_json=failure,
                                            observed_at=NOW)
        self.assertEqual("SOURCE_AUDIT_API_UNAVAILABLE", report["signal"])
        self.assertNotIn("SECRET_ERROR_STRING", json.dumps(report))

    def test_unknown_privileged_claims_rejected(self):
        for key, value in (("domain_business_pass", True),
                           ("sfdc_object_readback", "PASS"),
                           ("no_original_message_content_logged", False)):
            s = sample()
            s[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                ose.summarize_probe(s, observed_at=NOW)
        s = sample()
        s["qq_mail"]["mime_body_verified"] = True
        with self.assertRaises(ValueError):
            ose.summarize_probe(s, observed_at=NOW)
        s = sample()
        s["feishu_sheets"]["live_base_payment_certified"] = True
        with self.assertRaises(ValueError):
            ose.summarize_probe(s, observed_at=NOW)

    def test_bounded_zip_rejects_wrong_file_or_excessive_bytes(self):
        with self.assertRaises(ValueError):
            ose.read_artifact(b"x" * (ose.MAX_ZIP_BYTES + 1))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as z:
            z.writestr("private-customer-data.txt", "danger")
        with self.assertRaises(ValueError):
            ose.read_artifact(stream.getvalue())

    def test_strip_token_on_cross_host_redirect(self):
        req = urllib.request.Request(ose.API + "/actions/artifacts/11/zip",
                                     headers={"Authorization": "Bearer SECRET"})
        handler = ose.StripTokenOnRedirect()
        next_req = handler.redirect_request(req, None, 302, "Found", {},
                                            "https://objects.githubusercontent.com/archive.zip")
        self.assertFalse(any(k.lower() == "authorization" for k in next_req.headers))
        with self.assertRaises(ValueError):
            handler.redirect_request(req, None, 302, "Found", {},
                                     "http://unsafe.example.com/archive.zip")

    def test_sanitized_receipt_written_without_raw_personal_details(self):
        j, z, _ = mock_fetch()
        report = ose.original_probe_receipt(token="dummy", fetch_json=j,
                                            fetch_zip=z, observed_at=NOW)
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "receipt.json"
            ose.emit_report(report, path)
            content = path.read_text(encoding="utf-8")
            self.assertNotIn("NEVER_EXPORT_THIS", content)
            self.assertIn("NOT_VERIFIED", content)
            self.assertIn("SOURCE_AUDIT_SCOPED", content)


if __name__ == "__main__":
    unittest.main()
