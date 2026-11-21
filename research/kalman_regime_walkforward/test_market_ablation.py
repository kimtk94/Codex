import unittest
import numpy as np
import pandas as pd
from market_ablation import (MARKET_KEYS,MARKET_FEATURES,lagged_market_features,
                              make_matched_events,run_matched_walkforward,MODEL_SPEC,FEATURES)

class MarketAlignment(unittest.TestCase):
    def test_prior_nyse_session_only_and_no_fill(self):
        days=pd.Index(pd.bdate_range('2024-01-01',periods=20).strftime('%Y-%m-%d'))
        market=pd.DataFrame({key:100.0+np.arange(len(days))*(j+1) for j,key in enumerate(MARKET_KEYS)},index=days)
        got=lagged_market_features(days,market)
        self.assertTrue(got.iloc[0].isna().all())
        self.assertAlmostEqual(float(got.iloc[7]['m_vix_level']),float(market.iloc[6]['yf_vix']))
        market.loc[days[6],'yf_vix']=np.nan
        got2=lagged_market_features(days,market)
        self.assertTrue(pd.isna(got2.loc[days[7],'m_vix_level']))
        # Change to session D must not change feature at D (only D+1).
        altered=market.copy();altered.loc[days[8],'yf_hyg']=100000.0
        a=lagged_market_features(days,market)
        b=lagged_market_features(days,altered)
        pd.testing.assert_series_equal(a.loc[days[8]],b.loc[days[8]])

    def test_matched_events_exclude_incomplete_days(self):
        days=pd.Index(pd.bdate_range('2024-01-01',periods=80).strftime('%Y-%m-%d'))
        market=pd.DataFrame({k:100+np.arange(len(days))*.01 for k in MARKET_KEYS},index=days)
        rows=[]
        for i,d in enumerate(days):
            row={k:float(i/20+j) for j,k in enumerate(FEATURES)}
            row.update(date=d,year=int(d[:4]),date_index=i,expiry_index=i+4,
                       expiry_date=str(pd.Timestamp(d)+pd.offsets.BDay(4))[:10],
                       net_return=.01,target=i%2,regime='UP_NORMALVOL')
            rows.append(row)
        matched,cov=make_matched_events(pd.DataFrame(rows),market)
        self.assertTrue(len(matched)>40)
        self.assertTrue(len(matched)<80)
        self.assertEqual(len(matched),cov['matched_complete_days'])
        self.assertFalse(matched[list(MARKET_FEATURES)].isna().any().any())

    def test_year_and_regime_counts_are_global_nonoverlap(self):
        dates=pd.bdate_range('2024-01-02','2026-10-25')
        rows=[]
        for i,d in enumerate(dates):
            x={k:float(np.sin(i/37+j/3)) for j,k in enumerate(FEATURES)}
            x.update({k:float(np.cos(i/19+j/7)) for j,k in enumerate(MARKET_FEATURES)})
            x.update(date=d.strftime('%Y-%m-%d'),year=d.year,date_index=i,
                     expiry_index=i+4,expiry_date=(d+pd.offsets.BDay(4)).strftime('%Y-%m-%d'),
                     target=int(i%3==0),net_return=.028 if i%3==0 else -.032,
                     regime=['UP_NORMALVOL','DOWN_HIGHVOL'][i%2])
            rows.append(x)
        res=run_matched_walkforward(pd.DataFrame(rows),min_train=150)
        self.assertEqual(res['status'],'RESEARCH_MATCHED_OOS_ONLY')
        self.assertEqual([x['year'] for x in res['folds'] if x['status']=='OOS'],[2025,2026])
        for name in res['strategies']:
            self.assertEqual(res['strategies'][name]['trades'],sum(x['trades'] for x in res['by_year'] if x['strategy']==name))
            self.assertEqual(res['strategies'][name]['trades'],sum(x['trades'] for x in res['by_regime'] if x['strategy']==name))
        for f in res['folds']:
            if f['status']=='OOS':self.assertLess(f['train_last_matured'],f['test_first_decision'])
        self.assertTrue(res['fred_not_pit_no_macro_training'])
        self.assertTrue(res['usdkrw_and_derived_excluded'])
        self.assertFalse(res['live_modified'])

if __name__=='__main__':unittest.main()