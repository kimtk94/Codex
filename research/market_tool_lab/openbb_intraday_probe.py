"""Read-only OpenBB V5 intraday capability probe. No live trading or credentials."""
import json,os
from datetime import datetime,timezone
from pathlib import Path

OUT=Path(os.environ.get("INTRADAY_PROBE_OUTPUT","artifacts/market-tool-lab/openbb-intraday"))
OUT.mkdir(parents=True,exist_ok=True)
SYMBOLS=("QQQ","QLD")
INTERVALS=("1m","15m","1h")
summary={"observed_at_utc":datetime.now(timezone.utc).isoformat(),"provider":"cboe","checks":[]}
try:
    from openbb import obb
    for symbol in SYMBOLS:
        for interval in INTERVALS:
            row={"symbol":symbol,"interval":interval}
            try:
                result=obb.cboe.equity.historical(symbol=symbol,interval=interval,provider="cboe",use_cache=False)
                df=result.to_dataframe()
                row["rows"]=len(df)
                row["unique_timestamps"]=int(df.index.nunique())
                row["duplicate_timestamps"]=int(len(df)-df.index.nunique())
                row["status"]=("DUPLICATED_TIMESTAMPS" if row["duplicate_timestamps"] else "DATA") if len(df) else "EMPTY"
                row["columns"]=list(map(str,df.columns))
                if len(df):
                    dates=df.index.astype(str)
                    row["first_observed"]=str(dates.min())
                    row["last_observed"]=str(dates.max())
                    df.to_csv(OUT/f"{symbol}_{interval}.csv")
                    if row["duplicate_timestamps"]:
                        # Keep raw audit CSV; never silently select a duplicate OHLC bar.
                        row["bar_quality"]="BLOCKED_FOR_BACKTEST_UNTIL_DUPLICATES_RECONCILED"
            except Exception as exc:
                row["status"]="UNSUPPORTED_OR_FAILED"
                row["error_type"]=type(exc).__name__
                row["error_summary"]=str(exc)[:240]
            summary["checks"].append(row)
except Exception as exc:
    summary["setup_error"]={"type":type(exc).__name__,"summary":str(exc)[:240]}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2,ensure_ascii=False))
print(json.dumps(summary,ensure_ascii=False))
if "setup_error" in summary or not any(x["status"] in ("DATA","DUPLICATED_TIMESTAMPS") for x in summary["checks"]):
    raise SystemExit(1)
