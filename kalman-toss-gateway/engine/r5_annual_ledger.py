from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

MODEL_VERSION = "R5.1_BASE_HGB"
STRATEGY_VERSION = "R5.1_BASE_HGB"
CANDIDATE_ID = "R5P_HGB_REFIT_R4"
REPLAY_LEDGER_TYPE = "BACKTEST"
FORWARD_LEDGER_TYPE = "LIVE_SHADOW"
REPLAY_PROVENANCE = "R5_1_RECONSTRUCTED_2026"
FORWARD_PROVENANCE = "R5_1_CANONICAL_FORWARD_LOG"
REPLAY_RUN_ID = "r5-2026-reconstructed-v1"
FORWARD_IMPORT_RUN_ID = "r5-2026-forward-import-v1"
PIPELINE_VERSION = "r5-annual-ledger-v1"
FEATURE_VERSION = "R5.1_CANONICAL_1H_EXACT"
R51_START = "2026-09-03T13:30:00Z"
COST_BPS = 10.0
MIN_COVERAGE = 90
UUID_NAMESPACE = uuid.UUID("aab7410d-53e2-4d85-934f-0ea3bf2ab23e")

ML_FEATURES = [
    "cs_ret_1b",
    "cs_ret_2b",
    "cs_ret_4b",
    "cs_ret_6b",
    "cs_rv_6",
    "cs_rv_24",
    "cs_ma_dist_6",
    "cs_ma_dist_24",
    "cs_volume_z_24",
    "cs_bar_range",
    "cs_beta24",
    "cs_residual_ret_6b",
    "qqq_ret_2b",
    "qqq_ret_6b",
    "qqq_rv_24",
    "qqq_ma_dist_24",
    "ix_trend_qqq",
    "ix_vol_qqq",
    "ix_ret1_qqq",
    "ix_mom6_qqq",
]


@dataclass(frozen=True)
class Layout:
    us: Path
    src_panel: Path
    src_qqq_1h: Path
    contract: Path
    live_1h: Path
    live_qqq: Path
    r51_model_dir: Path
    r51_freeze_manifest: Path
    r51_model: Path
    r51_medians: Path
    r51_signal_log: Path
    r51_trade_log: Path
    r51_outcome_log: Path


@dataclass(frozen=True)
class LedgerTrade:
    trade_id: uuid.UUID
    original_trade_id: str
    symbol: str
    entry_time: datetime
    entry_price: float
    exit_time: datetime | None
    exit_price: float | None
    return_pct: float | None
    raw_return: float | None
    gross_weighted_return: float | None
    net10_return: float | None
    position_weight: float
    expected_seq: int
    expected_exit_seq: int
    score: float | None
    model_freeze_sha256: str
    ledger_type: str
    provenance: str
    prospective: bool
    in_sample_warning: bool


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description=(
            "Build the exact R5.1 2026 annual ledger: frozen-model reconstructed "
            "history plus canonical Forward SHADOW +4-bar trades."
        )
    )
    p.add_argument("--mode", choices=["full", "replay", "forward"], default="full")
    p.add_argument("--start", default="2026-01-01T00:00:00Z")
    p.add_argument("--replay-end", default=R51_START)
    p.add_argument("--us-root", default="")
    p.add_argument("--write-db", action="store_true")
    p.add_argument("--replace-legacy-live", action="store_true")
    p.add_argument("--publish-dashboard", action="store_true")
    p.add_argument("--output-json", default="")
    return p.parse_args()


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso(value: Any) -> str | None:
    if value is None:
        return None
    import pandas as pd

    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.isoformat()


def to_datetime(value: Any) -> datetime:
    import pandas as pd

    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def locate_us_root(explicit: str = "") -> Path:
    candidates: list[Path] = []
    for raw in (
        explicit,
        os.environ.get("KALMAN_US_ETF_ROOT", ""),
        "/content/drive/MyDrive/US_ETF",
        "/mnt/gdrive/US_ETF",
        "/mnt/gdrive/MyDrive/US_ETF",
    ):
        if raw:
            p = Path(raw).expanduser()
            if p not in candidates:
                candidates.append(p)

    sentinels = (
        "directional_research/canonical_history_v1",
        "model_lab_v1/results/r5_0_1_research_sandbox_all_data/model_freeze",
    )
    for candidate in candidates:
        if candidate.exists() and all((candidate / s).exists() for s in sentinels):
            return candidate

    checked = ", ".join(str(x) for x in candidates)
    raise RuntimeError(
        "US_ETF root not found. Set KALMAN_US_ETF_ROOT. Checked: " + checked
    )


def build_layout(us: Path) -> Layout:
    src_canon = us / "directional_research/canonical_history_v1"
    r291 = us / "model_lab_v1/results/r2_9_1_dual_engine"
    live = us / "directional_research/r4_live_canonical_v1"
    r501 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r51 = us / "model_lab_v1/results/r5_1_prospective_shadow"
    model_dir = r501 / "model_freeze"
    return Layout(
        us=us,
        src_panel=src_canon / "panel_1h_gap_aware",
        src_qqq_1h=src_canon / "qqq_context/history_1h/QQQ_1h_gap_aware.parquet",
        contract=r291 / "r2_9_1_model_contract.csv",
        live_1h=live / "panel_1h_overlay",
        live_qqq=live / "qqq_context",
        r51_model_dir=model_dir,
        r51_freeze_manifest=model_dir / "r5_1_model_freeze_manifest.json",
        r51_model=model_dir / "r5_hgb.joblib",
        r51_medians=model_dir / "r5_training_medians.json",
        r51_signal_log=r51 / "r5_1_signal_log.parquet",
        r51_trade_log=r51 / "r5_1_trade_entry_log.parquet",
        r51_outcome_log=r51 / "r5_1_outcome_log.parquet",
    )


