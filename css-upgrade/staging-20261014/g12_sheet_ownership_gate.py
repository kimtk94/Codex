"""G12 Google Sheets ownership / reconciliation policy, synthetic-only.

WARNING: This simulates a safe *disjoint ownership* protocol; it is NOT a
Google Sheets client, not a replacement for current CSS, and not proof of
cross-service transactions or exactly-once delivery.

Each simulated row has a stable, immutable synthetic record_id. System writes
must not touch any user-editable tab/cell, insert/delete/sort rows or change
row identity. A lost API response is reconciled with a read-only observation,
not automatically treated as an acknowledged transaction.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Mapping
from g16_synthetic_pipeline import IsolationError, assert_fixture_mode


class BoundaryViolation(IsolationError):
    pass


SYS_TAB = "SYN_SYSTEM_OUTPUT"
CONTROL_TAB = "SYN_USER_CONTROLS"
OUTPUT_KEYS = frozenset({"stage", "attention", "latest_uid"})
USER_KEYS = frozenset({"hold", "skip", "restore", "prepayment", "notes"})
VALID_STAGES = frozenset({"SYN-SIF", "SYN-QC", "SYN-DATA"})
VALID_ATTENTION = frozenset({"Yes", "No"})


def _synthetic_key(key: str) -> None:
    if not isinstance(key, str) or not key.startswith("TEST-") or len(key) > 64:
        raise BoundaryViolation("only synthetic stable row keys")


def projection_digest(values: Mapping[str, str]) -> str:
    return hashlib.sha256(json.dumps(dict(values), sort_keys=True,
                                     separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class WritePlan:
    sheet_id: str
    tab: str
    operation: str
    record_id: str
    expected_row: int
    values: dict[str, str]

    def validate(self) -> None:
        assert_fixture_mode()
        if self.sheet_id != "TEST-SHEET" or self.tab != SYS_TAB:
            raise BoundaryViolation("writes to non-synthetic or user-owned tabs denied")
        if self.operation != "update_existing_cells":
            raise BoundaryViolation("structural or bulk destructive changes denied")
        _synthetic_key(self.record_id)
        if type(self.expected_row) is not int or self.expected_row < 2:
            raise BoundaryViolation("invalid stable row index")
        if type(self.values) is not dict or set(self.values) != OUTPUT_KEYS:
            raise BoundaryViolation("output fields must exactly match system-owned columns")
        if (self.values["stage"] not in VALID_STAGES
            or self.values["attention"] not in VALID_ATTENTION
            or not isinstance(self.values["latest_uid"], str)
            or not self.values["latest_uid"].startswith("SYN-")):
            raise BoundaryViolation("non-synthetic output payload")


class SyntheticSheet:
    """Untrusted API surface model. No atomic CAS, no external IO."""
    def __init__(self):
        assert_fixture_mode()
        self.row_registry: dict[str, int] = {}    # stable key -> physical row
        self.system: dict[str, dict[str, str]] = {}
        self.controls: dict[str, dict] = {}
        self.writes = 0
        self.control_writes_by_system = 0
        self.fail_before = False
        self.fail_after = False

    def register_fixture(self, record_id: str, row: int, controls: dict):
        _synthetic_key(record_id)
        if record_id in self.row_registry or row < 2 or row in self.row_registry.values():
            raise BoundaryViolation("duplicate or invalid row identity")
        if set(controls) != USER_KEYS:
            raise BoundaryViolation("invalid synthetic control fixture")
        self.row_registry[record_id] = row
        self.controls[record_id] = dict(controls)

    def user_edit(self, record_id: str, key: str, value):
        _synthetic_key(record_id)
        if key not in USER_KEYS or record_id not in self.row_registry:
            raise BoundaryViolation("unknown user control")
        self.controls[record_id][key] = value

    def user_reorder_row(self, record_id: str, new_row: int):
        """Models concurrent structural edit. Guard must block stale row."""
        if record_id not in self.row_registry:
            raise BoundaryViolation("unknown row")
        self.row_registry[record_id] = new_row

    def publish(self, plan: WritePlan):
        plan.validate()
        if plan.record_id not in self.row_registry:
            raise BoundaryViolation("unknown stable ID: no implicit append")
        if self.row_registry[plan.record_id] != plan.expected_row:
            raise BoundaryViolation("row identity moved since planned read")
        if self.fail_before:
            self.fail_before = False
            raise RuntimeError("SYN_WRITE_REJECTED_BEFORE_APPLY")
        self.system[plan.record_id] = dict(plan.values)
        self.writes += 1
        if self.fail_after:
            self.fail_after = False
            raise RuntimeError("SYN_RESPONSE_LOST_AFTER_APPLY")

    def observe(self, record_id: str, expected_row: int):
        """Read-only observed state: cannot prove who applied a given write."""
        _synthetic_key(record_id)
        if self.row_registry.get(record_id) != expected_row:
            return None
        return dict(self.system[record_id]) if record_id in self.system else None


@dataclass(frozen=True)
class Observation:
    outcome: str
    # CONFIRMED_STATE != proof of exactly-once. The previous call may or may
    # not have committed; only the currently observed state is confirmed.
    project_record_id: str


def reconcile_unknown_response(sheet: SyntheticSheet, plan: WritePlan) -> Observation:
    assert_fixture_mode()
    plan.validate()
    actual = sheet.observe(plan.record_id, plan.expected_row)
    if actual is None:
        return Observation("UNKNOWN_OR_ROW_MOVED", plan.record_id)
    if projection_digest(actual) == projection_digest(plan.values):
        return Observation("CURRENT_STATE_MATCHES", plan.record_id)
    return Observation("CONFLICT_NEEDS_REVIEW", plan.record_id)


def unsafe_full_row_rewrite_demo(stale_controls: dict, live_controls: dict,
                                 intended_projection: dict):
    """Negative control: illustrates known overwrite hazard. Never used by safe writer."""
    row = dict(live_controls)
    row.update(intended_projection)
    row.update(stale_controls)  # old snapshot silently overwrites human edit
    return row
