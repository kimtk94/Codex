import unittest
import pandas as pd
from research.regime_countertrend.peer_macro_stress_v4 import prepare,evaluate

class PeerMacroStressV4Tests(unittest.TestCase):
    def example(self):
        rows=[]
        for i,(symbol,year) in enumerate([
             ("AMD",2022),("NVDA",2022),("MU",2023),("AMAT",2023),
             ("CRM",2024),("ORCL",2024),("MSFT",2025),("AAPL",2025),
             ("AMD",2026),("MU",2026)]):
            market=.53 if i%2 else .59
            peer=.72 if i<4 else float("nan")
            symbol_prob=.61 if i%3==0 else float("nan")
            haspeer=i<4
            hassym=i%3==0
            both=(1-.3*int(haspeer)-.2*int(hassym))*market+(
                .3*(peer if haspeer else 0))+.2*(symbol_prob if hassym else 0)
            rows.append({"date":f"{year}-03-{i+1:02d}","year":year,
                "symbol":symbol,"industry":"SEMICONDUCTORS" if i<4 else "SOFTWARE",
                "event":"SIDE_DIP","net_20bp":.028 if i%2 else -.032,
                "win":i%2,"macro_market_probability":market,
                "peer_probability":peer,"symbol_probability":symbol_prob,
                "macro_peer_probability":both,
                "macro_market_selected":market>=.55,
                "macro_peer_selected":both>=.55,
                "peer_available":haspeer,"symbol_available":hassym})
        return pd.DataFrame(rows)
    def test_component_separation_no_retrain(self):
        d=prepare(self.example())
        self.assertIn("macro_peer_only_selected",d.columns)
        self.assertIn("macro_symbol_only_selected",d.columns)
        self.assertEqual(len(d),10)
        self.assertEqual(d.peer_available.sum(),4)
    def test_reject_modified_original_mixture(self):
        d=self.example()
        d.loc[0,"macro_peer_probability"]=.0001
        with self.assertRaises(ValueError):
            prepare(d)
    def test_stress_blocks_promotion_and_cost_robustness(self):
        _,costs,annual,increment,r=evaluate(self.example(),
            placebo_draws=150,bootstrap_draws=500)
        self.assertFalse(r["promotion_allowed"])
        self.assertFalse(r["year_cluster_bootstrap"]["independent_significance"])
        self.assertEqual(len(annual),20)
        self.assertEqual(len(increment),5)
        self.assertEqual(r["peer_usable_2025_2026"],0)
        self.assertEqual(set(costs.roundtrip),{"20bp","40bp","80bp"})
        for model,grp in costs.groupby("model"):
            v=grp.set_index("roundtrip").net_per_opportunity
            self.assertGreater(v.loc["20bp"],v.loc["40bp"])
            self.assertGreater(v.loc["40bp"],v.loc["80bp"])
if __name__=="__main__":unittest.main()