def verify_freeze(layout: Layout) -> tuple[dict[str, Any], str]:
    import pandas as pd

    if not layout.r51_freeze_manifest.exists():
        raise RuntimeError(f"missing freeze manifest: {layout.r51_freeze_manifest}")
    freeze = json.loads(layout.r51_freeze_manifest.read_text(encoding="utf-8"))
    if freeze.get("selected_primary") != "R5C0_HGB_REFERENCE":
        raise RuntimeError("unexpected R5.1 selected_primary")
    if pd.Timestamp(freeze.get("prospective_start")) != pd.Timestamp(R51_START):
        raise RuntimeError("R5.1 prospective_start mismatch")
    if freeze.get("all_valid_pre_cutoff_rows_used") is not True:
        raise RuntimeError("R5.1 all_valid_pre_cutoff_rows_used invariant failed")

    for name, expected in (freeze.get("artifacts") or {}).items():
        p = layout.r51_model_dir / name
        if not p.exists():
            raise RuntimeError(f"missing frozen artifact: {p}")
        actual = sha256_file(p)
        if actual != expected:
            raise RuntimeError(
                f"R5.1 frozen artifact hash mismatch: {name} expected={expected} actual={actual}"
            )

    return freeze, sha256_file(layout.r51_freeze_manifest)


def normalize_ts(series: Any) -> Any:
    import pandas as pd

    return pd.to_datetime(series, utc=True, errors="coerce")


def readpq(path: Path) -> Any:
    import pandas as pd

    if not path.exists():
        return pd.DataFrame()
    return pd.read_parquet(path)


def load_locked_symbol(layout: Layout, symbol: str) -> Any:
    import pandas as pd

    p = layout.src_panel / f"{symbol}_1h_gap_aware.parquet"
    if not p.exists():
        raise RuntimeError(f"missing canonical symbol: {p}")
    z = pd.read_parquet(p)
    if "timestamp" in z.columns:
        z["timestamp"] = normalize_ts(z["timestamp"])
    else:
        z["market_open_utc"] = normalize_ts(z["market_open_utc"])
        z["timestamp"] = z["market_open_utc"] + pd.to_timedelta(
            z["session_bucket"].astype(int), unit="h"
        )
    z["expected_seq"] = pd.to_numeric(z["expected_seq"]).astype("int64")
    z["symbol"] = symbol
    return z


def combined_symbol(layout: Layout, symbol: str) -> Any:
    import pandas as pd

    locked = load_locked_symbol(layout, symbol)
    live = readpq(layout.live_1h / f"{symbol}_1h_live.parquet")
    if len(live):
        live["timestamp"] = normalize_ts(live["timestamp"])
        live["expected_seq"] = pd.to_numeric(live["expected_seq"]).astype("int64")
        live["symbol"] = symbol
        live = live.loc[live["timestamp"] > locked["timestamp"].max()]
    return (
        pd.concat([locked, live], ignore_index=True)
        .sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
    )


def combined_qqq(layout: Layout) -> Any:
    import pandas as pd

    locked = pd.read_parquet(layout.src_qqq_1h)
    if "timestamp" in locked.columns:
        locked["timestamp"] = normalize_ts(locked["timestamp"])
    else:
        locked["market_open_utc"] = normalize_ts(locked["market_open_utc"])
        locked["timestamp"] = locked["market_open_utc"] + pd.to_timedelta(
            locked["session_bucket"].astype(int), unit="h"
        )
    locked["expected_seq"] = pd.to_numeric(locked["expected_seq"]).astype("int64")
    locked["symbol"] = "QQQ"

    live = readpq(layout.live_qqq / "QQQ_1h_live.parquet")
    if len(live):
        live["timestamp"] = normalize_ts(live["timestamp"])
        live["expected_seq"] = pd.to_numeric(live["expected_seq"]).astype("int64")
        live["symbol"] = "QQQ"
        live = live.loc[live["timestamp"] > locked["timestamp"].max()]

    return (
        pd.concat([locked, live], ignore_index=True)
        .sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
    )


def grid_feature_frame(obs: Any) -> Any:
    import numpy as np
    import pandas as pd

    obs = obs.copy().sort_values("expected_seq")
    lo = int(obs["expected_seq"].min())
    hi = int(obs["expected_seq"].max())
    g = pd.DataFrame({"expected_seq": np.arange(lo, hi + 1, dtype=np.int64)})
    cols = [
        c
        for c in [
            "expected_seq",
            "timestamp",
            "session_date",
            "market_open_utc",
            "session_bucket",
            "open",
            "high",
            "low",
            "close",
            "volume",
        ]
        if c in obs.columns
    ]
    g = g.merge(obs[cols], on="expected_seq", how="left")
    c = g["close"]
    o = g["open"]
    h = g["high"]
    l = g["low"]
    v = g["volume"]

    for lag in [1, 2, 4, 6]:
        g[f"ret_{lag}b"] = c / c.shift(lag) - 1
    g["bar_body"] = (c - o) / o
    g["bar_range"] = (h - l) / c
    g["rv_6"] = g["ret_1b"].rolling(6, min_periods=4).std()
    g["rv_24"] = g["ret_1b"].rolling(24, min_periods=18).std()
    g["ma_dist_6"] = c / c.rolling(6, min_periods=5).mean() - 1
    g["ma_dist_24"] = c / c.rolling(24, min_periods=18).mean() - 1
    lv = np.log1p(v)
    mu = lv.rolling(24, min_periods=18).mean()
    sd = lv.rolling(24, min_periods=18).std()
    g["volume_z_24"] = (lv - mu) / sd.replace(0, np.nan)
    g["fwd_ret_1b"] = c.shift(-1) / c - 1
    g["fwd_ret_4b"] = c.shift(-4) / c - 1
    g["y_up_1b"] = (g["fwd_ret_1b"] > 0).astype(float).where(g["fwd_ret_1b"].notna())
    g["y_up_4b"] = (g["fwd_ret_4b"] > 0).astype(float).where(g["fwd_ret_4b"].notna())
    return g.loc[g["close"].notna()].copy()


