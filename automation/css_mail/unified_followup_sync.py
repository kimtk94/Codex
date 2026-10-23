#!/usr/bin/env python3
"""Idempotent CSS approvals -> consolidated private Google Sheets dashboard.

No customer email is sent and no Salesforce object is mutated. Never infer IsActive.
"""
import datetime as dt
import json, os, re, sys, urllib.parse
from collections import defaultdict
import incremental_sync as css

DST=os.getenv("SFDC_UNIFIED_SHEET_ID","1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI")
SRC=os.getenv("CSS_SHEET_ID","1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY")
KST=dt.timezone(dt.timedelta(hours=9))
HEAD=["Approval KST","AMEA Quotation ID","Quotation Name","SFDC Record ID","Approval Evidence","Week Status","SFDC Direct Link","Active","Amount KRW","Source","Link Verification"]
def req(s,method,url,**kw):
    return css.api(s,method,url,**kw)
def base(book):return "https://sheets.googleapis.com/v4/spreadsheets/"+book
def get(s,book,tab,cell):
    addr=urllib.parse.quote("'"+tab+"'!"+cell,safe="")
    return req(s,"GET",base(book)+"/values/"+addr).get("values",[])
def put(s,book,tab,cell,data,mode="USER_ENTERED"):
    addr=urllib.parse.quote("'"+tab+"'!"+cell,safe="")
    return req(s,"PUT",base(book)+"/values/"+addr+"?valueInputOption="+mode,json={"values":data})
def ensure(s,book,title):
    sheets=req(s,"GET",base(book)+"?fields=sheets.properties(title,sheetId,gridProperties)")
    found={x["properties"]["title"]:x["properties"] for x in sheets.get("sheets",[])}
    if title not in found:
        req(s,"POST",base(book)+":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":title,"gridProperties":{"rowCount":2000,"columnCount":20,"frozenRowCount":1}}}}]})
def dateval(v):
    v=str(v or "")
    if "T" in v:
        try:return dt.datetime.fromisoformat(v.replace("Z","+00:00")).astimezone(KST).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:pass
    return v
def key(r):
    rec=str(r.get("id") or "").strip()
    return "sf:"+rec if re.fullmatch(r"a0P[A-Za-z0-9]{12,15}",rec) else "qid:"+str(r.get("name") or "").strip()
def week_start(d):
    # Friday–Thursday, preserving calendar-year crossover.
    return d-dt.timedelta(days=(d.weekday()-4)%7)
