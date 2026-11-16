"""Fail-closed *local* selection of not-yet-attempted 2026 approved SFDC Quotes.

This module has NO Salesforce, filesystem or network access and cannot read prices.
GitHub Actions should run only synthetic tests. The caller must keep real Quote IDs,
Account/Contact details, approval rows and original KRW amounts on its private PC.
"""
from collections import Counter, defaultdict
from datetime import date
import re

QID = re.compile(r"^QID-(2026-\d{2}-\d{2})-\d{4,}$")


def _date_and_qid(row):
    if not isinstance(row, dict):
        raise ValueError("QUOTE_REFERENCE_INVALID")
    qid = row.get("quote_id")
    day = row.get("created_date")
    if not isinstance(qid, str) or not isinstance(day, str):
        raise ValueError("QUOTE_DATE_OR_ID_MISSING")
    match = QID.fullmatch(qid)
    try:
        parsed = date.fromisoformat(day)
    except ValueError:
        raise ValueError("QUOTE_DATE_INVALID") from None
    if not match or match.group(1) != day or parsed.year != 2026:
        raise ValueError("QUOTE_ID_DATE_MISMATCH")
    return qid, day


def select_unattempted_2026(eligible_rows, attempted_batches, verified_quote_ids,
                            per_month=6):
    """Select per-month unattempted single-Product approved references.

    Attempted means *ever sent to the browser*, including retryable HOLDS, not
    just successfully indexed Quotes. Prior repeated manifests are counted once.
    Reject duplicate eligible references instead of silently deduplicating them.
    """
    if not isinstance(eligible_rows, list) or len(eligible_rows) > 5000:
        raise ValueError("ELIGIBLE_SCOPE_INVALID")
    if not isinstance(attempted_batches, list) or len(attempted_batches) > 200:
        raise ValueError("ATTEMPTED_SCOPE_INVALID")
    if not isinstance(verified_quote_ids, (set, frozenset)):
        raise ValueError("VERIFIED_SET_INVALID")
    if isinstance(per_month, bool) or not isinstance(per_month, int) or not 1 <= per_month <= 10:
        raise ValueError("PER_MONTH_INVALID")
    eligible = {}
    for row in eligible_rows:
        qid, day = _date_and_qid(row)
        if qid in eligible:
            raise ValueError("DUPLICATE_ELIGIBLE_QID")
        if row.get("approval_evidence") != "APPROVED_TEXT":
            raise ValueError("UNAPPROVED_REFERENCE_IN_ELIGIBLE_SCOPE")
        eligible[qid] = row
    previous = Counter()
    for batch in attempted_batches:
        if not isinstance(batch, list) or len(batch) > 50:
            raise ValueError("ATTEMPTED_BATCH_INVALID")
        for row in batch:
            qid, _ = _date_and_qid(row)
            if qid not in eligible:
                raise ValueError("ATTEMPTED_QID_OUTSIDE_ELIGIBLE_SCOPE")
            previous[qid] += 1
    if not all(isinstance(q, str) for q in verified_quote_ids):
        raise ValueError("VERIFIED_QID_INVALID")
    covered = set(previous)
    confirmed = covered.intersection(verified_quote_ids)
    by_month = defaultdict(list)
    for qid, row in eligible.items():
        if qid in covered or qid in verified_quote_ids:
            continue
        by_month[row["created_date"][:7]].append(row)
    selected = []
    for month in sorted(by_month):
        selected.extend(sorted(by_month[month],
                               key=lambda x: (x["created_date"], x["quote_id"]))[:per_month])
    identities = [x["quote_id"] for x in selected]
    if len(identities) != len(set(identities)) or set(identities).intersection(covered):
        raise ValueError("DUPLICATE_OR_RETRIED_SELECTION")
    return {
        "status": "PASS",
        "selected": selected,
        "eligible_unique": len(eligible),
        "attempted_rows": sum(previous.values()),
        "attempted_unique": len(covered),
        "duplicate_attempt_rows": sum(v-1 for v in previous.values()),
        "verified_among_attempted": len(confirmed),
        "held_among_attempted": len(covered-confirmed),
        "remaining_before": len(eligible)-len(covered.union(verified_quote_ids.intersection(eligible))),
        "selected_count": len(selected),
        "selected_by_month": dict(sorted(Counter(x["created_date"][:7] for x in selected).items())),
        "crm_writes": 0,
        "price_auto_apply": False,
    }