def load_symbols(layout: Layout) -> list[str]:
    import pandas as pd

    if not layout.contract.exists():
        raise RuntimeError(f"missing R4 universe contract: {layout.contract}")
    contract = pd.read_csv(layout.contract)
    symbols = sorted(contract["symbol"].astype(str).unique())
    if len(symbols) != 93:
        raise RuntimeError(f"expected 93 R4 symbols, got {len(symbols)}")
    missing = [
        s for s in symbols if not (layout.src_panel / f"{s}_1h_gap_aware.parquet").exists()
    ]
    if missing:
        raise RuntimeError(f"missing canonical panel symbols: {missing[:10]}")
    return symbols


def trim_window(frame: Any, start: Any, end: Any, lookback_days: int = 120) -> Any:
    import pandas as pd

    lo = pd.Timestamp(start) - pd.Timedelta(days=lookback_days)
    hi = pd.Timestamp(end) + pd.Timedelta(days=5)
    return frame.loc[(frame["timestamp"] >= lo) & (frame["timestamp"] <= hi)].copy()


def build_replay_panel(
    layout: Layout,
    symbols: list[str],
    start: Any,
    replay_end: Any,
) -> Any:
    import numpy as np
    import pandas as pd

    qqq = trim_window(combined_qqq(layout), start, replay_end)
    qqq_base = grid_feature_frame(qqq)
    qqq_cols = {
        "ret_1b": "qqq_ret_1b",
        "ret_2b": "qqq_ret_2b",
        "ret_4b": "qqq_ret_4b",
        "ret_6b": "qqq_ret_6b",
        "bar_range": "qqq_bar_range",
        "rv_6": "qqq_rv_6",
        "rv_24": "qqq_rv_24",
        "ma_dist_6": "qqq_ma_dist_6",
        "ma_dist_24": "qqq_ma_dist_24",
    }
    qqq_ctx = qqq_base[["expected_seq"] + list(qqq_cols)].rename(columns=qqq_cols)

    parts = []
    for i, symbol in enumerate(symbols, start=1):
        obs = trim_window(combined_symbol(layout, symbol), start, replay_end)
        b = grid_feature_frame(obs)
        b["symbol"] = symbol
        b = b.merge(qqq_ctx, on="expected_seq", how="left", validate="one_to_one")
        b["timestamp"] = normalize_ts(b["timestamp"])
        b["day_of_week"] = b["timestamp"].dt.dayofweek
        parts.append(b)
        if i % 20 == 0:
            print(f"[R5-2026] feature base {i}/{len(symbols)}")

    panel = (
        pd.concat(parts, ignore_index=True)
        .sort_values(["symbol", "expected_seq"])
        .reset_index(drop=True)
    )

    panel = panel.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
    beta = np.full(len(panel), np.nan, float)
    for _, idxs in panel.groupby("symbol", sort=False).groups.items():
        idx = np.asarray(list(idxs), dtype=int)
        x = panel.loc[idx, "ret_1b"]
        y = panel.loc[idx, "qqq_ret_1b"]
        cov = x.rolling(24, min_periods=12).cov(y)
        var = y.rolling(24, min_periods=12).var()
        beta[idx] = (cov / var.replace(0, np.nan)).to_numpy()

    panel["beta24"] = np.clip(beta, -3, 3)
    panel["residual_ret_6b"] = (
        panel["ret_6b"] - panel["beta24"] * panel["qqq_ret_6b"]
    )
    grouped = panel.groupby("timestamp")
    for col in [
        "ret_1b",
        "ret_2b",
        "ret_4b",
        "ret_6b",
        "rv_6",
        "rv_24",
        "ma_dist_6",
        "ma_dist_24",
        "volume_z_24",
        "bar_range",
        "beta24",
        "residual_ret_6b",
    ]:
        panel["cs_" + col] = grouped[col].rank(pct=True, method="average")

    panel["universe_median_rv_24"] = grouped["rv_24"].transform("median")
    panel["universe_mean_fwd_ret_4b"] = grouped["fwd_ret_4b"].transform("mean")
    panel["ix_trend_qqq"] = panel["ma_dist_24"] * panel["qqq_ma_dist_24"]
    panel["ix_vol_qqq"] = panel["rv_24"] * panel["qqq_rv_24"]
    panel["ix_ret1_qqq"] = panel["ret_1b"] * panel["qqq_ret_2b"]
    panel["ix_mom6_qqq"] = panel["ret_6b"] * panel["qqq_ret_6b"]
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel


def deterministic_trade_uuid(provenance: str, original_trade_id: str) -> uuid.UUID:
    return uuid.uuid5(UUID_NAMESPACE, f"{provenance}|{original_trade_id}")


