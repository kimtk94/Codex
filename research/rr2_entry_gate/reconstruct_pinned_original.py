#!/usr/bin/env python3
"""Rebuild candidate dates with PINNED original Kalman US-five source, research only.

Import old model source unchanged, verify 5-symbol×2-model×2-year counts and
original EOD trade metrics, then (only if parity) use private dates to replay
COIN structure RR2. No dates or bars in public artifacts.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import subprocess
import sys
from pathlib import Path

PINNED_ORIGIN_SHA = "cccbb80059ab626da0cbd76cd825f879870f6727"
ORIGINAL_RUN_ID = 41217666574
EXPECTED_BAR_COUNT = 221014
EXPECTED_COUNTS = {
    "COIN": {2025: {"P_unweighted": 74, "V_unweighted": 80},
             2026: {"P_unweighted": 36, "V_unweighted": 46}},
    "IWM": {2025: {"P_unweighted": 72, "V_unweighted": 72},
            2026: {"P_unweighted": 33, "V_unweighted": 57}},
    "MU": {2025: {"P_unweighted": 33, "V_unweighted": 35},
           2026: {"P_unweighted": 188, "V_unweighted": 186}},
    "SMH": {2025: {"P_unweighted": 115, "V_unweighted": 112},
            2026: {"P_unweighted": 195, "V_unweighted": 155}},
    "SPY": {2025: {"P_unweighted": 154, "V_unweighted": 146},
            2026: {"P_unweighted": 167, "V_unweighted": 143}},
}
EXPECTED_EOD_V = {
    "COIN": {2025: -12.470582, 2026: 40.466772},
    "IWM": {2025: -2.726653, 2026: -5.499423},
    "MU": {2025: -18.769934, 2026: -23.502784},
    "SMH": {2025: -33.802180, 2026: -37.635900},
    "SPY": {2025: -29.428813, 2026: -33.343895},
}

def ensure_snapshot(snapshot:Path):
    result=subprocess.run(["git","-C",str(snapshot),"rev-parse","HEAD"],
                          text=True,capture_output=True,check=True)
    if result.stdout.strip()!=PINNED_ORIGIN_SHA:
        raise ValueError("ORIGINAL_SOURCE_COMMIT_NOT_PINNED")
    needed=[
      "research/kalman_integrated_regime/us_multisymbol_hold124.py",
      "research/kalman_integrated_regime/us_multisymbol_volume_trade_backtest.py",
      "research/kalman_integrated_regime/us_multisymbol_volume_screen.py",
      "research/kalman_integrated_regime/us_multisymbol_microstructure.py"
    ]
    if any(not (snapshot/p).is_file() for p in needed):
        raise ValueError("ORIGINAL_SOURCE_FILES_MISSING")
    return hashlib.sha256((snapshot/needed[0]).read_bytes()).hexdigest()

def check_signal_counts(panels, expected=EXPECTED_COUNTS):
    counts={}
    for ticker,years in expected.items():
        counts[ticker]={}
        for year,arms in years.items():
            panel=panels[(ticker,year)]
            if len(panel["dates"])!=208:
                raise ValueError("ORIGINAL_208_MATCHED_TEST_DAY_DRIFT")
            counts[ticker][year]={}
            for name,target in arms.items():
                n=int(panel["signals"][name].sum())
                counts[ticker][year][name]=n
                if n!=target:
                    raise ValueError(f"ORIGINAL_SIGNAL_PARITY_MISMATCH:{ticker}:{year}:{name}:{n}vs{target}")
    return counts

def generate_coins(panels,cal,*,source_sha=PINNED_ORIGIN_SHA):
    records=[]
    for year in (2025,2026):
        p=panels[("COIN",year)]
        for entry,decision in zip(p["dates"],p["signals"]["V_unweighted"]):
            if not bool(decision):
                continue
            entry_date=str(entry.date())
            signal_date=str(cal.previous_session(entry).date())
            records.append({
                "signal_id":f"RECON_{year}_{len(records):03d}",
                "signal_date":signal_date,
                "entry_date":entry_date,
                "symbol":"COIN","model":"V_unweighted",
                "available_after":"RTH_CLOSE",
                "source_run_id":f"RECON_FROM_ORIGINAL_{ORIGINAL_RUN_ID}_{source_sha[:12]}_{year}",
            })
    return records

def check_eod_original(original_report,expected=EXPECTED_EOD_V):
    rows={}
    for sym,annual in expected.items():
        rows[sym]={}
        for year,ret in annual.items():
            item=original_report["by_symbol"][sym][str(year)]["policies"]["NEXT_RTH_CLOSE"]["arms"]["V_unweighted"]
            measured=float(item["cumulative_return_pct"])
            rows[sym][year]={"cumulative_return_pct":measured,
                             "archive_expected_cumulative_return_pct":ret,
                             "within_1e_5_percentage_points":abs(measured-ret)<=.00001}
            if abs(measured-ret)>.00001:
                raise ValueError(f"ORIGINAL_RETURN_PARITY_MISMATCH:{sym}:{year}:{measured}vs{ret}")
    return rows

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--original-snapshot",required=True,type=Path)
    p.add_argument("--bars-parquet",required=True,type=Path)
    p.add_argument("--private-ledger-out",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    source_sha256=ensure_snapshot(a.original_snapshot)
    sys.path.insert(0,str(a.original_snapshot.resolve()))
    import pandas as pd
    import exchange_calendars as xcals
    from research.kalman_integrated_regime.us_multisymbol_hold124 import make_signal_panels
    from research.kalman_integrated_regime.us_multisymbol_volume_trade_backtest import run as original_run
    bars=pd.read_parquet(a.bars_parquet)
    if len(bars)!=EXPECTED_BAR_COUNT:
        raise ValueError("ORIGINAL_SOURCE_BARCOUNT_DRIFT:"+str(len(bars)))
    if set(bars.market.unique())!=set(EXPECTED_COUNTS):
        raise ValueError("UNEXPECTED_SOURCE_SYMBOLS")
    panels,_,qa=make_signal_panels(bars)
    counts=check_signal_counts(panels)
    eod=check_eod_original(original_run(bars))
    cal=xcals.get_calendar("XNYS")
    ledger=generate_coins(panels,cal)
    if (sum(r["entry_date"].startswith("2025") for r in ledger),
        sum(r["entry_date"].startswith("2026") for r in ledger))!=(80,46):
        raise ValueError("COIN_COHORT_DRIFT")
    a.private_ledger_out.parent.mkdir(parents=True,exist_ok=True)
    with a.private_ledger_out.open("w",newline="",encoding="utf8") as f:
        fields=("signal_id","signal_date","entry_date","symbol","model","available_after","source_run_id")
        writer=csv.DictWriter(f,fieldnames=fields)
        writer.writeheader();writer.writerows(ledger)
    # Imported AFTER pinned model source, but from this research branch.
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from coin_signal_replay import load_ledger, replay
    from coin_structure import build_sessions
    records,ledger_sha=load_ledger(a.private_ledger_out)
    coin=bars.loc[bars.market.eq("COIN")]
    coin_rows=[{"t":str(x.candle_time_utc),
                "o":float(x.open),"h":float(x.high),
                "l":float(x.low),"c":float(x.close)}
               for x in coin.itertuples(index=False)]
    sessions,quality=build_sessions(coin_rows,start="2024-01-01",end="2026-10-30")
    result=replay(sessions,quality,records,ledger_sha,source_sha=hashlib.sha256(
        a.bars_parquet.read_bytes()).hexdigest())
    result["provenance"]={
      "type":"RECONSTRUCTED_SOURCE_NOT_ORIGINAL_SAVED_SIGNAL_LEDGER",
      "original_success_run":ORIGINAL_RUN_ID,
      "original_commit":PINNED_ORIGIN_SHA,
      "original_hold124_source_sha256":source_sha256,
      "original_bar_count":len(bars),
      "full_universe_signal_count_parity":counts,
      "full_universe_EOD_return_parity":eod,
      "model_identities_verified_by_original_aggregate_metrics":True,
      "never_untouched_OOS":True,
      "can_promote_live":False,
    }
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(result,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps({
      "status":result["status"],"cohorts":result["signals_verified"],
      "verified_five_symbol_models":20,"result_rows":len(result["results"]),
      "source_bar_count":len(bars),"live":"HOLD"
    }))

if __name__=="__main__":main()
