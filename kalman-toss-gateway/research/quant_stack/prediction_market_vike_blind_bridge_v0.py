from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb
import numpy as np
import pandas as pd


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def api_key() -> str:
    return (os.environ.get("VIKE_API_KEY") or "").strip()


def public_manifest(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "KalmanVikeBlindBridge/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def available_l1_dates(
    manifest: dict[str, Any],
    *,
    asset: str,
    tenor: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in manifest.get("families", []):
        if row.get("asset") != asset or row.get("tenor") != tenor:
            continue
        date = str(row.get("date") or "")
        if not (start_date <= date <= end_date):
            continue
        l1 = (row.get("streams") or {}).get("l1_quotes") or {}
        if not l1:
            continue
        rows.append(
            {
                "date": date,
                "rows": int(l1.get("rows") or 0),
                "bytes": int(l1.get("bytes") or 0),
            }
        )
    return sorted(rows, key=lambda x: x["date"])


def archive_url(base: str, asset: str, tenor: str, date: str) -> str:
    return (
        base.rstrip("/")
        + f"/venue=polymarket/asset={asset}/tenor={tenor}"
        + f"/date={date}/l1_quotes.parquet"
    )


def download_authenticated(
    url: str,
    *,
    key: str,
    output: Path,
    expected_bytes: int,
    retries: int = 4,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    part = output.with_suffix(output.suffix + ".part")
    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "X-API-Key": key,
                    "User-Agent": "KalmanVikeBlindBridge/0.1",
                },
            )
            total = 0
            with urllib.request.urlopen(req, timeout=180) as r, part.open("wb") as f:
                while True:
                    chunk = r.read(8 * 1024 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    total += len(chunk)
            if expected_bytes and total != expected_bytes:
                part.unlink(missing_ok=True)
                raise RuntimeError(
                    f"archive byte mismatch expected={expected_bytes} actual={total}"
                )
            part.replace(output)
            return
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code in (429, 500, 502, 503, 504) and attempt + 1 < retries:
                time.sleep(min(20, 2 ** attempt))
                continue
            raise RuntimeError(f"Vike archive HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 >= retries:
                raise RuntimeError(f"Vike archive request failed: {exc}") from exc
            time.sleep(min(20, 2 ** attempt))
    raise RuntimeError("Vike archive retries exhausted")


def sql_path(path: Path) -> str:
    return str(path).replace("'", "''")


def aggregate_partition(
    raw_path: Path,
    output_path: Path,
    *,
    bucket_minutes: int,
) -> dict[str, Any]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    bucket_ms = int(bucket_minutes) * 60 * 1000
    con = duckdb.connect()
    try:
        query = f"""
        COPY (
          SELECT
            CAST(condition_id AS VARCHAR) AS condition_id,
            CAST(token_id AS VARCHAR) AS token_id,
            CAST(FLOOR(CAST(ts AS DOUBLE) / {bucket_ms}) * {bucket_ms} AS BIGINT) AS bucket_ms,
            arg_max(CAST(bid AS DOUBLE), ts) AS bid,
            arg_max(CAST(ask AS DOUBLE), ts) AS ask,
            arg_max((CAST(bid AS DOUBLE) + CAST(ask AS DOUBLE)) / 2.0, ts) AS midpoint,
            max(CAST(ts AS BIGINT)) AS source_ts
          FROM read_parquet('{sql_path(raw_path)}')
          WHERE
            CAST(bid AS DOUBLE) >= 0.0
            AND CAST(ask AS DOUBLE) <= 1.0
            AND CAST(ask AS DOUBLE) >= CAST(bid AS DOUBLE)
          GROUP BY 1,2,3
        ) TO '{sql_path(output_path)}'
        (FORMAT PARQUET, COMPRESSION ZSTD)
        """
        con.execute(query)
        row = con.execute(
            f"""
            SELECT
              count(*) AS rows,
              count(DISTINCT condition_id) AS conditions,
              count(DISTINCT token_id) AS tokens,
              min(bucket_ms) AS min_bucket,
              max(bucket_ms) AS max_bucket
            FROM read_parquet('{sql_path(output_path)}')
            """
        ).fetchone()
    finally:
        con.close()
    return {
        "rows": int(row[0]),
        "conditions": int(row[1]),
        "tokens": int(row[2]),
        "min_bucket_ms": int(row[3]) if row[3] is not None else None,
        "max_bucket_ms": int(row[4]) if row[4] is not None else None,
        "sha256": sha256(output_path),
    }


def load_reference(
    path: Path,
    *,
    theme: str,
    channel: str,
    start_utc: str,
    end_utc: str,
) -> pd.DataFrame:
    d = pd.read_parquet(path)
    d["ts"] = pd.to_datetime(d["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    start = pd.Timestamp(start_utc)
    end = pd.Timestamp(end_utc)
    out = d[
        (d["theme"] == theme)
        & (d["semantic_channel"] == channel)
        & (d["ts"] >= start)
        & (d["ts"] <= end)
    ][["slug", "ts", "probability", "poly_delta_1h"]].copy()
    out["probability"] = pd.to_numeric(out["probability"], errors="coerce")
    out["poly_delta_1h"] = pd.to_numeric(out["poly_delta_1h"], errors="coerce")
    out = out.dropna(subset=["slug", "ts", "probability"])
    out["bucket_ms"] = (out["ts"].astype("int64") // 1_000_000).astype("int64")
    return out.sort_values(["slug", "ts"]).reset_index(drop=True)


def blind_identity_match(
    train_ref: pd.DataFrame,
    aggregate_glob: str,
    *,
    min_points: int,
    mae_max: float,
    corr_min: float,
    margin_min: float,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    con = duckdb.connect()
    con.register(
        "ref_train",
        train_ref[["slug", "bucket_ms", "probability"]].copy(),
    )
    aggregate_glob = aggregate_glob.replace("'", "''")
    all_candidates: list[pd.DataFrame] = []

    try:
        for slug, ref_slug in train_ref.groupby("slug", sort=True):
            mean_p = float(ref_slug["probability"].mean())
            con.register(
                "ref_one",
                ref_slug[["bucket_ms", "probability"]].copy(),
            )
            query = f"""
            WITH coverage AS (
              SELECT
                condition_id,
                token_id,
                count(*) AS available_points,
                avg(midpoint) AS mean_mid
              FROM read_parquet('{aggregate_glob}')
              WHERE
                bucket_ms BETWEEN {int(ref_slug["bucket_ms"].min())}
                AND {int(ref_slug["bucket_ms"].max())}
              GROUP BY 1,2
              HAVING
                count(*) >= {int(min_points)}
                AND abs(avg(midpoint) - {mean_p}) <= 0.20
            ),
            metrics AS (
              SELECT
                a.condition_id,
                a.token_id,
                count(*) AS matched_points,
                avg(abs(a.midpoint - r.probability)) AS mae,
                corr(a.midpoint, r.probability) AS correlation
              FROM read_parquet('{aggregate_glob}') a
              JOIN ref_one r
                ON a.bucket_ms = r.bucket_ms
              JOIN coverage c
                ON a.condition_id = c.condition_id
               AND a.token_id = c.token_id
              GROUP BY 1,2
              HAVING count(*) >= {int(min_points)}
            ),
            best_token_per_condition AS (
              SELECT *,
                row_number() OVER (
                  PARTITION BY condition_id
                  ORDER BY mae ASC, correlation DESC NULLS LAST
                ) AS token_rank
              FROM metrics
            )
            SELECT
              condition_id,
              token_id,
              matched_points,
              mae,
              correlation
            FROM best_token_per_condition
            WHERE token_rank = 1
            ORDER BY mae ASC, correlation DESC NULLS LAST
            LIMIT 5
            """
            cands = con.execute(query).fetchdf()
            if not cands.empty:
                cands.insert(0, "slug", slug)
                all_candidates.append(cands)
    finally:
        con.close()

    candidates = (
        pd.concat(all_candidates, ignore_index=True)
        if all_candidates
        else pd.DataFrame(
            columns=[
                "slug",
                "condition_id",
                "token_id",
                "matched_points",
                "mae",
                "correlation",
            ]
        )
    )

    selected_rows = []
    identity_failures: list[str] = []
    for slug in sorted(train_ref["slug"].unique()):
        c = candidates[candidates["slug"] == slug].sort_values(
            ["mae", "correlation"],
            ascending=[True, False],
        )
        if c.empty:
            identity_failures.append(f"{slug}:no_candidate")
            continue
        best = c.iloc[0].to_dict()
        second_mae = float(c.iloc[1]["mae"]) if len(c) > 1 else math.inf
        best["mae_margin"] = second_mae - float(best["mae"])
        best["identity_pass"] = bool(
            int(best["matched_points"]) >= int(min_points)
            and float(best["mae"]) <= float(mae_max)
            and pd.notna(best["correlation"])
            and float(best["correlation"]) >= float(corr_min)
            and float(best["mae_margin"]) >= float(margin_min)
        )
        if not best["identity_pass"]:
            identity_failures.append(f"{slug}:threshold_fail")
        selected_rows.append(best)

    selected = pd.DataFrame(selected_rows)
    unique_conditions = (
        bool(selected["condition_id"].is_unique) if not selected.empty else False
    )
    if not unique_conditions:
        identity_failures.append("duplicate_condition_assignment")

    summary = {
        "reference_slugs": int(train_ref["slug"].nunique()),
        "selected_slugs": int(selected["slug"].nunique()) if not selected.empty else 0,
        "unique_conditions": unique_conditions,
        "identity_pass_count": (
            int(selected["identity_pass"].sum()) if "identity_pass" in selected else 0
        ),
        "min_mae_margin": (
            float(selected["mae_margin"].min()) if not selected.empty else None
        ),
        "max_identity_mae": (
            float(selected["mae"].max()) if not selected.empty else None
        ),
        "min_identity_correlation": (
            float(selected["correlation"].min()) if not selected.empty else None
        ),
        "failures": identity_failures,
        "identity_pass": bool(
            not identity_failures
            and len(selected) == train_ref["slug"].nunique()
            and unique_conditions
        ),
    }
    return selected, summary


def load_selected_validation(
    validation_ref: pd.DataFrame,
    mapping: pd.DataFrame,
    aggregate_glob: str,
) -> pd.DataFrame:
    if validation_ref.empty or mapping.empty:
        return pd.DataFrame()

    con = duckdb.connect()
    con.register(
        "ref_validation",
        validation_ref[
            ["slug", "bucket_ms", "probability", "poly_delta_1h"]
        ].copy(),
    )
    con.register(
        "mapping",
        mapping[["slug", "condition_id", "token_id"]].copy(),
    )
    aggregate_glob = aggregate_glob.replace("'", "''")
    try:
        out = con.execute(
            f"""
            SELECT
              r.slug,
              r.bucket_ms,
              r.probability,
              r.poly_delta_1h,
              a.midpoint AS vike_probability,
              a.condition_id,
              a.token_id
            FROM ref_validation r
            JOIN mapping m
              ON r.slug = m.slug
            JOIN read_parquet('{aggregate_glob}') a
              ON a.bucket_ms = r.bucket_ms
             AND a.condition_id = m.condition_id
             AND a.token_id = m.token_id
            ORDER BY r.slug, r.bucket_ms
            """
        ).fetchdf()
    finally:
        con.close()

    if out.empty:
        return out
    out["ts"] = pd.to_datetime(out["bucket_ms"], unit="ms", utc=True)
    return out


def validation_metrics(
    matched: pd.DataFrame,
    *,
    shock_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    if matched.empty:
        return {
            "shared_markets": 0,
            "matched_points": 0,
            "median_market_mae": None,
            "pooled_correlation": None,
            "median_abs_delta_1h_diff": None,
            "shock_pairs": 0,
            "shock_sign_agreement": None,
        }, pd.DataFrame()

    rows = []
    for slug, g in matched.groupby("slug", sort=True):
        corr = g["vike_probability"].corr(g["probability"])
        rows.append(
            {
                "slug": slug,
                "matched_points": int(len(g)),
                "mae": float(np.mean(np.abs(g["vike_probability"] - g["probability"]))),
                "correlation": (
                    float(corr)
                    if corr is not None and np.isfinite(corr)
                    else None
                ),
            }
        )
    per_market = pd.DataFrame(rows)

    x = matched.sort_values(["slug", "bucket_ms"]).copy()
    prior = x[["slug", "bucket_ms", "vike_probability"]].copy()
    prior["bucket_ms"] = prior["bucket_ms"] + 3_600_000
    prior = prior.rename(columns={"vike_probability": "vike_probability_1h_ago"})
    x = x.merge(prior, on=["slug", "bucket_ms"], how="left", validate="one_to_one")
    x["vike_delta_1h"] = x["vike_probability"] - x["vike_probability_1h_ago"]
    x["abs_delta_diff"] = np.abs(x["vike_delta_1h"] - x["poly_delta_1h"])

    corr = x["vike_probability"].corr(x["probability"])
    delta = x["abs_delta_diff"].dropna()
    shocks = x[
        x["poly_delta_1h"].notna()
        & x["vike_delta_1h"].notna()
        & (x["poly_delta_1h"].abs() >= float(shock_threshold))
    ].copy()
    shock_agreement = None
    if len(shocks):
        shock_agreement = float(
            (
                np.sign(shocks["poly_delta_1h"])
                == np.sign(shocks["vike_delta_1h"])
            ).mean()
        )

    metrics = {
        "shared_markets": int(per_market["slug"].nunique()),
        "matched_points": int(len(x)),
        "median_market_mae": float(per_market["mae"].median()),
        "pooled_correlation": (
            float(corr) if corr is not None and np.isfinite(corr) else None
        ),
        "median_abs_delta_1h_diff": (
            float(delta.median()) if len(delta) else None
        ),
        "shock_pairs": int(len(shocks)),
        "shock_sign_agreement": shock_agreement,
    }
    return metrics, per_market


def validation_gate(metrics: dict[str, Any], gate: dict[str, Any]) -> dict[str, bool]:
    return {
        "shared_markets_min": metrics["shared_markets"] >= int(gate["shared_markets_min"]),
        "matched_points_min": metrics["matched_points"] >= int(gate["matched_points_min"]),
        "median_market_mae_max": (
            metrics["median_market_mae"] is not None
            and metrics["median_market_mae"] <= float(gate["median_market_mae_max"])
        ),
        "pooled_correlation_min": (
            metrics["pooled_correlation"] is not None
            and metrics["pooled_correlation"] >= float(gate["pooled_correlation_min"])
        ),
        "median_abs_delta_1h_diff_max": (
            metrics["median_abs_delta_1h_diff"] is not None
            and metrics["median_abs_delta_1h_diff"]
            <= float(gate["median_abs_delta_1h_diff_max"])
        ),
        "shock_pairs_min": metrics["shock_pairs"] >= int(gate["shock_pairs_min"]),
        "shock_sign_agreement_min": (
            metrics["shock_sign_agreement"] is not None
            and metrics["shock_sign_agreement"]
            >= float(gate["shock_sign_agreement_min"])
        ),
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Vike archive-only blind OOS bridge v0")
    p.add_argument("--bridge-config", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--output-root", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    cfg_path = Path(args.bridge_config)
    cfg = read_json(cfg_path)
    source = cfg["source"]
    spec = cfg["discovery_bridge"]
    gate = cfg["bridge_gate"]
    out_root = Path(args.output_root)
    status_path = out_root / "bridge_status.json"

    payload: dict[str, Any] = {
        "schema": "kalman-prediction-market-vike-blind-bridge-v0.1",
        "checked_at_utc": now_iso(),
        "bridge_config_sha256": sha256(cfg_path),
        "identity_mode": "blind_time_series_match",
        "research_only": True,
        "production_promotion": False,
        "r51_mutated": False,
        "trade_execution": False,
        "retuning": False,
    }

    dates = [dict(x) for x in spec.get("frozen_overlap_partitions", [])]
    if not dates:
        manifest = public_manifest(source["manifest_url"])
        start_date = pd.Timestamp(spec["mapping_train_start_utc"]).strftime("%Y-%m-%d")
        end_date = pd.Timestamp(spec["validation_end_utc"]).strftime("%Y-%m-%d")
        dates = available_l1_dates(
            manifest,
            asset=source["family_asset"],
            tenor=source["family_tenor"],
            start_date=start_date,
            end_date=end_date,
        )
        payload["partition_plan_source"] = "live_manifest"
    else:
        payload["partition_plan_source"] = "frozen_public_manifest_snapshot"
        payload["partition_plan_provenance"] = spec.get("partition_plan_provenance")

    expected_dates = [
        "2026-09-08",
        "2026-09-09",
        "2026-09-10",
        "2026-09-11",
    ]
    actual_dates = [str(x.get("date")) for x in dates]
    if actual_dates != expected_dates:
        raise RuntimeError(
            f"unexpected frozen overlap dates expected={expected_dates} actual={actual_dates}"
        )
    if any(int(x.get("bytes") or 0) <= 0 for x in dates):
        raise RuntimeError("frozen overlap partition has invalid byte size")

    payload["archive_dates"] = dates
    payload["download_total_gb"] = float(sum(int(x["bytes"]) for x in dates) / 1e9)

    key = api_key()
    if not key:
        payload["status"] = "WAITING_FOR_VIKE_KEY"
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2))
        return 0

    aggregate_root = out_root / "aggregate_10m"
    aggregate_root.mkdir(parents=True, exist_ok=True)
    partition_audit = []
    for row in dates:
        date = row["date"]
        agg = aggregate_root / f"date={date}" / "l1_10m.parquet"
        if agg.exists():
            partition_audit.append(
                {
                    "date": date,
                    "status": "REUSED_AGGREGATE",
                    "sha256": sha256(agg),
                }
            )
            continue

        raw_dir = out_root / "raw"
        raw = raw_dir / f"l1_quotes_{date}.parquet"
        url = archive_url(
            source["archive_base"],
            source["family_asset"],
            source["family_tenor"],
            date,
        )
        try:
            download_authenticated(
                url,
                key=key,
                output=raw,
                expected_bytes=int(row["bytes"]),
            )
            audit = aggregate_partition(
                raw,
                agg,
                bucket_minutes=int(spec["bucket_minutes"]),
            )
            audit["date"] = date
            audit["status"] = "AGGREGATED"
            partition_audit.append(audit)
        finally:
            raw.unlink(missing_ok=True)

    payload["partitions"] = partition_audit
    aggregate_glob = str(aggregate_root / "date=*" / "l1_10m.parquet")

    train = load_reference(
        Path(args.reference),
        theme=spec["target_theme"],
        channel=spec["target_channel"],
        start_utc=spec["mapping_train_start_utc"],
        end_utc=spec["mapping_train_end_utc"],
    )
    validation = load_reference(
        Path(args.reference),
        theme=spec["target_theme"],
        channel=spec["target_channel"],
        start_utc=spec["validation_start_utc"],
        end_utc=spec["validation_end_utc"],
    )
    payload["reference"] = {
        "train_rows": int(len(train)),
        "train_slugs": int(train["slug"].nunique()),
        "validation_rows": int(len(validation)),
        "validation_slugs": int(validation["slug"].nunique()),
    }

    mapping, identity = blind_identity_match(
        train,
        aggregate_glob,
        min_points=int(gate["identity_train_points_min"]),
        mae_max=float(gate["identity_train_mae_max"]),
        corr_min=float(gate["identity_train_correlation_min"]),
        margin_min=float(gate["identity_margin_mae_min"]),
    )
    payload["identity"] = identity
    mapping_path = out_root / "blind_identity_mapping.csv"
    mapping.to_csv(mapping_path, index=False)

    if not identity["identity_pass"]:
        payload["status"] = "IDENTITY_BRIDGE_FAIL"
        payload["oos_source_allowed"] = False
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2, default=str))
        return 0

    matched = load_selected_validation(validation, mapping, aggregate_glob)
    metrics, per_market = validation_metrics(
        matched,
        shock_threshold=float(gate["shock_threshold"]),
    )
    checks = validation_gate(metrics, gate)
    passed = bool(checks) and all(checks.values())
    payload["validation_metrics"] = metrics
    payload["validation_gate_checks"] = checks
    payload["status"] = "BRIDGE_PASS" if passed else "BRIDGE_FAIL"
    payload["oos_source_allowed"] = passed

    per_market.to_csv(out_root / "validation_market_metrics.csv", index=False)
    matched.to_parquet(out_root / "validation_matched_points.parquet", index=False)
    write_json_atomic(status_path, payload)
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
