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
    force_rebuild_matrices: bool = False
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
        print("\n" + "=" * 88)
        print(f"PHASE: {value}")
        print("=" * 88)


def run(cmd: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> None:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    subprocess.run(args, check=True, cwd=cwd, env=env)


def capture(cmd: list[str | Path], *, cwd: Path | None = None, env: dict[str, str] | None = None) -> str:
    args = [str(x) for x in cmd]
    print("\n$", " ".join(args))
    return subprocess.check_output(
        args,
        cwd=cwd,
        env=env,
        text=True,
        stderr=subprocess.STDOUT,
    ).strip()


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


def find_named_v2_root(drive_root: Path, model_root: Path, name: str) -> Path | None:
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


def matrix_artifacts_complete(matrix_dir: Path) -> bool:
    required: list[Path] = []
    for market in ("us", "kr", "btc"):
        required.extend(
            [
                matrix_dir / f"{market}_matrix.parquet",
                matrix_dir / f"{market}_matrix_manifest.json",
            ]
        )
    return all(path.exists() for path in required)


def remap_server_path(
    raw_path: str,
    *,
    drive_root: Path,
    model_root: Path,
    market_root: Path | None,
    feature_root: Path | None,
) -> str:
    raw = str(raw_path)
    original = Path(raw)
    if original.exists():
        return raw

    candidates: list[Path] = []
    if raw.startswith("/mnt/gdrive/"):
        suffix = raw[len("/mnt/gdrive/") :]
        candidates.append(drive_root / suffix)

    if "Market_Data/" in raw and market_root is not None:
        suffix = raw.split("Market_Data/", 1)[1]
        candidates.append(market_root.parent / suffix)

    if "Market_Features/" in raw and feature_root is not None:
        suffix = raw.split("Market_Features/", 1)[1]
        candidates.append(feature_root.parent / suffix)

    if "Market_Model_V2/" in raw:
        suffix = raw.split("Market_Model_V2/", 1)[1]
        candidates.append(model_root / suffix)

    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return raw


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
                f"{market}: earliest labeled year={str(min_labeled)[:4]} > requested={start_year}"
            )

    return errors


def build_matrices(
    *,
    kpy: Path,
    app_root: Path,
    market_root: Path | None,
    feature_root: Path | None,
    matrix_dir: Path,
    universe: Path,
    spec: Path,
) -> None:
    if market_root is None or not market_root.exists():
        raise PrecheckBlocked("Market_Data/v2 not found")
    if feature_root is None or not feature_root.exists():
        raise PrecheckBlocked("Market_Features/v2 not found")

    matrix_dir.mkdir(parents=True, exist_ok=True)
    run(
        [
            kpy,
            "-m",
            "research.model_v2.build_feature_matrix",
            "--market-root",
            market_root,
            "--feature-root",
            feature_root,
            "--universe",
            universe,
            "--spec",
            spec,
            "--output-dir",
            matrix_dir,
        ],
        cwd=app_root,
    )


def prepare_matrix_mirror(
    *,
    matrix_dir: Path,
    mirror_dir: Path,
    drive_root: Path,
    model_root: Path,
    market_root: Path | None,
    feature_root: Path | None,
    spec_payload: dict[str, Any],
) -> list[str]:
    if mirror_dir.exists():
        shutil.rmtree(mirror_dir)
    mirror_dir.mkdir(parents=True)

    unresolved: list[str] = []
    for market in ("us", "kr", "btc"):
        parquet = matrix_dir / f"{market}_matrix.parquet"
        manifest = matrix_dir / f"{market}_matrix_manifest.json"

        if not parquet.exists() or not manifest.exists():
            unresolved.append(f"{market}: missing matrix/manifest")
            continue

        shutil.copy2(parquet, mirror_dir / parquet.name)
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        remapped: dict[str, Any] = {}

        for old_path, meta in payload.get("input_files", {}).items():
            new_path = remap_server_path(
                old_path,
                drive_root=drive_root,
                model_root=model_root,
                market_root=market_root,
                feature_root=feature_root,
            )
            remapped[new_path] = meta

        payload["input_files"] = remapped

        anchor_key = spec_payload["markets"][market.upper()]["anchor_key"]
        anchor_candidates = [
            path
            for path, meta in remapped.items()
            if str(meta.get("kind")) == "raw"
            and str(meta.get("fetch_key")) == anchor_key
        ]
        if not anchor_candidates or not any(Path(path).exists() for path in anchor_candidates):
            unresolved.append(
                f"{market}: anchor={anchor_key}, candidates={anchor_candidates}"
            )

        (mirror_dir / manifest.name).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
            encoding="utf-8",
        )

    return unresolved


