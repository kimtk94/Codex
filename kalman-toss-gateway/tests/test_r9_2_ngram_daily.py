import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

import r9_2_ngram_daily as m


def _registry():
    rows = []
    for i in range(93):
        sym = f"S{i:03d}"
        rows.append(
            {
                "symbol": sym,
                "company_name": sym,
                "alias": sym.lower(),
                "alias_lower": sym.lower(),
                "ngram_order": 1,
                "status": "SUPPORTED",
            }
        )
    return pd.DataFrame(rows)


def test_calendar_completion_is_exact_93_per_day(tmp_path):
    reg = _registry()
    csv = tmp_path / "q.csv"
    pd.DataFrame(
        [
            {"symbol": "S000", "day_utc": 20260902, "mention_count": 5},
            {"symbol": "S001", "day_utc": 20260903, "mention_count": 2},
        ]
    ).to_csv(csv, index=False)

    out = m.normalize_query_result(
        csv,
        reg,
        pd.Timestamp("2026-09-02", tz="UTC"),
        pd.Timestamp("2026-09-04", tz="UTC"),
    )
    assert len(out) == 93 * 2
    assert out.groupby("day").size().eq(93).all()
    assert int(
        out.loc[
            (out["symbol"] == "S002")
            & (out["day"] == pd.Timestamp("2026-09-02", tz="UTC")),
            "mention_count",
        ].iloc[0]
    ) == 0


def test_incremental_sql_is_strictly_bounded(tmp_path):
    reg = _registry()
    reg_path = tmp_path / "reg.csv"
    sql_path = tmp_path / "q.sql"
    reg.to_csv(reg_path, index=False)

    m.build_daily_sql(
        reg_path,
        sql_path,
        pd.Timestamp("2026-09-02", tz="UTC"),
        pd.Timestamp("2026-09-04", tz="UTC"),
    )
    sql = sql_path.read_text()
    assert "DATE >= 20260902000000" in sql
    assert "DATE < 20260904000000" in sql
    assert "LANG = 'ENGLISH'" in sql


def test_snapshot_feature_asof_is_day_plus_one():
    reg = _registry()
    rows = []
    for day in pd.date_range("2026-08-01", "2026-09-03", tz="UTC"):
        for sym in reg["symbol"]:
            rows.append(
                {
                    "symbol": sym,
                    "day_utc": int(day.strftime("%Y%m%d")),
                    "mention_count": 1 if sym == "S000" else 0,
                }
            )
    hist = pd.DataFrame(rows)
    snap = m.build_snapshot(
        hist,
        reg["symbol"].tolist(),
        pd.Timestamp("2026-09-04", tz="UTC"),
        pd.Timestamp("2026-09-02", tz="UTC"),
    )
    row = snap.loc[
        (snap["symbol"] == "S000")
        & (snap["news_day_used"] == pd.Timestamp("2026-09-03").date())
    ].iloc[0]
    assert row["feature_as_of"] == pd.Timestamp("2026-09-04", tz="UTC")
    assert row["source_complete"]


def test_unknown_symbol_is_rejected(tmp_path):
    reg = _registry()
    csv = tmp_path / "q.csv"
    pd.DataFrame(
        [{"symbol": "BAD", "day_utc": 20260902, "mention_count": 1}]
    ).to_csv(csv, index=False)

    try:
        m.normalize_query_result(
            csv,
            reg,
            pd.Timestamp("2026-09-02", tz="UTC"),
            pd.Timestamp("2026-09-03", tz="UTC"),
        )
        assert False, "expected unknown symbol rejection"
    except RuntimeError as exc:
        assert "unknown" in str(exc).lower()
