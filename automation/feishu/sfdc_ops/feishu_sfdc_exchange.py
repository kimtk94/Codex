#!/usr/bin/env python3
"""Private Feishu Base <-> Google Sheets transport (GitHub Actions only).

Feishu writes are only result columns. No Salesforce credentials or browser actions.
"""
from __future__ import annotations
import argparse
import base64
import datetime as dt
import json
import os
import sys
from urllib.parse import quote
from feishu_sfdc_bridge import (auth, ensure_table, paginate, request, url_base,
    validate_request, pure_reconcile, SOURCE_BOOK, QUEUE_TAB, RESULTS_TAB,
    QUEUE_COLUMNS, RESULT_COLUMNS, FIELDS, text_field)


def google_session():
    from google.oauth2.service_account import Credentials
    from google.auth.transport.requests import AuthorizedSession
    raw=os.getenv('GCP_SERVICE_ACCOUNT_JSON','')
    if not raw:raise RuntimeError('GOOGLE_AUTH_UNAVAILABLE')
    try:info=json.loads(raw)
    except ValueError:info=json.loads(base64.b64decode(raw))
    cred=Credentials.from_service_account_info(info,scopes=['https://www.googleapis.com/auth/spreadsheets'])
    return AuthorizedSession(cred)


def sheets_api(session,method,route,**kwargs):
    url='https://sheets.googleapis.com/v4/spreadsheets/'+SOURCE_BOOK+route
    resp=session.request(method,url,timeout=48,**kwargs)
    resp.raise_for_status()
    return resp.json()


def range_url(tab,rng):
    return '/values/'+quote("'"+tab.replace("'","''")+"'!"+rng,safe="!'$:")


def read_sheet(session,tab,rng):
    return sheets_api(session,'GET',range_url(tab,rng)).get('values',[])


def bootstrap_sheets(session):
    info=sheets_api(session,'GET','',params={'fields':'sheets(properties(title,gridProperties(rowCount,columnCount)))'})
    names={x['properties']['title']:x['properties']['gridProperties'] for x in info.get('sheets',[])}
    add=[{'addSheet':{'properties':{'title':name,'gridProperties':{
        'rowCount':1500,'columnCount':20,'frozenRowCount':1}}}}
        for name in (QUEUE_TAB,RESULTS_TAB) if name not in names]
    if add:sheets_api(session,'POST',':batchUpdate',json={'requests':add})
    for name,cols in ((QUEUE_TAB,QUEUE_COLUMNS),(RESULTS_TAB,RESULT_COLUMNS)):
        top=read_sheet(session,name,'A1:T1')
        if not top or not top[0]:
            write_range(session,name,'A1:'+chr(64+len(cols))+'1',[cols])
        elif top[0][:len(cols)]!=cols:
            raise RuntimeError('SHEET_HEADER_SCHEMA_MISMATCH')


def write_range(session,tab,rng,rows):
    return sheets_api(session,'PUT',range_url(tab,rng),params={'valueInputOption':'RAW'},json={
        'range':"'"+tab+"'!"+rng,'majorDimension':'ROWS','values':rows})


def publish_queue(session,rows):
    if len(rows)>700:raise RuntimeError('QUEUE_TOO_LARGE')
    # The queue is a projection, not the task ledger; the desktop worker keeps
    # durable processing state in local SQLite and a separate results sheet.
    padded=[QUEUE_COLUMNS]+rows+[['']*len(QUEUE_COLUMNS) for _ in range(750-len(rows))]
    write_range(session,QUEUE_TAB,'A1:R'+str(len(padded)),padded)
    verify=read_sheet(session,QUEUE_TAB,'A1:R'+str(len(rows)+1))
    for wanted,found in zip([QUEUE_COLUMNS]+rows,verify):
        if [str(x).strip() for x in wanted]!=[str(x).strip() for x in (found+['']*(len(wanted)-len(found)))]:
            raise RuntimeError('QUEUE_READBACK_MISMATCH')
    if len(verify)!=len(rows)+1:
        raise RuntimeError('QUEUE_SHORT_READBACK')
    return True


def updates_from_results(token,app,table_id,requests,results,records):
    # Select only independently verified private-Sheet results for current payload.
    outgoing=pure_reconcile(requests,results)
    by_id={r['record_id']:r for r in records}
    changed=0
    for update in outgoing:
        rid=update['record_id']
        original=by_id.get(rid)
        if not original:continue
        fields=original.get('fields') or {}
        desired=update['fields']
        if all(text_field(fields.get(k))==str(v) for k,v in desired.items()):continue
        path=url_base(app)+'/tables/'+quote(table_id,safe='')+'/records/'+quote(rid,safe='')
        request('PUT',path,token,{'fields':desired})
        changed+=1
    return changed


def sync(write):
    token,app=auth()
    table_id,_,_=ensure_table(token,app,False)
    path=url_base(app)+'/tables/'+quote(table_id,safe='')
    records=paginate(path+'/records',token)
    requests=[]
    for record in records:
        row=validate_request(record)
        if row is not None:requests.append(row)
    if len({r[0] for r in requests})!=len(requests):
        raise RuntimeError('DUPLICATE_FEISHU_ROW_IDS')
    # Feishu without a ready request is not an inaccessible source.
    session=google_session()
    if write:bootstrap_sheets(session)
    else:
        # Read-only mode validates access but cannot bootstrap queue.
        read_sheet(session,QUEUE_TAB,'A1:R1')
    results=read_sheet(session,RESULTS_TAB,'A1:K1500')
    if not results or results[0][:len(RESULT_COLUMNS)]!=RESULT_COLUMNS:
        raise RuntimeError('RESULTS_SHEET_SCHEMA_MISMATCH')
    if write:
        publish_queue(session,requests)
        changed=updates_from_results(token,app,table_id,requests,results[1:],records)
    else:changed=0
    return {'status':'PASS' if requests else 'NO_NEW_DATA',
            'source_records':len(records),'eligible_requests':len(requests),
            'queue_readback':'PASS' if write else 'NOT_CHECKED_DRY_RUN',
            'result_rows_examined':len(results)-1,
            'feishu_results_updated':changed,
            'sf_browser_access':'NOT_AVAILABLE_IN_ACTIONS',
            'crm_write_performed':False,
            'checked_at':dt.datetime.now(dt.timezone.utc).isoformat()}


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--write',action='store_true')
    a=p.parse_args()
    try:r=sync(a.write)
    except Exception as ex:
        r={'status':'BLOCK','error_type':type(ex).__name__,'error_details_suppressed':True}
    print(json.dumps(r,sort_keys=True,ensure_ascii=True))
    return 0 if r['status'] in ('PASS','NO_NEW_DATA') else 2

if __name__=='__main__':sys.exit(main())