def coverage_report(kpy: Path, mirror_dir: Path) -> dict[str, dict[str, Any]]:
    script = """
import json
import sys
from pathlib import Path
import pandas as pd

root = Path(sys.argv[1])
result = {}
for market in ("us", "kr", "btc"):
    frame = pd.read_parquet(root / f"{market}_matrix.parquet", columns=["as_of", "target_label"])
    ts = pd.to_datetime(frame["as_of"], utc=True, errors="coerce")
    labeled_mask = frame["target_label"].notna() & ts.notna()
    labeled_ts = ts.loc[labeled_mask]
    valid_ts = ts.dropna()
    result[market.upper()] = {
        "rows": int(len(frame)),
        "labeled_rows": int(labeled_mask.sum()),
        "min_as_of": None if valid_ts.empty else valid_ts.min().isoformat(),
        "max_as_of": None if valid_ts.empty else valid_ts.max().isoformat(),
        "min_labeled_as_of": None if labeled_ts.empty else labeled_ts.min().isoformat(),
        "max_labeled_as_of": None if labeled_ts.empty else labeled_ts.max().isoformat(),
    }
print(json.dumps(result))
"""
    raw = capture([kpy, "-c", script, mirror_dir])
    return json.loads(raw.splitlines()[-1])


def print_coverage(
    coverage: dict[str, dict[str, Any]],
    spec_payload: dict[str, Any],
    cfg: Config,
) -> None:
    for market in MARKETS:
        info = coverage[market]
        horizon = int(spec_payload["markets"][market]["horizon_observations"])
        required = minimum_labeled_rows(cfg.train_obs, cfg.valid_obs, cfg.test_obs, horizon)
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
    printable["sharpe"] = pd.to_numeric(printable["sharpe"], errors="coerce").round(3)
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
    assert minimum_labeled_rows(504, 63, 126, 14) == 721

    spec = {
        "markets": {
            "US": {"horizon_observations": 5},
            "KR": {"horizon_observations": 5},
            "BTC": {"horizon_observations": 14},
        }
    }
    good = {
        "US": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-03T00:00:00+00:00"},
        "KR": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-03T00:00:00+00:00"},
        "BTC": {"labeled_rows": 1000, "min_labeled_as_of": "2017-01-03T00:00:00+00:00"},
    }
    assert validate_coverage(
        good,
        start_date="2017-01-01",
        spec=spec,
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    ) == []

    bad = dict(good)
    bad["US"] = {"labeled_rows": 100, "min_labeled_as_of": "2026-01-01T00:00:00+00:00"}
    errors = validate_coverage(
        bad,
        start_date="2017-01-01",
        spec=spec,
        train_obs=504,
        valid_obs=63,
        test_obs=126,
    )
    assert any("labeled_rows" in item for item in errors)
    assert any("earliest labeled year" in item for item in errors)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        drive = root / "drive"
        model = drive / "Market_Model_V2"
        market = drive / "Market_Data" / "v2"
        feature = drive / "Market_Features" / "v2"
        (model / "matrices").mkdir(parents=True)
        market.mkdir(parents=True)
        feature.mkdir(parents=True)

        assert find_model_root(drive) == model
        assert find_named_v2_root(drive, model, "Market_Data") == market
        assert find_named_v2_root(drive, model, "Market_Features") == feature

        raw = drive / "Market_Data" / "v2" / "raw.parquet"
        raw.write_text("x", encoding="utf-8")
        mapped = remap_server_path(
            "/mnt/gdrive/Market_Data/v2/raw.parquet",
            drive_root=drive,
            model_root=model,
            market_root=market,
            feature_root=feature,
        )
        assert Path(mapped) == raw

    print("SELF_TEST=PASS")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Kalman historical quant Colab runner")
    parser.add_argument("--drive-root", default="/content/drive/MyDrive")
    parser.add_argument("--start-date", default="2017-01-01")
    parser.add_argument("--force-rebuild-matrices", action="store_true")
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
        force_rebuild_matrices=bool(args.force_rebuild_matrices),
        recreate_venvs=not bool(args.keep_venvs),
        run_riskfolio=not bool(args.disable_riskfolio),
        enable_qlib_recorder=bool(args.enable_qlib_recorder),
    )

    app_root = Path(__file__).resolve().parents[1]
    repo_root = app_root.parent
    spec_path = app_root / "config/model-v2-spec.json"
    universe_path = app_root / "config/market-data-v2-universe.json"
    pypfopt_req = app_root / "research/quant_stack/requirements-pypfopt.txt"
    riskfolio_req = app_root / "research/quant_stack/requirements-riskfolio.txt"
    qlib_req = app_root / "research/quant_stack/requirements-qlib.txt"

    for required in (spec_path, universe_path, pypfopt_req, riskfolio_req, qlib_req):
        if not required.exists():
            raise FileNotFoundError(required)

    Phase.set("LOCATE DRIVE DATA")
    if not cfg.drive_root.exists():
        raise FileNotFoundError(f"Drive root not mounted: {cfg.drive_root}")

    model_root = find_model_root(cfg.drive_root)
    if model_root is None:
        raise FileNotFoundError("Market_Model_V2 not found within Drive search depth 5")

    market_root = find_named_v2_root(cfg.drive_root, model_root, "Market_Data")
    feature_root = find_named_v2_root(cfg.drive_root, model_root, "Market_Features")
    matrix_dir = model_root / "matrices"
    run_tag = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = model_root / "historical_quant_colab_v4" / run_tag
    mirror_dir = Path("/content/kalman_matrix_mirror_v4")
    kalman_venv = Path("/content/.venv-kalman-v4")
    risk_venv = Path("/content/.venv-riskfolio-v4")

    print("REPO_ROOT   :", repo_root)
    print("APP_ROOT    :", app_root)
    print("MODEL_ROOT  :", model_root)
    print("MARKET_ROOT :", market_root)
    print("FEATURE_ROOT:", feature_root)
    print("MATRIX_DIR  :", matrix_dir)
    print("OUTPUT_DIR  :", output_dir)

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
            "-r",
            pypfopt_req,
        ]
    )
    if cfg.enable_qlib_recorder:
        run([kpip, "install", "-q", "-r", qlib_req])

    print(
        capture(
            [
                kpy,
                "-c",
                (
                    "import numpy,pandas,scipy,sklearn,pyarrow,pypfopt;"
                    "print('ENV_OK', numpy.__version__, pandas.__version__, scipy.__version__, sklearn.__version__)"
                ),
            ]
        )
    )

    spec_payload = json.loads(spec_path.read_text(encoding="utf-8"))

    Phase.set("MATRIX PREPARATION")
    rebuilt = False
    if cfg.force_rebuild_matrices or not matrix_artifacts_complete(matrix_dir):
        build_matrices(
            kpy=kpy,
            app_root=app_root,
            market_root=market_root,
            feature_root=feature_root,
            matrix_dir=matrix_dir,
            universe=universe_path,
            spec=spec_path,
        )
        rebuilt = True

    unresolved = prepare_matrix_mirror(
        matrix_dir=matrix_dir,
        mirror_dir=mirror_dir,
        drive_root=cfg.drive_root,
        model_root=model_root,
        market_root=market_root,
        feature_root=feature_root,
        spec_payload=spec_payload,
    )

    if unresolved and not rebuilt:
        print("Unresolved anchor manifests:", unresolved)
        build_matrices(
            kpy=kpy,
            app_root=app_root,
            market_root=market_root,
            feature_root=feature_root,
            matrix_dir=matrix_dir,
            universe=universe_path,
            spec=spec_path,
        )
        rebuilt = True
        unresolved = prepare_matrix_mirror(
            matrix_dir=matrix_dir,
            mirror_dir=mirror_dir,
            drive_root=cfg.drive_root,
            model_root=model_root,
            market_root=market_root,
            feature_root=feature_root,
            spec_payload=spec_payload,
        )

    if unresolved:
        raise PrecheckBlocked(
            "PRECHECK_ANCHOR_OHLC_UNRESOLVED: " + " | ".join(unresolved)
        )

    Phase.set("2017 COVERAGE PRECHECK")
    coverage = coverage_report(kpy, mirror_dir)
    print_coverage(coverage, spec_payload, cfg)
    errors = validate_coverage(
        coverage,
        start_date=cfg.start_date,
        spec=spec_payload,
        train_obs=cfg.train_obs,
        valid_obs=cfg.valid_obs,
        test_obs=cfg.test_obs,
    )

    if errors and not rebuilt:
        print("\nExisting matrices failed 2017 precheck. Rebuilding once...")
        build_matrices(
            kpy=kpy,
            app_root=app_root,
            market_root=market_root,
            feature_root=feature_root,
            matrix_dir=matrix_dir,
            universe=universe_path,
            spec=spec_path,
        )
        rebuilt = True
        unresolved = prepare_matrix_mirror(
            matrix_dir=matrix_dir,
            mirror_dir=mirror_dir,
            drive_root=cfg.drive_root,
            model_root=model_root,
            market_root=market_root,
            feature_root=feature_root,
            spec_payload=spec_payload,
        )
        if unresolved:
            raise PrecheckBlocked(
                "PRECHECK_ANCHOR_OHLC_UNRESOLVED_AFTER_REBUILD: "
                + " | ".join(unresolved)
            )
        coverage = coverage_report(kpy, mirror_dir)
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
            "PRECHECK_2017_HISTORY_INSUFFICIENT: historical data backfill is required before a genuine 2017 walk-forward run."
        )

    Phase.set("HISTORICAL WALK-FORWARD + HRP")
    output_dir.mkdir(parents=True, exist_ok=False)
    head = capture(["git", "-C", repo_root, "rev-parse", "--short", "HEAD"])

    runner_args: list[str | Path] = [
        kpy,
        "-m",
        "research.quant_stack.experiment_runner",
        "--matrix-dir",
        mirror_dir,
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
                model_root / "qlib_mlruns_colab_v4",
                "--qlib-provider-root",
                "/content/qlib_provider_v4",
                "--qlib-experiment-name",
                "kalman_historical_quant_colab_v4",
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
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except PrecheckBlocked as exc:
        print("\n" + "=" * 88)
        print("KALMAN STATUS: BLOCKED_DATA")
        print("=" * 88)
        print("PHASE       :", Phase.current)
        print("REASON      :", str(exc))
        print("ACTION      : historical data backfill is required before running the 2017 test")
        raise SystemExit(0)
    except Exception as exc:
        print("\n" + "!" * 88)
        print("KALMAN COLAB RUNNER FAILED")
        print("!" * 88)
        print("FAILED PHASE:", Phase.current)
        print("ERROR TYPE  :", type(exc).__name__)
        print("ERROR       :", str(exc))
        traceback.print_exc()
        raise
