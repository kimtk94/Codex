from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from r8_1_sec_ablation import BASE_FEATURES
from r9_news_features import NEWS_FEATURES, attach_news_features, build_daily_features

SCHEMA = "kalman-r9-2-prospective-shadow-v1"
CANDIDATE = "R9P_NGRAM_ATTENTION_FROZEN"
PROSPECTIVE_START = pd.Timestamp("2026-09-24T13:30:00Z")
COST_BPS = 10
MIN_COVERAGE = 90
TAIL_BARS = 160
B = 2000
BLOCK_DAYS = 5
RNG_SEED = 20260924
NEON_CONFIRM = "CONFIRM_R9_2_SHADOW_NEON"


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run frozen R9.2 forward-only shadow")
    root = Path(os.getenv("KALMAN_DATA_ROOT", "/mnt/gdrive"))
    state = Path(
        os.getenv(
            "R9_NEWS_STATE_DIR",
            str(Path.home() / ".local/state/kalman/r9_news_ngram"),
        )
    )
    p.add_argument("--root", default=str(root))
    p.add_argument(
        "--news-history",
        default=str(state / "r9_ngram_shadow_history.csv"),
    )
    p.add_argument(
        "--source-state",
        default=str(state / "r9_shadow_source_state.json"),
    )
    p.add_argument("--write-neon", action="store_true")
    return p.parse_args()


def nowiso() -> str:
    return datetime.now(timezone.utc).isoformat()


