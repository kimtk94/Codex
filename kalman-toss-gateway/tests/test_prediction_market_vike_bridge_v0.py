from pathlib import Path

import numpy as np
import pandas as pd

from research.quant_stack import prediction_market_vike_bridge_v0 as bridge


def test_manifest_summary_counts_post_cutoff_other_l1():
    manifest = {
        "generated_at": "2026-10-07T00:45:08Z",
        "license": {"name": "CC BY 4.0"},
        "dates": [{"date": "2026-09-13"}, {"date": "2026-09-14"}, {"date": "2026-10-06"}],
        "families": [
            {
                "asset": "other",
                "tenor": "other",
                "date": "2026-09-14",
                "streams": {"l1_quotes": {"rows": 10, "bytes": 100}},
            },
            {
                "asset": "other",
                "tenor": "other",
                "date": "2026-10-06",
                "streams": {"l1_quotes": {"rows": 20, "bytes": 200}},
            },
            {
                "asset": "btc",
                "tenor": "5m",
                "date": "2026-10-06",
                "streams": {"l1_quotes": {"rows": 999, "bytes": 999}},
            },
        ],
    }
    out = bridge.summarize_manifest(manifest, cutoff_date="2026-09-13")
    assert out["archive_latest"] == "2026-10-06"
    assert out["post_cutoff_family_days"] == 2
    assert out["post_cutoff_l1_rows"] == 30
    assert out["post_cutoff_l1_bytes"] == 300


def test_canonicalize_l1_uses_epoch_milliseconds_and_last_quote():
    markets = pd.DataFrame(
        [
            {
                "condition_id": "c1",
                "slug": "cpic-test-gt3pt0pct",
                "token0": "yes0",
                "token1": "no0",
            }
        ]
    )
    raw = pd.DataFrame(
        [
            {"token_id": "yes0", "condition_id": "c1", "ts": 1788800400000, "bid": 0.39, "ask": 0.41, "bid_size": 1, "ask_size": 1},
            {"token_id": "yes0", "condition_id": "c1", "ts": 1788800999000, "bid": 0.40, "ask": 0.42, "bid_size": 1, "ask_size": 1},
            {"token_id": "no0", "condition_id": "c1", "ts": 1788800999000, "bid": 0.58, "ask": 0.60, "bid_size": 1, "ask_size": 1},
        ]
    )
    out = bridge.canonicalize_l1(raw, markets, bucket_minutes=10)
    assert len(out) == 2
    yes = out[out["token_position"] == 0].iloc[0]
    assert abs(float(yes["midpoint"]) - 0.41) < 1e-12
    assert str(yes["ts"].tzinfo) == "UTC"


def synthetic_bridge_inputs(markets: int = 8, points: int = 180):
    refs = []
    vikes = []
    start = pd.Timestamp("2026-09-08T00:00:00Z")
    for m in range(markets):
        slug = f"cpic-test-{m}-gt3pt{m}pct"
        for i in range(points):
            ts = start + pd.Timedelta(minutes=10 * i)
            block = (i // 12) % 2
            p = 0.2 if block == 0 else 0.8
            refs.append(
                {
                    "slug": slug,
                    "ts": ts,
                    "probability": p,
                }
            )
            vikes.extend(
                [
                    {
                        "slug": slug,
                        "token_position": 0,
                        "ts": ts,
                        "midpoint": p,
                        "bid": p - 0.005,
                        "ask": p + 0.005,
                    },
                    {
                        "slug": slug,
                        "token_position": 1,
                        "ts": ts,
                        "midpoint": 1.0 - p,
                        "bid": 1.0 - p - 0.005,
                        "ask": 1.0 - p + 0.005,
                    },
                ]
            )
    ref = pd.DataFrame(refs).sort_values(["slug", "ts"]).reset_index(drop=True)
    prior = ref[["slug", "ts", "probability"]].copy()
    prior["ts"] = prior["ts"] + pd.Timedelta(hours=1)
    prior = prior.rename(columns={"probability": "prior"})
    ref = ref.merge(prior, on=["slug", "ts"], how="left")
    ref["poly_delta_1h"] = ref["probability"] - ref["prior"]
    return ref, pd.DataFrame(vikes)


def test_bridge_metrics_pass_exact_measurement_bridge():
    ref, vike = synthetic_bridge_inputs()
    metrics, market_metrics = bridge.bridge_metrics(
        ref,
        vike,
        shock_threshold=0.15,
    )
    gate = {
        "shared_markets_min": 8,
        "matched_points_min": 1000,
        "orientation_consistency_min": 0.90,
        "median_market_mae_max": 0.03,
        "pooled_correlation_min": 0.95,
        "median_abs_delta_1h_diff_max": 0.02,
        "shock_threshold": 0.15,
        "shock_pairs_min": 5,
        "shock_sign_agreement_min": 0.90,
    }
    checks = bridge.apply_gate(metrics, gate)
    assert all(checks.values())
    assert metrics["selected_token_position_mode"] == 0
    assert metrics["orientation_consistency"] == 1.0
    assert metrics["median_market_mae"] == 0.0
    assert metrics["shock_sign_agreement"] == 1.0
    assert len(market_metrics) == 8


def test_bridge_detects_token_position_one_when_needed():
    ref, vike = synthetic_bridge_inputs()
    flipped = vike.copy()
    flipped["token_position"] = 1 - flipped["token_position"]
    metrics, _ = bridge.bridge_metrics(ref, flipped, shock_threshold=0.15)
    assert metrics["selected_token_position_mode"] == 1
    assert metrics["orientation_consistency"] == 1.0


def test_bridge_gate_fails_bad_measurement():
    ref, vike = synthetic_bridge_inputs()
    rng = np.random.default_rng(7)
    vike = vike.copy()
    vike["midpoint"] = rng.uniform(0.05, 0.95, len(vike))
    metrics, _ = bridge.bridge_metrics(ref, vike, shock_threshold=0.15)
    gate = {
        "shared_markets_min": 8,
        "matched_points_min": 1000,
        "orientation_consistency_min": 0.90,
        "median_market_mae_max": 0.03,
        "pooled_correlation_min": 0.95,
        "median_abs_delta_1h_diff_max": 0.02,
        "shock_threshold": 0.15,
        "shock_pairs_min": 5,
        "shock_sign_agreement_min": 0.90,
    }
    checks = bridge.apply_gate(metrics, gate)
    assert not all(checks.values())


def test_source_has_no_trade_or_r51_side_effects():
    source = Path(bridge.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "r51_mutated = True"):
        assert forbidden not in source
