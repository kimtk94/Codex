"""Kalman quant research stack.

Research modules are isolated from production execution.
"""

from .contracts import BacktestConfig, ExperimentSpec, Mode, WalkForwardFold
from .native_ledger import BacktestResult, run_backtest
from .portfolio import allocate
from .walk_forward import generate_walk_forward_folds

__all__ = [
    "BacktestConfig",
    "ExperimentSpec",
    "Mode",
    "WalkForwardFold",
    "BacktestResult",
    "run_backtest",
    "allocate",
    "generate_walk_forward_folds",
]
