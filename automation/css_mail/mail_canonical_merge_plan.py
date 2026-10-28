#!/usr/bin/env python3
"""Pure, no-write planning for a lossless canonical mail migration.

Source tuple = (legacy rows, staging rows). Never dedupe on Message-ID alone:
the same Message-ID may be copied across folders or refer to divergent records.
"""
from collections import Counter
from email.utils import getaddresses
import re

CANONICAL_COLUMNS=[
    "canonical_key","source_table","source_row","legacy_uid","imap_folder",
    "imap_uid","uidvalidity","message_id","received_at","from_name",
    "from_email","to","cc","reply_to","subject","attachments",
    "attachment_count","amea_numbers","h_project_numbers","sam_numbers",
    "direction","fetched_at_utc","in_reply_to","references","migration_state",
]

def get(row,index):
    return str(row[index]).strip() if len(row)>index and row[index] is not None else ""

def email_key(value):
    return ",".join(sorted(set(addr.strip().lower() for _,addr in getaddresses([value]) if addr)))

def normalize_id(value):
    return value.strip().lower()

def legacy_key(row,rownum):
    # Legacy IMAP UID lacks UIDVALIDITY. Preserve source identity even for
    # repeated IDs rather than fabricating a safe IMAP checkpoint.
    return "legacy:All Emails:"+str(rownum)

def staging_key(row):
    return "imap:"+get(row,0)

def message_fingerprint(row,legacy):
    if legacy:
        return (normalize_id(get(row,1)),get(row,2),email_key(get(row,4)),email_key(get(row,5)),get(row,8))
    return (normalize_id(get(row,1)),get(row,5),email_key(get(row,6)),email_key(get(row,7)),get(row,9))

def plan(legacy_rows,staging_rows):
    if legacy_rows[0][:3]!=["uid","message_id","received_at"]:
        raise ValueError("LEGACY_SCHEMA_CHANGED")
    if staging_rows[0][:5]!=["ingest_key","message_id","imap_uid","folder","uidvalidity"]:
        raise ValueError("STAGING_SCHEMA_CHANGED")
    legacy=[(i,r) for i,r in enumerate(legacy_rows[1:],start=2) if get(r,0)]
    staging=[(i,r) for i,r in enumerate(staging_rows[1:],start=2) if get(r,0)]
    seen_keys=set()
    for _,r in staging:
        k=staging_key(r)
        if k in seen_keys:raise ValueError("DUPLICATE_STAGING_KEY")
        seen_keys.add(k)
        if not re.fullmatch(r"imap:[^|]+\|[0-9]+\|[0-9]+",k):
            raise ValueError("INVALID_IMAP_KEY")
    staging_fp=Counter(message_fingerprint(r,False) for _,r in staging)
    overlap=0
    collision=0
    legacy_with_attachment=0
    for i,r in legacy:
        if get(r,9):legacy_with_attachment+=1
        fp=message_fingerprint(r,True)
        if all(fp) and staging_fp[fp]:
            overlap+=1
            staging_fp[fp]-=1
        elif get(r,1) and any(normalize_id(get(r,1))==normalize_id(get(s,1)) for _,s in []):
            collision+=1
    # Never drop existing rows automatically. Emit a merge *plan* for manual gate.
    return {
        "legacy_rows":len(legacy),"staging_rows":len(staging),
        "legacy_with_attachment":legacy_with_attachment,
        "strict_same_message_candidates":overlap,
        "retained_legacy_records":len(legacy),
        "retained_staging_records":len(staging),
        "canonical_staging_rows_before_dedupe":len(legacy)+len(staging),
        "automatic_deletion_allowed":False,
        "cutover_allowed":False,
    }
