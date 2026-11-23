def summarize_quotes(rows):
    """Return VAT-exclusive KRW totals for synthetic quote rows."""
    if not isinstance(rows, list):
        raise ValueError('Input must be a list of dictionaries.')

    totals_krw = {}
    accepted = 0
    rejected = 0

    seen_quote_ids = set()

    for row in rows:
        if not isinstance(row, dict) or 'quote_id' not in row or 'product_line' not in row or 'sample_count' not in row or 'unit_price_krw' not in row:
            rejected += 1
            continue

        quote_id = row['quote_id'].strip()
        product_line = row['product_line'].strip().upper()
        sample_count = row['sample_count']
        unit_price_krw = row['unit_price_krw']

        if not isinstance(quote_id, str) or not isinstance(product_line, str) or not isinstance(sample_count, int) or not isinstance(unit_price_krw, int) or sample_count < 1 or unit_price_krw < 0:
            rejected += 1
            continue

        if quote_id in seen_quote_ids:
            rejected += 1
            continue

        seen_quote_ids.add(quote_id)

        if product_line not in totals_krw:
            totals_krw[product_line] = 0

        totals_krw[product_line] += sample_count * unit_price_krw

    return {'totals_krw': {k: v for k, v in sorted(totals_krw.items())}, 'accepted': accepted, 'rejected': rejected}