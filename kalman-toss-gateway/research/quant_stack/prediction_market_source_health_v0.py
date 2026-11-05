from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import numpy as np


def recent_snapshot_counts(
    sqlite_path: Path,
    *,
    exclude_observed_at: str | None,
    limit: int,
) -> list[int]:
    if not sqlite_path.exists():
        return []
    con = sqlite3.connect(sqlite_path)
    try:
        if exclude_observed_at is None:
            rows = con.execute(
                """
                SELECT observed_at, COUNT(*) AS n
                FROM snapshots
                GROUP BY observed_at
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        else:
            rows = con.execute(
                """
                SELECT observed_at, COUNT(*) AS n
                FROM snapshots
                WHERE observed_at <> ?
                GROUP BY observed_at
                ORDER BY observed_at DESC
                LIMIT ?
                """,
                (exclude_observed_at, int(limit)),
            ).fetchall()
    finally:
        con.close()
    return [int(row[1]) for row in rows]


def evaluate_source_health(
    collect_status: dict[str, Any],
    *,
    recent_counts: list[int],
    gate: dict[str, Any],
) -> dict[str, Any]:
    discovered = int(collect_status.get("discovered_markets") or 0)
    stored = int(collect_status.get("stored_snapshots") or 0)
    failures = len(collect_status.get("request_failures") or [])
    stored_ratio = stored / discovered if discovered > 0 else 0.0
    failure_rate = failures / discovered if discovered > 0 else 1.0

    max_deviation = collect_status.get("max_midpoint_vs_current")
    max_deviation = (
        float(max_deviation) if max_deviation is not None else None
    )

    baseline_ready = (
        len(recent_counts) >= int(gate["recent_baseline_min_cycles"])
    )
    recent_median = (
        float(np.median(recent_counts)) if recent_counts else None
    )
    recent_ratio = (
        stored / recent_median
        if baseline_ready and recent_median and recent_median > 0
        else None
    )

    checks = {
        "min_discovered_markets": (
            discovered >= int(gate["min_discovered_markets"])
        ),
        "min_stored_to_discovered_ratio": (
            stored_ratio >= float(gate["min_stored_to_discovered_ratio"])
        ),
        "max_request_failure_rate": (
            failure_rate <= float(gate["max_request_failure_rate"])
        ),
        "max_midpoint_vs_current_abs": (
            max_deviation is not None
            and max_deviation <= float(gate["max_midpoint_vs_current_abs"])
        ),
        "min_stored_vs_recent_median_ratio": (
            True
            if not baseline_ready
            else recent_ratio is not None
            and recent_ratio
            >= float(gate["min_stored_vs_recent_median_ratio"])
        ),
    }
    passed = all(checks.values())
    return {
        "status": (
            "SOURCE_HEALTH_PASS" if passed else "SOURCE_HEALTH_FAIL"
        ),
        "passed": passed,
        "checks": checks,
        "metrics": {
            "discovered_markets": discovered,
            "stored_snapshots": stored,
            "stored_to_discovered_ratio": stored_ratio,
            "request_failures": failures,
            "request_failure_rate": failure_rate,
            "max_midpoint_vs_current_abs": max_deviation,
            "recent_baseline_cycles_available": len(recent_counts),
            "recent_baseline_ready": baseline_ready,
            "recent_stored_median": recent_median,
            "stored_vs_recent_median_ratio": recent_ratio,
        },
        "thresholds": gate,
    }


def rollback_cycle(sqlite_path: Path, observed_at: str) -> int:
    if not sqlite_path.exists():
        return 0
    con = sqlite3.connect(sqlite_path)
    try:
        before = con.total_changes
        con.execute(
            "DELETE FROM snapshots WHERE observed_at = ?",
            (observed_at,),
        )
        deleted = con.total_changes - before
        con.commit()
    finally:
        con.close()
    return int(deleted)


def evaluate_and_rollback_if_needed(
    collect_status: dict[str, Any],
    *,
    sqlite_path: Path,
    gate: dict[str, Any],
) -> dict[str, Any]:
    if not bool(gate.get("enabled")):
        return {
            "status": "SOURCE_HEALTH_DISABLED",
            "passed": True,
            "checks": {},
            "metrics": {},
            "thresholds": gate,
            "rolled_back_rows": 0,
        }

    observed_at = str(collect_status.get("observed_at") or "")
    recent = recent_snapshot_counts(
        sqlite_path,
        exclude_observed_at=observed_at or None,
        limit=int(gate["recent_baseline_cycles"]),
    )
    result = evaluate_source_health(
        collect_status,
        recent_counts=recent,
        gate=gate,
    )
    rolled_back = 0
    if not result["passed"] and observed_at:
        rolled_back = rollback_cycle(sqlite_path, observed_at)
    result["rolled_back_rows"] = int(rolled_back)
    return result
