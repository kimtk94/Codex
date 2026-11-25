#!/usr/bin/env python3
"""Read-only GitHub Actions evidence scorecard for Kalman Daily20.

Operational PASS and research readiness are deliberately separate. No trade,
strategy promotion, Drive mutation, or credential echo is permitted.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

API = "https://api.github.com"
WORKFLOW = "kalman-daily20.yml"
REQUIRED_JOBS = ("contracts", "restore-drive-cache", "daily-research", "persist-google-drive")
MANDATORY_DIAGNOSTICS = (
    "DAILY20_REFRESH", "DAILY20_SOURCE_FINALITY", "DAILY20_PORTFOLIO",
    "DAILY20_FORWARD_SHADOW", "DAILY20_STABILITY",
)
DIAG_START = re.compile(r'\{"(DAILY20_[A-Z_]+)"\s*:')
DRIVE_READBACK = re.compile(r'"DAILY20_DRIVE_READBACK".*?"status"\s*:\s*"READBACK_VERIFIED"')
DRIVE_SESSION = re.compile(r'"DAILY20_DRIVE_READBACK".*?"session"\s*:\s*"(\d{4}-\d{2}-\d{2})"')


# A fixed, secret-free line emitted after actual Drive media re-download.
# It is deliberately simpler than the larger JSON, which can be log-masked.
FIRST_SEAL_CHECK = re.compile(
    r"DAILY20_FIRST_SEAL_CHECK_V1\s+"
    r"session=(?P<session>\d{4}-\d{2}-\d{2})\s+"
    r"status=(?P<status>[A-Z_]+)\s+"
    r"deep=(?P<deep>\d+)\s+"
    r"current=(?P<current>YES|NO)\s+"
    r"original_run=(?P<original_run>\d+|NONE)\s+"
    r"snapshot_sha=(?P<snapshot_sha>[a-f0-9]{64}|NONE)\b"
)
FIRST_NEW_SESSION = "2026-11-23"


def parse_first_seal_check(log: str) -> dict | None:
    matches = FIRST_SEAL_CHECK.findall(log)
    if len(matches) != 1:
        return None
    session, status, deep, current, original, sha = matches[0]
    return {
        "session": session, "status": status, "deep": int(deep),
        "current": current == "YES",
        "original_run": int(original) if original != "NONE" else None,
        "snapshot_sha256": sha if sha != "NONE" else None,
    }


def parse_diagnostics(log: str) -> dict:
    """Only parse emitted JSON diagnostic records; never persist raw logs."""
    diagnostics = {}
    for line in log.splitlines():
        match = DIAG_START.search(line)
        if not match:
            continue
        try:
            record = json.loads(line[match.start():])
        except json.JSONDecodeError:
            continue
        for key, value in record.items():
            if key.startswith("DAILY20_"):
                # Portfolio emits {"DAILY20_PORTFOLIO":"COMPLETE","scenarios":16}.
                diagnostics[key] = record if key == "DAILY20_PORTFOLIO" else value
    return diagnostics


def readback_session(log: str) -> str | None:
    m = DRIVE_SESSION.search(log.replace("\n", " "))
    return m.group(1) if m else None


def make_scorecard(run: dict, jobs: list[dict], research_log: str,
                   publisher_log: str, *, now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    started = datetime.fromisoformat(run["created_at"].replace("Z", "+00:00"))
    age_hours = round((now - started).total_seconds() / 3600, 2)
    by_name = {job.get("name"): job for job in jobs}
    diag = parse_diagnostics(research_log)
    problems = []
    for name in REQUIRED_JOBS:
        if by_name.get(name, {}).get("conclusion") != "success":
            problems.append(f"JOB_NOT_SUCCESS:{name}")
    if run.get("conclusion") != "success":
        problems.append("WORKFLOW_NOT_SUCCESS")
    if run.get("event") == "pull_request" or run.get("head_branch") != "main":
        problems.append("NON_MAIN_OR_PR_RUN")
    if age_hours < -1 or age_hours > 96:
        problems.append("RUN_STALE_OR_CLOCK_INVALID")
    for key in MANDATORY_DIAGNOSTICS:
        if key not in diag:
            problems.append(f"MISSING_DIAGNOSTIC:{key}")

    source = diag.get("DAILY20_SOURCE_FINALITY", {})
    refresh = diag.get("DAILY20_REFRESH", {})
    portfolio = diag.get("DAILY20_PORTFOLIO", {})
    forward = diag.get("DAILY20_FORWARD_SHADOW", {})
    stability = diag.get("DAILY20_STABILITY", {})
    if not isinstance(source, dict):
        source = {}
    if not isinstance(refresh, dict):
        refresh = {}
    if not isinstance(forward, dict):
        forward = {}
    if not isinstance(stability, dict):
        stability = {}
    if refresh.get("asset_count") != 26:
        problems.append("ASSET_COUNT_NOT_26")
    if source.get("required") != 26:
        problems.append("SOURCE_TARGET_COUNT_NOT_26")
    if forward.get("signals") != 20:
        problems.append("RESEARCH_SCORE_COUNT_NOT_20")
    if not isinstance(portfolio, dict) or portfolio.get("scenarios") != 16:
        problems.append("PORTFOLIO_SCENARIOS_NOT_16")

    matched = bool(DRIVE_READBACK.search(publisher_log.replace("\n", " ")))
    restored_session = readback_session(publisher_log)
    if not matched:
        problems.append("DRIVE_READBACK_MISSING")
    session = source.get("session")
    if not session or restored_session != session:
        problems.append("DRIVE_SESSION_MISMATCH")

    seal = parse_first_seal_check(publisher_log)
    replay_status = "LEGACY_AWAITING_GENUINE_NEW_SESSION"
    if isinstance(session, str) and session >= FIRST_NEW_SESSION:
        if seal is None:
            problems.append("FIRST_SEAL_READBACK_ATTESTATION_MISSING")
            replay_status = "NEW_SESSION_FIRST_SEAL_MISSING"
        elif (seal["session"] != session or seal["deep"] < 1
              or seal["current"] is not True
              or seal["snapshot_sha256"] is None
              or seal["status"] !=
                 "NEW_SESSION_ORIGINAL_INPUTS_AND_EVENTS_ATTESTED_RESEARCH_HOLD"):
            problems.append("NEW_SESSION_FIRST_SEAL_UNVERIFIED")
            replay_status = "NEW_SESSION_FIRST_SEAL_MISSING"
        elif forward.get("new_signals") == 20:
            if seal["original_run"] != run.get("id"):
                problems.append("FIRST_SEAL_ORIGINAL_RUN_ID_MISMATCH")
                replay_status = "FIRST_SEAL_ORIGINAL_RUN_ID_MISMATCH"
            else:
                replay_status = "FIRST_SEAL_REMOTE_READBACK_VERIFIED"
        elif forward.get("new_signals") == 0:
            if (seal["original_run"] is None
                    or not isinstance(run.get("id"), int)
                    or seal["original_run"] >= run["id"]):
                problems.append("SAME_SESSION_REPLAY_ORIGINAL_RUN_NOT_EARLIER")
                replay_status = "SAME_SESSION_REPLAY_ORIGINAL_RUN_INVALID"
            else:
                replay_status = "SAME_SESSION_ORIGINAL_INPUT_REPLAY_VERIFIED"
        else:
            problems.append("NEW_SESSION_PARTIAL_OR_UNKNOWN_ADMISSION")
            replay_status = "NEW_SESSION_PARTIAL_OR_UNKNOWN_ADMISSION"
    elif seal is not None and (seal["session"] != session or seal["deep"] != 0
                               or seal["current"] or seal["snapshot_sha256"] is not None
                               or seal["status"] != "AWAITING_GENUINE_NEW_SESSION"):
        problems.append("LEGACY_FAKE_PROSPECTIVE_EVIDENCE")

    gate_reasons = []
    if source.get("verified") != source.get("required") or source.get("status") != "SOURCE_FINALITY_VERIFIED":
        gate_reasons.append("INDEPENDENT_REGULAR_CLOSE_NOT_CERTIFIED")
    if stability.get("hold") is not False or stability.get("status") != "READY":
        gate_reasons.append("REPLAY_STABILITY_UNRESOLVED")
    if forward.get("frozen_replay_drift", 0) != 0:
        gate_reasons.append("FROZEN_FORWARD_REPLAY_DRIFT")
    if forward.get("settled", 0) == 0:
        gate_reasons.append("NO_SETTLED_FORWARD_VALIDATION")
    if isinstance(session, str) and session >= FIRST_NEW_SESSION:
        if replay_status == "FIRST_SEAL_REMOTE_READBACK_VERIFIED":
            gate_reasons.append("WAITING_INDEPENDENT_SAME_SESSION_REPLAY")
        elif replay_status != "SAME_SESSION_ORIGINAL_INPUT_REPLAY_VERIFIED":
            gate_reasons.append("NEW_SESSION_FIRST_SEAL_OR_REPLAY_UNVERIFIED")

    return {
        "schema": "kalman-daily20-ops-readiness-v1",
        "generated_at_utc": now.isoformat(),
        "research_only": True,
        "production_writes": False,
        "strategy_promoted": False,
        "source_run_id": run.get("id"),
        "source_run_url": run.get("html_url"),
        "source_head_sha": run.get("head_sha"),
        "source_created_at_utc": run.get("created_at"),
        "source_session": session,
        "run_age_hours": age_hours,
        "operational_status": "PASS" if not problems else "FAIL",
        "operational_failures": sorted(set(problems)),
        "research_status": "HOLD" if gate_reasons or problems else "ELIGIBLE_FOR_MANUAL_REVIEW",
        "research_hold_reasons": sorted(set(gate_reasons)),
        "core_symbols": 20,
        "total_assets": refresh.get("asset_count"),
        "source_certified": source.get("verified"),
        "source_required": source.get("required"),
        "source_status": source.get("status"),
        "research_scores": forward.get("signals"),
        "portfolio_scenarios": portfolio.get("scenarios") if isinstance(portfolio, dict) else None,
        "forward_replay_drift": forward.get("frozen_replay_drift"),
        "forward_settled": forward.get("settled"),
        "stability_status": stability.get("status"),
        "stability_incidents": stability.get("incidents"),
        "drive_readback_verified": matched,
        "drive_readback_session": restored_session,
        "first_seal_status": seal["status"] if seal else None,
        "first_seal_deep_verified": seal["deep"] if seal else None,
        "first_seal_original_run_id": seal["original_run"] if seal else None,
        "first_seal_original_snapshot_sha256": seal["snapshot_sha256"] if seal else None,
        "independent_same_session_replay_status": replay_status,
    }


class SafeGitHubLogRedirect(HTTPRedirectHandler):
    """GitHub Actions logs use a cross-host signed URL.

    Never forward the repository bearer token to Azure/GitHub blob storage.
    Disallow non-HTTPS and unrecognized download destinations.
    """

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        host = (parsed.hostname or "").lower()
        allowed = (
            host == "api.github.com"
            or host == "objects.githubusercontent.com"
            or host.endswith(".actions.githubusercontent.com")
            or host.endswith(".blob.core.windows.net")
        )
        if parsed.scheme != "https" or not allowed or parsed.username or parsed.password:
            raise ValueError("UNTRUSTED_GITHUB_LOG_REDIRECT")
        follow = super().redirect_request(req, fp, code, msg, headers, newurl)
        if follow is not None and host != urlparse(req.full_url).hostname:
            follow.remove_header("Authorization")
        return follow


def api(url: str, token: str, *, as_text=False):
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname != "api.github.com":
        raise ValueError("GITHUB_API_URL_NOT_PINNED")
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kalman-research-readiness-audit",
    })
    with build_opener(SafeGitHubLogRedirect()).open(req, timeout=40) as response:
        body = response.read()
    return body.decode("utf-8", errors="replace") if as_text else json.loads(body)


def safe_job_log(root: str, job_id: int | None, token: str, role: str):
    if job_id is None:
        return "", f"JOB_ID_NOT_FOUND:{role}"
    try:
        return api(f"{root}/actions/jobs/{job_id}/logs", token, as_text=True), None
    except (HTTPError, URLError, OSError, TimeoutError, ValueError, UnicodeError):
        # No raw error payload, redirected signed URL, bearer token, or log bytes.
        return "", f"GITHUB_LOG_DOWNLOAD_FAILED:{role}"


def render_md(card: dict) -> str:
    return "\n".join([
        "## Kalman Daily20 research readiness (read-only)",
        f"- Source: Actions run #{card['source_run_id']}: {card['source_run_url']}",
        f"- Source session: {card['source_session']}",
        f"- Operational pipeline: **{card['operational_status']}**",
        f"- Research approval: **{card['research_status']}** (never auto-promote)",
        f"- Assets: {card['total_assets']}/26; score signals: {card['research_scores']}/20",
        f"- Independent regular-close source: {card['source_certified']}/{card['source_required']}",
        f"- Frozen replay drift: {card['forward_replay_drift']}; stability: {card['stability_status']}",
        f"- Drive readback: {card['drive_readback_verified']} ({card['drive_readback_session']})",
        f"- First-seal deep proof: {card['first_seal_status']} ({card['first_seal_deep_verified']} sessions)",
        f"- Same-session replay: {card['independent_same_session_replay_status']}",
        f"- Original first-seal run: {card['first_seal_original_run_id']}; snapshot SHA256: {card['first_seal_original_snapshot_sha256'] or 'not-yet-sealed'}",
        f"- Operational failures: {', '.join(card['operational_failures']) or 'none'}",
        f"- Research HOLD reasons: {', '.join(card['research_hold_reasons']) or 'none'}",
        "- No orders, strategy promotion, Drive writes, or server access.",
        "",
    ])


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--run-id", type=int)
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", "kimtk94/Codex"))
    p.add_argument("--out", default="output/daily20/ops_readiness.json")
    args = p.parse_args()
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        raise SystemExit("GH_TOKEN required for read-only Actions metadata")
    root = f"{API}/repos/{args.repo}"
    if args.run_id:
        run = api(f"{root}/actions/runs/{args.run_id}", token)
    else:
        runs = api(f"{root}/actions/workflows/{WORKFLOW}/runs?branch=main&per_page=20", token)["workflow_runs"]
        run = next((r for r in runs if r.get("status") == "completed"), None)
        if not run:
            raise SystemExit("No completed Daily20 main run")
    jobs = api(f"{root}/actions/runs/{run['id']}/jobs?per_page=100", token)["jobs"]
    mapping = {j["name"]: j["id"] for j in jobs}
    research_log, research_error = safe_job_log(
        root, mapping.get("daily-research"), token, "daily-research")
    publisher_log, publisher_error = safe_job_log(
        root, mapping.get("persist-google-drive"), token, "persist-google-drive")
    result = make_scorecard(run, jobs, research_log, publisher_log)
    log_errors = [e for e in (research_error, publisher_error) if e]
    if log_errors:
        result["operational_failures"] = sorted(set(
            result["operational_failures"] + log_errors))
        result["operational_status"] = "FAIL"
        result["research_status"] = "HOLD"
    result["log_access_status"] = "HOLD" if log_errors else "VERIFIED"
    target = Path(args.out)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    md = render_md(result)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(md)
    print(md)
    return 0 if result["operational_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
