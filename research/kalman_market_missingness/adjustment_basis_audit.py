"""Read-only same-provider raw/adjusted basis diagnostic; never infer issuer proof."""
from __future__ import annotations

import argparse
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd
from backfill_queue import validated_archives, frame_dates, PRICE_KEYS, PAIRED_SHARED, sha

from bond_cash_factor_evidence import audit_cash_events

VERSION = "kalman-adjustment-basis-audit-v2"
# Numerical diagnostic tolerances, not market price certification tolerances.
COMMON_FACTOR_TOL_BP = 0.1
STEP_TOL_BP = 0.1


def require(ok, code):
    if not ok:
        raise ValueError("BASIS_" + code)


def compare_frames(old, new, key):
    frames = []
    for frame in (old, new):
        dates = frame_dates(frame, key)
        flags = frame["is_adjusted"]
        require(flags.notna().all() and all(isinstance(v, (bool, np.bool_)) for v in flags)
                and flags.nunique() == 1, "FLAG_INVALID")
        view = frame.copy()
        view.index = dates.tolist()
        frames.append(view)
    a, b = frames
    shared = sorted(set(a.index) & set(b.index))[-46:]
    require(len(shared) >= 12, "OVERLAP_INSUFFICIENT")
    x = a.loc[shared, list(PRICE_KEYS)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    y = b.loc[shared, list(PRICE_KEYS)].apply(pd.to_numeric, errors="coerce").to_numpy(float)
    good = np.isfinite(x).all(axis=1) & np.isfinite(y).all(axis=1) & (x > 0).all(axis=1) & (y > 0).all(axis=1)
    factor = np.full_like(x, np.nan)
    factor[good] = y[good] / x[good]
    good &= np.isfinite(factor).all(axis=1) & (factor > 0).all(axis=1)
    common = np.zeros(len(shared), dtype=bool)
    common[good] = (factor[good].max(axis=1) / factor[good].min(axis=1) - 1) * 10000 <= COMMON_FACTOR_TOL_BP
    changed = np.zeros(len(shared), dtype=bool)
    changed[good] = (np.abs(factor[good]-1) > 1e-9).any(axis=1)
    steps = []
    for i in range(1, len(shared)):
        # Adjacent overlap observations only; these dates are clues, not ex-dates.
        if common[i-1] and common[i]:
            delta = (factor[i, 3] / factor[i-1, 3] - 1) * 10000
            if abs(delta) > STEP_TOL_BP:
                steps.append({"previous_observed_date": shared[i-1],
                              "next_observed_date": shared[i],
                              "absolute_factor_step_bp": round(abs(float(delta)), 6)})
    old_flag, new_flag = bool(a["is_adjusted"].iloc[0]), bool(b["is_adjusted"].iloc[0])
    if not good.all():
        status = "INVALID_OVERLAP_HOLD"
    elif not common.all():
        status = "NONUNIFORM_OHLC_DIFFERENCE_HOLD"
    elif old_flag != new_flag:
        status = ("MULTIPLICATIVE_PATTERN_UNCERTIFIED_HOLD" if changed.any()
                  else "EQUAL_VALUES_DIFFERENT_BASIS_HOLD")
    elif changed.any():
        status = "SAME_FLAG_REVISED_VALUES_HOLD"
    else:
        status = "SAME_FLAG_EQUAL_OVERLAP_UNCERTIFIED_HOLD"
    return {
        "asset": key, "source_adjusted": old_flag, "reference_adjusted": new_flag,
        "overlap_sessions": len(shared), "invalid_sessions": int((~good).sum()),
        "uniform_factor_sessions": int(common.sum()),
        "nonuniform_valid_sessions": int((good & ~common).sum()),
        "changed_sessions": int(changed.sum()), "factor_step_candidates": steps,
        "status": status, "issuer_factor_verified": False,
        "official_close_verified": False, "pit_approved": False,
        "approved_backfill_rows": 0,
    }


def build_report(macro_blob, daily_blob):
    mzip, dzip, _, ready, daily, a, b = validated_archives(macro_blob, daily_blob)
    with mzip, dzip:
        rows, cash_events = [], []
        for key in sorted(PAIRED_SHARED):
            old = pd.read_parquet(BytesIO(mzip.read(a[key])))
            new = pd.read_parquet(BytesIO(dzip.read(b[key])))
            rows.append(compare_frames(old, new, key))
            cash_events.extend(audit_cash_events(old, new, key,
                                daily["data_expected_last_closed_xnys"]))
    return {"version": VERSION, "status": "RESEARCH_HOLD",
            "source_sha256": sha(macro_blob), "reference_sha256": sha(daily_blob),
            "source_session": ready["expected_last_completed_nyse_session"],
            "reference_session": daily["data_expected_last_closed_xnys"],
            "common_factor_tolerance_bp": COMMON_FACTOR_TOL_BP,
            "factor_step_tolerance_bp": STEP_TOL_BP,
            "research_only": True, "production_writes": False, "live_execution": False,
            "strategy_promoted": False, "approved_backfill_rows": 0,
            "assets": rows, "cash_event_hypotheses": cash_events}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--market-zip", required=True)
    p.add_argument("--daily20-zip", required=True)
    p.add_argument("--out", required=True)
    args = p.parse_args()
    report = build_report(Path(args.market_zip).read_bytes(), Path(args.daily20_zip).read_bytes())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "adjustment_basis_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("KALMAN_ADJUSTMENT_BASIS_HOLD", json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
