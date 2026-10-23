#!/usr/bin/env python3
"""CSS follow-up priority scoring from existing Action Center, read-only source."""
import datetime as dt
from unified_followup_sync import DST, KST, get, put, ensure
import incremental_sync as css
HEAD=["Priority score","Priority level","Task ID","Institution","Project ID","Task Type","Due date","Status","Recommended action","Data source"]
def score(status,priority,due,task):
    points=40 if priority=="긴급" else 20 if priority=="높음" else 5
    overdue=0
    try:overdue=max(0,(dt.datetime.now(KST).date()-dt.date.fromisoformat(due[:10])).days)
    except (ValueError,TypeError):pass
    points+=min(40,overdue*2)
    if "QC" in task or "장비" in task:points+=10
    if status in ("완료","CLOSED","DONE"):return 0,"CLOSED"
    return points,"P0" if points>=65 else "P1" if points>=35 else "P2"
def main():
    s=css.authorize()
    src=get(s,DST,"CSS Action Center","A1:P3000")
    if not src:raise RuntimeError("NO_ACTION_CENTER")
    out=[]
    for r in src[1:]:
        r=r+[""]*(16-len(r))
        status,priority,owner,due,task_id,task_type,_,project,institution,_,_,_,_,_,recommended,_=r[:16]
        if not task_id:continue
        value,level=score(status,priority,due,task_type)
        if level=="CLOSED":continue
        out.append([value,level,task_id,institution,project,task_type,due,status,recommended,"CSS Action Center"])
    out.sort(key=lambda x:(-x[0],x[6],x[2]))
    ensure(s,DST,"Follow-up Priority")
    put(s,DST,"Follow-up Priority","A1",[HEAD]+out)
    ensure(s,DST,"Automation Health")
    updated=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    put(s,DST,"Automation Health","A6",[["Follow-up Priority",updated,"PASS","open="+str(len(out))+" p0="+str(sum(x[1]=="P0" for x in out))]])
    print("FOLLOWUP_PRIORITY_PASS open="+str(len(out))+" p0="+str(sum(r[1]=="P0" for r in out)))
if __name__=="__main__":main()
