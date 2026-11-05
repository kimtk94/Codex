from pathlib import Path

import pandas as pd
import pytest

from research.quant_stack import prediction_market_oos_watch_v0 as watch


def test_release_tag_ordering():
    assert watch.is_newer_release("data-2026-09-14", "data-2026-09-13") is True
    assert watch.is_newer_release("data-2026-10-01", "data-2026-09-13") is True
    assert watch.is_newer_release("data-2026-09-13", "data-2026-09-13") is False
    assert watch.is_newer_release("data-2026-09-12", "data-2026-09-13") is False


def test_select_archive_asset_requires_single_sha256_digest():
    release = {
        "assets": [
            {
                "name": "polymarket-orderbook-2026-09-14.tar.zst",
                "digest": "sha256:" + "a" * 64,
            }
        ]
    }
    asset = watch.select_archive_asset(release)
    assert asset["name"].endswith(".tar.zst")

    with pytest.raises(RuntimeError):
        watch.select_archive_asset(
            {
                "assets": [
                    {
                        "name": "polymarket-orderbook-2026-09-14.tar.zst",
                        "digest": None,
                    }
                ]
            }
        )


def test_validate_archive_digest(tmp_path: Path):
    p = tmp_path / "x.bin"
    p.write_bytes(b"kalman")
    digest = "sha256:" + watch.sha256(p)
    assert watch.validate_archive_digest(p, digest) == digest.split(":", 1)[1]

    with pytest.raises(RuntimeError):
        watch.validate_archive_digest(p, "sha256:" + "0" * 64)


def test_parquet_range_uses_asset_loader(tmp_path: Path):
    p = tmp_path / "QQQ.parquet"
    pd.DataFrame(
        {
            "t": [
                "2026-09-14T13:00:00Z",
                "2026-09-14T14:00:00Z",
            ],
            "c": [100.0, 101.0],
        }
    ).to_parquet(p, index=False)

    info = watch.parquet_range(p, "QQQ")
    assert info["exists"] is True
    assert info["rows"] == 2
    assert info["max_ts"] == "2026-09-14T14:00:00+00:00"


def test_no_trade_or_r51_side_effect_symbols_present():
    source = Path(watch.__file__).read_text()
    forbidden = [
        "submit_order(",
        "place_order(",
        "trade_execution_allowed = True",
        "r51_mutated = True",
    ]
    for token in forbidden:
        assert token not in source
