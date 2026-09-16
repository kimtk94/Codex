from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

CATEGORIES = ("INFLATION", "LABOR", "GROWTH", "POLICY")

MARKET_CUTOFF = {
    "US": ("America/New_York", 16, 0),
    "KR": ("Asia/Seoul", 15, 30),
    "BTC": ("UTC", 23, 59),
}

RATES_CONTEXT_COLUMNS = {
    "us_treasury_2y": "rates__us2y_level",
    "us_treasury_10y": "rates__us10y_level",
    "us_10y_2y_spread": "rates__us10y_2y_spread",
    "us_fed_funds_effective": "rates__fed_funds_effective",
    "us_fed_target_mid": "rates__fed_target_mid",
    "us_sofr": "rates__sofr",
    "usdkrw": "rates__usdkrw",
    "policy_rate_gap_us_minus_kr": "rates__policy_gap_us_minus_kr",
}

LATEST_COLUMNS = [
    "hawkish_surprise_z",
    "us2y_5m_bp",
    "us2y_30m_bp",
    "fed_reprice_30m_bp",
    "fed_reprice_next_bp",
    "rates_confirmation_30m_bp",
    "policy_confirmation_30m_bp",
    "nq_5m_ret",
    "soxx_5m_ret",
    "dxy_5m_ret",
    "gold_5m_ret",
    "btc_5m_ret",
]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Merge Macro Event V1 into Historical V3 matrices"
    )
    p.add_argument("--matrix-dir", required=True)
    p.add_argument("--macro-events", required=True)
    p.add_argument("--macro-spec", required=True)
    p.add_argument(
        "--rates-context",
        default="",
        help="Optional model-safe daily rates/FX feature CSV or parquet.",
    )
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def decision_cutoffs(as_of: pd.Series, market: str) -> pd.DatetimeIndex:
    market = market.upper()
    if market not in MARKET_CUTOFF:
        raise ValueError(f"unsupported market: {market}")
    tz_name, hour, minute = MARKET_CUTOFF[market]
    local_tz = ZoneInfo(tz_name)
    dates = pd.to_datetime(as_of, utc=True, errors="raise").dt.date
    local = pd.DatetimeIndex(
        [
            pd.Timestamp(
                year=d.year,
                month=d.month,
                day=d.day,
                hour=hour,
                minute=minute,
                tz=local_tz,
            )
            for d in dates
        ]
    )
    return local.tz_convert("UTC")


def _decayed_state(
    eligible: pd.DataFrame,
    cutoff: pd.Timestamp,
    category: str,
) -> float:
    part = eligible.loc[
        (eligible["category"] == category)
        & eligible["hawkish_surprise_z"].notna()
    ]
    if part.empty:
        # Dense state feature: no active shock is economically zero, not missing.
        return 0.0

    ages = (cutoff - part["available_time"]).dt.total_seconds() / 3600.0
    half_life = pd.to_numeric(part["half_life_hours"], errors="coerce")
    valid = (ages >= 0) & half_life.gt(0) & half_life.notna()
    if not valid.any():
        return 0.0

    weights = np.exp(
        -np.log(2.0)
        * ages[valid].to_numpy(dtype=float)
        / half_life[valid].to_numpy(dtype=float)
    )
    shocks = pd.to_numeric(
        part.loc[valid, "hawkish_surprise_z"], errors="coerce"
    ).to_numpy(dtype=float)
    return float(np.nansum(shocks * weights))


def _latest_decayed_value(
    eligible: pd.DataFrame,
    cutoff: pd.Timestamp,
    column: str,
) -> float:
    part = eligible.loc[eligible[column].notna()].copy()
    if part.empty:
        return 0.0
    latest = part.iloc[-1]
    age = max(
        0.0,
        float((cutoff - latest["available_time"]).total_seconds() / 3600.0),
    )
    half_life = float(latest["half_life_hours"])
    decay = np.exp(-np.log(2.0) * age / half_life) if half_life > 0 else 0.0
    return float(latest[column]) * float(decay)


