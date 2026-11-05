#!/usr/bin/env python3
"""New Feishu Base: human review candidates for previously unmatched QQ emails.

Only unique evidence candidates are surfaced. No automatic customer/project
attribution, no mail forwarding or sending, no accounting/CRM writes.
Existing reviewer decisions and notes remain unchanged on every refresh.
"""
import collections
import datetime as dt
import json
import os
import re
import sys
import urllib.parse

from qq_mail_ingest import SafeError, api, auth, find_table, list_all, plain_field, SMOKE_KEY
from mail_identity_2026 import (
    build_index, decorate, load_references, EMAIL_RE, PROJECT_RE, H_RE, KST,
    normalize_account,
)
from mail_identity_gap_audit import PERSONAL_DOMAINS
from mail_classification_2026 import email_set, since_2026
from setup_sales_web import BASE_URL, EXPECTED_BASE, field_map, filter_matches, get_view, resolve_view

TABLE = "Mail Link Review 2026"
SCHEMA = (
    "Mail Key", "Received KST", "Feed Lane", "Direction", "Subject",
    "Candidate Basis", "Candidate Project", "Candidate Account",
    "Candidate Evidence", "Identity Status", "Review Status",
    "Review Note", "Last Sync KST",
)
VIEWS = (
    ("메일 추가연결 검토", None, None),
    ("본문 프로젝트 후보", "Candidate Basis", "BODY_PROJECT_UNIQUE"),
    ("도메인 기관 후보", "Candidate Basis", "DOMAIN_ACCOUNT_UNIQUE"),
    ("후보 충돌 확인", "Candidate Basis", "CANDIDATE_CONFLICT"),
)


def domains_by_account(index):
    lookup = collections.defaultdict(dict)
    for email_addr, rows in index["contacts"].items():
        domain = email_addr.rsplit("@", 1)[-1] if "@" in email_addr else ""
        if not domain or domain in PERSONAL_DOMAINS:
            continue
        for row in rows:
            account = (row.get("account") or "").strip()
            normal = normalize_account(account)
            if normal:
                lookup[domain][normal] = account
    return lookup


def suggestion(mail, relation, index, domains):
    # Only currently unlinked email can be a candidate. A message cannot be
    # reclassified as confirmed solely because a historic quote or domain agrees.
    if relation["Relationship Status"] != "UNMATCHED":
        return None
    subject = plain_field(mail.get("Subject")).upper()
    body = plain_field(mail.get("Body Excerpt")).upper()
    subject_tokens = set(PROJECT_RE.findall(subject)) | set(H_RE.findall(subject))
    body_tokens = set(PROJECT_RE.findall(body)) | set(H_RE.findall(body))
    projected = set()
    if not subject_tokens:
        for token in body_tokens:
            records = index["projects"].get(token, []) if token.startswith("AMEA") else index["h_ids"].get(token, [])
            for match in records:
                pid = str(match.get("project_id") or "").upper().strip()
                if pid:
                    projected.add(pid)
    body_candidate = next(iter(projected)) if len(projected)==1 else ""

    direction = plain_field(mail.get("Direction")).upper()
    from_addrs = email_set(plain_field(mail.get("From")))
    recipients = email_set(plain_field(mail.get("To"))) | email_set(plain_field(mail.get("CC")))
    correspondent = from_addrs if direction == "INBOUND" else recipients if direction == "OUTBOUND" else set()
    possible_accounts = {}
    for addr in correspondent:
        domain = addr.rsplit("@",1)[-1] if "@" in addr else ""
        matches = domains.get(domain, {})
        if len(matches) == 1:
            possible_accounts.update(matches)
    domain_candidate = next(iter(possible_accounts.values())) if len(possible_accounts) == 1 else ""
    if not body_candidate and not domain_candidate:
        return None
    project_institution = ""
    if body_candidate:
        rows = index["projects"].get(body_candidate, [])
        account_set = {str(row.get("institution") or "").strip() for row in rows if str(row.get("institution") or "").strip()}
        if len(account_set) == 1:
            project_institution = next(iter(account_set))
    conflict = bool(domain_candidate and project_institution and
                    normalize_account(domain_candidate) != normalize_account(project_institution))
    basis = ("CANDIDATE_CONFLICT" if conflict else
             "BODY_PROJECT_UNIQUE" if body_candidate else "DOMAIN_ACCOUNT_UNIQUE")
    return {
        "Mail Key": plain_field(mail.get("Mail Key")),
        "Received KST": relation["Received KST"],
        "Feed Lane": relation["Feed Lane"],
        "Direction": direction,
        "Subject": plain_field(mail.get("Subject"))[:500],
        "Candidate Basis": basis,
        "Candidate Project": body_candidate,
        "Candidate Account": domain_candidate or project_institution,
        "Candidate Evidence": (
            ("BODY_PROJECT_UNIQUE_NOT_VALIDATED " if body_candidate else "") +
            ("CONTACT_REFERENCE_DOMAIN_ONLY_NOT_PROOF " if domain_candidate else "") +
            ("ACCOUNT_CONFLICT " if conflict else "")
        ).strip(),
        "Identity Status": "UNMATCHED",
    }


