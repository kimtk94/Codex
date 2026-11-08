#!/usr/bin/env python3
"""Read-only sources -> BI lifecycle projection. Never changes the user month overrides."""
import datetime as dt
import re
import sys
import incremental_sync as css
from unified_followup_sync import SRC, DST, KST, get, put

TAB="BI Project Lifecycle Overview"
HEAD=["Project / Sub-project","AMEA","Institution","Customer","Service",
      "Feishu Status (latest)","CSS Stage (legacy)","CSS Progress %",
      "CSS Last Email","Sample Count","Feishu Remaining TAT Days",
      "Feishu Expected Completion","Expected Revenue Month",
      "Manual Month Override (reference)","Invoice Count","Invoice Actual KRW",
      "Billing Classification","Estimated KRW (existing)",
      "Immediate Next Step","Data Timestamp / Source",
      "Open Statement Numbers","Latest Statement Notice",
      "Pending KRW Verified","Pending Amount Evidence"]
INV_STMT=re.compile(r"(J\d{3})-(X\d+SC\d+-Z\d+)",re.I)
CSS_SENDER="css@novogene-amea.com"
ACCEPTED_INVOICE={"FILENAME_PARSED","VERIFIED_LEGACY_FILENAME","EXISTS_IN_LEGACY"}
REPLY=re.compile(r"^\s*(?:re|fw|fwd|회신|답장|전달)\s*[:：]",re.I)
H=re.compile(r"H\d+SC\d+",re.I)
A=re.compile(r"AMEA\d{7,}(?:-\d{1,3})?",re.I)

def latest_source_timestamp(rows):
    """Choose the most recent instant, not lexicographic mixed-offset ISO text."""
    values=[]
    for r in rows:
        if not r or not r[0]:
            continue
        value=dt.datetime.fromisoformat(str(r[0]).replace("Z","+00:00"))
        if value.tzinfo is None:
            value=value.replace(tzinfo=KST)
        values.append(value.astimezone(dt.timezone.utc))
    return max(values,default=None)

def present(r,i):
    return r[i] if i<len(r) else ""

