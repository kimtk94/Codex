#!/usr/bin/env python3
"""Mirror newest authorized Feishu sources into private generated Sheets; no Feishu writes."""
import datetime as dt
import json
import os
import re
import urllib.parse
from collections import Counter
from zoneinfo import ZoneInfo
from latest_four_formats import select
from sheets_tab_discovery import api as feishu, TOKEN
from base_readonly_probe import request, require
from payment_table_audit import list_pages

DESTS={'Payment Outstanding':'Feishu Latest Outstanding','Payment Receipt':'Feishu Latest Receipts','Prepayments':'Feishu Latest Prepayments','eTax Invoice':'Feishu Latest eTax','Online-Project':'Feishu Latest Online'}
LIMIT=10000

def text(value):
    if value is None:return ''
    if isinstance(value,list):return ' '.join(text(v) for v in value)
    if isinstance(value,dict):return text(value.get('text',value.get('name',value.get('value',json.dumps(value,ensure_ascii=False)))))
    return str(value)
def norm(value):return re.sub(r'[^a-z0-9]','',text(value).lower())
def shape(grid):
    """Find a real header within title rows; otherwise preserve the grid as raw columns."""
    known={'projectnumber','subprojectnumber','projectno','contractnumber','invoicenumber','customername','currency','amount','paymentamount','quotationnumber'}
    scores=[sum(norm(c) in known for c in r) for r in grid[:20]]
    index=max(range(len(scores)),key=scores.__getitem__) if scores else 0
    identified=bool(scores and scores[index]>=2)
    width=max((len(r) for r in grid),default=0)
    if not width:raise RuntimeError('EMPTY_SOURCE')
    base=grid[index] if identified else ['Column '+str(i+1) for i in range(width)]
    seen=Counter();headers=[]
    for i in range(width):
        h=text(base[i]).strip() if i<len(base) else ''
        h=h or 'Column '+str(i+1);seen[h]+=1
        headers.append(h if seen[h]==1 else h+' ['+str(seen[h])+']')
    rows=[r+['']*(width-len(r)) for r in grid[index+1:] if any(text(v).strip() for v in r)] if identified else [r+['']*(width-len(r)) for r in grid if any(text(v).strip() for v in r)]
    return headers,rows,'HEADER_MATCHED' if identified else 'RAW_GRID_REVIEW'
def collect():
    now=dt.datetime.now(ZoneInfo('Asia/Seoul'));stamp=now.isoformat()
    auth=feishu('/open-apis/auth/v3/tenant_access_token/internal',payload={'app_id':require('FEISHU_APP_ID'),'app_secret':require('FEISHU_APP_SECRET')})
    token=auth.get('tenant_access_token')
    if not token:raise RuntimeError('AUTH_FAILED')
    tabs=feishu('/open-apis/sheets/v3/spreadsheets/'+TOKEN+'/sheets/query',token).get('sheets')
    selected,_=select(tabs,now.date())
    if selected is None:raise RuntimeError('MISSING_LATEST_FORMAT')
    snapshots={}
    for fmt,item in selected.items():
        tab=next(t for t in tabs if t['sheet_id']==item['sheet_id'])
        count=int(tab.get('grid_properties',{}).get('row_count') or LIMIT)
        cols=int(tab.get('grid_properties',{}).get('column_count') or 52)
        if count>LIMIT or cols>52:raise RuntimeError('SOURCE_EXCEEDS_BOUNDS')
        span=urllib.parse.quote(item['sheet_id']+'!A1:AZ'+str(count),safe='!:')
        data=feishu('/open-apis/sheets/v2/spreadsheets/'+TOKEN+'/values/'+span,token)
        grid=(data.get('valueRange') or {}).get('values') or []
        headers,rows,schema=shape([[text(v) for v in r] for r in grid])
        if not rows:raise RuntimeError('EMPTY_SOURCE_REFUSE_OVERWRITE')
        snapshots[fmt]={'title':DESTS[fmt],'headers':headers,'rows':rows,'schema':schema,'source_date':item['date'],'source_id':item['sheet_id'],'synced_at':stamp}
    prefix='/open-apis/bitable/v1/apps/'+urllib.parse.quote(require('FEISHU_BASE_APP_TOKEN'),safe='')
    tables=list(list_pages(prefix+'/tables',token));matches=[t for t in tables if t.get('name')=='Online-Project']
    if len(matches)!=1:raise RuntimeError('ONLINE_SOURCE_AMBIGUOUS')
    root=prefix+'/tables/'+matches[0]['table_id']
    fields=list(list_pages(root+'/fields',token));records=list(list_pages(root+'/records',token))
    ids=[r.get('record_id') for r in records]
    if not ids or not all(ids) or len(set(ids))!=len(ids):raise RuntimeError('ONLINE_RECORD_IDS_INVALID')
    headers=['Feishu Record ID']+[f['field_name'] for f in fields]
    rows=[[r['record_id']]+[text((r.get('fields') or {}).get(h)) for h in headers[1:]] for r in records]
    snapshots['Online-Project']={'title':DESTS['Online-Project'],'headers':headers,'rows':rows,'schema':'BASE_FIELDS','source_date':now.date().isoformat(),'source_id':matches[0]['table_id'],'synced_at':stamp}
    return snapshots

