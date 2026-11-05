#!/usr/bin/env python3
"""Strict, local-only Korean contact alias export for the draft web UI.

Input is independently authenticated Contact Details evidence, NOT historical
Opportunity/Quote names. A display label alone never verifies Contact identity.
No Salesforce writes, GitHub uploads, external calls, or customer PII in logs.
"""
import argparse
import json
import re
import unicodedata
from pathlib import Path

from contact_oppo_selection import (
    ID_ACCOUNT, ID_CONTACT, ID_OPPORTUNITY, excluded_account
)

HANGUL_LABEL = re.compile(r"^([\uac00-\ud7a3]{2,6})(?:\s+[A-Za-z][A-Za-z .'-]{1,80})?$")
EMAIL = re.compile(r"^[^@\s]{1,64}@[^@\s]{1,190}$")
REQUIRED_FLAGS = (
    "contact_detail_id_verified", "contact_account_link_verified",
    "opportunity_contact_link_verified", "contact_email_verified",
    "contact_display_name_verified",
)


def korean_name_from_contact_label(label):
    if not isinstance(label, str):
        return None
    label=unicodedata.normalize("NFKC",label).strip()
    label=re.sub(r"\s+"," ",label)
    match=HANGUL_LABEL.fullmatch(label)
    return match.group(1) if match else None


def verified_private_aliases(rows):
    if not isinstance(rows,list):
        raise ValueError("EVIDENCE_ROWS_MUST_BE_LIST")
    if len(rows)>10000:
        raise ValueError("TOO_MANY_EVIDENCE_ROWS")
    eligible={}
    rejected=0
    conflicts=set()
    for item in rows:
        if not isinstance(item,dict) or not all(item.get(flag) is True for flag in REQUIRED_FLAGS):
            rejected+=1
            continue
        name=korean_name_from_contact_label(item.get("display_name"))
        cid=item.get("contact_id")
        aid=item.get("account_id")
        institution=item.get("institution")
        email=item.get("contact_email")
        opps=item.get("opportunity_ids")
        if (not name or not isinstance(cid,str) or not ID_CONTACT.fullmatch(cid)
                or not isinstance(aid,str) or not ID_ACCOUNT.fullmatch(aid)
                or not isinstance(institution,str) or not institution.strip()
                or excluded_account(institution) or not isinstance(email,str)
                or not EMAIL.fullmatch(email) or not isinstance(opps,list) or not opps
                or len(opps)>1000 or not all(isinstance(opp,str) and ID_OPPORTUNITY.fullmatch(opp) for opp in opps)):
            rejected+=1
            continue
        key=(cid,aid)
        record={"name":name,"institution":institution.strip(),"contact_id":cid,
                "account_id":aid,"contact_email":email,
                "opportunity_ids":sorted(set(opps))}
        if key in eligible and eligible[key] != record:
            conflicts.add(key)
        else:
            eligible[key]=record
    for key in conflicts:
        eligible.pop(key,None)
    records=sorted(eligible.values(),key=lambda r:(r["name"],r["institution"],r["contact_id"]))
    return {"records":records,"source_rows":len(rows),"rejected_rows":rejected,
            "conflicting_identity_keys":len(conflicts),"save_allowed":False}


def main():
    p=argparse.ArgumentParser()
    home=Path.home()/".sfdc_desktop"
    p.add_argument("--source",default=str(home/"private_verified_contact_details_evidence.json"))
    p.add_argument("--output",default=str(home/"web_contact_aliases_PRIVATE.json"))
    a=p.parse_args()
    source=Path(a.source).resolve()
    target=Path(a.output).resolve()
    private_root=home.resolve()
    if private_root not in source.parents or private_root not in target.parents:
        p.error("Input/output must remain in the private workstation .sfdc_desktop directory")
    if not source.is_file() or source.stat().st_size>5_000_000:
        p.error("Private verified Contact evidence file missing or too large")
    result=verified_private_aliases(json.loads(source.read_text(encoding="utf-8-sig")))
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result["records"],ensure_ascii=False,indent=2),encoding="utf-8")
    # stdout only aggregate counts; names, emails, institutions and IDs stay local.
    print(json.dumps({k:v for k,v in result.items() if k!="records"},
                     ensure_ascii=False,sort_keys=True))
    print("LOCAL_WEB_CANDIDATES",len(result["records"]))


if __name__=="__main__":
    main()
