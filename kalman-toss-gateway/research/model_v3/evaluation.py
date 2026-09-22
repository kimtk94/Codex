from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


REQUIRED_COLUMNS = {"as_of", "score", "target_forward_return"}


@dataclass(frozen=True)
class LockedQuantilePolicy:
    top_fraction: float
    lookback_observations: int
    minimum_history_observations: int
    selection_end: str
    source: str = "PRE_FORWARD_VALIDATION_ONLY"

    def to_dict(self) -> dict[str, Any]:
        return {
            "top_fraction": self.top_fraction,
            "lookback_observations": self.lookback_observations,
            "minimum_history_observations": self.minimum_history_observations,
            "selection_end": self.selection_end,
            "source": self.source,
        }


def _finite_float(value: Any, default: float | None = None) -> float | None:
    try:
        x = float(value)
    except Exception:
        return default
    return x if math.isfinite(x) else default


def _prepare(frame: pd.DataFrame) -> pd.DataFrame:
    missing = REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"missing required columns: {sorted(missing)}")

    x = frame.copy()
    x["as_of"] = pd.to_datetime(x["as_of"], errors="raise")
    x["score"] = pd.to_numeric(x["score"], errors="coerce")
    x["target_forward_return"] = pd.to_numeric(
        x["target_forward_return"], errors="coerce"
    )
    if "anchor_close" in x.columns:
        x["anchor_close"] = pd.to_numeric(x["anchor_close"], errors="coerce")
    if "target_label" in x.columns:
        x["target_label"] = pd.to_numeric(x["target_label"], errors="coerce")

    x = x.sort_values("as_of").drop_duplicates("as_of", keep="last").reset_index(drop=True)
    x["observation_index"] = np.arange(len(x), dtype=int)
    return x


def rolling_top_quantile_policy(
    frame: pd.DataFrame,
    *,
    top_fraction: float,
    lookback_observations: int,
    minimum_history_observations: int,
) -> pd.DataFrame:
    if not (0.0 < top_fraction < 1.0):
        raise ValueError("top_fraction must be between 0 and 1")
    if lookback_observations < 2:
        raise ValueError("lookback_observations must be >= 2")
    if minimum_history_observations < 2:
        raise ValueError("minimum_history_observations must be >= 2")
    if minimum_history_observations > lookback_observations:
        raise ValueError("minimum_history_observations cannot exceed lookback")

    x = _prepare(frame)
    scores = x["score"].to_numpy(dtype=float)
    cutoffs = np.full(len(x), np.nan, dtype=float)
    selected = np.zeros(len(x), dtype=bool)
    history_rows = np.zeros(len(x), dtype=int)

    q = 1.0 - float(top_fraction)
    for i in range(len(x)):
        start = max(0, i - lookback_observations)
        history = scores[start:i]
        history = history[np.isfinite(history)]
        history_rows[i] = len(history)
        if len(history) < minimum_history_observations:
            continue
        cutoff = float(np.quantile(history, q, method="linear"))
        cutoffs[i] = cutoff
        if np.isfinite(scores[i]):
            selected[i] = bool(scores[i] >= cutoff)

    out = x.copy()
    out["score_cutoff"] = cutoffs
    out["history_rows"] = history_rows
    out["policy_ready"] = history_rows >= minimum_history_observations
    out["selected"] = selected
    out["top_fraction"] = float(top_fraction)
    return out


def non_overlapping_mask(
    frame: pd.DataFrame,
    *,
    horizon_observations: int,
    selection_column: str = "selected",
) -> np.ndarray:
    if horizon_observations < 1:
        raise ValueError("horizon_observations must be >= 1")
    if selection_column not in frame.columns:
        raise ValueError(f"missing selection column: {selection_column}")

    chosen = np.zeros(len(frame), dtype=bool)
    next_allowed = 0
    flags = frame[selection_column].fillna(False).astype(bool).to_numpy()
    for i, flag in enumerate(flags):
        if not flag or i < next_allowed:
            continue
        chosen[i] = True
        next_allowed = i + horizon_observations
    return chosen


def _max_drawdown_from_returns(returns: np.ndarray) -> float | None:
    values = np.asarray(returns, dtype=float)
    values = values[np.isfinite(values)]
    if len(values) == 0:
        return None
    wealth = np.cumprod(1.0 + values)
    peaks = np.maximum.accumulate(wealth)
    drawdown = wealth / peaks - 1.0
    return float(np.min(drawdown))


