#!/usr/bin/env python3
"""GitHub Actions recurring writer watchdog. Only existing authorized pipeline may run.

The independent cron protects against delayed/missed GitHub schedule ticks.
No customer data is queried by this script. An eligible stale *previously
successful* Feishu writer can be dispatched at most once per cooldown;
the existing unified workflow retains its tests, concurrency and approval
scope. QQ historical ingestion is monitored only, never auto-dispatched.
"""
import datetime as dt
import json
import os
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request

UTC = dt.timezone.utc
FEISHU = "feishu-sources-unified.yml"
QQ = "qq-mail-2026-backfill.yml"
REPO = "kimtk94/Codex"
WRITER_MAX_AGE_HOURS = 6
QQ_MAX_AGE_HOURS = 12
RETRY_COOLDOWN_HOURS = 3
ACTIVE = {"requested", "queued", "pending", "waiting", "in_progress"}
VALID_EVENTS = {"schedule", "workflow_dispatch"}


def timestamp(value):
    try:
        parsed = dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return parsed.astimezone(UTC) if parsed.tzinfo else None


def inspect(runs, now, max_age_hours, cooldown_hours=RETRY_COOLDOWN_HOURS):
    """Fail closed on incomplete or ambiguous GitHub run history."""
    if now.tzinfo is None:
        raise ValueError("WATCHDOG_NOW_TZ_REQUIRED")
    if not isinstance(runs, list):
        return {"state": "RUN_HISTORY_UNVERIFIED", "last_success_age_hours": None,
                "last_attempt_age_hours": None, "eligible": False}
    selected = []
    for run in runs:
        if not isinstance(run, dict):
            return {"state": "RUN_HISTORY_UNVERIFIED", "last_success_age_hours": None,
                    "last_attempt_age_hours": None, "eligible": False}
        if run.get("event") not in VALID_EVENTS or run.get("head_branch") != "main":
            continue
        at = timestamp(run.get("created_at"))
        if at is None or at > now + dt.timedelta(minutes=5):
            return {"state": "RUN_HISTORY_UNVERIFIED", "last_success_age_hours": None,
                    "last_attempt_age_hours": None, "eligible": False}
        selected.append((at,run))
    if not selected:
        return {"state": "NO_PRODUCTION_HISTORY_HOLD", "last_success_age_hours": None,
                "last_attempt_age_hours": None, "eligible": False}
    selected.sort(key=lambda pair: pair[0], reverse=True)
    newest, latest = selected[0]
    age = (now-newest).total_seconds()/3600
    good = [at for at,run in selected
            if run.get("event") == "schedule"
            and run.get("status") == "completed" and run.get("conclusion") == "success"]
    # A manual workflow_dispatch without apply=true can run tests but no writer:
    # never mistake such a success for a production materialization.
    last_good = max(good) if good else None
    success_age = (now-last_good).total_seconds()/3600 if last_good else None
    details = {"last_success_age_hours": round(success_age,2) if success_age is not None else None,
               "last_attempt_age_hours": round(age,2), "eligible": False}
    if latest.get("status") in ACTIVE:
        return dict(details,state="RUNNING" if age <= max_age_hours else "STALLED_RUN_HOLD")
    if latest.get("status") != "completed" or latest.get("conclusion") not in {
            "success", "failure", "cancelled", "timed_out", "action_required", "skipped"}:
        return dict(details,state="RUN_HISTORY_UNVERIFIED")
    # The latest failed writer must not be hidden behind a previous PASS,
    # even while that prior PASS is still within the normal cadence window.
    if latest.get("conclusion") != "success" and age < cooldown_hours:
        return dict(details,state="RECENT_FAILURE_HOLD")
    if success_age is not None and success_age <= max_age_hours:
        if latest.get("conclusion") != "success":
            return dict(details,state="LATEST_FAILURE_HOLD")
        return dict(details,state="RECENT_SCHEDULE_SUCCESS")
    if last_good is None:
        return dict(details,state="NO_SUCCESS_BASELINE_HOLD")
    if age < cooldown_hours:
        return dict(details,state="COOLDOWN_WAIT" if latest.get("conclusion") == "success"
                    else "RECENT_FAILURE_HOLD")
    return dict(details,state="STALE_WRITER_ELIGIBLE",eligible=True)


