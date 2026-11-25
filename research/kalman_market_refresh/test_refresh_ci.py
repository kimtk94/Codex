import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch
import numpy as np
import pandas as pd
from refresh_ci import (NEEDED, OPTIONAL, FEATURE_STEMS, candidate_status, clean_fred_csv, select_universe, verified_status,
                        make_bundle, publish, last_completed_nyse_session, fred_completeness_label,
                        clean_fred_api_json)


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

    def make_state(self,root,session=None,keys=NEEDED):
        root=Path(root);md=root/'market';fd=root/'features';frd=root/'fred'
        (md/'raw'/'yfinance').mkdir(parents=True)
        (fd/'talib').mkdir(parents=True)
        frd.mkdir(parents=True)
        now=pd.Timestamp(session if session is not None else last_completed_nyse_session())
        dates=pd.date_range(now-pd.Timedelta(days=120),now,freq='D')
        srcs={};assets={}
        for k in keys:
            pd.DataFrame({'timestamp':dates,'close':np.arange(len(dates))+100.}).to_parquet(md/'raw'/'yfinance'/f'{k}.parquet')
            pd.DataFrame({'timestamp':dates,'talib_v2_rsi14':np.linspace(20,80,len(dates))}).to_parquet(fd/'talib'/f'{FEATURE_STEMS[k]}.parquet')
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

    def test_official_fred_api_observation_parser(self):
        payload={'observations':[{'date':f'2026-10-{i:02d}','value':str(3.0+i/100)}
                                 for i in range(1,27)]}
        parsed=clean_fred_api_json(payload)
        self.assertEqual(len(parsed),26)
        self.assertEqual(parsed['observation_date'].iloc[-1],'2026-10-26')
        with self.assertRaises(ValueError):
            clean_fred_api_json({'error':'invalid API key'})
        with self.assertRaises(ValueError):
            clean_fred_api_json({'observations':[{'date':'bad','value':'4'}]*25})

    def test_nyse_preclose_and_postclose_gate(self):
        self.assertEqual(last_completed_nyse_session('2026-10-30T17:09:00Z'),'2026-10-29')
        self.assertEqual(last_completed_nyse_session('2026-10-31T01:28:00Z'),'2026-10-30')
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root,session='2026-10-30')
            # When that day's US market is not closed, a daily Yahoo candle is not final.
            before=verified_status(md,fd,frd,now_utc='2026-10-30T17:09:00Z')
            self.assertEqual(before['status'],'BLOCKED')
            self.assertTrue(any('LAST_CLOSED_NYSE' in x for x in before['blocking_errors']))
            after=verified_status(md,fd,frd,now_utc='2026-10-31T01:28:00Z')
            self.assertEqual(after['status'],'READY')

    def test_feature_names_match_real_market_universe(self):
        repo=Path(__file__).resolve().parents[2]
        cfg=json.loads((repo/'kalman-toss-gateway/config/market-data-v2-universe.json').read_text())
        expected={}
        for asset in cfg['assets']:
            if asset['key'] in NEEDED+OPTIONAL and asset['provider']=='yfinance':
                stem=''.join(c.lower() if c.isalnum() else '_' for c in asset['symbol']).strip('_')
                while '__' in stem:
                    stem=stem.replace('__','_')
                expected[asset['key']]=stem
        self.assertEqual(expected,FEATURE_STEMS)
        self.assertEqual(len(set(expected.values())),19)

    def test_candidate_rejects_fetch_key_feature_alias(self):
        import zipfile
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root,keys=NEEDED+OPTIONAL)
            out=Path(root)/'candidate.zip'
            make_bundle(md,fd,frd,out,Path(root)/'readiness.json')
            wrong=Path(root)/'wrong_alias.zip'
            with zipfile.ZipFile(out) as source, zipfile.ZipFile(wrong,'w') as dest:
                manifest=json.loads(source.read('manifest.json'))
                old='features/talib/btc_usd.parquet'
                alias='features/talib/btc.parquet'
                for member in manifest['members']:
                    if member['path']==old:
                        member['path']=alias
                for name in source.namelist():
                    if name=='manifest.json':
                        dest.writestr(name,json.dumps(manifest))
                    else:
                        dest.writestr(alias if name==old else name,source.read(name))
            with self.assertRaisesRegex(RuntimeError,'CANDIDATE_NOT_EXACT_19'):
                candidate_status(wrong,Path(root)/'candidate_status.json')

    def test_candidate_exact_full_universe_metadata_only(self):
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root,keys=NEEDED+OPTIONAL)
            out=Path(root)/'candidate.zip'
            make_bundle(md,fd,frd,out,Path(root)/'readiness.json')
            report_path=Path(root)/'candidate_status.json'
            with patch('refresh_ci.publish') as writer:
                report=candidate_status(out,report_path)
                writer.assert_not_called()
            self.assertEqual(report['market_assets'],19)
            self.assertEqual(report['feature_assets'],19)
            self.assertEqual(report['status'],'CANDIDATE_METADATA_ONLY_RESEARCH_HOLD')
            self.assertFalse(report['canonical_drive_zip_replaced'])
            self.assertFalse(report['private_candidate_archive_persisted'])
            self.assertFalse(report['ready_for_pit_training'])
            self.assertEqual(json.loads(report_path.read_text()),report)

    def test_candidate_rejects_required_only_universe(self):
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root)
            out=Path(root)/'candidate.zip'
            make_bundle(md,fd,frd,out,Path(root)/'readiness.json')
            with self.assertRaisesRegex(RuntimeError,'CANDIDATE_NOT_EXACT_19'):
                candidate_status(out,Path(root)/'candidate_status.json')

    def test_candidate_rejects_tampered_member(self):
        import zipfile
        with tempfile.TemporaryDirectory() as root:
            md,fd,frd=self.make_state(root,keys=NEEDED+OPTIONAL)
            out=Path(root)/'candidate.zip'
            make_bundle(md,fd,frd,out,Path(root)/'readiness.json')
            tampered=Path(root)/'tampered.zip'
            with zipfile.ZipFile(out) as source, zipfile.ZipFile(tampered,'w') as dest:
                for name in source.namelist():
                    body=source.read(name)
                    if name=='market/raw/yfinance/yf_spy.parquet':
                        body+=b'changed'
                    dest.writestr(name,body)
            with self.assertRaisesRegex(RuntimeError,'CANDIDATE_MEMBER_HASH_MISMATCH'):
                candidate_status(tampered,Path(root)/'candidate_status.json')

    def test_fred_missing_must_be_visible(self):
        self.assertEqual(fred_completeness_label(0),'FRED_UNAVAILABLE')
        self.assertEqual(fred_completeness_label(3),'FRED_PARTIAL')
        self.assertEqual(fred_completeness_label(12),'FRED_READY_CURRENT_REVISED')

    def test_bad_target_id_never_updates(self):
        with self.assertRaises(ValueError):publish('/nonexistent','bad id')

if __name__=='__main__':unittest.main()