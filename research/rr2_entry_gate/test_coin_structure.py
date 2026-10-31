"""Offline synthetic contracts for COIN structural RR>=2 (never data results)."""
import importlib.util
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
from zoneinfo import ZoneInfo

spec=importlib.util.spec_from_file_location(
    "coin_structure",Path(__file__).with_name("coin_structure.py"))
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

def make_day(iso,opening=100,low_first=98,second_open=100,rest_close=100,split=26):
    local=datetime.fromisoformat(iso+"T09:30:00").replace(tzinfo=ZoneInfo("America/New_York"))
    start=local.astimezone(timezone.utc)
    rows=[]
    for idx in range(split):
        o=opening if idx==0 else second_open if idx==1 else rest_close
        lo=min(o,rest_close,low_first) if idx==0 else min(o,rest_close)
        hi=max(o,rest_close,101)
        rows.append({"t":(start+timedelta(minutes=15*idx)).isoformat(),
                     "o":o,"h":hi,"l":lo,"c":rest_close})
    return rows

class StructureContracts(unittest.TestCase):
    def test_cost_floor_and_ex_ante_structural_levels(self):
        g=m.geometry(100,98,97,107,"ORL_BUFFER_2R")
        self.assertTrue(g["pass"])
        self.assertAlmostEqual(g["stop_pct"],.021)
        self.assertGreaterEqual((g["target_pct"]-.003)/(g["stop_pct"]+.003),2)
        self.assertEqual(m.geometry(100,95,97,107,"ORL_BUFFER_2R")["reason"],"STOP_TOO_WIDE")
        self.assertEqual(m.geometry(100,99.9,97,107,"ORL_BUFFER_2R")["reason"],"STOP_TOO_TIGHT")
        self.assertEqual(m.geometry(100,98,97,103,"ORL_PRIOR20_HIGH")["reason"],"RESISTANCE_TOO_CLOSE")
        self.assertTrue(m.geometry(100,98,97,106,"ORL_PRIOR20_HIGH")["pass"])
        self.assertEqual(m.geometry(100,98,97,109,"ORL_PRIOR20_HIGH")["reason"],"TARGET_TOO_FAR")
        self.assertTrue(m.geometry(100,91,None,None,"FIXED_2PCT_2R")["pass"])
        self.assertEqual(m.geometry(100,91,None,None,"PRIOR_LOW_BUFFER_2R")["reason"],"MISSING_PRIOR_LOW")

    def test_early_close_and_dst_calendar(self):
        raw=make_day("2026-11-27",split=14)
        sessions,q=m.build_sessions(raw,start="2026-11-27",end="2026-11-27")
        self.assertEqual(q["complete_sessions"],1)
        self.assertTrue(sessions[0]["early_close"])
        sessions,q=m.build_sessions(make_day("2026-01-05"),start="2026-01-05",end="2026-01-05")
        self.assertEqual(q["complete_sessions"],1)
        sessions,q=m.build_sessions(make_day("2026-01-05")[:-1],start="2026-01-05",end="2026-01-05")
        self.assertEqual(q["incomplete_sessions"],1)
        self.assertEqual(m.research(sessions,q)["status"],"DATA_HOLD_INCOMPLETE_SIP")

    def test_stop_first_when_two_barriers_touch(self):
        raw=make_day("2026-01-05")
        raw[1].update(o=100,h=108,l=97,c=100)
        sessions,_=m.build_sessions(raw,start="2026-01-05",end="2026-01-05")
        r=m.simulate(sessions,0,1,.02,.049)
        self.assertEqual(r["reason"],"STOP")
        self.assertAlmostEqual(r["realized_R"],-1)

    def test_gap_stop_worse_than_planned_loss(self):
        raw=make_day("2026-01-05")+make_day(
            "2026-01-06",opening=90,low_first=89,second_open=90,rest_close=90)
        sessions,_=m.build_sessions(raw,start="2026-01-05",end="2026-01-06")
        r=m.simulate(sessions,0,2,.02,.049)
        self.assertEqual(r["reason"],"STOP_GAP")
        self.assertLess(r["realized_R"],-1)

    def test_research_scope_and_no_live_promotion(self):
        import exchange_calendars as xc, pandas as pd
        cal=xc.get_calendar("XNYS")
        dates=cal.sessions_in_range(pd.Timestamp("2026-01-02"),pd.Timestamp("2026-02-17"))[:27]
        bars=[]
        for d in dates:
            opened=cal.session_open(d).to_pydatetime()
            closed=cal.session_close(d).to_pydatetime()
            n=int((closed-opened).total_seconds()//900)
            bars.extend(make_day(d.date().isoformat(),low_first=98,split=n))
        sessions,q=m.build_sessions(bars,start=dates[0].date().isoformat(),
                                    end=dates[-1].date().isoformat())
        d=m.research(sessions,q)
        self.assertEqual(d["live"],"HOLD")
        self.assertEqual(d["status"],"RESEARCH_ONLY_NOT_MODEL_SIGNAL_MATCHED")
        self.assertEqual(len(d["results"]),36)
        row=next(x for x in d["results"]
                 if x["year"]==2026 and x["arm"]=="FIXED_2PCT_2R" and x["hold_sessions"]==1)
        self.assertEqual(row["geometry_pass"],7)
        self.assertGreater(row["trades"],0)
        self.assertLess(row["mean_R"],0)
        self.assertEqual(row["cost_stress_50bp_planned_rr2_count"],0)

    def test_invalid_ohlc_and_duplicate_rejected(self):
        rows=make_day("2026-01-05")
        with self.assertRaisesRegex(ValueError,"DUPLICATE_TIMESTAMPS"):
            m.build_sessions(rows+[rows[0]],start="2026-01-05",end="2026-01-05")
        rows[0]["h"]=1
        with self.assertRaisesRegex(ValueError,"INVALID_OHLC"):
            m.build_sessions(rows,start="2026-01-05",end="2026-01-05")

if __name__=="__main__": unittest.main()
