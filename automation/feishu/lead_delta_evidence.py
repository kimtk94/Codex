#!/usr/bin/env python3
"""Publish redacted, structured evidence for isolated Lead delta runs.

Reads aggregate-only process logs written by its own workflow. Never exports
Lead IDs, customer names, email addresses, Feishu tokens, or raw record data.
Distinguishes NO_NEW_DATA, PASS, READ_ONLY, STALE, SOURCE_UNAVAILABLE,
SINK_LAG, and BLOCK without treating a green CI job as data verification.
Evidence is retained in GitHub Actions artifacts, not emailed externally.
"""
import argparse
import datetime as dt
import json
import os
from pathlib import Path

ALLOWED_COUNTS = ("recontact", "planned", "review", "none")
ALLOWED_TIME_FIELDS = ("earliest_mail_checked_at", "latest_mail_checked_at",
                       "feishu_snapshot_at")
KNOWN_MARKERS = (
    "LEAD_DELTA_SOURCE_EVIDENCE=", "LEAD_DELTA_PLAN=",
    "LEAD_DELTA_READBACK_PASS=", "LEAD_DELTA_NO_NEW_DATA=1",
    "LEAD_DELTA_READ_ONLY_PASS=1", "LEAD_DELTA_FAILED=",
    "LEAD_DELTA_PREWRITE_SNAPSHOT_PASS=", "LEAD_DELTA_APPLY_PROGRESS=",
)

def marker_content(line, marker):
    if marker not in line:
        return None
    return line.split(marker, 1)[1].strip()

def parse_log(contents):
    """Parse only known non-PII metrics, no raw log lines in output."""
    result = {"source": None, "plan": None, "readback": None,
              "no_new_data": None, "read_only_pass": False,
              "failed_code": None, "prewrite_checked": False,
              "applied_batches": 0}
    for line in contents.splitlines():
        data = marker_content(line, "LEAD_DELTA_SOURCE_EVIDENCE=")
        if data is not None:
            payload = json.loads(data)
            result["source"] = {key: payload.get(key) for key in
                                (*ALLOWED_TIME_FIELDS, "records", "distinct_source_stamps")}
        data = marker_content(line, "LEAD_DELTA_PLAN=")
        if data is not None:
            payload = json.loads(data)
            result["plan"] = {
                "records": payload.get("records"),
                "pending_updates": payload.get("pending_updates"),
                "allowed_max": payload.get("allowed_max"),
                "counts_before": {k: payload.get("counts_before", {}).get(k)
                                  for k in ALLOWED_COUNTS},
            }
        data = marker_content(line, "LEAD_DELTA_READBACK_PASS=")
        if data is not None:
            payload = json.loads(data)
            result["readback"] = {
                "records": payload.get("records"),
                "changed": payload.get("changed"),
                "counts_after": {k: payload.get("counts_after", {}).get(k)
                                 for k in ALLOWED_COUNTS},
                "manual_selections_preserved": payload.get("manual_selections_preserved"),
                "other_tables_touched": payload.get("other_tables_touched"),
            }
        data = marker_content(line, "LEAD_DELTA_NO_NEW_DATA=1")
        if data is not None:
            payload = json.loads(data) if data.startswith("{") else {}
            result["no_new_data"] = {
                "checked": payload.get("checked"),
                "views_verified": payload.get("views_verified"),
                "writes": payload.get("writes"),
                "counts": {k: payload.get("counts", {}).get(k)
                           for k in ALLOWED_COUNTS},
            }
        if "LEAD_DELTA_READ_ONLY_PASS=1" in line:
            result["read_only_pass"] = True
        data = marker_content(line, "LEAD_DELTA_FAILED=")
        if data is not None:
            # No raw API text or PII in evidence. Record only the safe class.
            if "SOURCE_STALE" in data:
                result["failed_code"] = "SOURCE_STALE"
            elif "SOURCE_TIMESTAMP" in data or "EMPTY_SOURCE" in data:
                result["failed_code"] = "SOURCE_INVALID"
            elif "VIEW_IDS_MISMATCH" in data or "VIEW_FILTER_DRIFT" in data or "READBACK" in data:
                result["failed_code"] = "SINK_MISMATCH"
            elif "HTTP " in data or "Missing GitHub Actions secret" in data:
                result["failed_code"] = "SOURCE_UNAVAILABLE"
            elif "CONCURRENT" in data:
                result["failed_code"] = "CONCURRENT_CHANGE"
            elif "TOO_MANY_CHANGES" in data:
                result["failed_code"] = "BULK_CHANGE_BLOCKED"
            else:
                result["failed_code"] = "OTHER_BLOCKER"
        if "LEAD_DELTA_PREWRITE_SNAPSHOT_PASS=" in line:
            result["prewrite_checked"] = True
        if "LEAD_DELTA_APPLY_PROGRESS=" in line:
            result["applied_batches"] += 1
    return result

