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
      "Immediate Next Step","Data Timestamp / Source"]
INV_STMT=re.compile(r"^J\d{3}-(X\d+SC\d+-Z\d+)$",re.I)
H=re.compile(r"H\d+SC\d+",re.I)
A=re.compile(r"AMEA\d{7,}(?:-\d{1,3})?",re.I)

def present(r,i):
    return r[i] if i<len(r) else ""

def build(css_rows,feishu_rows,invoice_rows,controls):
    css_amea,css_h={},{}
    for r in css_rows[1:]:
        a=present(r,4)
        if a:css_amea[a]=r
        for h in H.findall(str(present(r,5))):
            css_h[h]=r
    invoices={}
    for r in invoice_rows[1:]:
        m=INV_STMT.match(str(present(r,3)))
        if not m:continue
        if not re.fullmatch(r"209126\d{6}",str(present(r,0))):continue
        x=m.group(1).upper()
        try:amount=int(present(r,4))
        except (TypeError,ValueError):continue
        if amount<=0:continue
        invoices.setdefault(x,{})[str(present(r,0))]=amount
    manual={present(r,0):r for r in controls[1:] if present(r,0)}
    out=[HEAD]
    for r in feishu_rows[1:]:
        x=str(present(r,1)).strip()
        if not x:continue
        project_name=str(present(r,3))
        hit=A.search(project_name)
        amea=hit.group(0) if hit else ""
        c=css_amea.get(amea) or css_h.get(str(present(r,2))) or []
        p=manual.get(x,[])
        inv=invoices.get(x,{})
        status=str(present(r,4))
        blocked=bool(re.search(r"abnormal|awaiting feedback|cancel",status,re.I))
        completed=bool(re.search(r"settled|completed|waiting for settlement",status,re.I))
        if blocked:
            billing="BLOCKED / EXCLUDED FROM FORECAST"
            next_step="Resolve project abnormal/start status"
        elif inv:
            billing="ISSUED (CHECK PARTIAL BILLING)"
            next_step="Payment follow-up; verify other Statement installments"
        elif completed:
            billing="STATEMENT PENDING VERIFICATION"
            next_step="Verify original Statement number and total"
        else:
            billing="PROJECT FORECAST"
            next_step="Monitor stage / refresh expected completion"
        try:percentage=float(present(c,13) or 0)
        except ValueError:percentage=0
        try:estimate=int(float(present(p,8) or present(r,15) or 0))
        except ValueError:estimate=0
        expected=present(p,6) or present(r,11)
        row=[x,amea,present(c,8),present(c,9),present(c,10),status,
             present(c,12) or "NOT_IN_CSS_SNAPSHOT",percentage,present(c,27),
             present(c,16),present(r,7),present(r,10),expected,present(p,3),
             len(inv),sum(inv.values()),billing,estimate,next_step,
             "Feishu "+str(present(r,0))+"; CSS "+str(present(c,36) or "unmatched")]
        out.append(row)
    if len(out)<2:raise RuntimeError("Empty lifecycle input; refusing update")
    return out

def main():
    s=css.authorize()
    sources=[
        get(s,SRC,"CSS Project Dashboard","A1:AK1000"),
        get(s,DST,"Feishu Project TAT Forecast","A1:Q2000"),
        get(s,DST,"QQ Invoice Reconciliation 2026","A1:H1000"),
        get(s,DST,"BI Project Month Control","A1:K2000")
    ]
    for data,expected in zip(sources,["exclude","Snapshot KST","Invoice Number","Sub-Project Number"]):
        if not data or not data[0] or data[0][0]!=expected:
            raise RuntimeError("Unexpected lifecycle source header: "+expected)
    result=build(*sources)
    previous=get(s,DST,TAB,"A1:T1000")
    if not previous or previous[0]!=HEAD:
        raise RuntimeError("Lifecycle output header changed; refusing update")
    if len(previous)>len(result):
        raise RuntimeError("Fewer projects than previous snapshot; refusing destructive shrink")
    put(s,DST,TAB,"A1",result,"RAW")
    print("PROJECT_LIFECYCLE_REFRESH_PASS projects="+str(len(result)-1)+
          " issued_projects="+str(sum(r[14]>0 for r in result[1:]))+
          " updated="+dt.datetime.now(KST).isoformat(),flush=True)

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("PROJECT_LIFECYCLE_REFRESH_FAILED "+type(exc).__name__,file=sys.stderr)
        raise
