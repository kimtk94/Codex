from __future__ import annotations

import numpy as np
import pandas as pd

NEWS_FEATURES = [
    "ngram_log1p_d1",
    "ngram_log1p_7d",
    "ngram_abnormal_z_30d",
]

HISTORY_START = pd.Timestamp("2024-08-01", tz="UTC")
HISTORY_END_EXCLUSIVE = pd.Timestamp("2026-09-02", tz="UTC")
FEATURE_READY_SIGNAL_DAY = pd.Timestamp("2024-09-01", tz="UTC")


def _utc_day(x: pd.Series) -> pd.Series:
    return pd.to_datetime(x, utc=True, errors="raise").dt.floor("D")


def build_daily_features(
    mentions: pd.DataFrame,
    symbols: list[str],
    *,
    history_start: pd.Timestamp = HISTORY_START,
    history_end_exclusive: pd.Timestamp = HISTORY_END_EXCLUSIVE,
) -> pd.DataFrame:
    required = {"symbol", "day_utc", "mention_count"}
    missing = required.difference(mentions.columns)
    if missing:
        raise ValueError(f"mentions missing columns: {sorted(missing)}")

    x = mentions.copy()
    x["symbol"] = x["symbol"].astype(str)
    x["day"] = pd.to_datetime(
        pd.to_numeric(x["day_utc"], errors="raise").astype("int64").astype(str),
        format="%Y%m%d",
        utc=True,
        errors="raise",
    )
    x["mention_count"] = pd.to_numeric(x["mention_count"], errors="raise")
    if (x["mention_count"] < 0).any():
        raise ValueError("mention_count must be nonnegative")
    if x.duplicated(["symbol", "day"]).any():
        raise ValueError("duplicate symbol/day rows")

    days = pd.date_range(
        history_start,
        history_end_exclusive - pd.Timedelta(days=1),
        freq="D",
        tz="UTC",
    )
    idx = pd.MultiIndex.from_product(
        [sorted(set(map(str, symbols))), days],
        names=["symbol", "day"],
    )
    panel = (
        x.set_index(["symbol", "day"])[["mention_count"]]
        .reindex(idx)
        .fillna({"mention_count": 0.0})
        .reset_index()
    )
    panel["mention_count"] = panel["mention_count"].astype(float)
    panel["ngram_log1p_d1"] = np.log1p(panel["mention_count"])

    parts = []
    for symbol, g in panel.groupby("symbol", sort=False):
        z = g.sort_values("day").copy()
        c = z["mention_count"]
        logc = z["ngram_log1p_d1"]

        z["ngram_log1p_7d"] = np.log1p(
            c.rolling(7, min_periods=1).sum()
        )

        prior_mean = logc.shift(1).rolling(30, min_periods=14).mean()
        prior_std = logc.shift(1).rolling(30, min_periods=14).std(ddof=0)
        denom = prior_std.where(prior_std > 1e-12)
        z["ngram_abnormal_z_30d"] = (
            (logc - prior_mean) / denom
        ).replace([np.inf, -np.inf], np.nan).fillna(0.0)

        parts.append(z)

    out = pd.concat(parts, ignore_index=True)
    for col in NEWS_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="raise")
    return out.sort_values(["symbol", "day"]).reset_index(drop=True)


def attach_news_features(
    frame: pd.DataFrame,
    daily_features: pd.DataFrame,
    *,
    timestamp_col: str = "timestamp",
) -> tuple[pd.DataFrame, dict]:
    required = {"symbol", timestamp_col}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"frame missing columns: {sorted(missing)}")

    out = frame.copy()
    out["signal_as_of"] = pd.to_datetime(
        out[timestamp_col], utc=True, errors="raise"
    ) + pd.Timedelta(hours=1)

    # Hard PIT rule: signal day D can only see completed UTC days <= D-1.
    out["news_day_used"] = out["signal_as_of"].dt.floor("D") - pd.Timedelta(days=1)

    feat = daily_features[["symbol", "day", *NEWS_FEATURES]].copy()
    feat["symbol"] = feat["symbol"].astype(str)
    out["symbol"] = out["symbol"].astype(str)

    out = out.merge(
        feat,
        left_on=["symbol", "news_day_used"],
        right_on=["symbol", "day"],
        how="left",
        validate="many_to_one",
    )
    out = out.drop(columns=["day"])

    for col in NEWS_FEATURES:
        out[col] = pd.to_numeric(out[col], errors="coerce")

    covered = out[NEWS_FEATURES].notna().all(axis=1)
    same_or_future = out["news_day_used"] >= out["signal_as_of"].dt.floor("D")
    if same_or_future.any():
        raise RuntimeError("PIT violation: same/future UTC day news used")

    audit = {
        "rows": int(len(out)),
        "covered_rows": int(covered.sum()),
        "coverage_ratio": float(covered.mean()) if len(out) else 0.0,
        "symbols": int(out["symbol"].nunique()),
        "news_features": list(NEWS_FEATURES),
        "signal_as_of_contract": "timestamp + 60 minutes",
        "news_day_contract": "UTC calendar day strictly before DATE(signal_as_of)",
        "same_day_forbidden": True,
    }
    return out, audit
