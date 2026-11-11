#!/usr/bin/env python3
"""Private Windows desktop read-only SFDC preflight agent for Feishu tasks.

Uses the Google Sheets transport; never receives Feishu app tokens. Designed to
run *once* from Windows Task Scheduler. Salesforce writes are fail-closed until
linked Oppo+Quote saves and price verification pass independent live tests.
"""
from __future__ import annotations
import argparse
import datetime as dt
import json
import math
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

SHEET_ID="1Fo0Tc6PQ3Ek0-33lmegScM_z8ST-ShUYQ0K3kD4PqnI"
QUEUE="SFDC Feishu Queue"; RESULTS="SFDC Feishu Results"
QHEAD=["record_id","request_id","fingerprint","action","mode","source_id","source_quote_id",
       "new_name","institution","contact","samples","gb_per_sample","close_date","progress",
       "price_confirmed","duplicate_confirmed","save_approved","source_created_at"]
RHEAD=["record_id","request_id","fingerprint","status","code","expected_net_krw",
       "expected_vat_krw","new_oppo_id","new_quote_id","checked_at","local_provenance"]


def authorized_session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    path=Path(os.getenv('GOOGLE_APPLICATION_CREDENTIALS') or
        (Path.home()/'CSS_Automation'/'credentials'/'service_account.json'))
    if not path.is_file():raise RuntimeError('GOOGLE_AUTH_FILE_MISSING')
    info=json.loads(path.read_text(encoding='utf-8'))
    credential=Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return AuthorizedSession(credential)


def url_for(tab,rng):
    return 'https://sheets.googleapis.com/v4/spreadsheets/'+SHEET_ID+'/values/'+quote("'"+tab+"'!"+rng,safe="!'$:")


def get_rows(session,tab,rng):
    response=session.get(url_for(tab,rng),timeout=36)
    response.raise_for_status()
    return response.json().get('values',[])


def result_append_url():
    return url_for(RESULTS,'A:K')+':append?valueInputOption=RAW&insertDataOption=INSERT_ROWS'

def append_result(session,row):
    if len(row)!=len(RHEAD):raise RuntimeError('RESULT_ROW_SIZE')
    url=result_append_url()
    response=session.post(url,json={'majorDimension':'ROWS','values':[row]},timeout=36)
    response.raise_for_status()
    data=response.json()
    updates=data.get('updates',{})
    if int(updates.get('updatedRows',0))!=1:
        raise RuntimeError('RESULT_WRITE_SHORT')
    # An append HTTP 200 is not proof the intended request was durably stored.
    # Require one exact, non-header result row and independently read it back.
    destination=str(updates.get('updatedRange',''))
    m=re.fullmatch(r"'SFDC Feishu Results'!A([0-9]+):K\1",destination)
    if not m or int(m.group(1))<2:
        raise RuntimeError('RESULT_APPEND_RANGE_UNVERIFIED')
    index=int(m.group(1))
    verified=get_rows(session,RESULTS,'A'+str(index)+':K'+str(index))
    if len(verified)!=1 or [str(v).strip() for v in
            (verified[0]+['']*(len(row)-len(verified[0])))]!=[str(v).strip() for v in row]:
        raise RuntimeError('RESULT_APPEND_READBACK_MISMATCH')


def validate_queue_row(row):
    v=(row+['']*len(QHEAD))[:len(QHEAD)]
    if not re.fullmatch(r'rec[A-Za-z0-9]{7,32}',v[0]):return False
    if not re.fullmatch(r'SFDC-[A-Z0-9-]{8,48}',v[1]):return False
    if not re.fullmatch('[0-9a-f]{64}',v[2]):return False
    if v[3] not in ('lead_convert','oppo_quote_pair','opportunity_create','quote_create'):return False
    if v[4] not in ('PREFLIGHT','SAVE'):return False
    prefix={'lead_convert':'00Q','oppo_quote_pair':'006','opportunity_create':'006','quote_create':'a0P'}[v[3]]
    if not re.fullmatch(prefix+r'[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',v[5]):return False
    if v[6] and not re.fullmatch(r'a0P[A-Za-z0-9]{12}(?:[A-Za-z0-9]{3})?',v[6]):return False
    try: n=int(v[10]);gb=float(v[11])
    except ValueError:return False
    if v[3]!='lead_convert' and not(1<=n<=500 and 0<gb<=100000):return False
    if v[4]=='SAVE' and any(v[i]!='true' for i in (14,15,16)):return False
    return v


