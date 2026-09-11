from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pandas as pd
from dotenv import load_dotenv


CANONICAL_COLUMNS = [
    "date", "ticker", "asset_type", "quant_rating", "value", "growth",
    "profitability", "momentum", "eps_revision", "expenses", "dividends",
    "risk", "liquidity", "sa_analyst_rating", "wall_street_rating",
    "news_sentiment",
]

COLUMN_ALIASES = {
    "date": ["date", "as_of_date", "asof_date", "as_of", "timestamp", "updated_at"],
    "ticker": ["ticker", "symbol", "security", "security_symbol"],
    "asset_type": ["asset_type", "type", "instrument_type", "security_type"],
    "quant_rating": ["quant_rating", "quant", "quant_score", "sa_quant_rating"],
    "value": ["value", "valuation", "value_grade"],
    "growth": ["growth", "growth_grade"],
    "profitability": ["profitability", "profitability_grade"],
    "momentum": ["momentum", "momentum_grade"],
    "eps_revision": ["eps_revision", "eps_revisions", "revision", "revisions", "eps_revision_grade"],
    "expenses": ["expenses", "expense", "expense_grade"],
    "dividends": ["dividends", "dividend", "dividend_grade"],
    "risk": ["risk", "risk_grade"],
    "liquidity": ["liquidity", "liquidity_grade"],
    "sa_analyst_rating": ["sa_analyst_rating", "analyst_rating", "sa_rating"],
    "wall_street_rating": ["wall_street_rating", "wall_street", "wallstreet_rating", "ws_rating"],
    "news_sentiment": ["news_sentiment", "sentiment", "news_score"],
}


def as_bool(value: object) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def load_env() -> None:
    env_file = Path(os.environ.get("KALMAN_ENV_FILE", "/opt/kalman/.env")).expanduser()
    if env_file.exists():
        load_dotenv(env_file, override=True)


@dataclass(frozen=True)
class Settings:
    mode: str
    output_csv: Path
    drop_csv: Path
    archive_dir: Path
    state_file: Path
    feed_url: str
    feed_token: str
    auth_header: str
    auth_scheme: str
    feed_format: str
    json_path: str
    timeout_seconds: float
    max_retries: int
    required: bool
    field_map_json: str

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> "Settings":
        data_root = Path(os.environ.get("KALMAN_DATA_ROOT", "/opt/kalman/data")).expanduser()
        output_csv = Path(
            args.output_csv
            or os.environ.get(
                "KALMAN_SA_INPUT_CSV",
                str(data_root / "SeekingAlpha" / "seeking_alpha_daily.csv"),
            )
        ).expanduser()
        return cls(
            mode=(args.mode or os.environ.get("KALMAN_SA_COLLECTOR_MODE", "disabled")).strip().lower(),
            output_csv=output_csv,
            drop_csv=Path(
                args.drop_csv
                or os.environ.get(
                    "KALMAN_SA_DROP_CSV",
                    str(data_root / "SeekingAlpha" / "incoming" / "seeking_alpha_latest.csv"),
                )
            ).expanduser(),
            archive_dir=Path(
                args.archive_dir
                or os.environ.get(
                    "KALMAN_SA_ARCHIVE_DIR",
                    str(data_root / "SeekingAlpha" / "archive"),
                )
            ).expanduser(),
            state_file=Path(
                args.state_file
                or os.environ.get(
                    "KALMAN_SA_COLLECTOR_STATE",
                    "/opt/kalman/state/sa_collector.json",
                )
            ).expanduser(),
            feed_url=(args.feed_url or os.environ.get("KALMAN_SA_FEED_URL", "")).strip(),
            feed_token=(args.feed_token or os.environ.get("KALMAN_SA_FEED_TOKEN", "")).strip(),
            auth_header=(args.auth_header or os.environ.get("KALMAN_SA_FEED_AUTH_HEADER", "Authorization")).strip(),
            auth_scheme=(args.auth_scheme or os.environ.get("KALMAN_SA_FEED_AUTH_SCHEME", "Bearer")).strip(),
            feed_format=(args.feed_format or os.environ.get("KALMAN_SA_FEED_FORMAT", "auto")).strip().lower(),
            json_path=(args.json_path or os.environ.get("KALMAN_SA_FEED_JSON_PATH", "")).strip(),
            timeout_seconds=float(
                args.timeout_seconds
                if args.timeout_seconds is not None
                else os.environ.get("KALMAN_SA_FEED_TIMEOUT_SECONDS", "30")
            ),
            max_retries=int(
                args.max_retries
                if args.max_retries is not None
                else os.environ.get("KALMAN_SA_FEED_MAX_RETRIES", "3")
            ),
            required=(
                args.required
                if args.required is not None
                else as_bool(os.environ.get("KALMAN_SA_REQUIRED", "false"))
            ),
            field_map_json=(args.field_map_json or os.environ.get("KALMAN_SA_FIELD_MAP_JSON", "")).strip(),
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Collect licensed/authorized Seeking Alpha data into canonical CSV"
    )
    p.add_argument("--mode", choices=["disabled", "drop_csv", "licensed_http"])
    p.add_argument("--output-csv")
    p.add_argument("--drop-csv")
    p.add_argument("--archive-dir")
    p.add_argument("--state-file")
    p.add_argument("--feed-url")
    p.add_argument("--feed-token")
    p.add_argument("--auth-header")
    p.add_argument("--auth-scheme")
    p.add_argument("--feed-format", choices=["auto", "json", "csv"])
    p.add_argument("--json-path")
    p.add_argument("--timeout-seconds", type=float)
    p.add_argument("--max-retries", type=int)
    p.add_argument("--required", action=argparse.BooleanOptionalAction, default=None)
    p.add_argument("--field-map-json")
    return p.parse_args()


