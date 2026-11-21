#!/usr/bin/env python3
"""Read-only effective GitHub main ruleset verification.

No writes. Does not enable protection or assume that a green CI check means the
GitHub ruleset is active. Any unreadable effective rule remains unverified.
"""
from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REQUIRED_TYPES = {"pull_request", "required_status_checks", "deletion", "non_fast_forward"}
REQUIRED_CHECK = "main-write-guard"


class SourceUnavailable(RuntimeError):
    pass


def fetch_json(path: str, *, token: str | None = None, base: str = "https://api.github.com"):
    if not path.startswith("/repos/"):
        raise ValueError("Only GitHub repository read endpoints are allowed")
    url = base.rstrip("/") + path
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "codex-main-protection-readback",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, method="GET", headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)
    except (urllib.error.URLError, OSError, ValueError) as exc:
        # Avoid logging response bodies or auth headers.
        code = getattr(exc, "code", "NETWORK")
        raise SourceUnavailable("GITHUB_API_READ_" + str(code)) from exc


def matches_default_branch(rule: dict, branch: str = "main") -> bool:
    if rule.get("target") != "branch" or rule.get("enforcement") != "active":
        return False
    condition = (rule.get("conditions") or {}).get("ref_name") or {}
    includes = condition.get("include") or []
    excludes = condition.get("exclude") or []
    ref = "refs/heads/" + branch
    def matches(pattern: str) -> bool:
        if pattern in ("~ALL", "~DEFAULT_BRANCH"):
            return True
        return fnmatch.fnmatchcase(ref, pattern) or fnmatch.fnmatchcase(branch, pattern)
    return any(matches(x) for x in includes) and not any(matches(x) for x in excludes)


def check_contexts(rule: dict) -> set[str]:
    if rule.get("type") != "required_status_checks":
        return set()
    obj = rule.get("parameters") or {}
    values = obj.get("required_status_checks") or []
    return {v.get("context") for v in values if isinstance(v, dict) and isinstance(v.get("context"), str)}


def evaluate(fetch, repository: str = "kimtk94/Codex") -> dict:
    if repository.count("/") != 1 or any(x not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-._/" for x in repository):
        raise ValueError("Unsafe repository identifier")
    prefix = "/repos/" + repository
    repo = fetch(prefix)
    if repo.get("default_branch") != "main":
        raise ValueError("Repository default branch unexpectedly differs from main")
    branch = fetch(prefix + "/branches/main")
    protected = branch.get("protected")
    if not isinstance(protected, bool):
        raise ValueError("GitHub branch protection field is missing")
    items = fetch(prefix + "/rulesets?includes_parents=true")
    if not isinstance(items, list):
        raise ValueError("GitHub ruleset list is unavailable or malformed")
    report = {
        "schema_version": 1,
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "repository": repository,
        "main_sha": (branch.get("commit") or {}).get("sha"),
        "branch_protected": protected,
        "ruleset_count": len(items),
        "active_matching_ruleset_ids": [],
        "effective_rule_types": [],
        "required_check_present": False,
        "bypass_actor_count": 0,
        "status": "WAITING_ADMIN",
        "missing": sorted(REQUIRED_TYPES),
        "limitations": ["GitHub API readback only; an attempted direct push is deliberately not performed"],
    }
    if not protected and not items:
        return report
    selected = []
    for item in items:
        if item.get("target") != "branch" or item.get("enforcement") != "active":
            continue
        rid = item.get("id")
        if not isinstance(rid, int):
            raise ValueError("Ruleset without numeric ID")
        detail = fetch(prefix + "/rulesets/" + str(rid))
        if matches_default_branch(detail):
            selected.append(detail)
    report["active_matching_ruleset_ids"] = sorted(x["id"] for x in selected)
    report["bypass_actor_count"] = sum(len(x.get("bypass_actors") or []) for x in selected)
    if not protected or not selected:
        report["status"] = "RULESET_NOT_EFFECTIVE"
        return report
    effective = fetch(prefix + "/rules/branches/main")
    if not isinstance(effective, list):
        raise ValueError("Effective branch rule API returned a non-list")
    allowed_ids = set(report["active_matching_ruleset_ids"])
    effective = [r for r in effective if r.get("ruleset_id") in allowed_ids]
    types = {r.get("type") for r in effective}
    contexts = set().union(*(check_contexts(r) for r in effective))
    report["effective_rule_types"] = sorted(x for x in types if isinstance(x, str))
    report["required_check_present"] = REQUIRED_CHECK in contexts
    report["missing"] = sorted(REQUIRED_TYPES - types)
    if REQUIRED_CHECK not in contexts:
        report["missing"].append("required_status_check:" + REQUIRED_CHECK)
    if report["bypass_actor_count"]:
        report["missing"].append("bypass_actor_review")
    report["status"] = "PROTECTION_VERIFIED" if not report["missing"] else "CONFIG_INCOMPLETE"
    return report


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Read-only main protection readback")
    p.add_argument("--output", required=True, type=Path)
    p.add_argument("--repository", default="kimtk94/Codex")
    args = p.parse_args(argv)
    try:
        report = evaluate(lambda path: fetch_json(path, token=os.environ.get("GITHUB_TOKEN")), args.repository)
        exit_code = 0
    except (SourceUnavailable, OSError, ValueError, KeyError, TypeError) as exc:
        report = {
            "schema_version": 1,
            "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "repository": args.repository,
            "status": "SOURCE_UNAVAILABLE",
            "failure_type": type(exc).__name__,
            "error_code": str(exc)[:90] if isinstance(exc, SourceUnavailable) else "INVALID_SOURCE_RESPONSE",
            "protection_verified": False,
        }
        exit_code = 2
    report["protection_verified"] = report["status"] == "PROTECTION_VERIFIED"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("MAIN_PROTECTION_READBACK:", report["status"])
    print("PROTECTION_VERIFIED:", report["protection_verified"])
    if "branch_protected" in report:
        print("BRANCH_PROTECTED:", report["branch_protected"])
        print("ACTIVE_RULESET_IDS:", report["active_matching_ruleset_ids"])
        print("MISSING:", report["missing"])
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
