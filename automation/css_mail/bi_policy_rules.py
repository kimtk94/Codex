"""Approved BI policy rules, free of credentials and external side effects.

Import from the scheduled BI reconciliation writer to keep future data refreshes
consistent with the user-approved October 2026 classifications.
"""
from collections import defaultdict

WGS_SUBTYPES = ("Human", "Microbial", "기타 (Plant/Animal)", "기타 (유형 확인 필요)")

def canonical_institution(name, aliases):
    """Normalize supplied institutions using audited, explicit mappings only."""
    if not name:
        return name
    visited = set()
    result = name
    while result in aliases:
        if result in visited:
            raise ValueError("Cyclic institution alias mapping")
        visited.add(result)
        result = aliases[result]
    return result

def wgs_subtype(group, original_l4):
    """Preserve WGS/WES at the top level, assigning a non-speculative subtype."""
    if group != "WGS/WES":
        return ""
    return {
        "Human WGS": "Human",
        "Microbial WGS": "Microbial",
        "Plant / Animal WGS": "기타 (Plant/Animal)",
    }.get(original_l4, "기타 (유형 확인 필요)")

def assert_wgs_reconciled(rows):
    """Fail closed when subtype and parent totals or counts differ."""
    subtotals = defaultdict(lambda: [0, 0])
    parent_count = 0
    parent_krw = 0
    for group, original_l4, amount_krw in rows:
        if group != "WGS/WES":
            continue
        amount = int(amount_krw)
        subtype = wgs_subtype(group, original_l4)
        subtotals[subtype][0] += 1
        subtotals[subtype][1] += amount
        parent_count += 1
        parent_krw += amount
    if sum(x[0] for x in subtotals.values()) != parent_count:
        raise ValueError("WGS subtype invoice count mismatch")
    if sum(x[1] for x in subtotals.values()) != parent_krw:
        raise ValueError("WGS subtype revenue mismatch")
    return dict(subtotals)
