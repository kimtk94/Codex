from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.prediction_market_layer_v0 import classify_theme, contract_semantics, load_config


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def public_manifest(url: str) -> dict[str, Any]:
    req = urllib.request.Request(url, headers={"User-Agent": "KalmanVikeBridge/0.1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def summarize_manifest(
    manifest: dict[str, Any],
    *,
    cutoff_date: str,
    asset: str = "other",
    tenor: str = "other",
) -> dict[str, Any]:
    dates = sorted(str(x.get("date")) for x in manifest.get("dates", []) if x.get("date"))
    fam = []
    for row in manifest.get("families", []):
        if row.get("asset") != asset or row.get("tenor") != tenor:
            continue
        date = str(row.get("date") or "")
        if date <= cutoff_date:
            continue
        streams = row.get("streams") or {}
        l1 = streams.get("l1_quotes") or {}
        fam.append(
            {
                "date": date,
                "rows": int(l1.get("rows") or 0),
                "bytes": int(l1.get("bytes") or 0),
            }
        )
    return {
        "generated_at": manifest.get("generated_at"),
        "license": (manifest.get("license") or {}).get("name"),
        "archive_earliest": dates[0] if dates else None,
        "archive_latest": dates[-1] if dates else None,
        "post_cutoff_family_days": len(fam),
        "post_cutoff_l1_rows": int(sum(x["rows"] for x in fam)),
        "post_cutoff_l1_bytes": int(sum(x["bytes"] for x in fam)),
        "post_cutoff_l1_gb": float(sum(x["bytes"] for x in fam) / 1e9),
        "post_cutoff_dates": [x["date"] for x in fam],
    }


def api_key() -> str:
    return (os.environ.get("VIKE_API_KEY") or "").strip()


def vike_json(url: str, key: str) -> Any:
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": key,
            "Accept": "application/json",
            "User-Agent": "KalmanVikeBridge/0.1",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Vike HTTP {exc.code}: {body[:500]}") from exc


def discover_markets(
    *,
    api_base: str,
    key: str,
    queries: list[str],
    target_theme: str,
    target_channel: str,
    prediction_config: dict[str, Any],
) -> pd.DataFrame:
    rows: dict[str, dict[str, Any]] = {}
    for query in queries:
        url = (
            api_base.rstrip("/")
            + "/markets?"
            + urllib.parse.urlencode({"query": query, "limit": 100})
        )
        payload = vike_json(url, key)
        if not isinstance(payload, list):
            raise RuntimeError("Vike /markets response is not a list")
        for market in payload:
            condition_id = str(market.get("condition_id") or "")
            slug = str(market.get("slug") or "")
            tokens = market.get("token_ids") or []
            if not condition_id or not slug or len(tokens) != 2:
                continue
            question_proxy = slug.replace("-", " ")
            theme = classify_theme(question_proxy, prediction_config)
            channel, risk_sign = contract_semantics(
                slug, question_proxy, theme, prediction_config
            )
            if theme != target_theme or channel != target_channel:
                continue
            rows[condition_id] = {
                "condition_id": condition_id,
                "slug": slug,
                "token0": str(tokens[0]),
                "token1": str(tokens[1]),
                "theme": theme,
                "semantic_channel": channel,
                "risk_prior_sign": risk_sign,
                "end_date": market.get("end_date"),
                "active": market.get("active"),
                "closed": market.get("closed"),
            }
    if not rows:
        return pd.DataFrame(
            columns=[
                "condition_id",
                "slug",
                "token0",
                "token1",
                "theme",
                "semantic_channel",
                "risk_prior_sign",
                "end_date",
                "active",
                "closed",
            ]
        )
    return pd.DataFrame(rows.values()).sort_values(["slug", "condition_id"]).reset_index(drop=True)


def _epoch_ms_to_utc(values: pd.Series) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return pd.to_datetime(numeric, unit="ms", utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )


def canonicalize_l1(
    raw: pd.DataFrame,
    markets: pd.DataFrame,
    *,
    bucket_minutes: int,
) -> pd.DataFrame:
    required = {
        "token_id",
        "condition_id",
        "ts",
        "bid",
        "ask",
        "bid_size",
        "ask_size",
    }
    missing = sorted(required - set(raw.columns))
    if missing:
        raise ValueError(f"Vike L1 missing columns: {missing}")
    if markets.empty:
        return pd.DataFrame()

    token_map: dict[str, tuple[str, str, int]] = {}
    for row in markets.itertuples(index=False):
        token_map[str(row.token0)] = (str(row.condition_id), str(row.slug), 0)
        token_map[str(row.token1)] = (str(row.condition_id), str(row.slug), 1)

    q = raw.copy()
    q["token_id"] = q["token_id"].astype(str)
    q = q[q["token_id"].isin(token_map)]
    if q.empty:
        return pd.DataFrame()

    q["ts"] = _epoch_ms_to_utc(q["ts"])
    q["bid"] = pd.to_numeric(q["bid"], errors="coerce")
    q["ask"] = pd.to_numeric(q["ask"], errors="coerce")
    q = q.dropna(subset=["ts", "bid", "ask"])
    q = q[(q["bid"] >= 0) & (q["ask"] <= 1) & (q["ask"] >= q["bid"])]
    q["midpoint"] = (q["bid"] + q["ask"]) / 2.0

    meta = q["token_id"].map(token_map)
    q["mapped_condition_id"] = meta.map(lambda x: x[0])
    q["slug"] = meta.map(lambda x: x[1])
    q["token_position"] = meta.map(lambda x: x[2]).astype(int)
    q["bucket_ts"] = q["ts"].dt.floor(f"{int(bucket_minutes)}min")
    q = q.sort_values(["slug", "token_position", "ts"])
    q = q.groupby(
        ["slug", "token_position", "bucket_ts"],
        as_index=False,
        sort=False,
    ).tail(1)
    return q[
        [
            "slug",
            "token_position",
            "bucket_ts",
            "midpoint",
            "bid",
            "ask",
        ]
    ].rename(columns={"bucket_ts": "ts"}).sort_values(
        ["slug", "token_position", "ts"]
    ).reset_index(drop=True)


def bridge_metrics(
    reference: pd.DataFrame,
    vike_l1: pd.DataFrame,
    *,
    shock_threshold: float,
) -> tuple[dict[str, Any], pd.DataFrame]:
    if reference.empty or vike_l1.empty:
        return {
            "shared_markets": 0,
            "matched_points": 0,
            "orientation_consistency": None,
            "median_market_mae": None,
            "pooled_correlation": None,
            "median_abs_delta_1h_diff": None,
            "shock_pairs": 0,
            "shock_sign_agreement": None,
        }, pd.DataFrame()

    ref = reference.copy()
    ref["ts"] = pd.to_datetime(ref["ts"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    ref["probability"] = pd.to_numeric(ref["probability"], errors="coerce")
    ref["poly_delta_1h"] = pd.to_numeric(ref["poly_delta_1h"], errors="coerce")
    ref = ref.dropna(subset=["ts", "slug", "probability"])

    wide = (
        vike_l1.pivot_table(
            index=["slug", "ts"],
            columns="token_position",
            values="midpoint",
            aggfunc="last",
        )
        .rename(columns={0: "vike_mid_0", 1: "vike_mid_1"})
        .reset_index()
    )
    merged = ref.merge(wide, on=["slug", "ts"], how="inner")
    merged = merged.dropna(subset=["vike_mid_0", "vike_mid_1"])
    if merged.empty:
        return {
            "shared_markets": 0,
            "matched_points": 0,
            "orientation_consistency": None,
            "median_market_mae": None,
            "pooled_correlation": None,
            "median_abs_delta_1h_diff": None,
            "shock_pairs": 0,
            "shock_sign_agreement": None,
        }, merged

    market_rows = []
    orientation: dict[str, int] = {}
    for slug, g in merged.groupby("slug"):
        mae0 = float(np.mean(np.abs(g["vike_mid_0"] - g["probability"])))
        mae1 = float(np.mean(np.abs(g["vike_mid_1"] - g["probability"])))
        pos = 0 if mae0 <= mae1 else 1
        orientation[str(slug)] = pos
        selected = g[f"vike_mid_{pos}"]
        corr = selected.corr(g["probability"])
        market_rows.append(
            {
                "slug": slug,
                "matched_points": int(len(g)),
                "selected_token_position": pos,
                "mae0": mae0,
                "mae1": mae1,
                "selected_mae": min(mae0, mae1),
                "correlation": float(corr) if corr is not None and np.isfinite(corr) else None,
            }
        )

    merged["selected_token_position"] = merged["slug"].map(orientation)
    merged["vike_probability"] = np.where(
        merged["selected_token_position"] == 0,
        merged["vike_mid_0"],
        merged["vike_mid_1"],
    )
    merged = merged.sort_values(["slug", "ts"]).reset_index(drop=True)

    prior = merged[["slug", "ts", "vike_probability"]].copy()
    prior["ts"] = prior["ts"] + pd.Timedelta(hours=1)
    prior = prior.rename(columns={"vike_probability": "vike_probability_1h_ago"})
    merged = merged.merge(prior, on=["slug", "ts"], how="left", validate="one_to_one")
    merged["vike_delta_1h"] = (
        merged["vike_probability"] - merged["vike_probability_1h_ago"]
    )
    merged["abs_delta_diff"] = np.abs(
        merged["vike_delta_1h"] - merged["poly_delta_1h"]
    )

    market_df = pd.DataFrame(market_rows)
    counts = market_df["selected_token_position"].value_counts()
    orientation_consistency = float(counts.max() / counts.sum()) if len(counts) else None

    pooled_corr = merged["vike_probability"].corr(merged["probability"])
    delta_diff = merged["abs_delta_diff"].dropna()

    shocks = merged[
        merged["poly_delta_1h"].notna()
        & merged["vike_delta_1h"].notna()
        & (merged["poly_delta_1h"].abs() >= float(shock_threshold))
    ].copy()
    if len(shocks):
        agree = np.sign(shocks["poly_delta_1h"]) == np.sign(shocks["vike_delta_1h"])
        shock_agreement = float(agree.mean())
    else:
        shock_agreement = None

    metrics = {
        "shared_markets": int(market_df["slug"].nunique()),
        "matched_points": int(len(merged)),
        "orientation_consistency": orientation_consistency,
        "selected_token_position_mode": (
            int(counts.index[0]) if len(counts) else None
        ),
        "median_market_mae": (
            float(market_df["selected_mae"].median()) if len(market_df) else None
        ),
        "pooled_correlation": (
            float(pooled_corr) if pooled_corr is not None and np.isfinite(pooled_corr) else None
        ),
        "median_abs_delta_1h_diff": (
            float(delta_diff.median()) if len(delta_diff) else None
        ),
        "shock_pairs": int(len(shocks)),
        "shock_sign_agreement": shock_agreement,
    }
    return metrics, market_df


def apply_gate(metrics: dict[str, Any], gate: dict[str, Any]) -> dict[str, bool]:
    def ge(name: str, threshold_name: str) -> bool:
        v = metrics.get(name)
        return v is not None and float(v) >= float(gate[threshold_name])

    def le(name: str, threshold_name: str) -> bool:
        v = metrics.get(name)
        return v is not None and float(v) <= float(gate[threshold_name])

    return {
        "shared_markets_min": ge("shared_markets", "shared_markets_min"),
        "matched_points_min": ge("matched_points", "matched_points_min"),
        "orientation_consistency_min": ge(
            "orientation_consistency", "orientation_consistency_min"
        ),
        "median_market_mae_max": le("median_market_mae", "median_market_mae_max"),
        "pooled_correlation_min": ge(
            "pooled_correlation", "pooled_correlation_min"
        ),
        "median_abs_delta_1h_diff_max": le(
            "median_abs_delta_1h_diff", "median_abs_delta_1h_diff_max"
        ),
        "shock_pairs_min": ge("shock_pairs", "shock_pairs_min"),
        "shock_sign_agreement_min": ge(
            "shock_sign_agreement", "shock_sign_agreement_min"
        ),
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Vike -> frozen prediction-market measurement bridge v0")
    p.add_argument("--bridge-config", required=True)
    p.add_argument("--prediction-config", required=True)
    p.add_argument("--reference", required=True)
    p.add_argument("--vike-l1")
    p.add_argument("--markets-json")
    p.add_argument("--output-dir", required=True)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    bridge_cfg_path = Path(args.bridge_config)
    bridge_cfg = read_json(bridge_cfg_path)
    prediction_cfg = load_config(Path(args.prediction_config))
    source = bridge_cfg["source"]
    bridge = bridge_cfg["discovery_bridge"]
    gate = bridge_cfg["bridge_gate"]

    manifest = public_manifest(source["manifest_url"])
    cutoff_date = pd.Timestamp(bridge["reference_cutoff_utc"]).strftime("%Y-%m-%d")
    manifest_summary = summarize_manifest(
        manifest,
        cutoff_date=cutoff_date,
        asset=source["family_asset"],
        tenor=source["family_tenor"],
    )

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "schema": "kalman-prediction-market-vike-bridge-v0.1",
        "checked_at_utc": utc_now_iso(),
        "bridge_config_sha256": sha256(bridge_cfg_path),
        "manifest": manifest_summary,
        "safety": bridge_cfg["safety"],
        "production_promotion": False,
        "r51_mutated": False,
        "trade_execution": False,
    }

    key = api_key()
    if not key and not args.vike_l1:
        payload["status"] = "WAITING_FOR_VIKE_KEY"
        (out_dir / "bridge_status.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload, indent=2, default=str))
        return 0

    if args.markets_json:
        markets_payload = json.loads(Path(args.markets_json).read_text())
        markets = pd.DataFrame(markets_payload)
    else:
        markets = discover_markets(
            api_base=source["api_base"],
            key=key,
            queries=list(bridge["market_queries"]),
            target_theme=bridge["target_theme"],
            target_channel=bridge["target_channel"],
            prediction_config=prediction_cfg,
        )

    markets.to_json(
        out_dir / "vike_target_markets.json",
        orient="records",
        indent=2,
    )
    payload["target_market_count"] = int(len(markets))

    if not args.vike_l1:
        payload["status"] = "READY_FOR_OVERLAP_DOWNLOAD"
        (out_dir / "bridge_status.json").write_text(
            json.dumps(payload, indent=2, default=str) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(payload, indent=2, default=str))
        return 0

    raw = pd.read_parquet(args.vike_l1)
    l1 = canonicalize_l1(
        raw,
        markets,
        bucket_minutes=int(bridge["bucket_minutes"]),
    )
    ref = pd.read_parquet(args.reference)
    ref["ts"] = pd.to_datetime(ref["ts"], utc=True, errors="coerce")
    start = pd.Timestamp(bridge["overlap_start_utc"])
    end = pd.Timestamp(bridge["overlap_end_utc"])
    ref = ref[
        (ref["ts"] >= start)
        & (ref["ts"] <= end)
        & (ref["theme"] == bridge["target_theme"])
        & (ref["semantic_channel"] == bridge["target_channel"])
    ].copy()

    metrics, market_metrics = bridge_metrics(
        ref,
        l1,
        shock_threshold=float(gate["shock_threshold"]),
    )
    checks = apply_gate(metrics, gate)
    passed = bool(checks) and all(checks.values())
    payload["metrics"] = metrics
    payload["gate_checks"] = checks
    payload["status"] = "BRIDGE_PASS" if passed else "BRIDGE_FAIL"
    payload["oos_source_allowed"] = passed

    market_metrics.to_csv(out_dir / "bridge_market_metrics.csv", index=False)
    l1.to_parquet(out_dir / "vike_l1_10m_overlap.parquet", index=False)
    (out_dir / "bridge_status.json").write_text(
        json.dumps(payload, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
