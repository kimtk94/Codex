#!/usr/bin/env python3
"""Append conservative SFDC relationship evidence to the existing Customer 360 tab."""
import json
import re
from collections import defaultdict
from followup_stage1 import auth,OUTPUT_ID
from opportunity_quote_mirror import range_data,replace_tab

TAB="CSS Customer 360"
EXTRA=["sfdc_account_name_matches","sfdc_opportunities_name_matched",
       "sfdc_contacts_account_matched","sfdc_main_contacts_exact_matched",
       "sfdc_quote_candidates_name_date","css_contracts_amea_matched",
       "css_contract_numbers","relation_quality"]
def clean(v):return " ".join(str(v or "").strip().casefold().split())
def rows(source):
    if not source:return []
    h=source[0]
    return [{str(k):r[i] if i<len(r) else "" for i,k in enumerate(h)} for r in source[1:]]
def main():
    session=auth()
    customer=range_data(session,OUTPUT_ID,TAB,2000)
    opp=rows(range_data(session,OUTPUT_ID,"Opportunity",2000))
    contacts=rows(range_data(session,OUTPUT_ID,"SFDC Contacts",2000))
    contracts=rows(range_data(session,OUTPUT_ID,"CSS Contract-SIF",2000))
    links=rows(range_data(session,OUTPUT_ID,"SFDC Active Quote Links",2000))
    if not customer:raise RuntimeError("Customer 360 missing")
    h=customer[0]
    if "institution" not in h or "project_ids" not in h:raise RuntimeError("Customer 360 schema changed")
    # The CSS Institution label often abbreviates the Salesforce Account name.
    # No fuzzy Account matching is allowed; no false verified identities.
    opbyaccount=defaultdict(list);contactbyaccount=defaultdict(list)
    for r in opp:opbyaccount[clean(r.get("Account Name"))].append(r)
    for r in contacts:contactbyaccount[clean(r.get("Account Name"))].append(r)
    linked=defaultdict(int)
    for r in links:
        if r.get("link_result") in ("NAME_MATCH_UNIQUE","NAME_DATE_MATCH_UNIQUE","MATCHED_BY_ID"):
            linked[clean(r.get("matched_opportunity_name"))]+=1
    base=[x for x in h if x not in EXTRA]
    width=len(base)
    output=[base+EXTRA]
    summary={"customer_rows":0,"account_matches":0,"contract_links":0}
    for r in customer[1:]:
        data=dict(zip(h,r))
        inst=clean(data.get("institution"))
        os=opbyaccount.get(inst,[])
        cs=contactbyaccount.get(inst,[])
        emailname=lambda c:clean((str(c.get("First Name") or "")+" "+str(c.get("Last Name") or "")).strip())
        mains=sum(1 for x in os for c in cs if emailname(c)==clean(x.get("Main Contact")) and emailname(c))
        projects=set(re.findall(r"AMEA\\d+",str(data.get("project_ids") or ""),flags=re.I))
        project_upper={x.upper() for x in projects}
        contractset=[x for x in contracts if str(x.get("AMEA No.") or "").upper() in project_upper]
        contractnums=sorted({str(x.get("Contract No.") or "") for x in contractset if x.get("Contract No.")})
        quote_count=sum(linked[clean(x.get("Opportunity Name"))] for x in os)
        quality="AMEA_CONTRACT_AND_ACCOUNT_EXACT" if contractset and os else "AMEA_CONTRACT_ONLY" if contractset else "ACCOUNT_NAME_EXACT_ONLY" if os or cs else "NO_SFDC_EXACT_ACCOUNT_MATCH"
        if os or cs:summary["account_matches"]+=1
        summary["contract_links"]+=len(contractset)
        values=[1 if os or cs else 0,len(os),len(cs),mains,quote_count,len(contractset)," | ".join(contractnums),quality]
        output.append([data.get(k,"") for k in base]+values)
        summary["customer_rows"]+=1
    replace_tab(session,TAB,output)
    verified=range_data(session,OUTPUT_ID,TAB,2000)
    if len(verified)!=len(output) or verified[0]!=output[0]:
        raise RuntimeError("Customer 360 relation enrichment failed")
    print(json.dumps(summary))
if __name__=="__main__":main()