def desired_records(records, reference_index, now):
    domain_map=domains_by_account(reference_index)
    keys = set()
    result = []
    for item in records:
        fields = {key: plain_field(val) for key,val in (item.get("fields") or {}).items()}
        key = fields.get("Mail Key","").strip()
        if key == SMOKE_KEY:
            continue
        if not key or key in keys:
            raise SafeError("REVIEW_DUPLICATE_OR_EMPTY_SOURCE_MAIL_KEY")
        keys.add(key)
        if not since_2026(fields.get("Received At")):
            continue
        rel=decorate(fields,reference_index,now)
        if rel is None:
            continue
        proposal=suggestion(fields,rel,reference_index,domain_map)
        if proposal:
            result.append(proposal)
    return result


def ensure_table(token, root):
    tables=list_all(root+"/tables",token,"review_tables")
    matches=[x for x in tables if x.get("name")==TABLE]
    if len(matches)>1:
        raise SafeError("REVIEW_DUPLICATE_TABLE")
    if not matches:
        api("POST",root+"/tables",token,data={"table":{
            "name":TABLE,"default_view_name":"All",
            "fields":[{"field_name":x,"type":1} for x in SCHEMA],
        }},action="review_create_table")
        matches=[x for x in list_all(root+"/tables",token,"review_table_recheck") if x.get("name")==TABLE]
    if len(matches)!=1:
        raise SafeError("REVIEW_TABLE_CREATE_NOT_VERIFIED")
    tid=matches[0]["table_id"]
    path=root+"/tables/"+urllib.parse.quote(tid,safe="")
    fields={r.get("field_name"):r.get("type") for r in list_all(path+"/fields",token,"review_fields")}
    if any(fields.get(x)!=1 for x in SCHEMA):
        raise SafeError("REVIEW_SCHEMA_INVALID")
    return tid,path


def ensure_views(token, tid, path):
    fields=field_map(token,path)
    for title, key, expected in VIEWS:
        vid,_=resolve_view(token,path,title,key is not None)
        view=get_view(token,path,vid)
        if key:
            fid=fields.get(key)
            if not fid:
                raise SafeError("REVIEW_VIEW_FIELD_NOT_FOUND")
            if not (view.get("view_name")==title and filter_matches(view,fid,expected)):
                api("PATCH",path+"/views/"+urllib.parse.quote(vid,safe=""),token,
                    data={"view_name":title,"property":{"filter_info":{
                        "conjunction":"and","conditions":[{"field_id":fid,"operator":"is",
                          "value":json.dumps([expected])}]
                    }}},action="review_filter")
                view=get_view(token,path,vid)
                if not (view.get("view_name")==title and filter_matches(view,fid,expected)):
                    raise SafeError("REVIEW_VIEW_FILTER_READBACK_FAILED")
        elif view.get("view_name")!=title:
            raise SafeError("REVIEW_VIEW_READBACK_FAILED")
        print("REVIEW_VIEW_READY="+title+" URL="+BASE_URL+"?table="+tid+"&view="+vid)


