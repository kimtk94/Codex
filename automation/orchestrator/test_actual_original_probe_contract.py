"""Contract tests consuming the ACTUAL existing QQ/Feishu probe producer functions.

No QQ, Sheets, or network connections. Distinct from mocks that invent the
output schema: change in upstream real producer breaks this regression.
"""
import datetime as dt
import io
import json
from pathlib import Path
import sys
import unittest
import zipfile

# The audited producer is the code already running on main, not a duplicated
# fixture generator. This import only defines functions; no network operation.
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "automation" / "ops"))
import css_authenticated_original_probes as producer
import original_source_evidence as consumer
import priority

FIXED_NOW = dt.datetime(2026, 11, 16, 12, 0, tzinfo=dt.timezone.utc)


def producer_mail(*, recent_gap=False, sixty_day_gap=False, old_gap=False):
    folders = {
        "INBOX": {
            "folder": "INBOX", "uidvalidity": "100",
            "uids": ["10", "11", "12"],
            "recent_uids": ["12"],
            "scan_uids": ["11", "12"],
        },
        "SENT": {
            "folder": "Sent Messages", "uidvalidity": "101",
            "uids": ["20", "21"],
            "recent_uids": ["21"],
            "scan_uids": ["20", "21"],
        },
    }
    keys = ["INBOX|100|10", "INBOX|100|11", "INBOX|100|12",
            "Sent Messages|101|20", "Sent Messages|101|21"]
    if recent_gap:
        keys.remove("INBOX|100|12")
    if sixty_day_gap:
        keys.remove("INBOX|100|11")
    if old_gap:
        keys.remove("INBOX|100|10")
    report = producer.validate_mail_coverage(folders, keys)
    report["status"] = "SOURCE_PROBED"
    return report


def producer_feishu(*, drift=False):
    rows = [["Service", "Value"], ["eTax Invoice", "synthetic"]]
    original = {
        "sheet_id": "fake-tab-id",
        "source_date": "2026-11-16",
        "row_count": 1,
        "schema": "schema-v1",
        "projected_grid": rows,
    }
    manifest = {"id": "fake-tab-id", "date": "2026-11-16",
                "rows": 1, "schema": "schema-v1"}
    mirror = [["Service", "Value"],
              ["eTax Invoice", "synthetic-changed" if drift else "synthetic"]]
    projection = producer.compare_feishu_projection(original, manifest, mirror)
    return {
        "status": "SOURCE_PROBED", "source_probe": "PASS_ORIGINAL_READ",
        "mirror_projection_status": (
            "PASS" if projection["status"] == "PASS_SNAPSHOT_PROJECTION_ONLY"
            else "SINK_LAG"),
        "formats": {"eTax Invoice": projection},
        "scope": "ORIGINAL_FEISHU_SHEETS_VS_GOOGLE_MIRROR_ONLY",
        "live_base_payment_certified": False,
    }


def artifact_report(*, recent_gap=False, sixty_day_gap=False, old_gap=False, drift=False):
    return {
        "checked_utc": "2026-11-16T11:55:00+00:00",
        "no_original_message_content_logged": True,
        "qq_mail": producer_mail(recent_gap=recent_gap,
                                 sixty_day_gap=sixty_day_gap, old_gap=old_gap),
        "feishu_sheets": producer_feishu(drift=drift),
        "sfdc_object_readback": "NOT_CHECKED",
        "domain_business_pass": False,
        "private_customer": "DO_NOT_PROPAGATE_REAL_OR_SYNTHETIC_IDENTIFIERS",
    }


class ProducerConsumerContractTests(unittest.TestCase):
    def test_actual_qq_producer_output_schema_is_accepted(self):
        output = producer.validate_mail_coverage({
            "INBOX": {"folder": "INBOX", "uidvalidity": "2",
                      "uids": ["1"], "recent_uids": ["1"], "scan_uids": ["1"]},
            "SENT": {"folder": "Sent", "uidvalidity": "3",
                     "uids": ["2"], "recent_uids": ["2"], "scan_uids": ["2"]},
        }, ["INBOX|2|1", "Sent|3|2"])
        self.assertIs(output["mime_body_verified"], False)
        self.assertEqual("PASS_UID_ONLY", output["uid_coverage_state"])
        self.assertEqual("PASS_UID_ONLY", output["recent_3d_state"])
        self.assertEqual("PASS_UID_ONLY", output["scan_60d_state"])
        assessed = consumer.summarize_probe(artifact_report(), observed_at=FIXED_NOW)
        self.assertEqual("SOURCE_AUDIT_SCOPED", assessed["signal"])
        self.assertEqual("UID_SCOPED_PASS", assessed["qq_signal"])
        self.assertEqual("PROJECTION_SCOPED_PASS", assessed["feishu_signal"])
        self.assertEqual("NOT_VERIFIED", assessed["business_source_sink_verification"])

    def test_actual_qq_recent_uid_gap_is_classified(self):
        assessed = consumer.summarize_probe(
            artifact_report(recent_gap=True), observed_at=FIXED_NOW)
        self.assertEqual("RECENT_UID_SINK_LAG", assessed["qq_signal"])

    def test_actual_qq_60d_uid_gap_is_classified(self):
        assessed = consumer.summarize_probe(
            artifact_report(sixty_day_gap=True), observed_at=FIXED_NOW)
        self.assertEqual("SIXTY_DAY_UID_SINK_LAG", assessed["qq_signal"])

    def test_actual_qq_historical_uid_gap_is_classified(self):
        assessed = consumer.summarize_probe(
            artifact_report(old_gap=True), observed_at=FIXED_NOW)
        self.assertEqual("HISTORICAL_UID_SINK_LAG", assessed["qq_signal"])

    def test_actual_feishu_projection_drift_is_classified(self):
        payload = artifact_report(drift=True)
        self.assertEqual("SINK_LAG",
                         payload["feishu_sheets"]["formats"]["eTax Invoice"]["status"])
        assessed = consumer.summarize_probe(payload, observed_at=FIXED_NOW)
        self.assertEqual("PROJECTION_SINK_LAG", assessed["feishu_signal"])

    def test_actual_producer_output_survives_github_artifact_zip_and_remains_private(self):
        body = artifact_report(recent_gap=True, drift=True)
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("audit-results/css-authenticated-original-probes.json",
                        json.dumps(body))
        restored = consumer.read_artifact(stream.getvalue())
        assessed = consumer.summarize_probe(restored, observed_at=FIXED_NOW)
        self.assertEqual("RECENT_UID_SINK_LAG", assessed["qq_signal"])
        self.assertEqual("PROJECTION_SINK_LAG", assessed["feishu_signal"])
        self.assertNotIn("DO_NOT_PROPAGATE", json.dumps(assessed))

    def test_actual_producer_marks_original_vs_mirror_not_business_base_acceptance(self):
        self.assertIs(producer_feishu()["live_base_payment_certified"], False)
        self.assertIs(producer.compare_feishu_projection(
            {"sheet_id": "A", "source_date": "2026-11-16",
             "row_count": 1, "schema": "v1",
             "projected_grid": [["a"], ["b"]]},
            {"id": "A", "date": "2026-11-16", "rows": 1, "schema": "v1"},
            [["a"], ["b"]])["invoice_issue_dates_certified"], False)


if __name__ == "__main__":
    unittest.main()
