from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from r9_news_features import NEWS_FEATURES, build_daily_features
from r9_news_ngram_bq import build_sql

SOURCE = "GDELT_BIGQUERY_WEB_1GRAMS_2GRAMS"
FEATURE_VERSION = "R9_1_NGRAM_ATTENTION_FROZEN"
SOURCE_KEY = "gdelt_web_ngram_daily"
NEON_CONFIRM = "CONFIRM_R9_2_NGRAM_DAILY_NEON"


def nowiso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_day(x: str) -> pd.Timestamp:
    t = pd.Timestamp(x)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    else:
        t = t.tz_convert("UTC")
    return t.floor("D")


def day_int(t: pd.Timestamp) -> int:
    return int(t.strftime("%Y%m%d") + "000000")


def atomic_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def load_registry(path: Path) -> pd.DataFrame:
    reg = pd.read_csv(path)
    required = {
        "symbol", "company_name", "alias", "alias_lower", "ngram_order", "status"
    }
    missing = required.difference(reg.columns)
    if missing:
        raise RuntimeError(f"registry missing columns: {sorted(missing)}")
    if len(reg) != 93 or reg["symbol"].nunique() != 93:
        raise RuntimeError("R9 registry must contain exactly 93 unique symbols")
    if not reg["status"].eq("SUPPORTED").all():
        raise RuntimeError("R9 registry contains unsupported alias")
    return reg.sort_values("symbol").reset_index(drop=True)


