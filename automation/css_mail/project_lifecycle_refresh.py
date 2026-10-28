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
      "Open Statement Numbers","Latest Statement Notice"]
INV_STMT=re.compile(r"^J\d{3}-(X\d+SC\d+-Z\d+)$",re.I)
H=re.compile(r"H\d+SC\d+",re.I)
A=re.compile(r"AMEA\d{7,}(?:-\d{1,3})?",re.I)

def present(r,i):
    return r[i] if i<len(r) else ""

def build(css_rows,feishu_rows,invoice_rows,controls,mail_rows):
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
        if not re.fullmatch(r"209126\\d{6}",number):continue
        if REPLY.match(subject) or not re.match(
            r"^\\s*❗?\\ufe0f?\\s*Notice:\\s*Invoice Issued\\s*&\\s*Statement Confirmed\\b",
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
        hits=[x.upper() for x in re.findall(r"X\\d+SC\\d+-Z\\d+",subject,re.I)]
        if not hits:
            continue
        low=subject.lower()
        for term,order,label in stages:
            if term in low:
                for x in hits:
                    old=stage_evidence.get(x)
                    if old is None or (order,date)>(old[0],old[1]):
                        stage_evidence[x]=(order,date,label)
                break

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
        row=[x,amea,present(c,8),present(c,9),present(c,10),status,
             stage,percentage,last_css,present(c,16),present(r,7),
             present(r,10),expected,present(p,3),len(inv),sum(inv.values()),
             billing,estimate,next_step,
             "Feishu "+str(present(r,0))+"; CSS "+str(present(c,36) or "unmatched"),
             " | ".join(open_j),
             max((notices[j] for j in open_j),default="")]
        out.append(row)
    if len(out)<2:raise RuntimeError("Empty lifecycle input; refusing update")
    return out

def main():
    s=css.authorize()
    sources=[
        get(s,SRC,"CSS Project Dashboard","A1:AK1000"),
        get(s,DST,"Feishu Project TAT Forecast","A1:Q2000"),
        get(s,SRC,"CSS Tax Invoice Extract","A1:L10000"),
        get(s,DST,"BI Project Month Control","A1:K2000"),
        get(s,SRC,"CSS Git Ingest","F1:Q10000")
    ]
    for data,expected in zip(sources,["exclude","Snapshot KST","invoice_number","Sub-Project Number","received_at"]):
        if not data or not data[0] or data[0][0]!=expected:
            raise RuntimeError("Unexpected lifecycle source header: "+expected)
    result=build(*sources)
    previous=get(s,DST,TAB,"A1:V1000")
    if not previous or previous[0] not in (HEAD,HEAD[:20]):
        raise RuntimeError("Lifecycle output header changed; refusing update")
    if len(previous)>len(result):
        raise RuntimeError("Fewer projects than previous snapshot; refusing destructive shrink")
    put(s,DST,TAB,"A1",result,"RAW")
    # Verify the materialized result before reporting success. A stale sheet
    # must never be presented as a completed refresh.
    observed=get(s,DST,TAB,"A1:V"+str(len(result)))
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
        " CSS_snapshot=legacy Feishu_snapshot=external"
    ]],"RAW")
    print("PROJECT_LIFECYCLE_REFRESH_PASS projects="+str(len(result)-1)+
          " issued_projects="+str(sum(r[14]>0 for r in result[1:]))+
          " open_statements="+str(sum(bool(r[20]) for r in result[1:]))+
          " updated="+dt.datetime.now(KST).isoformat(),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("PROJECT_LIFECYCLE_REFRESH_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
