#!/usr/bin/env python3
"""Research-only *joint* execution-policy search for QLD 15-minute SIP data.

Every row evaluates a complete, interacting execution policy, NOT a sum of
single-option effects. Seeded mixed-level sampling is exploratory and no row
may be promoted to LIVE based on 2025/2026 in-sample policy search.
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, asdict
from itertools import combinations
import json
from pathlib import Path
import hashlib

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.kalman_integrated_regime import run as base

# All dimensions are adjustable; full Cartesian space is intentionally not
# enumerated. Values are plausible search bounds, NOT validated live rules.
AXES = {
    "tp": [0.015, 0.02, 0.025, 0.03, 0.04, 0.05, 0.06],
    "sl": [0.01, 0.015, 0.02, 0.025, 0.03, 0.04],
    "hold": [1, 2, 3, 4, 5, 6],
    "entry_delay": [0, 1, 2, 4],
    "size": [0.25, 0.5, 0.75, 1.0],
    "risk_budget": [0.0, 0.005, 0.01, 0.02],
    "split": ["single", "equal", "front", "back"],
    "add_dip": [0.0, 0.0075, 0.015, 0.03],
    "add_deadline": [4, 8, 26, 52],
    "partial_tp": [0.0, 0.25, 0.5, 0.75],
    "partial_at_r": [0.5, 0.75, 1.0],
    "trail": [0.0, 0.0125, 0.02, 0.03],
    "trail_start_r": [0.5, 1.0, 1.5],
    "breakeven_r": [0.0, 0.75, 1.0, 1.5],
    "be_offset_bps": [0, 10, 20],
    "cooldown": [0, 1, 2, 4],
    "vix_min": [0.0, 12.0, 15.0, 18.0],
    "vix_max": [20.0, 25.0, 35.0, 99.0],
    "trend": ["none", "r5", "r20", "both"],
    "qld_r5_gate": ["none", "positive", "negative"],
    "vol_cap": [0.0, 0.02, 0.03, 0.04],
    "confidence": [0.45, 0.5, 0.55, 0.6, 0.65],
    "slippage_bps": [0, 5, 10, 20],
    "max_month": [0, 2, 4, 8],
    "gap_cap": [0.0, 0.01, 0.02, 0.04],
}
# Default replicates original fixed-barrier strategy where compatible. Actual
# historical baseline is independently computed in base.run.
BASELINE = {
    "tp": .03, "sl": .03, "hold": 4, "entry_delay": 0,
    "size": 1.0, "risk_budget": 0., "split": "single",
    "add_dip": 0., "add_deadline": 4,
    "partial_tp": 0., "partial_at_r": 1.,
    "trail": 0., "trail_start_r": 1., "breakeven_r": 0.,
    "be_offset_bps": 0, "cooldown": 0,
    "vix_min": 0., "vix_max": 99., "trend": "none",
    "qld_r5_gate": "none", "vol_cap": 0.,
    "confidence": .5, "slippage_bps": 0, "max_month": 0,
    "gap_cap": 0.,
}
assert set(BASELINE) == set(AXES)
FEE = base.FEE


def normalize(p):
    q = dict(p)
    if q["split"] == "single":
        q["add_dip"] = 0.
        q["add_deadline"] = 4
    if q["partial_tp"] == 0.:
        q["partial_at_r"] = 1.
    if q["trail"] == 0.:
        q["trail_start_r"] = 1.
    if q["breakeven_r"] == 0.:
        q["be_offset_bps"] = 0
    if q["risk_budget"] == 0.:
        q["risk_budget"] = 0.
    return q


def policy_id(p):
    canonical = json.dumps(p, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def policy_valid(p):
    return bool(p["vix_min"] < p["vix_max"] and
                p["sl"] > 0 and p["tp"] > 0 and
                p["size"] > 0 and p["size"] <= 1 and
                p["hold"] >= 1)


def generate_policies(n, seed=20261031):
    """Deterministically sample *joint* mixed-level policies and report coverage.

    Baseline included as first policy; n-1 policies vary many axes jointly.
    No outcome feedback is used in candidate generation.
    """
    if n < 2:
        raise ValueError("NEED_MULTIPLE_JOINT_CONFIGS")
    rng = np.random.default_rng(seed)
    keys = tuple(AXES)
    policies = [normalize(BASELINE)]
    seen = {policy_id(policies[0])}
    # Sample first independently across all axes; avoid one-knob experiments.
    # Add mirrored levels to improve coverage of rare combinations.
    attempts = 0
    while len(policies) < n and attempts < n * 100:
        attempts += 1
        p = {k: AXES[k][int(rng.integers(0, len(AXES[k])))] for k in keys}
        p = normalize(p)
        if not policy_valid(p):
            continue
        if sum(p[k] != BASELINE[k] for k in keys) < 5:
            continue
        uid = policy_id(p)
        if uid in seen:
            continue
        seen.add(uid)
        policies.append(p)
    if len(policies) != n:
        raise RuntimeError("FAILED_TO_GENERATE_REQUIRED_POLICIES")
    return policies


def pairwise_coverage(policies):
    """Report observed two-factor value-pairs against the advertised full grid."""
    observed, possible = 0, 0
    for a, b in combinations(AXES, 2):
        pairs = {(p[a], p[b]) for p in policies}
        possible += len(AXES[a]) * len(AXES[b])
        observed += len(pairs)
    return {"covered": observed, "possible": possible,
            "fraction": round(observed / possible, 6) if possible else None,
            "not_full_factorial": True}


def allow_signal(p, f, probability):
    if probability < p["confidence"]:
        return False
    vix = float(f["vix_lag1"])
    if not (p["vix_min"] <= vix <= p["vix_max"]):
        return False
    if p["trend"] in ("r5", "both") and f["qqq_r5"] <= 0:
        return False
    if p["trend"] in ("r20", "both") and f["qqq_r20"] <= 0:
        return False
    if p["qld_r5_gate"] == "positive" and f["qld_r5"] <= 0:
        return False
    if p["qld_r5_gate"] == "negative" and f["qld_r5"] >= 0:
        return False
    if p["vol_cap"] > 0 and f["qqq_vol20"] > p["vol_cap"]:
        return False
    return True


@dataclass
class Fill:
    """Cash-account trading record, per one unit of starting portfolio equity."""
    signal_date: pd.Timestamp
    entry_date: pd.Timestamp
    exit_date: pd.Timestamp
    net_pnl: float
    fills_buy: int
    fills_sell: int
    holding_sessions: int
    exited_by: str
    equity_marks: dict


def simulate_trade(p, future_sessions, start_slot, signal_day, previous_close):
    """Single-position cash ledger with explicit split entry/exit & 15m precedence.

    Stop is anchored to initial entry, never loosened after averaging down.
    Any stop/TP collision in same OHLC bar assumes stop first. A trailing stop
    is activated only at the NEXT candle after the observed high.
    """
    if not future_sessions:
        return None
    entry_day, opening = future_sessions[0]
    if start_slot >= len(opening):
        return None
    px0 = float(opening.iloc[start_slot].open)
    if p["gap_cap"] and px0 > previous_close * (1 + p["gap_cap"]):
        return None
    alloc = float(p["size"])
    if p["risk_budget"] > 0.:
        alloc = min(alloc, float(p["risk_budget"]) / float(p["sl"]))
    if alloc <= 0:
        return None
    if p["split"] == "single":
        first, second = 1., 0.
    elif p["split"] == "equal":
        first, second = .5, .5
    elif p["split"] == "front":
        first, second = .7, .3
    else:
        first, second = .3, .7
    slip = p["slippage_bps"] / 10000.
    fee_buy = 1 + FEE + slip
    fee_sell = 1 - FEE - slip
    if fee_sell <= 0:
        raise ValueError("INVALID_FEE")
    first_shares = alloc * first / (px0 * fee_buy)
    shares = first_shares
    spent = alloc * first
    proceeds = 0.
    buy_fills = 1
    sell_fills = 0
    add_done = second == 0.
    partial_done = False
    static_stop = px0 * (1 - p["sl"])
    working_stop = static_stop
    high_water = px0
    anchor_cost = px0
    elapsed = 0
    exit_date = None
    exit_reason = ""
    marks = {}
    max_days = min(p["hold"], len(future_sessions))
    for day_i, (day, frame) in enumerate(future_sessions[:max_days]):
        last_close = float(frame.iloc[-1].close)
        for bar_i, b in enumerate(frame.itertuples(index=False)):
            if day_i == 0 and bar_i < start_slot:
                continue
            o, h, lo, cl = float(b.open), float(b.high), float(b.low), float(b.close)
            # Intrabar stop is checked before upside events (pessimistic).
            if o <= working_stop or lo <= working_stop:
                exit_px = o if o <= working_stop else working_stop
                proceeds += shares * exit_px * fee_sell
                shares = 0.
                sell_fills += 1
                exit_reason = "SL_OR_TRAIL"
            else:
                # Optional take-profit scale-out at R multiple of initial risk.
                partial_px = anchor_cost + p["partial_at_r"] * (px0 * p["sl"])
                full_tp = anchor_cost * (1 + p["tp"])
                partial_this_bar = False
                if not partial_done and p["partial_tp"] > 0 and h >= partial_px:
                    fraction = float(p["partial_tp"])
                    sold = shares * fraction
                    # Opening gap past threshold executes at open.
                    proceeds += sold * max(o, partial_px) * fee_sell
                    shares -= sold
                    sell_fills += 1
                    partial_done = True
                    partial_this_bar = True
                if h >= full_tp and shares > 0:
                    proceeds += shares * max(o, full_tp) * fee_sell
                    shares = 0.
                    sell_fills += 1
                    exit_reason = "TP"
                if shares > 0:
                    # Add is processed only when neither stop nor final TP fired.
                    # Same-bar add then new stop/TP path cannot be recovered from
                    # OHLC. A new stop becomes effective NEXT BAR only.
                    just_added = False
                    if (not add_done and not partial_this_bar and elapsed <= p["add_deadline"] and
                        lo <= px0 * (1 - p["add_dip"])):
                        fill_px = min(o, px0 * (1 - p["add_dip"]))
                        extra = alloc * second / (fill_px * fee_buy)
                        spent += alloc * second
                        shares += extra
                        buy_fills += 1
                        add_done = True
                        just_added = True
                        # Cost basis for TP changes but hard stop stays anchored.
                        anchor_cost = (alloc * first + alloc * second) / (first_shares + extra) / fee_buy
                    # High watermark and BE only update after current bar check,
                    # preventing within-bar knowledge of high->low order.
                    high_water = max(high_water, cl if just_added else h)
                    next_stop = static_stop
                    if p["trail"] > 0 and high_water >= px0 * (1 + p["trail_start_r"] * p["sl"]):
                        next_stop = max(next_stop, high_water * (1 - p["trail"]))
                    if p["breakeven_r"] > 0 and high_water >= px0 * (1 + p["breakeven_r"] * p["sl"]):
                        next_stop = max(next_stop, px0 * (1 + p["be_offset_bps"]/10000.))
                    working_stop = max(working_stop, next_stop)
            elapsed += 1
            if shares <= 1e-12:
                shares = 0.
                exit_date = day
                break
        if shares > 0 and day_i + 1 == max_days:
            proceeds += shares * last_close * fee_sell
            shares = 0.
            sell_fills += 1
            exit_date = day
            exit_reason = "TIME"
        # Per-session realized or unrealized cash equity adjustment.
        marks[day] = proceeds + shares * last_close * fee_sell - spent
        if exit_date is not None:
            break
    if exit_date is None:
        raise AssertionError("UNSETTLED_POSITION")
    return Fill(signal_day, entry_day, exit_date, float(proceeds - spent),
                buy_fills, sell_fills, 1 + day_i, exit_reason, marks)


def simulate_portfolio(p, signal_prob, features, complete, dates, year):
    """Re-run the entire signal, entry, exit and account path for each joint policy."""
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.Timestamp(f"{year}-12-31")
    year_days = [d for d in dates if start <= d <= end and d in complete]
    date_list = list(pd.DatetimeIndex(dates))
    date_idx = {d: i for i, d in enumerate(date_list)}
    capital = 1.
    entries = 0
    trades = []
    by_month = defaultdict(int)
    last_exit_index = -1
    daily_marks = {}
    for signal_day, prob in signal_prob.items():
        if signal_day not in date_idx or signal_day not in features.index:
            continue
        ix = date_idx[signal_day]
        if not (start <= signal_day <= end):
            continue
        f = features.loc[signal_day]
        if not allow_signal(p, f, prob):
            continue
        follow = date_list[ix+1:ix+1+p["hold"]]
        if len(follow) < p["hold"] or any(d not in complete for d in follow):
            continue
        entry_day = follow[0]
        if not (start <= entry_day <= end) or follow[-1] > end:
            continue
        entry_idx = ix + 1
        if entry_idx <= last_exit_index + p["cooldown"]:
            continue
        month = entry_day.strftime("%Y-%m")
        if p["max_month"] > 0 and by_month[month] >= p["max_month"]:
            continue
        previous_close = float(complete[signal_day].iloc[-1].close)
        future = [(d, complete[d]) for d in follow]
        trade = simulate_trade(p, future, p["entry_delay"], signal_day, previous_close)
        if trade is None:
            continue
        if trade.entry_date != entry_day or trade.exit_date not in date_idx:
            raise AssertionError("INCONSISTENT_SESSION_ORDER")
        if last_exit_index >= entry_idx:
            raise AssertionError("OVERLAPPING_POSITION")
        if trade.net_pnl < -1 or trade.net_pnl > 10:
            raise ValueError("INVALID_TRADE_EQUITY")
        base_equity = capital
        for date, mark in trade.equity_marks.items():
            daily_marks[date] = base_equity * (1 + mark)
        capital = base_equity * (1 + trade.net_pnl)
        trades.append(trade)
        entries += 1
        last_exit_index = date_idx[trade.exit_date]
        by_month[month] += 1
    # Closed-session path, with explicit mark-to-market inside each position;
    # do not treat missing marks as zero return when another position is open.
    equity = 1.
    path = [equity]
    for d in year_days:
        if d in daily_marks:
            equity = daily_marks[d]
        path.append(equity)
    if abs(path[-1] - capital) > 1e-7:
        raise AssertionError("ACCOUNT_MARK_RECONCILIATION")
    array = np.asarray(path)
    mdd = float((array / np.maximum.accumulate(array) - 1).min()) * 100
    active_days = sum(t.holding_sessions for t in trades)
    return {
        "trades": entries,
        "return_pct": round((capital - 1.) * 100, 5),
        "mdd_daily_mark_pct": round(mdd, 5),
        "win_rate_pct": round(100*sum(t.net_pnl > 0 for t in trades)/entries, 5) if entries else None,
        "avg_holding_sessions": round(active_days/entries, 4) if entries else None,
        "buy_fills": int(sum(t.fills_buy for t in trades)),
        "sell_fills": int(sum(t.fills_sell for t in trades)),
        "worst_trade_portfolio_pct": round(100*min((t.net_pnl for t in trades), default=0.), 5),
        "total_invested_session_days": int(active_days),
    }


def fit_probabilities(features, events, year):
    start, end = pd.Timestamp(f"{year}-01-01"), pd.Timestamp(f"{year}-12-31")
    eligible = features[base.PRICE + base.EXTRA].notna().all(axis=1)
    train = events.loc[events.exit_date < start].sort_values("date")
    train = train.loc[train.date.map(eligible).fillna(False)]
    test = events.loc[(events.date >= start) & (events.date <= end)].sort_values("date")
    test = test.loc[test.date.map(eligible).fillna(False)]
    if len(train) < 80 or train.positive.nunique() < 2 or len(test) < 80:
        raise ValueError("INSUFFICIENT_PIT_TRAIN_TEST")
    out = {}
    for name, cols in (("price_only", base.PRICE),
                       ("integrated_regime", base.PRICE + base.EXTRA)):
        mod = make_pipeline(StandardScaler(),
                            LogisticRegression(C=1., class_weight="balanced",
                                               max_iter=1000, random_state=42))
        mod.fit(features.loc[train.date, cols], train.positive)
        prediction = mod.predict_proba(features.loc[test.date, cols])[:, 1]
        out[name] = pd.Series(prediction, index=pd.DatetimeIndex(test.date))
    return out


def interaction_screen(rows, year, model):
    """Empirical two-factor contrast, jointly averaged over other options.

    This is a descriptive screen, not an identified causal or significant effect.
    """
    selected = [r for r in rows if r["year"] == year and r["model"] == model]
    flags = {
        "split_entry": lambda p: p["split"] != "single",
        "trail_enabled": lambda p: p["trail"] > 0,
        "breakeven_enabled": lambda p: p["breakeven_r"] > 0,
        "partial_profit": lambda p: p["partial_tp"] > 0,
        "tight_sl": lambda p: p["sl"] <= .02,
        "wide_tp": lambda p: p["tp"] >= .04,
        "low_size": lambda p: p["size"] <= .5,
        "vix_gate": lambda p: p["vix_min"] > 0 or p["vix_max"] < 99,
        "trend_gate": lambda p: p["trend"] != "none",
        "entry_delay": lambda p: p["entry_delay"] > 0,
        "cooldown": lambda p: p["cooldown"] > 0,
        "confidence_gate": lambda p: p["confidence"] >= .55,
    }
    scored = []
    for a, b in combinations(flags, 2):
        groups = defaultdict(list)
        for r in selected:
            p = r["params"]
            groups[(bool(flags[a](p)), bool(flags[b](p)))].append(r["return_pct"])
        if any(len(groups[v]) < 5 for v in ((False, False), (False, True), (True, False), (True, True))):
            continue
        means = {str(k): round(float(np.mean(v)), 5) for k, v in groups.items()}
        interaction = (np.mean(groups[(True, True)]) - np.mean(groups[(True, False)])
                       - np.mean(groups[(False, True)]) + np.mean(groups[(False, False)]))
        scored.append({"option_a": a, "option_b": b,
                       "joint_interaction_pct_points": round(float(interaction), 5),
                       "cell_counts": {str(k): len(v) for k, v in groups.items()},
                       "mean_by_cell": means})
    return sorted(scored, key=lambda v: abs(v["joint_interaction_pct_points"]), reverse=True)[:15]


def search(daily, intraday, market_zip, n, seed, shard, shards):
    if shards < 1 or not (0 <= shard < shards):
        raise ValueError("INVALID_SHARD")
    prices = base.read_prices(daily)
    features = base.build_features(prices, base.read_market_zip(market_zip))
    candles = base.read_15m(intraday)
    complete, coverage = base.complete_sessions(candles, prices.index)
    events = base.label_events(prices.index, complete)
    signals = {year: fit_probabilities(features, events, year) for year in (2025, 2026)}
    policies = generate_policies(n, seed)
    rows = []
    dates = list(pd.DatetimeIndex(prices.index))
    for k, p in enumerate(policies):
        if k % shards != shard:
            continue
        for year in (2025, 2026):
            for model, probs in signals[year].items():
                result = simulate_portfolio(p, probs, features, complete, dates, year)
                rows.append({"config_index": k, "policy_id": policy_id(p),
                             "year": year, "model": model, "params": p, **result})
    # Pairwise interaction across the full design requires combining shards.
    report = {"schema": "kalman-qld-joint-policy-v1",
              "status": "EXPLORATORY_NO_LIVE_GO",
              "configs_total": n, "configs_in_shard": len([k for k in range(n) if k%shards==shard]),
              "shard": shard, "shards": shards,
              "axes": {k: len(v) for k, v in AXES.items()},
              "dimensions": len(AXES),
              "full_factorial_count": int(np.prod(np.array([len(v) for v in AXES.values()], dtype=object))),
              "pairwise_coverage": pairwise_coverage(policies),
              "design_seed": seed,
              "not_exhaustive": True,
              "not_out_of_sample_policy_selection": True,
              "hold_live": True, "live_modified": False,
              "original_model_probabilities_reused": True,
              "selection": "NO_SELECTION; report all joint strategy results",
              "rth_complete_sessions": coverage["complete"],
              "rows": rows}
    return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--daily", required=True)
    p.add_argument("--intraday", required=True)
    p.add_argument("--market-zip", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--configs", type=int, default=800)
    p.add_argument("--shard", type=int, default=0)
    p.add_argument("--shards", type=int, default=4)
    p.add_argument("--seed", type=int, default=20261031)
    args = p.parse_args()
    result = search(args.daily, args.intraday, args.market_zip, args.configs,
                    args.seed, args.shard, args.shards)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    # Only trading-parameter configurations and scalar summary scores,
    # never raw proprietary bars or individual position fills.
    (out / f"joint_shard_{args.shard}.json").write_text(json.dumps(
        result, ensure_ascii=False, indent=None) + "\n")
    print("JOINT_POLICY_SHARD " + json.dumps({
        k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