def build_daily_macro_panel(
    as_of: pd.Series,
    events: pd.DataFrame,
    *,
    market: str,
    max_age_hours: float,
    rates_context: pd.DataFrame | None = None,
) -> pd.DataFrame:
    market = market.upper()
    e = events.copy()
    e["available_time"] = pd.to_datetime(
        e["available_time"], utc=True, errors="raise"
    )
    e = e.sort_values(["available_time", "event_id"]).reset_index(drop=True)
    source_available = {
        col: bool(e[col].notna().any()) if col in e.columns else False
        for col in LATEST_COLUMNS
    }

    cutoffs = decision_cutoffs(as_of, market)
    rows: list[dict[str, Any]] = []

    for cutoff in cutoffs:
        lower = cutoff - pd.Timedelta(hours=float(max_age_hours))
        eligible = e.loc[
            (e["available_time"] <= cutoff)
            & (e["available_time"] >= lower)
        ]

        row: dict[str, Any] = {"macro__decision_cutoff": cutoff}
        for category in CATEGORIES:
            row[f"macro__{category.lower()}_shock"] = _decayed_state(
                eligible, cutoff, category
            )

        if eligible.empty:
            row["macro__event_age_hours_latest"] = float(max_age_hours)
            row["macro__event_count_72h"] = 0.0
            row["macro__active_event_window"] = 0.0
        else:
            latest = eligible.iloc[-1]
            row["macro__event_age_hours_latest"] = float(
                (cutoff - latest["available_time"]).total_seconds() / 3600.0
            )
            recent72 = eligible.loc[
                eligible["available_time"]
                >= cutoff - pd.Timedelta(hours=72)
            ]
            row["macro__event_count_72h"] = float(len(recent72))
            row["macro__active_event_window"] = 1.0

        # If a reaction series exists in the dataset, represent "no active reaction"
        # as zero and decay the most recent non-null observation. If the source is
        # entirely unavailable (e.g. no intraday US2Y feed yet), keep it all-NaN so
        # feature selection cannot mistake missing data for a real zero series.
        for col in LATEST_COLUMNS:
            row[f"macro__{col}_latest"] = (
                _latest_decayed_value(eligible, cutoff, col)
                if source_available[col]
                else np.nan
            )

        rows.append(row)

    return pd.DataFrame(rows, index=pd.RangeIndex(len(rows)))


def _load_rates_context(path: Path) -> pd.DataFrame:
    if path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    elif path.suffix.lower() in {".csv", ".txt"}:
        frame = pd.read_csv(path)
    else:
        raise ValueError(f"unsupported rates context file: {path}")
    if "date" not in frame.columns:
        raise ValueError("rates context must contain a date column")
    return frame


def build_rates_context_panel(
    as_of: pd.Series,
    rates_context: pd.DataFrame,
) -> pd.DataFrame:
    rates = rates_context.copy()
    rates["__date"] = pd.to_datetime(
        rates["date"], errors="coerce"
    ).dt.normalize()
    rates = (
        rates.loc[rates["__date"].notna()]
        .sort_values("__date")
        .drop_duplicates("__date", keep="last")
        .set_index("__date")
    )

    selected = pd.DataFrame(index=rates.index)
    for source, dest in RATES_CONTEXT_COLUMNS.items():
        if source in rates.columns:
            selected[dest] = pd.to_numeric(
                rates[source], errors="coerce"
            )

    if "rates__us2y_level" in selected.columns:
        selected["rates__us2y_chg1d_bp"] = (
            selected["rates__us2y_level"].diff() * 100.0
        )
    if "rates__us10y_level" in selected.columns:
        selected["rates__us10y_chg1d_bp"] = (
            selected["rates__us10y_level"].diff() * 100.0
        )
    if "rates__us10y_2y_spread" in selected.columns:
        selected["rates__us10y_2y_chg1d_bp"] = (
            selected["rates__us10y_2y_spread"].diff() * 100.0
        )

    if "us_treasury_2y_available_flag" in rates.columns:
        selected["rates__us2y_available_flag"] = pd.to_numeric(
            rates["us_treasury_2y_available_flag"], errors="coerce"
        )
    if "us_treasury_2y_changed_flag" in rates.columns:
        selected["rates__us2y_changed_flag"] = pd.to_numeric(
            rates["us_treasury_2y_changed_flag"], errors="coerce"
        )

    anchor_dates = pd.to_datetime(
        as_of, utc=True, errors="raise"
    ).dt.tz_convert(None).dt.normalize()
    panel = selected.reindex(pd.DatetimeIndex(anchor_dates)).reset_index(drop=True)
    panel.index = pd.RangeIndex(len(panel))
    return panel


