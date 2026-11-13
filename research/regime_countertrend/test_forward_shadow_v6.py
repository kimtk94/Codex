import json
import tempfile
import unittest
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
import pandas as pd
from research.regime_countertrend.sector_price_sources_v3 import manifest_load
from research.regime_countertrend.forward_shadow_v6 import (
    most_recent_completed_ny_session,frozen_anchor_audit,new_proxy_signals,
    run_snapshot
)

FROZEN_PATH="research/regime_countertrend/frozen_market_anchor_v6.json"
MANIFEST_PATH="research/regime_countertrend/universe_sector_v3.json"

class ForwardShadowV6Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.frozen=json.loads(Path(FROZEN_PATH).read_text())
        cls.manifest=manifest_load(MANIFEST_PATH)

    def test_ny_close_time_does_not_include_unfinished_session(self):
        # November 13 2026, 08:15 ET -> 12 November is last full US day.
        self.assertEqual(str(most_recent_completed_ny_session(
            datetime(2026,11,13,13,15,tzinfo=timezone.utc))),"2026-11-12")
        # Friday 18:00 ET -> the Friday session has completed.
        self.assertEqual(str(most_recent_completed_ny_session(
            datetime(2026,11,13,23,0,tzinfo=timezone.utc))),"2026-11-13")
        # Weekend does not result in a weekend market date.
        self.assertEqual(str(most_recent_completed_ny_session(
            datetime(2026,11,15,18,0,tzinfo=timezone.utc))),"2026-11-13")

    def test_frozen_anchor_price_revision_is_explicit_hold(self):
        a=pd.DataFrame({"date":["2026-11-10","2026-11-11","2026-11-12"],
                        "close":[100.,101.,102.]})
        good=frozen_anchor_audit(a,100.,pd.Timestamp("2026-11-12").date())
        self.assertTrue(good["anchor_match_within_5bp"])
        a.loc[0,"close"]=100.3
        drift=frozen_anchor_audit(a,100.,pd.Timestamp("2026-11-12").date())
        self.assertFalse(drift["anchor_match_within_5bp"])
        self.assertEqual(drift["frozen_compatibility"],"HOLD_RETRO_ADJUSTMENT")
        a.loc[2,"date"]="2026-11-13"
        with self.assertRaises(ValueError):
            frozen_anchor_audit(a,100.,pd.Timestamp("2026-11-12").date())

    def synthetic_ticker(self,symbol):
        days=pd.bdate_range(end="2026-11-12",periods=210)
        dates=days.strftime("%Y-%m-%d")
        reference=self.frozen["anchored_adjusted_close_usd"][symbol]
        idx=next(i for i,day in enumerate(dates) if day=="2026-11-10")
        if symbol=="QQQ":
            prices=np.array([reference*(1.002)**(i-idx)
                for i in range(len(dates))])
        else:
            prices=np.full(len(dates),reference,dtype=float)
            if symbol=="AMD":prices[idx+1:]=reference*.94
        return pd.DataFrame({"date":dates,
            "open":prices,"high":prices*1.005,"low":prices*.995,
            "close":prices,"volume":[20000.]*len(dates)})

    def test_immature_up_dip_is_not_fake_profit(self):
        amd=self.synthetic_ticker("AMD")
        qqq=self.synthetic_ticker("QQQ")
        obs,done=new_proxy_signals(amd,qqq,"AMD","SEMICONDUCTORS")
        self.assertEqual(len(obs),1)
        self.assertEqual(obs[0]["date"],"2026-11-11")
        self.assertEqual(obs[0]["event"],"UP_DIP")
        self.assertFalse(obs[0]["horizon_complete"])
        self.assertFalse(obs[0]["formal_prospective"])
        self.assertEqual(done,[])

    def test_full_market_frozen_and_missing_model_stays_hold(self):
        def mocked_download(symbol,from_date,until):
            return self.synthetic_ticker(symbol),{
                "status":"SOURCE_PASS","provider":"TEST","sha256":"test_hash"}
        fx=pd.DataFrame({"date":pd.bdate_range(end="2026-11-12",periods=25).strftime("%Y-%m-%d"),
                         "usdkrw_close":[1334.]*25})
        def mockfx(target):
            return fx,{"status":"SOURCE_PASS","provider":"TEST"}
        with tempfile.TemporaryDirectory() as directory:
            result=run_snapshot(self.manifest,self.frozen,directory,
                 now_utc=datetime(2026,11,13,13,15,tzinfo=timezone.utc),
                 downloader=mocked_download,fx_downloader=mockfx)
            self.assertEqual(result["complete_us_sources"],24)
            self.assertEqual(result["new_proxy_events"],1)
            self.assertEqual(result["matured_synthetic_events"],0)
            self.assertEqual(result["formal_completed_events"],0)
            self.assertEqual(result["status"],"HOLD_PENDING_OUTCOME")
            self.assertFalse(result["v5_frozen_model_available"])
            self.assertFalse(result["promotion_allowed"])
            self.assertTrue((Path(directory)/"all_24_market_price_health.csv").is_file())

if __name__=="__main__":unittest.main()
