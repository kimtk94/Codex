from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from .contracts import WalkForwardFold


def _unique_index(timestamps: Iterable[object]) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(pd.to_datetime(list(timestamps), utc=True, errors="raise"))
    idx = idx.drop_duplicates().sort_values()
    if idx.empty:
        raise ValueError("timestamps are empty")
    return idx


def generate_walk_forward_folds(
    timestamps: Iterable[object],
    *,
    train_observations: int = 504,
    valid_observations: int = 63,
    test_observations: int = 126,
    purge_observations: int = 5,
    step_observations: int | None = None,
    expanding: bool = True,
) -> list[WalkForwardFold]:
    """Generate deterministic purged walk-forward folds.

    This intentionally mirrors Qlib-style rolling experiment semantics without
    making Qlib a production dependency.

    Layout per fold:
        TRAIN -> PURGE -> VALID -> PURGE -> TEST
    """
    for name, value in {
        "train_observations": train_observations,
        "valid_observations": valid_observations,
        "test_observations": test_observations,
        "purge_observations": purge_observations,
    }.items():
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
    if train_observations <= 0 or test_observations <= 0:
        raise ValueError("train_observations and test_observations must be > 0")

    idx = _unique_index(timestamps)
    step = step_observations or test_observations
    if step <= 0:
        raise ValueError("step_observations must be > 0")

    folds: list[WalkForwardFold] = []
    cursor = train_observations
    fold_id = 0

    while True:
        train_start_i = 0 if expanding else cursor - train_observations
        train_end_i = cursor - 1
        valid_start_i = cursor + purge_observations
        valid_end_i = valid_start_i + valid_observations - 1
        test_start_i = valid_end_i + 1 + purge_observations
        test_end_i = test_start_i + test_observations - 1

        if valid_observations == 0:
            valid_start_i = train_end_i
            valid_end_i = train_end_i
            test_start_i = cursor + purge_observations

        if test_end_i >= len(idx):
            break

        folds.append(
            WalkForwardFold(
                fold_id=fold_id,
                train_start=idx[train_start_i].isoformat(),
                train_end=idx[train_end_i].isoformat(),
                valid_start=idx[valid_start_i].isoformat(),
                valid_end=idx[valid_end_i].isoformat(),
                test_start=idx[test_start_i].isoformat(),
                test_end=idx[test_end_i].isoformat(),
                purge_observations=purge_observations,
            )
        )

        fold_id += 1
        cursor += step

    return folds
