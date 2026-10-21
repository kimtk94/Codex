#!/usr/bin/env python3
"""Unified read-only action dashboard from independently labelled source ledgers."""
import datetime as dt
import json
from followup_stage1 import auth, call, OUTPUT_ID
from opportunity_quote_mirror import range_data, replace_tab

TAB="Action Dashboard"
HEADER=["priority","workstream","institution","customer","reference_id","status","next_action","due_or_event_date","source_tab","source_note","source_uid","attention_bucket"]
def records(session,tab,limit=6000):
    data=range_data(session,OUTPUT_ID,tab,limit)
    if not data:return []
    header=[str(c).strip() for c in data[0]]
    return [{k:(row[i] if i<len(row) else "") for i,k in enumerate(header)} for row in data[1:] if any(str(v).strip() for v in row)]
def s(v):return str(v or "").strip()
def main():
    session=auth()
    data=[HEADER]
    tally={}
    seen=set()
    today=dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    def add(priority,workstream,inst,customer,ref,status,action,date,tab,note,uid):
        identity=(workstream,ref or uid,action)
        if identity in seen:return
        seen.add(identity)
        due=None
        try:due=dt.date.fromisoformat(str(date)[:10])
        except (ValueError,TypeError):pass
        bucket=("OVERDUE" if due and due<today else "TODAY" if due==today else "UPCOMING" if due and due>today else "CHECK_DATE")
        if workstream in ("SFDC Follow-up","Quote / Invoice"):bucket="VERIFY"
        data.append([priority,workstream,inst,customer,ref,status,action,date,tab,note,uid,bucket])
        tally[workstream]=tally.get(workstream,0)+1
    for x in records(session,"SFDC Follow-up",1200):
        add(s(x.get("priority")), "SFDC Follow-up",s(x.get("institution")),s(x.get("customer_name")),s(x.get("record_id")),
            s(x.get("followup_status")),s(x.get("recommended_action")),s(x.get("latest_event")),"SFDC Follow-up",
            "Email-derived SFDC enquiry; follow-up requires verification",s(x.get("source_uid")))
    for x in records(session,"CSS Action Center",1200):
        if s(x.get("status")) in ("완료","종료","제외","Done","Closed","Resolved"):continue
        add(s(x.get("priority")),"CSS Action",s(x.get("institution")),s(x.get("customer_name")),s(x.get("project_id") or x.get("task_id")),
            s(x.get("status")),s(x.get("recommended_action") or x.get("reason")),s(x.get("due_date")),"CSS Action Center",
            "Existing CSS operational task",s(x.get("task_id")))
    for x in records(session,"CSS Contract-SIF",1200):
        if s(x.get("skip")).lower() in ("true","1","yes"):continue
        if s(x.get("Status")).lower() in ("complete","completed","closed","종료","완료"):continue
        add("높음" if s(x.get("Aging Days")).isdigit() and int(s(x.get("Aging Days")))>4 else "보통",
            "Contract / SIF",s(x.get("Institution")),s(x.get("Customer Name")),s(x.get("AMEA No.")),
            s(x.get("Status")),s(x.get("Next Action")),s(x.get("Date")),"CSS Contract-SIF",
            "Verify current status; email-derived",s(x.get("source_uid")))
    # Invoice status is not an action unless the approval is outstanding with no invoice.
    for x in records(session,"Quotation Approvals",1500):
        if s(x.get("invoice_match_status")).lower() not in ("not invoiced","unmatched"):continue
        add("보통","Quote / Invoice", "", "",s(x.get("quotation_id")),s(x.get("invoice_match_status")),
            "견적 승인 후 실제 청구 필요 여부 확인",s(x.get("approved_at_kst")),"Quotation Approvals",
            "Not invoiced does not by itself mean overdue or ready to invoice",s(x.get("uid")))
    ranks={"긴급":0,"높음":1,"보통":2,"낮음":3}
    buckets={"OVERDUE":0,"TODAY":1,"CHECK_DATE":2,"VERIFY":3,"UPCOMING":4}
    data[1:]=sorted(data[1:],key=lambda row:(buckets.get(row[11],5),ranks.get(row[0],4),row[1],row[4]))
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(session,"GET",root+"?fields=sheets.properties",stage="action_metadata")
    if TAB not in {x["properties"]["title"] for x in meta["sheets"]}:
        call(session,"POST",root+":batchUpdate",json={"requests":[{"addSheet":{"properties":{"title":TAB,"index":0}}}]},stage="action_create")
    replace_tab(session,TAB,data)
    metadata=call(session,"GET",root+"?fields=sheets.properties",stage="action_layout_metadata")
    sid=next(x["properties"]["sheetId"] for x in metadata["sheets"] if x["properties"]["title"]==TAB)
    call(session,"POST",root+":batchUpdate",stage="action_layout",json={"requests":[
      {"updateSheetProperties":{"properties":{"sheetId":sid,"index":0,"hidden":False,
       "gridProperties":{"frozenRowCount":1},
       "tabColorStyle":{"rgbColor":{"red":0.78,"green":0.29,"blue":0.20}}},
       "fields":"index,hidden,gridProperties.frozenRowCount,tabColorStyle"}},
      {"repeatCell":{"range":{"sheetId":sid,"startRowIndex":0,"endRowIndex":1},
       "cell":{"userEnteredFormat":{"backgroundColor":{"red":0.78,"green":0.29,"blue":0.20},
       "textFormat":{"bold":True,"foregroundColor":{"red":1,"green":1,"blue":1}}}},
       "fields":"userEnteredFormat(backgroundColor,textFormat)"}}
    ]})
    print(json.dumps({"status":"ok","action_rows":len(data)-1,"by_source":tally},ensure_ascii=False))
if __name__=="__main__":main()
