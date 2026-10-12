"""Pure, side-effect-free proposed Kalman entry gate (RESEARCH ONLY).

This module is not connected to any LIVE execution path. A stale or failed
model pipeline must not authorize new BUY, while the existing exit engine
continues to operate. Does not query a broker or read credentials.
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class GateDecision:
    new_entry_allowed: bool
    exit_management_allowed: bool
    reason: str


def decide_entry_gate(*, preflight_ok: bool, pipeline_ok: bool,
                      fresh_signal: bool, emergency_stop: bool = False) -> GateDecision:
    if emergency_stop:
        return GateDecision(False, True, "EMERGENCY_STOP_ENTRIES")
    if not preflight_ok:
        return GateDecision(False, True, "DRIVE_PREFLIGHT_FAILED")
    if not pipeline_ok:
        return GateDecision(False, True, "PIPELINE_INCOMPLETE")
    if not fresh_signal:
        return GateDecision(False, True, "STALE_OR_MISSING_SIGNAL")
    return GateDecision(True, True, "ENTRY_GATE_PASS")
