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
    universe_path: Path

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Settings":
        data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
        default_universe = (
            Path(__file__).resolve().parents[2] / "config" / "market-data-v2-universe.json"
        )
        return cls(
            output_dir=Path(
                args.output_dir
                or os.environ.get(
                    "KALMAN_MARKET_V2_OUTPUT_DIR",
                    str(data_root / "Market_Data" / "v2"),
                )
            ).expanduser(),
            start_date=args.start_date
            or os.environ.get("KALMAN_MARKET_V2_START_DATE", "2024-01-01"),
            end_date=args.end_date
            or os.environ.get("KALMAN_MARKET_V2_END_DATE")
            or None,
            universe_path=Path(
                args.universe
                or os.environ.get("KALMAN_MARKET_V2_UNIVERSE", str(default_universe))
            ).expanduser(),
        )


@dataclass(frozen=True)
class FetchSpec:
    key: str
    group: str
    provider: MarketDataProvider
    request: ProviderRequest
    required: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build Market Data V2 shadow snapshots")
    parser.add_argument("--start-date")
    parser.add_argument("--end-date")
    parser.add_argument("--output-dir")
    parser.add_argument("--universe")
    return parser.parse_args()


def load_server_env() -> None:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)


def load_universe(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Market V2 universe file missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("assets"), list):
        raise ValueError("Market V2 universe must contain an assets list")
    return payload


def build_specs(settings: Settings, universe: dict[str, Any]) -> list[FetchSpec]:
    providers: dict[str, MarketDataProvider] = {
        "yfinance": YFinanceProvider(),
        "fdr": FinanceDataReaderProvider(),
        "pykrx": PyKrxProvider(),
    }
    specs: list[FetchSpec] = []
    seen_keys: set[str] = set()

    for item in universe["assets"]:
        if not isinstance(item, dict):
            raise ValueError("every universe asset must be an object")
        key = str(item["key"])
        if key in seen_keys:
            raise ValueError(f"duplicate universe key: {key}")
        seen_keys.add(key)

        provider_name = str(item["provider"]).lower()
        if provider_name not in providers:
            raise ValueError(f"unknown provider {provider_name!r} for {key}")

        request = ProviderRequest(
            symbol=str(item["symbol"]),
            provider_symbol=str(item.get("provider_symbol") or item["symbol"]),
            market=str(item.get("market") or "UNKNOWN"),
            currency=str(item.get("currency") or ""),
            kind=str(item.get("kind") or "equity"),
            start=settings.start_date,
            end=settings.end_date,
            interval=str(item.get("interval") or "1d"),
            adjusted=bool(item.get("adjusted", False)),
            extra={"group": str(item.get("group") or "UNGROUPED")},
        )
        specs.append(
            FetchSpec(
                key=key,
                group=str(item.get("group") or "UNGROUPED").upper(),
                provider=providers[provider_name],
                request=request,
                required=bool(item.get("required", False)),
            )
        )
    return specs


def _safe_provider_dir(name: str) -> str:
    return "".join(c.lower() if c.isalnum() else "_" for c in name).strip("_")


def build(settings: Settings) -> tuple[dict[str, Any], int]:
    universe = load_universe(settings.universe_path)
    specs = build_specs(settings, universe)

    settings.output_dir.mkdir(parents=True, exist_ok=True)
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, dict[str, Any]] = {}

    for spec in specs:
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
                    "universe_version": universe.get("version"),
                    "fetch_key": spec.key,
                    "group": spec.group,
                    "required": spec.required,
                },
            )
            frames[spec.key] = result.data
            sources[spec.key] = {
                "status": result.metadata.get("status", "READY"),
                "group": spec.group,
                "required": spec.required,
                "manifest": manifest,
            }
        except Exception as exc:
            sources[spec.key] = {
                "status": "FAIL",
                "group": spec.group,
                "required": spec.required,
                "error_type": type(exc).__name__,
                "error": str(exc),
            }

    comparisons: dict[str, dict[str, Any]] = {}
    for comparison in universe.get("comparisons", []):
        name = str(comparison["name"])
        primary_key = str(comparison["primary"])
        secondary_key = str(comparison["secondary"])
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
        key
        for key, item in sources.items()
        if item.get("required") and item.get("status") != "READY"
    ]
    optional_issues = [
        key
        for key, item in sources.items()
        if not item.get("required") and item.get("status") != "READY"
    ]
    comparison_failures = [
        key for key, item in comparisons.items() if item.get("status") == "FAIL"
    ]

    group_summary: dict[str, dict[str, int]] = {}
    for item in sources.values():
        group = str(item.get("group") or "UNGROUPED")
        bucket = group_summary.setdefault(group, {"ready": 0, "issue": 0})
        if item.get("status") == "READY":
            bucket["ready"] += 1
        else:
            bucket["issue"] += 1

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
        "universe_path": str(settings.universe_path),
        "universe_version": universe.get("version"),
        "asset_count": len(specs),
        "group_summary": group_summary,
        "required_failures": required_failures,
        "optional_issues": optional_issues,
        "comparison_failures": comparison_failures,
        "sources": sources,
        "comparisons": comparisons,
    }

    atomic_json(
        settings.output_dir / "validation" / "provider_comparison.json",
        {
            "built_at": run_status["built_at"],
            "universe_version": universe.get("version"),
            "comparisons": comparisons,
        },
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
