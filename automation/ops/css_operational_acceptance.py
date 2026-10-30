#!/usr/bin/env python3
"""Read-only operational acceptance evidence; writes a generated status ledger only.

CI green is NOT authenticated browser E2E or business acceptance.
No customer emails, SFDC mutations, payment changes or Vercel promotion.
"""
import datetime as dt
import re
import sys
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"css_mail"))
from unified_followup_sync import DST,KST,get,put,ensure
import incremental_sync as css

TAB="CSS Operational Acceptance"
HEAD=["Area","Check","Result","Gate","Evidence KST","Observed","Next action","Checked KST"]
SOURCES={
 "health":("Automation Health","A1:D45"),
 "reports":("SFDC Email Ingest Audit","A1:J8"),
 "lifecycle":("BI Revenue Lifecycle Monthly","A1:Q24"),
 "net":("BI Revenue Net VAT Monthly","A1:I24"),
 "authority":("Revenue Source Authority","A1:J24"),
 "mail":("CSS Mail Backfill Status","A1:O2"),
 "feishu":("Feishu Source Manifest","A1:G10"),
 "payment":("Payment Reconciliation QC","A1:C22"),
}
def v(row,i):
    return str(row[i]).strip() if row and i<len(row) and row[i] is not None else ""
def amount(value):
    x=str(value or "").replace(",","").replace("₩","").replace(" KRW","").strip()
    if not re.fullmatch(r"\d+",x):raise ValueError("UNVERIFIED_NUMBER")
    return int(x)
def stamp(x):
    s=str(x or "").strip()
    try:
        if s.endswith(" KST"):
            return dt.datetime.strptime(s[:-4],"%Y-%m-%d %H:%M:%S").replace(tzinfo=KST)
        z=dt.datetime.fromisoformat(s.replace("Z","+00:00"))
        return z if z.tzinfo else None
    except ValueError:return None
def fresh(x,now,hours):
    z=stamp(x)
    return bool(z and 0<=(now-z).total_seconds()<=hours*3600)
def require(rows,prefix):
    if not rows or rows[0][:len(prefix)]!=prefix:raise ValueError("BAD_SOURCE_HEADER_"+prefix[0])