def build_reconstructed_trades(
    layout: Layout,
    panel: Any,
    start: Any,
    replay_end: Any,
    freeze_sha: str,
) -> tuple[list[LedgerTrade], dict[str, Any]]:
    import joblib
    import numpy as np
    import pandas as pd

    model = joblib.load(layout.r51_model)
    med = pd.Series(json.loads(layout.r51_medians.read_text(encoding="utf-8")), dtype=float)
    missing_features = [x for x in ML_FEATURES if x not in med.index]
    if missing_features:
        raise RuntimeError(f"training medians missing features: {missing_features}")

    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(replay_end)
    timestamps = sorted(
        pd.Timestamp(x)
        for x in panel.loc[
            (panel["timestamp"] >= start_ts) & (panel["timestamp"] <= end_ts),
            "timestamp",
        ]
        .dropna()
        .unique()
    )

    signals: list[dict[str, Any]] = []
    coverage_skipped = 0
    for i, ts in enumerate(timestamps, start=1):
        z = panel.loc[panel["timestamp"] == ts].copy()
        valid = z.dropna(
            subset=[
                "rv_24",
                "ma_dist_24",
                "volume_z_24",
                "bar_range",
                "qqq_rv_24",
                "qqq_ma_dist_24",
            ]
        ).copy()
        coverage = int(valid["symbol"].nunique())
        if coverage < MIN_COVERAGE:
            coverage_skipped += 1
            continue
        valid["R5_HGB_SCORE"] = model.predict(valid[ML_FEATURES].fillna(med))
        top = valid.sort_values(
            ["R5_HGB_SCORE", "symbol"], ascending=[False, True]
        ).iloc[0]
        ratio = (
            float(top["universe_median_rv_24"] / top["rv_24"])
            if float(top["rv_24"]) > 0
            else 1.0
        )
        weight = float(np.clip(ratio, 0.25, 1.0))
        signals.append(
            {
                "timestamp": pd.Timestamp(ts),
                "expected_seq": int(top["expected_seq"]),
                "expected_exit_seq": int(top["expected_seq"]) + 4,
                "selected_symbol": str(top["symbol"]),
                "score": float(top["R5_HGB_SCORE"]),
                "position_weight": weight,
                "coverage": coverage,
            }
        )
        if i % 250 == 0:
            print(f"[R5-2026] scored {i}/{len(timestamps)} timestamps")

    price_lookup = (
        panel[["symbol", "expected_seq", "timestamp", "close"]]
        .drop_duplicates(["symbol", "expected_seq"])
        .set_index(["symbol", "expected_seq"])
    )

    trades: list[LedgerTrade] = []
    last_exit = -10**18
    for signal in sorted(signals, key=lambda x: (x["expected_seq"], x["timestamp"])):
        seq = int(signal["expected_seq"])
        exit_seq = int(signal["expected_exit_seq"])
        if seq < last_exit:
            continue

        symbol = str(signal["selected_symbol"])
        entry_key = (symbol, seq)
        exit_key = (symbol, exit_seq)
        if entry_key not in price_lookup.index:
            raise RuntimeError(f"missing reconstructed entry price: {entry_key}")
        if exit_key not in price_lookup.index:
            # Near the boundary, do not allow a reconstructed trade to leak into
            # the prospective period. Earlier missing +4 data is a data failure.
            entry_row = price_lookup.loc[entry_key]
            if pd.Timestamp(entry_row["timestamp"]) >= end_ts - pd.Timedelta(days=2):
                break
            raise RuntimeError(f"missing reconstructed +4 exit price: {exit_key}")

        entry_row = price_lookup.loc[entry_key]
        exit_row = price_lookup.loc[exit_key]
        if isinstance(entry_row, pd.DataFrame) or isinstance(exit_row, pd.DataFrame):
            raise RuntimeError(f"duplicate canonical price row for {symbol} seq={seq}")

        exit_time = pd.Timestamp(exit_row["timestamp"])
        if exit_time > end_ts:
            break

        entry_price = float(entry_row["close"])
        exit_price = float(exit_row["close"])
        raw_return = exit_price / entry_price - 1.0
        weight = float(signal["position_weight"])
        gross = weight * raw_return
        net10 = gross - weight * COST_BPS / 10000.0
        original_trade_id = f"{CANDIDATE_ID}|{seq}"

        trades.append(
            LedgerTrade(
                trade_id=deterministic_trade_uuid(
                    REPLAY_PROVENANCE, original_trade_id
                ),
                original_trade_id=original_trade_id,
                symbol=symbol,
                entry_time=to_datetime(entry_row["timestamp"]),
                entry_price=entry_price,
                exit_time=to_datetime(exit_time),
                exit_price=exit_price,
                return_pct=net10,
                raw_return=raw_return,
                gross_weighted_return=gross,
                net10_return=net10,
                position_weight=weight,
                expected_seq=seq,
                expected_exit_seq=exit_seq,
                score=float(signal["score"]),
                model_freeze_sha256=freeze_sha,
                ledger_type=REPLAY_LEDGER_TYPE,
                provenance=REPLAY_PROVENANCE,
                prospective=False,
                in_sample_warning=True,
            )
        )
        last_exit = exit_seq

    stats = {
        "timestamps_considered": len(timestamps),
        "signals": len(signals),
        "coverage_skipped": coverage_skipped,
        "trades": len(trades),
    }
    return trades, stats


def load_price_map(layout: Layout, symbol: str) -> dict[int, tuple[datetime, float]]:
    z = combined_symbol(layout, symbol)
    out: dict[int, tuple[datetime, float]] = {}
    for row in z[["expected_seq", "timestamp", "close"]].itertuples(index=False):
        try:
            close = float(row.close)
        except Exception:
            continue
        out[int(row.expected_seq)] = (to_datetime(row.timestamp), close)
    return out


