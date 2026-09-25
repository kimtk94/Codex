import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "research" / "r7_information_layer_readiness.py"
spec = importlib.util.spec_from_file_location("r7", P)
r7 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r7)


def base_stats():
    return {
        "macro_release": {
            "n": 200,
            "actual_rate": 0.99,
            "consensus_rate": 0.95,
            "good_time_rate": 0.99,
            "lookahead_violations": 0,
            "span_days": 900,
        },
        "macro_repricing": {
            "n": 180,
            "coverage_vs_macro": 0.90,
            "lookahead_violations": 0,
        },
        "company_news": {
            "n": 8000,
            "symbols": 90,
            "avg_coverage": 0.80,
            "span_days": 500,
        },
        "earnings": {
            "pit_table_present": True,
            "candidate_tables": ["earnings_revision_observation"],
        },
    }


def test_all_ready():
    x = r7.assess(base_stats())
    assert x["macro_consensus_surprise"] == "READY"
    assert x["macro_event_repricing"] == "READY"
    assert x["company_news"] == "READY"
    assert x["earnings_revisions"] == "READY"
    assert len(x["r7_1_runnable_candidates"]) == 3


def test_macro_consensus_missing_blocks_macro_candidate():
    s = base_stats()
    s["macro_release"]["consensus_rate"] = 0.2
    x = r7.assess(s)
    assert x["macro_consensus_surprise"] == "BLOCKED"
    assert "R7C1_MACRO_EVENT_HGB" not in x["r7_1_runnable_candidates"]


def test_news_requires_symbol_level_depth():
    s = base_stats()
    s["company_news"]["symbols"] = 1
    x = r7.assess(s)
    assert x["company_news"] == "BLOCKED"
    assert "R7C2_COMPANY_NEWS_HGB" not in x["r7_1_runnable_candidates"]


def test_earnings_is_fail_closed():
    s = base_stats()
    s["earnings"]["pit_table_present"] = False
    x = r7.assess(s)
    assert x["earnings_revisions"] == "BLOCKED"
    assert "R7C3_EARNINGS_REV_HGB" not in x["r7_1_runnable_candidates"]
