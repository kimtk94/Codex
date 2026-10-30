"""Research-only universe contract: never authorize LIVE orders by inclusion."""
import json
import unittest
from pathlib import Path


class UniverseContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((Path(__file__).parent/'recommended_universe_v1.json').read_text())

    def test_unique_tickers_and_fixed_counts(self):
        assets=self.data['assets']
        self.assertEqual(len(assets),24)
        self.assertEqual(len({(x['market'],x['symbol']) for x in assets}),24)
        self.assertEqual(sum(x['market']=='US' for x in assets),20)
        self.assertEqual(sum(x['market']=='UPBIT' for x in assets),4)

    def test_research_only_and_no_unsupported_claims(self):
        self.assertEqual(self.data['status'],'CANDIDATE_ONLY_NOT_LIVE')
        self.assertIs(self.data['live_policy_modified'],False)
        for asset in self.data['assets']:
            self.assertIn(asset['priority'],('P0','P1','P2'))
            self.assertTrue(asset['role'])
            self.assertTrue(asset['evidence'])
            self.assertTrue(asset['collect'])
            self.assertTrue(set(asset['collect'])<= {'1m','15m','60m','1d'})
            if asset['market']=='UPBIT':
                self.assertTrue(asset['symbol'].startswith('KRW-'))
        self.assertEqual(self.data['dynamic_cohorts']['mode'],
                         'POINT_IN_TIME_EVENT_COHORT_NOT_STATIC_TICKERS')

    def test_pair_roles_and_existing_baseline(self):
        assets={a['symbol']:a for a in self.data['assets']}
        self.assertEqual(assets['QQQ']['priority'],'P0')
        self.assertEqual(assets['QLD']['priority'],'P0')
        self.assertIn('1m',assets['TSLA']['collect'])
        self.assertIn('1m',assets['KRW-ETH']['collect'])
        self.assertIn('SIP',self.data['selection_policy']['intraday_provenance'])


if __name__=='__main__':
    unittest.main()
