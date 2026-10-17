"""G12 synthetic-only Google Sheets update adapter.

A gspread-shaped method call with a checked A1 range and stable synthetic IDs.
Does not connect to Google Sheets or intercept the production engine.
"""
from __future__ import annotations
import os
from g12_sheet_range_fence import WriteDenied, WriteIntent, parse_bounded_a1, validate_intent

class SyntheticWorksheet:
    """In-memory worksheet; no external imports or network methods."""
    def __init__(self, sheet_id: int, name: str, registry: dict[int,str]):
        self.id, self.title = sheet_id, name
        self.registry = dict(registry)
        self.cells = {}
        self.calls = 0
        self.fail_after = False

    def update(self, range_name: str, values, value_input_option="RAW"):
        row0, row1, col0, col1 = parse_bounded_a1(range_name)
        if len(values) != row1-row0 or any(len(row) != col1-col0 for row in values):
            raise WriteDenied("payload shape differs from bounded range")
        for y, row in enumerate(values):
            for x, value in enumerate(row):
                self.cells[(row0+y+1,col0+x)] = value
        self.calls += 1
        if self.fail_after:
            self.fail_after = False
            raise RuntimeError("synthetic response lost after write")
        return {"updatedCells": (row1-row0)*(col1-col0)}

    def read_cells(self, range_name):
        row0, row1, col0, col1 = parse_bounded_a1(range_name)
        return [[self.cells.get((row+1,col),"") for col in range(col0,col1)]
                for row in range(row0,row1)]

class ScopedWriter:
    """Explicit test adapter. Refuses gspread and all unapproved methods."""
    def __init__(self, worksheet: SyntheticWorksheet):
        if os.environ.get("G16_SYNTHETIC_ONLY") != "1":
            raise WriteDenied("synthetic guard mode required")
        if type(worksheet) is not SyntheticWorksheet:
            raise WriteDenied("network-backed worksheet rejected")
        self.ws = worksheet

    def update(self, range_name: str, values: list[list], *, record_ids: tuple[str,...]):
        validate_intent(WriteIntent(self.ws.id, self.ws.title, "values.update", range_name))
        row0, row1, _, _ = parse_bounded_a1(range_name)
        if len(record_ids) != row1-row0 or len(values) != len(record_ids):
            raise WriteDenied("record count and range disagree")
        if not all(isinstance(key,str) and key.startswith("TEST-") for key in record_ids):
            raise WriteDenied("non-synthetic record key")
        if len(set(record_ids)) != len(record_ids):
            raise WriteDenied("duplicate record key")
        for i, key in enumerate(record_ids):
            if self.ws.registry.get(row0+i+1) != key:
                raise WriteDenied("physical row identity changed")
        try:
            result = self.ws.update(range_name,values,value_input_option="RAW")
        except RuntimeError:
            observed = self.ws.read_cells(range_name)
            return {"outcome": "CURRENT_STATE_MATCHES_NOT_EXACTLY_ONCE"
                    if observed == values else "UNKNOWN_NEEDS_REVIEW",
                    "retry_automatically": False}
        return {"outcome": "ACKNOWLEDGED_SYNTHETIC_WRITE",
                "retry_automatically": False, "updatedCells": result["updatedCells"]}

    def __getattr__(self,name):
        raise WriteDenied("unapproved worksheet mutation denied")
