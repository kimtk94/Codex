"""Reference long-only fixed triple barrier for *daily* OHLCV, offline.

Entry at close of signal day i; first eligible barrier observation is i+1.
Horizon = up to 4 following daily bars. If both barriers touch same bar,
pessimistic stop-first convention. No live execution, portfolio or forecasts.
"""
def triple_barrier(ohlc, signal_idx, take_profit=0.03, stop_loss=0.03, horizon=4):
    if not (0 < take_profit and 0 < stop_loss and horizon >= 1):
        raise ValueError("invalid barrier parameters")
    if signal_idx < 0 or signal_idx >= len(ohlc)-1:
        raise ValueError("signal needs future bars")
    entry=float(ohlc[signal_idx]["close"])
    if entry<=0: raise ValueError("entry must be positive")
    tp=entry*(1+take_profit)
    sl=entry*(1-stop_loss)
    final_idx=min(len(ohlc)-1,signal_idx+horizon)
    for i in range(signal_idx+1, final_idx+1):
        high=float(ohlc[i]["high"]);low=float(ohlc[i]["low"])
        if low<=sl:  # Includes simultaneous TP+SL ambiguity: worst-case.
            exit_price=sl;reason="SL"
        elif high>=tp:
            exit_price=tp;reason="TP"
        elif i == final_idx:
            exit_price=float(ohlc[i]["close"]);reason="TIME" if i==signal_idx+horizon else "DATA_END"
        else:
            continue
        return {"entry_idx":signal_idx,"exit_idx":i,"entry":entry,"exit":exit_price,
                "gross_return":exit_price/entry-1,"reason":reason,
                "simultaneous_barrier":low<=sl and high>=tp}
    raise AssertionError("unreachable")
