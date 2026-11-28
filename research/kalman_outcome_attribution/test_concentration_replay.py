import unittest
import pandas as pd
from concentration_replay import bear_episodes,summarize,positive_concentration


class ConcentrationContracts(unittest.TestCase):
    def test_bear_episodes_split_on_bull_and_missing(self):
        dates=pd.bdate_range("2025-01-01",periods=8)
        state=pd.DataFrame({"bull":[True,False,False,True,False,None,False,False]},index=dates)
        self.assertEqual(bear_episodes(state,dates),[
            (dates[1],dates[2],2),(dates[4],dates[4],1),(dates[6],dates[7],2)])

    def test_positive_symbol_denominator_excludes_negative_symbols(self):
        result=positive_concentration({"A":{"pnl":40.},"B":{"pnl":30.},
            "C":{"pnl":20.},"D":{"pnl":10.},"E":{"pnl":-80.}})
        self.assertAlmostEqual(result["top3_positive_symbol_pnl_share"],.9)
        self.assertAlmostEqual(result["positive_symbol_pnl_hhi"],.3)
        self.assertIsNone(positive_concentration({"A":{"pnl":-1.}})["positive_symbol_pnl_hhi"])

    def test_pnl_conservation_and_unclosed_position(self):
        c=pd.DataFrame({"active_positions":[1,0],"cash":[80000.,100100.],
            "equity":[100000.,100100.],"drawdown":[0.,0.],"gross_exposure":[.2,0.]})
        f=pd.DataFrame({"net_pnl":[100.],"realized_return":[.005]})
        self.assertAlmostEqual(summarize(c,f)["total_return"],.001)
        with self.assertRaisesRegex(ValueError,"CASH_PNL_CONSERVATION_MISMATCH"):
            summarize(c,f.assign(net_pnl=200.))
        with self.assertRaisesRegex(ValueError,"CASH_OR_UNCLOSED_POSITION"):
            summarize(c.assign(active_positions=[1,1]),f)


if __name__=="__main__":
    unittest.main()
