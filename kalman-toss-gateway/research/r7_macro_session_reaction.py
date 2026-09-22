#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import timedelta, timezone
from pathlib import Path

import pandas as pd

UTC=timezone.utc

DEFAULT_EVENTS="/opt/kalman/state/r7_macro_free/events.json"
DEFAULT_QQQ="/mnt/gdrive/US_ETF/directional_research/canonical_history_v1/qqq_context/history_1h/QQQ_1h_gap_aware.parquet"
DEFAULT_OUT="/opt/kalman/state/r7_macro_reaction"

REQUIRED_QQQ_COLS={
    "candle_time_utc","open","close","session_date","session_bucket",
    "expected_seq","bar_time_aligned","data_gap_before"
}

def _ts(x):
    return pd.Timestamp(x).tz_convert("UTC") if pd.Timestamp(x).tzinfo else pd.Timestamp(x, tz="UTC")

def load_qqq(path: Path) -> pd.DataFrame:
    df=pd.read_parquet(path)
    missing=sorted(REQUIRED_QQQ_COLS-set(df.columns))
    if missing:
        raise RuntimeError(f"QQQ parquet missing required columns: {missing}")
    df=df.copy()
    df["candle_time_utc"]=pd.to_datetime(df["candle_time_utc"],utc=True)
    df=df.sort_values(["candle_time_utc","expected_seq"]).reset_index(drop=True)
    # Canonical contract requires aligned, non-gap bars. Keep only fully valid 60m rows.
    valid=df["bar_time_aligned"].fillna(False).astype(bool) & ~df["data_gap_before"].fillna(True).astype(bool)
    df=df.loc[valid].copy()
    df["bar_end_utc"]=df["candle_time_utc"]+pd.Timedelta(hours=1)
    return df