def build_forward_trades(
    layout: Layout,
    freeze_sha: str,
) -> tuple[list[LedgerTrade], dict[str, Any]]:
    import pandas as pd

    if not layout.r51_trade_log.exists():
        raise RuntimeError(f"missing canonical R5.1 trade log: {layout.r51_trade_log}")

    trade_log = pd.read_parquet(layout.r51_trade_log)
    if len(trade_log) == 0:
        return [], {"canonical_trade_rows": 0, "outcome_rows": 0, "trades": 0}
    trade_log["timestamp"] = normalize_ts(trade_log["timestamp"])
    trade_log = trade_log.sort_values(["expected_seq", "timestamp"]).copy()

    outcome_log = readpq(layout.r51_outcome_log)
    outcome_by_id: dict[str, dict[str, Any]] = {}
    if len(outcome_log):
        for row in outcome_log.to_dict(orient="records"):
            outcome_by_id[str(row["trade_id"])] = row

    symbols = sorted(set(trade_log["selected_symbol"].astype(str)))
    price_maps = {symbol: load_price_map(layout, symbol) for symbol in symbols}

    result: list[LedgerTrade] = []
    for row in trade_log.to_dict(orient="records"):
        original_trade_id = str(row["trade_id"])
        symbol = str(row["selected_symbol"])
        seq = int(row["expected_seq"])
        exit_seq = int(row["expected_exit_seq"])
        weight = float(row["position_weight"])
        score = float(row["score"]) if row.get("score") is not None else None
        prices = price_maps[symbol]
        if seq not in prices:
            raise RuntimeError(f"missing forward canonical entry price: {symbol} seq={seq}")

        entry_time, entry_price = prices[seq]
        exit_time: datetime | None = None
        exit_price: float | None = None
        raw_return: float | None = None
        gross: float | None = None
        net10: float | None = None

        if exit_seq in prices:
            exit_time, exit_price = prices[exit_seq]
            raw_return = exit_price / entry_price - 1.0
            gross = weight * raw_return
            net10 = gross - weight * COST_BPS / 10000.0

        outcome = outcome_by_id.get(original_trade_id)
        if outcome is not None and outcome.get("net10_return") is not None:
            canonical_net = float(outcome["net10_return"])
            if net10 is not None and abs(canonical_net - net10) > 1e-10:
                raise RuntimeError(
                    f"forward outcome mismatch {original_trade_id}: "
                    f"log={canonical_net} reconstructed={net10}"
                )
            net10 = canonical_net
            if outcome.get("gross_return") is not None:
                gross = float(outcome["gross_return"])
            if exit_time is None:
                raise RuntimeError(
                    f"matured outcome exists without +4 canonical exit: {original_trade_id}"
                )

        result.append(
            LedgerTrade(
                trade_id=deterministic_trade_uuid(
                    FORWARD_PROVENANCE, original_trade_id
                ),
                original_trade_id=original_trade_id,
                symbol=symbol,
                entry_time=entry_time,
                entry_price=entry_price,
                exit_time=exit_time,
                exit_price=exit_price,
                return_pct=net10,
                raw_return=raw_return,
                gross_weighted_return=gross,
                net10_return=net10,
                position_weight=weight,
                expected_seq=seq,
                expected_exit_seq=exit_seq,
                score=score,
                model_freeze_sha256=str(
                    row.get("model_freeze_sha256") or freeze_sha
                ),
                ledger_type=FORWARD_LEDGER_TYPE,
                provenance=FORWARD_PROVENANCE,
                prospective=True,
                in_sample_warning=False,
            )
        )

    return result, {
        "canonical_trade_rows": len(trade_log),
        "outcome_rows": len(outcome_log),
        "trades": len(result),
        "closed": sum(x.exit_time is not None for x in result),
        "open": sum(x.exit_time is None for x in result),
    }


def compound_return(trades: list[LedgerTrade]) -> float | None:
    closed = [x.return_pct for x in trades if x.return_pct is not None]
    if not closed:
        return None
    multiple = 1.0
    for ret in closed:
        multiple *= 1.0 + float(ret)
    return (multiple - 1.0) * 100.0


def trade_payload(trade: LedgerTrade) -> dict[str, Any]:
    return {
        "trade_id": str(trade.trade_id),
        "original_trade_id": trade.original_trade_id,
        "symbol": trade.symbol,
        "entry_time": trade.entry_time.isoformat(),
        "entry_price": trade.entry_price,
        "exit_time": trade.exit_time.isoformat() if trade.exit_time else None,
        "exit_price": trade.exit_price,
        "return_pct": trade.return_pct,
        "raw_return": trade.raw_return,
        "gross_weighted_return": trade.gross_weighted_return,
        "net10_return": trade.net10_return,
        "position_weight": trade.position_weight,
        "expected_seq": trade.expected_seq,
        "expected_exit_seq": trade.expected_exit_seq,
        "score": trade.score,
        "model_freeze_sha256": trade.model_freeze_sha256,
        "ledger_type": trade.ledger_type,
        "provenance": trade.provenance,
        "prospective": trade.prospective,
        "in_sample_warning": trade.in_sample_warning,
        "status": "CLOSED" if trade.exit_time else "OPEN",
        "shadow_only": True,
        "execution": False,
    }


def event_payload(trade: LedgerTrade) -> list[dict[str, Any]]:
    events = [
        {
            "trade_id": str(trade.trade_id),
            "symbol": trade.symbol,
            "time": trade.entry_time.isoformat(),
            "price": trade.entry_price,
            "signal": "BUY",
            "event_type": (
                "R5_1_FORWARD_ENTER" if trade.prospective else "R5_1_RECON_ENTER"
            ),
            "source": trade.provenance,
            "provenance": trade.provenance,
            "prospective": trade.prospective,
        }
    ]
    if trade.exit_time is not None and trade.exit_price is not None:
        events.append(
            {
                "trade_id": str(trade.trade_id),
                "symbol": trade.symbol,
                "time": trade.exit_time.isoformat(),
                "price": trade.exit_price,
                "signal": "SELL",
                "event_type": (
                    "R5_1_FORWARD_EXIT" if trade.prospective else "R5_1_RECON_EXIT"
                ),
                "source": trade.provenance,
                "provenance": trade.provenance,
                "prospective": trade.prospective,
                "exit_reason": "EXPECTED_SEQ_PLUS_4",
            }
        )
    return events