def main():
    s=css.authorize()
    old=get(s,SRC,"Quotation Approval List","A1:P10000")
    auto=get(s,SRC,"Quotation Approval Auto","A1:L10000")
    unified={}
    for r in old[1:]:
        if len(r)<9:continue
        it={"date":dateval(r[3]),"quote":r[7],"name":r[6],"id":r[8],"evidence":"VERIFIED_LEGACY_RECORD","source":"Quotation Approval List"}
        k=key(it)
        if k not in ("qid:","sf:"):unified[k]=it
    for r in auto[1:]:
        if len(r)<6 or r[0]=="":continue
        it={"date":dateval(r[0]),"quote":r[1],"name":r[2],"id":r[3],"evidence":r[5],"source":r[7] if len(r)>7 else ""}
        if it["evidence"] not in ("APPROVED_TEXT","EXISTS_IN_LEGACY","VERIFIED_LEGACY_RECORD"):continue
        k=key(it)
        if k not in ("qid:","sf:") and (k not in unified or it["date"]>unified[k]["date"]):unified[k]=it
    if not unified:raise RuntimeError("No approved quotations; refuse empty overwrite")
    items=sorted(unified.values(),key=lambda r:r["date"],reverse=True)
    data=[HEAD]
    per_week=defaultdict(int)
    for r in items:
        day=dt.date.fromisoformat(r["date"][:10])
        first=week_start(day); last=first+dt.timedelta(days=6)
        period=first.isoformat()+" ~ "+last.isoformat()
        per_week[(first,last)]+=1
        url=("https://novogene.lightning.force.com/lightning/r/Quotation__c/"+r["id"]+"/view") if re.fullmatch(r"a0P[A-Za-z0-9]{12,15}",r["id"]) else ""
        link='=HYPERLINK("'+url+'","Open SFDC")' if url else ""
        data.append([r["date"],r["quote"],r["name"],r["id"],r["evidence"],period,link,"UNVERIFIED","",r["source"],"LINK_NOT_AUTHENTICATED"])
    ensure(s,DST,"Quote Approval Dedup")
    # Write only this generated table; full historical feed, no destructive row clear.
    put(s,DST,"Quote Approval Dedup","A1",data)
    # Mark any trailing stale generated rows, without touching unrelated tabs.
    prior=get(s,DST,"Quote Approval Dedup","A1:A2000")
    if len(prior)>len(data):
        tail=[[""]*11 for _ in range(len(prior)-len(data))]
        put(s,DST,"Quote Approval Dedup","A"+str(len(data)+1),tail,"RAW")
    today=dt.datetime.now(KST).date(); this_start=week_start(today)
    existing=get(s,DST,"SFDC Weekly Overview","A1:P1000")
    idx={str(r[0]):i+1 for i,r in enumerate(existing[1:],2) if r}
    # Weekly row is updated at its own calendar key; never replace a previous week.
    per_week.setdefault((this_start,this_start+dt.timedelta(days=6)),0)
    for (first,last),count in sorted(per_week.items(),reverse=True):
        label=first.isoformat()
        if label not in idx:
            row=max(2,len(existing)+1)
            idx[label]=row;existing.append([])
            put(s,DST,"SFDC Weekly Overview","A"+str(row),[[label,last.isoformat(),"FRI_THU_IN_PROGRESS" if first==this_start else "FRI_THU_VERIFIED",0,0,0,0,0,0,0]])
        row=idx[label]
        put(s,DST,"SFDC Weekly Overview","G"+str(row),[[count,count]])
    # Dashboard links to the true current-week row even if data is not in row 2.
    ensure(s,DST,"Executive Dashboard")
    current_row=idx.get(this_start.isoformat())
    if current_row:
        p="'SFDC Weekly Overview'!"
        put(s,DST,"Executive Dashboard","E9",[['="WEEKLY RESULT | "&TEXT('+p+'A'+str(current_row)+',"yyyy-mm-dd")&" ~ "&TEXT('+p+'B'+str(current_row)+',"yyyy-mm-dd")&IF('+p+'C'+str(current_row)+'="FRI_THU_IN_PROGRESS"," [진행 중]"," [마감]")']])
        for address,col in [("F10","A"),("H10","C"),("F11","G"),("H11","H"),("F12","I"),("H12","J"),("F13","D"),("H13","F")]:
            if address=="F10":formula='=TEXT('+p+'A'+str(current_row)+',"yyyy-mm-dd")&" ~ "&TEXT('+p+'B'+str(current_row)+',"yyyy-mm-dd")'
            elif address=="H10":formula='=IF('+p+'C'+str(current_row)+'="FRI_THU_IN_PROGRESS","진행 중","마감")'
            else:formula='=IFERROR('+p+col+str(current_row)+',0)'
            put(s,DST,"Executive Dashboard",address,[[formula]])
        put(s,DST,"Executive Dashboard","F14",[[f'=IF({p}O{current_row}="","미검증",{p}O{current_row})']])
        put(s,DST,"Executive Dashboard","H14",[[f'=IF({p}P{current_row}="","미검증",{p}P{current_row})']])
    ensure(s,DST,"Automation Health")
    stamp=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    put(s,DST,"Automation Health","A1",[["Component","Last success KST","State","Detail"],["CSS Quotes",stamp,"PASS","Unique="+str(len(items))+" current_week="+str(per_week.get((this_start,this_start+dt.timedelta(days=6)),0))]])
    print("UNIFIED_QUOTES_PASS unique="+str(len(items))+" current_week="+str(per_week.get((this_start,this_start+dt.timedelta(days=6)),0))+" historical_weeks="+str(len(per_week)))
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("UNIFIED_QUOTES_FAILED "+type(e).__name__,file=sys.stderr);raise
