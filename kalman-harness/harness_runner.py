#!/usr/bin/env python3
"""Kalman read-only harness v1. No trading, DB, SSH, or deployment operations.

Only optional network activity: GitHub Actions REST GET for two allowlisted
workflows. Historical audit findings are kept separate from current evidence.
"""
import argparse
import json
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen

REPO = "kimtk94/Codex"
AUDIT_BRANCH = "audit/kalman-control-20261014"
WORKFLOWS = {
    "offline_quality": "kalman-audit-quality.yml",
    "server_readonly": "server-readonly-audit.yml",
}
MAX_CI_AGE_HOURS = 48
WORKSTREAMS = [
    ("00", "운영 통제·통합 관리", "P0", "변경 동결·프로덕션 승인 게이트 확인"),
    ("01", "미국 주식 LIVE", "P0", "LIVE 주문·포지션·중개사 명세 읽기 전용 대조"),
    ("02", "미국 주식 전략 연구", "P2", "전략 OOS/Walk-forward, 수수료·슬리피지 검사"),
    ("03", "암호화폐 Grid", "P2", "실제 체결·수수료·재고 기준 장기 백테스트"),
    ("04", "암호화폐 Regime·선물", "P2", "2020년 이후 OOS 및 레버리지 위험·청산 검사"),
    ("05", "데이터 수집·품질", "P1", "CRYPTO/GLOBAL TTL 프로듀서 원인 추적"),
    ("06", "Harness·AI 실험", "P1", "격리 CI 성공과 서버 LIVE 검증 결과를 분리"),
    ("07", "웹·Vercel·Neon", "P0", "과거 수익률 오류 및 웹 소스/SSO/alias 차단 해소"),
]
# Known audit findings are NOT current runtime observations. They can only be
# retired after explicit human-reviewed proof; no automated clearing.
KNOWN_BLOCKERS = {
    "00": ["release approval not granted; main/LIVE frozen"],
    "01": ["current broker holdings/orders and LIVE runtime SHA not independently attested"],
    "05": ["2026-10-14 audit: CRYPTO/GLOBAL READY records frequently expired by TTL"],
    "07": [
        "five historical Neon multi-entry net returns remain overstated",
        "active Vercel Git link points to unrelated research repository",
        "staging SSO/password protection was disabled at prior inspection",
        "MAIN API rewrites also affect US/KR consumer sites",
    ],
}
RESULTS = ("SUCCESS", "FAILURE", "STALE", "IN_PROGRESS", "NO_RUN", "UNAVAILABLE")

def utc_now():
    return datetime.now(timezone.utc)