def read_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def atomic_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    df.to_csv(tmp, index=False, encoding="utf-8-sig")
    os.replace(tmp, path)


def extract_json_path(payload: Any, path: str) -> Any:
    if not path:
        if isinstance(payload, dict):
            for key in ("data", "results", "rows", "items"):
                if key in payload and isinstance(payload[key], list):
                    return payload[key]
        return payload

    current = payload
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise KeyError(f"JSON path not found: {path}")
    return current


def fetch_licensed_http(
    settings: Settings,
    state: dict[str, Any],
) -> tuple[bytes, str, dict[str, Any]]:
    if not settings.feed_url:
        raise RuntimeError("KALMAN_SA_FEED_URL is required for licensed_http mode")

    headers = {"Accept": "application/json, text/csv;q=0.9, */*;q=0.8"}
    if settings.feed_token:
        value = settings.feed_token
        if settings.auth_scheme:
            value = f"{settings.auth_scheme} {value}"
        headers[settings.auth_header] = value

    if state.get("etag"):
        headers["If-None-Match"] = str(state["etag"])
    if state.get("last_modified"):
        headers["If-Modified-Since"] = str(state["last_modified"])

    last_exc: Exception | None = None
    for attempt in range(1, settings.max_retries + 1):
        try:
            with httpx.Client(
                timeout=settings.timeout_seconds,
                follow_redirects=True,
                headers=headers,
            ) as client:
                response = client.get(settings.feed_url)

            if response.status_code == 304:
                return b"", "not_modified", {
                    "status_code": 304,
                    "etag": state.get("etag"),
                    "last_modified": state.get("last_modified"),
                }

            response.raise_for_status()
            content_type = response.headers.get("content-type", "").lower()
            fmt = settings.feed_format
            if fmt == "auto":
                fmt = "json" if "json" in content_type else "csv"

            return response.content, fmt, {
                "status_code": response.status_code,
                "etag": response.headers.get("etag"),
                "last_modified": response.headers.get("last-modified"),
                "content_type": content_type,
            }
        except Exception as exc:
            last_exc = exc
            if attempt == settings.max_retries:
                break
            time.sleep(min(2 ** attempt, 10))

    raise RuntimeError(
        f"licensed_http fetch failed after {settings.max_retries} attempts: {last_exc}"
    ) from last_exc


