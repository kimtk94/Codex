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
def report_due_slot(now,grace_minutes=40):
    """Latest due 09/12/17 KST subscription; overnight uses yesterday 17."""
    if now.tzinfo is None:raise ValueError("NAIVE_CURRENT_TIME")
    local=now.astimezone(KST)
    for offset in (0,-1):
        day=local.date()+dt.timedelta(days=offset)
        for hour in (17,12,9):
            slot=dt.datetime.combine(day,dt.time(hour),tzinfo=KST)
            if local>=slot+dt.timedelta(minutes=grace_minutes):return slot
    raise RuntimeError("REPORT_SLOT_UNAVAILABLE")


def report_slot_state(sources,now):
    due=report_due_slot(now)
    if any(t is None or t>now+dt.timedelta(minutes=10) for t in sources):
        return "BLOCK",due
    if all(t>=due for t in sources):return "PASS",due
    late_hours=(now-due).total_seconds()/3600
    return ("WARN" if 0<=late_hours<=6 else "BLOCK"),due


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
    month=now.astimezone(KST).strftime("%Y-%m")
    l,n=data["lifecycle"],data["net"]
    require(l,["Month","Actual Invoice KRW"])
    require(n,["Month","Issued Invoice Gross KRW (VAT incl)","Issued Net Revenue KRW (VAT excl)"])
    lr=next((r for r in l[1:] if v(r,0)==month),None)
    nr=next((r for r in n[1:] if v(r,0)==month),None)
    vatok=False
    observed="MISSING_CURRENT_MONTH_"+month
    if lr and nr:
        try:
            gross,count=amount(v(lr,1)),amount(v(lr,5))
            ngross,nnet,ncount=amount(v(nr,1)),amount(v(nr,2)),amount(v(nr,4))
            observed=f"count={count};gross={gross};net={nnet}"
            vatok=(gross==ngross and count==ncount and count>=0 and nnet<=gross
                   and v(nr,8)=="INVOICE_FILENAME_VERIFIED_NET;PENDING_VAT_UNVERIFIED"
                   and fresh(v(lr,11),now,6) and fresh(v(nr,7),now,6))
        except ValueError:observed="UNVERIFIED_AMOUNT"
    add("Revenue","Gross/net invoice parity","PASS" if vatok else "BLOCK",
        "DATA",v(nr,7),observed,
        "VAT basis verified" if vatok else "Source parity/freshness invalid; never use gross as net")
    a=data["authority"]
    require(a,["Month","Source Tab","Source Role"])
    ar=next((r for r in a[1:] if v(r,0)==month and
             v(r,2)=="CANONICAL_ACTUAL_GROSS"),None)
    an=next((r for r in a[1:] if v(r,0)==month and
             v(r,2)=="CANONICAL_ISSUED_NET"),None)
    olds=[r for r in a[1:] if v(r,0)==month and v(r,2).startswith("LEGACY")]
    legacy_ok=(len(olds)>=3 and
               all(v(r,7)=="NO" and v(r,6)=="STALE_SOURCE_DO_NOT_USE" for r in olds)
               if month=="2026-10" else all(v(r,7)=="NO" for r in olds))
    try:
        parity=bool(lr and nr and ar and an
            and amount(v(ar,3))==amount(v(lr,5))
            and amount(v(ar,4))==amount(v(lr,1))
            and amount(v(an,3))==amount(v(nr,4))
            and amount(v(an,4))==amount(v(nr,2)))
    except ValueError:parity=False
    ok=bool(ar and an and legacy_ok and parity
        and v(ar,7)=="YES" and v(an,7)=="YES"
        and v(ar,6)=="MATCHED_TO_NET_AUDIT"
        and v(an,6)=="MATCHED_TO_INVOICE_SOURCE"
        and fresh(v(ar,8),now,6) and fresh(v(an,8),now,6))
    add("Revenue","Canonical vs stale legacy","PASS" if ok else "BLOCK","DATA",v(ar,8),
        f"month={month};canonical={int(bool(ar))+int(bool(an))};legacy_flagged={len(olds)}",
        "Current-month invoice authority verified" if ok
        else "Current month missing/stale/mismatch; do not reuse previous month's PASS")
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
    if good:
        state,due=report_slot_state(t,now)
        age=max((now-z).total_seconds()/3600 for z in t)
    else:
        state,due,age="BLOCK",report_due_slot(now),9999
    add("SFDC","Three subscription Reports",state,"DATA",v(by.get("Leads"),1),
        f"entities={len(by)};due_KST={due.strftime('%Y-%m-%d %H:%M')};"
        f"source_age_h={round(age,1)}",
        "Expected report slot verified against original attachments" if state=="PASS"
        else "One or more scheduled 09/12/17 QQ report attachments missing/invalid")
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
    # A failed body workflow can append verified MIME rows before the strict
    # post-write readback aborts. A prior successful progress snapshot must
    # never conceal that more recent failed execution.
    body_health=next((r for r in reversed(rows[1:]) if v(r,0)=="CSS Mail Body"),None)
    body_ok=bool(body_health and v(body_health,2)=="BACKFILL_ACTIVE"
                 and fresh(v(body_health,1),now,8))
    add("Mail","Body workflow execution","PASS" if body_ok else "BLOCK",
        "DATA",v(body_health,1),v(body_health,2) or "NO_HEALTH_EVIDENCE",
        "Body workflow heartbeat healthy (independent of cache completeness)" if body_ok
        else "Latest body workflow failed/stale; backfill snapshot may precede failed writes")
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
