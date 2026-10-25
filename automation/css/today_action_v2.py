"""Read-only adapters for QQ unanswered mail and SFDC quote review.

Emits a unified Top 10 CSV; never sends mail or mutates source systems.
"""
import argparse
import csv
from datetime import date
from pathlib import Path
from today_action_top10 import HEADERS, build, clean, read_csv

YES={"TRUE","YES","1","Y"}
DONE={"DONE","CLOSED","RESOLVED","EXCLUDED","SKIPPED","COMPLETED"}
MONITOR={"MONITOR_0_1D","NONE","DISMISSED","CLOSED","EXCLUDED"}
def yes(v): return clean(v).upper() in YES
def csvout(path, rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",encoding="utf-8-sig",newline="") as f:
        writer=csv.DictWriter(f,fieldnames=HEADERS)
        writer.writeheader(); writer.writerows(rows)

def mail_rows(rows):
    result=[]
    for r in rows:
        uid=clean(r.get("Thread UID") or r.get("uid"))
        if not uid or yes(r.get("Excluded?") or r.get("exclude")): continue
        if yes(r.get("exclude_sender")) or clean(r.get("Sender Exclusion") or r.get("Mail UID Exclusion")): continue
        action=clean(r.get("Reviewer Mail Action")).upper()
        if action in DONE or action in {"IGNORE","REMOVE","REPLIED","ANSWERED","REPLY_SENT","SENT_CONFIRMED","DELEGATE_REPLIED"}: continue
        queue=clean(r.get("Effective Queue") or r.get("Triage Priority")).upper()
        if not queue: queue=clean(r.get("review_status")).upper()
        if queue in MONITOR or queue.startswith("MONITOR_"): continue
        try: days=int(float(clean(r.get("Aging Days"))))
        except (ValueError,TypeError): days=-1
        # Older threads remain available in the 60-day review ledger, but\n        # are not actionable in the current 2-30 day Action Center.\n        if days < 2 or days > 30: continue
        evidence=clean(r.get("Reply Evidence") or r.get("reply_status"))
        # Not every reply_status is proof. Only explicit sent evidence suppresses.
        if evidence.upper() in {"SENT_CONFIRMED","REPLIED","ANSWERED","REPLY_SENT","DONE","PC_REPLIED","TS_REPLIED","DELEGATE_REPLIED"}: continue
        score=min(89,65+min(14,days))
        result.append({"Priority":"P1","Score":score,"Source":"QQ_MAIL","Record ID":uid,
          "Institution":"","Customer":clean(r.get("Sender Email") or r.get("from_email")),
          "Project ID":clean(r.get("Project IDs") or r.get("project_ids")),
          "Issue":clean(r.get("Subject / Thread") or r.get("subject")),
          "Action":"발신/대리응답 확인 후 미응답이면 회신","Due Date":"","Final Contact Date":"",
          "Verification":"REVIEW_NOT_CONFIRMED_UNANSWERED","Evidence":evidence,
          "Source Tab":"BI Unanswered Triage"})
    return result

def quote_rows(rows):
    result=[]
    for r in rows:
        quote_id=clean(r.get("Salesforce Quote ID"))
        if not quote_id: continue
        approval=clean(r.get("Approval")).upper()
        active=clean(r.get("Active")).upper()
        reason=clean(r.get("Review Reason"))
        relation=clean(r.get("Relation Status")).upper()
        if approval not in {"APPROVED","APPROVAL GRANTED"} or active not in {"ACTIVE","TRUE","YES"}: continue
        # Review queue is for exception handling, not every approved/active quote.
        if not reason and relation in {"MATCHED","LINKED","OK","VALID"}: continue
        if not reason and not relation: continue
        if relation in {"CLOSED","RESOLVED","DONE"}: continue
        result.append({"Priority":"P1","Score":62,"Source":"SFDC_QUOTE","Record ID":quote_id,
          "Institution":"","Customer":"","Project ID":clean(r.get("Opportunity ID")),
          "Issue":reason or "견적 연결 상태 확인","Action":"Active/Approved 견적 연결 및 고객 후속조치 확인",
          "Due Date":"","Final Contact Date":"","Verification":"QUOTE_LINK_REVIEW",
          "Evidence":clean(r.get("AMEA ID")),"Source Tab":"Quote Review Queue"})
    return result

def assemble(css,leads,mail,quotes,today,limit=10):
    baseline,_=build(css,leads,today,limit=100000)
    candidates=baseline+mail_rows(mail)+quote_rows(quotes)
    # Explicit stable IDs; no fuzzy matching of unrelated clients.
    unique={}
    for r in candidates:
        key=(r["Source"].upper(),r["Record ID"].upper())
        if key not in unique or r["Score"]>unique[key]["Score"]: unique[key]=r
    ranked=sorted(unique.values(),key=lambda r:(-r["Score"],r["Source"],r["Record ID"]))
    caps={"SFDC":3,"CSS":3,"LEAD":2,"QQ_MAIL":2,"SFDC_QUOTE":2}
    counts={}
    output=[]
    for row in ranked:
        source=row["Source"].upper()
        if counts.get(source,0)>=caps.get(source,2):
            continue
        output.append(row)
        counts[source]=counts.get(source,0)+1
        if len(output)>=limit:
            break
    for idx,r in enumerate(output,1):r["Rank"]=idx
    return output,len(unique)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--unified-csv",type=Path,required=True)
    p.add_argument("--lead-csv",type=Path)
    p.add_argument("--mail-csv",type=Path)
    p.add_argument("--quote-csv",type=Path)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--today",type=date.fromisoformat,default=date.today())
    p.add_argument("--limit",type=int,default=10)
    a=p.parse_args()
    if a.limit<1:p.error("--limit must be positive")
    rows,count=assemble(read_csv(a.unified_csv),read_csv(a.lead_csv),read_csv(a.mail_csv),read_csv(a.quote_csv),a.today,a.limit)
    csvout(a.output,rows)
    print(f"TODAY_ACTION_CANDIDATES={count} TOP={len(rows)} OUTPUT={a.output}")

if __name__=="__main__":main()
