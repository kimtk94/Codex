"""Read-only CSS mail -> statement ledger reconciliation plan.

This module deliberately returns a plan, not writes. A separate approved publisher
may apply it after checking manual decisions and native row identities.
"""
from css_statement_parser import unique_observations

HEADERS = [
    "AMEA", "H Contract", "X Sub-project", "SAM Batch",
    "Statement Event KST", "Statement Amount KRW", "Statement State",
    "Invoice Number", "Invoice Amount KRW", "Invoice Issued Date",
    "Attribution State", "Revenue Treatment", "Evidence Source", "Next Check",
]


def plan_statement_updates(mails, existing_rows):
    """Produce immutable append candidates; leave previously reviewed rows unchanged.

    Cannot attribute a Statement to a SAM merely because the same AMEA has
    one or more SAM records. Never turn a statement into an invoice or revenue.
    """
    existing_uids = set()
    for row in existing_rows:
        source = str(row.get("Evidence Source") or "")
        for token in source.split(";"):
            token = token.strip()
            if token.startswith("MAIL_UID="):
                existing_uids.add(token.split("=", 1)[1])
    proposed, deferred = [], []
    for obs in unique_observations(mails):
        uid = obs["mail_uid"]
        if uid in existing_uids:
            continue
        if len(obs["amea"]) != 1 or len(obs["contracts"]) != 1 or len(obs["subprojects"]) != 1:
            deferred.append({"uid": uid, "reason": "AMBIGUOUS_IDENTIFIERS"})
            continue
        if obs["statement_total"] is None or obs["statement_currency"] != "KRW":
            deferred.append({"uid": uid, "reason": "UNVERIFIED_AMOUNT"})
            continue
        proposed.append({
            "AMEA": obs["amea"][0],
            "H Contract": obs["contracts"][0],
            "X Sub-project": obs["subprojects"][0],
            "SAM Batch": "",  # strict no inferred batch attribution
            "Statement Event KST": "",
            "Statement Amount KRW": obs["statement_total"],
            "Statement State": "STATEMENT_READY_UNCONFIRMED",
            "Invoice Number": "",
            "Invoice Amount KRW": "",
            "Invoice Issued Date": "",
            "Attribution State": "UNATTRIBUTED_STATEMENT",
            "Revenue Treatment": "NO_REVENUE_ADDITION",
            "Evidence Source": "MAIL_UID=" + uid,
            "Next Check": "Verify batch/stage and independent TAX INVOICE",
        })
    return {"proposed": proposed, "deferred": deferred,
            "operational_writes": 0, "decision_changes": 0}


def load_mail_rows(matrix):
    if not matrix:
        raise ValueError("Missing CSS Mail Inbox Raw header")
    headers = [str(x).strip() for x in matrix[0]]
    required = {"Mail UID", "Subject", "Body Text"}
    if not required.issubset(headers):
        raise ValueError("Missing source columns: " + ", ".join(sorted(required - set(headers))))
    return [dict(zip(headers, row)) for row in matrix[1:]]