def _return_stats(values: Iterable[float]) -> dict[str, Any]:
    arr = np.asarray(list(values), dtype=float)
    arr = arr[np.isfinite(arr)]
    if len(arr) == 0:
        return {
            "rows": 0,
            "mean": None,
            "median": None,
            "win_rate": None,
            "compounded_return": None,
            "max_drawdown": None,
        }
    return {
        "rows": int(len(arr)),
        "mean": float(np.mean(arr)),
        "median": float(np.median(arr)),
        "win_rate": float(np.mean(arr > 0.0)),
        "compounded_return": float(np.prod(1.0 + arr) - 1.0),
        "max_drawdown": _max_drawdown_from_returns(arr),
    }


def evaluate_policy(
    frame: pd.DataFrame,
    *,
    top_fraction: float,
    lookback_observations: int,
    minimum_history_observations: int,
    horizon_observations: int,
    round_trip_cost_bps: float,
) -> dict[str, Any]:
    scored = rolling_top_quantile_policy(
        frame,
        top_fraction=top_fraction,
        lookback_observations=lookback_observations,
        minimum_history_observations=minimum_history_observations,
    )
    scored["nonoverlap_selected"] = non_overlapping_mask(
        scored,
        horizon_observations=horizon_observations,
    )

    valid = scored["target_forward_return"].notna()
    unconditional_returns = scored.loc[valid, "target_forward_return"].to_numpy(dtype=float)
    overlapping_selected_returns = scored.loc[
        valid & scored["selected"], "target_forward_return"
    ].to_numpy(dtype=float)
    nonoverlap_selected_returns = scored.loc[
        valid & scored["nonoverlap_selected"], "target_forward_return"
    ].to_numpy(dtype=float)

    cost_rate = float(round_trip_cost_bps) / 10000.0
    nonoverlap_net = nonoverlap_selected_returns - cost_rate

    unconditional = _return_stats(unconditional_returns)
    overlapping = _return_stats(overlapping_selected_returns)
    nonoverlap_gross = _return_stats(nonoverlap_selected_returns)
    nonoverlap_net_stats = _return_stats(nonoverlap_net)

    unconditional_mean = _finite_float(unconditional.get("mean"))
    unconditional_win = _finite_float(unconditional.get("win_rate"))
    nonoverlap_mean_net = _finite_float(nonoverlap_net_stats.get("mean"))
    nonoverlap_win = _finite_float(nonoverlap_net_stats.get("win_rate"))

    incremental_alpha_mean_net = (
        float(nonoverlap_mean_net - unconditional_mean)
        if nonoverlap_mean_net is not None and unconditional_mean is not None
        else None
    )
    win_rate_lift = (
        float(nonoverlap_win - unconditional_win)
        if nonoverlap_win is not None and unconditional_win is not None
        else None
    )

    buy_hold_return = None
    anchor = scored.get("anchor_close")
    if anchor is not None:
        finite = pd.to_numeric(anchor, errors="coerce").dropna()
        if len(finite) >= 2 and float(finite.iloc[0]) != 0.0:
            buy_hold_return = float(finite.iloc[-1] / finite.iloc[0] - 1.0)

    return {
        "top_fraction": float(top_fraction),
        "lookback_observations": int(lookback_observations),
        "minimum_history_observations": int(minimum_history_observations),
        "horizon_observations": int(horizon_observations),
        "round_trip_cost_bps": float(round_trip_cost_bps),
        "rows": int(len(scored)),
        "policy_ready_rows": int(scored["policy_ready"].sum()),
        "selected_rows": int(scored["selected"].sum()),
        "nonoverlap_selected_rows": int(scored["nonoverlap_selected"].sum()),
        "unconditional": unconditional,
        "overlapping_selected": overlapping,
        "nonoverlap_selected_gross": nonoverlap_gross,
        "nonoverlap_selected_net": nonoverlap_net_stats,
        "nonoverlap_incremental_alpha_mean_net": incremental_alpha_mean_net,
        "nonoverlap_win_rate_lift": win_rate_lift,
        "buy_hold_return": buy_hold_return,
        "first_as_of": (
            pd.Timestamp(scored["as_of"].min()).isoformat() if len(scored) else None
        ),
        "last_as_of": (
            pd.Timestamp(scored["as_of"].max()).isoformat() if len(scored) else None
        ),
        "entry_dates": [
            pd.Timestamp(x).isoformat()
            for x in scored.loc[scored["nonoverlap_selected"], "as_of"].tolist()
        ],
    }


