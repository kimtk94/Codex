#!/usr/bin/env python3
"""Bounded GitHub Actions "next" runner. Only executes audited offline/synthetic suites.

A GitHub issue stores resumable progress. CI artifacts contain the full run receipt.
No CRM, Feishu, email, deployment, git push, or PR merge is performed.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
PLAN_PATH = Path(__file__).with_name("sales_plan.json")
START = "<!-- AUTONEXT_STATE_BEGIN -->"
END = "<!-- AUTONEXT_STATE_END -->"
PAUSE_CHECKBOX = "- [x] PAUSE_AUTONEXT"
RUN_CHECKBOX = "- [ ] PAUSE_AUTONEXT"
RETRY_LIMIT = 3
RESET_AFTER_HOURS = 24
SUITES = {
    "policy": ("python3", "-m", "unittest", "discover", "-s", "automation_policy",
               "-p", "test_*.py", "-t", ".", "-v"),
    "sfdc_patterns": ("python3", "-m", "unittest", "discover", "-s", "automation/sfdc",
                      "-p", "test_oppo_quote_popular_patterns.py", "-v"),
    "sfdc_krw": ("python3", "-m", "unittest", "discover", "-s", "automation/sfdc",
                 "-p", "test_quote_2026_krw_price_reuse.py", "-v"),
    "feishu_offline": ("python3", "-m", "unittest", "discover", "-s", "integrations/feishu",
                       "-p", "test_*.py", "-v"),
    "freshness_policy": ("python3", "-m", "unittest", "discover", "-s", "automation/ops",
                         "-p", "test_css_freshness_policy.py", "-v"),
    "progress_evidence": ("python3", "-m", "unittest", "discover", "-s", "automation/progress",
                          "-p", "test_gate_evaluator.py", "-v"),
}


def now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def validate_plan(plan: dict) -> None:
    if plan.get("schema_version") != 1 or plan.get("profile") != "sales":
        raise ValueError("Unsupported or non-sales plan")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or not tasks or len(tasks) > 20:
        raise ValueError("Expected 1-20 tasks")
    seen = set()
    for task in tasks:
        if not isinstance(task, dict) or set(task) != {"id", "title", "suite", "depends_on"}:
            raise ValueError("Invalid task fields")
        task_id = task["id"]
        if not isinstance(task_id, str) or not task_id or task_id in seen:
            raise ValueError("Duplicate or missing task ID")
        if task["suite"] not in SUITES:
            raise ValueError("Unapproved suite: " + str(task["suite"]))
        if not isinstance(task["depends_on"], list) or any(dep not in seen for dep in task["depends_on"]):
            raise ValueError("Dependencies must reference earlier tasks only")
        seen.add(task_id)


def fingerprint(plan: dict) -> str:
    return hashlib.sha256(json.dumps(plan, sort_keys=True).encode("utf-8")).hexdigest()


def fresh_state(plan: dict, sha: str, run_url: str) -> dict:
    return {
        "schema_version": 1, "profile": "sales", "fingerprint": fingerprint(plan),
        "head_sha": sha, "started_at": now(), "updated_at": now(), "run_url": run_url,
        "tasks": {}, "overall": "PENDING",
        "policy": {"sfdc_save": False, "email_send": False, "pr_merge": False,
                   "live_source_verified": False},
    }


def reusable(state: dict | None, plan: dict, sha: str, current: dt.datetime | None = None) -> bool:
    if not isinstance(state, dict) or state.get("fingerprint") != fingerprint(plan):
        return False
    if state.get("head_sha") != sha or state.get("profile") != "sales":
        return False
    try:
        started = dt.datetime.fromisoformat(state["started_at"])
        if started.tzinfo is None:
            return False
        age = (current or dt.datetime.now(dt.timezone.utc)) - started
        return dt.timedelta(0) <= age < dt.timedelta(hours=RESET_AFTER_HOURS)
    except (KeyError, ValueError, TypeError):
        return False


class IssueCheckpoint:
    """Writes only the marked JSON section of a known GitHub issue."""

    def __init__(self, repo: str, number: int, token: str):
        if not token or not number or "/" not in repo:
            raise ValueError("Existing issue, repository and GitHub token required")
        self.url = f"https://api.github.com/repos/{repo}/issues/{number}"
        self.token = token
        self.body = None

    def request(self, method: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(
            self.url, data=data, method=method,
            headers={"Authorization": "Bearer " + self.token,
                     "Accept": "application/vnd.github+json",
                     "Content-Type": "application/json",
                     "X-GitHub-Api-Version": "2022-11-28",
                     "User-Agent": "autonomous-next-sales"},
        )
        with urllib.request.urlopen(req, timeout=25) as response:
            return json.load(response)

    def load(self) -> dict | None:
        self.body = self.request("GET").get("body") or ""
        if self.body.count(START) != 1 or self.body.count(END) != 1:
            raise ValueError("Missing unique state markers in issue")
        raw = self.body.split(START, 1)[1].split(END, 1)[0].strip()
        return json.loads(raw) if raw else None

    def paused(self) -> bool:
        """Re-check operator pause control before starting each task."""
        self.load()
        if self.body.count(PAUSE_CHECKBOX) == 1 and RUN_CHECKBOX not in self.body:
            return True
        if self.body.count(RUN_CHECKBOX) == 1 and PAUSE_CHECKBOX not in self.body:
            return False
        raise ValueError("Missing or ambiguous PAUSE_AUTONEXT checkbox")

    def save(self, state: dict) -> None:
        # Refresh human notes and pause toggle before each write. A checkpoint
        # update must never overwrite notes edited since the previous stage.
        self.load()
        left, tail = self.body.split(START, 1)
        _, right = tail.split(END, 1)
        new_body = (left + START + "\n" + json.dumps(state, ensure_ascii=False,
                    sort_keys=True, indent=2) + "\n" + END + right)
        self.request("PATCH", {"body": new_body})
        self.body = new_body


def next_task(plan: dict, state: dict) -> dict | None:
    statuses = state["tasks"]
    for task in plan["tasks"]:
        previous = statuses.get(task["id"], {})
        if previous.get("status") == "PASS":
            continue
        if previous.get("attempts", 0) >= RETRY_LIMIT:
            return None
        if any(statuses.get(dep, {}).get("status") != "PASS" for dep in task["depends_on"]):
            return None
        return task
    return None


def execute_suite(suite: str, *, root: Path = ROOT, timeout: int = 240) -> tuple[bool, str]:
    # No shell, no arbitrary user commands, no inherited GitHub API credential.
    env = os.environ.copy()
    for name in ("GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY"):
        env.pop(name, None)
    env["FEISHU_APP_ID"] = ""
    env["FEISHU_APP_SECRET"] = ""
    try:
        proc = subprocess.run(
            SUITES[suite], cwd=root, env=env, capture_output=True,
            text=True, timeout=timeout, check=False,
        )
        detail = (proc.stdout + "\n" + proc.stderr)[-1800:]
        return proc.returncode == 0, detail
    except subprocess.TimeoutExpired:
        return False, f"Timeout after {timeout}s"


def report(plan: dict, state: dict, output_dir: Path) -> str:
    output_dir.mkdir(parents=True, exist_ok=True)
    done = sum(state["tasks"].get(x["id"], {}).get("status") == "PASS" for x in plan["tasks"])
    total = len(plan["tasks"])
    pending = [x["id"] for x in plan["tasks"]
               if state["tasks"].get(x["id"], {}).get("status") != "PASS"]
    lines = [
        "# Autonomous Next — Sales (synthetic/offline only)", "",
        f"- Status: **{state['overall']}**",
        f"- Verified test stages: **{done}/{total}** ({done * 100 // total}%)",
        f"- Remaining stages: **{len(pending)}**",
        f"- Next / blocked stage: {pending[0] if pending else 'none'}",
        f"- Run evidence: {state['run_url'] or 'local dry-run'}",
        "- Business-source freshness / sink reconciliation: **NOT VERIFIED**",
        "- SFDC Save, customer mail, PR auto-merge: **DISABLED**",
        "- Pause control: check PAUSE_AUTONEXT in issue #794 (effective before next stage)", "",
        "| Stage | Result | Attempts |", "|---|---|---:|",
    ]
    for task in plan["tasks"]:
        item = state["tasks"].get(task["id"], {})
        lines.append(f"| {task['id']} | {item.get('status', 'PENDING')} | {item.get('attempts', 0)} |")
    summary = "\n".join(lines) + "\n"
    (output_dir / "state.json").write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    (output_dir / "summary.md").write_text(summary, encoding="utf-8")
    if os.getenv("GITHUB_STEP_SUMMARY"):
        with Path(os.environ["GITHUB_STEP_SUMMARY"]).open("a", encoding="utf-8") as f:
            f.write(summary)
    return summary


def run(plan: dict, state: dict, *, max_steps: int,
        checkpoint: IssueCheckpoint | None, root: Path, dry_run: bool) -> dict:
    if not 1 <= max_steps <= 10:
        raise ValueError("max_steps must be 1..10")
    if dry_run:
        state["overall"] = "DRY_RUN_NO_EXECUTION"
        return state
    processed = 0
    paused = False
    while processed < max_steps:
        if checkpoint and checkpoint.paused():
            paused = True
            break
        task = next_task(plan, state)
        if task is None:
            break
        task_id = task["id"]
        before = state["tasks"].get(task_id, {})
        entry = {"status": "RUNNING", "attempts": before.get("attempts", 0) + 1,
                 "started_at": now(), "suite": task["suite"]}
        state["tasks"][task_id] = entry
        state["overall"] = "RUNNING"
        state["updated_at"] = now()
        if checkpoint:
            checkpoint.save(state)
        passed, detail = execute_suite(task["suite"], root=root)
        entry["status"] = "PASS" if passed else "FAILED"
        entry["finished_at"] = now()
        if not passed:
            entry["failure_excerpt"] = detail[-800:]
        state["updated_at"] = now()
        processed += 1
        if checkpoint:
            checkpoint.save(state)
        print(f"{task_id}: {entry['status']} ({entry['attempts']}/{RETRY_LIMIT})", flush=True)
        if not passed:
            break

    passed_count = sum(state["tasks"].get(x["id"], {}).get("status") == "PASS"
                       for x in plan["tasks"])
    if paused:
        state["overall"] = "PAUSED_BY_OPERATOR"
    elif passed_count == len(plan["tasks"]):
        state["overall"] = "TEST_CHAIN_PASS"
    elif any(x.get("status") == "FAILED" for x in state["tasks"].values()):
        state["overall"] = "BLOCKED" if next_task(plan, state) is None else "FAILED_RETRYABLE"
    else:
        state["overall"] = "PARTIAL"
    state["updated_at"] = now()
    if checkpoint:
        checkpoint.save(state)
    return state


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", type=Path, default=PLAN_PATH)
    ap.add_argument("--out", type=Path, default=ROOT / "autonomous-next-results")
    ap.add_argument("--max-steps", type=int, default=5)
    ap.add_argument("--issue-number", type=int, default=0)
    ap.add_argument("--reset", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--offline-run", action="store_true", help="Execute offline suites without GitHub issue I/O")
    args = ap.parse_args()
    plan = json.loads(args.plan.read_text(encoding="utf-8"))
    validate_plan(plan)
    repo = os.getenv("GITHUB_REPOSITORY", "kimtk94/Codex")
    sha = os.getenv("GITHUB_SHA", "local")
    run_url = ("https://github.com/" + repo + "/actions/runs/" + os.environ["GITHUB_RUN_ID"]
               if os.environ.get("GITHUB_RUN_ID") else "")
    checkpoint = None
    previous = None
    if args.dry_run and args.offline_run:
        ap.error("--dry-run and --offline-run cannot be combined")
    if not args.dry_run and not args.offline_run:
        checkpoint = IssueCheckpoint(repo, args.issue_number, os.getenv("GITHUB_TOKEN", ""))
        previous = checkpoint.load()
    state = (previous if not args.reset and reusable(previous, plan, sha)
             else fresh_state(plan, sha, run_url))
    state["run_url"] = run_url
    try:
        result = run(plan, state, max_steps=args.max_steps, checkpoint=checkpoint,
                     root=ROOT, dry_run=args.dry_run)
        print(report(plan, result, args.out))
        return 1 if result["overall"] in ("FAILED_RETRYABLE", "BLOCKED") else 0
    except Exception:
        state["overall"] = "BLOCKED_INFRASTRUCTURE"
        state["updated_at"] = now()
        report(plan, state, args.out)
        raise


if __name__ == "__main__":
    sys.exit(main())