def request_json(repo, workflow, token):
    if repo != REPO:
        raise ValueError("WATCHDOG_REPO_NOT_ALLOWLISTED")
    if workflow not in (FEISHU, QQ):
        raise ValueError("WATCHDOG_WORKFLOW_NOT_ALLOWLISTED")
    url = ("https://api.github.com/repos/" + repo + "/actions/workflows/" +
           urllib.parse.quote(workflow, safe="") + "/runs?branch=main&per_page=40")
    req = urllib.request.Request(url,headers={
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req,timeout=20) as response:
        payload = json.load(response)
    if not isinstance(payload,dict) or not isinstance(payload.get("workflow_runs"),list):
        raise RuntimeError("WORKFLOW_RUN_HISTORY_INCOMPLETE")
    return payload["workflow_runs"]


def dispatch_existing_writer(repo, token):
    if repo != REPO:
        raise ValueError("WATCHDOG_REPO_NOT_ALLOWLISTED")
    url="https://api.github.com/repos/"+repo+"/actions/workflows/"+FEISHU+"/dispatches"
    body=json.dumps({"ref":"main","inputs":{"apply":"true"}}).encode("utf-8")
    req=urllib.request.Request(url,method="POST",data=body,headers={
        "Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "Content-Type":"application/json","X-GitHub-Api-Version":"2022-11-28"})
    with urllib.request.urlopen(req,timeout=20) as response:
        if response.status != 204:
            raise RuntimeError("WRITER_DISPATCH_NOT_ACCEPTED")


def reconcile(feishu_runs,qq_runs,now,auto_dispatch=False,dispatch=None):
    """No dispatch if unknown, busy, failed recently, or no verified schedule baseline."""
    feishu=inspect(feishu_runs,now,WRITER_MAX_AGE_HOURS)
    qq=inspect(qq_runs,now,QQ_MAX_AGE_HOURS)
    result={"feishu":feishu,"qq_2026":qq,"dispatch_state":"NOT_REQUESTED",
            "feishu_writer_owned_by_existing_unified_workflow":True,
            "qq_historical_auto_replay":False,"financial_original_writes":False,
            "customer_mail_sends":False}
    if feishu["eligible"] and auto_dispatch:
        if dispatch is None:
            result["dispatch_state"]="DISPATCH_DEPENDENCY_UNAVAILABLE"
        else:
            dispatch()
            result["dispatch_state"]="EXISTING_FEISHU_WRITER_REQUESTED"
    elif feishu["eligible"]:
        result["dispatch_state"]="ELIGIBLE_REPORT_ONLY"
    return result


def main():
    path=Path("audit-results/css-writer-watchdog.json")
    path.parent.mkdir(parents=True,exist_ok=True)
    now=dt.datetime.now(UTC)
    result={"checked_utc":now.isoformat(),"state":"RUN_HISTORY_UNVERIFIED",
            "dispatch_state":"NOT_REQUESTED"}
    try:
        token=os.environ["GITHUB_TOKEN"]
        repo=os.environ.get("GITHUB_REPOSITORY","")
        if repo != REPO or not token or os.environ.get("GITHUB_REF") != "refs/heads/main":
            raise ValueError("WATCHDOG_GITHUB_SCOPE_UNAVAILABLE")
        feishu_runs=request_json(repo,FEISHU,token)
        qq_runs=request_json(repo,QQ,token)
        auto=os.environ.get("CSS_WATCHDOG_AUTO_DISPATCH","false").lower()=="true"
        result=reconcile(feishu_runs,qq_runs,now,auto,
                         lambda:dispatch_existing_writer(repo,token))
        result["checked_utc"]=now.isoformat()
    except Exception as exc:
        result={"checked_utc":now.isoformat(),"state":"RUN_HISTORY_UNVERIFIED",
                "dispatch_state":"NOT_REQUESTED","error_type":type(exc).__name__}
    path.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print("CSS_RECURRING_WATCHDOG "+json.dumps(result,sort_keys=True))
    summary=os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary,"a",encoding="utf-8") as out:
            out.write("## Recurring ingestion health (schedule vs independent watchdog)\n\n")
            out.write("Existing Feishu unified Writer only; no new writer. QQ 2026 backfill monitored only.\n\n")
            out.write("| Pipeline | Health state | Last scheduled success age (h) | Last attempt age (h) |\n")
            out.write("|---|---|---:|---:|\n")
            for name in ("feishu","qq_2026"):
                item=result.get(name) or {}
                out.write("| "+name+" | "+str(item.get("state","RUN_HISTORY_UNVERIFIED"))+
                          " | "+str(item.get("last_success_age_hours"))+
                          " | "+str(item.get("last_attempt_age_hours"))+" |\n")
            out.write("\nRecovery: **"+result.get("dispatch_state","NOT_REQUESTED")+
                      "**. No SFDC, QQ replay, payment or original finance writes.\n")
    if "feishu" not in result or "qq_2026" not in result:
        return 2
    if result["dispatch_state"]=="EXISTING_FEISHU_WRITER_REQUESTED":
        print("::warning title=Missing Feishu schedule recovered::Requested existing guarded writer after cooldown")
    severe={"RUN_HISTORY_UNVERIFIED","NO_PRODUCTION_HISTORY_HOLD",
            "NO_SUCCESS_BASELINE_HOLD","STALLED_RUN_HOLD",
            "RECENT_FAILURE_HOLD","LATEST_FAILURE_HOLD","COOLDOWN_WAIT"}
    if result["feishu"]["state"] in severe or result["qq_2026"]["state"] in severe:
        return 2
    # QQ schedule stale and writer dispatch problems remain actionable P0.
    if (result["qq_2026"]["state"]=="STALE_WRITER_ELIGIBLE"
            or result["dispatch_state"]=="DISPATCH_DEPENDENCY_UNAVAILABLE"
            or (result["feishu"]["state"]=="STALE_WRITER_ELIGIBLE"
                and result["dispatch_state"]!="EXISTING_FEISHU_WRITER_REQUESTED")):
        return 2
    return 0


if __name__=="__main__":
    sys.exit(main())
