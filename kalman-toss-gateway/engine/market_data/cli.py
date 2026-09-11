from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
from dotenv import load_dotenv

from .base import MarketDataProvider, ProviderRequest
from .fdr_provider import FinanceDataReaderProvider
from .pykrx_provider import PyKrxProvider
from .snapshot import atomic_json, write_snapshot
from .validation import compare_close
from .yfinance_provider import YFinanceProvider


@dataclass(frozen=True)
class Settings:
    output_dir: Path
    start_date: str
    end_date: str | None

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Settings":
        data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
        output = Path(
            args.output_dir
            or os.environ.get(
                "KALMAN_MARKET_V2_OUTPUT_DIR",
                str(data_root / "Market_Data" / "v2"),
            )
        ).expanduser()
        return cls(
            output_dir=output,
            start_date=args.start_date
            or os.environ.get("KALMAN_MARKET_V2_START_DATE", "2024-01-01"),
            end_date=args.end_date
            or os.environ.get("KALMAN_MARKET_V2_END_DATE")
            or None,
        )


@dataclass(frozen=True)
class FetchSpec:
    key: str
    provider: MarketDataProvider
    request: ProviderRequest
    required: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Market Data V2 shadow snapshots")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output-dir")
    return parser.parse_args()


def load_server_env() -> None:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)


def fetch_specs(settings: Settings) -> list[FetchSpec]:
    yf = YFinanceProvider()
    fdr = FinanceDataReaderProvider()
    krx = PyKrxProvider()
    common = {"start": settings.start_date, "end": settings.end_date}

    return [
        FetchSpec(
            "yf_spy",
            yf,
            ProviderRequest(
                symbol="SPY", provider_symbol="SPY", market="US", currency="USD",
                kind="etf", **common,
            ),
            required=True,
        ),
        FetchSpec(
            "yf_btc",
            yf,
            ProviderRequest(
                symbol="BTC-USD", provider_symbol="BTC-USD", market="CRYPTO",
                currency="USD", kind="crypto", **common,
            ),
            required=True,
        ),
        FetchSpec(
            "yf_usdkrw",
            yf,
            ProviderRequest(
                symbol="USD/KRW", provider_symbol="KRW=X", market="FX",
                currency="KRW", kind="fx", **common,
            ),
        ),
        FetchSpec(
            "yf_kospi",
            yf,
            ProviderRequest(
                symbol="KOSPI", provider_symbol="^KS11", market="KR",
                currency="KRW", kind="index", **common,
            ),
        ),
        FetchSpec(
            "fdr_btc",
            fdr,
            ProviderRequest(
                symbol="BTC-USD", provider_symbol="BTC/USD", market="CRYPTO",
                currency="USD", kind="crypto", **common,
            ),
        ),
        FetchSpec(
            "fdr_usdkrw",
            fdr,
            ProviderRequest(
                symbol="USD/KRW", provider_symbol="USD/KRW", market="FX",
                currency="KRW", kind="fx", **common,
            ),
        ),
        FetchSpec(
            "fdr_kospi",
            fdr,
            ProviderRequest(
                symbol="KOSPI", provider_symbol="KS11", market="KR",
                currency="KRW", kind="index", **common,
            ),
        ),
        FetchSpec(
            "pykrx_kospi",
            krx,
            ProviderRequest(
                symbol="KOSPI", provider_symbol="1001", market="KR",
                currency="KRW", kind="index", **common,
            ),
        ),
    ]


def _safe_provider_dir(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")


def build(settings: Settings) -> tuple[dict[str, Any], int]:
    settings.output_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, dict[str, Any]] = {}

    for spec in fetch_specs(settings):
        try:
            result = spec.provider.fetch(spec.request)
            snapshot_path = (
                settings.output_dir
                / "raw"
                / _safe_provider_dir(spec.provider.name)
                / f"{spec.key}.parquet"
            )
            manifest = write_snapshot(
                result.data,
                snapshot_path,
                metadata={
                    **result.metadata,
                    "dataset_layer": "market_data_v2_shadow",
                    "fetch_key": spec.key,
                    "required": spec.required,
                },
            )
            frames[spec.key] = result.data
            sources[spec.key] = {
                "status": result.metadata.get("status", "READY"),
                "required": spec.required,
                "manifest": manifest,
            }
        except Exception as exc:
            sources[spec.key] = {
                "status": "FAIL",
                "required": spec.required,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    comparisons: dict[str, dict[str, Any]] = {}
    for name, primary_key, secondary_key in [
        ("btc_yf_vs_fdr", "yf_btc", "fdr_btc"),
        ("usdkrw_yf_vs_fdr", "yf_usdkrw", "fdr_usdkrw"),
        ("kospi_yf_vs_fdr", "yf_kospi", "fdr_kospi"),
        ("kospi_pykrx_vs_fdr", "pykrx_kospi", "fdr_kospi"),
    ]:
        if primary_key not in frames or secondary_key not in frames:
            comparisons[name] = {
                "status": "SKIPPED",
                "reason": "one_or_more_sources_unavailable",
                "primary_key": primary_key,
                "secondary_key": secondary_key,
            }
            continue
        comparisons[name] = compare_close(
            frames[primary_key],
            frames[secondary_key],
            primary_name=primary_key,
            secondary_name=secondary_key,
        )

    required_failures = [
        key for key, item in sources.items()
        if item.get("required") and item.get("status") != "READY"
    ]
    optional_issues = [
        key for key, item in sources.items()
        if not item.get("required") and item.get("status") != "READY"
    ]
    comparison_failures = [
        key for key, item in comparisons.items()
        if item.get("status") == "FAIL"
    ]

    if required_failures:
        overall, exit_code = "FAIL", 2
    elif optional_issues or comparison_failures:
        overall, exit_code = "DEGRADED", 0
    else:
        overall, exit_code = "READY", 0

    run_status = {
        "status": overall,
        "shadow_only": True,
        "production_writes": False,
        "built_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "start_date": settings.start_date,
        "end_date": settings.end_date,
        "output_dir": str(settings.output_dir),
        "required_failures": required_failures,
        "optional_issues": optional_issues,
        "comparison_failures": comparison_failures,
        "sources": sources,
        "comparisons": comparisons,
    }

    atomic_json(
        settings.output_dir / "validation" / "provider_comparison.json",
        {"built_at": run_status["built_at"], "comparisons": comparisons},
    )
    atomic_json(settings.output_dir / "market_data_v2_run_status.json", run_status)
    return run_status, exit_code


def main() -> int:
    load_server_env()
    settings = Settings.from_args(parse_args())
    status, exit_code = build(settings)
    print(json.dumps(status, ensure_ascii=False, indent=2, default=str))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