def load_drop_csv(path: Path) -> tuple[bytes, str, dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"drop CSV missing: {path}")
    data = path.read_bytes()
    return data, "csv", {
        "source_path": str(path),
        "mtime": path.stat().st_mtime,
    }


def frame_from_bytes(raw: bytes, fmt: str, json_path: str) -> pd.DataFrame:
    if fmt == "csv":
        return pd.read_csv(io.BytesIO(raw))

    if fmt == "json":
        payload = json.loads(raw.decode("utf-8"))
        rows = extract_json_path(payload, json_path)
        if isinstance(rows, dict):
            rows = [rows]
        if not isinstance(rows, list):
            raise ValueError("licensed JSON feed must resolve to a list of records")
        return pd.DataFrame(rows)

    raise ValueError(f"unsupported feed format: {fmt}")


def parse_explicit_map(text: str) -> dict[str, str]:
    if not text:
        return {}
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("KALMAN_SA_FIELD_MAP_JSON must be a JSON object")
    return {str(k): str(v) for k, v in parsed.items()}


def normalize_columns(
    df: pd.DataFrame,
    explicit_map: dict[str, str],
) -> pd.DataFrame:
    x = df.copy()
    x.columns = [str(c).strip().lower() for c in x.columns]

    for source, canonical in explicit_map.items():
        src = source.strip().lower()
        dst = canonical.strip().lower()
        if src in x.columns and dst not in x.columns:
            x = x.rename(columns={src: dst})

    rename: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        if canonical in x.columns:
            continue
        for alias in aliases:
            if alias in x.columns:
                rename[alias] = canonical
                break
    if rename:
        x = x.rename(columns=rename)

    missing = {"date", "ticker"} - set(x.columns)
    if missing:
        raise ValueError(
            f"collector input missing required columns after mapping: {sorted(missing)}"
        )

    x["date"] = (
        pd.to_datetime(x["date"], errors="coerce", utc=True)
        .dt.tz_convert(None)
        .dt.normalize()
    )
    x = x.dropna(subset=["date"])
    x["ticker"] = x["ticker"].astype(str).str.upper().str.strip()
    x = x[x["ticker"].ne("")]

    if "asset_type" not in x.columns:
        x["asset_type"] = np.where(
            x["ticker"].isin(["IBIT", "FBTC"]), "ETF", "STOCK"
        )
    else:
        x["asset_type"] = x["asset_type"].astype(str).str.upper().str.strip()
        x.loc[~x["asset_type"].isin(["ETF", "STOCK"]), "asset_type"] = ""

    for col in CANONICAL_COLUMNS:
        if col not in x.columns:
            x[col] = np.nan

    x = x[CANONICAL_COLUMNS].copy()
    return (
        x.sort_values(["date", "ticker"])
        .drop_duplicates(["date", "ticker"], keep="last")
    )


def validate_frame(df: pd.DataFrame) -> None:
    if df.empty:
        raise ValueError("collector produced an empty dataset")
    if df["date"].isna().any():
        raise ValueError("collector output contains invalid dates")
    if df["ticker"].isna().any() or df["ticker"].eq("").any():
        raise ValueError("collector output contains invalid tickers")

    latest = pd.Timestamp(df["date"].max()).normalize()
    today = pd.Timestamp.utcnow().tz_localize(None).normalize()
    if latest > today + pd.Timedelta(days=1):
        raise ValueError(f"collector latest date is in the future: {latest.date()}")


def merge_history(existing_path: Path, fresh: pd.DataFrame) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if existing_path.exists():
        old = pd.read_csv(existing_path)
        if not old.empty:
            old.columns = [str(c).strip().lower() for c in old.columns]
            for col in CANONICAL_COLUMNS:
                if col not in old.columns:
                    old[col] = np.nan
            old = old[CANONICAL_COLUMNS]
            old["date"] = pd.to_datetime(old["date"], errors="coerce")
            old["ticker"] = old["ticker"].astype(str).str.upper().str.strip()
            frames.append(old)

    frames.append(fresh)
    merged = pd.concat(frames, ignore_index=True)
    merged = merged.dropna(subset=["date"])
    merged["date"] = pd.to_datetime(merged["date"]).dt.normalize()
    merged["ticker"] = merged["ticker"].astype(str).str.upper().str.strip()
    merged = merged.sort_values(["date", "ticker"]).drop_duplicates(
        ["date", "ticker"], keep="last"
    )
    return merged[CANONICAL_COLUMNS].reset_index(drop=True)