def merge_market_matrix(
    matrix: pd.DataFrame,
    events: pd.DataFrame,
    *,
    market: str,
    max_age_hours: float,
) -> pd.DataFrame:
    x = matrix.copy().reset_index(drop=True)
    panel = build_daily_macro_panel(
        x["as_of"],
        events,
        market=market,
        max_age_hours=max_age_hours,
    )
    if len(panel) != len(x):
        raise RuntimeError("macro panel length mismatch")

    parts = [x, panel]
    if rates_context is not None:
        parts.append(build_rates_context_panel(x["as_of"], rates_context))
    out = pd.concat(parts, axis=1)
    return out.drop(columns=["macro__decision_cutoff"])


def main() -> int:
    args = parse_args()
    matrix_dir = Path(args.matrix_dir).expanduser()
    events = pd.read_parquet(Path(args.macro_events).expanduser())
    spec = json.loads(
        Path(args.macro_spec).expanduser().read_text(encoding="utf-8")
    )
    output_dir = Path(args.output_dir).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)
    rates_context = None
    rates_path = None
    if str(args.rates_context).strip():
        rates_path = Path(args.rates_context).expanduser()
        if not rates_path.exists():
            raise FileNotFoundError(rates_path)
        rates_context = _load_rates_context(rates_path)
    max_age_hours = float(spec.get("max_event_age_hours", 168.0))

    status: dict[str, Any] = {
        "status": "READY",
        "markets": {},
        "rates_context": str(rates_path) if rates_path else None,
        "research_only": True,
        "live_execution": False,
        "neon_write": False,
        "toss_execution": False,
    }

    for market in ("US", "KR", "BTC"):
        try:
            source = matrix_dir / f"{market.lower()}_matrix.parquet"
            matrix = pd.read_parquet(source)
            merged = merge_market_matrix(
                matrix,
                events,
                market=market,
                max_age_hours=max_age_hours,
                rates_context=rates_context,
            )
            dest = output_dir / f"{market.lower()}_matrix.parquet"
            merged.to_parquet(dest, index=False)

            price_src = matrix_dir / f"{market.lower()}_anchor_prices.parquet"
            if price_src.exists():
                pd.read_parquet(price_src).to_parquet(
                    output_dir / price_src.name, index=False
                )

            macro_cols = [
                c for c in merged.columns if c.startswith("macro__")
            ]
            rates_cols = [
                c for c in merged.columns if c.startswith("rates__")
            ]
            status["markets"][market] = {
                "status": "READY",
                "rows": int(len(merged)),
                "macro_feature_count": len(macro_cols),
                "rates_feature_count": len(rates_cols),
                "rates_non_null_ratio": (
                    float(merged[rates_cols].notna().mean().mean())
                    if rates_cols
                    else 0.0
                ),
                "macro_non_null_ratio": (
                    float(merged[macro_cols].notna().mean().mean())
                    if macro_cols
                    else 0.0
                ),
            }
        except Exception as exc:
            status["status"] = "FAIL"
            status["markets"][market] = {
                "status": "FAIL",
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    (output_dir / "macro_merge_status.json").write_text(
        json.dumps(status, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return 0 if status["status"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
