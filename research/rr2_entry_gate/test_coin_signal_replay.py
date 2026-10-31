"""Provenance and temporal anti-lookahead contracts for private COIN model replay."""
import csv
import tempfile
import unittest
from pathlib import Path
import exchange_calendars as xc
import pandas as pd

from coin_signal_replay import FIELDS, load_ledger, validate_entries, replay
from test_coin_structure import make_day
from coin_structure import build_sessions


def synthetic_sessions():
    cal = xc.get_calendar("XNYS")
    dates = list(cal.sessions_in_range(
        pd.Timestamp("2026-01-02"), pd.Timestamp("2026-03-02"))[:31])
    bars = []
    for d in dates:
        opened = cal.session_open(d).to_pydatetime()
        closed = cal.session_close(d).to_pydatetime()
        bars.extend(make_day(d.date().isoformat(), low_first=98,
                             split=int((closed-opened).total_seconds()/900)))
    sessions, q = build_sessions(
        bars, start=dates[0].date().isoformat(),
        end=dates[-1].date().isoformat())
    return sessions, q


def row(sessions, i, sid):
    return {
        "signal_id": sid,
        "signal_date": sessions[i-1]["date"],
        "entry_date": sessions[i]["date"],
        "symbol": "COIN",
        "model": "V_unweighted",
        "available_after": "RTH_CLOSE",
        "source_run_id": "ORIGINAL_FROZEN_MODEL_RUN_ID",
    }


class SignalReplayContracts(unittest.TestCase):
    def test_provenance_date_next_session_and_replay(self):
        sessions, q = synthetic_sessions()
        rows = [row(sessions, 22, "a"), row(sessions, 24, "b")]
        self.assertEqual(len(validate_entries(
            rows, sessions, expected={2026:2})),2)
        d = replay(sessions, q, rows, "synthetic-test-sha",
                   expected={2026:2})
        self.assertEqual(d["status"],
                         "MATCHED_LEDGER_RESEARCH_ONLY_NOT_UNSEEN_OOS")
        self.assertEqual(d["live"], "HOLD")
        self.assertEqual(d["signals_verified"], {2026:2})
        self.assertEqual(len(d["results"]),12)
        self.assertEqual(d["baseline_parity"][2026]
                         ["original_atr125_stop300_gate_pass"],0)
        for r in d["results"]:
            self.assertEqual(r["original_signals"],2)
            self.assertEqual(
                r["structural_pass"]+sum(
                    r["first_rejection_counts"].values()),2)
            self.assertLessEqual(r["trades"],r["structural_pass"])
        self.assertNotIn("signal_id", str(d))
        self.assertNotIn("signal_date", str(d))

    def test_temporal_leak_and_origin_rejected(self):
        sessions, _ = synthetic_sessions()
        r = row(sessions,22,"a")
        r["signal_date"] = r["entry_date"]
        with self.assertRaisesRegex(ValueError, "NOT_IMMEDIATELY_NEXT"):
            validate_entries([r],sessions,expected={2026:1})
        r = row(sessions,22,"a")
        r["signal_date"] = sessions[20]["date"]
        r["entry_date"] = sessions[24]["date"]
        with self.assertRaisesRegex(ValueError, "NOT_IMMEDIATELY_NEXT"):
            validate_entries([r],sessions,expected={2026:1})
        r = row(sessions,22,"a")
        r["model"] = "P_unweighted"
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/"wrong.csv"
            with p.open("w", newline="") as f:
                w=csv.DictWriter(f,fieldnames=FIELDS)
                w.writeheader();w.writerow(r)
            with self.assertRaisesRegex(ValueError,"WRONG_SYMBOL_OR_MODEL"):
                load_ledger(p)

    def test_cardinality_duplicate_and_missing_source_rejected(self):
        sessions, q = synthetic_sessions()
        rows = [row(sessions,22,"a"),row(sessions,24,"b")]
        with self.assertRaisesRegex(ValueError,"COHORT_CARDINALITY_MISMATCH"):
            validate_entries(rows,sessions,expected={2026:3})
        with self.assertRaisesRegex(ValueError,"DUPLICATE_SIGNAL_OR_ENTRY"):
            with tempfile.TemporaryDirectory() as tmp:
                p=Path(tmp)/"dup.csv"
                with p.open("w",newline="") as f:
                    w=csv.DictWriter(f,fieldnames=FIELDS)
                    w.writeheader();w.writerow(rows[0]);w.writerow(rows[0])
                load_ledger(p)
        wrong=[dict(r) for r in rows]
        wrong[1]["source_run_id"]="ANOTHER_MODEL_RUN"
        with self.assertRaisesRegex(ValueError,"MULTIPLE_UNVERIFIED_SOURCE_RUNS"):
            replay(sessions,q,wrong,"synthetic-test-sha",expected={2026:2})
        q = dict(q)
        q["incomplete_sessions"]=1
        with self.assertRaisesRegex(ValueError,"INCOMPLETE_SIP_SOURCE"):
            replay(sessions,q,rows,"synthetic-test-sha",expected={2026:2})


if __name__ == "__main__":
    unittest.main()
