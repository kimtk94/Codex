from pathlib import Path

import pandas as pd
import pytest

from research.quant_stack import qqq_1h_iex_updater_v0 as updater


def bars(start: str, count: int = 4, base: float = 100.0) -> pd.DataFrame:
    ts = pd.date_range(start, periods=count, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "c": [base + i + 0.5 for i in range(count)],
            "h": [base + i + 1.0 for i in range(count)],
            "l": [base + i - 1.0 for i in range(count)],
            "n": [100 + i for i in range(count)],
            "o": [base + i for i in range(count)],
            "t": ts,
            "v": [1000 + i for i in range(count)],
            "vw": [base + i + 0.25 for i in range(count)],
        }
    )[updater.BAR_COLUMNS]


def test_normalize_preserves_alpaca_schema():
    frame = bars("2026-09-01T13:00:00Z")
    out = updater.normalize_bars(frame)
    assert list(out.columns) == updater.BAR_COLUMNS
    assert str(out["t"].dtype) == "datetime64[ns, UTC]"
    assert str(out["n"].dtype) == "int64"
    assert str(out["v"].dtype) == "int64"


def test_build_candidate_appends_only_after_canonical_max():
    existing = bars("2026-09-01T13:00:00Z", count=4)
    fresh = pd.concat(
        [
            existing.iloc[2:].copy(),
            bars("2026-09-01T17:00:00Z", count=2, base=104.0),
        ],
        ignore_index=True,
    )
    candidate, audit = updater.build_candidate(
        existing,
        fresh,
        now_utc=pd.Timestamp("2026-09-01T20:30:00Z"),
    )
    assert audit["overlap_rows"] == 2
    assert audit["appended_rows"] == 2
    assert len(candidate) == 6
    pd.testing.assert_frame_equal(
        candidate.iloc[: len(existing)].reset_index(drop=True),
        existing.reset_index(drop=True),
    )


def test_overlap_mismatch_fails_closed():
    existing = bars("2026-09-01T13:00:00Z", count=4)
    fresh = existing.iloc[2:].copy()
    fresh.loc[fresh.index[0], "c"] += 0.01
    with pytest.raises(RuntimeError, match="overlap mismatch"):
        updater.build_candidate(
            existing,
            fresh,
            now_utc=pd.Timestamp("2026-09-01T20:30:00Z"),
        )


def test_incomplete_current_hour_is_not_appended():
    existing = bars("2026-09-01T13:00:00Z", count=2)
    fresh = pd.concat(
        [
            existing.iloc[-1:].copy(),
            bars("2026-09-01T15:00:00Z", count=2, base=102.0),
        ],
        ignore_index=True,
    )
    candidate, audit = updater.build_candidate(
        existing,
        fresh,
        now_utc=pd.Timestamp("2026-09-01T16:20:00Z"),
    )
    assert audit["appended_rows"] == 1
    assert candidate["t"].max() == pd.Timestamp("2026-09-01T15:00:00Z")


def test_load_canonical_requires_exact_schema(tmp_path: Path):
    path = tmp_path / "bad.parquet"
    frame = bars("2026-09-01T13:00:00Z").drop(columns=["vw"])
    frame.to_parquet(path, index=False)
    with pytest.raises(ValueError, match="schema mismatch"):
        updater.load_canonical(path)


def test_no_live_trade_side_effect_tokens_present():
    source = Path(updater.__file__).read_text()
    forbidden = ["submit_order(", "place_order(", "r51_mutated = True"]
    for token in forbidden:
        assert token not in source


def test_drive_backup_remote_is_versioned_same_folder():
    out = updater.drive_backup_remote(
        "gdrive:US_ETF/history_1h/QQQ_1h_2017plus.parquet",
        "20261007T130000Z",
    )
    assert out == (
        "gdrive:US_ETF/history_1h/"
        "QQQ_1h_2017plus.pre_qqq_update_20261007T130000Z.parquet"
    )
