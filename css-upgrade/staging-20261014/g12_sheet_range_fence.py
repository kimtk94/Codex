"""G12 preflight-only Google Sheets write-range ownership fence.

Uses IDs and control columns verified from the live workbook on 2026-10-17.
Pure, offline and side-effect free. It does NOT intercept gspread calls unless
explicitly wired after review. It cannot establish a real Sheets transaction,
stable physical row identity, or exactly-once processing.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ProtectedSheet:
    name: str
    sheet_id: int
    control_columns: frozenset[int]
    key_columns: frozenset[int]


SHEETS = {
    948865119: ProtectedSheet(
        "CSS Project Dashboard", 948865119, frozenset({0, 1}), frozenset({4})),
    1618938211: ProtectedSheet(
        "CSS Contract-SIF Tracker", 1618938211,
        frozenset({0, 1, 2}), frozenset({29, 33})),
    692581491: ProtectedSheet(
        "CSS Contract-SIF Skipped", 692581491,
        frozenset({0, 2, 3}), frozenset({13, 20})),
    1445506838: ProtectedSheet(
        "CSS Manual Exclusions", 1445506838,
        frozenset({0}), frozenset({1})),
}
# Include ambiguous Prepayment/skip_reason among protected until ownership agreed.
ALLOW_VALUE_OPERATIONS = frozenset({"values.update", "updateCells.userEnteredValue"})
CELL = re.compile(r"^\$?([A-Z]{1,3})\$?([1-9][0-9]*)$")
RANGE = re.compile(r"^\s*(\$?[A-Z]{1,3}\$?[1-9][0-9]*)"
                   r"(?::(\$?[A-Z]{1,3}\$?[1-9][0-9]*))?\s*$")


class WriteDenied(ValueError):
    """Intent must not reach Google Sheets."""


def column_number(letters: str) -> int:
    number = 0
    for ch in letters:
        if not "A" <= ch <= "Z":
            raise WriteDenied("unsupported column reference")
        number = number * 26 + (ord(ch) - 64)
    if number < 1 or number > 18278:
        raise WriteDenied("unsupported column size")
    return number - 1


def parse_bounded_a1(cell_range: str) -> tuple[int, int, int, int]:
    """Return 0-based start/end rows and cols, with exclusive upper bounds."""
    if not isinstance(cell_range, str):
        raise WriteDenied("explicit bounded A1 range required")
    match = RANGE.fullmatch(cell_range)
    if match is None:
        raise WriteDenied("unbounded, title-qualified or malformed A1 range")
    def parse_cell(cell):
        found = CELL.fullmatch(cell)
        if found is None:
            raise WriteDenied("invalid A1 address")
        return int(found.group(2)) - 1, column_number(found.group(1))
    top, left = parse_cell(match.group(1))
    bottom, right = parse_cell(match.group(2) or match.group(1))
    if bottom < top or right < left:
        raise WriteDenied("reversed range")
    return top, bottom + 1, left, right + 1


@dataclass(frozen=True)
class WriteIntent:
    sheet_id: int
    sheet_name: str
    operation: str
    cell_range: str
    field_mask: str = "userEnteredValue"


def validate_intent(intent: WriteIntent) -> dict:
    """Fail closed for protected tabs; does not execute any update."""
    if not isinstance(intent, WriteIntent):
        raise WriteDenied("explicit audited write intent required")
    if type(intent.sheet_id) is not int or intent.sheet_id not in SHEETS:
        raise WriteDenied("unknown or invalid protected sheet id")
    spec = SHEETS[intent.sheet_id]
    if intent.sheet_name != spec.name:
        raise WriteDenied("sheet title/id mismatch")
    if intent.operation not in ALLOW_VALUE_OPERATIONS:
        raise WriteDenied("bulk, structural, formatting or unknown operation denied")
    if intent.field_mask != "userEnteredValue":
        raise WriteDenied("unknown update field mask")
    start_row, end_row, start_col, end_col = parse_bounded_a1(intent.cell_range)
    if start_row < 1:
        raise WriteDenied("header row is system-defined; update denied")
    touched = frozenset(range(start_col, end_col))
    if spec.control_columns & touched:
        raise WriteDenied("write overlaps protected operator controls")
    # Identity columns are never rewritten by this policy either.
    if spec.key_columns & touched:
        raise WriteDenied("record identity field write denied")
    return {
        "status": "SCOPED_NON_CONTROL_VALUE_WRITE",
        "sheet_id": spec.sheet_id,
        "operation": intent.operation,
        "rows": end_row - start_row,
        "columns": end_col - start_col,
        "controls_protected_by_this_intent": True,
        "live_sheet_write_performed": False,
        "row_identity_or_concurrency_proven": False,
    }
