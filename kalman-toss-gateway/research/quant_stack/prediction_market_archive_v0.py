from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from engine.prediction_market_layer_v0 import classify_theme, contract_semantics


DEFAULT_CONFIG = Path("config/prediction-market-layer-v0.json")
KNOWN_OUTAGE_START = pd.Timestamp("2026-07-17T17:26:09Z")
KNOWN_OUTAGE_END = pd.Timestamp("2026-07-22T10:32:48Z")
DEFAULT_CATEGORIES = {"macro", "finance", "geopolitics", "politics"}


def read_config(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_market_metadata(root: Path, config: dict[str, Any]) -> pd.DataFrame:
    path = root / "markets.parquet"
    if not path.exists():
        raise FileNotFoundError(f"missing markets.parquet: {path}")
    meta = pd.read_parquet(path, columns=["slug", "question", "category"])
    meta["slug"] = meta["slug"].astype(str)
    meta["question"] = meta["question"].fillna("").astype(str)
    meta["category"] = meta["category"].fillna("").astype(str)
    joined = (meta["question"] + " " + meta["category"]).str.strip()
    meta["theme"] = [classify_theme(x, config) for x in joined]
    sem = [
        contract_semantics(slug, question, theme, config)
        for slug, question, theme in zip(
            meta["slug"],
            meta["question"],
            meta["theme"],
        )
    ]
    meta["semantic_channel"] = [x[0] for x in sem]
    meta["risk_prior_sign"] = [x[1] for x in sem]
    return meta


def iter_quote_files(root: Path) -> Iterable[Path]:
    return sorted((root / "quotes").glob("dt=*/*.parquet"))


def _read_quote_file(path: Path, categories: set[str]) -> pd.DataFrame:
    wanted = [
        "ts",
        "slug",
        "category",
        "bid",
        "ask",
        "mid",
        "spread",
        "volume24hr",
        "segment",
    ]
    return pd.read_parquet(
        path,
        columns=wanted,
        filters=[("category", "in", sorted({x.lower() for x in categories}))],
    )


def compute_probability_deltas(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    out = frame.copy()
    keys = ["slug", "segment", "ts"]
    base = out[keys + ["probability"]].copy()

    for minutes, column in ((10, "poly_delta_10m"), (60, "poly_delta_1h")):
        prior = base.copy()
        prior["ts"] = prior["ts"] + pd.Timedelta(f"{minutes}min")
        prior = prior.rename(columns={"probability": f"probability_{minutes}m_ago"})
        out = out.merge(prior, how="left", on=keys, sort=False, validate="one_to_one")
        prior_col = f"probability_{minutes}m_ago"
        out[column] = out["probability"] - out[prior_col]
        out = out.drop(columns=[prior_col])

    out["poly_velocity_1h"] = out["poly_delta_1h"]
    return out


def normalize_quotes(
    raw: pd.DataFrame,
    metadata: pd.DataFrame,
    *,
    config: dict[str, Any],
    categories: set[str],
    start: pd.Timestamp | None = None,
    end: pd.Timestamp | None = None,
    compute_deltas: bool = True,
) -> pd.DataFrame:
    if raw.empty:
        return pd.DataFrame()

    q = raw.copy()
    q["slug"] = q["slug"].astype(str)
    q["category"] = q["category"].fillna("").astype(str).str.lower()
    q["ts"] = pd.to_datetime(q["ts"], utc=True, errors="coerce")
    q = q.dropna(subset=["ts", "slug", "mid"])
    q = q[q["category"].isin({x.lower() for x in categories})]

    if start is not None:
        q = q[q["ts"] >= start]
    if end is not None:
        q = q[q["ts"] <= end]

    for c in ["bid", "ask", "mid", "spread", "volume24hr"]:
        q[c] = pd.to_numeric(q[c], errors="coerce")
    q = q[q["mid"].between(0.0, 1.0, inclusive="both")]
    q = q[(q["bid"].isna()) | (q["ask"].isna()) | (q["ask"] >= q["bid"])]

    if "segment" not in q or q["segment"].isna().all():
        q["segment"] = (q["ts"] >= KNOWN_OUTAGE_END).astype(int) + 1
    q["segment"] = pd.to_numeric(q["segment"], errors="coerce").fillna(-1).astype(int)

    meta = metadata[
        ["slug", "question", "theme", "semantic_channel", "risk_prior_sign"]
    ].drop_duplicates("slug")
    q = q.merge(meta, how="left", on="slug")
    q = q[q["theme"].fillna("OTHER") != "OTHER"]
    if q.empty:
        return q

    q["bucket_ts"] = q["ts"].dt.floor("10min")
    q = q.sort_values(["slug", "segment", "ts"])
    q = (
        q.groupby(["slug", "segment", "bucket_ts"], sort=False, as_index=False)
        .tail(1)
        .rename(columns={"bucket_ts": "canonical_ts"})
    )
    q["ts"] = q["canonical_ts"]
    q["probability"] = q["mid"]
    q["quote_price_kind"] = "MIDPOINT_NOT_TRADE"
    q["traded_price_available"] = False
    q["volume24hr_quality"] = q["volume24hr"].notna().map(
        {True: "UPSTREAM_REPORTED", False: "MISSING_KNOWN_DATASET_LIMITATION"}
    )
    q["known_gap_guard"] = "SEGMENT_SCOPED"
    q["source_dataset"] = "DineshKumar8399/polymarket-orderbook-dataset"
    q["source_license"] = "CC-BY-4.0"
    if compute_deltas:
        q = compute_probability_deltas(q)
    else:
        q["poly_delta_10m"] = pd.NA
        q["poly_delta_1h"] = pd.NA
        q["poly_velocity_1h"] = pd.NA
    cols = [
        "ts",
        "slug",
        "question",
        "category",
        "theme",
        "semantic_channel",
        "risk_prior_sign",
        "segment",
        "probability",
        "poly_delta_10m",
        "poly_delta_1h",
        "poly_velocity_1h",
        "bid",
        "ask",
        "spread",
        "volume24hr",
        "quote_price_kind",
        "traded_price_available",
        "volume24hr_quality",
        "known_gap_guard",
        "source_dataset",
        "source_license",
    ]
    return q[cols].sort_values(["ts", "slug"]).reset_index(drop=True)


def build_archive(
    root: Path,
    output: Path,
    *,
    config: dict[str, Any],
    categories: set[str],
    start: pd.Timestamp | None,
    end: pd.Timestamp | None,
) -> dict[str, Any]:
    metadata = load_market_metadata(root, config)
    in_scope = metadata[metadata["theme"] != "OTHER"]["slug"]
    in_scope_set = set(in_scope.astype(str))

    chunks: list[pd.DataFrame] = []
    files_scanned = 0
    raw_rows = 0
    for path in iter_quote_files(root):
        raw = _read_quote_file(path, categories)
        files_scanned += 1
        if raw.empty:
            continue
        raw["slug"] = raw["slug"].astype(str)
        raw = raw[raw["slug"].isin(in_scope_set)]
        raw_rows += len(raw)
        if raw.empty:
            continue
        norm = normalize_quotes(
            raw,
            metadata,
            config=config,
            categories=categories,
            start=start,
            end=end,
            compute_deltas=False,
        )
        if not norm.empty:
            chunks.append(norm)

    result = pd.concat(chunks, ignore_index=True) if chunks else pd.DataFrame()
    if not result.empty:
        result = result.sort_values(["slug", "segment", "ts"])
        result = compute_probability_deltas(
            result.drop(columns=["poly_delta_10m", "poly_delta_1h", "poly_velocity_1h"])
        )
        result = result.sort_values(["ts", "slug"]).reset_index(drop=True)

    output.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(output, index=False)

    themes = (
        result.groupby("theme")["slug"].nunique().sort_values(ascending=False).to_dict()
        if not result.empty
        else {}
    )
    return {
        "status": "READY",
        "archive_root": str(root),
        "output": str(output),
        "files_scanned": files_scanned,
        "raw_in_scope_rows": raw_rows,
        "canonical_rows": len(result),
        "market_count": int(result["slug"].nunique()) if not result.empty else 0,
        "themes": {str(k): int(v) for k, v in themes.items()},
        "known_outage_start": KNOWN_OUTAGE_START.isoformat(),
        "known_outage_end": KNOWN_OUTAGE_END.isoformat(),
        "delta_guard": "same slug + same segment + exact lag timestamp",
        "price_semantics": "book midpoint, not executed trade",
    }


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Offline public prediction-market archive importer")
    p.add_argument("--archive-root", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--config", default=str(DEFAULT_CONFIG))
    p.add_argument(
        "--categories",
        default=",".join(sorted(DEFAULT_CATEGORIES)),
        help="comma-separated archive categories",
    )
    p.add_argument("--start")
    p.add_argument("--end")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    config = read_config(Path(args.config))
    categories = {x.strip().lower() for x in args.categories.split(",") if x.strip()}
    start = pd.Timestamp(args.start, tz="UTC") if args.start else None
    end = pd.Timestamp(args.end, tz="UTC") if args.end else None
    summary = build_archive(
        Path(args.archive_root),
        Path(args.output),
        config=config,
        categories=categories,
        start=start,
        end=end,
    )
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