def publish(session,snapshots):
    from project_status_sync import api,SHEET
    manifest=[['Source','Source Date','Synced At KST','Source ID','Rows','Schema','Meaning']]
    tables={}
    for fmt,s in snapshots.items():
        tables[s['title']]=[s['headers']]+s['rows']
        meaning={'Payment Outstanding':'Outstanding snapshot; absence is not payment evidence','Payment Receipt':'Receipt evidence; no automatic invoice settlement','Prepayments':'Prepayment evidence; not issued revenue','eTax Invoice':'eTax source; issuance requires explicit evidence','Online-Project':'Project status; forecast is not revenue'}[fmt]
        manifest.append([fmt,s['source_date'],s['synced_at'],s['source_id'],len(s['rows']),s['schema'],meaning])
    tables['Feishu Source Manifest']=manifest
    meta=api(session,'GET','?fields=sheets.properties')
    props={s['properties']['title']:s['properties'] for s in meta.get('sheets',[])}
    requests=[];nextid=2036102801
    used={p['sheetId'] for p in props.values()}
    for title,rows in tables.items():
        width=max(map(len,rows));height=len(rows)
        if title not in props:
            while nextid in used:nextid+=1
            p={'sheetId':nextid,'title':title,'gridProperties':{'rowCount':height+10,'columnCount':width,'frozenRowCount':1}}
            requests.append({'addSheet':{'properties':p}});props[title]=p;used.add(nextid)
        else:
            p=props[title];grid=p.get('gridProperties',{})
            requests.append({'updateSheetProperties':{'properties':{'sheetId':p['sheetId'],'gridProperties':{'rowCount':max(height+10,grid.get('rowCount',0)),'columnCount':max(width,grid.get('columnCount',0))}},'fields':'gridProperties.rowCount,gridProperties.columnCount'}})
        grid=p.get('gridProperties',{});endrow=max(height,grid.get('rowCount',height));endcol=max(width,grid.get('columnCount',width))
        # One atomic batch replaces generated cells, including stale trailing rows.
        requests.append({'updateCells':{'range':{'sheetId':p['sheetId'],'startRowIndex':0,'endRowIndex':endrow,'startColumnIndex':0,'endColumnIndex':endcol},'rows':[{'values':[{'userEnteredValue':{'stringValue':text(v)}} for v in r]} for r in rows],'fields':'userEnteredValue'}})
    api(session,'POST',':batchUpdate',json={'requests':requests})
    # Verify row counts and chosen source versions without logging customer values.
    for title,rows in tables.items():
        addr=urllib.parse.quote("'"+title+"'!A1:AZ"+str(len(rows)),safe='')
        got=api(session,'GET','/values/'+addr).get('values',[])
        if len(got)!=len(rows):raise RuntimeError('READBACK_ROW_COUNT_MISMATCH')
    print('FEISHU_LATEST_SYNC_PASS sources='+str(len(snapshots))+' rows='+str(sum(len(x['rows']) for x in snapshots.values())))
    for fmt,s in snapshots.items(): print('SOURCE',fmt,'DATE',s['source_date'],'ROWS',len(s['rows']),'SCHEMA',s['schema'])
    return snapshots

def main():
    from project_status_sync import google
    return publish(google(),collect())
if __name__=='__main__':
    try:main()
    except Exception as exc:
        print('FEISHU_LATEST_SYNC_FAILED '+type(exc).__name__);raise SystemExit(1)
