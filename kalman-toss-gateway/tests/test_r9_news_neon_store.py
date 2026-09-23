from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest


P = Path(__file__).resolve().parents[1] / "research" / "r9_news_neon_store.py"
spec = importlib.util.spec_from_file_location("r9neon", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def _registry() -> pd.DataFrame:
    rows = []
    for i in range(93):
        symbol = f"S{i:02d}"
        alias = f"Alias{i}"
        rows.append(
            {
                "symbol": symbol,
                "company_name": f"Company {i}",
                "alias": alias,
                "alias_lower": alias.lower(),
                "ngram_order": 1,
                "status": "SUPPORTED",
            }
        )
    return pd.DataFrame(rows)


def test_registry_requires_frozen_93_supported_symbols():
    x = m.normalize_registry(_registry())
    assert len(x) == 93
    assert x["status"].eq("SUPPORTED").all()

    bad = _registry().iloc[:-1].copy()
    with pytest.raises(ValueError, match="93-symbol"):
        m.normalize_registry(bad)


def test_registry_rejects_unsupported_alias():
    x = _registry()
    x.loc[0, "status"] = "NEEDS_OVERRIDE"
    with pytest.raises(ValueError, match="unsupported aliases"):
        m.normalize_registry(x)


def test_mentions_are_normalized_and_duplicate_safe():
    symbols = set(_registry()["symbol"])
    x = pd.DataFrame(
        [
            {"symbol": "S00", "day_utc": 20260901, "mention_count": 3},
            {"symbol": "S01", "day_utc": 20260901, "mention_count": 0},
        ]
    )
    out = m.normalize_mentions(x, symbols)
    assert str(out.iloc[0]["day_utc"]) == "2026-09-01"
    assert out["mention_count"].tolist() == [3, 0]

    dup = pd.concat([x, x.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        m.normalize_mentions(dup, symbols)


def test_mentions_reject_negative_and_unknown_symbol():
    symbols = set(_registry()["symbol"])
    neg = pd.DataFrame(
        [{"symbol": "S00", "day_utc": 20260901, "mention_count": -1}]
    )
    with pytest.raises(ValueError, match="nonnegative"):
        m.normalize_mentions(neg, symbols)

    unknown = pd.DataFrame(
        [{"symbol": "AMD", "day_utc": 20260901, "mention_count": 1}]
    )
    with pytest.raises(ValueError, match="outside frozen registry"):
        m.normalize_mentions(unknown, symbols)


def test_manifest_is_hard_research_only():
    with tempfile.TemporaryDirectory() as tmp:
        p = Path(tmp) / "manifest.json"
        p.write_text(
            json.dumps(
                {
                    "research_only": True,
                    "production_changed": False,
                }
            ),
            encoding="utf-8",
        )
        out = m.load_manifest(p)
        assert out["research_only"] is True

        p.write_text(
            json.dumps(
                {
                    "research_only": False,
                    "production_changed": False,
                }
            ),
            encoding="utf-8",
        )
        with pytest.raises(ValueError, match="research_only"):
            m.load_manifest(p)


def test_neon_schema_is_research_isolated():
    schema = (
        Path(__file__).resolve().parents[1]
        / "research"
        / "r9_news_neon_schema.sql"
    ).read_text(encoding="utf-8")
    assert "research.r9_news_alias_registry" in schema
    assert "research.r9_news_mentions_daily" in schema
    assert "research.r9_news_manifest" in schema
    assert "strategy_signal" not in schema
    assert "dashboard_snapshot" not in schema
