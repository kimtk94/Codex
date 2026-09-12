"""Kalman quant research stack.

Research modules are isolated from production execution.
"""

from .contracts import BacktestConfig, ExperimentSpec, Mode, WalkForwardFold
from .native_ledger import BacktestResult, run_backtest
from .lean_execution import (
    BrokerOrder,
    ExecutionCycleResult,
    ExecutionFill,
    ExecutionPolicy,
    ExecutionState,
    GatedOrderIntent,
    OrderIntent,
    PortfolioTargetContract,
    RiskAdjustedTarget,
    run_shadow_rebalance,
)
from .portfolio import allocate
from .portfolio_targets import PortfolioTargetResult, run_portfolio_target_layer
from .riskfolio_benchmarks import RiskfolioBenchmarkResult, run_riskfolio_benchmarks
from .walk_forward import generate_walk_forward_folds

__all__ = [
    "BacktestConfig",
    "ExperimentSpec",
    "Mode",
    "WalkForwardFold",
    "BacktestResult",
    "run_backtest",
    "BrokerOrder",
    "ExecutionCycleResult",
    "ExecutionFill",
    "ExecutionPolicy",
    "ExecutionState",
    "GatedOrderIntent",
    "OrderIntent",
    "PortfolioTargetContract",
    "RiskAdjustedTarget",
    "run_shadow_rebalance",
    "allocate",
    "PortfolioTargetResult",
    "run_portfolio_target_layer",
    "RiskfolioBenchmarkResult",
    "run_riskfolio_benchmarks",
    "generate_walk_forward_folds",
]