def status_of(parsed, phase):
    if parsed["failed_code"]:
        return {
            "SOURCE_STALE": "STALE",
            "SOURCE_INVALID": "SOURCE_UNAVAILABLE",
            "SOURCE_UNAVAILABLE": "SOURCE_UNAVAILABLE",
            "SINK_MISMATCH": "SINK_LAG",
        }.get(parsed["failed_code"], "BLOCK")
    if phase == "apply" and parsed["readback"]:
        rb = parsed["readback"]
        if (rb["manual_selections_preserved"] is True
                and rb["other_tables_touched"] is False):
            return "PASS"
        return "BLOCK"
    if phase == "apply" and parsed["no_new_data"]:
        n = parsed["no_new_data"]
        if n.get("writes") == 0 and n.get("views_verified") == 3:
            return "NO_NEW_DATA"
        return "BLOCK"
    if phase == "preview" and parsed["read_only_pass"]:
        return "READ_ONLY"
    return "BLOCK"

def evidence(preview_log, apply_log=None, env=None, now=None):
    env = env or {}
    now = now or dt.datetime.now(dt.timezone.utc)
    preview = parse_log(preview_log)
    apply = parse_log(apply_log) if apply_log is not None else None
    phase = "apply" if apply is not None else "preview"
    chosen = apply if apply is not None else preview
    status = status_of(chosen, phase)
    # Failure during preview must not be suppressed by an apparently successful apply.
    if preview["failed_code"] and status in ("PASS", "NO_NEW_DATA"):
        status = "BLOCK"
    return {
        "version": 1,
        "workflow": "Feishu Lead Action Queue Delta Refresh",
        "run_id": env.get("GITHUB_RUN_ID"),
        "run_attempt": env.get("GITHUB_RUN_ATTEMPT"),
        "commit_sha": env.get("GITHUB_SHA"),
        "run_url": ("https://github.com/" + env.get("GITHUB_REPOSITORY", "") +
                    "/actions/runs/" + env.get("GITHUB_RUN_ID", ""))
                    if env.get("GITHUB_REPOSITORY") and env.get("GITHUB_RUN_ID") else None,
        "verified_at": now.isoformat(),
        "result": status,
        "phase": phase,
        "source_type": "Feishu mirrored QQ Lead evidence timestamp",
        "independent_qq_or_sfdc_fetch_performed": False,
        "source": chosen.get("source") or preview.get("source"),
        "plan": chosen.get("plan") or preview.get("plan"),
        "readback": chosen.get("readback"),
        "no_new_data": chosen.get("no_new_data"),
        "read_only_verified": preview.get("read_only_pass"),
        "prewrite_snapshot_checked": chosen.get("prewrite_checked"),
        "applied_batches": chosen.get("applied_batches"),
        "error_class": chosen.get("failed_code") or preview.get("failed_code"),
        "lead_ids_or_customer_data_exported": False,
    }

def render_summary(e):
    counts = e.get("readback") and e["readback"].get("counts_after")
    if counts is None and e.get("no_new_data"):
        counts = e["no_new_data"]["counts"]
    if counts is None and e.get("plan"):
        counts = e["plan"]["counts_before"]
    counts = counts or {}
    source = e.get("source") or {}
    lines = [
        "## Feishu Lead Delta · evidence",
        "",
        "| 검증 항목 | 결과 |", "|---|---|",
        "| 판정 | **" + e["result"] + "** |",
        "| 수행 구분 | " + e["phase"] + " |",
        "| Lead 수 | " + str((e.get("plan") or {}).get("records") or "-") + " |",
        "| 변경 대상 | " + str((e.get("plan") or {}).get("pending_updates") or 0) + " |",
        "| 실제 반영 | " + str((e.get("readback") or {}).get("changed") or 0) + " |",
        "| 재연락 / 발송 예정 / 검토 대기 | " +
        " / ".join(str(counts.get(k, "-")) for k in ("recontact","planned","review")) + " |",
        "| QQ 메일 확인시각(Feishu 보관값) | " +
        str(source.get("earliest_mail_checked_at") or "-") + " |",
        "| Feishu 조회시각 | " + str(source.get("feishu_snapshot_at") or "-") + " |",
        "| 최종 검증시각 | " + str(e["verified_at"]) + " |",
        "",
        "개인정보/Lead ID 없이 집계 증거만 저장합니다. 원천 QQ·SFDC 직접 재조회가 아닌 Feishu 기준 증분 검증입니다.",
    ]
    if e.get("error_class"):
        lines.extend(["", "검증 실패 분류: " + e["error_class"]])
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", required=True)
    parser.add_argument("--apply")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    preview = Path(args.preview).read_text(encoding="utf-8") if Path(args.preview).exists() else ""
    applied = (Path(args.apply).read_text(encoding="utf-8")
               if args.apply and Path(args.apply).exists() else None)
    e = evidence(preview, applied, dict(os.environ))
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(e, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as stream:
            stream.write(render_summary(e))
    print("LEAD_DELTA_EVIDENCE_RESULT=" + e["result"], flush=True)
    print("LEAD_DELTA_EVIDENCE_FILE=" + str(target), flush=True)

if __name__ == "__main__":
    main()
