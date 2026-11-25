import unittest
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
import pandas as pd
from crosscheck_fx_sources import validate_bar, label_audit, flatten_yahoo, produce


class FXCrosscheckContractTests(unittest.TestCase):
    def test_bad_ohlc(self):
        valid,bps=validate_bar({'open':101,'high':100,'low':99,'close':100})
        self.assertFalse(valid);self.assertEqual(bps,100)
        self.assertTrue(validate_bar({'open':100,'high':102,'low':99,'close':100})[0])
    def test_no_auto_replace_label(self):
        self.assertEqual(label_audit(False,False,True,True),'YAHOO_REPAIR_FLAG_CANDIDATE')
        self.assertEqual(label_audit(False,False,False,True),'YAHOO_UNREPAIRED_AND_REPAIRED_INVALID')
        self.assertEqual(label_audit(False,True,True,True),'SNAPSHOT_OR_UPSTREAM_VERSION_DRIFT')
    def test_flatten_yahoo(self):
        i=pd.date_range('2024-01-01',periods=3,freq='D')
        df=pd.DataFrame({'Open':[100,101,102], 'High':[101,102,103], 'Low':[99,100,101], 'Close':[100,102,103]},index=i)
        out=flatten_yahoo(df,'KRW=X')
        self.assertEqual(out.loc['2024-01-01','open'],100)
    def test_flatten_multi_yahoo(self):
        i=pd.date_range('2024-01-01',periods=2)
        cols=pd.MultiIndex.from_tuples([('Open','KRW=X'),('High','KRW=X'),('Low','KRW=X'),('Close','KRW=X')])
        df=pd.DataFrame([[100,102,99,101],[102,103,101,102]],columns=cols,index=i)
        out=flatten_yahoo(df,'KRW=X')
        self.assertEqual(out.loc['2024-01-01','close'],101)
    def test_pinned_sha_mismatch_stops_before_source_or_provider_reads(self):
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.zip';path.write_bytes(b'fixture')
            with patch('crosscheck_fx_sources.verified_zip_frame') as read:
                with self.assertRaisesRegex(ValueError,'FX_INPUT_SHA256_MISMATCH'):
                    produce(path,Path(tmp)/'out',expected_sha256='0'*64)
                read.assert_not_called()
                self.assertFalse((Path(tmp)/'out').exists())

    def test_after_asof_invalid_bar_is_separate_and_clean_input_succeeds(self):
        dates=['2026-11-23','2026-11-24','2026-11-25']
        frame=pd.DataFrame({'open':[100,101,200],'high':[102,103,103],
                            'low':[99,100,100],'close':[101,102,102]},index=dates)
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.zip';path.write_bytes(b'fixture')
            out=Path(tmp)/'out'
            with patch('crosscheck_fx_sources.verified_zip_frame',
                       return_value=(frame,{'expected_last_completed_nyse_session':'2026-11-24'})), \
                 patch('crosscheck_fx_sources.load_yahoo') as yahoo, \
                 patch('crosscheck_fx_sources.load_stooq') as stooq, \
                 patch('crosscheck_fx_sources.load_ecb_reference') as ecb:
                r=produce(path,out,expected_sha256=hashlib.sha256(b'fixture').hexdigest())
                for provider in (yahoo,stooq,ecb):provider.assert_not_called()
            self.assertTrue(r['input_sha256_pinned'])
            self.assertEqual(r['anomaly_dates'],0)
            self.assertEqual(r['source_rows_at_or_before_common_asof'],2)
            self.assertEqual(r['source_dates_after_common_asof'],['2026-11-25'])
            self.assertEqual(r['auto_corrected_ohlc'],0)
            self.assertTrue(pd.read_csv(out/'fx_source_triangulation.csv').empty)
            gate=json.loads((out/'fx_research_gate.json').read_text())
            self.assertEqual(gate['affected_dates'],[])
            self.assertEqual(gate['excluded_after_common_asof_dates'],['2026-11-25'])
            self.assertFalse(gate['ta_lib_fx_features_training_eligible'])

    def test_flagged_asof_bar_compared_without_claiming_source_certification(self):
        frame=pd.DataFrame({'open':[105,105],'high':[102,102],
                            'low':[99,99],'close':[101,101]},index=['2026-11-24','2026-11-25'])
        alternate=frame.copy();alternate['open']=100
        with TemporaryDirectory() as tmp:
            path=Path(tmp)/'source.zip';path.write_bytes(b'fixture')
            out=Path(tmp)/'out'
            with patch('crosscheck_fx_sources.verified_zip_frame',
                       return_value=(frame,{'expected_last_completed_nyse_session':'2026-11-24'})), \
                 patch('crosscheck_fx_sources.load_yahoo',return_value=alternate) as yahoo, \
                 patch('crosscheck_fx_sources.load_stooq',return_value=alternate), \
                 patch('crosscheck_fx_sources.load_ecb_reference',return_value={'2026-11-24':101}):
                r=produce(path,out)
                self.assertEqual(yahoo.call_count,2)
            self.assertEqual(r['anomaly_dates'],1)
            self.assertEqual(r['stooq_ohlc_valid_for_flagged'],1)
            self.assertEqual(r['original_source_same_session_ohlc_certified_dates'],0)
            self.assertEqual(r['source_rows_after_common_asof'],1)
            self.assertEqual(r['auto_corrected_ohlc'],0)
            self.assertEqual(r['excluded_from_training'],1)
            rows=pd.read_csv(out/'fx_source_triangulation.csv')
            self.assertEqual(rows['date'].to_list(),['2026-11-24'])
            self.assertFalse(bool(rows.loc[0,'original_source_same_session_ohlc_certified']))
            self.assertFalse(bool(rows.loc[0,'training_eligible']))

if __name__=='__main__':unittest.main()