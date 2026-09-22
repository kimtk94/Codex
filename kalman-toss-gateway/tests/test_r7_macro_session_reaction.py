import importlib.util
from pathlib import Path
import pandas as pd

P=Path(__file__).resolve().parents[1]/"research"/"r7_macro_session_reaction.py"
spec=importlib.util.spec_from_file_location("r7react",P)
m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)

def _qqq():
    return pd.DataFrame({
        "candle_time_utc":pd.to_datetime([
            "2026-09-01T13:30:00Z",
            "2026-09-01T14:30:00Z",
            "2026-09-01T15:30:00Z",
        ],utc=True),
        "open":[100.0,101.0,102.0],
        "close":[101.0,102.0,103.0],
        "session_date":["2026-09-01"]*3,
        "session_bucket":[0,1,2],
        "expected_seq":[10,11,12],
        "bar_time_aligned":[True]*3,
        "data_gap_before":[False]*3,
    }).assign(bar_end_utc=lambda x:x.candle_time_utc+pd.Timedelta(hours=1))

def test_post_event_uses_first_full_bar_not_straddle():
    events=[{
        "family":"JOLTS",
        "event_name":"JOLTS",
        "release_at":"2026-09-01T14:00:00Z",
        "pit_actual_eligible":True,
    }]
    rows,stats=m.build_reaction(events,_qqq(),6)
    r=rows[0]
    assert r["first_full_bar_start"]=="2026-09-01T14:30:00+00:00"
    assert r["reaction_available_at"]=="2026-09-01T15:30:00+00:00"
    assert round(r["qqq_reaction_1h_open_to_close"],10)==round(102/101-1,10)
    assert stats["reaction_coverage_ratio"]==1.0

def test_reissued_actual_is_not_reaction_eligible():
    events=[{
        "family":"EMPLOYMENT",
        "event_name":"Employment Situation",
        "release_at":"2026-09-01T13:00:00Z",
        "pit_actual_eligible":False,
    }]
    rows,stats=m.build_reaction(events,_qqq(),6)
    assert rows[0]["reaction_available"] is False
    assert rows[0]["blocker"]=="EVENT_INPUT_NOT_PIT_ELIGIBLE"
    assert stats["eligible_events_in_qqq_history"]==0

def test_fomc_event_timestamp_is_eligible_without_bls_actual():
    events=[{
        "family":"FOMC",
        "event_name":"FOMC statement",
        "release_at":"2026-09-01T14:00:00Z",
        "pit_actual_eligible":False,
    }]
    rows,stats=m.build_reaction(events,_qqq(),6)
    assert rows[0]["reaction_available"] is True
    assert stats["eligible_events_in_qqq_history"]==1
