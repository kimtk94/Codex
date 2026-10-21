#!/usr/bin/env python3
"""Read-only SFDC Opportunity to CSS project bridge by exact AMEA identifiers."""
import json
import re
from collections import defaultdict
from followup_stage1 import auth, OUTPUT_ID
from opportunity_quote_mirror import range_data, replace_tab, ensure_tabs
from followup_stage1 import call

KEY=re.compile(r"AMEA20[0-9]{8}",re.I)
TAB="SFDC CSS Project Bridge"
SUMMARY="SFDC CSS Match Audit"
HEAD=["match_status","amea_id","opportunity_name","account","stage","amount","css_status","contract_number","sif_number","css_institution","match_basis"]
def keys(v):
    return set(k.upper() for k in KEY.findall(str(v or "")))
def main():
    session=auth()
    # Read full source snapshots; never mutate the source.
    opp=range_data(session,OUTPUT_ID,"Opportunity",2000)
    css=range_data(session,OUTPUT_ID,"CSS Contract-SIF",2000)
    if len(opp)<2 or len(css)<2: raise RuntimeError("Source snapshot missing; bridge not written")
    oh={str(v).strip():i for i,v in enumerate(opp[0])}
    ch={str(v).strip():i for i,v in enumerate(css[0])}
    for name in ["Opportunity Name","Stage","Amount","Account Name"]:
        if name not in oh: raise RuntimeError("Missing Opportunity column: "+name)
    for name in ["AMEA No.","Status","Contract No.","SIF No.","Institution"]:
        if name not in ch: raise RuntimeError("Missing CSS column: "+name)
    def value(row, pos): return row[pos] if pos<len(row) else ""
    indexed=defaultdict(list)
    for row in css[1:]:
        for key in keys(value(row,ch["AMEA No."])):
            indexed[key].append(row)
    out=[HEAD]
    stats=defaultdict(int)
    for row in opp[1:]:
        name=value(row,oh["Opportunity Name"])
        found=keys(name)
        base=[name,value(row,oh["Account Name"]),value(row,oh["Stage"]),value(row,oh["Amount"])]
        if len(found)!=1:
            status="NO_AMEA" if not found else "MULTIPLE_AMEA"
            out.append([status,", ".join(sorted(found)),*base,"","","","","NO_SAFE_KEY"])
            stats[status]+=1
            continue
        key=next(iter(found)); hits=indexed.get(key,[])
        if len(hits)!=1:
            status="UNMATCHED" if not hits else "AMBIGUOUS_CSS"
            out.append([status,key,*base,"","","","","EXACT_AMEA_ONLY"])
            stats[status]+=1
            continue
        match=hits[0]
        out.append(["MATCHED",key,*base,
                    value(match,ch["Status"]),value(match,ch["Contract No."]),
                    value(match,ch["SIF No."]),value(match,ch["Institution"]),"EXACT_AMEA_ONLY"])
        stats["MATCHED"]+=1
    root="https://sheets.googleapis.com/v4/spreadsheets/"+OUTPUT_ID
    meta=call(session,"GET",root+"?fields=sheets.properties",stage="bridge_metadata")
    existing={s["properties"]["title"] for s in meta["sheets"]}
    req=[{"addSheet":{"properties":{"title":title}}} for title in [TAB,SUMMARY] if title not in existing]
    if req: call(session,"POST",root+":batchUpdate",json={"requests":req},stage="bridge_tabs")
    replace_tab(session,TAB,out)
    replace_tab(session,SUMMARY,[["metric","count"],["total_opportunity",len(opp)-1]]+[[k,stats[k]] for k in ["MATCHED","NO_AMEA","MULTIPLE_AMEA","UNMATCHED","AMBIGUOUS_CSS"]])
    print(json.dumps({"status":"ok","total_opportunity":len(opp)-1,"match_counts":dict(stats)},ensure_ascii=False))
if __name__=="__main__":
    try: main()
    except Exception as exc:
        print("SFDC bridge failure: "+str(exc) if isinstance(exc,RuntimeError) else "SFDC bridge unexpected failure")
        raise