def call_live_catalog(script,source_id,mode='bundle',resource='opportunity'):
    command=[sys.executable,str(script)]
    req={'resource':resource,'mode':mode,'recordId':source_id}
    proc=subprocess.run(command,input=json.dumps(req),text=True,capture_output=True,
                        timeout=105,check=False)
    if proc.returncode or len(proc.stdout)>200000:raise RuntimeError('SFDC_CATALOG_PROCESS_FAILURE')
    result=json.loads(proc.stdout)
    if result.get('status')!='PASS':raise RuntimeError('SFDC_LIVE_READ_BLOCKED')
    return result


def price_pair(bundle,row):
    if bundle.get('selectionStatus')!='EXACT_ONE' or len(bundle.get('linkedQuotes',[]))!=1:
        raise RuntimeError('LINKED_QUOTE_NOT_UNIQUE')
    opp=bundle['opportunity'];quote_data=bundle['linkedQuotes'][0]
    if quote_data.get('opportunityId')!=row[5]:raise RuntimeError('SOURCE_PARENT_MISMATCH')
    if row[6] and quote_data.get('id')!=row[6]:raise RuntimeError('EXPLICIT_QUOTE_ID_MISMATCH')
    if quote_data.get('pricingStatus')!='VERIFIED_PROCESS_LINES' or quote_data.get('productCount')!=1:
        raise RuntimeError('SOURCE_PRICE_NOT_VERIFIED')
    if quote_data.get('sourceVatRateVerified10Pct') is not True or not quote_data.get('cloudLinePresent'):
        raise RuntimeError('VAT_OR_CLOUD_NOT_VERIFIED')
    if not isinstance(quote_data.get('sampleUnitNetKrw'),int) or not isinstance(quote_data.get('cloudUnitNetKrw'),int):
        raise RuntimeError('UNIT_PRICE_MISSING')
    n=int(row[10]);gb=float(row[11]);source_gb=quote_data.get('dataSize')
    if not isinstance(source_gb,(int,float)) or abs(gb-source_gb)>1e-8:
        raise RuntimeError('DATA_SIZE_CHANGE_REQUIRES_NEW_QUOTE')
    source_name=opp.get('name') or ''
    if row[7].strip()==source_name.strip():raise RuntimeError('DUPLICATE_OPPORTUNITY_NAME')
    if row[8].strip() and row[8].strip()!=str(opp.get('accountName','')).strip():
        raise RuntimeError('ACCOUNT_CHANGE_REQUIRES_CONTACT_REVIEW')
    if row[9].strip() and row[9].strip()!=str(opp.get('contactName','')).strip():
        raise RuntimeError('CONTACT_CHANGE_REQUIRES_LOOKUP')
    old_progress=str(opp.get('progressDescriptionSource') or '').strip()
    if old_progress and row[13].strip()==old_progress:
        raise RuntimeError('PROGRESS_DESCRIPTION_COPIED')
    units=math.ceil(n*gb/100)
    net=n*quote_data['sampleUnitNetKrw']+units*quote_data['cloudUnitNetKrw']
    if not isinstance(net,int) or net<=0 or net%10:raise RuntimeError('PRICE_INVALID')
    return net,net//10,units


def check_ledger(con,key):
    found=con.execute('SELECT status FROM ledger WHERE key=?',(key,)).fetchone()
    return found[0] if found else None


