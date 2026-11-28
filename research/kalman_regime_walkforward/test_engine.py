import unittest
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
from engine import triple_barrier, nonoverlap_select, run_walkforward, FEATURES, build_features

class WalkforwardTests(unittest.TestCase):
    def mock_group(self, opens, highs, lows, closes):
        return pd.DataFrame({'open':opens,'high':highs,'low':lows,'close':closes})

    def test_both_barriers_same_15min_choose_stop(self):
        g=self.mock_group([100.],[105.],[95.],[103.])
        result=triple_barrier([g,g,g,g],100.)
        self.assertEqual(result['outcome'],'STOP')
        self.assertEqual(result['target'],0)
        self.assertLess(result['net_return'],-.03)

    def test_gap_through_stop_uses_worse_open(self):
        g=self.mock_group([94.],[98.],[92.],[96.])
        result=triple_barrier([g,g,g,g],100.)
        self.assertEqual(result['outcome'],'STOP_GAP')
        self.assertLess(result['net_return'],-.06)

    def test_tp_exact_and_cost_deducted(self):
        g=self.mock_group([100.],[104.],[100.],[103.])
        result=triple_barrier([g,g,g,g],100.,leg_cost_bps=10)
        self.assertEqual(result['target'],1)
        self.assertLess(result['net_return'],.03)
        self.assertGreater(result['net_return'],.027)

    def test_no_imputation_of_partial_four_days(self):
        g=self.mock_group([100.],[101.],[99.],[100.])
        self.assertIsNone(triple_barrier([g,g,None,g],100.))

    def test_nonoverlap_four_sessions(self):
        df=pd.DataFrame({'date_index':[0,1,4,5,9], 'expiry_index':[4,5,8,9,13],
                         'trade':[True]*5,'net_return':[0]*5,'target':[0]*5})
        out=nonoverlap_select(df,df['trade'])
        self.assertEqual(out['date_index'].tolist(),[0,5])

    def test_walkforward_mature_labels_only(self):
        # Synthetic independent events to assert label maturities and no train/test mixing.
        rows=[]
        for i,day in enumerate(pd.bdate_range('2019-01-01','2023-12-29')):
            row={k:float(np.sin(i/29.0+j*0.17)) for j,k in enumerate(FEATURES)}
            row.update(date=day.strftime('%Y-%m-%d'), year=day.year,date_index=i,
                       expiry_index=i+4,expiry_date=(day+pd.offsets.BDay(4)).strftime('%Y-%m-%d'),
                       regime='UP_NORMALVOL',net_return=.03 if i%3==0 else -.03,
                       target=int(i%3==0))
            rows.append(row)
        result=run_walkforward(pd.DataFrame(rows),2022)
        self.assertEqual(result['status'],'RESEARCH_OOS_ONLY')
        self.assertTrue(result['no_1min_execution'])
        self.assertTrue(result['no_live_changes'])
        self.assertEqual(len(result['folds']),2)
        for f in result['folds']:
            self.assertLess(f['train_label_last_date'],f['test_first_decision'])
        self.assertEqual(set(result['strategies']),{'logistic_p70','trend20','unconditional_QLD'})
        # Global position selection must not be repeated independently within
        # year/regime groups, otherwise summary trade counts are inflated.
        for name,metric in result['strategies'].items():
            self.assertEqual(metric['trades'],sum(x['trades'] for x in result['by_year'] if x['strategy']==name))
        self.assertEqual(result['strategies']['logistic_p70']['trades'],
                         sum(x['model_trade_count'] for x in result['by_regime']))

    def test_features_are_backward_looking(self):
        idx=pd.bdate_range('2025-01-01',periods=90).strftime('%Y-%m-%d')
        def make(price):
            df=pd.DataFrame(index=idx)
            df['complete']=True
            df['close']=np.linspace(100,200,90)
            df['open']=df['close']*.999
            df['intraday']=df['close']/df['open']-1
            df['volume']=1000.
            return (df,{})
        data={'QQQ':make(1),'QLD':make(2)}
        a=build_features(data)
        data['QQQ'][0].loc[idx[-1],'close']=1e6
        b=build_features(data)
        pd.testing.assert_series_equal(a.iloc[-2][FEATURES],b.iloc[-2][FEATURES])

if __name__=='__main__':unittest.main()