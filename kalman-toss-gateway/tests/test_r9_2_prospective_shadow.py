import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "research"))

import r9_2_prospective_shadow as m


def test_prospective_boundary_is_frozen():
    assert m.PROSPECTIVE_START == pd.Timestamp("2026-09-24T13:30:00Z")
    assert m.CANDIDATE == "R9P_NGRAM_ATTENTION_FROZEN"
    assert m.MIN_COVERAGE == 90
    assert m.COST_BPS == 10


def test_max_drawdown_includes_initial_equity():
    x = np.array([-0.10, 0.05], dtype=float)
    assert abs(m.max_drawdown(x) - (-0.10)) < 1e-12


def test_source_state_fails_closed(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "status": "BLOCKED_QUOTA",
                "last_complete_day": "2026-09-22",
            }
        )
    )
    try:
        m.load_source_state(p)
        assert False, "expected fail-closed source state"
    except RuntimeError as exc:
        assert "not READY" in str(exc)


def test_source_state_ready_parses_utc_day(tmp_path):
    p = tmp_path / "state.json"
    p.write_text(
        json.dumps(
            {
                "status": "READY",
                "last_complete_day": "2026-09-23",
            }
        )
    )
    state, day = m.load_source_state(p)
    assert state["status"] == "READY"
    assert day == pd.Timestamp("2026-09-23", tz="UTC")