def summary_for(trades: list[LedgerTrade]) -> dict[str, Any]:
    closed = [x for x in trades if x.exit_time is not None]
    open_ = [x for x in trades if x.exit_time is None]
    returns = [float(x.return_pct) for x in closed if x.return_pct is not None]
    return {
        "trade_count": len(trades),
        "closed_count": len(closed),
        "open_count": len(open_),
        "closed_compound_return_pct": compound_return(trades),
        "closed_mean_return_pct": (
            sum(returns) / len(returns) * 100.0 if returns else None
        ),
        "open_symbols": [x.symbol for x in open_],
        "first_entry": min((x.entry_time.isoformat() for x in trades), default=None),
        "last_event": max(
            (
                (x.exit_time or x.entry_time).isoformat()
                for x in trades
            ),
            default=None,
        ),
        "return_semantics": "POSITION_WEIGHTED_NET10_DECIMAL_COMPOUNDED",
    }


def ensure_research_run(
    cur: Any,
    run_id: str,
    data_as_of: datetime | None,
    provenance: str,
    freeze_sha: str,
) -> None:
    metadata = {
        "source": "r5_annual_ledger_v1",
        "provenance": provenance,
        "shadow_only": True,
        "trade_execution": False,
        "auto_trade_visible": False,
        "dashboard_snapshot_created": False,
        "model_version": MODEL_VERSION,
        "model_freeze_sha256": freeze_sha,
        "research_only": True,
    }
    now = utcnow()
    cur.execute(
        """
        INSERT INTO pipeline_run (
            run_id,market,pipeline_version,data_as_of,feature_version,
            model_version,git_sha,started_at,completed_at,status,metadata
        ) VALUES (
            %s,'US',%s,%s,%s,%s,%s,%s,%s,'ABORTED',%s::jsonb
        )
        ON CONFLICT (run_id) DO UPDATE SET
            data_as_of=EXCLUDED.data_as_of,
            feature_version=EXCLUDED.feature_version,
            model_version=EXCLUDED.model_version,
            git_sha=EXCLUDED.git_sha,
            completed_at=EXCLUDED.completed_at,
            status='ABORTED',
            error_message=NULL,
            metadata=EXCLUDED.metadata
        """,
        (
            run_id,
            PIPELINE_VERSION,
            data_as_of,
            FEATURE_VERSION,
            MODEL_VERSION,
            os.environ.get("KALMAN_GIT_SHA") or None,
            now,
            now,
            json.dumps(metadata, separators=(",", ":")),
        ),
    )


def upsert_trade(cur: Any, trade: LedgerTrade, run_id: str) -> None:
    metadata = trade_payload(trade)
    metadata.update(
        {
            "trade_execution": False,
            "shadow_only": True,
            "execution": False,
            "exit_rule": "EXPECTED_SEQ_PLUS_4",
            "cost_bps": COST_BPS,
            "model_was_not_prospective": not trade.prospective,
            "warning": (
                "Frozen R5.1 model replay over pre-freeze data; in-sample and not OOS."
                if trade.in_sample_warning
                else None
            ),
        }
    )
    cur.execute(
        """
        INSERT INTO strategy_ledger (
            trade_id,market,symbol,strategy_version,model_version,
            entry_time,entry_price,exit_time,exit_price,return_pct,
            exit_reason,ledger_type,run_id,metadata
        ) VALUES (
            %s,'US',%s,%s,%s,%s,%s,%s,%s,%s,
            %s,%s,%s,%s::jsonb
        )
        ON CONFLICT (trade_id) DO UPDATE SET
            entry_time=EXCLUDED.entry_time,
            entry_price=EXCLUDED.entry_price,
            exit_time=EXCLUDED.exit_time,
            exit_price=EXCLUDED.exit_price,
            return_pct=EXCLUDED.return_pct,
            exit_reason=EXCLUDED.exit_reason,
            ledger_type=EXCLUDED.ledger_type,
            run_id=EXCLUDED.run_id,
            metadata=EXCLUDED.metadata
        """,
        (
            trade.trade_id,
            trade.symbol,
            STRATEGY_VERSION,
            MODEL_VERSION,
            trade.entry_time,
            trade.entry_price,
            trade.exit_time,
            trade.exit_price,
            trade.return_pct,
            "EXPECTED_SEQ_PLUS_4" if trade.exit_time else None,
            trade.ledger_type,
            run_id,
            json.dumps(metadata, separators=(",", ":")),
        ),
    )


def latest_success_map(cur: Any) -> list[tuple[Any, ...]]:
    cur.execute(
        """
        SELECT market,run_id,pipeline_version,data_as_of,model_version,completed_at
        FROM v_latest_successful_run
        WHERE market='US'
        ORDER BY market
        """
    )
    return list(cur.fetchall())


