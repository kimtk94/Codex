from __future__ import annotations

import numpy as np
import pandas as pd


def _normalize(weights: pd.Series) -> pd.Series:
    weights = pd.to_numeric(weights, errors="coerce").fillna(0.0).clip(lower=0.0)
    total = float(weights.sum())
    if total <= 0:
        raise ValueError("weights sum to zero")
    return weights / total


def equal_weight(returns: pd.DataFrame) -> pd.Series:
    cols = list(returns.columns)
    if not cols:
        raise ValueError("returns has no assets")
    return pd.Series(1.0 / len(cols), index=cols, dtype=float)


def inverse_volatility(returns: pd.DataFrame) -> pd.Series:
    vol = returns.std(ddof=0).replace(0.0, np.nan)
    inv = 1.0 / vol
    if inv.dropna().empty:
        return equal_weight(returns)
    return _normalize(inv.fillna(0.0))


def pypfopt_hrp(returns: pd.DataFrame) -> pd.Series:
    """Optional PyPortfolioOpt adapter.

    PyPortfolioOpt is intentionally imported lazily so Kalman production does
    not depend on it. Install only in the research environment.
    """
    try:
        from pypfopt import HRPOpt
    except ImportError as exc:
        raise RuntimeError(
            "PyPortfolioOpt is not installed. "
            "Install research/quant_stack/requirements.txt in the research venv."
        ) from exc

    optimizer = HRPOpt(returns=returns.dropna(how="all"))
    weights = optimizer.optimize()
    return _normalize(pd.Series(weights, dtype=float).reindex(returns.columns).fillna(0.0))


def pypfopt_max_sharpe(returns: pd.DataFrame) -> pd.Series:
    try:
        from pypfopt import EfficientFrontier, expected_returns, risk_models
    except ImportError as exc:
        raise RuntimeError(
            "PyPortfolioOpt is not installed. "
            "Install research/quant_stack/requirements.txt in the research venv."
        ) from exc

    clean = returns.dropna(how="all")
    prices = (1.0 + clean.fillna(0.0)).cumprod()
    mu = expected_returns.mean_historical_return(prices, frequency=252)
    cov = risk_models.CovarianceShrinkage(prices, frequency=252).ledoit_wolf()
    ef = EfficientFrontier(mu, cov, weight_bounds=(0.0, 1.0))
    ef.max_sharpe()
    return _normalize(pd.Series(ef.clean_weights(), dtype=float).reindex(returns.columns).fillna(0.0))


def allocate(returns: pd.DataFrame, method: str = "inverse_volatility") -> pd.Series:
    method = method.strip().lower()
    if method == "equal_weight":
        return equal_weight(returns)
    if method == "inverse_volatility":
        return inverse_volatility(returns)
    if method == "hrp":
        return pypfopt_hrp(returns)
    if method == "max_sharpe":
        return pypfopt_max_sharpe(returns)
    raise ValueError(f"unsupported allocation method: {method}")