def build_reaction(events: list[dict], qqq: pd.DataFrame, max_anchor_delay_hours: float=6.0):
    rows=[]
    qqq_by_seq={int(r.expected_seq):r for r in qqq.itertuples() if pd.notna(r.expected_seq)}
    start=qqq["candle_time_utc"].min()
    end=qqq["bar_end_utc"].max()

    eligible_denominator=0
    covered=0

    for e in events:
        release=pd.to_datetime(e.get("release_at"),utc=True,errors="coerce")
        if pd.isna(release):
            continue

        family=str(e.get("family") or "")
        actual_ok=bool(e.get("pit_actual_eligible"))
        # FOMC has no BLS actual; its event timestamp itself is the PIT input.
        event_input_ok=actual_ok or family=="FOMC"

        row={
            "family":family,
            "event_name":e.get("event_name"),
            "release_at":release.isoformat(),
            "actual_input_eligible":actual_ok,
            "event_input_eligible":event_input_ok,
            "reaction_contract":"QQQ_SESSION_REACTION_1H",
            "reaction_quality":None,
            "reaction_available":False,
            "reaction_available_at":None,
            "first_full_bar_start":None,
            "anchor_delay_minutes":None,
            "qqq_open":None,
            "qqq_close_1h":None,
            "qqq_reaction_1h_open_to_close":None,
            "qqq_reaction_1h_prev_close_to_close":None,
            "qqq_reaction_2h_open_to_close":None,
            "first_expected_seq":None,
            "blocker":None,
        }

        if not event_input_ok:
            row["blocker"]="EVENT_INPUT_NOT_PIT_ELIGIBLE"
            rows.append(row)
            continue

        # Only score releases that fall within the canonical QQQ history window.
        if release < start or release > end:
            row["blocker"]="OUTSIDE_QQQ_HISTORY"
            rows.append(row)
            continue

        eligible_denominator += 1

        candidates=qqq.loc[qqq["candle_time_utc"]>=release]
        if candidates.empty:
            row["blocker"]="NO_POST_EVENT_FULL_BAR"
            rows.append(row)
            continue

        first=candidates.iloc[0]
        delay=(first["candle_time_utc"]-release).total_seconds()/60.0
        if delay < 0 or delay > max_anchor_delay_hours*60.0:
            row["blocker"]="POST_EVENT_BAR_DELAY_TOO_LARGE"
            rows.append(row)
            continue

        seq=int(first["expected_seq"])
        o=float(first["open"])
        c1=float(first["close"])
        available_at=first["bar_end_utc"]

        row.update({
            "reaction_quality":"NEXT_FULL_60M_AFTER_EVENT",
            "reaction_available":True,
            "reaction_available_at":available_at.isoformat(),
            "first_full_bar_start":first["candle_time_utc"].isoformat(),
            "anchor_delay_minutes":delay,
            "qqq_open":o,
            "qqq_close_1h":c1,
            "qqq_reaction_1h_open_to_close":(c1/o)-1.0 if o else None,
            "first_expected_seq":seq,
        })

        prev=qqq_by_seq.get(seq-1)
        if prev is not None and float(prev.close)!=0:
            row["qqq_reaction_1h_prev_close_to_close"]=(c1/float(prev.close))-1.0

        nxt=qqq_by_seq.get(seq+1)
        if nxt is not None and str(nxt.session_date)==str(first["session_date"]):
            # Never bridge a missing bucket or an overnight session boundary.
            c2=float(nxt.close)
            if o:
                row["qqq_reaction_2h_open_to_close"]=(c2/o)-1.0

        covered += 1
        rows.append(row)

    coverage=(covered/eligible_denominator) if eligible_denominator else 0.0
    per_family={}
    for family in sorted({str(r.get("family") or "") for r in rows}):
        xs=[r for r in rows if str(r.get("family") or "")==family]
        elig=[r for r in xs if r.get("event_input_eligible") and r.get("blocker")!="OUTSIDE_QQQ_HISTORY"]
        # denominator is restricted to events that actually fall in the QQQ history window
        elig=[r for r in elig if r.get("blocker")!="OUTSIDE_QQQ_HISTORY"]
        cov=[r for r in elig if r.get("reaction_available")]
        per_family[family]={
            "eligible_events":len(elig),
            "covered_events":len(cov),
            "coverage_ratio":(len(cov)/len(elig)) if elig else None,
        }
    return rows,{
        "eligible_events_in_qqq_history":eligible_denominator,
        "reaction_covered_events":covered,
        "reaction_coverage_ratio":coverage,
        "per_family_reaction_coverage":per_family,
        "session_reaction_ready":coverage>=0.80,
    }

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--events",default=DEFAULT_EVENTS)
    ap.add_argument("--qqq",default=DEFAULT_QQQ)
    ap.add_argument("--output-dir",default=DEFAULT_OUT)
    ap.add_argument("--max-anchor-delay-hours",type=float,default=6.0)
    args=ap.parse_args()

    events=json.loads(Path(args.events).read_text(encoding="utf-8"))
    qqq=load_qqq(Path(args.qqq))
    rows,stats=build_reaction(events,qqq,args.max_anchor_delay_hours)

    out=Path(args.output_dir)
    out.mkdir(parents=True,exist_ok=True)
    (out/"session_reactions.json").write_text(json.dumps(rows,indent=2)+"\n",encoding="utf-8")

    manifest={
        "schema":"kalman-r7-macro-session-reaction-v1",
        "research_only":True,
        "production_changed":False,
        "reaction_contract":"QQQ_SESSION_REACTION_1H",
        "not_us2y_intraday":True,
        "straddle_bar_used":False,
        "feature_available_at_rule":"first_full_bar_start + 60 minutes",
        "max_anchor_delay_hours":args.max_anchor_delay_hours,
        "qqq_source":str(args.qqq),
        "qqq_first_bar":qqq["candle_time_utc"].min().isoformat(),
        "qqq_last_bar_end":qqq["bar_end_utc"].max().isoformat(),
        **stats,
        "model_fitting_allowed":False,
        "blockers":[
            "CONSENSUS_UNAVAILABLE_FOR_SURPRISE_CHALLENGER",
            "R7_REACTION_REQUIRES_REVIEW_BEFORE_MODEL_FITTING"
        ] if stats["session_reaction_ready"] else [
            "SESSION_REACTION_COVERAGE_BELOW_80PCT",
            "CONSENSUS_UNAVAILABLE_FOR_SURPRISE_CHALLENGER",
            "R7_REACTION_REQUIRES_REVIEW_BEFORE_MODEL_FITTING"
        ],
    }
    (out/"manifest.json").write_text(json.dumps(manifest,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(manifest,indent=2))
    print("REACTIONS_FILE=",out/"session_reactions.json")
    print("MANIFEST=",out/"manifest.json")

if __name__=="__main__":
    main()
