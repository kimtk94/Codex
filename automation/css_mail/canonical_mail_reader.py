#!/usr/bin/env python3
"""Canonical Mail Ledger adapter preserving CSS Git Ingest column contract.

Only staging source records are selected. Legacy rows must not be counted twice.
Read-only; fail closed if canonical header or source parity is invalid.
"""
import urllib.parse
import incremental_sync as src

TAB="Canonical Mail Ledger"
HEAD=["canonical_key","source_table","source_row","legacy_uid","imap_folder","imap_uid","uidvalidity","message_id","received_at","from_name","from_email","recipient_to","cc","reply_to","subject","attachments","attachment_count","amea_numbers","h_project_numbers","sam_numbers","direction","fetched_at_utc","in_reply_to","references","migration_state","owner_verification","invoice_numbers"]

def read_staging_compatible(session):
    path=urllib.parse.quote("'"+TAB+"'!A1:AA60000",safe="")
    rows=src.api(session,"GET",src.endpoint("/values/"+path)).get("values",[])
    if not rows or rows[0]!=HEAD:
        raise RuntimeError("CANONICAL_SCHEMA_MISMATCH")
    output=[]
    seen=set()
    for row in rows[1:]:
        if len(row)<2 or row[1]!="CSS Git Ingest":continue
        def val(i):
            return str(row[i]) if i<len(row) and row[i] is not None else ""
        canonical=val(0)
        if not canonical.startswith("imap:"):
            raise RuntimeError("CANONICAL_STAGING_KEY_INVALID")
        key=canonical[5:]
        if key in seen:raise RuntimeError("CANONICAL_STAGING_DUPLICATE")
        seen.add(key)
        output.append([key,val(7),val(5),val(4),val(6),val(8),val(10),val(11),
                       val(12),val(14),val(17),val(18),val(19),"",val(21),
                       val(20),val(22),val(23)])
    return [src.COLS]+output
