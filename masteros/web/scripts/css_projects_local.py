#!/usr/bin/env python3
"""PC-only read-only CSS project source→WEB_EXPORT_V4 parity. Never log credentials."""
import base64, datetime as dt, json, os, re
from pathlib import Path
from urllib.parse import quote
KST=dt.timezone(dt.timedelta(hours=9))
SRC="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
DST="1753nq7_zX-6ae7srmJryHrFECEG5L9Mjf7JvjrbFxVY"
HEAD=["project_subproject_id","amea","institution","service","feishu_status",
"css_legacy_stage","css_legacy_last_email","sample_count","feishu_expected_completion",
"expected_revenue_month","invoice_count","billing_classification",
"mirror_source_status","source_manifest_date"]
IDX=[0,1,2,4,5,6,8,9,11,12,14,16]
MARK="MIRROR_ONLY_NOT_ORIGINAL_FEISHU_VERIFIED"
def cell(row,i):return str(row[i]).strip() if len(row)>i and row[i] is not None else ""
def when(s):
    try:
        t=dt.datetime.fromisoformat(str(s).strip().replace(" KST","").replace("Z","+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=KST)
    except ValueError:return None
def inspect(source,sink,manifest,mail,now=None):
    now=now or dt.datetime.now(KST)
    if now.tzinfo is None:raise ValueError("AWARE_CLOCK_REQUIRED")
    if not source or source[0][:7]!=["Project / Sub-project","AMEA","Institution","Customer","Service","Feishu Status (latest)","CSS Stage (legacy)"]:
        raise ValueError("SOURCE_SCHEMA")
    if len(sink)<2 or sink[0][:2]!=["WEB_EXPORT_V4","MIRROR_ONLY"] or sink[1][:14]!=HEAD:
        raise ValueError("SINK_SCHEMA")
    source_rows=[r for r in source[1:] if cell(r,0)]
    sink_rows=[r for r in sink[2:] if cell(r,0)]
    if not 1<=len(source_rows)<=1500 or len(sink_rows)>1500:raise ValueError("SOURCE_ROWS")
    source_map={cell(r,0):r for r in source_rows}
    sink_ids=[cell(r,0) for r in sink_rows]
    if len(source_map)!=len(source_rows) or len(set(sink_ids))!=len(sink_ids):
        raise ValueError("DUPLICATE_IDS")
    matched_manifest=[r for r in manifest[1:] if cell(r,0)=="Online-Project"] if manifest else []
    if len(matched_manifest)!=1 or len(matched_manifest[0])<5:raise ValueError("MANIFEST_MISSING")
    manifest_row=matched_manifest[0]
    source_date=cell(manifest_row,1)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}",source_date):raise ValueError("DATE_INVALID")
    if not mail or len(mail)<2 or cell(mail[1],1) not in ("WINDOW_CAUGHT_UP","WINDOW_PARTIAL","PARTIAL","WINDOW_PENDING"):
        raise ValueError("MAIL_STATUS_UNVERIFIED")
    metadata={cell(sink[0],i):cell(sink[0],i+1) for i in range(2,len(sink[0])-1,2)}
    times=[when(cell(manifest_row,2)),when(cell(mail[1],0)),when(metadata.get("sink_generated_at"))]
    recent=all(t and -10 <= (now-t).total_seconds()/60 <= 36*60 for t in times)
    bad=0
    for row in sink_rows:
        original=source_map.get(cell(row,0))
        if not original or any(cell(row,i)!=cell(original,j) for i,j in enumerate(IDX)) or cell(row,12)!=MARK or cell(row,13)!=source_date:
            bad+=1
    missing=len(set(source_map)-set(sink_ids))
    unexpected=len(set(sink_ids)-set(source_map))
    aligned=(not bad and not missing and not unexpected and len(source_rows)==len(sink_rows)
             and metadata.get("projects")==str(len(source_rows)))
    status="SINK_LAG" if not aligned else "PASS_MIRROR_ONLY" if recent else "STALE"
    return {"status":status,"scope":"GOOGLE_MIRROR_TO_V4_NOT_ORIGINAL_PROOF",
            "checked_at":now.isoformat(),"source_manifest_date":source_date,
            "source_synced_at":times[0].isoformat() if times[0] else None,
            "mail_mirror_updated_at":times[1].isoformat() if times[1] else None,
            "sink_generated_at":times[2].isoformat() if times[2] else None,
            "source_count":len(source_rows),"sink_count":len(sink_rows),
            "source_sink_mismatch_count":bad,"missing_project_count":missing,
            "unexpected_project_count":unexpected,"original_feishu_verified":False,
            "original_qq_verified":False,"sfdc_save_verified":False,
            "financial_actual_certified":False,
            "project_rows":[{"project_id":cell(r,0),"amea":cell(r,1),
              "institution":cell(r,2),"service":cell(r,3),"stage":cell(r,4),
              "css_legacy_stage":cell(r,5),"sample_count":cell(r,7),
              "expected_completion":cell(r,8),"expected_revenue_month":cell(r,9),
              "invoice_count":cell(r,10)} for r in sink_rows]}
def session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv("GCP_SERVICE_ACCOUNT_JSON","").strip()
    if raw:
        try:info=json.loads(raw)
        except ValueError:info=json.loads(base64.b64decode(raw))
    else:
        path=Path(os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or
                  Path.home()/"CSS_Automation"/"credentials"/"service_account.json")
        if not path.is_file():raise RuntimeError("AUTH_NOT_CONFIGURED")
        info=json.loads(path.read_text(encoding="utf8"))
    return AuthorizedSession(Credentials.from_service_account_info(info,
                scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]))
def google_fetch():
    client=session()
    def read(book,name,area):
        u="https://sheets.googleapis.com/v4/spreadsheets/"+book+"/values/"+quote("'"+name+"'!"+area,safe="!'")
        r=client.get(u,timeout=28)
        r.raise_for_status()
        return r.json().get("values",[])
    return inspect(read(SRC,"BI Project Lifecycle Overview","A1:Q1500"),
                   read(DST,"WEB_EXPORT_V4","A1:P1500"),
                   read(SRC,"Feishu Source Manifest","A1:G20"),
                   read(SRC,"CSS Mail Backfill Status","A1:L5"))
if __name__=="__main__":
    try:result=google_fetch()
    except Exception as e:
        result={"status":"SOURCE_UNAVAILABLE","error_type":type(e).__name__,
                "source_count":None,"sink_count":None,"project_rows":[],
                "original_feishu_verified":False,"financial_actual_certified":False}
    print(json.dumps(result,ensure_ascii=False,separators=(",",":")))