def write_db(
    database_url: str,
    replay: list[LedgerTrade],
    forward: list[LedgerTrade],
    freeze_sha: str,
    replace_legacy_live: bool,
) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('r5_annual_ledger_v1'))")
            before = latest_success_map(cur)

            if replay:
                ensure_research_run(
                    cur,
                    REPLAY_RUN_ID,
                    max(x.exit_time or x.entry_time for x in replay),
                    REPLAY_PROVENANCE,
                    freeze_sha,
                )
                for trade in replay:
                    upsert_trade(cur, trade, REPLAY_RUN_ID)

            if forward:
                ensure_research_run(
                    cur,
                    FORWARD_IMPORT_RUN_ID,
                    max(x.exit_time or x.entry_time for x in forward),
                    FORWARD_PROVENANCE,
                    freeze_sha,
                )
                for trade in forward:
                    upsert_trade(cur, trade, FORWARD_IMPORT_RUN_ID)

            legacy_deleted = 0
            if replace_legacy_live:
                keep_ids = [x.trade_id for x in forward]
                cur.execute(
                    """
                    DELETE FROM strategy_ledger
                    WHERE market='US'
                      AND model_version=%s
                      AND ledger_type='LIVE_SHADOW'
                      AND COALESCE(metadata->>'provenance','') <> %s
                      AND COALESCE(metadata->>'lifecycle','')='R5.1_SHADOW_SELECTOR'
                      AND NOT (trade_id = ANY(%s))
                    """,
                    (MODEL_VERSION, FORWARD_PROVENANCE, keep_ids or [uuid.UUID(int=0)]),
                )
                legacy_deleted = int(cur.rowcount)

            after = latest_success_map(cur)
            if before != after:
                raise RuntimeError(
                    f"research ledger changed v_latest_successful_run: before={before} after={after}"
                )

            for run_id in (REPLAY_RUN_ID, FORWARD_IMPORT_RUN_ID):
                cur.execute(
                    """
                    SELECT status,metadata
                    FROM pipeline_run
                    WHERE run_id=%s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                if row is None:
                    continue
                status, metadata = row
                if status != "ABORTED":
                    raise RuntimeError(f"{run_id} must stay ABORTED")
                if (metadata or {}).get("auto_trade_visible") is not False:
                    raise RuntimeError(f"{run_id} auto_trade_visible safety mismatch")

                cur.execute(
                    "SELECT count(*) FROM dashboard_snapshot WHERE run_id=%s",
                    (run_id,),
                )
                if int(cur.fetchone()[0]) != 0:
                    raise RuntimeError(f"{run_id} unexpectedly has dashboard_snapshot")

                cur.execute(
                    "SELECT count(*) FROM strategy_signal WHERE run_id=%s",
                    (run_id,),
                )
                if int(cur.fetchone()[0]) != 0:
                    raise RuntimeError(f"{run_id} unexpectedly has strategy_signal")

        conn.commit()

    return {
        "replay_rows": len(replay),
        "forward_rows": len(forward),
        "legacy_live_deleted": legacy_deleted,
    }


def fetch_annual_from_db(cur: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cur.execute(
        """
        SELECT trade_id,symbol,entry_time,entry_price,exit_time,exit_price,
               return_pct,ledger_type,metadata
        FROM strategy_ledger
        WHERE market='US'
          AND model_version=%s
          AND (
            (ledger_type='BACKTEST' AND metadata->>'provenance'=%s)
            OR
            (ledger_type='LIVE_SHADOW' AND metadata->>'provenance'=%s)
          )
        ORDER BY entry_time
        """,
        (MODEL_VERSION, REPLAY_PROVENANCE, FORWARD_PROVENANCE),
    )

    replay: list[dict[str, Any]] = []
    forward: list[dict[str, Any]] = []
    for (
        trade_id,
        symbol,
        entry_time,
        entry_price,
        exit_time,
        exit_price,
        return_pct,
        ledger_type,
        metadata,
    ) in cur.fetchall():
        m = dict(metadata or {})
        row = {
            **m,
            "trade_id": str(trade_id),
            "symbol": symbol,
            "entry_time": entry_time.isoformat(),
            "entry_price": float(entry_price),
            "exit_time": exit_time.isoformat() if exit_time else None,
            "exit_price": float(exit_price) if exit_price is not None else None,
            "return_pct": float(return_pct) if return_pct is not None else None,
            "ledger_type": ledger_type,
            "status": "CLOSED" if exit_time else "OPEN",
            "shadow_only": True,
            "execution": False,
        }
        if m.get("provenance") == REPLAY_PROVENANCE:
            replay.append(row)
        elif m.get("provenance") == FORWARD_PROVENANCE:
            forward.append(row)

    return replay, forward


def dict_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closed = [x for x in rows if x.get("exit_time") and x.get("return_pct") is not None]
    open_ = [x for x in rows if not x.get("exit_time")]
    multiple = 1.0
    for row in closed:
        multiple *= 1.0 + float(row["return_pct"])
    returns = [float(x["return_pct"]) for x in closed]
    return {
        "trade_count": len(rows),
        "closed_count": len(closed),
        "open_count": len(open_),
        "closed_compound_return_pct": (multiple - 1.0) * 100.0 if closed else None,
        "closed_mean_return_pct": (
            sum(returns) / len(returns) * 100.0 if returns else None
        ),
        "open_symbols": [x["symbol"] for x in open_],
        "first_entry": min((x["entry_time"] for x in rows), default=None),
        "last_event": max(
            ((x.get("exit_time") or x["entry_time"]) for x in rows),
            default=None,
        ),
        "return_semantics": "POSITION_WEIGHTED_NET10_DECIMAL_COMPOUNDED",
    }


def dict_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for row in rows:
        prospective = bool(row.get("prospective"))
        provenance = str(row.get("provenance") or "")
        events.append(
            {
                "trade_id": row["trade_id"],
                "symbol": row["symbol"],
                "time": row["entry_time"],
                "price": row["entry_price"],
                "signal": "BUY",
                "event_type": (
                    "R5_1_FORWARD_ENTER" if prospective else "R5_1_RECON_ENTER"
                ),
                "source": provenance,
                "provenance": provenance,
                "prospective": prospective,
            }
        )
        if row.get("exit_time") and row.get("exit_price") is not None:
            events.append(
                {
                    "trade_id": row["trade_id"],
                    "symbol": row["symbol"],
                    "time": row["exit_time"],
                    "price": row["exit_price"],
                    "signal": "SELL",
                    "event_type": (
                        "R5_1_FORWARD_EXIT" if prospective else "R5_1_RECON_EXIT"
                    ),
                    "source": provenance,
                    "provenance": provenance,
                    "prospective": prospective,
                    "exit_reason": "EXPECTED_SEQ_PLUS_4",
                }
            )
    return sorted(events, key=lambda x: (x["time"], x["symbol"], x["signal"]))


def publish_dashboard(database_url: str) -> dict[str, Any]:
    import psycopg

    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT pg_advisory_xact_lock(hashtext('r5_annual_dashboard_v1'))")
            replay, forward = fetch_annual_from_db(cur)
            if not forward:
                raise RuntimeError("canonical Forward SHADOW ledger is empty")

            # Backward-compatible top level: v7.4.13 continues to see Forward
            # SHADOW only. v7.4.14+ can consume annual_2026.
            forward_summary = dict_summary(forward)
            annual_rows = sorted(replay + forward, key=lambda x: x["entry_time"])
            annual = {
                "schema_version": "r5-annual-2026-v0.1",
                "calendar_year": 2026,
                "reconstructed_boundary": R51_START,
                "official_ytd": False,
                "warning": (
                    "2026-01-01 through the R5.1 freeze boundary is a frozen-model "
                    "reconstruction over pre-freeze training-era data. It is not OOS "
                    "and must not be reported as prospective performance."
                ),
                "reconstructed": {
                    "provenance": REPLAY_PROVENANCE,
                    "in_sample_warning": True,
                    "summary": dict_summary(replay),
                },
                "forward": {
                    "provenance": FORWARD_PROVENANCE,
                    "prospective": True,
                    "summary": forward_summary,
                },
                "trades": annual_rows,
                "events": dict_events(annual_rows),
            }
            payload = {
                "schema_version": "r5-shadow-lifecycle-v0.2",
                "model_version": MODEL_VERSION,
                "strategy_version": STRATEGY_VERSION,
                "ledger_type": FORWARD_LEDGER_TYPE,
                "shadow_only": True,
                "execution": False,
                "generated_at": utcnow().isoformat(),
                "summary": forward_summary,
                "trades": forward,
                "events": dict_events(forward),
                "annual_2026": annual,
            }

            cur.execute(
                """
                SELECT snapshot_id,run_id
                FROM dashboard_snapshot
                WHERE market='US'
                  AND status='READY'
                  AND model_version=%s
                ORDER BY generated_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (MODEL_VERSION,),
            )
            row = cur.fetchone()
            if not row:
                raise RuntimeError("latest R5.1 US dashboard snapshot not found")
            snapshot_id, run_id = row
            cur.execute(
                """
                UPDATE dashboard_snapshot
                SET payload=jsonb_set(
                    payload,
                    '{source_payload,r5_shadow_ledger}',
                    %s::jsonb,
                    true
                )
                WHERE snapshot_id=%s
                """,
                (json.dumps(payload, separators=(",", ":")), snapshot_id),
            )
            if cur.rowcount != 1:
                raise RuntimeError("R5.1 annual dashboard update failed")

        conn.commit()

    return {
        "dashboard_run_id": str(run_id),
        "replay_trades": len(replay),
        "forward_trades": len(forward),
        "annual_events": len(annual["events"]),
        "forward_events": len(payload["events"]),
    }


