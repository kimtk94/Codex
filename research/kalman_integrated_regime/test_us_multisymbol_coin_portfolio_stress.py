"""Contracts for research-only five-ticker costs, portfolio allocation and COIN attribution."""
import unittest
import numpy as np
import pandas as pd

from research.kalman_integrated_regime.us_multisymbol_coin_portfolio_stress import (
    SYMBOLS, COST_BPS, POLICIES, ARMS, net_returns, metrics,
    concentration, summarize_panels,
)


def mock_panels():
    dates=pd.bdate_range("2026-01-05",periods=10)
    panels={}
    for sym in SYMBOLS:
        for year in (2025,2026):
            d=dates-pd.DateOffset(years=2026-year)
            f=pd.DataFrame({
                "trade_date":d,
                "signal_P_unweighted":[True,False]*5,
                "signal_V_unweighted":[True,True,False,False,True]*2,
                "signal_ALWAYS_INTRADAY_LONG":[True]*10,
                "gross_NEXT_RTH_CLOSE":[.02,-.01,.005,-.01,.01,.02,-.01,.005,-.01,.01],
                "gross_SAME_SESSION_TP3_SL3":[.03,-.03,.005,-.03,.01,.03,-.03,.005,-.03,.01],
                "regime_rvol2":[False,True]*5,
                "regime_train_high_price_vol":[True,False]*5,
                "regime_prior20_negative":[True,False]*5,
            })
            panels[(sym,year)]=f
    return panels


class StressContracts(unittest.TestCase):
    def test_fixed_cost_applied_only_when_entering(self):
        gross=np.array([.02,-.01,.01])
        sig=np.array([True,False,True])
        self.assertTrue(np.allclose(net_returns(gross,sig,30),[.017,0,.007]))
        with self.assertRaisesRegex(ValueError,"COST_OR_SIGNAL_INVALID"):
            net_returns(gross,sig,-1)

    def test_zero_trades_no_drawdown_and_expensive_cost_is_worse(self):
        sig=np.array([True,False,True])
        gross=np.array([.02,.03,.01])
        costs=[metrics(net_returns(gross,sig,cost),sig)["cumulative_return_pct"]
               for cost in COST_BPS]
        self.assertEqual(costs,sorted(costs,reverse=True))
        self.assertEqual(metrics([0,0,0],[False]*3)["mdd_daily_close_pct"],0)

    def test_all_five_symbols_use_one_portfolio_cash_and_equal_weights(self):
        result=summarize_panels(mock_panels(),{"complete":True})
        self.assertEqual(result["status"],"EXPLORATORY_COST_STRESS_LIVE_HOLD")
        for year in ("2025","2026"):
            for policy in POLICIES:
                equal=result["equalweight_daily_rebalance_portfolio"][year][policy]
                for arm in ARMS:
                    for cost in COST_BPS:
                        v=equal[arm][str(cost)]
                        # Identical synthetic returns across 5 tickers:
                        # equal-weight portfolio must equal each isolated ticker.
                        ticker=result["by_symbol"]["COIN"][year]["policies"][policy]
                        ticker=ticker["cost_sensitivity_roundtrip_bps"][arm][str(cost)]
                        self.assertAlmostEqual(v["cumulative_return_pct"],
                                               ticker["cumulative_return_pct"])
                        self.assertEqual(v["total_ticker_trades"],5*ticker["trades"])
                        self.assertEqual(v["days"],10)
                        self.assertLessEqual(v["mean_invested_portfolio_fraction"],1)
        self.assertFalse(result["live_changed"])

    def test_monthly_concentration_reconciles_daily_compound(self):
        f=mock_panels()[("COIN",2026)]
        detail=concentration(f,"NEXT_RTH_CLOSE","V_unweighted",30)
        self.assertGreaterEqual(len(detail["monthly"]),1)
        self.assertEqual(sum(x["trades"] for x in detail["monthly"]),
                         int(f.signal_V_unweighted.sum()))
        self.assertTrue(detail["removed_top_days_are_diagnostic_not_investable"])
        self.assertGreaterEqual(detail["gross_positive_trade_log_contribution_pct_from_top_5"],0)
        self.assertLessEqual(detail["gross_positive_trade_log_contribution_pct_from_top_5"],100)
        self.assertGreaterEqual(detail["signal_day_prior20_price_decline"]["trades"],0)


if __name__=="__main__":
    unittest.main()