def build(data,now):
    checked=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    result=[HEAD]
    def add(area,check,state,gate,evidence,observed,action):
        if state not in ("PASS","WARN","BLOCK"):raise ValueError("BAD_STATE")
        result.append([area,check,state,gate,evidence,observed,action,checked])
    rows=data["health"]
    require(rows,["Component","Last success KST","State"])
    qq=next((r for r in reversed(rows[1:]) if v(r,0)=="CSS Mail"),None)
    qqok=bool(qq and v(qq,2)=="PASS" and fresh(v(qq,1),now,3))
    add("QQ","Inbox/Sent source","PASS" if qqok else "BLOCK","DATA",v(qq,1),v(qq,2),
        "Fresh source verified" if qqok else "Source heartbeat not PASS within 3 hours")
    l,n=data["lifecycle"],data["net"]
    require(l,["Month","Actual Invoice KRW"])
    require(n,["Month","Issued Invoice Gross KRW (VAT incl)","Issued Net Revenue KRW (VAT excl)"])
    lr=next((r for r in l[1:] if v(r,0)=="2026-10"),None)
    nr=next((r for r in n[1:] if v(r,0)=="2026-10"),None)
    vatok=False
    observed="MISSING_CURRENT_MONTH"
    if lr and nr:
        try:
            gross,count=amount(v(lr,1)),amount(v(lr,5))
            ngross,nnet,ncount=amount(v(nr,1)),amount(v(nr,2)),amount(v(nr,4))
            observed=f"count={count};gross={gross};net={nnet}"
            vatok=(gross==ngross and count==ncount and count>0 and nnet<=gross
                   and v(nr,8)=="INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"
                   and fresh(v(lr,11),now,6) and fresh(v(nr,7),now,6))
        except ValueError:observed="UNVERIFIED_AMOUNT"
    add("Revenue","Gross/net invoice parity","PASS" if vatok else "BLOCK",
        "DATA",v(nr,7),observed,
        "VAT basis verified" if vatok else "Source parity/freshness invalid; never use gross as net")
    a=data["authority"]
    require(a,["Month","Source Tab","Source Role"])
    ar=next((r for r in a[1:] if v(r,2)=="CANONICAL_ACTUAL_GROSS"),None)
    an=next((r for r in a[1:] if v(r,2)=="CANONICAL_ISSUED_NET"),None)
    olds=[r for r in a[1:] if v(r,2).startswith("LEGACY")]
    ok=bool(ar and an and len(olds)>=3
       and all(v(r,7)=="YES" for r in (ar,an))
       and all(v(r,7)=="NO" and v(r,6)=="STALE_SOURCE_DO_NOT_USE" for r in olds)
       and fresh(v(ar,8),now,6) and fresh(v(an,8),now,6))
    add("Revenue","Canonical vs stale legacy","PASS" if ok else "BLOCK","DATA",v(ar,8),
        f"canonical={int(bool(ar))+int(bool(an))};legacy_flagged={len(olds)}",
        "Legacy snapshots excluded from KPI" if ok else "KPI authority missing or stale")
    r=data["reports"]
    require(r,["Entity","Source Received KST","Ingest Checked KST"])
    by={v(z,0):z for z in r[1:] if v(z,0) in ("Leads","Opportunities","Quotation")}
    good=len(by)==3
    for name in ("Leads","Opportunities","Quotation"):
        row=by.get(name)
        good=bool(good and row and v(row,8) in ("STAGED_NOT_PROMOTED","PRESERVED_NO_NEW_REPORT")
                  and v(row,6)=="0" and re.fullmatch(r"[a-f0-9]{64}",v(row,7)))
    t=[stamp(v(by.get(n),1)) for n in ("Leads","Opportunities","Quotation")] if good else []
    good=bool(good and all(t))
    age=max((now-z).total_seconds()/3600 for z in t) if good else 9999
    state="PASS" if good and 0<=age<=6 else "WARN" if good and 0<=age<=16 else "BLOCK"
    add("SFDC","Three subscription Reports",state,"DATA",v(by.get("Leads"),1),
        f"entities={len(by)};oldest_age_hours={round(age,1)}",
        "Staged reports only, never CRM Save; confirm 17:00 delivery" if state!="PASS"
        else "Hashed staged report evidence (not CRM direct write)")
    m=data["mail"]
    require(m,["Updated At KST","State","QQ Staged Headers","Web Cached UID"])
    z=m[1] if len(m)>1 else None
    try:
        remain,err,ready=amount(v(z,7)),amount(v(z,11)),amount(v(z,4))
        st="BLOCK" if err or not fresh(v(z,0),now,8) else "WARN" if remain else "PASS"
        observed=f"body_ready={ready};remaining={remain};errors={err}"
    except ValueError:st,observed="BLOCK","INVALID_BODY_BACKFILL_COUNTS"
    add("Mail","Body cache completeness",st,"DATA",v(z,0),observed,
        "Exact-UID on-demand lookup exists; backfill incomplete" if st=="WARN"
        else "Review cache heartbeat and source MIME, do not invent bodies")
    f=data["feishu"]
    require(f,["Source","Source Date","Synced At KST"])
    online=next((r for r in f[1:] if v(r,0)=="Online-Project"),None)
    try:
        online_ok=bool(online and v(online,5)=="BASE_FIELDS" and amount(v(online,4))>0
            and dt.date.fromisoformat(v(online,1))>=now.astimezone(KST).date()-dt.timedelta(days=1)
            and fresh(v(online,2),now,6))
    except ValueError:online_ok=False
    add("Feishu","Online projects","PASS" if online_ok else "WARN","DATA",
        v(online,2),f"source_date={v(online,1)}",
        "Verified projects" if online_ok else "Refresh original Online/Payment source separately")
    pay=data["payment"]
    require(pay,["Payment Reconciliation QC"])
    info={v(q,0):v(q,1) for q in pay[2:]}
    collected=info.get("Invoice-level verified paid count","UNKNOWN")
    paidok=bool(re.fullmatch(r"\d+",collected))
    add("Payment","Paid invoice evidence","PASS" if paidok else "BLOCK","FINANCE",
        v(pay[0],1),f"verified_paid_count={collected}",
        "Receipt evidence required; unknown != unpaid" if not paidok else "Receipt count documented")
    add("Release","Owner-authenticated Preview E2E","BLOCK","RELEASE","",
        "NO_AUTHENTICATED_LIVE_BROWSER_EVIDENCE",
        "Owner login, exact UID body and API 200 required; mocked Chromium is insufficient")
    add("Release","Production READY SHA parity","BLOCK","RELEASE","",
        "NO_PRODUCTION_RELEASE_RECEIPT",
        "Check Vercel routed Production SHA; never auto-promote from CI")
    blocks=[q for q in result[1:] if q[2]=="BLOCK" and q[3] in ("DATA","RELEASE")]
    add("Decision","Production acceptance","BLOCK" if blocks else "PASS","RELEASE","",
        f"release_and_data_blockers={len(blocks)}",
        "No automatic deployment, mail send or SFDC Save")
    return result
def main():
    api=css.authorize()
    d={k:get(api,DST,tab,span) for k,(tab,span) in SOURCES.items()}
    rows=build(d,dt.datetime.now(dt.timezone.utc))
    ensure(api,DST,TAB)
    old=get(api,DST,TAB,"A1:H20")
    if old and old[0]!=HEAD:raise RuntimeError("FOREIGN_STATUS_TAB_REFUSE_OVERWRITE")
    put(api,DST,TAB,"A1",rows,"RAW")
    back=get(api,DST,TAB,"A1:H"+str(len(rows)))
    if back!=[[str(x) for x in row] for row in rows]:
        raise RuntimeError("ACCEPTANCE_READBACK_MISMATCH")
    print("OPERATIONAL_ACCEPTANCE_PUBLISHED")
    for row in rows[1:]:print(row[0]+": "+row[1]+" = "+row[2])
    print("NO_CUSTOMER_SEND_NO_SFDC_SAVE_NO_VERCEL_PROMOTE")
if __name__=="__main__":main()
