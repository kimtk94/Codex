"""Monitor NBA scheduled runs independently; create at most one issue per failed/missed slot."""
import datetime as dt
import io
import json
import os
import urllib.error
import urllib.request
import zipfile

KST = dt.timezone(dt.timedelta(hours=9))
SLOTS = (8, 12, 17)
WORKFLOW = "nba-verified-pool-pipeline.yml"
GRACE_MINUTES = 100


def expected_slot(now):
    local = now.astimezone(KST)
    candidates = [dt.datetime.combine((local - dt.timedelta(days=d)).date(),
                  dt.time(h, tzinfo=KST)) for d in (0, 1) for h in SLOTS]
    eligible = [t for t in candidates if t + dt.timedelta(minutes=GRACE_MINUTES) <= local]
    return max(eligible) if eligible else None


def assess(slot, runs):
    if slot is None:
        return "WAIT", None
    start = slot.astimezone(dt.timezone.utc)
    # Do not confuse a successful push or dispatch with a scheduled run.
    matches = [r for r in runs if r.get("event") == "schedule"
               and abs((dt.datetime.fromisoformat(r["created_at"].replace("Z", "+00:00")) - start).total_seconds()) <= 7200]
    if not matches:
        return "MISSING", None
    latest = max(matches, key=lambda r: r["created_at"])
    if latest.get("conclusion") == "success":
        return "SUCCESS", latest
    if latest.get("status") != "completed":
        return "PENDING", latest
    return "FAILED", latest


def api(path, method="GET", data=None):
    request = urllib.request.Request("https://api.github.com" + path,
        data=json.dumps(data).encode() if data is not None else None,
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json",
                 "X-GitHub-Api-Version": "2022-11-28",
                 "Content-Type": "application/json"}, method=method)
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = response.read()
        return json.loads(payload) if payload else {}


def check_readback(repo, run_id):
    # GitHub returns a ZIP archive containing all job log text.
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}/actions/runs/{run_id}/logs",
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=30) as response:
        archive = response.read()
    with zipfile.ZipFile(io.BytesIO(archive)) as bundle:
        logs = "\n".join(bundle.read(name).decode("utf-8", errors="replace")
                          for name in bundle.namelist() if name.endswith(".txt"))
    return "READBACK_VERIFIED=true" in logs and "NBA_REPLY_DASHBOARD_UPDATED" in logs


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    now = dt.datetime.now(dt.timezone.utc)
    slot = expected_slot(now)
    if slot is None:
        print("NBA_SCHEDULE_MONITOR WAIT")
        return
    runs = api(f"/repos/{repo}/actions/workflows/{WORKFLOW}/runs?event=schedule&per_page=50")["workflow_runs"]
    state, run = assess(slot, runs)
    if state == "SUCCESS":
        try:
            state = "SUCCESS" if check_readback(repo, run["id"]) else "READBACK_MISSING"
        except (urllib.error.URLError, zipfile.BadZipFile, TimeoutError) as exc:
            # Inability to inspect logs is not proof of a failed scheduled run.
            print("NBA_SCHEDULE_MONITOR LOG_CHECK_UNAVAILABLE", type(exc).__name__)
            return
    print("NBA_SCHEDULE_MONITOR", state, slot.isoformat())
    if state in ("SUCCESS", "PENDING", "WAIT"):
        return
    title = "[NBA Schedule Health] " + slot.strftime("%Y-%m-%d %H:%M KST")
    existing = api(f"/repos/{repo}/issues?state=all&per_page=100")
    if any(i.get("title") == title for i in existing):
        print("NBA_SCHEDULE_MONITOR ISSUE_EXISTS")
        return
    run_link = run.get("html_url") if run else f"https://github.com/{repo}/actions/workflows/{WORKFLOW}"
    body = (f"NBA scheduled pipeline health check: **{state}**.\\n\\n"
            f"Expected slot: {slot.isoformat()}\\n"
            f"Run: {run_link}\\n\\n"
            "Check scheduled execution, dashboard update and READBACK_VERIFIED=true. "
            "Do not infer customer email or NBA decision outcomes from this alert.")
    issue = api(f"/repos/{repo}/issues", "POST", {"title": title, "body": body})
    print("NBA_SCHEDULE_MONITOR ISSUE_CREATED", issue["html_url"])


if __name__ == "__main__":
    main()
