from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import traceback
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


MARKETS = ("US", "KR", "BTC")

DIAGNOSTIC_STATUS_PATH: Path | None = None
DIAGNOSTIC_LOG_PATH: Path | None = None
_DIAGNOSTIC_HANDLE = None
_ORIGINAL_STDOUT = sys.stdout
_ORIGINAL_STDERR = sys.stderr


class Tee:
    def __init__(self, *streams: Any) -> None:
        self.streams = streams

    def write(self, data: str) -> int:
        for stream in self.streams:
            stream.write(data)
            stream.flush()
        return len(data)

    def flush(self) -> None:
        for stream in self.streams:
            stream.flush()


def write_diagnostic_status(status: str, **extra: Any) -> None:
    if DIAGNOSTIC_STATUS_PATH is None:
        return
    payload = {
        "status": status,
        "phase": Phase.current if "Phase" in globals() else "BOOTSTRAP",
        "updated_at": datetime.now().astimezone().isoformat(),
        **extra,
    }
    tmp = DIAGNOSTIC_STATUS_PATH.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, DIAGNOSTIC_STATUS_PATH)


def init_diagnostics(drive_root: Path) -> None:
    global DIAGNOSTIC_STATUS_PATH, DIAGNOSTIC_LOG_PATH, _DIAGNOSTIC_HANDLE

    if not drive_root.exists():
        return

    diag_dir = drive_root / "Kalman_Diagnostics"
    diag_dir.mkdir(parents=True, exist_ok=True)
    DIAGNOSTIC_STATUS_PATH = diag_dir / "historical_colab_last_status.json"
    DIAGNOSTIC_LOG_PATH = diag_dir / "historical_colab_last.log"

    _DIAGNOSTIC_HANDLE = DIAGNOSTIC_LOG_PATH.open(
        "w",
        encoding="utf-8",
        buffering=1,
    )
    sys.stdout = Tee(_ORIGINAL_STDOUT, _DIAGNOSTIC_HANDLE)
    sys.stderr = Tee(_ORIGINAL_STDERR, _DIAGNOSTIC_HANDLE)
    write_diagnostic_status(
        "RUNNING",
        log_path=str(DIAGNOSTIC_LOG_PATH),
    )


@dataclass(frozen=True)
class Config:
    drive_root: Path
    start_date: str = "2017-01-01"
    train_obs: int = 504
    valid_obs: int = 63
    test_obs: int = 126
    max_hold_bars: int = 20
    portfolio_method: str = "hrp"
    portfolio_lookback: int = 180
    portfolio_min_obs: int = 90
    portfolio_rebalance: str = "M"
    recreate_venvs: bool = True
    run_riskfolio: bool = True
    enable_qlib_recorder: bool = False


class PrecheckBlocked(RuntimeError):
    pass


class Phase:
    current = "BOOTSTRAP"

    @classmethod
    def set(cls, value: str) -> None:
        cls.current = value
        write_diagnostic_status("RUNNING")
        print("\n" + "=" * 88)
        print(f"PHASE: {value}")
        print("=" * 88)


