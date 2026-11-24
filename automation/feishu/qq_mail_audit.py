#!/usr/bin/env python3
"""Read-only post-ingest audit for the NEW Feishu sales Base.

Only aggregate counts go to public Actions logs. Never exports mail content.
"""
import collections
import re
import sys
import urllib.parse

import qq_mail_ingest as q

# This business catalog is informational for mail-only operations: the mail
# staging Base can be healthy even if unrelated business tables are absent.
# The independent Base schema check still reports an explicit BLOCK.
EXPECTED_BUSINESS_TABLES = frozenset({
    "Accounts", "Contacts", "Opportunities", "Quotes", "Projects", "Revenue",
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


def catalog_status(tables):
    """Report unrelated business-table readiness without masking mail integrity."""
    names = collections.Counter(row.get("name") for row in tables)
    missing = sum(names[name] == 0 for name in EXPECTED_BUSINESS_TABLES)
    duplicate = sum(names[name] > 1 for name in EXPECTED_BUSINESS_TABLES)
    return ("PASS" if not (missing or duplicate) else "BLOCK", missing, duplicate)


def main():
    token, root = q.auth()
    tables = q.list_all(root + "/tables", token, "audit_tables")

    # The QQ Mail Intake table is the *only* required table for the mail
    # ledger. A missing or duplicate staging table always fails closed.
    mail_tables = [row for row in tables if row.get("name") == q.TABLE]
    if len(mail_tables) != 1 or not mail_tables[0].get("table_id"):
        raise q.SafeError(
            "AUDIT_STAGING_TABLE_MISSING" if not mail_tables
            else "AUDIT_STAGING_TABLE_DUPLICATE_OR_ID_MISSING"
        )

    table_id = mail_tables[0]["table_id"]
    table_path = root + "/tables/" + urllib.parse.quote(table_id, safe="")
    fields = q.get_fields(token, table_path)
    field_counts = collections.Counter(field.get("field_name") for field in fields)
    field_types = {field.get("field_name"): field.get("type") for field in fields}
    if any(field_counts[name] != 1 or field_types[name] != 1 for name in q.FIELDS):
        raise q.SafeError("AUDIT_STAGING_FIELD_SCHEMA_MISMATCH")

    records = q.list_all(table_path + "/records", token, "audit_records")
    metrics = summarize(records)  # Duplicate/malformed mail keys fail closed.

    for name, value in metrics.items():
        print("FEISHU_MAIL_AUDIT_" + name.upper() + "=" + str(value))
    print("MAIL_SINK_READBACK_PASS records=" + str(metrics["mail_total"]) +
          " smoke=" + str(metrics["smoke"]) + " duplicate_keys=0 writes=0")

    status, missing, duplicated = catalog_status(tables)
    print("BASE_SCHEMA_" + status + " missing_required=" + str(missing) +
          " duplicated_required=" + str(duplicated) + " mail_only=0")
    if status == "BLOCK":
        # GitHub Actions will surface a warning while allowing successful
        # *mail* backfills to be reported independently from business tables.
        print("::warning title=Feishu Business Catalog::BASE_SCHEMA_BLOCK "
              "missing_required=" + str(missing) +
              " duplicated_required=" + str(duplicated))
    print("FEISHU_MAIL_AUDIT_PASS mail_only=1 business_catalog=" + status +
          " customer_payload_logs=0 writes=0")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        reason = str(exc) if isinstance(exc, q.SafeError) else type(exc).__name__
        print("FEISHU_MAIL_AUDIT_FAILED:" + reason, file=sys.stderr)
        sys.exit(1)