def select_pre_forward_policy(
    frame: pd.DataFrame,
    *,
    top_fractions: Iterable[float],
    forward_start: str | pd.Timestamp,
    lookback_observations: int,
    minimum_history_observations: int,
    horizon_observations: int,
    round_trip_cost_bps: float,
    minimum_nonoverlap_entries: int,
) -> tuple[LockedQuantilePolicy, dict[str, Any]]:
    x = _prepare(frame)
    forward_ts = pd.Timestamp(forward_start)
    reference = x.loc[x["as_of"] < forward_ts].copy()
    if reference.empty:
        raise RuntimeError("no pre-forward rows available for policy selection")

    candidates: list[dict[str, Any]] = []
    for fraction in sorted({float(v) for v in top_fractions}):
        result = evaluate_policy(
            reference,
            top_fraction=fraction,
            lookback_observations=lookback_observations,
            minimum_history_observations=minimum_history_observations,
            horizon_observations=horizon_observations,
            round_trip_cost_bps=round_trip_cost_bps,
        )
        result["selection_floor_pass"] = (
            result["nonoverlap_selected_rows"] >= int(minimum_nonoverlap_entries)
        )
        candidates.append(result)

    eligible = [x for x in candidates if x["selection_floor_pass"]]
    if not eligible:
        raise RuntimeError(
            "no top-fraction policy met minimum pre-forward non-overlap entries"
        )

    def key(item: dict[str, Any]) -> tuple[float, float, float]:
        alpha = _finite_float(
            item.get("nonoverlap_incremental_alpha_mean_net"), -999.0
        )
        lift = _finite_float(item.get("nonoverlap_win_rate_lift"), -999.0)
        return (
            float(alpha),
            float(lift),
            -float(item["top_fraction"]),
        )

    eligible.sort(key=key, reverse=True)
    best = eligible[0]
    selection_end = pd.Timestamp(reference["as_of"].max()).isoformat()
    policy = LockedQuantilePolicy(
        top_fraction=float(best["top_fraction"]),
        lookback_observations=int(lookback_observations),
        minimum_history_observations=int(minimum_history_observations),
        selection_end=selection_end,
    )
    return policy, {
        "status": "LOCKED",
        "forward_start": forward_ts.isoformat(),
        "selection_end": selection_end,
        "selection_uses_forward_rows": False,
        "selected_policy": policy.to_dict(),
        "candidate_results": candidates,
    }


