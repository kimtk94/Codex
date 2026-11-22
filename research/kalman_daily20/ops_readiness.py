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
from urllib.request import Request, urlopen

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

    gate_reasons = []
    if source.get("verified") != source.get("required") or source.get("status") != "SOURCE_FINALITY_VERIFIED":
        gate_reasons.append("INDEPENDENT_REGULAR_CLOSE_NOT_CERTIFIED")
    if stability.get("hold") is not False or stability.get("status") != "READY":
        gate_reasons.append("REPLAY_STABILITY_UNRESOLVED")
    if forward.get("frozen_replay_drift", 0) != 0:
        gate_reasons.append("FROZEN_FORWARD_REPLAY_DRIFT")
    if forward.get("settled", 0) == 0:
        gate_reasons.append("NO_SETTLED_FORWARD_VALIDATION")

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
    }


def api(url: str, token: str, *, as_text=False):
    req = Request(url, headers={
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "kalman-research-readiness-audit",
    })
    with urlopen(req, timeout=40) as response:
        body = response.read()
    return body.decode("utf-8", errors="replace") if as_text else json.loads(body)


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
    research_log = api(f"{root}/actions/jobs/{mapping['daily-research']}/logs", token, as_text=True) if "daily-research" in mapping else ""
    publisher_log = api(f"{root}/actions/jobs/{mapping['persist-google-drive']}/logs", token, as_text=True) if "persist-google-drive" in mapping else ""
    result = make_scorecard(run, jobs, research_log, publisher_log)
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