def resolve_database_url() -> str:
    value = (
        os.environ.get("DATABASE_URL_WRITER")
        or os.environ.get("DATABASE_URL")
        or os.environ.get("NEON_DATABASE_URL")
    )
    if not value:
        raise RuntimeError(
            "DATABASE_URL_WRITER/DATABASE_URL/NEON_DATABASE_URL is required"
        )
    return value


def main() -> int:
    args = parse_args()
    load_dotenv(
        os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env"),
        override=True,
    )

    us_root = locate_us_root(args.us_root)
    layout = build_layout(us_root)
    freeze, freeze_sha = verify_freeze(layout)
    symbols = load_symbols(layout)

    replay: list[LedgerTrade] = []
    forward: list[LedgerTrade] = []
    replay_stats: dict[str, Any] = {}
    forward_stats: dict[str, Any] = {}

    if args.mode in {"full", "replay"}:
        print(f"[R5-2026] building reconstructed panel from {us_root}")
        panel = build_replay_panel(layout, symbols, args.start, args.replay_end)
        replay, replay_stats = build_reconstructed_trades(
            layout,
            panel,
            args.start,
            args.replay_end,
            freeze_sha,
        )

    if args.mode in {"full", "forward"}:
        print("[R5-2026] importing canonical Forward SHADOW trade/outcome logs")
        forward, forward_stats = build_forward_trades(layout, freeze_sha)

    report = {
        "status": "VALIDATED",
        "mode": args.mode,
        "us_root": str(us_root),
        "model_version": MODEL_VERSION,
        "freeze_sha256": freeze_sha,
        "freeze_train_rows": freeze.get("train_rows"),
        "prospective_start": freeze.get("prospective_start"),
        "replay_period": {
            "start": args.start,
            "end": args.replay_end,
            "provenance": REPLAY_PROVENANCE,
            "in_sample_warning": True,
        },
        "replay": {
            **replay_stats,
            "summary": summary_for(replay),
        },
        "forward": {
            **forward_stats,
            "summary": summary_for(forward),
        },
        "safety": {
            "execution": False,
            "shadow_only": True,
            "trading_enabled_changed": False,
            "auto_trade_visible": False,
        },
    }

    if args.output_json:
        Path(args.output_json).write_text(
            json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))

    if not args.write_db:
        print("R5_2026_LEDGER_DRY_RUN_COMPLETE")
        return 0

    database_url = resolve_database_url()
    db_result = write_db(
        database_url,
        replay,
        forward,
        freeze_sha,
        args.replace_legacy_live,
    )
    print(json.dumps({"db_write": db_result}, indent=2))

    if args.publish_dashboard:
        dashboard_result = publish_dashboard(database_url)
        print(json.dumps({"dashboard": dashboard_result}, indent=2))

    print("R5_2026_LEDGER_SYNC_COMPLETE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
