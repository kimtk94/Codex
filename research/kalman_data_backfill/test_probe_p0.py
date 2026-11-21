import unittest
from types import SimpleNamespace
from unittest.mock import patch
import exchange_calendars as xcals
from audit_stage import expected_starts
from probe_p0 import US_15M,US_1M,UPBIT,probe_us,probe_upbit,request_json

class FakeSession:
    def __init__(self, payload):
        self.payload=payload
        self.calls=[]
    def get(self,url,params=None,headers=None,timeout=None):
        self.calls.append((url,params))
        return SimpleNamespace(status_code=200,raise_for_status=lambda:None,json=lambda:self.payload)

class ProbeTests(unittest.TestCase):
    def test_exact_nine_assets(self):
        self.assertEqual(set(US_15M)|set(UPBIT),{'QQQ','QLD','SPY','SMH','NVDA','TSLA','AMD','KRW-BTC','KRW-ETH'})
        self.assertEqual(len(US_1M),5)

    def test_nyse_sample_calendar(self):
        cal=xcals.get_calendar('XNYS')
        expected=expected_starts(cal,'2026-10-29','2026-10-29','15m')
        fake=FakeSession({'bars':[{'t':t.isoformat()} for t in expected],'next_page_token':None})
        result=probe_us(fake,'QQQ','15m',cal,'2026-10-29','private','private',1)
        self.assertEqual(result['status'],'SAMPLE_OK')
        self.assertEqual(result['expected'],26)
        self.assertEqual(result['missing'],0)
        self.assertIn('feed',fake.calls[0][1])
        self.assertEqual(fake.calls[0][1]['feed'],'sip')

    def test_nyse_missing_first(self):
        cal=xcals.get_calendar('XNYS')
        expected=expected_starts(cal,'2026-10-29','2026-10-29','15m')
        fake=FakeSession({'bars':[{'t':t.isoformat()} for t in expected[1:]],'next_page_token':None})
        result=probe_us(fake,'QQQ','15m',cal,'2026-10-29','private','private',1)
        self.assertEqual(result['status'],'COVERAGE_GAPS')
        self.assertEqual(result['missing'],1)

    def test_upbit_does_not_impute_minutes(self):
        fake=FakeSession([
            {'candle_date_time_utc':'2026-10-29T08:00:00'},
            {'candle_date_time_utc':'2026-10-29T08:02:00'}
        ])
        result=probe_upbit(fake,'KRW-BTC',1)
        self.assertEqual(result['status'],'SAMPLE_OK')
        self.assertEqual(result['observed'],2)
        self.assertIn('NOT data defects',result['note'])

    def test_provider_rejection(self):
        fake=FakeSession({})
        fake.get=lambda *args,**kwargs:SimpleNamespace(status_code=403)
        content,error=request_json(fake,'https://example.invalid',{})
        self.assertIsNone(content)
        self.assertEqual(error,'PROVIDER_ACCESS_DENIED_403')

if __name__=='__main__':unittest.main()