def process_row(row,results,script):
    record,req,fp,action,mode=row[:5]
    matching=[r for r in results if len(r)==len(RHEAD) and r[:3]==[record,req,fp]]
    if mode=='SAVE':
        # A successful preflight must exist in the separate, independently
        # written results sheet for this same immutable request payload.
        if not any(r[3]=='PREFLIGHT_PASS' and r[10]=='PREFLIGHT' for r in matching):
            return 'BLOCK','PREFLIGHT_PROOF_MISSING','',''
        # No multi-object transaction or verified Cloud process writer exists.
        # Never create a partial opportunity/quotation silently.
        return 'BLOCK','COMBINED_SFDC_SAVE_NOT_RELEASED','',''
    if action!='oppo_quote_pair':
        # Stage 2: lead and single-object writing needs separate verified mapping.
        return 'BLOCK','ACTION_PREFLIGHT_NOT_RELEASED','',''
    bundle=call_live_catalog(script,row[5])
    net,vat,units=price_pair(bundle,row)
    return 'PREFLIGHT_PASS','CLOUD_UNITS_'+str(units),str(net),str(vat)


def run(write):
    session=authorized_session()
    queue=get_rows(session,QUEUE,'A1:R750')
    results=get_rows(session,RESULTS,'A1:K1500')
    if not queue or queue[0][:len(QHEAD)]!=QHEAD:raise RuntimeError('QUEUE_SCHEMA_UNAVAILABLE')
    if not results or results[0][:len(RHEAD)]!=RHEAD:raise RuntimeError('RESULTS_SCHEMA_UNAVAILABLE')
    existing=results[1:]
    db_path=Path.home()/'.sfdc_desktop'/'feishu_agent_ledger.sqlite3'
    db_path.parent.mkdir(exist_ok=True,parents=True)
    con=sqlite3.connect(str(db_path),timeout=5)
    try:
        con.execute('CREATE TABLE IF NOT EXISTS ledger(key TEXT PRIMARY KEY,status TEXT, updated_at TEXT)')
        con.commit()
        script=Path(__file__).with_name('sfdc_record_catalog.py')
        tested=0;written=0;blocked=0
        for original in queue[1:]:
            if not original or not original[0]:continue
            row=validate_queue_row(original)
            if not row:blocked+=1;continue
            key=':'.join((row[0],row[2],row[4]))
            if check_ledger(con,key):continue
            # If a prior remote append succeeded but local ledger lost, never
            # re-execute. The remote result is an additional idempotency layer.
            if any(len(x)>=11 and x[0]==row[0] and x[2]==row[2] and x[10]==row[4] for x in existing):
                continue
            tested+=1
            if not write:continue
            # First durable claim, before even opening Salesforce UI.
            con.execute('INSERT INTO ledger(key,status,updated_at) VALUES(?,?,?)',
                        (key,'CLAIMED',dt.datetime.now(dt.timezone.utc).isoformat()))
            con.commit()
            try:status,code,net,vat=process_row(row,existing,script)
            except Exception as ex:
                status,code,net,vat='BLOCK',str(ex) if isinstance(ex,RuntimeError) and re.fullmatch('[A-Z_]{5,90}',str(ex)) else 'SFDC_PREFLIGHT_EXCEPTION','',''
            checked=dt.datetime.now(dt.timezone.utc).isoformat()
            report=[row[0],row[1],row[2],status,code,net,vat,'','',checked,row[4]]
            append_result(session,report)
            con.execute('UPDATE ledger SET status=?,updated_at=? WHERE key=?',(status,checked,key))
            con.commit();written+=1
            existing.append(report)
            if status=='BLOCK':blocked+=1
            if tested>=12:break
        return {'status':'PASS' if written else 'NO_NEW_DATA' if write else 'DRY_RUN',
                'queue_rows':len(queue)-1,'new_tasks_checked':tested,'results_written':written,
                'blocked_count':blocked,'crm_save_performed':False,
                'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()}
    finally:con.close()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--write-results',action='store_true')
    args=parser.parse_args()
    try:r=run(args.write_results)
    except Exception as e:
        r={'status':'BLOCK','error_type':type(e).__name__,'details_suppressed':True}
    print(json.dumps(r,sort_keys=True,ensure_ascii=True))
    return 0 if r['status']!='BLOCK' else 2

if __name__=='__main__':sys.exit(main())
