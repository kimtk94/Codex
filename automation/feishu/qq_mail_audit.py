#!/usr/bin/env python3
"""Read-only post-ingest audit for the NEW Feishu sales Base.

Only aggregate counts go to public Actions logs. Never exports mail content.
"""
import collections
import re
import sys
import urllib.parse

import qq_mail_ingest as q

EXPECTED_TABLES = frozenset({
    "QQ Mail Intake", "Accounts", "Contacts", "Opportunities",
    "Quotes", "Projects", "Revenue",
})


def summarize(records):
    counts = collections.Counter()
    keys = set()
    smoke = 0
    for record in records:
        fields = record.get("fields") or {}
        rid = record.get("record_id")
        key = q.plain_field(fields.get("Mail Key")).strip()
        if not rid or not key:
            raise q.SafeError("AUDIT_MISSING_RECORD_ID_OR_MAIL_KEY")
        if key in keys:
            raise q.SafeError("AUDIT_DUPLICATE_MAIL_KEY")
        keys.add(key)
        if key == q.SMOKE_KEY:
            smoke += 1
            continue
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise q.SafeError("AUDIT_UNEXPECTED_MAIL_KEY_FORMAT")
        direction = q.plain_field(fields.get("Direction")).strip()
        if direction not in ("INBOUND", "OUTBOUND"):
            raise q.SafeError("AUDIT_UNKNOWN_MAIL_DIRECTION")
        counts[direction] += 1
        if q.plain_field(fields.get("Message ID")).strip():
            counts["WITH_MESSAGE_ID"] += 1
        if q.plain_field(fields.get("Body Excerpt")).strip():
            counts["WITH_BODY_EXCERPT"] += 1
        if q.plain_field(fields.get("AMEA")).strip():
            counts["WITH_AMEA"] += 1
        if q.plain_field(fields.get("H Project")).strip():
            counts["WITH_H_PROJECT"] += 1
    return {
        "mail_total": counts["INBOUND"] + counts["OUTBOUND"],
        "inbound": counts["INBOUND"], "outbound": counts["OUTBOUND"],
        "smoke": smoke, "message_ids": counts["WITH_MESSAGE_ID"],
        "body_excerpts": counts["WITH_BODY_EXCERPT"],
        "amea": counts["WITH_AMEA"], "h_project": counts["WITH_H_PROJECT"],
        "duplicate": 0,
    }


def main():
    token, root = q.auth()
    tables = q.list_all(root + "/tables", token, "audit_tables")
    names = [r.get("name") for r in tables]
    if any(names.count(name) != 1 for name in EXPECTED_TABLES):
        raise q.SafeError("SALES_BASE_REQUIRED_TABLES_MISSING_OR_DUPLICATED")
    table_id = q.find_table(token, root)
    if not table_id:
        raise q.SafeError("QQ_MAIL_INTAKE_NOT_FOUND")
    table_path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
    field_types = {f.get("field_name"): f.get("type") for f in q.get_fields(token, table_path)}
    if any(field_types.get(field) != 1 for field in q.FIELDS):
        raise q.SafeError("AUDIT_STAGING_FIELD_SCHEMA_MISMATCH")
    records = q.list_all(table_path + "/records", token, "audit_records")
    metrics = summarize(records)
    # Stable machine-readable aggregate output; never log records, IDs, messages or tokens.
    for name, value in metrics.items():
        print("FEISHU_MAIL_AUDIT_" + name.upper() + "=" + str(value))
    print("FEISHU_MAIL_AUDIT_PASS expected_tables=7 customer_payload_logs=0 writes=0")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, q.SafeError) else type(exc).__name__
        print("FEISHU_MAIL_AUDIT_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