def nts(x: Any) -> pd.Series:
    return pd.to_datetime(x, utc=True, errors="coerce")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def stable_hash(obj: Any) -> str:
    raw = json.dumps(
        obj, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    return hashlib.sha256(raw).hexdigest()


def readpq(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path) if path.exists() else pd.DataFrame()


def atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def append_event(path: Path, event: str, **kw: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    rec = {"at_utc": nowiso(), "event": event, **kw}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    print("[R9.2]", event, kw)


def append_immutable(
    path: Path,
    new: pd.DataFrame,
    key: str,
    hash_col: str,
) -> tuple[pd.DataFrame, int]:
    old = readpq(path)
    if new.empty:
        return old, 0
    new = new.copy()
    if new[key].duplicated().any():
        raise RuntimeError(f"duplicate new {key}")
    if not old.empty:
        if old[key].duplicated().any():
            raise RuntimeError(f"duplicate existing {key}")
        overlap = new.merge(
            old[[key, hash_col]],
            on=key,
            how="inner",
            suffixes=("_new", "_old"),
        )
        if len(overlap):
            if not (
                overlap[f"{hash_col}_new"] == overlap[f"{hash_col}_old"]
            ).all():
                raise RuntimeError(f"immutable ledger mismatch for {key}")
        new = new.loc[~new[key].isin(old[key])]
    out = pd.concat([old, new], ignore_index=True)
    atomic_parquet(out, path)
    return out, len(new)


def max_drawdown(r: np.ndarray) -> float | None:
    r = np.asarray(r, float)
    if len(r) == 0:
        return None
    eq = np.r_[1.0, np.cumprod(1.0 + r)]
    peak = np.maximum.accumulate(eq)
    return float(np.min(eq / peak - 1.0))


def moving_block_indices(n: int, rng: np.random.Generator) -> np.ndarray:
    if n <= 0:
        return np.array([], dtype=np.int32)
    if n <= BLOCK_DAYS:
        return rng.integers(0, n, size=n, dtype=np.int32)
    starts = np.arange(n - BLOCK_DAYS + 1, dtype=np.int32)
    nb = int(np.ceil(n / BLOCK_DAYS))
    selected = rng.choice(starts, size=nb, replace=True)
    return (
        selected[:, None] + np.arange(BLOCK_DAYS)[None, :]
    ).ravel()[:n].astype(np.int32)


def verify_freeze(manifest_path: Path) -> dict:
    if not manifest_path.exists():
        raise FileNotFoundError(manifest_path)
    m = json.loads(manifest_path.read_text(encoding="utf-8"))
    if m.get("schema") != "kalman-r9-2-prospective-model-freeze-v1":
        raise RuntimeError("unexpected R9.2 model freeze schema")
    if m.get("candidate") != CANDIDATE:
        raise RuntimeError("R9.2 candidate drift")
    if pd.Timestamp(m["prospective_start"]) != PROSPECTIVE_START:
        raise RuntimeError("R9.2 prospective start drift")
    if m.get("refit_allowed") is not False:
        raise RuntimeError("R9.2 refit invariant violated")
    if list(m.get("features") or []) != list(BASE_FEATURES) + list(NEWS_FEATURES):
        raise RuntimeError("R9.2 feature contract drift")
    for name, expected in (m.get("artifacts") or {}).items():
        p = manifest_path.parent / name
        if not p.exists() or sha256_file(p) != expected:
            raise RuntimeError(f"R9.2 frozen artifact mismatch: {name}")
    return m


def grid_feature_frame(obs: pd.DataFrame) -> pd.DataFrame:
    obs = obs.copy().sort_values("expected_seq")
    lo = int(obs["expected_seq"].min())
    hi = int(obs["expected_seq"].max())
    g = pd.DataFrame({"expected_seq": np.arange(lo, hi + 1, dtype=np.int64)})
    cols = [
        c
        for c in [
            "expected_seq", "timestamp", "session_date", "market_open_utc",
            "session_bucket", "open", "high", "low", "close", "volume",
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
    return g.loc[g["close"].notna()].copy()


def load_locked_symbol(src_panel: Path, sym: str) -> pd.DataFrame:
    p = src_panel / f"{sym}_1h_gap_aware.parquet"
    if not p.exists():
        raise FileNotFoundError(p)
    z = pd.read_parquet(p)
    if "timestamp" in z.columns:
        z["timestamp"] = nts(z["timestamp"])
    else:
        z["market_open_utc"] = nts(z["market_open_utc"])
        z["timestamp"] = z["market_open_utc"] + pd.to_timedelta(
            pd.to_numeric(z["session_bucket"], errors="raise").astype(int),
            unit="h",
        )
    z["expected_seq"] = pd.to_numeric(
        z["expected_seq"], errors="raise"
    ).astype("int64")
    z["symbol"] = sym
    return z.sort_values("expected_seq").tail(TAIL_BARS).copy()


def combined_symbol(
    src_panel: Path,
    live_1h: Path,
    sym: str,
) -> pd.DataFrame:
    locked = load_locked_symbol(src_panel, sym)
    live = readpq(live_1h / f"{sym}_1h_live.parquet")
    if len(live):
        live["timestamp"] = nts(live["timestamp"])
        live["expected_seq"] = pd.to_numeric(
            live["expected_seq"], errors="raise"
        ).astype("int64")
        live["symbol"] = sym
        live = live.loc[live["timestamp"] > locked["timestamp"].max()]
    return (
        pd.concat([locked, live], ignore_index=True)
        .sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
    )


def build_live_panel(us: Path, symbols: list[str]) -> tuple[pd.DataFrame, pd.Timestamp]:
    src = us / "directional_research/canonical_history_v1"
    src_panel = src / "panel_1h_gap_aware"
    src_qqq = src / "qqq_context/history_1h/QQQ_1h_gap_aware.parquet"
    live = us / "directional_research/r4_live_canonical_v1"
    live_1h = live / "panel_1h_overlay"
    live_qqq = live / "qqq_context"

    locked_q = pd.read_parquet(src_qqq)
    if "timestamp" in locked_q.columns:
        locked_q["timestamp"] = nts(locked_q["timestamp"])
    else:
        locked_q["market_open_utc"] = nts(locked_q["market_open_utc"])
        locked_q["timestamp"] = locked_q["market_open_utc"] + pd.to_timedelta(
            pd.to_numeric(locked_q["session_bucket"], errors="raise").astype(int),
            unit="h",
        )
    locked_q["expected_seq"] = pd.to_numeric(
        locked_q["expected_seq"], errors="raise"
    ).astype("int64")
    locked_q = (
        locked_q.sort_values("expected_seq")
        .drop_duplicates("expected_seq")
        .tail(TAIL_BARS)
        .copy()
    )
    live_q = readpq(live_qqq / "QQQ_1h_live.parquet")
    if len(live_q):
        live_q["timestamp"] = nts(live_q["timestamp"])
        live_q["expected_seq"] = pd.to_numeric(
            live_q["expected_seq"], errors="raise"
        ).astype("int64")
        live_q = live_q.loc[live_q["timestamp"] > locked_q["timestamp"].max()]
    qqq = (
        pd.concat([locked_q, live_q], ignore_index=True)
        .sort_values("expected_seq")
        .drop_duplicates("expected_seq", keep="first")
    )
    source_max = pd.Timestamp(qqq["timestamp"].max())

    qbase = grid_feature_frame(qqq)
    qcols = {
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
    qctx = qbase[["expected_seq", *qcols.keys()]].rename(columns=qcols)

    parts = []
    for sym in symbols:
        b = grid_feature_frame(combined_symbol(src_panel, live_1h, sym))
        b["symbol"] = sym
        b = b.merge(qctx, on="expected_seq", how="left", validate="one_to_one")
        b["timestamp"] = nts(b["timestamp"])
        parts.append(b)

    panel = (
        pd.concat(parts, ignore_index=True)
        .sort_values(["symbol", "expected_seq"])
        .reset_index(drop=True)
    )

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

    g = panel.groupby("timestamp")
    for col in [
        "ret_1b", "ret_2b", "ret_4b", "ret_6b", "rv_6", "rv_24",
        "ma_dist_6", "ma_dist_24", "volume_z_24", "bar_range",
        "beta24", "residual_ret_6b",
    ]:
        panel["cs_" + col] = g[col].rank(pct=True, method="average")

    panel["universe_median_rv_24"] = g["rv_24"].transform("median")
    panel["universe_mean_fwd_ret_4b"] = g["fwd_ret_4b"].transform("mean")
    panel["ix_trend_qqq"] = panel["ma_dist_24"] * panel["qqq_ma_dist_24"]
    panel["ix_vol_qqq"] = panel["rv_24"] * panel["qqq_rv_24"]
    panel["ix_ret1_qqq"] = panel["ret_1b"] * panel["qqq_ret_2b"]
    panel["ix_mom6_qqq"] = panel["ret_6b"] * panel["qqq_ret_6b"]

    qclose = qqq.set_index("expected_seq")["close"]
    qfwd = {}
    for s in qqq["expected_seq"]:
        s = int(s)
        a = qclose.get(s, np.nan)
        b = qclose.get(s + 4, np.nan)
        qfwd[s] = (
            float(b / a - 1)
            if np.isfinite(a) and np.isfinite(b)
            else np.nan
        )
    panel["qqq_fwd_ret_4b"] = panel["expected_seq"].map(qfwd)
    panel = panel.replace([np.inf, -np.inf], np.nan)
    return panel, source_max


def reconcile_features(us: Path, panel: pd.DataFrame, symbols: list[str]) -> dict:
    r1 = us / "directional_research/r1_directional_v1_2/primary_train"
    cols = [
        "ret_1b", "ret_2b", "ret_4b", "ret_6b", "bar_range", "rv_6",
        "rv_24", "ma_dist_6", "ma_dist_24", "volume_z_24",
        "qqq_ret_1b", "qqq_ret_2b", "qqq_ret_4b", "qqq_ret_6b",
        "qqq_rv_6", "qqq_rv_24", "qqq_ma_dist_6", "qqq_ma_dist_24",
    ]
    diffs: list[float] = []
    agree: list[bool] = []
    rows = 0
    for sym in symbols:
        p = r1 / f"{sym}_r1.parquet"
        if not p.exists():
            continue
        old = pd.read_parquet(p)
        old["expected_seq"] = pd.to_numeric(
            old["expected_seq"], errors="coerce"
        )
        old = old.loc[old["expected_seq"].notna()].copy()
        old["expected_seq"] = old["expected_seq"].astype("int64")
        tail = old.sort_values("expected_seq").tail(100)
        new = panel.loc[
            (panel["symbol"] == sym)
            & panel["expected_seq"].isin(tail["expected_seq"]),
            ["expected_seq", *cols],
        ]
        m = tail[["expected_seq", *[c for c in cols if c in tail.columns]]].merge(
            new,
            on="expected_seq",
            how="inner",
            suffixes=("_old", "_new"),
        )
        rows += len(m)
        for col in cols:
            a = col + "_old"
            b = col + "_new"
            if a not in m.columns or b not in m.columns:
                continue
            x = pd.to_numeric(m[a], errors="coerce").to_numpy(float)
            y = pd.to_numeric(m[b], errors="coerce").to_numpy(float)
            both = np.isfinite(x) & np.isfinite(y)
            if both.any():
                diffs.extend(np.abs(x[both] - y[both]).tolist())
            agree.extend((np.isfinite(x) == np.isfinite(y)).tolist())

    audit = {
        "rows_compared": int(rows),
        "median_abs_diff": float(np.median(diffs)) if diffs else None,
        "finite_agreement": float(np.mean(agree)) if agree else None,
    }
    audit["pass"] = bool(
        rows > 5000
        and audit["median_abs_diff"] is not None
        and audit["median_abs_diff"] <= 1e-10
        and audit["finite_agreement"] is not None
        and audit["finite_agreement"] >= 0.999
    )
    if not audit["pass"]:
        raise RuntimeError(f"R9.2 canonical feature reconciliation failed: {audit}")
    return audit


def build_news_daily(
    history_path: Path,
    symbols: list[str],
    last_complete_day: pd.Timestamp,
) -> pd.DataFrame:
    if not history_path.exists():
        raise FileNotFoundError(history_path)
    hist = pd.read_csv(history_path)
    if hist.empty:
        raise RuntimeError("R9.2 news history is empty")
    days = pd.to_datetime(
        hist["day_utc"].astype("int64").astype(str),
        format="%Y%m%d",
        utc=True,
        errors="raise",
    )
    start = days.min()
    return build_daily_features(
        hist[["symbol", "day_utc", "mention_count"]],
        symbols,
        history_start=start,
        history_end_exclusive=last_complete_day + pd.Timedelta(1, unit="D"),
    )


def load_source_state(path: Path) -> tuple[dict, pd.Timestamp]:
    if not path.exists():
        raise FileNotFoundError(path)
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("status") != "READY":
        raise RuntimeError(f"R9.2 NGram source not READY: {state.get('status')}")
    day = pd.Timestamp(state["last_complete_day"], tz="UTC")
    return state, day


def _jsonable_record(row: pd.Series) -> dict:
    out = {}
    for k, v in row.to_dict().items():
        if isinstance(v, pd.Timestamp):
            out[k] = v.isoformat()
        elif isinstance(v, np.generic):
            out[k] = v.item()
        elif pd.isna(v):
            out[k] = None
        else:
            out[k] = v
    return out


def write_neon(
    signals: pd.DataFrame,
    trades: pd.DataFrame,
    outcomes: pd.DataFrame,
) -> None:
    if os.getenv("KALMAN_R9_2_SHADOW_NEON_ENABLED", "").lower() != "true":
        raise RuntimeError("KALMAN_R9_2_SHADOW_NEON_ENABLED=true required")
    if os.getenv("KALMAN_R9_2_SHADOW_NEON_CONFIRM") != NEON_CONFIRM:
        raise RuntimeError(
            f"KALMAN_R9_2_SHADOW_NEON_CONFIRM={NEON_CONFIRM} required"
        )

    env_file = os.getenv("KALMAN_ENV_FILE", "/opt/kalman/.env")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except Exception:
        pass
    url = os.getenv("DATABASE_URL_WRITER") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_WRITER is required")

    import psycopg
    from psycopg.types.json import Jsonb

    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            expected = [
                "research.r9_shadow_signal",
                "research.r9_shadow_trade_entry",
                "research.r9_shadow_outcome",
            ]
            for table in expected:
                cur.execute("SELECT to_regclass(%s)", (table,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError(f"missing Neon table: {table}")

            for _, r in signals.iterrows():
                cur.execute(
                    """
                    INSERT INTO research.r9_shadow_signal (
                        signal_id, signal_as_of, expected_seq, expected_exit_seq,
                        selected_symbol, score, position_weight, universe_coverage,
                        news_day_used, model_sha256, r5_selected_symbol, r5_score,
                        top1_agree, score_spearman, top10_overlap, payload, created_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                    ON CONFLICT (signal_id) DO NOTHING
                    """,
                    (
                        r["signal_id"],
                        pd.Timestamp(r["signal_as_of"]).to_pydatetime(),
                        int(r["expected_seq"]),
                        int(r["expected_exit_seq"]),
                        r["selected_symbol"],
                        float(r["score"]),
                        float(r["position_weight"]),
                        int(r["universe_coverage"]),
                        pd.Timestamp(r["news_day_used"]).date(),
                        r["model_sha256"],
                        r.get("r5_selected_symbol"),
                        (
                            float(r["r5_score"])
                            if pd.notna(r.get("r5_score")) else None
                        ),
                        (
                            bool(r["top1_agree"])
                            if pd.notna(r.get("top1_agree")) else None
                        ),
                        (
                            float(r["score_spearman"])
                            if pd.notna(r.get("score_spearman")) else None
                        ),
                        (
                            int(r["top10_overlap"])
                            if pd.notna(r.get("top10_overlap")) else None
                        ),
                        Jsonb(_jsonable_record(r)),
                    ),
                )

            for _, r in trades.iterrows():
                cur.execute(
                    """
                    INSERT INTO research.r9_shadow_trade_entry (
                        trade_id, signal_id, signal_as_of, expected_seq,
                        expected_exit_seq, selected_symbol, score,
                        position_weight, model_sha256, payload, created_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                    ON CONFLICT (trade_id) DO NOTHING
                    """,
                    (
                        r["trade_id"], r["signal_id"],
                        pd.Timestamp(r["signal_as_of"]).to_pydatetime(),
                        int(r["expected_seq"]), int(r["expected_exit_seq"]),
                        r["selected_symbol"], float(r["score"]),
                        float(r["position_weight"]), r["model_sha256"],
                        Jsonb(_jsonable_record(r)),
                    ),
                )

            for _, r in outcomes.iterrows():
                cur.execute(
                    """
                    INSERT INTO research.r9_shadow_outcome (
                        trade_id, signal_as_of, entry_day, expected_seq,
                        expected_exit_seq, selected_symbol, net10_return,
                        matched_qqq_net10_return, matched_universe_net10_return,
                        log_excess_vs_qqq, log_excess_vs_universe,
                        r5_selected_symbol, r5_net10_return,
                        paired_log_diff_r9_minus_r5, payload, created_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                    ON CONFLICT (trade_id) DO NOTHING
                    """,
                    (
                        r["trade_id"],
                        pd.Timestamp(r["signal_as_of"]).to_pydatetime(),
                        pd.Timestamp(r["entry_date"]).date(),
                        int(r["expected_seq"]), int(r["expected_exit_seq"]),
                        r["selected_symbol"], float(r["net10_return"]),
                        float(r["matched_qqq_net10_return"]),
                        float(r["matched_universe_net10_return"]),
                        float(r["log_excess_vs_qqq"]),
                        float(r["log_excess_vs_universe"]),
                        r.get("r5_selected_symbol"),
                        (
                            float(r["r5_net10_return"])
                            if pd.notna(r.get("r5_net10_return")) else None
                        ),
                        (
                            float(r["paired_log_diff_r9_minus_r5"])
                            if pd.notna(r.get("paired_log_diff_r9_minus_r5"))
                            else None
                        ),
                        Jsonb(_jsonable_record(r)),
                    ),
                )
        conn.commit()


def metrics(outcomes: pd.DataFrame) -> dict:
    if outcomes.empty:
        return {
            "outcomes": 0,
            "distinct_days": 0,
            "net10_cum_return": None,
            "net10_mdd": None,
            "hit_rate": None,
            "log_excess_vs_qqq": None,
            "log_excess_vs_universe": None,
            "paired_log_diff_r9_minus_r5": None,
        }
    z = outcomes.sort_values(["expected_seq", "signal_as_of"]).copy()
    r = pd.to_numeric(z["net10_return"], errors="raise").to_numpy(float)
    paired = pd.to_numeric(
        z["paired_log_diff_r9_minus_r5"], errors="coerce"
    )
    return {
        "outcomes": int(len(z)),
        "distinct_days": int(pd.to_datetime(z["entry_date"], utc=True).nunique()),
        "net10_cum_return": float(np.prod(1 + r) - 1),
        "net10_mdd": max_drawdown(r),
        "hit_rate": float((r > 0).mean()),
        "log_excess_vs_qqq": float(z["log_excess_vs_qqq"].sum()),
        "log_excess_vs_universe": float(z["log_excess_vs_universe"].sum()),
        "paired_log_diff_r9_minus_r5": (
            float(paired.dropna().sum()) if paired.notna().any() else None
        ),
    }


def paired_bootstrap(outcomes: pd.DataFrame) -> dict | None:
    z = outcomes.loc[
        pd.to_numeric(
            outcomes["paired_log_diff_r9_minus_r5"], errors="coerce"
        ).notna()
    ].copy()
    if z.empty:
        return None
    days = int(pd.to_datetime(z["entry_date"], utc=True).nunique())
    if len(z) < 100 or days < 60:
        return None

    z["entry_date"] = pd.to_datetime(z["entry_date"], utc=True).dt.floor("D")
    daily = (
        z.groupby("entry_date")["paired_log_diff_r9_minus_r5"]
        .sum()
        .sort_index()
    )
    arr = daily.to_numpy(float)
    rng = np.random.default_rng(RNG_SEED)
    vals = np.empty(B, float)
    for i in range(B):
        vals[i] = float(arr[moving_block_indices(len(arr), rng)].mean())

    return {
        "replicates": B,
        "block_days": BLOCK_DAYS,
        "paired_outcomes": int(len(z)),
        "distinct_days": int(len(arr)),
        "mean_daily_log_diff_r9_minus_r5": float(arr.mean()),
        "ci95_low": float(np.quantile(vals, 0.025)),
        "ci95_high": float(np.quantile(vals, 0.975)),
        "p_one_sided_r9_gt_r5": float((np.sum(vals <= 0) + 1) / (B + 1)),
    }


def main() -> int:
    a = parse_args()
    root = Path(a.root)
    us = root / "US_ETF"

    out = us / "model_lab_v1/results/r9_2_prospective_shadow"
    freeze_dir = out / "model_freeze"
    out.mkdir(parents=True, exist_ok=True)

    manifest_path = freeze_dir / "r9_2_model_freeze_manifest.json"
    model_path = freeze_dir / "r9_2_hgb.joblib"
    medians_path = freeze_dir / "r9_2_training_medians.json"

    r501 = us / "model_lab_v1/results/r5_0_1_research_sandbox_all_data"
    r5_manifest_path = r501 / "model_freeze/r5_1_model_freeze_manifest.json"
    r5_model_path = r501 / "model_freeze/r5_hgb.joblib"
    r5_medians_path = r501 / "model_freeze/r5_training_medians.json"

    signal_path = out / "r9_2_signal_log.parquet"
    trade_path = out / "r9_2_trade_entry_log.parquet"
    outcome_path = out / "r9_2_outcome_log.parquet"
    status_path = out / "r9_2_status.json"
    run_log = out / "r9_2_run_log.jsonl"

    freeze = verify_freeze(manifest_path)
    model = joblib.load(model_path)
    medians = pd.Series(
        json.loads(medians_path.read_text(encoding="utf-8")),
        dtype=float,
    )

    r5_manifest = json.loads(r5_manifest_path.read_text(encoding="utf-8"))
    if r5_manifest.get("selected_primary") != "R5C0_HGB_REFERENCE":
        raise RuntimeError("R5.1 frozen lineage drift")
    for name, expected in (r5_manifest.get("artifacts") or {}).items():
        p = r501 / "model_freeze" / name
        if not p.exists() or sha256_file(p) != expected:
            raise RuntimeError(f"R5.1 frozen artifact mismatch: {name}")
    r5_model = joblib.load(r5_model_path)
    r5_medians = pd.Series(
        json.loads(r5_medians_path.read_text(encoding="utf-8")),
        dtype=float,
    )

    scored_symbols = pd.read_parquet(
        r501 / "r5_0_1_scored_rows.parquet",
        columns=["symbol"],
    )
    symbols = sorted(scored_symbols["symbol"].astype(str).unique())
    if len(symbols) != 93:
        raise RuntimeError(f"expected 93 symbols, got {len(symbols)}")

    source_state, last_complete_day = load_source_state(Path(a.source_state))
    news_daily = build_news_daily(
        Path(a.news_history),
        symbols,
        last_complete_day,
    )

    panel, live_source_max = build_live_panel(us, symbols)
    recon = reconcile_features(us, panel, symbols)
    append_event(
        run_log,
        "PREFLIGHT_PASS",
        live_source_max=str(live_source_max),
        ngram_last_complete_day=str(last_complete_day.date()),
        feature_reconciliation=recon,
    )

    old_signals = readpq(signal_path)
    if len(old_signals):
        old_signals["timestamp"] = nts(old_signals["timestamp"])
    seen_ts = set(old_signals["timestamp"].unique()) if len(old_signals) else set()

    candidate_ts = sorted(
        pd.Timestamp(x)
        for x in panel.loc[
            panel["timestamp"] >= PROSPECTIVE_START,
            "timestamp",
        ].dropna().unique()
        if pd.Timestamp(x) not in seen_ts
    )

    new_signals = []
    skipped = []
    features = list(BASE_FEATURES) + list(NEWS_FEATURES)
    base_required = [
        "rv_24", "ma_dist_24", "volume_z_24", "bar_range",
        "qqq_rv_24", "qqq_ma_dist_24",
    ]

    for ts in candidate_ts:
        z = panel.loc[panel["timestamp"] == ts].copy()
        valid = z.dropna(subset=base_required).copy()
        if valid.empty:
            skipped.append({"timestamp": str(ts), "reason": "NO_BASE_ROWS"})
            continue

        signal_as_of = pd.Timestamp(ts) + pd.Timedelta(1, unit="h")
        news_day_used = signal_as_of.floor("D") - pd.Timedelta(1, unit="D")
        if news_day_used > last_complete_day:
            skipped.append(
                {
                    "timestamp": str(ts),
                    "reason": "NGRAM_SOURCE_NOT_COMPLETE",
                    "news_day_used": str(news_day_used.date()),
                    "last_complete_day": str(last_complete_day.date()),
                }
            )
            continue

        valid, news_audit = attach_news_features(valid, news_daily)
        valid = valid.loc[valid[NEWS_FEATURES].notna().all(axis=1)].copy()
        coverage = int(valid["symbol"].nunique())
        if coverage < MIN_COVERAGE:
            skipped.append(
                {
                    "timestamp": str(ts),
                    "reason": "LOW_COVERAGE",
                    "coverage": coverage,
                }
            )
            continue

        valid["R9_SCORE"] = model.predict(
            valid[features].fillna(medians)
        )
        valid["R5_SCORE"] = r5_model.predict(
            valid[list(BASE_FEATURES)].fillna(r5_medians)
        )

        r9 = valid.sort_values(
            ["R9_SCORE", "symbol"], ascending=[False, True]
        ).iloc[0]
        r5 = valid.sort_values(
            ["R5_SCORE", "symbol"], ascending=[False, True]
        ).iloc[0]

        r9w = (
            float(np.clip(
                r9["universe_median_rv_24"] / r9["rv_24"],
                0.25,
                1.0,
            ))
            if r9["rv_24"] > 0 else 1.0
        )
        r5w = (
            float(np.clip(
                r5["universe_median_rv_24"] / r5["rv_24"],
                0.25,
                1.0,
            ))
            if r5["rv_24"] > 0 else 1.0
        )

        spearman = float(
            pd.Series(valid["R9_SCORE"].to_numpy()).corr(
                pd.Series(valid["R5_SCORE"].to_numpy()),
                method="spearman",
            )
        )
        r9top10 = set(valid.nlargest(10, "R9_SCORE")["symbol"])
        r5top10 = set(valid.nlargest(10, "R5_SCORE")["symbol"])

        rec = {
            "candidate_id": CANDIDATE,
            "role": "RESEARCH_ONLY_PROSPECTIVE_SHADOW",
            "timestamp": pd.Timestamp(ts),
            "signal_as_of": signal_as_of,
            "expected_seq": int(r9["expected_seq"]),
            "expected_exit_seq": int(r9["expected_seq"] + 4),
            "selected_symbol": str(r9["symbol"]),
            "score": float(r9["R9_SCORE"]),
            "position_weight": r9w,
            "universe_coverage": coverage,
            "news_day_used": news_day_used,
            "ngram_source_complete": True,
            "r5_selected_symbol": str(r5["symbol"]),
            "r5_score": float(r5["R5_SCORE"]),
            "r5_position_weight": r5w,
            "top1_agree": bool(r9["symbol"] == r5["symbol"]),
            "score_spearman": spearman,
            "top10_overlap": int(len(r9top10 & r5top10)),
            "model_sha256": freeze["artifacts"][model_path.name],
            "model_manifest_sha256": sha256_file(manifest_path),
            "r5_model_sha256": sha256_file(r5_model_path),
            "live_source_max_timestamp": str(live_source_max),
            "production_enabled": False,
            "live_execution": False,
            "strategy_signal_write": False,
            "news_feature_audit": news_audit,
        }
        rec["signal_id"] = f"{CANDIDATE}|{pd.Timestamp(ts).isoformat()}"
        rec["decision_hash"] = stable_hash(
            {
                k: (v.isoformat() if isinstance(v, pd.Timestamp) else v)
                for k, v in rec.items()
                if k != "decision_hash"
            }
        )
        new_signals.append(rec)

    new_signal_df = pd.DataFrame(new_signals)
    signal_log, n_signal = append_immutable(
        signal_path, new_signal_df, "signal_id", "decision_hash"
    )

    trade_log = readpq(trade_path)
    new_trades = []
    if len(signal_log):
        signal_log["timestamp"] = nts(signal_log["timestamp"])
        z = signal_log.sort_values(["expected_seq", "timestamp"])
        existing = set(trade_log["trade_id"]) if len(trade_log) else set()
        last_exit = (
            int(trade_log["expected_exit_seq"].max())
            if len(trade_log) else -10**18
        )
        for _, r in z.iterrows():
            tid = f"{CANDIDATE}|{int(r['expected_seq'])}"
            if tid in existing or int(r["expected_seq"]) < last_exit:
                continue
            tr = {
                "trade_id": tid,
                "signal_id": r["signal_id"],
                "decision_hash": r["decision_hash"],
                "candidate_id": CANDIDATE,
                "timestamp": r["timestamp"],
                "signal_as_of": r["signal_as_of"],
                "expected_seq": int(r["expected_seq"]),
                "expected_exit_seq": int(r["expected_exit_seq"]),
                "selected_symbol": r["selected_symbol"],
                "score": float(r["score"]),
                "position_weight": float(r["position_weight"]),
                "r5_selected_symbol": r["r5_selected_symbol"],
                "r5_score": float(r["r5_score"]),
                "r5_position_weight": float(r["r5_position_weight"]),
                "model_sha256": r["model_sha256"],
            }
            tr["trade_entry_hash"] = stable_hash(
                {
                    k: (v.isoformat() if isinstance(v, pd.Timestamp) else v)
                    for k, v in tr.items()
                    if k != "trade_entry_hash"
                }
            )
            new_trades.append(tr)
            last_exit = int(r["expected_exit_seq"])

    new_trade_df = pd.DataFrame(new_trades)
    trade_log, n_trade = append_immutable(
        trade_path, new_trade_df, "trade_id", "trade_entry_hash"
    )

    outcome_log = readpq(outcome_path)
    done = set(outcome_log["trade_id"]) if len(outcome_log) else set()
    asset_lookup = panel.set_index(["symbol", "expected_seq"])
    seq_lookup = (
        panel[
            ["expected_seq", "universe_mean_fwd_ret_4b", "qqq_fwd_ret_4b"]
        ]
        .drop_duplicates("expected_seq")
        .set_index("expected_seq")
    )
    new_outcomes = []

    if len(trade_log):
        for _, tr in trade_log.iterrows():
            if tr["trade_id"] in done:
                continue
            s = int(tr["expected_seq"])
            key = (tr["selected_symbol"], s)
            r5_key = (tr["r5_selected_symbol"], s)
            if key not in asset_lookup.index or r5_key not in asset_lookup.index:
                continue
            rr = asset_lookup.loc[key]
            rr5 = asset_lookup.loc[r5_key]
            if isinstance(rr, pd.DataFrame) or isinstance(rr5, pd.DataFrame):
                raise RuntimeError("non-unique R9.2 asset lookup")
            if not np.isfinite(rr["fwd_ret_4b"]) or not np.isfinite(rr5["fwd_ret_4b"]):
                continue
            if s not in seq_lookup.index:
                continue
            mt = seq_lookup.loc[s]
            if isinstance(mt, pd.DataFrame):
                mt = mt.iloc[0]
            if not (
                np.isfinite(mt["universe_mean_fwd_ret_4b"])
                and np.isfinite(mt["qqq_fwd_ret_4b"])
            ):
                continue

            w = float(tr["position_weight"])
            cost = w * COST_BPS / 10000
            net = w * float(rr["fwd_ret_4b"]) - cost
            qnet = w * float(mt["qqq_fwd_ret_4b"]) - cost
            unet = w * float(mt["universe_mean_fwd_ret_4b"]) - cost

            w5 = float(tr["r5_position_weight"])
            cost5 = w5 * COST_BPS / 10000
            r5net = w5 * float(rr5["fwd_ret_4b"]) - cost5

            rec = {
                "trade_id": tr["trade_id"],
                "trade_entry_hash": tr["trade_entry_hash"],
                "timestamp": pd.Timestamp(tr["timestamp"]),
                "signal_as_of": pd.Timestamp(tr["signal_as_of"]),
                "entry_date": pd.Timestamp(tr["timestamp"]).floor("D"),
                "expected_seq": s,
                "expected_exit_seq": int(tr["expected_exit_seq"]),
                "selected_symbol": tr["selected_symbol"],
                "position_weight": w,
                "net10_return": net,
                "matched_qqq_net10_return": qnet,
                "matched_universe_net10_return": unet,
                "log_excess_vs_qqq": float(np.log1p(net) - np.log1p(qnet)),
                "log_excess_vs_universe": float(np.log1p(net) - np.log1p(unet)),
                "r5_selected_symbol": tr["r5_selected_symbol"],
                "r5_position_weight": w5,
                "r5_net10_return": r5net,
                "paired_log_diff_r9_minus_r5": float(
                    np.log1p(net) - np.log1p(r5net)
                ),
                "matured_at_run_utc": nowiso(),
            }
            rec["outcome_hash"] = stable_hash(
                {
                    k: (v.isoformat() if isinstance(v, pd.Timestamp) else v)
                    for k, v in rec.items()
                    if k not in ["outcome_hash", "matured_at_run_utc"]
                }
            )
            new_outcomes.append(rec)

    new_outcome_df = pd.DataFrame(new_outcomes)
    outcome_log, n_outcome = append_immutable(
        outcome_path, new_outcome_df, "trade_id", "outcome_hash"
    )

    if a.write_neon:
        write_neon(new_signal_df, new_trade_df, new_outcome_df)

    m = metrics(outcome_log)
    boot = paired_bootstrap(outcome_log)
    if live_source_max < PROSPECTIVE_START:
        state = "WAITING_FOR_PROSPECTIVE_BOUNDARY"
    elif m["outcomes"] < 100 or m["distinct_days"] < 60:
        state = "ACCUMULATING_PROSPECTIVE_EVIDENCE"
    elif m["outcomes"] < 150 or m["distinct_days"] < 90:
        state = "MINIMUM_REVIEW_GATE_REACHED"
    else:
        state = "PREFERRED_CONFIRMATION_GATE_REACHED"

    if boot is None:
        prospective_confirmation = None
    else:
        prospective_confirmation = bool(
            boot["ci95_low"] > 0
            and boot["p_one_sided_r9_gt_r5"] < 0.05
            and (m["paired_log_diff_r9_minus_r5"] or 0) > 0
        )

    status = {
        "schema": SCHEMA,
        "updated_at_utc": nowiso(),
        "state": state,
        "candidate": CANDIDATE,
        "prospective_start": PROSPECTIVE_START.isoformat(),
        "production_enabled": False,
        "live_execution": False,
        "trade_enabled": False,
        "strategy_signal_write": False,
        "auto_trade_changed": False,
        "model_freeze_sha256": sha256_file(manifest_path),
        "live_source_max_timestamp": str(live_source_max),
        "ngram_source_state": source_state,
        "feature_reconciliation": recon,
        "signal_rows": int(len(signal_log)),
        "trade_entries": int(len(trade_log)),
        "mature_outcomes": int(len(outcome_log)),
        "new_this_run": {
            "candidate_timestamps": int(len(candidate_ts)),
            "signals": int(n_signal),
            "trades": int(n_trade),
            "outcomes": int(n_outcome),
            "skipped": int(len(skipped)),
        },
        "minimum_review_gate": {"outcomes": 100, "distinct_days": 60},
        "preferred_confirmation_gate": {"outcomes": 150, "distinct_days": 90},
        "metrics": m,
        "paired_bootstrap_if_eligible": boot,
        "prospective_confirmation": prospective_confirmation,
        "governance_note": (
            "R9.2 is research-only. Frozen model/features. "
            "No refit, no production strategy_signal write, no broker execution."
        ),
        "skipped_latest": skipped[-20:],
    }
    atomic_json(status_path, status)
    append_event(
        run_log,
        "SUCCESS",
        state=state,
        new_signals=n_signal,
        new_trades=n_trade,
        new_outcomes=n_outcome,
        prospective_confirmation=prospective_confirmation,
    )

    print(json.dumps(status, indent=2, default=str))
    print("R9_2_PROSPECTIVE_SHADOW=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
