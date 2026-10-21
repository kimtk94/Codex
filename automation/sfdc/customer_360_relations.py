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
# Explicit institution aliases; never fuzzy-match customer or contact names.
# A canonical account may aggregate multiple legal Account names from the same institution.
ALIASES={
"yonsei univ.":["yonsei university","yonsei university health system"],
"kyungpook national univ.":["kyungpook national university"],
"chungang univ.":["chung ang university"],
"konkuk univ.":["konkuk university"],
"ewha univ.":["ewha university","ehwa woman university"],
"jeju univ.":["jeju national university"],
"labs mro":["labsmro"],
"labsmro":["labsmro"],
"sogang univ.":["sogang university"],
"aginglab":["aginglab"],
"bioto":["bioto"],
"inha univ.":["inha university"],
"daegu catholic univ.":["daegu catholic university"],
"keimyung univ.":["keimyung university"],
"chungbuk univ.":["chungbuk national university"],
"gyeongkuk univ.":["gyeongkuk national university"],
"eulji univ.":["eulji university"],
"soonchunhyang univ.":["soonchunhyang university","soonchunhyanguniversity"],
"sookmyung womens univ.":["sookmyung women's university"],
"sookmyung womens university":["sookmyung women's university"],
"gyeongsang national univ.":["gyeongsang national university"],
"gyeongsang univ.":["gyeongsang national university"],
"gnu":["gyeongsang national university"],
"kaist":["kaist"],
"incheon univ.":["incheon university"],
"dgist univ.":["dgist"],
"unist":["unist","ulsan national institute of science and technology"],
"unist univ.":["unist","ulsan national institute of science and technology"],
"kist":["kist"],
"gist":["gist"],
"kopri":["korea polar research institute"],
"kbiohealth":["kbiohealth"],
"kbri":["korea brain research institute"],
"rokit genomics":["rokit genomics"],
"rokit genoics":["rokit genomics"],
"aibiotics":["aibiotics"],
"medytox":["medytox"],
"decodecell":["decodecell"],
"geromics":["geromics"],
"yeungnam univ.":["yeungnam university"],
"kongju univ.":["kongju university"],
"hannam univ.":["hannamuniversity"],
"the province of chungcheongnamdo":["the province of chungcheongnam-do"],
}
def matching_account(account, institution):
    account=clean(account);institution=clean(institution)
    if account==institution:return True
    # Boundaries prevent 'unist' accidentally matching an unrelated long word.
    return any(re.search(r"(?<![a-z])"+re.escape(alias)+r"(?![a-z])",account)
               for alias in ALIASES.get(institution,[]))
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
            key=(clean(r.get("matched_opportunity_name")),str(r.get("matched_close_date") or ""))
            linked[key]+=1
    base=[x for x in h if x not in EXTRA]
    width=len(base)
    output=[base+EXTRA]
    summary={"customer_rows":0,"account_matches":0,"contract_links":0}
    for r in customer[1:]:
        data=dict(zip(h,r))
        inst=clean(data.get("institution"))
        account_keys={k for k in set(opbyaccount)|set(contactbyaccount) if matching_account(k,inst)}
        os=[item for k in account_keys for item in opbyaccount.get(k,[])]
        cs=[item for k in account_keys for item in contactbyaccount.get(k,[])]
        emailname=lambda c:clean((str(c.get("First Name") or "")+" "+str(c.get("Last Name") or "")).strip())
        mains=sum(1 for x in os for c in cs if emailname(c)==clean(x.get("Main Contact")) and emailname(c))
        projects=set(re.findall(r"AMEA\d+",str(data.get("project_ids") or ""),flags=re.I))
        project_upper={x.upper() for x in projects}
        contractset=[x for x in contracts if str(x.get("AMEA No.") or "").upper() in project_upper]
        contractnums=sorted({str(x.get("Contract No.") or "") for x in contractset if x.get("Contract No.")})
        def iso_date(v):
            from datetime import datetime
            for fmt in ("%m/%d/%Y","%Y-%m-%d","%m/%d/%y"):
                try:return datetime.strptime(str(v or ""),fmt).strftime("%Y-%m-%d")
                except ValueError:pass
            return str(v or "")
        quote_count=sum(linked[(clean(x.get("Opportunity Name")),iso_date(x.get("Close Date")))] for x in os)
        quality="AMEA_CONTRACT_CONFIRMED_ACCOUNT_EXACT" if contractset and os else "AMEA_CONTRACT_CONFIRMED" if contractset else "ACCOUNT_NAME_EXACT_ONLY" if os or cs else "NO_SFDC_EXACT_ACCOUNT_MATCH"
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
