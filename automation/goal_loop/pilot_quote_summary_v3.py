"""Nonproduction synthetic quotation summary pilot. No external data or writes."""


def summarize_quotes(rows):
    """Return VAT-exclusive KRW totals for synthetic quote rows."""
    return {"totals_krw": {}, "accepted": 0, "rejected": 0}