def build_daily_sql(
    registry_path: Path,
    output_path: Path,
    start_day: pd.Timestamp,
    end_day: pd.Timestamp,
) -> None:
    if end_day <= start_day:
        raise RuntimeError("end day must be after start day")
    reg = load_registry(registry_path)
    sql = build_sql(
        reg,
        start_int=day_int(start_day),
        end_int=day_int(end_day),
    )
    header = (
        "-- R9.2 prospective source bridge / daily incremental query\n"
        f"-- start_day={start_day.date()} end_day_exclusive={end_day.date()}\n"
        "-- This query updates source history only; it does not create model signals.\n"
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(header + sql, encoding="utf-8")
    print(f"SQL={output_path}")
    print(f"START_DAY={start_day.date()}")
    print(f"END_DAY_EXCLUSIVE={end_day.date()}")
    print(f"CALENDAR_DAYS={(end_day-start_day).days}")


def normalize_query_result(
    csv_path: Path,
    reg: pd.DataFrame,
    start_day: pd.Timestamp,
    end_day: pd.Timestamp,
) -> pd.DataFrame:
    raw = pd.read_csv(csv_path)
    required = {"symbol", "day_utc", "mention_count"}
    if not required.issubset(raw.columns):
        raise RuntimeError(f"BigQuery result missing columns: {sorted(required-set(raw.columns))}")

    raw = raw[list(required)].copy()
    raw["symbol"] = raw["symbol"].astype(str)
    unknown = sorted(set(raw["symbol"]) - set(reg["symbol"]))
    if unknown:
        raise RuntimeError(f"unknown R9 symbols in query result: {unknown}")

    raw["mention_count"] = pd.to_numeric(raw["mention_count"], errors="raise")
    if (~np.isfinite(raw["mention_count"])).any() or (raw["mention_count"] < 0).any():
        raise RuntimeError("mention_count must be finite and nonnegative")

    raw["day"] = pd.to_datetime(
        pd.to_numeric(raw["day_utc"], errors="raise").astype("int64").astype(str),
        format="%Y%m%d",
        utc=True,
        errors="raise",
    )
    if ((raw["day"] < start_day) | (raw["day"] >= end_day)).any():
        raise RuntimeError("BigQuery result contains day outside requested range")
    if raw.duplicated(["symbol", "day"]).any():
        raise RuntimeError("BigQuery result has duplicate symbol/day")

    days = pd.date_range(
        start_day,
        end_day - pd.Timedelta(days=1),
        freq="D",
        tz="UTC",
    )
    full = pd.MultiIndex.from_product(
        [reg["symbol"].tolist(), days],
        names=["symbol", "day"],
    ).to_frame(index=False)

    full = full.merge(
        raw[["symbol", "day", "mention_count"]],
        on=["symbol", "day"],
        how="left",
        validate="one_to_one",
    )
    full["mention_count"] = full["mention_count"].fillna(0).astype("int64")
    full["day_utc"] = full["day"].dt.strftime("%Y%m%d").astype("int64")
    return full[["symbol", "day", "day_utc", "mention_count"]]


def merge_history(
    historical_path: Path,
    shadow_history_path: Path,
    completed: pd.DataFrame,
) -> pd.DataFrame:
    base_path = shadow_history_path if shadow_history_path.exists() else historical_path
    if not base_path.exists():
        raise FileNotFoundError(base_path)

    old = pd.read_csv(base_path)
    required = {"symbol", "day_utc", "mention_count"}
    if not required.issubset(old.columns):
        raise RuntimeError("existing R9 history has invalid columns")
    old = old[["symbol", "day_utc", "mention_count"]].copy()
    old["symbol"] = old["symbol"].astype(str)
    old["day_utc"] = pd.to_numeric(old["day_utc"], errors="raise").astype("int64")
    old["mention_count"] = pd.to_numeric(
        old["mention_count"], errors="raise"
    ).astype("int64")

    new = completed[["symbol", "day_utc", "mention_count"]].copy()
    merged = pd.concat([old, new], ignore_index=True)
    merged = (
        merged.sort_values(["day_utc", "symbol"])
        .drop_duplicates(["symbol", "day_utc"], keep="last")
        .reset_index(drop=True)
    )

    tmp = shadow_history_path.with_suffix(".csv.tmp")
    merged.to_csv(tmp, index=False)
    os.replace(tmp, shadow_history_path)
    return merged


def build_snapshot(
    history: pd.DataFrame,
    symbols: list[str],
    end_day: pd.Timestamp,
    start_output_day: pd.Timestamp,
) -> pd.DataFrame:
    if history.empty:
        raise RuntimeError("empty R9 history")
    x = history.copy()
    x["day"] = pd.to_datetime(
        x["day_utc"].astype("int64").astype(str),
        format="%Y%m%d",
        utc=True,
        errors="raise",
    )
    hist_start = x["day"].min()
    daily = build_daily_features(
        x[["symbol", "day_utc", "mention_count"]],
        symbols,
        history_start=hist_start,
        history_end_exclusive=end_day,
    )
    snap = daily.loc[daily["day"] >= start_output_day].copy()
    snap["feature_as_of"] = snap["day"] + pd.Timedelta(days=1)
    snap["news_day_used"] = snap["day"].dt.date
    snap["feature_version"] = FEATURE_VERSION
    snap["source_complete"] = True
    snap["run_id"] = (
        "r9ngram-" + snap["day"].dt.strftime("%Y%m%d")
    )
    return snap[
        [
            "symbol", "feature_as_of", "news_day_used", "feature_version",
            *NEWS_FEATURES, "source_complete", "run_id",
        ]
    ].copy()


def _load_database_url() -> str:
    env_file = os.getenv("KALMAN_ENV_FILE", "/opt/kalman/.env")
    try:
        from dotenv import load_dotenv
        load_dotenv(env_file, override=False)
    except Exception:
        pass
    url = os.getenv("DATABASE_URL_WRITER") or os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL_WRITER is required for R9.2 Neon write")
    return url


def write_neon(
    reg: pd.DataFrame,
    completed: pd.DataFrame,
    snapshot: pd.DataFrame,
    state: dict,
) -> None:
    if os.getenv("KALMAN_R9_2_DAILY_NEON_ENABLED", "").lower() != "true":
        raise RuntimeError("KALMAN_R9_2_DAILY_NEON_ENABLED=true required")
    if os.getenv("KALMAN_R9_2_DAILY_NEON_CONFIRM") != NEON_CONFIRM:
        raise RuntimeError(
            f"KALMAN_R9_2_DAILY_NEON_CONFIRM={NEON_CONFIRM} required"
        )

    import psycopg
    from psycopg.types.json import Jsonb

    url = _load_database_url()
    with psycopg.connect(url) as conn:
        with conn.cursor() as cur:
            for table in (
                "research.r9_news_mentions_daily",
                "research.r9_shadow_source_state",
                "research.r9_shadow_feature_snapshot",
            ):
                cur.execute("SELECT to_regclass(%s)", (table,))
                if cur.fetchone()[0] is None:
                    raise RuntimeError(f"missing Neon table: {table}")

            cur.executemany(
                """
                INSERT INTO research.r9_news_mentions_daily
                    (symbol, day_utc, mention_count, source, loaded_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (symbol, day_utc) DO UPDATE SET
                    mention_count = EXCLUDED.mention_count,
                    source = EXCLUDED.source,
                    loaded_at = now()
                """,
                [
                    (
                        r.symbol,
                        r.day.date(),
                        int(r.mention_count),
                        SOURCE,
                    )
                    for r in completed.itertuples(index=False)
                ],
            )

            cur.executemany(
                """
                INSERT INTO research.r9_shadow_feature_snapshot (
                    symbol, feature_as_of, news_day_used, feature_version,
                    ngram_log1p_d1, ngram_log1p_7d, ngram_abnormal_z_30d,
                    source_complete, run_id, created_at
                )
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                ON CONFLICT (symbol, feature_as_of, feature_version) DO UPDATE SET
                    news_day_used = EXCLUDED.news_day_used,
                    ngram_log1p_d1 = EXCLUDED.ngram_log1p_d1,
                    ngram_log1p_7d = EXCLUDED.ngram_log1p_7d,
                    ngram_abnormal_z_30d = EXCLUDED.ngram_abnormal_z_30d,
                    source_complete = EXCLUDED.source_complete,
                    run_id = EXCLUDED.run_id,
                    created_at = now()
                """,
                [
                    (
                        r.symbol,
                        r.feature_as_of.to_pydatetime(),
                        r.news_day_used,
                        r.feature_version,
                        float(r.ngram_log1p_d1),
                        float(r.ngram_log1p_7d),
                        float(r.ngram_abnormal_z_30d),
                        bool(r.source_complete),
                        r.run_id,
                    )
                    for r in snapshot.itertuples(index=False)
                ],
            )

            cur.execute(
                """
                INSERT INTO research.r9_shadow_source_state
                    (source_key, last_complete_day, status, payload, updated_at)
                VALUES (%s, %s, %s, %s, now())
                ON CONFLICT (source_key) DO UPDATE SET
                    last_complete_day = EXCLUDED.last_complete_day,
                    status = EXCLUDED.status,
                    payload = EXCLUDED.payload,
                    updated_at = now()
                """,
                (
                    SOURCE_KEY,
                    state["last_complete_day"],
                    state["status"],
                    Jsonb(state),
                ),
            )
        conn.commit()


def finalize(args: argparse.Namespace) -> None:
    start_day = parse_day(args.start_day)
    end_day = parse_day(args.end_day_exclusive)
    reg = load_registry(Path(args.registry))
    completed = normalize_query_result(
        Path(args.csv), reg, start_day, end_day
    )
    history = merge_history(
        Path(args.historical),
        Path(args.shadow_history),
        completed,
    )
    snapshot = build_snapshot(
        history,
        reg["symbol"].tolist(),
        end_day,
        start_day,
    )

    snapshot_path = Path(args.snapshot)
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = snapshot_path.with_suffix(".csv.tmp")
    snapshot.to_csv(tmp, index=False)
    os.replace(tmp, snapshot_path)

    last_complete = (end_day - pd.Timedelta(days=1)).date()
    state = {
        "schema": "kalman-r9-2-ngram-source-state-v1",
        "source_key": SOURCE_KEY,
        "source": SOURCE,
        "status": "READY",
        "start_day": str(start_day.date()),
        "end_day_exclusive": str(end_day.date()),
        "last_complete_day": str(last_complete),
        "calendar_days": int((end_day - start_day).days),
        "universe_symbols": int(len(reg)),
        "completed_rows": int(len(completed)),
        "query_rows_with_mentions": int((completed["mention_count"] > 0).sum()),
        "symbols_with_mentions_latest_day": int(
            completed.loc[
                completed["day"].dt.date == last_complete,
                :,
            ].query("mention_count > 0")["symbol"].nunique()
        ),
        "feature_version": FEATURE_VERSION,
        "production_changed": False,
        "live_execution": False,
        "updated_at_utc": nowiso(),
    }
    atomic_json(Path(args.state), state)

    if args.write_neon:
        write_neon(reg, completed, snapshot, state)

    print(json.dumps(state, indent=2, default=str))
    print(f"SHADOW_HISTORY={args.shadow_history}")
    print(f"FEATURE_SNAPSHOT={args.snapshot}")


def mark_state(args: argparse.Namespace) -> None:
    end_day = parse_day(args.end_day_exclusive)
    state = {
        "schema": "kalman-r9-2-ngram-source-state-v1",
        "source_key": SOURCE_KEY,
        "source": SOURCE,
        "status": args.status,
        "last_complete_day": args.last_complete_day,
        "end_day_exclusive": str(end_day.date()),
        "message": args.message,
        "production_changed": False,
        "live_execution": False,
        "updated_at_utc": nowiso(),
    }
    atomic_json(Path(args.state), state)
    print(json.dumps(state, indent=2))


def main() -> int:
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("build-sql")
    b.add_argument("--registry", required=True)
    b.add_argument("--start-day", required=True)
    b.add_argument("--end-day-exclusive", required=True)
    b.add_argument("--output", required=True)

    f = sub.add_parser("finalize")
    f.add_argument("--registry", required=True)
    f.add_argument("--csv", required=True)
    f.add_argument("--historical", required=True)
    f.add_argument("--shadow-history", required=True)
    f.add_argument("--snapshot", required=True)
    f.add_argument("--state", required=True)
    f.add_argument("--start-day", required=True)
    f.add_argument("--end-day-exclusive", required=True)
    f.add_argument("--write-neon", action="store_true")

    m = sub.add_parser("mark-state")
    m.add_argument("--state", required=True)
    m.add_argument("--status", choices=["WAITING", "BLOCKED_QUOTA", "FAILED"], required=True)
    m.add_argument("--last-complete-day")
    m.add_argument("--end-day-exclusive", required=True)
    m.add_argument("--message", default="")

    a = p.parse_args()
    if a.cmd == "build-sql":
        build_daily_sql(
            Path(a.registry),
            Path(a.output),
            parse_day(a.start_day),
            parse_day(a.end_day_exclusive),
        )
    elif a.cmd == "finalize":
        finalize(a)
    else:
        mark_state(a)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
