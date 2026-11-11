from __future__ import annotations

import argparse
import json
import os
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

from engine.prediction_market_layer_v0 import load_config
from research.quant_stack.prediction_market_vike_bridge_v0 import (
    api_key,
    discover_markets,
    public_manifest,
    read_json,
    sha256,
)


L1_COLUMNS = [
    "token_id",
    "condition_id",
    "ts",
    "local_ts",
    "bid",
    "ask",
    "bid_size",
    "ask_size",
]


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def date_rows(
    manifest: dict[str, Any],
    *,
    asset: str,
    tenor: str,
    start_date: str,
    end_date: str,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in manifest.get("families", []):
        if row.get("asset") != asset or row.get("tenor") != tenor:
            continue
        date = str(row.get("date") or "")
        if not (start_date <= date <= end_date):
            continue
        l1 = (row.get("streams") or {}).get("l1_quotes") or {}
        if not l1:
            continue
        out.append(
            {
                "date": date,
                "rows": int(l1.get("rows") or 0),
                "bytes": int(l1.get("bytes") or 0),
            }
        )
    return sorted(out, key=lambda x: x["date"])


def archive_url(base: str, asset: str, tenor: str, date: str) -> str:
    return (
        base.rstrip("/")
        + f"/venue=polymarket/asset={asset}/tenor={tenor}"
        + f"/date={date}/l1_quotes.parquet"
    )


def download_authenticated(url: str, key: str, output: Path, expected_bytes: int) -> None:
    req = urllib.request.Request(
        url,
        headers={
            "X-API-Key": key,
            "User-Agent": "KalmanVikeFetcher/0.1",
        },
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    tmp = output.with_suffix(output.suffix + ".part")
    total = 0
    with urllib.request.urlopen(req, timeout=120) as r, tmp.open("wb") as f:
        while True:
            chunk = r.read(8 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    if expected_bytes and total != expected_bytes:
        tmp.unlink(missing_ok=True)
        raise RuntimeError(
            f"Vike archive byte mismatch expected={expected_bytes} actual={total}"
        )
    tmp.replace(output)


def filter_tokens(raw_path: Path, output: Path, token_ids: set[str]) -> dict[str, Any]:
    pf = pq.ParquetFile(raw_path)
    chunks = []
    raw_rows = 0
    kept_rows = 0
    for batch in pf.iter_batches(columns=L1_COLUMNS, batch_size=250_000):
        raw_rows += batch.num_rows
        token_col = batch.column(batch.schema.get_field_index("token_id"))
        mask = pc.is_in(token_col, value_set=pa_array_strings(token_ids))
        selected = batch.filter(mask)
        if selected.num_rows:
            chunks.append(selected)
            kept_rows += selected.num_rows

    output.parent.mkdir(parents=True, exist_ok=True)
    if chunks:
        import pyarrow as pa

        table = pa.Table.from_batches(chunks)
        pq.write_table(table, output, compression="zstd")
    else:
        pd.DataFrame(columns=L1_COLUMNS).to_parquet(output, index=False)
    return {
        "raw_rows": int(raw_rows),
        "kept_rows": int(kept_rows),
        "output": str(output),
        "sha256": sha256(output),
    }


def pa_array_strings(values: set[str]):
    import pyarrow as pa

    return pa.array(sorted(values), type=pa.string())


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch/filter Vike L1 overlap partitions v0")
    p.add_argument("--bridge-config", required=True)
    p.add_argument("--prediction-config", required=True)
    p.add_argument("--output-root", required=True)
    p.add_argument("--keep-raw", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    bridge_cfg = read_json(Path(args.bridge_config))
    prediction_cfg = load_config(Path(args.prediction_config))
    source = bridge_cfg["source"]
    bridge = bridge_cfg["discovery_bridge"]
    output_root = Path(args.output_root)
    status_path = output_root / "fetch_status.json"

    payload: dict[str, Any] = {
        "schema": "kalman-prediction-market-vike-fetch-v0.1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "trade_execution": False,
        "r51_mutated": False,
    }

    key = api_key()
    manifest = public_manifest(source["manifest_url"])
    start_date = pd.Timestamp(bridge["overlap_start_utc"]).strftime("%Y-%m-%d")
    end_date = pd.Timestamp(bridge["overlap_end_utc"]).strftime("%Y-%m-%d")
    dates = date_rows(
        manifest,
        asset=source["family_asset"],
        tenor=source["family_tenor"],
        start_date=start_date,
        end_date=end_date,
    )
    payload["overlap_dates"] = dates
    payload["overlap_total_gb"] = float(sum(x["bytes"] for x in dates) / 1e9)

    if not key:
        payload["status"] = "WAITING_FOR_VIKE_KEY"
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2))
        return 0

    markets = discover_markets(
        api_base=source["api_base"],
        key=key,
        queries=list(bridge["market_queries"]),
        target_theme=bridge["target_theme"],
        target_channel=bridge["target_channel"],
        prediction_config=prediction_cfg,
    )
    if markets.empty:
        payload["status"] = "NO_TARGET_MARKETS"
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2))
        return 2

    output_root.mkdir(parents=True, exist_ok=True)
    markets_path = output_root / "vike_target_markets.json"
    markets.to_json(markets_path, orient="records", indent=2)
    token_ids = set(markets["token0"].astype(str)) | set(markets["token1"].astype(str))
    payload["target_market_count"] = int(len(markets))
    payload["target_token_count"] = int(len(token_ids))

    filtered_paths: list[Path] = []
    audits = []
    for row in dates:
        date = row["date"]
        filt = output_root / "filtered" / f"date={date}" / "l1_quotes_target.parquet"
        if filt.exists():
            filtered_paths.append(filt)
            audits.append(
                {
                    "date": date,
                    "status": "REUSED_FILTERED",
                    "output": str(filt),
                    "sha256": sha256(filt),
                }
            )
            continue

        url = archive_url(
            source["archive_base"],
            source["family_asset"],
            source["family_tenor"],
            date,
        )
        with tempfile.TemporaryDirectory(prefix=f"kalman-vike-{date}-") as td:
            raw = Path(td) / "l1_quotes.parquet"
            download_authenticated(url, key, raw, int(row["bytes"]))
            audit = filter_tokens(raw, filt, token_ids)
            audit["date"] = date
            audit["status"] = "FILTERED"
            audits.append(audit)
        filtered_paths.append(filt)

    frames = [pd.read_parquet(p) for p in filtered_paths if p.exists()]
    combined = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=L1_COLUMNS)
    combined_path = output_root / "vike_l1_overlap_target.parquet"
    combined.to_parquet(combined_path, index=False)

    payload["partitions"] = audits
    payload["combined_rows"] = int(len(combined))
    payload["combined_path"] = str(combined_path)
    payload["combined_sha256"] = sha256(combined_path)
    payload["markets_path"] = str(markets_path)
    payload["status"] = "READY_FOR_BRIDGE_VALIDATION"
    write_json_atomic(status_path, payload)
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