def run(
    cmd: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    proc = subprocess.Popen(
        args,
        cwd=cwd,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
    return_code = proc.wait()
    if return_code != 0:
        raise subprocess.CalledProcessError(return_code, args)


def capture(
    cmd: list[str | Path],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    try:
        output = subprocess.check_output(
            args,
            cwd=cwd,
            env=env,
            text=True,
            stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        if exc.output:
            print(exc.output, end="" if exc.output.endswith("\n") else "\n")
        raise
    if output:
        print(output, end="" if output.endswith("\n") else "\n")
    return output.strip()


def bounded_find_dir(root: Path, target_name: str, max_depth: int = 5) -> Path | None:
    if not root.exists():
        return None
    base_depth = len(root.parts)
    for current, dirs, _files in os.walk(root):
        current_path = Path(current)
        depth = len(current_path.parts) - base_depth
        if depth > max_depth:
            dirs[:] = []
            continue
        if current_path.name == target_name:
            return current_path
    return None


def find_model_root(drive_root: Path) -> Path | None:
    candidates = [
        drive_root / "Market_Model_V2",
        drive_root / "Kalman" / "Market_Model_V2",
        drive_root / "kalman" / "Market_Model_V2",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return bounded_find_dir(drive_root, "Market_Model_V2", max_depth=5)


def find_named_v2_root(
    drive_root: Path,
    model_root: Path,
    name: str,
) -> Path | None:
    candidates = [
        model_root.parent / name / "v2",
        drive_root / name / "v2",
        drive_root / "Kalman" / name / "v2",
        drive_root / "kalman" / name / "v2",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate

    root = bounded_find_dir(drive_root, name, max_depth=5)
    if root is not None and (root / "v2").exists():
        return root / "v2"
    return None


def _first_existing(candidates: list[Path]) -> Path | None:
    for candidate in candidates:
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def find_historical_sources(
    market_root: Path | None,
    feature_root: Path | None,
) -> tuple[Path, Path]:
    if market_root is None or not market_root.exists():
        raise PrecheckBlocked("Market_Data/v2 not found")
    if feature_root is None or not feature_root.exists():
        raise PrecheckBlocked("Market_Features/v2 not found")

    raw_dir = market_root / "raw" / "historical_2017"
    feature_dir = feature_root / "talib" / "historical_2017"
    if not raw_dir.exists():
        raise PrecheckBlocked(f"historical raw folder missing: {raw_dir}")
    if not feature_dir.exists():
        raise PrecheckBlocked(f"historical feature folder missing: {feature_dir}")

    raw = _first_existing(
        [
            raw_dir / "multimarket_raw_2017_present.parquet",
            raw_dir / "multimarket_raw_2017_present_v0_3.parquet",
        ]
    )
    if raw is None:
        raw_candidates = sorted(
            (
                path
                for path in raw_dir.glob("multimarket_raw_*2017*present*.parquet")
                if "warmup" not in path.name.lower()
            ),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        raw = raw_candidates[0] if raw_candidates else None

    features = _first_existing(
        [
            feature_dir / "multimarket_features_2017_present_v0_3.parquet",
            feature_dir / "multimarket_features_2017_present.parquet",
        ]
    )
    if features is None:
        feature_candidates = sorted(
            feature_dir.glob("multimarket_features_*2017*present*.parquet"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        features = feature_candidates[0] if feature_candidates else None

    if raw is None:
        raise PrecheckBlocked(
            f"historical integrated raw parquet not found under {raw_dir}"
        )
    if features is None:
        raise PrecheckBlocked(
            f"historical integrated feature parquet not found under {feature_dir}"
        )
    return raw, features


def create_venv(path: Path, *, recreate: bool) -> None:
    if recreate and path.exists():
        shutil.rmtree(path)
    if (path / "bin/python").exists():
        return

    try:
        run([sys.executable, "-m", "venv", path])
    except subprocess.CalledProcessError:
        run([sys.executable, "-m", "pip", "install", "-q", "virtualenv"])
        run([sys.executable, "-m", "virtualenv", path])

    if not (path / "bin/python").exists():
        raise RuntimeError(f"virtualenv creation failed: {path}")


def minimum_labeled_rows(train: int, valid: int, test: int, horizon: int) -> int:
    return int(train + valid + test + (2 * horizon))


def validate_coverage(
    coverage: dict[str, dict[str, Any]],
    *,
    start_date: str,
    spec: dict[str, Any],
    train_obs: int,
    valid_obs: int,
    test_obs: int,
) -> list[str]:
    errors: list[str] = []
    start_year = int(start_date[:4])

    for market in MARKETS:
        info = coverage[market]
        horizon = int(spec["markets"][market]["horizon_observations"])
        required = minimum_labeled_rows(train_obs, valid_obs, test_obs, horizon)

        if int(info["labeled_rows"]) < required:
            errors.append(
                f"{market}: labeled_rows={info['labeled_rows']} < required={required}"
            )

        min_labeled = info.get("min_labeled_as_of")
        if not min_labeled:
            errors.append(f"{market}: no labeled history")
            continue

        if int(str(min_labeled)[:4]) > start_year:
            errors.append(
                f"{market}: earliest labeled year={str(min_labeled)[:4]} "
                f"> requested={start_year}"
            )
    return errors


def build_historical_matrices(
    *,
    kpy: Path,
    app_root: Path,
    raw_parquet: Path,
    feature_parquet: Path,
    matrix_dir: Path,
    spec_path: Path,
    start_date: str,
) -> None:
    if matrix_dir.exists():
        shutil.rmtree(matrix_dir)
    matrix_dir.mkdir(parents=True)

    run(
        [
            kpy,
            "-m",
            "research.model_v2.build_historical_feature_matrix",
            "--raw-parquet",
            raw_parquet,
            "--feature-parquet",
            feature_parquet,
            "--spec",
            spec_path,
            "--output-dir",
            matrix_dir,
            "--start-date",
            start_date,
        ],
        cwd=app_root,
    )

    status_path = matrix_dir / "historical_feature_matrix_run_status.json"
    if not status_path.exists():
        raise RuntimeError("historical matrix builder did not write status")
    status = json.loads(status_path.read_text(encoding="utf-8"))
    if status.get("status") != "READY":
        raise RuntimeError(
            "historical matrix builder failed: "
            + json.dumps(status.get("markets", {}), ensure_ascii=False)
        )


def coverage_report(
    kpy: Path,
    matrix_dir: Path,
) -> dict[str, dict[str, Any]]:
    script = """
import json
import sys
from pathlib import Path
import pandas as pd

root = Path(sys.argv[1])
result = {}
for market in ("us", "kr", "btc"):
    frame = pd.read_parquet(
        root / f"{market}_matrix.parquet",
        columns=["as_of", "target_label"],
    )
    ts = pd.to_datetime(frame["as_of"], utc=True, errors="coerce")
    labeled_mask = frame["target_label"].notna() & ts.notna()
    labeled_ts = ts.loc[labeled_mask]
    valid_ts = ts.dropna()
    result[market.upper()] = {
        "rows": int(len(frame)),
        "labeled_rows": int(labeled_mask.sum()),
        "min_as_of": None if valid_ts.empty else valid_ts.min().isoformat(),
        "max_as_of": None if valid_ts.empty else valid_ts.max().isoformat(),
        "min_labeled_as_of": (
            None if labeled_ts.empty else labeled_ts.min().isoformat()
        ),
        "max_labeled_as_of": (
            None if labeled_ts.empty else labeled_ts.max().isoformat()
        ),
    }
print(json.dumps(result))
"""
    raw = capture([kpy, "-c", script, matrix_dir])
    return json.loads(raw.splitlines()[-1])


def print_coverage(
    coverage: dict[str, dict[str, Any]],
    spec_payload: dict[str, Any],
    cfg: Config,
) -> None:
    for market in MARKETS:
        info = coverage[market]
        horizon = int(spec_payload["markets"][market]["horizon_observations"])
        required = minimum_labeled_rows(
            cfg.train_obs,
            cfg.valid_obs,
            cfg.test_obs,
            horizon,
        )
        print(
            f"{market:4s} rows={int(info['rows']):,} "
            f"labeled={int(info['labeled_rows']):,} "
            f"min_labeled={info['min_labeled_as_of']} "
            f"max_labeled={info['max_labeled_as_of']} "
            f"required>={required}"
        )


def final_summary(kpy: Path, output_dir: Path) -> None:
    script = """
import json
import sys
from pathlib import Path
import pandas as pd

root = Path(sys.argv[1])

def load_json(path):
    path = Path(path)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None

rows = []
for market in ("us", "kr", "btc"):
    perf = load_json(root / market / "historical_performance.json")
    if perf:
        rows.append({
            "method": market.upper(),
            "source": "MARKET_BACKTEST",
            "total_return": perf.get("total_return"),
            "cagr": perf.get("cagr"),
            "sharpe": perf.get("sharpe"),
            "max_drawdown": perf.get("max_drawdown"),
            "trade_count": perf.get("trade_count"),
        })

hrp = load_json(root / "portfolio" / "portfolio_performance.json")
if hrp:
    rows.append({
        "method": "HRP",
        "source": "PYPFOPT",
        "total_return": hrp.get("total_return"),
        "cagr": hrp.get("cagr"),
        "sharpe": hrp.get("sharpe"),
        "max_drawdown": hrp.get("max_drawdown"),
        "trade_count": None,
    })

risk_cmp = root / "riskfolio" / "riskfolio_comparison.csv"
if risk_cmp.exists():
    rdf = pd.read_csv(risk_cmp)
    for _, row in rdf.iterrows():
        if str(row.get("source", "")).upper() == "PYPFOPT":
            continue
        rows.append({
            "method": str(row.get("method")),
            "source": str(row.get("source", "RISKFOLIO")),
            "total_return": row.get("total_return"),
            "cagr": row.get("cagr"),
            "sharpe": row.get("sharpe"),
            "max_drawdown": row.get("max_drawdown"),
            "trade_count": None,
        })

df = pd.DataFrame(rows)
if not df.empty:
    printable = df.copy()
    for col in ("total_return", "cagr", "max_drawdown"):
        printable[col] = pd.to_numeric(printable[col], errors="coerce").map(
            lambda x: f"{x*100:.2f}%" if pd.notna(x) else "-"
        )
    printable["sharpe"] = pd.to_numeric(
        printable["sharpe"], errors="coerce"
    ).round(3)
    print("\nKALMAN HISTORICAL QUANT FINAL SUMMARY")
    print(printable.to_string(index=False))
    df.to_csv(root / "kalman_final_comparison.csv", index=False)

execution = load_json(root / "execution" / "execution_status.json")
validation = load_json(root / "historical_validation_report.json")
print("\nLEAN-INSPIRED SHADOW EXECUTION")
print(json.dumps(execution, ensure_ascii=False, indent=2, default=str))
print("\nVALIDATION")
print(json.dumps(validation, ensure_ascii=False, indent=2, default=str))
"""
    print(capture([kpy, "-c", script, output_dir]))


def self_test() -> None:
    assert minimum_labeled_rows(504, 63, 126, 5) == 703
    assert minimum_labeled_rows(504, 63, 126, 7) == 707

    spec = {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 7},
        }
    }
    good = {
        "US": {
            "labeled_rows": 1000,
            "min_labeled_as_of": "2017-01-03T00:00:00+00:00",
        },
        "KR": {
            "labeled_rows": 1000,
            "min_labeled_as_of": "2017-01-03T00:00:00+00:00",
        },
        "BTC": {
            "labeled_rows": 1000,
            "min_labeled_as_of": "2017-01-03T00:00:00+00:00",
        },
    }
    assert validate_coverage(
        good,
        start_date="2017-01-01",
        spec=spec,
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    ) == []

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        market_root = root / "Market_Data" / "v2"
        feature_root = root / "Market_Features" / "v2"
        raw_dir = market_root / "raw" / "historical_2017"
        feature_dir = feature_root / "talib" / "historical_2017"
        raw_dir.mkdir(parents=True)
        feature_dir.mkdir(parents=True)

        raw = raw_dir / "multimarket_raw_2017_present.parquet"
        features = feature_dir / "multimarket_features_2017_present_v0_3.parquet"
        raw.write_bytes(b"raw")
        features.write_bytes(b"features")

        found_raw, found_features = find_historical_sources(
            market_root,
            feature_root,
        )
        assert found_raw == raw
        assert found_features == features

    print("SELF_TEST=PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Kalman 2017 historical quant Colab runner"
    )
    parser.add_argument("--drive-root", default="/content/drive/MyDrive")
    parser.add_argument("--start-date", default="2017-01-01")
    parser.add_argument("--keep-venvs", action="store_true")
    parser.add_argument("--disable-riskfolio", action="store_true")
    parser.add_argument("--enable-qlib-recorder", action="store_true")
    parser.add_argument("--self-test", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        return 0

    cfg = Config(
        drive_root=Path(args.drive_root),
        start_date=args.start_date,
        recreate_venvs=not bool(args.keep_venvs),
        run_riskfolio=not bool(args.disable_riskfolio),
        enable_qlib_recorder=bool(args.enable_qlib_recorder),
    )
    init_diagnostics(cfg.drive_root)

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    spec_path = app_root / "config/model-v2-historical-spec.json"
    pypfopt_req = app_root / "research/quant_stack/requirements-pypfopt.txt"
    riskfolio_req = app_root / "research/quant_stack/requirements-riskfolio.txt"
    qlib_req = app_root / "research/quant_stack/requirements-qlib.txt"

    for required in (spec_path, pypfopt_req, riskfolio_req, qlib_req):
        if not required.exists():
            raise FileNotFoundError(required)

    Phase.set("LOCATE DRIVE DATA")
    if not cfg.drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {cfg.drive_root}")

    model_root = find_model_root(cfg.drive_root)
    if model_root is None:
        raise FileNotFoundError(
            "Market_Model_V2 not found within Drive search depth 5"
        )

    market_root = find_named_v2_root(
        cfg.drive_root,
        model_root,
        "Market_Data",
    )
    feature_root = find_named_v2_root(
        cfg.drive_root,
        model_root,
        "Market_Features",
    )
    raw_parquet, feature_parquet = find_historical_sources(
        market_root,
        feature_root,
    )

    matrix_dir = model_root / "historical_matrices_v1"
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = model_root / "historical_quant_2017_v1" / run_tag
    kalman_venv = Path("/content/.venv-kalman-historical-v1")
    risk_venv = Path("/content/.venv-riskfolio-historical-v1")

    print("REPO_ROOT       :", repo_root)
    print("APP_ROOT        :", app_root)
    print("MODEL_ROOT      :", model_root)
    print("HIST_RAW        :", raw_parquet)
    print("HIST_FEATURES   :", feature_parquet)
    print("HIST_MATRIX_DIR :", matrix_dir)
    print("OUTPUT_DIR      :", output_dir)

    Phase.set("ISOLATED KALMAN ENV")
    create_venv(kalman_venv, recreate=cfg.recreate_venvs)
    kpy = kalman_venv / "bin/python"
    kpip = kalman_venv / "bin/pip"

    run(
        [
            kpip,
            "install",
            "-q",
            "pandas",
            "numpy",
            "scikit-learn",
            "pyarrow",
            "python-dotenv",
        ]
    )
    capture(
        [
            kpy,
            "-c",
            (
                "import numpy,pandas,sklearn,pyarrow;"
                "print('BASE_ENV_OK', numpy.__version__, pandas.__version__, "
                "sklearn.__version__, pyarrow.__version__)"
            ),
        ]
    )

    spec_payload = json.loads(spec_path.read_text(encoding="utf-8"))

    Phase.set("HISTORICAL MATRIX BUILD")
    build_historical_matrices(
        kpy=kpy,
        app_root=app_root,
        raw_parquet=raw_parquet,
        feature_parquet=feature_parquet,
        matrix_dir=matrix_dir,
        spec_path=spec_path,
        start_date=cfg.start_date,
    )

    Phase.set("2017 COVERAGE PRECHECK")
    coverage = coverage_report(kpy, matrix_dir)
    print_coverage(coverage, spec_payload, cfg)
    errors = validate_coverage(
        coverage,
        start_date=cfg.start_date,
        spec=spec_payload,
        train_obs=cfg.train_obs,
        valid_obs=cfg.valid_obs,
        test_obs=cfg.test_obs,
    )
    if errors:
        print("\n2017 precheck failures:")
        for error in errors:
            print(" -", error)
        raise PrecheckBlocked(
            "HISTORICAL_MATRIX_COVERAGE_INSUFFICIENT: "
            + " | ".join(errors)
        )

    Phase.set("PORTFOLIO / MODEL DEPENDENCIES")
    run([kpip, "install", "-q", "-r", pypfopt_req])
    if cfg.enable_qlib_recorder:
        run([kpip, "install", "-q", "-r", qlib_req])
    capture(
        [
            kpy,
            "-c",
            (
                "import scipy,pypfopt;"
                "print('PORTFOLIO_ENV_OK', scipy.__version__)"
            ),
        ]
    )

    Phase.set("HISTORICAL WALK-FORWARD + HRP")
    output_dir.mkdir(parents=True, exist_ok=False)
    head = capture(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"])

    runner_args: list[str | Path] = [
        kpy,
        "-m",
        "research.quant_stack.experiment_runner",
        "--matrix-dir",
        matrix_dir,
        "--spec",
        spec_path,
        "--output-dir",
        output_dir,
        "--start-date",
        cfg.start_date,
        "--train",
        str(cfg.train_obs),
        "--valid",
        str(cfg.valid_obs),
        "--test",
        str(cfg.test_obs),
        "--max-hold-bars",
        str(cfg.max_hold_bars),
        "--git-sha",
        head,
        "--portfolio-targets",
        "--portfolio-method",
        cfg.portfolio_method,
        "--portfolio-lookback-days",
        str(cfg.portfolio_lookback),
        "--portfolio-min-observations",
        str(cfg.portfolio_min_obs),
        "--portfolio-rebalance",
        cfg.portfolio_rebalance,
    ]

    if cfg.enable_qlib_recorder:
        runner_args.extend(
            [
                "--qlib-recorder",
                "--qlib-tracking-root",
                model_root / "qlib_mlruns_historical_v1",
                "--qlib-provider-root",
                "/content/qlib_provider_historical_v1",
                "--qlib-experiment-name",
                "kalman_historical_2017_v1",
            ]
        )

    run(runner_args, cwd=app_root)

    Phase.set("ARTIFACT VALIDATION")
    run(
        [
            kpy,
            "-m",
            "research.quant_stack.validate_artifacts",
            "--output-dir",
            output_dir,
        ],
        cwd=app_root,
    )

    Phase.set("LEAN SHADOW EXECUTION")
    run(
        [
            kpy,
            "-m",
            "research.quant_stack.lean_execution_runner",
            "--output-dir",
            output_dir,
            "--max-symbol-weight",
            "0.75",
            "--max-gross-weight",
            "1.0",
            "--min-order-notional",
            "10",
            "--max-single-order-fraction",
            "0.80",
            "--max-total-turnover-fraction",
            "2.0",
        ],
        cwd=app_root,
    )

    if cfg.run_riskfolio:
        Phase.set("ISOLATED RISKFOLIO")
        create_venv(risk_venv, recreate=cfg.recreate_venvs)
        risk_py = risk_venv / "bin/python"
        risk_pip = risk_venv / "bin/pip"
        run([risk_pip, "install", "-q", "-r", riskfolio_req])

        env = os.environ.copy()
        env["PYTHONPATH"] = str(app_root)
        run(
            [
                risk_py,
                "-m",
                "research.quant_stack.riskfolio_benchmark_runner",
                "--output-dir",
                output_dir,
                "--lookback-days",
                str(cfg.portfolio_lookback),
                "--min-observations",
                str(cfg.portfolio_min_obs),
                "--rebalance",
                cfg.portfolio_rebalance,
            ],
            cwd=app_root,
            env=env,
        )

    Phase.set("FINAL SUMMARY")
    final_summary(kpy, output_dir)

    print("\n" + "=" * 88)
    print("COMPLETE")
    print("=" * 88)
    print("OUTPUT :", output_dir)
    print("RUN TAG:", run_tag)
    print("SAFETY : LIVE=False / Toss=False / Neon write=False")
    write_diagnostic_status(
        "COMPLETE",
        output_dir=str(output_dir),
        matrix_dir=str(matrix_dir),
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PrecheckBlocked as exc:
        write_diagnostic_status(
            "BLOCKED_DATA",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print("\n" + "=" * 88)
        print("KALMAN STATUS: BLOCKED_DATA")
        print("=" * 88)
        print("PHASE       :", Phase.current)
        print("REASON      :", str(exc))
        raise SystemExit(0)
    except Exception as exc:
        write_diagnostic_status(
            "FAIL",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        print("\n" + "!" * 88)
        print("KALMAN COLAB RUNNER FAILED")
        print("!" * 88)
        print("FAILED PHASE:", Phase.current)
        print("ERROR TYPE  :", type(exc).__name__)
        print("ERROR       :", str(exc))
        traceback.print_exc()
        raise