def build(css_rows,feishu_rows,invoice_rows,controls,mail_rows,statement_amount_rows):
    """Build a single project-stage and billing view from live validated inputs.

    Invoice keys are invoice numbers; Statement keys are J-number + exact X
    subproject. No payment confirmation or pending amount is ever inferred.
    """
    from tax_invoice_extract import extract
    css_amea,css_h={},{}
    for r in css_rows[1:]:
        a=present(r,4)
        if a:css_amea[a]=r
        for h in H.findall(str(present(r,5))):
            css_h[h]=r
    invoices={}
    issued_statements={}
    global_invoice={}
    for r in invoice_rows[1:]:
        number=str(present(r,0)).strip()
        status=str(present(r,10))
        subject=str(present(r,6))
        filename=str(present(r,5))
        if status not in ACCEPTED_INVOICE:continue
        if not re.fullmatch(r"209126\d{6}",number):continue
        if REPLY.match(subject) or not re.match(
            r"^\s*❗?\ufe0f?\s*Notice:\s*Invoice Issued\s*&\s*Statement Confirmed\b",
            subject,re.I):continue
        m=INV_STMT.search(subject)
        if not m:continue
        statement,x=m.group(1).upper(),m.group(2).upper()
        parsed=extract(filename)
        if not parsed or parsed[4] is None:continue
        try:amount=int(present(r,1))
        except (TypeError,ValueError):continue
        if amount<=0 or parsed[0]!=number or parsed[4]!=amount:continue
        if present(r,2) and parsed[3]!=present(r,2):
            raise RuntimeError("Invoice AMEA/file mismatch for "+number)
        if number in global_invoice:
            if global_invoice[number]!=(x,amount,statement):
                raise RuntimeError("Conflicting invoice identity: "+number)
            continue
        global_invoice[number]=(x,amount,statement)
        invoices.setdefault(x,{})[number]=amount
        issued_statements.setdefault(x,set()).add(statement)

    # CSS Git Ingest header metadata is more recent than legacy CSS timeline.
    # Search original official notices only, never RE/FW or in-reply-to.
    statement_notices={}
    stage_evidence={}
    by_h,by_amea={},{}
    for project in feishu_rows[1:]:
        project_x=str(present(project,1)).strip().upper()
        contract=str(present(project,2)).strip().upper()
        label=str(present(project,3))
        if not project_x:continue
        if contract:by_h.setdefault(contract,set()).add(project_x)
        hit=A.search(label)
        if hit:by_amea.setdefault(hit.group(0).upper(),set()).add(project_x)
    stages=[
        ("invoice issued & statement confirmed",100,"Invoice issued"),
        ("final report & statement ready for confirmation",97,"Statement confirmation"),
        ("statement ready for confirmation",97,"Statement confirmation"),
        ("final report",95,"Final report ready"),
        ("data ready to download",90,"Data ready"),
        ("sequencing completed",85,"Sequencing / production"),
        ("sequencing",80,"Sequencing / production"),
        ("library preparation",70,"Library preparation"),
        ("library prep",70,"Library preparation"),
        ("sample qc",55,"Sample QC review"),
        ("review sample qc report",55,"Sample QC review"),
        ("sample received",40,"Sample received"),
        ("sif approved",30,"SIF approved"),
        ("sif received",20,"SIF received"),
    ]
    for r in mail_rows[1:]:
        date,from_email,to,cc,subject=map(str,[present(r,i) for i in range(5)])
        direction=str(present(r,10))
        in_reply=str(present(r,11))
        if from_email.strip().lower()!=CSS_SENDER or direction!="INBOUND":
            continue
        if in_reply.strip() or REPLY.match(subject):
            continue
        m=INV_STMT.search(subject)
        if m and "statement" in subject.lower() and (
            "ready for confirmation" in subject.lower() or
            "revised statement" in subject.lower()):
            x=m.group(2).upper()
            j=m.group(1).upper()
            prev=statement_notices.setdefault(x,{})
            if j not in prev or date>prev[j]:
                prev[j]=date
        # Build the most advanced confirmed CSS milestone per project;
        # a late reminder must not roll back a completed milestone.
        hits=[x.upper() for x in re.findall(r"X\d+SC\d+-Z\d+",subject,re.I)]
        evidence_scope="direct"
        if not hits:
            evidence_scope="contract"
            linked=set()
            for h in H.findall(subject):
                linked.update(by_h.get(h.upper(),set()))
            if not linked:
                evidence_scope="AMEA"
                for a in A.findall(subject):
                    linked.update(by_amea.get(a.upper(),set()))
            hits=sorted(linked)
        if not hits:continue
        low=subject.lower()
        for term,order,label in stages:
            if term in low:
                actual_label=label if evidence_scope=="direct" else (
                    label+" [QQ "+evidence_scope+"-level]")
                for x in hits:
                    old=stage_evidence.get(x)
                    if old is None or (order,date)>(old[0],old[1]):
                        stage_evidence[x]=(order,date,actual_label)
                break

    statement_amounts={}
    for a in statement_amount_rows[1:]:
        key=str(present(a,0)).upper()
        if present(a,8)!="AMOUNT_VERIFIED" or present(a,4)!="KRW":continue
        try:amount=int(present(a,3))
        except (TypeError,ValueError):continue
        if amount<=0 or not INV_STMT.fullmatch(key):continue
        statement_amounts[key]=(amount,str(present(a,5)))
    manual={present(r,0):r for r in controls[1:] if present(r,0)}
    out=[HEAD]
    for r in feishu_rows[1:]:
        x=str(present(r,1)).strip().upper()
        if not x:continue
        project_name=str(present(r,3))
        hit=A.search(project_name)
        amea=hit.group(0) if hit else ""
        c=css_amea.get(amea) or css_h.get(str(present(r,2))) or []
        p=manual.get(x,[])
        inv=invoices.get(x,{})
        issued=issued_statements.get(x,set())
        notices=statement_notices.get(x,{})
        open_j=sorted(set(notices)-issued)
        status=str(present(r,4))
        blocked=bool(re.search(r"abnormal|awaiting feedback|cancel",status,re.I))
        completed=bool(re.search(r"settled|completed|waiting for settlement",status,re.I))
        if inv and open_j:
            billing="ISSUED + STATEMENT PENDING"
            next_step="Verify open Statement amount; follow up invoice/payment"
        elif inv:
            billing="ISSUED (BALANCE UNVERIFIED)"
            next_step="Check payment and whether other billing tranches remain"
        elif open_j:
            billing="STATEMENT READY - INVOICE PENDING"
            next_step="Verify Statement amount and confirm invoice issuance"
        elif blocked:
            billing="BLOCKED / EXCLUDED FROM FORECAST"
            next_step="Resolve project abnormal/start status"
        elif completed:
            billing="COMPLETED - STATEMENT NOT VERIFIED"
            next_step="Verify original Statement number and total"
        else:
            billing="PROJECT FORECAST"
            next_step="Monitor stage / refresh expected completion"
        try:percentage=float(present(c,13) or 0)
        except ValueError:percentage=0
        stage=str(present(c,12) or "NOT_IN_CSS_SNAPSHOT")
        recent=stage_evidence.get(x)
        if recent:
            try:legacy_order=int(float(present(c,13) or 0))
            except ValueError:legacy_order=0
            if recent[0]>legacy_order:
                stage=recent[2]+" [QQ confirmed]"
                percentage=max(percentage,float(recent[0]))
        try:estimate=int(float(present(p,8) or present(r,15) or 0))
        except ValueError:estimate=0
        expected=present(p,6) or present(r,11)
        last_css=present(c,27)
        if recent:
            last_css=max(str(last_css or ""),str(recent[1]))
        known_pending=[]
        for j in open_j:
            record=statement_amounts.get(j+"-"+x)
            if record and record[1]==notices[j]:
                known_pending.append(record[0])
        pending_verified=sum(known_pending) if known_pending else ""
        evidence=("AMOUNT_VERIFIED "+str(len(known_pending))+"/"+str(len(open_j))
                  if open_j else "NO_OPEN_STATEMENT")
        row=[x,amea,present(c,8),present(c,9),present(c,10),status,
             stage,percentage,last_css,present(c,16),present(r,7),
             present(r,10),expected,present(p,3),len(inv),sum(inv.values()),
             billing,estimate,next_step,
             "Feishu "+str(present(r,0))+"; CSS "+str(present(c,36) or "unmatched"),
             " | ".join(open_j),
             max((notices[j] for j in open_j),default=""),
             pending_verified,evidence]
        out.append(row)
    # A source-verified open Statement can exist before the Feishu project
    # snapshot is populated (one real 11/08 case: exact J001+X present in QQ
    # evidence but the matching X not among 110 Feishu project rows).
    # Preserve the deterministic original J+X entry as SOURCE_ONLY instead
    # of silently omitting it, or declaring unrelated real issued invoices
    # incorrect. Never invent a customer, expected price, Feishu progress,
    # ownership, or completed/invoiced status.
    feishu_keys={str(present(r,1)).strip().upper()
                 for r in feishu_rows[1:] if present(r,1)}
    from collections import defaultdict
    missing=defaultdict(dict)
    for record in statement_amount_rows[1:]:
        key=str(present(record,0)).strip().upper()
        if present(record,8)!="AMOUNT_VERIFIED" or present(record,4)!="KRW":
            continue
        m=INV_STMT.fullmatch(key)
        if not m:continue
        j,x=m.group(1).upper(),m.group(2).upper()
        if x in feishu_keys or j in issued_statements.get(x,set()):
            continue
        # Original validated Statement row requires exact immutable X/J,
        # official notice subject, original UID and a source timestamp.
        subject=str(present(record,10))
        when=str(present(record,5))
        uid=str(present(record,6))
        if (str(present(record,1)).strip().upper()!=x
                or str(present(record,2)).strip().upper()!=j
                or key not in subject.upper() or not uid
                or not when or REPLY.match(subject)
                or "statement ready" not in subject.lower()):
            raise RuntimeError("SOURCE_ONLY_STATEMENT_EVIDENCE_INVALID")
        try:
            original=dt.datetime.fromisoformat(when.replace("Z","+00:00"))
            if original.tzinfo is None:raise ValueError("without timezone")
            month=original.astimezone(KST).strftime("%Y-%m")
            amount=int(present(record,3))
        except (ValueError,TypeError) as exc:
            raise RuntimeError("SOURCE_ONLY_STATEMENT_VALUE_INVALID") from exc
        if amount<=0:raise RuntimeError("SOURCE_ONLY_STATEMENT_AMOUNT_INVALID")
        am=set(v.upper() for v in A.findall(subject))
        if len(am)!=1:
            raise RuntimeError("SOURCE_ONLY_STATEMENT_AMEA_NOT_UNIQUE")
        old=missing[x].get(j)
        proof=(amount,when,next(iter(am)))
        if old is not None and old!=proof:
            raise RuntimeError("SOURCE_ONLY_STATEMENT_CONFLICT")
        matching_notice=statement_notices.get(x,{}).get(j)
        if matching_notice and matching_notice!=when:
            raise RuntimeError("SOURCE_ONLY_STATEMENT_NOTICE_CONFLICT")
        missing[x][j]=proof
    if len(missing)>50:raise RuntimeError("SOURCE_ONLY_STATEMENT_SCOPE_LIMIT")
    for x,by_j in sorted(missing.items()):
        am={value[2] for value in by_j.values()}
        months={dt.datetime.fromisoformat(value[1].replace("Z","+00:00"))
                .astimezone(KST).strftime("%Y-%m") for value in by_j.values()}
        if len(am)!=1 or len(months)!=1:
            raise RuntimeError("SOURCE_ONLY_STATEMENT_MULTI_MONTH_REVIEW")
        notes=[value[1] for value in by_j.values()]
        inv=invoices.get(x,{})
        pending_total=sum(value[0] for value in by_j.values())
        billing=("ISSUED + STATEMENT PENDING" if inv
                 else "STATEMENT READY - INVOICE PENDING")
        out.append([x,next(iter(am)),"","","",
                    "NOT_IN_FEISHU_SNAPSHOT",
                    "Statement confirmation [QQ exact X]",97,
                    max(notes),"","", "",next(iter(months)),"",
                    len(inv),sum(inv.values()),billing,0,
                    "Review exact X project match and pending Invoice",
                    "QQ original verified Statement (not Feishu source)",
                    " | ".join(sorted(by_j)),max(notes),pending_total,
                    "AMOUNT_VERIFIED "+str(len(by_j))+"/"+str(len(by_j))])
    if missing:
        print("PROJECT_LIFECYCLE_SOURCE_ONLY_VERIFIED_STATEMENTS="+
              str(len(missing))+" attribution=EXACT_J_X pending_not_revenue",
              flush=True)
    if len(out)<2:raise RuntimeError("Empty lifecycle input; refusing update")
    return out

