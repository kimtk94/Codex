import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
from refresh_ci import (NEEDED, clean_fred_csv, select_universe, verified_status,
                        make_bundle, publish, last_completed_nyse_session, fred_completeness_label)


class RefreshContracts(unittest.TestCase):
    def test_universe_required_and_isolation(self):
        with tempfile.TemporaryDirectory() as root:
            src=Path(root)/'cfg.json';out=Path(root)/'new.json'
            assets=[{'key':k,'provider':'yfinance','symbol':k[3:]} for k in NEEDED]
            assets.append({'key':'other','provider':'pykrx','symbol':'123'})
            src.write_text(json.dumps({'version':'original','assets':assets}))
            cfg=select_universe(src,out)
            self.assertEqual(len(cfg['assets']),len(NEEDED))
            self.assertTrue(all(x['required'] for x in cfg['assets']))
            self.assertFalse(any(x['provider']=='pykrx' for x in cfg['assets']))
            self.assertEqual(json.loads(src.read_text())['version'],'original')

    def test_fred_invalid_and_no_lookahead_promotion(self):
        valid=b'DATE,VALUE\n'+b''.join(f'2026-09-{i:02d},{3+i/10}\n'.encode() for i in range(1,29))
        df=clean_fred_csv(valid)
        self.assertEqual(len(df),28)
        with self.assertRaises(ValueError):clean_fred_csv(b'DATE,VALUE\n2026-01-01,3\n2026-01-01,4\n')

    def make_state(self,root):
        root=Path(root);md=root/'market';fd=root/'features';frd=root/'fred'
        (md/'raw'/'yfinance').mkdir(parents=True)
        (fd/'talib').mkdir(parents=True)
        frd.mkdir(parents=True)
        now=pd.Timestamp(last_completed_nyse_session())
        dates=pd.date_range(now-pd.Timedelta(days=120),now,freq='D')
        srcs={};assets={}
        for k in NEEDED:
            pd.DataFrame({'timestamp':dates,'close':np.arange(len(dates))+100.}).to_parquet(md/'raw'/'yfinance'/f'{k}.parquet')
            pd.DataFrame({'timestamp':dates,'talib_v2_rsi14':np.linspace(20,80,len(dates))}).to_parquet(fd/'talib'/f'{k[3:]}.parquet')
            srcs[k]={'status':'READY'};assets[k]={'status':'READY'}
        (md/'market_data_v2_run_status.json').write_text(json.dumps({'status':'READY','sources':srcs}))
        (fd/'features_v2_002_run_status.json').write_text(json.dumps({'status':'READY','required_failures':[],'assets':assets}))
        (frd/'fred_status.json').write_text(json.dumps({'status':'DEGRADED','series_ready':0,'source_revision':'latest_revised'}))
        return md,fd,frd

    def test_ready_with_macro_degraded_cannot_promote_training(self):
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root)
            s=verified_status(md,fd,frd)
            self.assertEqual(s['status'],'READY')
            self.assertEqual(s['fred_status'],'DEGRADED')
            self.assertFalse(s['point_in_time_training_ready'])
            out=Path(root)/'market.zip'
            mf=make_bundle(md,fd,frd,out,Path(root)/'status.json')
            self.assertEqual(mf['market_assets'],len(NEEDED))
            self.assertFalse(mf['production_writes'])
            import zipfile
            with zipfile.ZipFile(out) as z:self.assertEqual(json.loads(z.read('manifest.json'))['status'],'RESEARCH_ONLY_VALIDATED')

    def test_stale_required_blocks_publishing(self):
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root)
            f=md/'raw'/'yfinance'/'yf_vix.parquet'
            d=pd.read_parquet(f);d['timestamp']=pd.to_datetime(d['timestamp'])-pd.Timedelta(days=20);d.to_parquet(f)
            self.assertEqual(verified_status(md,fd,frd)['status'],'BLOCKED')
            with self.assertRaises(RuntimeError):make_bundle(md,fd,frd,Path(root)/'bad.zip',Path(root)/'report.json')

    def test_nyse_preclose_and_postclose_gate(self):
        self.assertEqual(last_completed_nyse_session('2026-10-30T17:09:00Z'),'2026-10-29')
        self.assertEqual(last_completed_nyse_session('2026-10-31T01:28:00Z'),'2026-10-30')
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root)
            # When that day's US market is not closed, a daily Yahoo candle is not final.
            before=verified_status(md,fd,frd,now_utc='2026-10-30T17:09:00Z')
            self.assertEqual(before['status'],'BLOCKED')
            self.assertTrue(any('LAST_CLOSED_NYSE' in x for x in before['blocking_errors']))
            after=verified_status(md,fd,frd,now_utc='2026-10-31T01:28:00Z')
            self.assertEqual(after['status'],'READY')

    def test_fred_missing_must_be_visible(self):
        self.assertEqual(fred_completeness_label(0),'FRED_UNAVAILABLE')
        self.assertEqual(fred_completeness_label(3),'FRED_PARTIAL')
        self.assertEqual(fred_completeness_label(12),'FRED_READY_CURRENT_REVISED')

    def test_bad_target_id_never_updates(self):
        with self.assertRaises(ValueError):publish('/nonexistent','bad id')

if __name__=='__main__':unittest.main()