def same(existing,fields):
    return all(plain_field(existing.get(k)).strip()==str(val).strip()
               for k,val in fields.items())


def upsert(token,path,wanted,limit=250):
    previous=list_all(path+"/records",token,"review_existing")
    by_key={}
    for record in previous:
        key=plain_field((record.get("fields") or {}).get("Mail Key")).strip()
        if not key:
            continue
        if key in by_key:
            raise SafeError("REVIEW_DUPLICATE_TARGET_KEY")
        by_key[key]=record
    changes=[]
    creates=[]
    unchanged=0
    for row in wanted:
        key=row["Mail Key"]
        prior=by_key.get(key)
        if prior and same(prior.get("fields") or {},row):
            unchanged+=1
            continue
        if len(creates)+len(changes)>=limit:
            continue
        data={**row,"Last Sync KST":dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M KST")}
        if prior:
            # DO NOT overwrite Review Status or Review Note user-edited fields.
            changes.append({"record_id":prior["record_id"],"fields":data})
        else:
            creates.append({"fields":{**data,"Review Status":"PENDING","Review Note":""}})
    for endpoint, records in (("batch_create",creates),("batch_update",changes)):
        for i in range(0,len(records),25):
            batch=records[i:i+25]
            response=api("POST",path+"/records/"+endpoint,token,
                         data={"records":batch},action="review_"+endpoint)
            returned=response.get("records") or []
            if len(returned)!=len(batch) or any(not x.get("record_id") for x in returned):
                raise SafeError("REVIEW_WRITE_UNCONFIRMED")
    if creates or changes:
        check=list_all(path+"/records",token,"review_verify")
        indexed={}
        for record in check:
            k=plain_field((record.get("fields") or {}).get("Mail Key")).strip()
            if k in indexed:
                raise SafeError("REVIEW_DUPLICATE_KEY_AFTER_UPSERT")
            indexed[k]=record.get("fields") or {}
        for record in creates+changes:
            values=record["fields"]
            key=values["Mail Key"]
            if key not in indexed or not same(indexed[key],values):
                raise SafeError("REVIEW_READBACK_MISMATCH")
    return len(creates),len(changes),unchanged


def main():
    if os.getenv("FEISHU_BASE_APP_TOKEN")!=EXPECTED_BASE:
        raise SafeError("REVIEW_REFUSE_OTHER_BASE")
    mode=os.getenv("FEISHU_REVIEW_MODE","plan")
    if mode not in ("plan","apply"):
        raise SafeError("REVIEW_BAD_MODE")
    token,root=auth()
    tid=find_table(token,root)
    if not tid:
        raise SafeError("REVIEW_SOURCE_MAIL_MISSING")
    raw=list_all(root+"/tables/"+urllib.parse.quote(tid,safe="")+"/records",token,"review_original_mail")
    refs=build_index(load_references())
    now=dt.datetime.now(KST)
    wanted=desired_records(raw,refs,now)
    counter=collections.Counter(x["Candidate Basis"] for x in wanted)
    print("REVIEW_CANDIDATE_PLAN total="+str(len(wanted))+
          " body_unique="+str(counter["BODY_PROJECT_UNIQUE"])+
          " domain_unique="+str(counter["DOMAIN_ACCOUNT_UNIQUE"])+
          " conflicts="+str(counter["CANDIDATE_CONFLICT"]))
    if mode=="plan":
        print("REVIEW_PLAN_PASS writes=0")
        return
    tid,path=ensure_table(token,root)
    ensure_views(token,tid,path)
    creates,updates,unchanged=upsert(token,path,wanted)
    print("REVIEW_APPLY_PASS created="+str(creates)+" updated="+str(updates)+
          " unchanged="+str(unchanged)+" source_mail_writes=0"+
          " original_accounts_writes=0 user_notes_preserved=true")


if __name__=="__main__":
    try:main()
    except Exception as error:
        msg=str(error) if isinstance(error,SafeError) else type(error).__name__
        print("REVIEW_FAILED:"+msg,file=sys.stderr)
        sys.exit(1)
