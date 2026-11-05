from pathlib import Path
import sqlite3

from research.quant_stack import prediction_market_source_health_v0 as health


GATE = {
    "enabled": True,
    "min_discovered_markets": 8,
    "min_stored_to_discovered_ratio": 0.90,
    "max_request_failure_rate": 0.05,
    "max_midpoint_vs_current_abs": 0.02,
    "recent_baseline_cycles": 10,
    "recent_baseline_min_cycles": 5,
    "min_stored_vs_recent_median_ratio": 0.75,
    "fail_closed": True,
}


def _status(discovered=44, stored=44, failures=0, max_dev=0.0, observed="t-new"):
    return {
        "observed_at": observed,
        "discovered_markets": discovered,
        "stored_snapshots": stored,
        "request_failures": [{"x": 1}] * failures,
        "max_midpoint_vs_current": max_dev,
    }


def test_health_passes_normal_cycle():
    out = health.evaluate_source_health(
        _status(),
        recent_counts=[44, 44, 44, 44, 44],
        gate=GATE,
    )
    assert out["passed"] is True
    assert all(out["checks"].values())
    assert out["metrics"]["stored_vs_recent_median_ratio"] == 1.0


def test_health_fails_coverage_collapse():
    out = health.evaluate_source_health(
        _status(discovered=44, stored=20),
        recent_counts=[44, 44, 44, 44, 44],
        gate=GATE,
    )
    assert out["passed"] is False
    assert out["checks"]["min_stored_to_discovered_ratio"] is False
    assert out["checks"]["min_stored_vs_recent_median_ratio"] is False


def test_health_fails_request_errors_and_price_mismatch():
    out = health.evaluate_source_health(
        _status(failures=5, max_dev=0.03),
        recent_counts=[44, 44, 44, 44, 44],
        gate=GATE,
    )
    assert out["passed"] is False
    assert out["checks"]["max_request_failure_rate"] is False
    assert out["checks"]["max_midpoint_vs_current_abs"] is False


def test_baseline_gate_waits_until_five_cycles():
    out = health.evaluate_source_health(
        _status(discovered=10, stored=10),
        recent_counts=[44, 44, 44, 44],
        gate=GATE,
    )
    assert out["metrics"]["recent_baseline_ready"] is False
    assert out["checks"]["min_stored_vs_recent_median_ratio"] is True


def test_failed_cycle_is_removed_from_raw_db(tmp_path: Path):
    db = tmp_path / "raw.sqlite3"
    con = sqlite3.connect(db)
    con.execute("create table snapshots(observed_at text, slug text)")
    for cycle in range(5):
        con.executemany(
            "insert into snapshots values (?,?)",
            [(f"old-{cycle}", f"s{i}") for i in range(44)],
        )
    con.executemany(
        "insert into snapshots values (?,?)",
        [("bad-new", f"s{i}") for i in range(20)],
    )
    con.commit()
    con.close()

    result = health.evaluate_and_rollback_if_needed(
        _status(discovered=44, stored=20, observed="bad-new"),
        sqlite_path=db,
        gate=GATE,
    )
    assert result["passed"] is False
    assert result["rolled_back_rows"] == 20

    con = sqlite3.connect(db)
    try:
        remaining = con.execute(
            "select count(*) from snapshots where observed_at='bad-new'"
        ).fetchone()[0]
        total = con.execute("select count(*) from snapshots").fetchone()[0]
    finally:
        con.close()
    assert remaining == 0
    assert total == 220


def test_source_has_no_execution_side_effects():
    source = Path(health.__file__).read_text()
    for forbidden in ("submit_order(", "place_order(", "trade_execution = True"):
        assert forbidden not in source
