"""GitHub Issue alert for unresolved *scheduled* progress automation failures."""
import json
import os
import urllib.request
from ops_failure_audit import classify

REPO="kimtk94/Codex"
WORKFLOWS=("automation-progress-audit.yml","automation-progress-evidence-publisher.yml","automation-gate-gaps-sheet.yml")

def incidents_for_workflow(runs, workflow):
    return [{"workflow":workflow,"run_id":i["failed_run_id"],"recovery_run_id":i["recovery_run_id"]}
            for i in classify(runs) if i["state"]=="UNRESOLVED"]

def issue_title(item):
    return "[Automation OPS] "+item["workflow"]+" run "+str(item["run_id"])+" failed"

def get_json(path,token,method="GET",payload=None):
    data=json.dumps(payload).encode() if payload is not None else None
    request=urllib.request.Request("https://api.github.com/repos/"+REPO+"/"+path,
        data=data,method=method,headers={
        "Authorization":"Bearer "+token,"Accept":"application/vnd.github+json",
        "Content-Type":"application/json","User-Agent":"automation-ops-watch"})
    with urllib.request.urlopen(request,timeout=25) as response:
        return json.load(response)

def main():
    token=os.environ["GITHUB_TOKEN"]
    created=[]
    observed=[]
    for wf in WORKFLOWS:
        result=get_json("actions/workflows/"+wf+"/runs?event=schedule&per_page=100",token)
        run_rows=[{"id":r["id"],"event":r.get("event"),"status":r.get("status"),
                   "conclusion":r.get("conclusion"),"created_at":r.get("created_at")}
                  for r in result.get("workflow_runs",[])]
        observed.extend(incidents_for_workflow(run_rows,wf))
    # Issues are an audit channel; GitHub notifications depend on repository subscriptions.
    issues=get_json("issues?state=all&per_page=100",token)
    existing={i.get("title") for i in issues if "pull_request" not in i}
    for item in observed:
        title=issue_title(item)
        if title in existing: continue
        url="https://github.com/"+REPO+"/actions/runs/"+str(item["run_id"])
        body="Scheduled automation run requires investigation.\n\nRun: "+url+"\nWorkflow: "+item["workflow"]+"\n\nThis issue is an alert record, not proof of message delivery or recovery."
        created.append(get_json("issues",token,"POST",{"title":title,"body":body}).get("html_url"))
        existing.add(title)
    print(json.dumps({"unresolved":len(observed),"created_issues":created},ensure_ascii=False))

if __name__=="__main__":
    main()
