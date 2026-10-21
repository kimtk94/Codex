#!/usr/bin/env python3
"""Strict Salesforce Opportunity/Quote related-ID reconciliation.
Only the Salesforce Active checkbox is authoritative; quote lifecycle status is separate.
"""
import json
from collections import Counter
from datetime import datetime
from followup_stage1 import auth, call, OUTPUT_ID
from opportunity_quote_mirror import range_data, replace_tab

TAB="SFDC Active Quote Links"
AUDIT="SFDC Quote Link Audit"
HEAD=["sfdc_quotation_id","amea_quotation_id","opportunity_id","quote_name","quote_status","is_active","link_result","valid_quote","reason","matched_opportunity_name","match_method","matched_close_date"]
def pick(h,options):
    normalized={str(k).strip().lower():i for i,k in enumerate(h)}
    for candidate in options:
        if candidate.lower() in normalized:return normalized[candidate.lower()]
    return None
def get(row,i):
    return str(row[i]).strip() if i is not None and i<len(row) and row[i] is not None else ""
def main():
    sess=auth()
    q=range_data(sess,OUTPUT_ID,"Quotation",2000)
    o=range_data(sess,OUTPUT_ID,"SFDC Opportunity Raw",2000)
    if not q or not o: raise RuntimeError("Missing mirrored Opportunity/Quotation")
    qi=pick(q[0],["SFDC Quotation ID","Salesforce Quotation ID","Quote Record ID","Id"])
    amea=pick(q[0],["Quotation ID","AMEA No.","AMEA ID"])
    oi=pick(q[0],["Opportunity ID","OpportunityId","Opportunity: ID"])
    st=pick(q[0],["Quote Status","Quotation Status","Status"])
    active=pick(q[0],["IsActive","Is Active","Active","Is Active Quote"])
    name=pick(q[0],["Quote Name","Quotation Name","Name","Opportunity Name"])
    opportunity_id=pick(o[0],["Opportunity ID","OpportunityId","Id"])
    known={get(row,opportunity_id) for row in o[1:] if get(row,opportunity_id)} if opportunity_id is not None else set()
    def normalized(v):return " ".join(str(v or "").strip().casefold().split())
    qname=pick(q[0],["Opportunity Name"])
    oname=pick(o[0],["Opportunity Name"])
    names={}
    if oname is not None:
        for opp in o[1:]:
            key=normalized(get(opp,oname))
            if key:names.setdefault(key,[]).append(opp)
    qclose=pick(q[0],["Close Date"])
    oclose=pick(o[0],["Close Date"])
    def normdate(v):
        v=str(v or "").strip()
        for pattern in ("%m/%d/%Y","%Y-%m-%d","%m/%d/%y"):
            try:return datetime.strptime(v,pattern).strftime("%Y-%m-%d")
            except ValueError:pass
        return v
    rows=[HEAD];stats=Counter();match_stats=Counter()
    for row in q[1:]:
        status=get(row,st)
        flag=get(row,active).lower()
        valid="YES" if flag in ("true","yes","1","✓","✔","checked") else "NO" if flag in ("false","no","0","unchecked") else "UNKNOWN"
        qid=get(row,qi);oid=get(row,oi)
        candidates=names.get(normalized(get(row,qname)),[]) if qname is not None else []
        matched_name=""
        method="NONE"
        matched_date=""
        if oid and oid in known:
            link="MATCHED_BY_ID"
            method="OPPORTUNITY_ID"
        elif len(candidates)==1:
            link="NAME_MATCH_UNIQUE"
            matched_name=get(candidates[0],oname)
            method="EXACT_NORMALIZED_NAME"
            matched_date=normdate(get(candidates[0],oclose))
        elif len(candidates)>1:
            qdate=normdate(get(row,qclose))
            dated=[v for v in candidates if qdate and normdate(get(v,oclose))==qdate]
            if len(dated)==1:
                link="NAME_DATE_MATCH_UNIQUE"
                matched_name=get(dated[0],oname)
                matched_date=qdate
                method="EXACT_NAME_AND_CLOSE_DATE"
            else:
                link="NAME_AMBIGUOUS"
        else:
            link="NO_NAME_MATCH"
        match_stats[link]+=1
        reason=("missing Active checkbox" if valid=="UNKNOWN" else
                "not explicitly active" if valid=="NO" else
                "active but related Opportunity ID not verified" if link!="MATCHED" else "verified")
        rows.append([qid,get(row,amea),oid,get(row,name),status,flag,link,valid,reason,matched_name,method,matched_date])
        stats[valid]+=1
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(sess,"GET",root+"?fields=sheets.properties",stage="quote_link_metadata")
    existing={item["properties"]["title"] for item in meta["sheets"]}
    requests=[{"addSheet":{"properties":{"title":tab,"hidden":True}}} for tab in (TAB,AUDIT) if tab not in existing]
    if requests:call(sess,"POST",root+":batchUpdate",json={"requests":requests},stage="quote_link_create")
    replace_tab(sess,TAB,rows)
    audit=[["metric","value"],["quote_rows",len(q)-1],["active",stats["YES"]],
           ["inactive",stats["NO"]],["unknown_status",stats["UNKNOWN"]],
           ["sfdc_quote_id_column_present",str(qi is not None)],["amea_quote_id_column_present",str(amea is not None)],["related_opportunity_id_column_present",str(oi is not None)],
           ["opportunity_id_column_present",str(opportunity_id is not None)],
           ["name_match_unique",match_stats["NAME_MATCH_UNIQUE"]],["name_date_match_unique",match_stats["NAME_DATE_MATCH_UNIQUE"]],["name_match_ambiguous",match_stats["NAME_AMBIGUOUS"]],["name_match_missing",match_stats["NO_NAME_MATCH"]],["source","SFDC_Auto exported snapshot; not live Salesforce"]]
    replace_tab(sess,AUDIT,audit)
    # Enrich the visible Opportunity mirror AFTER the raw mirror refresh.
    # Only uniquely matched names or verified record IDs may contribute to counts.
    summary={}
    for linkrow in rows[1:]:
        if linkrow[6] not in ("MATCHED_BY_ID","NAME_MATCH_UNIQUE","NAME_DATE_MATCH_UNIQUE"):
            continue
        key=normalized(linkrow[9]) if linkrow[9] else ""
        if not key and linkrow[6]=="MATCHED_BY_ID":
            source_id=linkrow[2]
            candidates_by_id=[opp for opp in o[1:] if get(opp,opportunity_id)==source_id]
            if len(candidates_by_id)==1:key=normalized(get(candidates_by_id[0],oname))
        if not key:continue
        if linkrow[6]=="NAME_DATE_MATCH_UNIQUE":key+="|"+linkrow[11]
        bucket=summary.setdefault(key,{"total":0,"active":0,"unknown":0,"inactive":0})
        bucket["total"]+=1
        if linkrow[7]=="YES":bucket["active"]+=1
        elif linkrow[7]=="NO":bucket["inactive"]+=1
        else:bucket["unknown"]+=1
    extra=["linked_quote_count_name_or_id","active_quote_count_confirmed",
           "quote_active_unknown_count","inactive_quote_count_confirmed","quote_relationship_evidence"]
    base_header=list(o[0])
    # Do not carry forward previous enrichment columns.
    for column in extra:
        if column in base_header:
            base_header=base_header[:base_header.index(column)]
            break
    width=len(base_header)
    enriched=[base_header+extra]
    for opp in o[1:]:
        original=(list(opp)+[""]*width)[:width]
        namekey=normalized(get(opp,oname))
        if len(names.get(namekey,[]))>1:namekey+="|"+normdate(get(opp,oclose))
        count=summary.get(namekey,{"total":0,"active":0,"unknown":0,"inactive":0})
        confidence="NAME_MATCH_UNIQUE (not Salesforce Related ID)" if count["total"] else "NO_VERIFIED_QUOTE_RELATION"
        enriched.append(original+[count["total"],count["active"],count["unknown"],count["inactive"],confidence])
    replace_tab(sess,"Opportunity",enriched)
    check=range_data(sess,OUTPUT_ID,"Opportunity",2000)
    if not check or check[0][:len(enriched[0])]!=enriched[0]:
        raise RuntimeError("Opportunity enrichment missing after write")
    if len(check)!=len(o):
        raise RuntimeError(f"Opportunity row preservation failed: raw={len(o)-1}, published={len(check)-1}")
    expected_names=[get(r,oname) for r in o[1:]]
    published_names=[get(r,oname) for r in check[1:]]
    if expected_names!=published_names:
        raise RuntimeError("Opportunity identity/order mismatch (duplicate records must remain separate)")
    if len(rows)-1!=len(q)-1:
        raise RuntimeError("Quotation rows lost during reconciliation")
    observed=sum(int(r[check[0].index("linked_quote_count_name_or_id")] or 0) for r in check[1:])
    expected=sum(1 for r in rows[1:] if r[6] in ("MATCHED_BY_ID","NAME_MATCH_UNIQUE","NAME_DATE_MATCH_UNIQUE"))
    if observed!=expected:
        raise RuntimeError(f"Opportunity quote count mismatch: observed={observed} expected={expected}")
    print(json.dumps({"quote_rows":len(q)-1,"active":stats["YES"],"inactive":stats["NO"],
      "unknown":stats["UNKNOWN"],"related_ids_available":oi is not None and opportunity_id is not None}))
if __name__=="__main__":main()