def main():
    s=css.authorize()
    sources=[
        get(s,SRC,"CSS Project Dashboard","A1:AK1000"),
        get(s,DST,"Feishu Project TAT Forecast","A1:Q2000"),
        get(s,SRC,"CSS Tax Invoice Extract","A1:L10000"),
        get(s,DST,"BI Project Month Control","A1:K2000"),
        get(s,SRC,"CSS Git Ingest","F1:Q10000"),
        get(s,SRC,"CSS Statement Amount Extract","A1:K2000")
    ]
    for data,expected in zip(sources,["exclude","Snapshot KST","invoice_number","Sub-Project Number","received_at","statement_key"]):
        if not data or not data[0] or data[0][0]!=expected:
            raise RuntimeError("Unexpected lifecycle source header: "+expected)
    # Gate the full chain on source freshness. Never regenerate revenue with
    # a stale Feishu snapshot while recording a fresh PASS heartbeat.
    now_utc=dt.datetime.now(dt.timezone.utc)
    latest_feishu=latest_source_timestamp(sources[1][1:])
    if not latest_feishu or (now_utc-latest_feishu).total_seconds()/3600>float(__import__("os").getenv("FEISHU_SNAPSHOT_MAX_AGE_HOURS","48")):
        raise RuntimeError("FEISHU_SOURCE_STALE: refresh Feishu before project/revenue sync")
    latest_qq=latest_source_timestamp(sources[4][1:])
    if not latest_qq or (now_utc-latest_qq).total_seconds()/3600>float(__import__("os").getenv("QQ_SOURCE_MAX_AGE_HOURS","6")):
        raise RuntimeError("QQ_SOURCE_STALE: stop project/revenue refresh")
    result=build(*sources)
    previous=get(s,DST,TAB,"A1:X1000")
    if not previous or previous[0] not in (HEAD,HEAD[:22],HEAD[:20]):
        raise RuntimeError("Lifecycle output header changed; refusing update")
    if len(previous)>len(result):
        raise RuntimeError("Fewer projects than previous snapshot; refusing destructive shrink")
    put(s,DST,TAB,"A1",result,"RAW")
    # Verify the materialized result before reporting success. A stale sheet
    # must never be presented as a completed refresh.
    observed=get(s,DST,TAB,"A1:X"+str(len(result)))
    if len(observed)!=len(result) or observed[0]!=HEAD:
        raise RuntimeError("Lifecycle post-write row/header verification failed")
    if [str(x) for x in observed[-1][:2]]!=[str(x) for x in result[-1][:2]]:
        raise RuntimeError("Lifecycle post-write last-project mismatch")
    now=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S KST")
    put(s,DST,"Automation Health","A15",[[
        "Project Lifecycle",now,"PASS",
        "projects="+str(len(result)-1)+
        " linked_invoices="+str(sum(r[14]>0 for r in result[1:]))+
        " open_statements="+str(sum(bool(r[20]) for r in result[1:]))+
        " verified_pending_krw="+str(sum(r[22] for r in result[1:] if isinstance(r[22],int)))+
        " CSS_snapshot=legacy Feishu_snapshot=external"
    ]],"RAW")
    print("PROJECT_LIFECYCLE_REFRESH_PASS projects="+str(len(result)-1)+
          " issued_projects="+str(sum(r[14]>0 for r in result[1:]))+
          " open_statements="+str(sum(bool(r[20]) for r in result[1:]))+
          " verified_pending_krw="+str(sum(r[22] for r in result[1:] if isinstance(r[22],int)))+
          " updated="+dt.datetime.now(KST).isoformat(),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("PROJECT_LIFECYCLE_REFRESH_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
