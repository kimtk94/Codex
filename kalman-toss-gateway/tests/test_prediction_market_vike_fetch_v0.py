from pathlib import Path

import pandas as pd

from research.quant_stack import prediction_market_vike_fetch_v0 as fetch


def test_date_rows_filters_family_and_window():
    manifest = {
        "families": [
            {
                "asset": "other",
                "tenor": "other",
                "date": "2026-09-08",
                "streams": {"l1_quotes": {"rows": 10, "bytes": 100}},
            },
            {
                "asset": "other",
                "tenor": "other",
                "date": "2026-09-14",
                "streams": {"l1_quotes": {"rows": 20, "bytes": 200}},
            },
            {
                "asset": "btc",
                "tenor": "5m",
                "date": "2026-09-10",
                "streams": {"l1_quotes": {"rows": 30, "bytes": 300}},
            },
        ]
    }
    out = fetch.date_rows(
        manifest,
        asset="other",
        tenor="other",
        start_date="2026-09-08",
        end_date="2026-09-13",
    )
    assert out == [{"date": "2026-09-08", "rows": 10, "bytes": 100}]


def test_archive_url_uses_family_layout():
    url = fetch.archive_url(
        "https://data.vike.io/archive",
        "other",
        "other",
        "2026-10-06",
    )
    assert url == (
        "https://data.vike.io/archive/venue=polymarket/"
        "asset=other/tenor=other/date=2026-10-06/l1_quotes.parquet"
    )


def test_filter_tokens_keeps_only_target_ids(tmp_path: Path):
    raw = tmp_path / "raw.parquet"
    out = tmp_path / "filtered.parquet"
    pd.DataFrame(
        {
            "token_id": ["a", "b", "c", "a"],
            "condition_id": ["x", "x", "y", "x"],
            "ts": [1, 2, 3, 4],
            "local_ts": [1, 2, 3, 4],
            "bid": [0.1, 0.2, 0.3, 0.4],
            "ask": [0.2, 0.3, 0.4, 0.5],
            "bid_size": [1, 1, 1, 1],
            "ask_size": [1, 1, 1, 1],
        }
    ).to_parquet(raw, index=False)

    audit = fetch.filter_tokens(raw, out, {"a", "c"})
    got = pd.read_parquet(out)
    assert audit["raw_rows"] == 4
    assert audit["kept_rows"] == 3
    assert set(got["token_id"].astype(str)) == {"a", "c"}


def test_source_has_no_execution_side_effects():
    source = Path(fetch.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "r51_mutated = True"):
        assert forbidden not in source