def archive_raw(
    settings: Settings,
    raw: bytes,
    fmt: str,
    digest: str,
) -> Path | None:
    if not raw:
        return None
    settings.archive_dir.mkdir(parents=True, exist_ok=True)
    ext = "json" if fmt == "json" else "csv"
    stamp = pd.Timestamp.now(tz="UTC").strftime("%Y%m%dT%H%M%SZ")
    path = settings.archive_dir / f"sa_raw_{stamp}_{digest[:12]}.{ext}"
    if not path.exists():
        path.write_bytes(raw)
    return path


def main() -> None:
    load_env()
    settings = Settings.from_args(parse_args())
    state = read_state(settings.state_file)

    print(f"[SA-COLLECT] mode={settings.mode} output={settings.output_csv}")

    if settings.mode == "disabled":
        status = {
            "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "mode": "disabled",
            "output_csv": str(settings.output_csv),
            "output_exists": settings.output_csv.exists(),
        }
        atomic_text(
            settings.state_file,
            json.dumps(status, indent=2, ensure_ascii=False),
        )
        if settings.required and not settings.output_csv.exists():
            raise RuntimeError(
                "SA collector is disabled but KALMAN_SA_REQUIRED=true "
                "and no canonical CSV exists"
            )
        print("[SA-COLLECT] disabled")
        return

    if settings.mode == "drop_csv":
        raw, fmt, meta = load_drop_csv(settings.drop_csv)
    elif settings.mode == "licensed_http":
        raw, fmt, meta = fetch_licensed_http(settings, state)
        if fmt == "not_modified":
            state.update({
                "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
                "mode": settings.mode,
                "result": "not_modified",
                **meta,
            })
            atomic_text(
                settings.state_file,
                json.dumps(state, indent=2, ensure_ascii=False),
            )
            print("[SA-COLLECT] not modified")
            return
    else:
        raise ValueError(f"unsupported collector mode: {settings.mode}")

    digest = hashlib.sha256(raw).hexdigest()
    if state.get("source_sha256") == digest and settings.output_csv.exists():
        state.update({
            "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
            "mode": settings.mode,
            "result": "unchanged",
            **meta,
        })
        atomic_text(
            settings.state_file,
            json.dumps(state, indent=2, ensure_ascii=False),
        )
        print("[SA-COLLECT] source unchanged")
        return

    fresh = frame_from_bytes(raw, fmt, settings.json_path)
    fresh = normalize_columns(
        fresh,
        parse_explicit_map(settings.field_map_json),
    )
    validate_frame(fresh)

    merged = merge_history(settings.output_csv, fresh)
    validate_frame(merged)

    archive_path = archive_raw(settings, raw, fmt, digest)
    atomic_csv(merged, settings.output_csv)

    state = {
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "mode": settings.mode,
        "result": "updated",
        "source_sha256": digest,
        "source_format": fmt,
        "fresh_rows": int(len(fresh)),
        "merged_rows": int(len(merged)),
        "fresh_tickers": int(fresh["ticker"].nunique()),
        "latest_date": pd.Timestamp(merged["date"].max()).date().isoformat(),
        "output_csv": str(settings.output_csv),
        "archive_path": str(archive_path) if archive_path else None,
        **meta,
    }
    atomic_text(
        settings.state_file,
        json.dumps(state, indent=2, ensure_ascii=False),
    )
    print(
        f"[SA-COLLECT] updated rows={len(merged)} "
        f"fresh={len(fresh)} latest={state['latest_date']}"
    )


if __name__ == "__main__":
    main()
