import unittest
import numpy as np
from audit_missingness import date_keys,mode_market,mode_fred,prior_holiday_like,CODES,last_closed_nyse_session,classify_feature_gaps

class ScheduleValidationTests(unittest.TestCase):
 def test_market_weekend_not_mislabeled(self):
  self.assertEqual(date_keys('2026-10-30','2026-11-02','XNYS'),{'2026-10-30','2026-11-02'})
  self.assertIn('2026-10-31',date_keys('2026-10-30','2026-11-02','calendar'))
 def test_good_friday(self):
  self.assertNotIn('2026-04-03',date_keys('2026-04-02','2026-04-06','XNYS'))
 def test_us_federal_not_nyse(self):
  self.assertTrue(prior_holiday_like('2026-10-12','business'))
  self.assertIn('2026-10-12',date_keys('2026-10-09','2026-10-13','XNYS'))
 def test_korean_calendar(self):
  self.assertEqual(mode_market('yf_kospi'),'XKRX')
  self.assertEqual(mode_market('yf_btc'),'calendar')
 def test_special_krx_2026_holidays(self):
  # Documented exchange closures not yet included in all calendar packages.
  dates=date_keys('2026-06-01','2026-07-20','XKRX')
  self.assertNotIn('2026-06-03',dates)
  self.assertNotIn('2026-07-17',dates)
 def test_dxy_sunday_placeholder_is_not_session_gap(self):
  self.assertEqual(mode_market('yf_dxy'),'US_DXY_XNYS_PROXY')
  self.assertNotIn('2026-07-12',date_keys('2026-07-10','2026-07-13','US_DXY_XNYS_PROXY'))
 def test_frequency(self):
  self.assertEqual(mode_fred('CPIAUCSL'),'monthly')
  self.assertEqual(mode_fred('DFF'),'calendar')
  self.assertEqual(mode_fred('WALCL'),'weekly')
  self.assertEqual(date_keys('2026-10-01','2026-10-31','monthly'),{'2026-10-01'})
  self.assertEqual(date_keys('2026-10-01','2026-10-31','weekly'),{'2026-10-07','2026-10-14','2026-10-21','2026-10-28'})
 def test_dynamic_asof_including_early_close(self):
  self.assertEqual(last_closed_nyse_session('2026-10-31T02:20:00Z'),'2026-10-30')
  self.assertEqual(last_closed_nyse_session('2026-11-02T18:00:00Z'),'2026-10-30')
  self.assertEqual(last_closed_nyse_session('2026-11-03T01:00:00Z'),'2026-11-02')
  self.assertEqual(last_closed_nyse_session('2026-11-27T18:10:00Z'),'2026-11-25')
  self.assertEqual(last_closed_nyse_session('2026-11-27T18:50:00Z'),'2026-11-27')
 def test_status_contract(self):
  self.assertEqual(CODES['valid'],'V');self.assertEqual(CODES['missing_record'],'G')


class FeatureGapTests(unittest.TestCase):
 def test_calendar_and_raw_status_distinct(self):
  dates=['2026-11-23','2026-11-24','2026-11-25','2026-11-26','2026-11-27','2026-11-28','2026-11-29','2026-11-30']
  values=[1,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan,np.nan]
  expected={'2026-11-23','2026-11-24','2026-11-25','2026-11-27'}
  raw={'2026-11-24':'P','2026-11-25':'V','2026-11-26':'P','2026-11-28':'V'}
  reasons,counts=classify_feature_gaps(dates,values,'2026-11-29',expected,raw)
  self.assertEqual(reasons,{1:'IN_SESSION_RAW_INVALID',2:'IN_SESSION_RAW_VALID_FEATURE_GAP',
    3:'OFF_SESSION_RAW_INVALID',4:'IN_SESSION_RAW_ABSENT',5:'OFF_SESSION_RAW_VALID',
    6:'OFF_SESSION_RAW_ABSENT',7:'AFTER_ASOF_NULL'})
  self.assertEqual(sum(counts.values()),7)
 def test_future_and_off_session_cannot_establish_warmup(self):
  dates=['2026-11-25','2026-11-26','2026-11-27']
  reasons,_=classify_feature_gaps(dates,[np.nan,1,1],'2026-11-26',
    {'2026-11-25'},{})
  self.assertEqual(reasons,{0:'NO_VALID_SESSION_FEATURE_HOLD'})
 def test_inferred_warmup_and_infinite_value(self):
  dates=['2026-11-23','2026-11-24','2026-11-25']
  reasons,_=classify_feature_gaps(dates,[np.nan,1,np.inf],'2026-11-25',set(dates),
    {'2026-11-25':'V'})
  self.assertEqual(reasons,{0:'LEADING_NULL_WARMUP_CANDIDATE',2:'IN_SESSION_RAW_VALID_FEATURE_GAP'})
 def test_invalid_duplicate_and_reverse_dates_fail(self):
  for dates in (['2026-11-24','2026-11-24'],['2026-11-25','2026-11-24'],['2026-11-24',None]):
   with self.assertRaisesRegex(ValueError,'INVALID_FEATURE_DATE_SEQUENCE'):
    classify_feature_gaps(dates,[1,2],'2026-11-25',set(),{})
 def test_empty_series_is_not_automatically_warmup(self):
  dates=['2026-11-23','2026-11-24']
  _,counts=classify_feature_gaps(dates,[np.nan,np.nan],'2026-11-24',set(dates),{})
  self.assertEqual(counts,{'NO_VALID_SESSION_FEATURE_HOLD':2})
 def test_cutoff_gap_not_mislabeled_off_session(self):
  dates=['2026-11-25','2026-11-27']
  _,counts=classify_feature_gaps(dates,[1,np.nan],'2026-11-25',{'2026-11-25'},{})
  self.assertEqual(counts,{'AFTER_ASOF_NULL':1})

if __name__=='__main__': unittest.main()