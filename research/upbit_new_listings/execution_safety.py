"""Conservative order-fill and candle-integrity primitives (research only).

OHLC candles cannot reveal the high/low sequence inside one bar.
Stops are evaluated before targets if both are reached.
"""
from datetime import datetime, timedelta, timezone

def validate_candles(bars, interval_minutes=15):
    issues=[]
    prev=None
    for i,b in enumerate(bars):
        t=b["t"]
        if t.tzinfo is None:
            issues.append((i,"naive_timestamp"))
        if prev is not None:
            delta=(t-prev).total_seconds()
            if delta<=0:issues.append((i,"duplicate_or_unsorted"))
            elif delta!=interval_minutes*60:issues.append((i,"missing_or_irregular_candle"))
        prev=t
        if min(b["o"],b["c"])<b["l"] or max(b["o"],b["c"])>b["h"] or b["l"]>b["h"]:
            issues.append((i,"invalid_ohlc"))
    return issues

def first_utc_day(candle_timestamp):
    return candle_timestamp.astimezone(timezone.utc).date()

def conservative_exit(bar, stop, target, sell_slippage=0.0015):
    """Return (fill, reason) or (None,None); gap-open outranks stop/target."""
    op,low,high=bar["o"],bar["l"],bar["h"]
    if op<=stop:
        return op*(1-sell_slippage),"gap_stop"
    if op>=target:
        return target*(1-sell_slippage),"take"
    if low<=stop:
        return stop*(1-sell_slippage),"stop"
    if high>=target:
        return target*(1-sell_slippage),"take"
    return None,None

def trailing_exit(bars, entry_idx, initial_stop_pct=.03, trail_pct=.10,
                  take_pct=None, buy_slippage=.0015, sell_slippage=.0015, fee=.0005):
    """No forward-looking stop updates. Entry at next bar's open, then walk bars.
    Bar's high updates trailing stop only for following bar.
    """
    entry=bars[entry_idx]["o"]*(1+buy_slippage)
    stop=entry*(1-initial_stop_pct)
    target=entry*(1+take_pct) if take_pct is not None else float("inf")
    peak=entry
    for i in range(entry_idx,len(bars)):
        fill,reason=conservative_exit(bars[i],stop,target,sell_slippage)
        if fill is not None:
            net=100*(fill*(1-fee)/(entry*(1+fee))-1)
            return {"net_pct":net,"exit_idx":i,"reason":reason,"fill":fill}
        peak=max(peak,bars[i]["h"])
        if trail_pct is not None:
            stop=max(stop,peak*(1-trail_pct))
    fill=bars[-1]["c"]*(1-sell_slippage)
    net=100*(fill*(1-fee)/(entry*(1+fee))-1)
    return {"net_pct":net,"exit_idx":len(bars)-1,"reason":"time","fill":fill}
