#!/usr/bin/env python3
"""Weekly operational rollup, anchored to existing CSS Quotation Weekly Summary (Fri-Thu)."""
import collections
import datetime as dt
import json
from followup_stage1 import auth,call,SOURCE_ID,OUTPUT_ID
from opportunity_quote_mirror import range_data,replace_tab

TAB="SFDC Weekly Overview"
HEAD=["week_start","week_end","weekly_basis","opportunity_created","opportunity_closed_target","opportunity_closed_won_target","quotation_approvals","approvals_created_in_week","approval_invoice_count","realized_invoice_amount_krw","active_quote_count","quote_active_unknown","source","data_quality"]
KST=dt.timezone(dt.timedelta(hours=9))
def get(row,i):
    return str(row[i]).strip() if i is not None and i<len(row) and row[i] is not None else ""
def index(header,key):
    try:return header.index(key)
    except ValueError:return None
def parse_date(x):
    x=str(x or "").strip()
    if not x:return None
    for fmt in ("%Y-%m-%d","%m/%d/%Y","%-m/%-d/%Y","%m/%d/%y"):
        try:return dt.datetime.strptime(x[:10],fmt).date()
        except ValueError:pass
    for fmt in ("%Y-%m-%dT%H:%M:%S","%Y-%m-%d %H:%M:%S"):
        try:return dt.datetime.strptime(x[:19],fmt).date()
        except ValueError:pass
    return None
def numeric(x):
    try:return int(float(str(x or "0").replace(",","")))
    except ValueError:return 0
def week_start(day):
    return day-dt.timedelta(days=(day.weekday()-4)%7)
def main():
    sess=auth()
    op=range_data(sess,OUTPUT_ID,"SFDC Opportunity Raw",2000)
    css=range_data(sess,SOURCE_ID,"Quotation Weekly Summary",2000)
    audits=range_data(sess,OUTPUT_ID,"SFDC Quote Link Audit",40)
    if not op or not css:raise RuntimeError("Required weekly source missing")
    oh=op[0]; ch=css[0]
    if not {"week_start","week_end","quotation_count"}.issubset(set(ch)):
        raise RuntimeError("CSS weekly source schema incompatible")
    created,closed,won=collections.Counter(),collections.Counter(),collections.Counter()
    for row in op[1:]:
        d=parse_date(get(row,index(oh,"Created Date")))
        if d:created[week_start(d)]+=1
        close=parse_date(get(row,index(oh,"Close Date")))
        if close:
            wk=week_start(close)
            closed[wk]+=1
            if get(row,index(oh,"Stage")).strip().lower()=="closed won":won[wk]+=1
    all_week={}
    for row in css[1:]:
        begin=parse_date(get(row,index(ch,"week_start")))
        end=parse_date(get(row,index(ch,"week_end")))
        if not begin or end!=begin+dt.timedelta(days=6):continue
        all_week[begin]=row
    keys=sorted(set(created)|set(closed)|set(all_week),reverse=True)
    result=[HEAD]
    for wk in keys:
        w=all_week.get(wk,[])
        value=lambda key:get(w,index(ch,key))
        result.append([wk.isoformat(),(wk+dt.timedelta(days=6)).isoformat(),"FRI_THU_CSS_EXISTING",
            created[wk],closed[wk],won[wk],
            numeric(value("quotation_count")) if w else "",
            numeric(value("created_in_week_count")) if w else "",
            numeric(value("realized_invoice_count")) if w else "",
            value("realized_amount_krw") if w else "",
            "", "", "SFDC_Auto Oppo list + CSS Quotation Weekly Summary",
            "Quote Active not in snapshot; invoice realized from CSS source; Close Date is target, not actual close"])
    audit={get(r,0):get(r,1) for r in audits[1:] if len(r)>1}
    # Do not spread global Active status across weeks: Quote's date and status are not both known.
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(sess,"GET",root+"?fields=sheets.properties",stage="weekly_metadata")
    if TAB not in {x["properties"]["title"] for x in meta["sheets"]}:
        call(sess,"POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":TAB,"hidden":True}}}]},stage="weekly_create")
    replace_tab(sess,TAB,result)
    metadata=call(sess,'GET',root+'?fields=sheets.properties',stage='weekly_visibility')
    tab=next(v['properties'] for v in metadata['sheets'] if v['properties']['title']==TAB)
    if not tab.get('hidden'):
        call(sess,'POST',root+':batchUpdate',json={'requests':[{'updateSheetProperties':{'properties':{'sheetId':tab['sheetId'],'hidden':True},'fields':'hidden'}}]},stage='weekly_hide')
    print(json.dumps({"weeks":len(result)-1,"opportunity_rows":len(op)-1,
        "quotation_active_unknown_global":audit.get("unknown_status","UNAVAILABLE"),
        "latest_week":str(keys[0]) if keys else None}))
if __name__=="__main__":main()
