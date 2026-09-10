from __future__ import annotations

from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))


def unwrap(payload):
    if isinstance(payload, dict) and 'result' in payload:
        return payload['result']
    return payload


async def us_fractional_order_window(client) -> tuple[bool, dict]:
    """Return whether US fractional/amount MARKET orders are currently accepted.

    Toss documents amount orders and fractional-quantity orders as available from
    regular-session open until one hour before regular-session close. Times in
    the market-calendar response are ISO 8601 values in KST.
    """
    calendar = unwrap(await client.market_calendar_us()) or {}
    now = datetime.now(KST)
    windows = []
    for key in ('previousBusinessDay', 'today', 'nextBusinessDay'):
        day = calendar.get(key) or {}
        regular = day.get('regularMarket') or {}
        start_text = regular.get('startTime')
        end_text = regular.get('endTime')
        if not start_text or not end_text:
            continue
        start = datetime.fromisoformat(start_text)
        regular_end = datetime.fromisoformat(end_text)
        fractional_end = regular_end - timedelta(hours=1)
        item = {
            'businessDate': day.get('date'),
            'startTime': start.isoformat(),
            'fractionalOrderEndTime': fractional_end.isoformat(),
            'regularEndTime': regular_end.isoformat(),
        }
        windows.append(item)
        if start <= now < fractional_end:
            return True, {'nowKst': now.isoformat(), 'activeWindow': item, 'windows': windows}
    return False, {'nowKst': now.isoformat(), 'activeWindow': None, 'windows': windows}
