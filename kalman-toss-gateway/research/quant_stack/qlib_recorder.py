from __future__ import annotations

import contextlib
import importlib.util
import math
import os
from pathlib import Path
from typing import Any, Iterator


def qlib_available() -> bool:
    return importlib.util.find_spec("qlib") is not None


@contextlib.contextmanager
def _working_directory(path: Path) -> Iterator[None]:
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def _param_value(value: Any) -> str | int | float | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    if isinstance(value, str):
        return value
    return str(value)


def _numeric_metrics(metrics: dict[str, Any]) -> dict[str, float]:
    out: dict[str, float] = {}
    for key, value in metrics.items():
        if isinstance(value, bool):
            out[str(key)] = float(value)
        elif isinstance(value, (int, float)):
            number = float(value)
            if math.isfinite(number):
                out[str(key)] = number
    return out


def record_market_experiment(
    *,
    experiment_name: str,
    tracking_root: Path,
    provider_root: Path,
    params: dict[str, Any],
    metrics: dict[str, Any],
    artifact_manifest: dict[str, Any],
) -> dict[str, Any]:
    """Record one Kalman market backtest in Qlib Recorder.

    Qlib is used only as an experiment/recorder layer. Kalman remains the
    authoritative source for data, model outputs, execution semantics and PnL.

    Qlib 0.9.7 is paired here with an SQLite MLflow tracking backend.
    This avoids MLflow 3.x filesystem-tracking deprecation/maintenance mode
    and also avoids Qlib's absolute file-URI lock-path issue.
    """
    if not qlib_available():
        raise RuntimeError(
            "Qlib recorder requested but pyqlib is not installed. "
            "Install research/quant_stack/requirements-qlib.txt."
        )

    tracking_root = Path(tracking_root).expanduser().resolve()
    provider_root = Path(provider_root).expanduser().resolve()
    tracking_root.mkdir(parents=True, exist_ok=True)
    provider_root.mkdir(parents=True, exist_ok=True)

    # Import lazily so the base Kalman research environment does not require Qlib.
    import qlib
    from qlib.constant import REG_US
    from qlib.workflow import R

    db_name = "qlib_mlflow.db"
    tracking_db = tracking_root / db_name
    exp_manager = {
        "class": "MLflowExpManager",
        "module_path": "qlib.workflow.expm",
        "kwargs": {
            # Keep the SQLite URI relative to the controlled working directory.
            # This is portable across server/CI paths and avoids file-store mode.
            "uri": f"sqlite:///{db_name}",
            "default_exp_name": experiment_name,
        },
    }

    with _working_directory(tracking_root):
        qlib.init(
            provider_uri=str(provider_root),
            region=REG_US,
            exp_manager=exp_manager,
            skip_if_reg=True,
        )
        with R.start(experiment_name=experiment_name):
            R.log_params(**{str(k): _param_value(v) for k, v in params.items()})
            numeric = _numeric_metrics(metrics)
            if numeric:
                R.log_metrics(**numeric)
            R.save_objects(**{"kalman_manifest.pkl": artifact_manifest})
            recorder = R.get_recorder()
            recorder_id = str(recorder.id)

    return {
        "status": "RECORDED",
        "backend": "QLIB_RECORDER_MLFLOW_SQLITE",
        "experiment_name": experiment_name,
        "recorder_id": recorder_id,
        "tracking_root": str(tracking_root),
        "tracking_db": str(tracking_db),
        "authoritative_data_source": "KALMAN",
        "authoritative_execution_engine": "KALMAN_NATIVE_LEDGER",
    }
