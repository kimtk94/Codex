from pathlib import Path

import pandas as pd

from research.quant_stack import prediction_market_vike_blind_bridge_v0 as blind


def _reference(slugs=2, points=18, start="2026-09-08T00:00:00Z"):
    rows = []
    t0 = pd.Timestamp(start)
    for s in range(slugs):
        slug = f"cpic-test-{s}-gt"
        for i in range(points):
            p = 0.15 + 0.03 * s + 0.01 * i
            rows.append(
                {
                    "slug": slug,
                    "ts": t0 + pd.Timedelta(minutes=10 * i),
                    "probability": p,
                    "poly_delta_1h": 0.0,
                }
            )
    d = pd.DataFrame(rows)
    d["bucket_ms"] = (d["ts"].astype("int64") // 1_000_000).astype("int64")
    return d


def _aggregate_from_reference(ref: pd.DataFrame, path: Path):
    rows = []
    for slug, g in ref.groupby("slug"):
        idx = int(slug.split("-")[2])
        for row in g.itertuples(index=False):
            rows.append(
                {
                    "condition_id": f"cond-{idx}",
                    "token_id": f"yes-{idx}",
                    "bucket_ms": int(row.bucket_ms),
                    "midpoint": float(row.probability),
                    "bid": float(row.probability) - 0.005,
                    "ask": float(row.probability) + 0.005,
                    "source_ts": int(row.bucket_ms),
                }
            )
            rows.append(
                {
                    "condition_id": f"cond-{idx}",
                    "token_id": f"no-{idx}",
                    "bucket_ms": int(row.bucket_ms),
                    "midpoint": 1.0 - float(row.probability),
                    "bid": 1.0 - float(row.probability) - 0.005,
                    "ask": 1.0 - float(row.probability) + 0.005,
                    "source_ts": int(row.bucket_ms),
                }
            )
        for alt in range(2):
            for row in g.itertuples(index=False):
                rows.append(
                    {
                        "condition_id": f"noise-{idx}-{alt}",
                        "token_id": f"noise-token-{idx}-{alt}",
                        "bucket_ms": int(row.bucket_ms),
                        "midpoint": min(0.99, max(0.01, float(row.probability) + 0.08 + alt * 0.03)),
                        "bid": 0.1,
                        "ask": 0.2,
                        "source_ts": int(row.bucket_ms),
                    }
                )
    pd.DataFrame(rows).to_parquet(path, index=False)


def test_blind_identity_match_selects_unique_true_tokens(tmp_path: Path):
    ref = _reference(slugs=2, points=18)
    agg = tmp_path / "agg.parquet"
    _aggregate_from_reference(ref, agg)

    mapping, summary = blind.blind_identity_match(
        ref,
        str(agg),
        min_points=15,
        mae_max=0.03,
        corr_min=0.95,
        margin_min=0.005,
    )
    assert summary["identity_pass"] is True
    assert set(mapping["token_id"]) == {"yes-0", "yes-1"}
    assert mapping["condition_id"].is_unique


def test_validation_metrics_exact_match():
    ref = _reference(slugs=2, points=18)
    matched = ref.copy()
    matched["vike_probability"] = matched["probability"]
    matched["condition_id"] = matched["slug"].map(lambda x: "cond-" + x.split("-")[2])
    matched["token_id"] = matched["slug"].map(lambda x: "yes-" + x.split("-")[2])
    metrics, per_market = blind.validation_metrics(matched, shock_threshold=0.15)
    assert metrics["shared_markets"] == 2
    assert metrics["matched_points"] == 36
    assert metrics["median_market_mae"] == 0.0
    assert metrics["pooled_correlation"] == 1.0
    assert len(per_market) == 2


def test_archive_url_family_layout():
    assert blind.archive_url(
        "https://data.vike.io/archive",
        "other",
        "other",
        "2026-09-08",
    ) == (
        "https://data.vike.io/archive/venue=polymarket/"
        "asset=other/tenor=other/date=2026-09-08/l1_quotes.parquet"
    )


def test_source_has_no_execution_side_effects():
    source = Path(blind.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "r51_mutated = True"):
        assert forbidden not in source
