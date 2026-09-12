from __future__ import annotations

import ast
import json
from pathlib import Path

NOTEBOOK = Path("notebooks/Kalman_Historical_Quant_2017_Colab_v3.ipynb")


def main() -> int:
    payload = json.loads(NOTEBOOK.read_text(encoding="utf-8"))

    cells = payload.get("cells", [])
    assert len(cells) == 1, f"expected 1 cell, got {len(cells)}"
    assert cells[0].get("cell_type") == "code"

    source = "".join(cells[0].get("source", []))
    assert source.strip(), "empty code cell"

    # Syntax / AST validity.
    compile(source, str(NOTEBOOK), "exec")
    ast.parse(source, filename=str(NOTEBOOK))

    required = [
        'START_DATE = "2017-01-01"',
        'KALMAN_VENV = Path("/content/.venv-kalman-v3")',
        'RISK_VENV = Path("/content/.venv-riskfolio-v3")',
        'PRECHECK_2017_HISTORY_INSUFFICIENT',
        'research.quant_stack.experiment_runner',
        'research.quant_stack.validate_artifacts',
        'research.quant_stack.lean_execution_runner',
        'research.quant_stack.riskfolio_benchmark_runner',
        'SAFETY : LIVE=False / Toss=False / Neon write=False',
        'FAILED PHASE:',
    ]
    for needle in required:
        assert needle in source, f"missing invariant: {needle}"

    forbidden = [
        "allow_live_execution=True",
        'broker="TOSS"',
        "toss_client",
        "production_writes",
        "neon_write=True",
        "WRITE_BACK=True",
    ]
    for needle in forbidden:
        assert needle not in source, f"forbidden live/write pattern: {needle}"

    # Colab host environment should not import pandas/numpy for parquet work.
    assert "\nimport pandas as pd\n" not in source
    assert "\nimport numpy as np\n" not in source

    # Historical test must not silently degrade to a later start year.
    assert "requested start year" in source
    assert "minimum_labeled" in source

    print("COLAB_V3_STATIC_CHECK=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