def evaluate_forward_gate(
    frame: pd.DataFrame,
    *,
    policy: LockedQuantilePolicy,
    forward_start: str | pd.Timestamp,
    horizon_observations: int,
    round_trip_cost_bps: float,
    gate: dict[str, Any],
) -> dict[str, Any]:
    x = _prepare(frame)
    forward_ts = pd.Timestamp(forward_start)
    if pd.Timestamp(policy.selection_end) >= forward_ts:
        raise ValueError("locked policy selection_end must be before forward_start")

    forward = x.loc[x["as_of"] >= forward_ts].copy()
    minimum_interpret = int(
        gate.get("minimum_forward_observations_for_interpretation", 60)
    )
    minimum_promote = int(
        gate.get("minimum_forward_observations_for_promotion", 120)
    )
    minimum_entries = int(
        gate.get("minimum_nonoverlap_entries_for_promotion", 8)
    )

    if forward.empty:
        return {
            "status": "TRACKING_NO_FORWARD_ROWS",
            "promotion_eligible": False,
            "forward_start": forward_ts.isoformat(),
            "forward_observations": 0,
            "policy": policy.to_dict(),
            "checks": {
                "minimum_forward_observations": False,
                "minimum_nonoverlap_entries": False,
                "minimum_incremental_alpha_mean_net": False,
                "minimum_win_rate_lift": False,
                "minimum_net_compounded_return": False,
            },
        }

    # Keep pre-forward history available for point-in-time rolling thresholds,
    # but evaluate returns only on forward rows.
    full_scored = rolling_top_quantile_policy(
        x,
        top_fraction=policy.top_fraction,
        lookback_observations=policy.lookback_observations,
        minimum_history_observations=policy.minimum_history_observations,
    )
    full_scored["nonoverlap_selected"] = non_overlapping_mask(
        full_scored,
        horizon_observations=horizon_observations,
    )
    forward_scored = full_scored.loc[full_scored["as_of"] >= forward_ts].copy()

    # Recompute non-overlap inside the forward era so a pre-forward position
    # cannot suppress the first eligible forward entry.
    forward_scored["nonoverlap_selected"] = non_overlapping_mask(
        forward_scored.reset_index(drop=True),
        horizon_observations=horizon_observations,
    )

    # Summarize the forward selections produced by thresholds that used
    # all information available strictly before each current score.
    valid = forward_scored["target_forward_return"].notna()
    unconditional_returns = forward_scored.loc[
        valid, "target_forward_return"
    ].to_numpy(dtype=float)
    selected_returns = forward_scored.loc[
        valid & forward_scored["nonoverlap_selected"], "target_forward_return"
    ].to_numpy(dtype=float)
    cost_rate = float(round_trip_cost_bps) / 10000.0
    net_returns = selected_returns - cost_rate

    unconditional = _return_stats(unconditional_returns)
    nonoverlap_gross = _return_stats(selected_returns)
    nonoverlap_net = _return_stats(net_returns)
    u_mean = _finite_float(unconditional.get("mean"))
    u_win = _finite_float(unconditional.get("win_rate"))
    n_mean = _finite_float(nonoverlap_net.get("mean"))
    n_win = _finite_float(nonoverlap_net.get("win_rate"))
    alpha = (
        float(n_mean - u_mean)
        if n_mean is not None and u_mean is not None
        else None
    )
    lift = (
        float(n_win - u_win)
        if n_win is not None and u_win is not None
        else None
    )

    forward_observations = int(valid.sum())
    entry_count = int(nonoverlap_net["rows"])
    min_alpha = float(gate.get("minimum_incremental_alpha_mean_net", 0.0))
    min_lift = float(gate.get("minimum_win_rate_lift", 0.0))
    min_compounded = float(gate.get("minimum_net_compounded_return", 0.0))

    checks = {
        "minimum_forward_observations": forward_observations >= minimum_promote,
        "minimum_nonoverlap_entries": entry_count >= minimum_entries,
        "minimum_incremental_alpha_mean_net": (
            alpha is not None and alpha > min_alpha
        ),
        "minimum_win_rate_lift": (
            lift is not None and lift > min_lift
        ),
        "minimum_net_compounded_return": (
            _finite_float(nonoverlap_net.get("compounded_return"), -999.0)
            > min_compounded
        ),
    }
    eligible = all(checks.values())
    status = (
        "READY_FOR_PROMOTION_REVIEW"
        if eligible
        else (
            "TRACKING_INSUFFICIENT_FORWARD_HISTORY"
            if forward_observations < minimum_interpret
            else "TRACKING_GATE_NOT_MET"
        )
    )

    return {
        "status": status,
        "promotion_eligible": eligible,
        "forward_start": forward_ts.isoformat(),
        "forward_observations": forward_observations,
        "policy": policy.to_dict(),
        "checks": checks,
        "minimums": {
            "minimum_forward_observations_for_interpretation": minimum_interpret,
            "minimum_forward_observations_for_promotion": minimum_promote,
            "minimum_nonoverlap_entries_for_promotion": minimum_entries,
            "minimum_incremental_alpha_mean_net": min_alpha,
            "minimum_win_rate_lift": min_lift,
            "minimum_net_compounded_return": min_compounded,
        },
        "unconditional": unconditional,
        "nonoverlap_selected_gross": nonoverlap_gross,
        "nonoverlap_selected_net": nonoverlap_net,
        "nonoverlap_incremental_alpha_mean_net": alpha,
        "nonoverlap_win_rate_lift": lift,
        "entry_dates": [
            pd.Timestamp(v).isoformat()
            for v in forward_scored.loc[
                valid & forward_scored["nonoverlap_selected"], "as_of"
            ].tolist()
        ],
    }
