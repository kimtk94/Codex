#!/usr/bin/env python3
"""Month-indexed Actual/Pending/Forecast from the linked project lifecycle.

Invoice numbers: actual only. Original unissued J Statements: pending only.
Unbilled projects without Statement: estimate only. No duplicate X forecasts.
Only >=2026-10 is treated as covered by this validated new QQ source.
"""
import datetime as dt
import re
import sys

import incremental_sync as css
from tax_invoice_extract import extract
from unified_followup_sync import DST, SRC, KST, get, put

TAB="BI Revenue Lifecycle Monthly"
HEAD=["Month","Actual Invoice KRW","Pending Verified KRW","Forecast KRW",
      "Combined KRW (verified + estimate)","Invoice Count","Open Statement Count",
      "Pending Amount Unknown","Forecast Projects","Partial Billing Reviews",
      "Data Quality","Snapshot KST"]
ALLOWED={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
FIRST="2026-10"

def cell(r,n):
    return str(r[n]) if n<len(r) and r[n] is not None else ""

def month_of(v):
    if not v:return ""
    try:
        return dt.datetime.fromisoformat(str(v).replace("Z","+00:00")).astimezone(KST).strftime("%Y-%m")
    except ValueError:
        return ""

def compute(invoice_rows,lifecycle_rows,now):
    invoices={}
    for row in invoice_rows[1:]:
        number=cell(row,0)
        if cell(row,10) not in ALLOWED or not re.fullmatch(r"209126\d{6}",number):
            continue
        subject=cell(row,6)
        if re.match(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",subject,re.I):
            continue
        if not re.match(r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",subject,re.I):
            continue
        result=extract(cell(row,5))
        if not result or result[4] is None:continue
        try:amount=int(cell(row,1))
        except ValueError:continue
        if number!=result[0] or amount!=result[4] or amount<=0:
            raise RuntimeError("Invoice filename amount mismatch: "+number)
        month=month_of(cell(row,7))
        if not month:raise RuntimeError("Unknown original invoice issue date: "+number)
        if month<FIRST:continue
        if number in invoices and invoices[number]!=(month,amount):
            raise RuntimeError("Duplicate invoice amount or date conflict: "+number)
        invoices[number]=(month,amount)

    buckets={}
    def bucket(month):
        if month not in buckets:
            buckets[month]={"actual":0,"invoice":0,"pending":0,"open":0,
                            "unknown":0,"forecast":0,"forecast_n":0,"partial":0}
        return buckets[month]
    for month,amount in invoices.values():
        p=bucket(month);p["actual"]+=amount;p["invoice"]+=1

    seen_projects=set()
    for row in lifecycle_rows[1:]:
        x=cell(row,0).upper()
        if not x:continue
        if x in seen_projects:raise RuntimeError("Duplicate project lifecycle row: "+x)
        seen_projects.add(x)
        billing=cell(row,16)
        month=cell(row,12)
        if not re.fullmatch(r"\d{4}-(?:0[1-9]|1[0-2])",month or ""):
            month=month_of(cell(row,21)) or "UNSCHEDULED"
        if month!="UNSCHEDULED" and month<FIRST:continue
        open_j=[j.strip() for j in cell(row,20).split("|") if j.strip()]
        p=bucket(month)
        if open_j:
            # Pending belongs to original Statement notice month, not Feishu forecast.
            pending_month=month_of(cell(row,21)) or month
            p=bucket(pending_month)
            p["open"]+=len(open_j)
            label=cell(row,23)
            m=re.fullmatch(r"AMOUNT_VERIFIED (\d+)/(\d+)",label)
            verified_n=int(m.group(1)) if m else 0
            if not m or int(m.group(2))!=len(open_j) or verified_n>len(open_j):
                raise RuntimeError("Inconsistent pending verification status for "+x)
            p["unknown"]+=len(open_j)-verified_n
            pending_value=cell(row,22)
            if verified_n:
                try:value=int(float(pending_value))
                except ValueError:raise RuntimeError("Missing verified pending amount for "+x)
                if value<=0:raise RuntimeError("Nonpositive verified pending for "+x)
                p["pending"]+=value
        if "ISSUED" in billing and open_j:
            p["partial"]+=1
        if (not open_j and "ISSUED" not in billing and
            billing in ("PROJECT FORECAST","COMPLETED - STATEMENT NOT VERIFIED")):
            try:estimate=int(float(cell(row,17) or 0))
            except ValueError:estimate=0
            if estimate>0:
                p["forecast"]+=estimate
                p["forecast_n"]+=1

    stamp=now.astimezone(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    rows=[HEAD]
    for month in sorted(buckets,key=lambda k:(k=="UNSCHEDULED",k)):
        p=buckets[month]
        if not any(p.values()):continue
        quality=("PENDING_AMOUNTS_UNVERIFIED" if p["unknown"]
                 else "INVOICES_VERIFIED_FORECAST_ESTIMATED")
        rows.append([month,p["actual"],p["pending"],p["forecast"],
                     p["actual"]+p["pending"]+p["forecast"],p["invoice"],
                     p["open"],p["unknown"],p["forecast_n"],p["partial"],
                     quality,stamp])
    if not rows[1:]:raise RuntimeError("No covered revenue rows")
    return rows


def reconcile_pending(statement_rows, invoice_rows, lifecycle_rows, monthly_rows):
    """Fail closed unless each source-verified J+X appears once in monthly Pending.

    Three independent layers must agree: QQ original Statement evidence,
    lifecycle open J installments, and published monthly aggregates.
    """
    if not statement_rows or cell(statement_rows[0], 0)!="statement_key" or (
            len(statement_rows[0])<11 or cell(statement_rows[0], 8)!="validation_status"):
        raise RuntimeError("STATEMENT_SOURCE_SCHEMA_INVALID")
    pattern=re.compile(r"(J\d{3})-(X\d+SC\d+-Z\d+)",re.I)
    reply=re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
    invoice_notice=re.compile(
        r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",re.I)
    issued=set()
    for row in invoice_rows[1:]:
        subject=cell(row,6)
        if cell(row,10) not in ALLOWED or reply.match(subject) or not invoice_notice.match(subject):
            continue
        parsed=extract(cell(row,5))
        try: amount=int(cell(row,1))
        except ValueError: continue
        if not parsed or parsed[0]!=cell(row,0) or parsed[4]!=amount or amount<=0:
            raise RuntimeError("INVOICE_EVIDENCE_CONFLICT "+cell(row,0))
        m=pattern.search(subject)
        if m:issued.add(m.group(1).upper()+"-"+m.group(2).upper())

    source={}
    for row in statement_rows[1:]:
        key=cell(row,0).strip().upper()
        if cell(row,8)!="AMOUNT_VERIFIED" or cell(row,4)!="KRW":
            continue
        if not pattern.fullmatch(key) or not cell(row,6) or not cell(row,7):
            raise RuntimeError("INVALID_VERIFIED_STATEMENT_KEY_OR_UID "+key)
        if key in issued:continue
        try: amount=int(cell(row,3))
        except ValueError: raise RuntimeError("INVALID_VERIFIED_STATEMENT_AMOUNT "+key)
        notice=cell(row,5)
        notice_month=month_of(notice)
        if amount<=0 or not notice_month or key not in cell(row,10).upper():
            raise RuntimeError("INVALID_VERIFIED_STATEMENT_EVIDENCE "+key)
        record=(amount,notice_month,notice)
        if key in source and source[key]!=record:
            raise RuntimeError("CONFLICTING_STATEMENT_SOURCE "+key)
        source[key]=record

    lifecycle={}
    for row in lifecycle_rows[1:]:
        x=cell(row,0).upper()
        js=[j.strip().upper() for j in cell(row,20).split("|") if j.strip()]
        if not js:continue
        keys=[j+"-"+x for j in js]
        if len(set(keys))!=len(keys):
            raise RuntimeError("DUPLICATE_PROJECT_STATEMENT "+x)
        missing=[k for k in keys if k not in source]
        if missing:
            raise RuntimeError("OPEN_STATEMENT_HAS_NO_VERIFIED_SOURCE "+",".join(missing))
        if any(k in issued or k in lifecycle for k in keys):
            raise RuntimeError("ISSUED_OR_DUPLICATE_PENDING "+x)
        total=sum(source[k][0] for k in keys)
        try: recorded=int(float(cell(row,22)))
        except ValueError: raise RuntimeError("LIFECYCLE_PENDING_AMOUNT_MISSING "+x)
        if total!=recorded or cell(row,23)!="AMOUNT_VERIFIED "+str(len(keys))+"/"+str(len(keys)):
            raise RuntimeError("LIFECYCLE_PENDING_SOURCE_AMOUNT_MISMATCH "+x)
        latest=max(source[k][2] for k in keys)
        if cell(row,21)!=latest:
            raise RuntimeError("LIFECYCLE_STATEMENT_NOTICE_DATE_MISMATCH "+x)
        months={source[k][1] for k in keys}
        if len(months)!=1:
            raise RuntimeError("MULTI_MONTH_PROJECT_PENDING_NEEDS_PER_J_MONTH_ALLOCATION "+x)
        for k in keys:lifecycle[k]=source[k]
    if set(source)!=set(lifecycle):
        raise RuntimeError("SOURCE_STATEMENT_MISSING_FROM_LIFECYCLE "+
                           ",".join(sorted(set(source)-set(lifecycle))[:10]))

    expected={}
    for amount,month,_ in source.values():
        slot=expected.setdefault(month,[0,0])
        slot[0]+=amount
        slot[1]+=1
    published={cell(r,0):r for r in monthly_rows[1:]}
    for month in set(expected)|set(published):
        amount,n=expected.get(month,[0,0])
        actual=published.get(month,[])
        if int(cell(actual,2) or 0)!=amount or int(cell(actual,6) or 0)!=n or int(cell(actual,7) or 0)!=0:
            raise RuntimeError("MONTHLY_PENDING_SOURCE_MISMATCH "+month)
    return len(source),sum(v[0] for v in source.values())


def assert_written_totals(rows, observed):
    """Check materialized formatted Sheet totals before sending a PASS heartbeat."""
    if len(observed)!=len(rows) or observed[0]!=HEAD:
        raise RuntimeError("MONTHLY_WRITE_SCHEMA_MISMATCH")
    for expected,got in zip(rows[1:],observed[1:]):
        if cell(got,0)!=str(expected[0]):
            raise RuntimeError("MONTHLY_WRITE_MONTH_MISMATCH")
        for col in range(1,10):
            raw=cell(got,col)
            if not raw or not re.fullmatch(r"-?\d+",re.sub(r"[₩,\s]","",raw)):
                raise RuntimeError("MONTHLY_WRITE_FORMAT_INVALID "+str(expected[0]))
            value=int(re.sub(r"[₩,\s]","",raw))
            if value!=int(expected[col]):
                raise RuntimeError("MONTHLY_WRITE_VALUE_MISMATCH "+str(expected[0])+" col="+str(col))
        if cell(got,10)!=str(expected[10]):
            raise RuntimeError("MONTHLY_WRITE_QUALITY_MISMATCH "+str(expected[0]))


def main():
    s=css.authorize()
    invoices=get(s,SRC,"CSS Tax Invoice Extract","A1:L10000")
    lifecycle=get(s,DST,"BI Project Lifecycle Overview","A1:X1000")
    statements=get(s,SRC,"CSS Statement Amount Extract","A1:K2000")
    stamp=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    try:
        old=get(s,DST,TAB,"A1:L100")
        if not invoices or invoices[0][0]!="invoice_number":
            raise RuntimeError("Invoice source unavailable")
        if not lifecycle or lifecycle[0][0]!="Project / Sub-project" or len(lifecycle[0])!=24:
            raise RuntimeError("Lifecycle source not updated with pending amount evidence")
        if not old or old[0]!=HEAD:raise RuntimeError("Monthly revenue schema mismatch")
        rows=compute(invoices,lifecycle,dt.datetime.now(dt.timezone.utc))
        count,total=reconcile_pending(statements,invoices,lifecycle,rows)
        if len(rows)<len(old):
            raise RuntimeError("Refuse to shrink existing monthly revenue ledger")
        put(s,DST,TAB,"A1",rows,"RAW")
        check=get(s,DST,TAB,"A1:L"+str(len(rows)))
        assert_written_totals(rows,check)
        oct_row=next((r for r in rows[1:] if r[0]=="2026-10"),None)
        if not oct_row:raise RuntimeError("October 2026 monthly evidence missing")
        put(s,DST,"Automation Health","A16",[[
            "Revenue Lifecycle",stamp,"PASS",
            "oct_invoice_count="+str(oct_row[5])+
            " oct_actual_krw="+str(oct_row[1])+
            " oct_pending_verified_krw="+str(oct_row[2])+
            " oct_forecast_krw="+str(oct_row[3])+
            " source_pending_count="+str(count)+
            " source_pending_krw="+str(total)+
            " unresolved_pending_count="+str(sum(r[7] for r in rows[1:]))
        ]],"RAW")
    except Exception as exc:
        put(s,DST,"Automation Health","A16",[[
            "Revenue Lifecycle",stamp,"FAIL",
            "SOURCE_PENDING_RECONCILE_FAILED "+type(exc).__name__+" "+str(exc)[:180]
        ]],"RAW")
        raise
    print("REVENUE_LIFECYCLE_MONTHLY_PASS October_invoice_count="+str(oct_row[5])+
          " October_actual_krw="+str(oct_row[1])+
          " October_pending_verified_krw="+str(oct_row[2])+
          " source_pending_count="+str(count)+
          " source_pending_krw="+str(total),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("REVENUE_LIFECYCLE_MONTHLY_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
