#!/usr/bin/env python3
"""Fail-closed read-only briefing from pre-exported domain snapshots."""
import argparse
import datetime as dt
import json
import re
from pathlib import Path

DOMAINS=("is_ckd","css","kalman","harness")
VALID={"COMPLETE","RUNNING","BLOCKED","REVIEW_REQUIRED","UNKNOWN"}
MAX_AGE_HOURS=26
def clean(value,limit=240):
    text=str(value or "").replace("\r"," ").replace("\n"," ")
    text=re.sub(r"(?i)(bearer\s+|gh[pousr]_|sk-[a-z0-9_-]+|password\s*[:=]|token\s*[:=])\S+", "[REDACTED]",text)
    return text[:limit]
def load(folder,domain,now):
    item={"domain":domain,"status":"UNKNOWN","summary":"No verified fresh snapshot",
          "next_action":"Check source adapter","requires_approval":False,"evidence":[]}
    path=folder/(domain+".json")
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size>65536:
            return item
        d=json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(d,dict) or d.get("domain")!=domain or d.get("status") not in VALID:
            return item
        when=dt.datetime.fromisoformat(str(d.get("observed_at","")).replace("Z","+00:00"))
        if when.tzinfo is None:
            return item
        age=(now-when.astimezone(dt.timezone.utc)).total_seconds()
        if age< -300 or age>MAX_AGE_HOURS*3600:
            item["summary"]="Snapshot missing, stale, or future-dated"
            return item
        ev=d.get("evidence",[])
        if not isinstance(ev,list) or len(ev)>10 or any(not isinstance(s,str) for s in ev):
            return item
        for field in ("summary","next_action"):
            if not isinstance(d.get(field),str):
                return item
        if not isinstance(d.get("requires_approval",False),bool):
            return item
        return {"domain":domain,"status":d["status"],"summary":clean(d["summary"]),
                "next_action":clean(d["next_action"]),
                "requires_approval":d.get("requires_approval",False),
                "observed_at":when.isoformat(),
                "evidence":[clean(x,180) for x in ev[:5]]}
    except (OSError,ValueError,TypeError,UnicodeError,OverflowError):
        return item
def review_queue(folder,now):
    """Deterministic human review queue, never an execution queue."""
    severity={"BLOCKED":0,"REVIEW_REQUIRED":1,"UNKNOWN":2,"RUNNING":3,"COMPLETE":4}
    tasks=[]
    for item in (load(folder,d,now) for d in DOMAINS):
        if item["status"] in ("BLOCKED","REVIEW_REQUIRED","UNKNOWN") or item["requires_approval"]:
            tasks.append({
                "id":item["domain"]+":review",
                "domain":item["domain"],
                "status":item["status"],
                "priority":severity[item["status"]],
                "requires_approval":item["requires_approval"],
                "next_action":item["next_action"],
                "evidence":item["evidence"],
                "execution_allowed":False
            })
    return sorted(tasks,key=lambda item:(item["priority"],item["domain"]))

def report(folder,now):
    items=[load(folder,d,now) for d in DOMAINS]
    lines=["# Unified Daily Briefing", "", "Generated UTC: "+now.isoformat(),
           "", "> READ ONLY. GitHub workflow success is not scientific or trading validation.",""]
    queue=[]
    for x in items:
        lines += ["## "+x["domain"]+" — "+x["status"],
                  "- Summary: "+x["summary"],"- Next: "+x["next_action"],
                  "- Approval: "+("YES" if x["requires_approval"] else "NO"),
                  "- Evidence: "+("; ".join(x["evidence"]) or "none"),""]
        if x["status"] in {"UNKNOWN","BLOCKED","REVIEW_REQUIRED"} or x["requires_approval"]:
            queue.append(x)
    lines += ["## Human review queue"]
    lines += ["- "+x["domain"]+": "+x["next_action"] for x in queue] or ["- None"]
    lines += ["","All tasks are proposals; this program executes no queued actions."]
    return "\n".join(lines)+"\n"
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--snapshots",required=True,type=Path)
    p.add_argument("--queue-json",type=Path,default=None)
    args=p.parse_args()
    now=dt.datetime.now(dt.timezone.utc)
    if args.queue_json is not None:
        payload={"schema":"unified-human-review-queue-v1",
                 "generated_at":now.isoformat(),
                 "tasks":review_queue(args.snapshots,now)}
        args.queue_json.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\\n",encoding="utf-8")
    print(report(args.snapshots,now),end="")
if __name__=="__main__":
    main()
