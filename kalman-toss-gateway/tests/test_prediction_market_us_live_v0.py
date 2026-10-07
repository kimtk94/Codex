from pathlib import Path
import sqlite3

import pandas as pd

from research.quant_stack import prediction_market_us_live_v0 as us


def test_parse_bbo_midpoint_matches_current_px():
    payload = {
        "marketData": {
            "marketSlug": "cpic-test-gt0pt2pct",
            "state": "MARKET_STATE_OPEN",
            "bestBid": {"value": "0.3700", "currency": "USD"},
            "bestAsk": {"value": "0.3800", "currency": "USD"},
            "currentPx": {"value": "0.3750", "currency": "USD"},
            "lastTradePx": {"value": "0.3800", "currency": "USD"},
            "longQuote": {"value": "0.3800", "currency": "USD"},
            "shortQuote": {"value": "0.63", "currency": "USD"},
            "lastPriceSample": {"ts": "2026-10-07T14:39:38Z"},
        }
    }
    out = us.parse_bbo(payload)
    assert out["bid"] == 0.37
    assert out["ask"] == 0.38
    assert out["midpoint"] == 0.375
    assert out["current_px"] == 0.375
    assert out["midpoint_vs_current"] == 0.0


def test_parse_bbo_rejects_one_sided_midpoint():
    payload = {
        "marketData": {
            "marketSlug": "resolved",
            "bestBid": None,
            "bestAsk": None,
            "currentPx": {"value": "0.99"},
        }
    }
    out = us.parse_bbo(payload)
    assert out["midpoint"] is None


def _insert_snapshot(con, ts, slug, midpoint, bid=None, ask=None):
    bid = midpoint - 0.005 if bid is None else bid
    ask = midpoint + 0.005 if ask is None else ask
    con.execute(
        """
        INSERT INTO snapshots (
            observed_at, slug, market_id, event_id, event_slug,
            question, title, category, theme, semantic_channel,
            risk_prior_sign, state, bid, ask, midpoint, spread,
            current_px, last_trade, shares_traded, open_interest,
            bid_depth, ask_depth, last_sample_ts, midpoint_vs_current,
            source
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            ts, slug, "1", "2", "evt",
            "CPI YoY in September", "Above 3.0%", "macro", "INFLATION",
            "INFLATION_UPSIDE", -1, "MARKET_STATE_OPEN",
            bid, ask, midpoint, ask-bid, midpoint, midpoint,
            100, 20, 3, 3, ts, 0.0, "test",
        ),
    )


def test_canonical_exact_one_hour_delta_and_gap_guard(tmp_path: Path):
    db = tmp_path / "snap.sqlite3"
    con = us.init_db(db)
    slug = "cpic-test-gt3pt0pct"
    # First segment: exact 10-minute grid with a 1h comparison.
    for i in range(7):
        ts = pd.Timestamp("2026-10-08T00:01:00Z") + pd.Timedelta(minutes=10*i)
        _insert_snapshot(con, ts.isoformat(), slug, 0.20 + 0.01*i)
    # Gap >30m starts a new segment; must not compute across it.
    _insert_snapshot(con, "2026-10-08T02:01:00+00:00", slug, 0.70)
    con.commit()
    con.close()

    out = tmp_path / "canonical.parquet"
    status = us.build_canonical(
        sqlite_path=db,
        output_path=out,
        bucket_minutes=10,
        gap_segment_minutes=30,
    )
    assert status["rows"] == 8
    d = pd.read_parquet(out)
    one = d[d["ts"] == pd.Timestamp("2026-10-08T01:00:00Z")].iloc[0]
    assert abs(float(one["poly_delta_1h"]) - 0.06) < 1e-12
    after_gap = d[d["ts"] == pd.Timestamp("2026-10-08T02:00:00Z")].iloc[0]
    assert pd.isna(after_gap["poly_delta_1h"])
    assert int(d["segment"].nunique()) == 2


def test_same_bucket_keeps_last_observation(tmp_path: Path):
    db = tmp_path / "snap.sqlite3"
    con = us.init_db(db)
    slug = "cpic-test-gt3pt0pct"
    _insert_snapshot(con, "2026-10-08T00:01:00+00:00", slug, 0.20)
    _insert_snapshot(con, "2026-10-08T00:09:00+00:00", slug, 0.30)
    con.commit()
    con.close()

    out = tmp_path / "canonical.parquet"
    us.build_canonical(
        sqlite_path=db,
        output_path=out,
        bucket_minutes=10,
        gap_segment_minutes=30,
    )
    d = pd.read_parquet(out)
    assert len(d) == 1
    assert float(d.iloc[0]["probability"]) == 0.30


def test_source_has_no_auth_or_order_side_effects():
    source = Path(us.__file__).read_text()
    forbidden = [
        "Authorization:",
        "X-API-Key",
        "submit_order(",
        "place_order(",
        "trade_execution = True",
    ]
    for token in forbidden:
        assert token not in source
