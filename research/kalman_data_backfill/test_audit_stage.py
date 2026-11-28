import datetime as dt
import os
from unittest.mock import patch
import json
import tempfile
import unittest
from pathlib import Path

import exchange_calendars as xcals
import pandas as pd

from audit_stage import (evaluate, expected_starts, last_completed_session,
                         read_bars, staged_dataframe, main, _fetch_month)


class GapAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cal=xcals.get_calendar('XNYS')

    def sample(self,begin='2026-10-28',end='2026-10-29',drop=None):
        stamps=expected_starts(self.cal,begin,end,'15m')
        if drop is not None:
            stamps=stamps.delete(drop)
        return pd.DataFrame({'market':'QQQ','candle_time_utc':stamps,
                             'open':100.,'high':101.,'low':99.,'close':100.,
                             'volume':1000.,'quote_volume':100000.,'unit_min':15})

    def test_new_york_calendar_and_missing(self):
        df=self.sample(drop=2)
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/'sample.csv'
            df.to_csv(path,index=False)
            missing,report,_=evaluate(read_bars(path,'15m'),'QQQ','15m','2026-10-29')
        self.assertEqual(report['expected'],52)
        self.assertEqual(report['missing'],1)
        self.assertEqual(report['duplicates'],0)
        self.assertEqual(missing.iloc[0]['start_utc'],
                         (self.cal.session_open('2026-10-28') + pd.Timedelta(minutes=30)).isoformat())

    def test_expected_sessions_38(self):
        sessions=self.cal.sessions_in_range('2026-09-05','2026-10-29')
        self.assertEqual(len(sessions),38)
        bars=expected_starts(self.cal,'2026-09-08','2026-10-29','15m')
        self.assertEqual(len(bars),988)

    def test_early_close(self):
        b=expected_starts(self.cal,'2025-11-28','2025-11-28','15m')
        self.assertEqual(len(b),14)

    def test_1d_mapping_ny_start_and_utc_midnight(self):
        session_start=self.cal.session_open('2026-10-29')
        df=pd.DataFrame({'market':['QQQ']*2,'candle_time_utc':[pd.Timestamp('2026-10-28T00:00:00Z'),session_start],
                         'open':[100.,100.],'high':[110.,110.],
                         'low':[90.,90.],'close':[105.,105.]})
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'sample.csv';df.to_csv(p,index=False)
            data=read_bars(p,'1d')
        self.assertEqual(data['_start'].dt.date.tolist(),[dt.date(2026,10,28),dt.date(2026,10,29)])
        _,report,_=evaluate(data,'QQQ','1d','2026-10-29')
        self.assertEqual(report['missing'],0)

    def test_not_yet_completed(self):
        now=dt.datetime(2026,10,30,13,0,tzinfo=dt.timezone.utc)
        self.assertEqual(last_completed_session(now),'2026-10-29')

    def test_staging_keeps_only_missing_and_source_untouched(self):
        t=self.cal.session_open('2026-10-28')
        wanted={t.isoformat()}
        b=[{'t':t.isoformat(),'o':100,'h':101,'l':99,'c':100,'v':1000,'vw':100.1},
           {'t':(t+pd.Timedelta(minutes=15)).isoformat(),'o':100,'h':101,'l':99,'c':100,'v':1000}]
        frame=staged_dataframe('QQQ','15m',b,wanted,self.cal)
        self.assertEqual(len(frame),1)
        self.assertEqual(frame.loc[0,'market'],'QQQ')
        self.assertEqual(frame.loc[0,'unit_min'],15)
        self.assertEqual(frame.loc[0,'quote_volume'],100100)

    def test_cli_audit_does_not_rewrite_source(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'raw.csv';out=Path(d)/'out'
            self.sample(drop=5).to_csv(p,index=False)
            before=p.read_bytes()
            rc=main(['--dataset',f'QQQ:15m:{p}','--as-of','2026-10-29','--out-dir',str(out)])
            self.assertEqual(rc,0)
            self.assertEqual(before,p.read_bytes())
            result=json.loads((out/'summary.json').read_text())
            self.assertEqual(result['status'],'AUDIT_ONLY')
            self.assertEqual(result['datasets'][0]['missing'],1)
            self.assertFalse(result['source_mutated'])



    def test_sip_future_month_end_is_capped(self):
        class StubResponse:
            status_code = 200
            def raise_for_status(self):
                return None
            def json(self):
                return {'bars': []}
        class StubSession:
            def __init__(self):
                self.params = []
            def get(self, url, params, headers, timeout):
                self.params.append(params)
                return StubResponse()

        stub = StubSession()
        with patch.dict(os.environ, {'ALPACA_API_KEY_ID': 'dummy_id',
                                     'ALPACA_API_SECRET_KEY': 'dummy_secret'}):
            _fetch_month(stub, 'QQQ', '15m',
                         pd.Timestamp.now(tz='UTC') - pd.Timedelta(days=5),
                         pd.Timestamp.now(tz='UTC') + pd.Timedelta(days=4),
                         sleep=lambda _: None)
        self.assertEqual(len(stub.params), 1)
        self.assertEqual(stub.params[0]['feed'], 'sip')
        effective_end = pd.Timestamp(stub.params[0]['end'])
        self.assertLessEqual(effective_end, pd.Timestamp.now(tz='UTC') - pd.Timedelta(minutes=19))

    def test_sip_historical_window_unchanged(self):
        class StubResponse:
            status_code = 200
            def raise_for_status(self):
                return None
            def json(self):
                return {'bars': []}
        class StubSession:
            def __init__(self):
                self.params = []
            def get(self, url, params, headers, timeout):
                self.params.append(params)
                return StubResponse()
        stub = StubSession()
        with patch.dict(os.environ, {'ALPACA_API_KEY_ID': 'dummy_id',
                                     'ALPACA_API_SECRET_KEY': 'dummy_secret'}):
            _fetch_month(stub, 'QQQ', '1d', pd.Timestamp('2026-09-01T00:00:00Z'),
                         pd.Timestamp('2026-10-01T00:00:00Z'), sleep=lambda _:None)
        self.assertEqual(stub.params[0]['end'], '2026-10-01T00:00:00Z')

if __name__=='__main__':unittest.main()
