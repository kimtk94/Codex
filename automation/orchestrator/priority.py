#!/usr/bin/env python3
"""Read-only next-audit selector using actual GitHub Actions main-branch run metadata.

This is NOT an AI code agent, a source-of-truth audit, or a CRM writer.
GitHub Actions SUCCESS is only CI telemetry, never a source/sink parity PASS.
Missing, inaccessible and in-progress runs remain distinct from success.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from reconcile_priority import with_mirror_evidence

ROOT = Path(__file__).resolve().parents[2]
POLICY_PATH = ROOT / "automation" / "ops" / "css_freshness_policy.json"
EXPECTED_REPO = "kimtk94/Codex"
STATUSES = frozenset({
    "CI_FAILED", "CI_INTERRUPTED", "CI_PENDING", "CI_SUCCESS_UNVERIFIED",
    "CI_API_UNAVAILABLE", "CI_NO_MAIN_RUN", "CI_UNKNOWN",
})
WEIGHTS = {
    "CI_FAILED": 100,
    "CI_API_UNAVAILABLE": 90,
    "CI_UNKNOWN": 85,
    "CI_NO_MAIN_RUN": 80,
    "CI_INTERRUPTED": 70,
    "CI_PENDING": 50,
    "CI_SUCCESS_UNVERIFIED": 10,
}
NEXT_ACTION = {
    "CI_FAILED": "INSPECT_FAILURE_LOGS_READ_ONLY",
    "CI_API_UNAVAILABLE": "RESTORE_GITHUB_RUN_VISIBILITY",
    "CI_UNKNOWN": "CHECK_UNRECOGNIZED_RUN_STATE",
    "CI_NO_MAIN_RUN": "CHECK_WORKFLOW_TRIGGER_AND_BRANCH",
    "CI_INTERRUPTED": "CHECK_CANCELLATION_AND_CONCURRENCY",
    "CI_PENDING": "CHECK_CURRENT_IN_PROGRESS_RUN",
    "CI_SUCCESS_UNVERIFIED": "COLLECT_ORIGINAL_SOURCE_AND_SINK_READBACK",
}
ALLOWED_END = frozenset({"success", "failure", "timed_out", "cancelled", "skipped", "neutral", "action_required", "startup_failure"})
DATE_PATTERN = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+\.ya?ml$")


def utcnow():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def load_policy(path=POLICY_PATH):
    policy = json.loads(Path(path).read_text(encoding="utf-8"))
    if len(policy.get("domains", [])) != 9:
        raise ValueError("Expected nine policy domains")
    seen = set()
    seen_workflows = set()
    for domain in policy["domains"]:
        name = domain.get("workflow", "")
        domain_id = domain.get("id")
        if (not isinstance(domain_id, str) or domain_id in seen
                or not isinstance(name, str) or name in seen_workflows
                or not NAME_PATTERN.fullmatch(name)):
            raise ValueError("Invalid duplicate domain or workflow name")
        seen.add(domain_id)
        seen_workflows.add(name)
    if len(seen) != 9:
        raise ValueError("Duplicate domain")
    return policy


def github_fetch(url, token):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "codex-autonext-readonly-triage",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=18) as response:
        return json.load(response)


def workflow_url(repo, workflow):
    if repo != EXPECTED_REPO or not NAME_PATTERN.fullmatch(workflow):
        raise ValueError("Out-of-scope repo or workflow")
    return ("https://api.github.com/repos/" + repo + "/actions/workflows/"
            + urllib.parse.quote(workflow, safe="") + "/runs?branch=main&per_page=5")


def check_timestamp(value):
    if not isinstance(value, str) or not DATE_PATTERN.fullmatch(value):
        return False
    try:
        dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return True
    except ValueError:
        return False


def run_signal(payload, repo=EXPECTED_REPO):
    if not isinstance(payload, dict) or not isinstance(payload.get("workflow_runs"), list):
        raise ValueError("Invalid GitHub runs response")
    records = payload["workflow_runs"]
    eligible = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Invalid GitHub run record")
        if item.get("head_branch") != "main" or item.get("event") == "pull_request":
            continue
        if not check_timestamp(item.get("created_at")):
            raise ValueError("No trustworthy run timestamp")
        run_id = item.get("id")
        if type(run_id) is not int or run_id <= 0:
            raise ValueError("Invalid run ID")
        eligible.append(item)
    if not eligible:
        return {"signal": "CI_NO_MAIN_RUN", "run_id": None, "run_url": None,
                "run_created_at": None, "event": None}
    latest = max(eligible, key=lambda x: (x["created_at"], x["id"]))
    status = latest.get("status")
    conclusion = latest.get("conclusion")
    if status in ("queued", "in_progress", "pending", "requested", "waiting"):
        signal = "CI_PENDING"
    elif status == "completed":
        if conclusion not in ALLOWED_END:
            signal = "CI_UNKNOWN"
        elif conclusion == "success":
            signal = "CI_SUCCESS_UNVERIFIED"
        elif conclusion in ("cancelled", "skipped", "neutral"):
            signal = "CI_INTERRUPTED"
        else:
            signal = "CI_FAILED"
    else:
        signal = "CI_UNKNOWN"
    run_id = latest["id"]
    # Canonical link is constructed from validated GitHub run ID, not arbitrary URL fields.
    return {
        "signal": signal,
        "run_id": run_id,
        "run_url": f"https://github.com/{repo}/actions/runs/{run_id}",
        "run_created_at": latest["created_at"],
        "event": str(latest.get("event") or "")[:40],
    }


def build_priority(policy, fetch=github_fetch, *, token=None, repo=EXPECTED_REPO):
    if repo != EXPECTED_REPO:
        raise ValueError("Repository not allowed")
    queue = []
    for order, domain in enumerate(policy["domains"]):
        item = {
            "domain": domain["id"],
            "name": domain["name"],
            "workflow": domain["workflow"],
        }
        try:
            item.update(run_signal(fetch(workflow_url(repo, domain["workflow"]), token), repo=repo))
        except (OSError, ValueError, KeyError, TypeError) as exc:
            item.update({
                "signal": "CI_API_UNAVAILABLE", "run_id": None, "run_url": None,
                "run_created_at": None, "event": None,
                "unavailable_reason_type": type(exc).__name__,
            })
        item["priority"] = WEIGHTS[item["signal"]]
        item["next_safe_action"] = NEXT_ACTION[item["signal"]]
        item["business_source_checked"] = False
        item["business_sink_checked"] = False
        item["business_freshness"] = "NOT_VERIFIED"
        item["_order"] = order
        queue.append(item)
    queue.sort(key=lambda x: (-x["priority"], x["_order"]))
    for item in queue:
        del item["_order"]
    # This result proposes investigation only; it cannot grant write authorization.
    return {
        "schema_version": 1,
        "checked_at": utcnow(),
        "repository": repo,
        "evidence_scope": "GITHUB_ACTIONS_MAIN_BRANCH_METADATA_ONLY",
        "business_source_sink_verification": "NOT_VERIFIED",
        "auto_execute_business_writes": False,
        "auto_merge_pr": False,
        "domain_count": len(queue),
        "unavailable_workflow_count": sum(x["signal"] == "CI_API_UNAVAILABLE" for x in queue),
        "next_review": queue[0] if queue else None,
        "queue": queue,
    }


def summary(report):
    item = report["next_review"]
    lines = [
        "## Autonomous Next — next safe audit to review",
        "",
        f"- CI domains checked: **{report['domain_count']}/9**",
        f"- GitHub metadata unavailable: **{report['unavailable_workflow_count']}**",
        "- Business source/sink freshness: **NOT VERIFIED**",
        f"- Revenue mirror receipt: **{report.get('revenue_mirror_evidence', 'NOT_COLLECTED')}**",
        "- This ranks read-only investigation tasks; it does not dispatch workflows or change SFDC/Feishu.",
    ]
    if item:
        lines += [
            f"- Priority domain: **{item['domain']}**",
            f"- Latest CI signal: **{item['signal']}**",
            f"- Safe next action: `{item['next_safe_action']}`",
            f"- Run evidence: {item['run_url'] or 'unavailable'}",
        ]
    lines += ["", "| Domain | CI signal | Suggested next action |",
              "|---|---|---|"]
    for item in report["queue"]:
        lines.append(f"| {item['domain']} | {item['signal']} | {item['next_safe_action']} |")
    return "\n".join(lines) + "\n"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("autonomous-next-triage/priority.json"))
    ap.add_argument("--policy", type=Path, default=POLICY_PATH)
    ap.add_argument("--revenue-evidence-file", type=Path, default=None)
    args = ap.parse_args()
    report = build_priority(load_policy(args.policy), token=os.getenv("GITHUB_TOKEN"),
                            repo=os.getenv("GITHUB_REPOSITORY", EXPECTED_REPO))
    report = with_mirror_evidence(report, receipt_path=args.revenue_evidence_file)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    text = summary(report)
    print(text)
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
            f.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
