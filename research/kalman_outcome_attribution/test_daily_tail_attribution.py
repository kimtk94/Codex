import unittest
import numpy as np
import pandas as pd
from daily_tail_attribution import tail_mean,bucketize,describe,decompose,analyze,BUCKETS

class TailAttributionContracts(unittest.TestCase):
    def test_fractional_tail_boundary(self):
        self.assertAlmostEqual(tail_mean([-.2,-.1,.1,.2,.3],.3),(-.2-.05)/1.5)
        self.assertAlmostEqual(tail_mean([-.2,-.1,.1,.2,.3],.3,True),(.3+.1)/1.5)
        with self.assertRaises(ValueError):tail_mean([np.nan])

    def test_exact_bucket_boundaries_and_contribution(self):
        net=pd.Series([-.10,-.05,-.01,0.,.01,.05,.10])
        self.assertEqual(bucketize(net).tolist(),list(BUCKETS))
        g=pd.DataFrame({'net':net,'signal_date':['2025-01-02']*len(net)})
        a=describe(g)
        self.assertAlmostEqual(sum(b['unconditional_mean_contribution'] for b in a['buckets'].values()),a['mean'])
        self.assertEqual(sum(b['n'] for b in a['buckets'].values()),len(net))

    def test_decomposition_with_unobserved_conditional_mean(self):
        a=describe(pd.DataFrame({'net':[.12,.02],'signal_date':['a','b']}))
        b=describe(pd.DataFrame({'net':[-.12,.01],'signal_date':['a','b']}))
        r=decompose(a,b)
        self.assertAlmostEqual(sum(v['total'] for v in r.values()),a['mean']-b['mean'])
        self.assertIsNone(r['WIN_GE10']['frequency_component'])
        self.assertIsNone(r['LOSS_GE10']['conditional_magnitude_component'])
        self.assertTrue(r['WIN_LT5']['both_conditional_means_observed'])

    def test_clipping_does_not_modify_labels_or_select_candidates(self):
        f=pd.DataFrame({'symbol':['SPY','QQQ','SPY','QQQ'],'signal_date':['2025-01-02']*2+['2025-01-03']*2,
            'gross_return':[.202,.002,.102,-.098],'qualifies':[True,False,True,False]})
        before=f.copy(deep=True);r=analyze(f,'BULL')['costs']['20']
        self.assertAlmostEqual(r['raw_contrast']['pooled'],.2)
        self.assertAlmostEqual(r['clipped_contrasts']['0.05']['pooled'],.075)
        self.assertEqual(r['clipped_contrasts']['0.05']['matched_groups'],2)
        pd.testing.assert_frame_equal(f,before)

    def test_bear_gate_must_be_common_by_date(self):
        f=pd.DataFrame({'symbol':['SPY','QQQ'],'signal_date':['2025-01-02']*2,
            'gross_return':[.1,.02],'qualifies':[True,False],'episode':[1,1]})
        with self.assertRaisesRegex(ValueError,'INVALID_BEAR_EPISODE_OR_COMMON_GATE'):analyze(f,'BEAR')

if __name__=='__main__':unittest.main()
