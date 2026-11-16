#!/usr/bin/env python3
"""Bounded read-only retrieval and triage of existing QQ/Feishu source probe evidence.

The existing css-live-freshness-evidence workflow reads original QQ IMAP UID sets
and original Feishu dated Sheets. This module reads ONLY that workflow's sanitized
JSON artifact from GitHub Actions; it performs no direct QQ/Feishu/SFDC/API writes.

A matching UID subset or Sheets projection is narrow scope evidence and NEVER
proves message MIME/body, original Tax Invoice issuance, Salesforce object saves,
bank receipts, or live Feishu Base KPI write/readback.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
from pathlib import Path
import urllib.parse
import urllib.request
import zipfile

REPO = "kimtk94/Codex"
WORKFLOW = "css-live-freshness-evidence.yml"
ARTIFACT = "css-authenticated-original-probes"
ARTIFACT_FILE = "css-authenticated-original-probes.json"
API = "https://api.github.com/repos/" + REPO
MAX_ZIP_BYTES = 2_000_000
MAX_JSON_BYTES = 256_000
MAX_AGE_HOURS = 12  # evidence review window, not source cadence
SIGNALS = frozenset({
    "SOURCE_AUDIT_SCOPED", "SOURCE_AUDIT_STALE", "SOURCE_AUDIT_NOT_FOUND",
    "SOURCE_AUDIT_IN_PROGRESS", "SOURCE_AUDIT_RUN_FAILED",
    "SOURCE_AUDIT_ARTIFACT_MISSING", "SOURCE_AUDIT_INVALID",
    "SOURCE_AUDIT_API_UNAVAILABLE",
})
CASES = {
    "SOURCE_AUDIT_STALE": (190, "monitor", "REFRESH_AUTHENTICATED_ORIGINAL_PROBES_READONLY"),
    "SOURCE_AUDIT_NOT_FOUND": (185, "monitor", "CHECK_AUTHENTICATED_PROBE_WORKFLOW_SCHEDULE"),
    "SOURCE_AUDIT_IN_PROGRESS": (65, "monitor", "WAIT_FOR_AUTHENTICATED_PROBE_RUN"),
    "SOURCE_AUDIT_RUN_FAILED": (195, "monitor", "INVESTIGATE_AUTHENTICATED_PROBE_WORKFLOW_FAILURE"),
    "SOURCE_AUDIT_ARTIFACT_MISSING": (190, "monitor", "REPAIR_AUTHENTICATED_PROBE_ARTIFACT"),
    "SOURCE_AUDIT_INVALID": (200, "monitor", "INVESTIGATE_INVALID_AUTHENTICATED_SOURCE_EVIDENCE"),
    "SOURCE_AUDIT_API_UNAVAILABLE": (190, "monitor", "RESTORE_AUTHENTICATED_EVIDENCE_API_ACCESS"),
}


def now_utc():
    return dt.datetime.now(dt.timezone.utc)


def as_utc(s):
    if not isinstance(s, str) or not s:
        raise ValueError("TIMESTAMP_MISSING")
    try:
        parsed = dt.datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("TIMESTAMP_INVALID") from exc
    if parsed.tzinfo is None:
        raise ValueError("TIMESTAMP_NAIVE")
    return parsed.astimezone(dt.timezone.utc)


def req(url: str, token: str):
    if not url.startswith(API + "/"):
        raise ValueError("OUT_OF_SCOPE_API")
    h = {"Accept": "application/vnd.github+json",
         "X-GitHub-Api-Version": "2022-11-28",
         "User-Agent": "codex-autonext-readonly-evidence"}
    if token:
        h["Authorization"] = "Bearer " + token
    return urllib.request.Request(url, headers=h, method="GET")


class StripTokenOnRedirect(urllib.request.HTTPRedirectHandler):
    """Do not forward the GitHub bearer token to third-party ZIP storage hosts."""
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        parsed = urllib.parse.urlsplit(newurl)
        if parsed.scheme != "https":
            raise ValueError("UNSAFE_REDIRECT_SCHEME")
        nxt = super().redirect_request(request, fp, code, msg, headers, newurl)
        if nxt is not None and parsed.netloc.lower() != urllib.parse.urlsplit(request.full_url).netloc.lower():
            for key in list(nxt.headers):
                if key.lower() in ("authorization", "cookie", "proxy-authorization"):
                    del nxt.headers[key]
            for key in list(nxt.unredirected_hdrs):
                if key.lower() in ("authorization", "cookie", "proxy-authorization"):
                    del nxt.unredirected_hdrs[key]
        return nxt


def github_json(url, token):
    with urllib.request.urlopen(req(url, token), timeout=20) as response:
        body = response.read(MAX_JSON_BYTES + 1)
    if len(body) > MAX_JSON_BYTES:
        raise ValueError("API_JSON_TOO_LARGE")
    return json.loads(body)


def github_zip(url, token):
    opener = urllib.request.build_opener(StripTokenOnRedirect)
    with opener.open(req(url, token), timeout=25) as response:
        if response.geturl().split(":", 1)[0] != "https":
            raise ValueError("UNSAFE_ARCHIVE_URL")
        data = response.read(MAX_ZIP_BYTES + 1)
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError("ARCHIVE_TOO_LARGE")
    return data


def read_artifact(data: bytes):
    if not isinstance(data, bytes) or len(data) > MAX_ZIP_BYTES:
        raise ValueError("INVALID_ARTIFACT_BYTES")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        matches = [n for n in zf.namelist()
                   if n == ARTIFACT_FILE or n == "audit-results/" + ARTIFACT_FILE]
        if len(matches) != 1:
            raise ValueError("PROBE_ARTIFACT_FILE_MISSING_OR_DUPLICATE")
        info = zf.getinfo(matches[0])
        if info.file_size > MAX_JSON_BYTES:
            raise ValueError("PROBE_ARTIFACT_CONTENT_TOO_LARGE")
        with zf.open(info) as handle:
            raw = handle.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError("PROBE_ARTIFACT_CONTENT_TOO_LARGE")
    return json.loads(raw)


def summarize_probe(raw: dict, *, observed_at=None):
    """Validate the known narrow schema and return ONLY safe status enums/countless proof."""
    if not isinstance(raw, dict) or raw.get("domain_business_pass") is not False:
        raise ValueError("PROBE_CANNOT_CERTIFY_BUSINESS_PASS")
    if raw.get("no_original_message_content_logged") is not True:
        raise ValueError("PROBE_PRIVACY_GUARD")
    if raw.get("sfdc_object_readback") != "NOT_CHECKED":
        raise ValueError("SFDC_READBACK_OUT_OF_SCOPE")
    at = as_utc(raw.get("checked_utc"))
    now = observed_at or now_utc()
    if now.tzinfo is None or at > now + dt.timedelta(minutes=10):
        raise ValueError("PROBE_TIME_IN_FUTURE")
    age = (now - at).total_seconds() / 3600
    if age > MAX_AGE_HOURS:
        return {"signal": "SOURCE_AUDIT_STALE", "qq_signal": "NOT_VERIFIED",
                "feishu_signal": "NOT_VERIFIED"}
    mail, feishu = raw.get("qq_mail"), raw.get("feishu_sheets")
    if not isinstance(mail, dict) or not isinstance(feishu, dict):
        raise ValueError("PROBE_SOURCE_BLOCKS_MISSING")
    allowed_status = {"SOURCE_PROBED", "SOURCE_UNAVAILABLE"}
    if mail.get("status") not in allowed_status or feishu.get("status") not in allowed_status:
        raise ValueError("PROBE_STATUS_UNKNOWN")
    qq_signal = "SOURCE_UNAVAILABLE" if mail["status"] == "SOURCE_UNAVAILABLE" else "UID_SCOPED_PASS"
    if mail["status"] == "SOURCE_PROBED":
        if mail.get("mime_body_verified") is not False:
            raise ValueError("PROBE_UNSAFE_MIME_CLAIM")
        if mail.get("recent_3d_state") not in ("PASS_UID_ONLY", "SINK_LAG") or (
                mail.get("scan_60d_state") not in ("PASS_UID_ONLY", "SINK_LAG")) or (
                mail.get("uid_coverage_state") not in ("PASS_UID_ONLY", "HISTORICAL_SINK_LAG")):
            raise ValueError("PROBE_INVALID_UID_COVERAGE")
        if mail["recent_3d_state"] == "SINK_LAG":
            qq_signal = "RECENT_UID_SINK_LAG"
        elif mail["scan_60d_state"] == "SINK_LAG":
            qq_signal = "SIXTY_DAY_UID_SINK_LAG"
        elif mail["uid_coverage_state"] == "HISTORICAL_SINK_LAG":
            qq_signal = "HISTORICAL_UID_SINK_LAG"
    f_signal = "SOURCE_UNAVAILABLE" if feishu["status"] == "SOURCE_UNAVAILABLE" else "PROJECTION_SCOPED_PASS"
    if feishu["status"] == "SOURCE_PROBED":
        if feishu.get("source_probe") != "PASS_ORIGINAL_READ" or feishu.get("scope") != "ORIGINAL_FEISHU_SHEETS_VS_GOOGLE_MIRROR_ONLY" or feishu.get("live_base_payment_certified") is not False:
            raise ValueError("PROBE_UNSAFE_FEISHU_SCOPE")
        if feishu.get("mirror_projection_status") not in ("PASS", "SINK_LAG"):
            raise ValueError("PROBE_INVALID_PROJECTION_STATUS")
        if feishu["mirror_projection_status"] == "SINK_LAG":
            f_signal = "PROJECTION_SINK_LAG"
    return {"signal": "SOURCE_AUDIT_SCOPED", "qq_signal": qq_signal,
            "feishu_signal": f_signal}


def original_probe_receipt(*, token=None, fetch_json=github_json, fetch_zip=github_zip,
                           observed_at=None):
    """Fetch latest completed/scheduled report; fail closed if recent probe is absent."""
    token = token if token is not None else os.getenv("GITHUB_TOKEN", "")
    now = observed_at or now_utc()
    base = {"schema_version": 1,
            "evidence_scope": "AUTHENTICATED_QQ_UID_AND_FEISHU_ORIGINAL_SHEETS_PROJECTION_ONLY",
            "business_source_sink_verification": "NOT_VERIFIED",
            "sfdc_object_readback": "NOT_CHECKED",
            "customer_data_writes": False, "auto_merge_pr": False}
    try:
        url = API + "/actions/workflows/" + WORKFLOW + "/runs?branch=main&per_page=10"
        response = fetch_json(url, token)
        records = response.get("workflow_runs")
        if not isinstance(records, list):
            raise ValueError("RUNS_SCHEMA_INVALID")
        records = [r for r in records if isinstance(r, dict)
                   and r.get("head_branch") == "main"
                   and r.get("event") != "pull_request"]
        for run in records:
            as_utc(run.get("created_at"))
            if type(run.get("id")) is not int or run["id"] < 1:
                raise ValueError("RUN_ID_INVALID")
        if not records:
            result = {"signal": "SOURCE_AUDIT_NOT_FOUND"}
        else:
            latest = max(records, key=lambda r: (as_utc(r["created_at"]), r["id"]))
            rid = latest["id"]
            if latest.get("status") != "completed":
                result = {"signal": "SOURCE_AUDIT_IN_PROGRESS"}
            elif latest.get("conclusion") != "success":
                result = {"signal": "SOURCE_AUDIT_RUN_FAILED"}
            else:
                artifacts = fetch_json(API + f"/actions/runs/{rid}/artifacts?per_page=100", token).get("artifacts")
                if not isinstance(artifacts, list):
                    raise ValueError("ARTIFACT_LIST_INVALID")
                found = [a for a in artifacts if a.get("name") == ARTIFACT and a.get("expired") is False]
                if len(found) != 1:
                    result = {"signal": "SOURCE_AUDIT_ARTIFACT_MISSING"}
                else:
                    aid = found[0].get("id")
                    if type(aid) is not int or aid < 1:
                        raise ValueError("ARTIFACT_ID_INVALID")
                    blob = fetch_zip(API + f"/actions/artifacts/{aid}/zip", token)
                    result = summarize_probe(read_artifact(blob), observed_at=now)
            result["run_id"] = rid
            result["run_url"] = f"https://github.com/{REPO}/actions/runs/{rid}"
    except (ValueError, TypeError, KeyError, zipfile.BadZipFile, json.JSONDecodeError) as exc:
        result = {"signal": "SOURCE_AUDIT_INVALID", "error_type": type(exc).__name__}
    except (OSError, TimeoutError) as exc:
        result = {"signal": "SOURCE_AUDIT_API_UNAVAILABLE", "error_type": type(exc).__name__}
    base.update(result)
    return base


def annotate_priority(report: dict, evidence: dict):
    """Rank investigation only. Never promote protected domain values to verified."""
    if not isinstance(evidence, dict) or evidence.get("signal") not in SIGNALS or evidence.get("business_source_sink_verification") != "NOT_VERIFIED":
        raise ValueError("UNTRUSTED_SOURCE_EVIDENCE")
    lookup = {x["domain"]: x for x in report["queue"]}
    if not {"mail", "feishu_bi", "monitor"}.issubset(lookup):
        raise ValueError("MISSING_AUDIT_DOMAINS")
    choices = []
    signal = evidence["signal"]
    if signal in CASES:
        choices.append(CASES[signal])
    if signal == "SOURCE_AUDIT_SCOPED":
        qs, fs = evidence.get("qq_signal"), evidence.get("feishu_signal")
        qmap = {
            "SOURCE_UNAVAILABLE": (190, "mail", "RESTORE_QQ_ORIGINAL_PROBE"),
            "RECENT_UID_SINK_LAG": (185, "mail", "INSPECT_QQ_RECENT_3D_UID_GAP"),
            "SIXTY_DAY_UID_SINK_LAG": (165, "mail", "INSPECT_QQ_60D_UID_GAP"),
            "HISTORICAL_UID_SINK_LAG": (115, "mail", "INSPECT_QQ_HISTORICAL_UID_GAP"),
            "UID_SCOPED_PASS": None,
        }
        fmap = {
            "SOURCE_UNAVAILABLE": (190, "feishu_bi", "RESTORE_FEISHU_ORIGINAL_SHEETS_PROBE"),
            "PROJECTION_SINK_LAG": (180, "feishu_bi", "RECONCILE_FEISHU_ORIGINAL_TO_MIRROR_PROJECTION"),
            "PROJECTION_SCOPED_PASS": None,
        }
        if qs not in qmap or fs not in fmap:
            raise ValueError("PROBE_SIGNAL_UNSUPPORTED")
        for item in (qmap[qs], fmap[fs]):
            if item is not None:
                choices.append(item)
    before = {entry["domain"]: i for i, entry in enumerate(report["queue"])}
    for priority, domain, next_action in choices:
        row = lookup[domain]
        if priority > row["priority"]:
            row["priority"] = priority
            row["next_safe_action"] = next_action
        row["business_source_checked"] = False
        row["business_sink_checked"] = False
        row["business_freshness"] = "NOT_VERIFIED"
    report["queue"].sort(key=lambda x: (-x["priority"], before[x["domain"]]))
    report["next_review"] = report["queue"][0]
    report["authenticated_probe_signal"] = signal
    report["qq_uid_signal"] = evidence.get("qq_signal", "NOT_VERIFIED")
    report["feishu_original_projection_signal"] = evidence.get("feishu_signal", "NOT_VERIFIED")
    report["authenticated_probe_run_url"] = evidence.get("run_url")
    report["business_source_sink_verification"] = "NOT_VERIFIED"
    report["auto_execute_business_writes"] = False
    report["auto_merge_pr"] = False
    return report


def emit_report(report: dict, path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    # The file is limited to canonical enum/status fields and validated GitHub run URL.
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    output = ("## Autonomous Next — authenticated source probe evidence\n"
              f"- Scope: QQ UID and Feishu original dated Sheets projection ONLY\n"
              f"- Evidence: **{report['signal']}**\n"
              f"- QQ: {report.get('qq_signal', 'NOT_VERIFIED')}\n"
              f"- Feishu: {report.get('feishu_signal', 'NOT_VERIFIED')}\n"
              "- Business source-to-sink acceptance: **NOT VERIFIED**\n"
              "- Source reads reused existing CI evidence; no customer data writes.\n")
    print(output)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as handle:
            handle.write(output)


if __name__ == "__main__":
    emit_report(original_probe_receipt(),
                Path("autonomous-next-triage/original-source-probes.json"))
