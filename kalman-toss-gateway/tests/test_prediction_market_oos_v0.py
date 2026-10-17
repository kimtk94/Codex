import pandas as pd

from research.quant_stack import prediction_market_oos_v0 as oos


def spec():
    return {
        "hypothesis_id": "TEST",
        "frozen_at_utc": "2026-10-07T12:55:00Z",
        "discovery": {
            "data_end_utc": "2026-09-13T11:50:00Z",
        },
        "hypothesis": {
            "shock_threshold": 0.15,
            "dominant_channel": "INFLATION_UPSIDE",
            "symbol": "QQQ",
            "horizon_bars": 7,
            "expected_direction": "DOWNSIDE",
            "max_entry_lag_minutes": 90,
        },
        "confirmatory_gate": {
            "n_min": 3,
            "unique_dates_min": 3,
            "hit_rate_min": 0.50,
            "positive_date_rate_min": 0.50,
            "mean_signed_return_gt": 0.0,
            "cluster_bootstrap_ci_low_gt": -1.0,
            "cluster_signflip_p_max": 1.0,
        },
        "safety": {
            "research_only": True,
            "auto_promote": False,
            "r51_mutation_allowed": False,
            "trade_execution_allowed": False,
        },
    }


def prediction_rows():
    rows = [
        {
            "ts": "2026-09-13T11:50:00Z",
            "slug": "boundary-row",
            "question": "CPI above boundary?",
            "theme": "INFLATION",
            "semantic_channel": "INFLATION_UPSIDE",
            "risk_prior_sign": -1,
            "poly_delta_1h": 0.30,
        }
    ]
    for day in ("2026-09-14", "2026-09-15", "2026-09-16"):
        rows.append(
            {
                "ts": f"{day}T14:10:00Z",
                "slug": f"cpi-{day}",
                "question": f"CPI above target {day}?",
                "theme": "INFLATION",
                "semantic_channel": "INFLATION_UPSIDE",
                "risk_prior_sign": -1,
                "poly_delta_1h": 0.20,
            }
        )
    return pd.DataFrame(rows)


def declining_asset():
    rows = []
    for day in ("2026-09-14", "2026-09-15", "2026-09-16"):
        start = pd.Timestamp(f"{day}T14:30:00Z")
        for i in range(8):
            rows.append(
                {
                    "ts": start + pd.Timedelta(hours=i),
                    "price": 100.0 - i,
                    "symbol": "QQQ",
                }
            )
    frame = pd.DataFrame(rows).sort_values("ts").reset_index(drop=True)
    for bars in (1, 4, 7):
        frame[f"fwd_return_{bars}bar"] = frame["price"].shift(-bars) / frame["price"] - 1.0
    return frame


def test_strict_oos_excludes_discovery_boundary():
    out = oos.filter_strict_oos(prediction_rows(), "2026-09-13T11:50:00Z")
    assert len(out) == 3
    assert (out["ts"] > pd.Timestamp("2026-09-13T11:50:00Z")).all()


def test_frozen_hypothesis_can_pass_without_auto_promotion():
    result, rows = oos.evaluate_frozen_hypothesis(
        prediction_rows(),
        declining_asset(),
        spec(),
        bootstrap_iterations=200,
    )
    assert result["status"] == "PASS_CONFIRMATORY_GATE"
    assert result["metrics"]["bars"] == 7
    assert result["metrics"]["hit_rate"] == 1.0
    assert result["production_promotion"] is False
    assert result["r51_mutated"] is False
    assert result["auto_promote"] is False
    assert len(rows) == 3


def test_discovery_only_data_waits_for_oos():
    frame = prediction_rows().iloc[:1].copy()
    result, rows = oos.evaluate_frozen_hypothesis(
        frame,
        declining_asset(),
        spec(),
        bootstrap_iterations=100,
    )
    assert result["status"] == "WAITING_FOR_OOS_DATA"
    assert rows.empty