def parse_utc(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone(timezone.utc) if dt.tzinfo else None
    except ValueError:
        return None

def request_latest(workflow, branch, token=None):
    """GET only, fixed allowlisted repository and workflow, small response."""
    if workflow not in WORKFLOWS.values():
        raise ValueError("workflow not allowlisted")
    url = ("https://api.github.com/repos/" + REPO + "/actions/workflows/"
           + quote(workflow, safe="") + "/runs?branch=" + quote(branch, safe="")
           + "&per_page=5")
    headers = {"Accept": "application/vnd.github+json",
               "User-Agent": "kalman-readonly-harness/1.0",
               "X-GitHub-Api-Version": "2022-11-28"}
    if token:
        headers["Authorization"] = "Bearer " + token
    with urlopen(Request(url, headers=headers, method="GET"), timeout=12) as resp:
        payload = json.load(resp)
    runs = payload.get("workflow_runs", [])
    for run in runs:
        if run.get("head_branch") == branch:
            return {
                "id": run.get("id"),
                "status": run.get("status"),
                "conclusion": run.get("conclusion"),
                "completed_at": run.get("updated_at"),
                "url": run.get("html_url"),
                "head_branch": run.get("head_branch"),
            }
    return None

def classify_run(run, now, ttl_hours=MAX_CI_AGE_HOURS):
    if run is None:
        return {"state": "NO_RUN", "age_hours": None}
    if run.get("status") != "completed":
        return {"state": "IN_PROGRESS", "age_hours": None}
    when = parse_utc(run.get("completed_at"))
    if when is None or when > now + timedelta(minutes=5):
        return {"state": "UNAVAILABLE", "age_hours": None}
    age = round((now - when).total_seconds() / 3600, 2)
    if run.get("conclusion") != "success":
        state = "FAILURE"
    elif age > ttl_hours:
        state = "STALE"
    else:
        state = "SUCCESS"
    return {"state": state, "age_hours": age}

def assemble(now, runs, errors=None, evidence_mode="github_get_only"):
    errors = errors or {}
    checks = {}
    for key, workflow in WORKFLOWS.items():
        branch = AUDIT_BRANCH if key == "offline_quality" else "main"
        run = runs.get(key)
        checks[key] = {
            "workflow": workflow,
            "branch": branch,
            "run": run,
            "error": errors.get(key),
            **classify_run(run, now),
        }
    tracks = []
    for ident, name, priority, action in WORKSTREAMS:
        blockers = KNOWN_BLOCKERS.get(ident, [])
        if blockers:
            status = "BLOCKED_REVIEW"
        elif ident == "06" and checks["offline_quality"]["state"] == "SUCCESS":
            status = "OFFLINE_CI_PASS_ONLY"
        else:
            status = "EVIDENCE_REQUIRED"
        tracks.append({
            "id": ident, "name": name, "priority": priority, "status": status,
            "historical_blockers": blockers, "next_action": action,
            "live_runtime_verified": False,
        })
    return {
        "schema_version": "kalman-harness-1.0",
        "generated_at_utc": now.isoformat().replace("+00:00", "Z"),
        "evidence_mode": evidence_mode,
        "historical_audit_cutoff": "2026-10-15",
        "github_checks": checks,
        "workstreams": tracks,
        "live_runtime_verified": False,
        "broker_reconciled": False,
        "production_release_authorized": False,
        "trading_mutations_performed": False,
        "next_priority": [
            "P0: read-only broker/server provenance and LIVE config reconciliation",
            "P0: resolve five incorrect historical multi-entry net returns with evidence",
            "P0: attest Vercel MAIN/US/KR aliases, staging SSO and Git source",
            "P1: fix CRYPTO/GLOBAL TTL computation without treating READY as FRESH",
            "P1: connect sanitized, authorized server audit snapshots to this harness",
        ],
        "limitations": [
            "A green offline CI result is NOT a verified LIVE broker or deployment state.",
            "Historical blockers are not automatically cleared by successful tests.",
            "Only GitHub workflow metadata is polled. No secret, order or personal account data is fetched.",
            "Scheduled GitHub Actions jobs run only after the workflow exists on the default branch.",
        ],
    }

def as_markdown(report):
    lines = [
        "# Kalman Harness | Read-only control report",
        "",
        "Generated (UTC): " + report["generated_at_utc"],
        "",
        "**LIVE verified: NO | Release authorized: NO | Writes: NONE**",
        "",
        "## Current GitHub Actions evidence",
        "",
        "| Check | Result | Age (hours) | Run |",
        "|---|---|---:|---|",
    ]
    for key, rec in report["github_checks"].items():
        r = rec["run"] or {}
        link = r.get("url") or "-"
        age = rec["age_hours"]
        lines.append("| " + key + " | " + rec["state"] + " | " +
                     (str(age) if age is not None else "-") + " | " + link + " |")
    lines += ["", "## Workstreams", "",
              "| ID | Workstream | Priority | Status | Next action |",
              "|---|---|---|---|---|"]
    for t in report["workstreams"]:
        lines.append("| " + t["id"] + " | " + t["name"] + " | " +
                     t["priority"] + " | " + t["status"] + " | " +
                     t["next_action"] + " |")
    lines += ["", "## Unresolved historical blockers", ""]
    for t in report["workstreams"]:
        for blocker in t["historical_blockers"]:
            lines.append("- " + t["id"] + ": " + blocker)
    lines += ["", "## Release boundary", "",
              "Offline PASS does not unlock deployments or trades. "
              "Independent current evidence and explicit operator approval are required.",
              "", "## Evidence limitations", ""]
    lines += ["- " + s for s in report["limitations"]]
    return "\n".join(lines) + "\n"

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", default="kalman-harness/out")
    parser.add_argument("--no-network", action="store_true")
    parser.add_argument("--fixture", help="JSON mapping workflow keys to sanitized run metadata")
    parser.add_argument("--now", help="UTC timestamp for deterministic local tests")
    args = parser.parse_args()
    now = parse_utc(args.now) if args.now else utc_now()
    if now is None:
        parser.error("--now must include a UTC offset")
    runs, errors = {}, {}
    if args.fixture:
        with open(args.fixture, encoding="utf-8") as f:
            source = json.load(f)
        if not isinstance(source, dict):
            parser.error("--fixture must contain a JSON object")
        runs = {k: source.get(k) for k in WORKFLOWS}
        mode = "local_fixture_nonlive"
    elif args.no_network:
        mode = "offline_no_evidence"
    else:
        mode = "github_get_only"
        for key, workflow in WORKFLOWS.items():
            branch = AUDIT_BRANCH if key == "offline_quality" else "main"
            try:
                runs[key] = request_latest(workflow, branch, os.getenv("GITHUB_TOKEN"))
            except Exception as exc:
                # Fail closed while preserving a compact non-sensitive error.
                runs[key] = None
                errors[key] = type(exc).__name__
    report = assemble(now, runs, errors, mode)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=True)
    (output / "status.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "STATUS.md").write_text(as_markdown(report), encoding="utf-8")
    print(json.dumps({
        "status": "REPORT_WRITTEN",
        "mode": mode,
        "offline_quality": report["github_checks"]["offline_quality"]["state"],
        "server_readonly": report["github_checks"]["server_readonly"]["state"],
        "workstreams": len(report["workstreams"]),
        "release_authorized": False,
    }, sort_keys=True))

if __name__ == "__main__":
    main()
