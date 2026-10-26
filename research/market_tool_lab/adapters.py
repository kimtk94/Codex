"""Adapters for existing Kalman CSV schemas. No trading or network access."""
import argparse
import csv
from datetime import date, datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

FIELDS = ["timestamp", "symbol", "open", "high", "low", "close", "volume"]


def convert(source, dest, schema, symbol=None):
    source, dest = Path(source), Path(dest)
    if source.resolve() == dest.resolve():
        raise ValueError("output must differ from input")
    count = 0
    with source.open(newline="", encoding="utf-8-sig") as handle, dest.open("w", newline="", encoding="utf-8") as output:
        rd=csv.DictReader(handle)
        wr=csv.DictWriter(output, fieldnames=FIELDS)
        wr.writeheader()
        for row in rd:
            if schema == "alignment":
                # Date-only daily bars are normalized to official US cash-session close.
                # This is a label, not a guarantee of data publication at that instant.
                d=date.fromisoformat(row["date_ny"])
                ts=datetime.combine(d,time(16),ZoneInfo("America/New_York")).astimezone(timezone.utc)
                symbols=("QQQ","QLD") if symbol is None else (symbol.upper(),)
                for sym in symbols:
                    if sym not in ("QQQ","QLD"):
                        raise ValueError("alignment symbol must be QQQ or QLD")
                    wr.writerow({"timestamp":ts.isoformat(),"symbol":sym,**{k:row[f"{k}_{sym.lower()}"] for k in ("open","high","low","close","volume")}})
                    count += 1
            elif schema == "etf_bars":
                sym=row["market"].upper()
                if symbol and sym != symbol.upper():
                    continue
                ts=datetime.fromisoformat(row["candle_time_utc"].replace("Z","+00:00"))
                if ts.tzinfo is None:
                    raise ValueError("candle_time_utc must be timezone aware")
                wr.writerow({"timestamp":ts.astimezone(timezone.utc).isoformat(),"symbol":sym,**{k:row[k] for k in ("open","high","low","close","volume")}})
                count += 1
            else:
                raise ValueError("unknown schema")
    return count


if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--input",required=True)
    ap.add_argument("--output",required=True)
    ap.add_argument("--schema",choices=("alignment","etf_bars"),required=True)
    ap.add_argument("--symbol")
    args=ap.parse_args()
    print({"rows_written":convert(args.input,args.output,args.schema,args.symbol),"output":args.output})
