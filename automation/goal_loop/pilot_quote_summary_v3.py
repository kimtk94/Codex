"""HAND-AUTHORED NONPRODUCTION CI FIXTURE. Never merge or count as AI-generated."""


def summarize_quotes(rows):
    if not isinstance(rows, list):
        raise ValueError("rows must be a list")
    seen = set()
    totals = {}
    accepted = 0
    rejected = 0
    for row in rows:
        if not isinstance(row, dict):
            rejected += 1
            continue
        quote_id = row.get("quote_id")
        product = row.get("product_line")
        count = row.get("sample_count")
        price = row.get("unit_price_krw")
        if (not isinstance(quote_id, str) or not quote_id.strip()
                or not isinstance(product, str) or not product.strip()
                or type(count) is not int or count < 1
                or type(price) is not int or price < 0):
            rejected += 1
            continue
        normalized_id = quote_id.strip()
        if normalized_id in seen:
            rejected += 1
            continue
        seen.add(normalized_id)
        key = product.strip().upper()
        totals[key] = totals.get(key, 0) + count * price
        accepted += 1
    return {
        "totals_krw": dict(sorted(totals.items())),
        "accepted": accepted,
        "rejected": rejected,
    }
