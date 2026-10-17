from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ALPACA_BARS_URL = "https://data.alpaca.markets/v2/stocks/{symbol}/bars"
BAR_COLUMNS = ["c", "h", "l", "n", "o", "t", "v", "vw"]
PRICE_COLUMNS = ["c", "h", "l", "o", "vw"]
COUNT_COLUMNS = ["n", "v"]


def utc_now() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(timezone.utc))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def credentials() -> tuple[str, str]:
    key = (
        os.environ.get("ALPACA_API_KEY")
        or os.environ.get("APCA_API_KEY_ID")
        or ""
    ).strip()
    secret = (
        os.environ.get("ALPACA_API_SECRET")
        or os.environ.get("APCA_API_SECRET_KEY")
        or ""
    ).strip()
    if not key or not secret:
        raise RuntimeError(
            "Alpaca credentials missing; updater requires existing Kalman "
            "EnvironmentFile injection and never stores credentials itself"
        )
    return key, secret


def request_json(
    url: str,
    *,
    key: str,
    secret: str,
    max_retries: int = 5,
) -> dict[str, Any]:
    headers = {
        "APCA-API-KEY-ID": key,
        "APCA-API-SECRET-KEY": secret,
        "Accept": "application/json",
        "User-Agent": "KalmanQQQ1hUpdater/0.1",
    }
    for attempt in range(max_retries):
        req = urllib.request.Request(url, headers=headers, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=45) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            if exc.code == 429 and attempt + 1 < max_retries:
                retry_after = exc.headers.get("Retry-After")
                delay = float(retry_after) if retry_after else min(30.0, 1.5 ** (attempt + 1))
                time.sleep(delay)
                continue
            if 500 <= exc.code < 600 and attempt + 1 < max_retries:
                time.sleep(min(20.0, 1.5 ** (attempt + 1)))
                continue
            raise RuntimeError(f"Alpaca HTTP {exc.code}: {body[:500]}") from exc
        except urllib.error.URLError as exc:
            if attempt + 1 >= max_retries:
                raise RuntimeError(f"Alpaca request failed: {exc}") from exc
            time.sleep(min(20.0, 1.5 ** (attempt + 1)))
    raise RuntimeError("Alpaca request exhausted retries")


def fetch_1h_iex(
    symbol: str,
    *,
    start_utc: pd.Timestamp,
    end_utc: pd.Timestamp,
    adjustment: str = "raw",
) -> pd.DataFrame:
    key, secret = credentials()
    rows: list[dict[str, Any]] = []
    page_token: str | None = None

    while True:
        query = {
            "timeframe": "1Hour",
            "start": start_utc.isoformat(),
            "end": end_utc.isoformat(),
            "adjustment": adjustment,
            "feed": "iex",
            "limit": "10000",
            "sort": "asc",
        }
        if page_token:
            query["page_token"] = page_token
        url = ALPACA_BARS_URL.format(symbol=urllib.parse.quote(symbol, safe=""))
        payload = request_json(
            url + "?" + urllib.parse.urlencode(query),
            key=key,
            secret=secret,
        )
        rows.extend(payload.get("bars") or [])
        page_token = payload.get("next_page_token")
        if not page_token:
            break

    return normalize_bars(pd.DataFrame(rows))


def normalize_bars(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return pd.DataFrame(columns=BAR_COLUMNS)

    missing = [c for c in BAR_COLUMNS if c not in frame.columns]
    if missing:
        raise ValueError(f"Alpaca bars missing required columns: {missing}")

    out = frame[BAR_COLUMNS].copy()
    out["t"] = pd.to_datetime(out["t"], utc=True, errors="coerce").astype(
        "datetime64[ns, UTC]"
    )
    for c in PRICE_COLUMNS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    for c in COUNT_COLUMNS:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.dropna(subset=BAR_COLUMNS)

    if out.empty:
        return out
    if out["t"].duplicated().any():
        raise ValueError("duplicate timestamps in Alpaca response")
    if not out["t"].is_monotonic_increasing:
        out = out.sort_values("t").reset_index(drop=True)

    if not np.isfinite(out[PRICE_COLUMNS].to_numpy(dtype=float)).all():
        raise ValueError("non-finite price values in Alpaca response")
    if (out[PRICE_COLUMNS] < 0).any().any():
        raise ValueError("negative price values in Alpaca response")
    if (out[COUNT_COLUMNS] < 0).any().any():
        raise ValueError("negative volume/trade-count values in Alpaca response")

    out["n"] = out["n"].astype("int64")
    out["v"] = out["v"].astype("int64")
    return out[BAR_COLUMNS].reset_index(drop=True)


def load_canonical(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"canonical missing: {path}")
    frame = pd.read_parquet(path)
    if list(frame.columns) != BAR_COLUMNS:
        raise ValueError(
            f"canonical schema mismatch expected={BAR_COLUMNS} got={list(frame.columns)}"
        )
    out = normalize_bars(frame)
    if len(out) != len(frame):
        raise ValueError("canonical normalization changed row count")
    return out


def compare_overlap(
    existing: pd.DataFrame,
    fresh: pd.DataFrame,
    *,
    price_atol: float = 1e-9,
) -> dict[str, Any]:
    overlap = existing.merge(
        fresh,
        on="t",
        how="inner",
        suffixes=("_old", "_new"),
        validate="one_to_one",
    )
    if overlap.empty:
        raise RuntimeError("no overlap with canonical; refusing append")

    mismatch: dict[str, int] = {}
    for c in PRICE_COLUMNS:
        ok = np.isclose(
            overlap[f"{c}_old"].to_numpy(dtype=float),
            overlap[f"{c}_new"].to_numpy(dtype=float),
            rtol=0.0,
            atol=price_atol,
            equal_nan=False,
        )
        mismatch[c] = int((~ok).sum())
    for c in COUNT_COLUMNS:
        mismatch[c] = int(
            (
                overlap[f"{c}_old"].astype("int64")
                != overlap[f"{c}_new"].astype("int64")
            ).sum()
        )

    total_mismatch = sum(mismatch.values())
    if total_mismatch:
        raise RuntimeError(
            f"overlap mismatch; likely feed/adjustment/data revision: {mismatch}"
        )
    return {
        "overlap_rows": int(len(overlap)),
        "mismatch_counts": mismatch,
    }


def build_candidate(
    existing: pd.DataFrame,
    fresh: pd.DataFrame,
    *,
    now_utc: pd.Timestamp | None = None,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    if fresh.empty:
        return existing.copy(), {
            "overlap_rows": 0,
            "appended_rows": 0,
            "fresh_rows": 0,
            "fresh_max_ts": None,
        }

    now = utc_now() if now_utc is None else pd.Timestamp(now_utc)
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    else:
        now = now.tz_convert("UTC")
    completed_cutoff = now.floor("1h")

    fresh_complete = fresh[fresh["t"] < completed_cutoff].copy()
    if fresh_complete.empty:
        return existing.copy(), {
            "overlap_rows": 0,
            "appended_rows": 0,
            "fresh_rows": int(len(fresh)),
            "fresh_max_ts": fresh["t"].max().isoformat(),
        }

    overlap_summary = compare_overlap(existing, fresh_complete)
    old_max = existing["t"].max()
    append = fresh_complete[fresh_complete["t"] > old_max].copy()
    candidate = pd.concat([existing, append], ignore_index=True)
    candidate = candidate.sort_values("t").reset_index(drop=True)

    if candidate["t"].duplicated().any():
        raise RuntimeError("candidate contains duplicate timestamps")
    if not candidate.iloc[: len(existing)].equals(existing.reset_index(drop=True)):
        raise RuntimeError("existing canonical rows changed; refusing write")

    return candidate, {
        **overlap_summary,
        "fresh_rows": int(len(fresh)),
        "fresh_complete_rows": int(len(fresh_complete)),
        "fresh_max_ts": fresh["t"].max().isoformat(),
        "completed_cutoff": completed_cutoff.isoformat(),
        "appended_rows": int(len(append)),
        "old_max_ts": old_max.isoformat(),
        "new_max_ts": candidate["t"].max().isoformat(),
    }


def preserve_owner_mode(path: Path, reference: Path) -> None:
    st = reference.stat()
    os.chmod(path, st.st_mode & 0o777)
    if os.geteuid() == 0:
        os.chown(path, st.st_uid, st.st_gid)


def write_atomic(path: Path, frame: pd.DataFrame) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = path.with_name(f"{path.stem}.pre_qqq_update_{stamp}{path.suffix}")
    tmp = path.with_suffix(path.suffix + ".tmp")
    shutil.copy2(path, backup)
    preserve_owner_mode(backup, path)
    frame.to_parquet(tmp, index=False)
    check = load_canonical(tmp)
    if len(check) != len(frame):
        tmp.unlink(missing_ok=True)
        raise RuntimeError("post-write validation row count mismatch")
    preserve_owner_mode(tmp, path)
    tmp.replace(path)
    return backup


def drive_backup_remote(remote: str, stamp: str) -> str:
    if ":" not in remote:
        raise ValueError("rclone remote must include remote-name prefix")
    prefix, rel = remote.split(":", 1)
    path = Path(rel)
    name = f"{path.stem}.pre_qqq_update_{stamp}{path.suffix}"
    parent = path.parent.as_posix()
    joined = name if parent in {"", "."} else f"{parent}/{name}"
    return f"{prefix}:{joined}"


def _rclone_copyto(source: str, destination: str, config: Path) -> None:
    proc = subprocess.run(
        [
            "rclone",
            "copyto",
            source,
            destination,
            "--config",
            str(config),
        ],
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"rclone copyto failed {source} -> {destination}: "
            f"{(proc.stderr or '')[-1000:]}"
        )


def sync_drive(
    local_path: Path,
    *,
    remote: str,
    rclone_config: Path,
) -> dict[str, Any]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_remote = drive_backup_remote(remote, stamp)
    _rclone_copyto(remote, backup_remote, rclone_config)

    try:
        _rclone_copyto(str(local_path), remote, rclone_config)
        with tempfile.TemporaryDirectory(prefix="kalman-qqq-drive-") as td:
            verify_path = Path(td) / local_path.name
            _rclone_copyto(remote, str(verify_path), rclone_config)
            local_sha = sha256(local_path)
            remote_sha = sha256(verify_path)
            if remote_sha != local_sha:
                raise RuntimeError(
                    f"Drive verification sha256 mismatch "
                    f"local={local_sha} remote={remote_sha}"
                )
    except Exception:
        try:
            _rclone_copyto(backup_remote, remote, rclone_config)
        except Exception as restore_exc:
            raise RuntimeError(
                f"Drive sync failed and restore also failed: {restore_exc}"
            ) from restore_exc
        raise

    return {
        "remote": remote,
        "backup_remote": backup_remote,
        "local_sha256": local_sha,
        "remote_verified_sha256": remote_sha,
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="QQQ 1h Alpaca IEX canonical updater v0")
    p.add_argument("--symbol", default="QQQ")
    p.add_argument("--canonical", required=True)
    p.add_argument("--overlap-days", type=int, default=5)
    p.add_argument("--adjustment", default="raw", choices=["raw", "all", "split", "dividend"])
    p.add_argument("--drive-remote")
    p.add_argument("--rclone-config")
    p.add_argument("--status", required=True)
    p.add_argument("--no-write", action="store_true")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    canonical_path = Path(args.canonical).resolve()
    status_path = Path(args.status).resolve()
    payload: dict[str, Any] = {
        "schema": "kalman-qqq-1h-iex-updater-v0.1",
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "symbol": args.symbol.upper(),
        "timeframe": "1Hour",
        "feed": "iex",
        "adjustment": args.adjustment,
        "research_only": True,
        "trade_execution": False,
        "r51_mutated": False,
    }

    try:
        existing = load_canonical(canonical_path)
        old_sha = sha256(canonical_path)
        start = existing["t"].max() - pd.Timedelta(days=args.overlap_days)
        end = utc_now()
        fresh = fetch_1h_iex(
            args.symbol.upper(),
            start_utc=start,
            end_utc=end,
            adjustment=args.adjustment,
        )
        candidate, audit = build_candidate(existing, fresh, now_utc=end)
        payload["audit"] = audit
        payload["before"] = {
            "rows": int(len(existing)),
            "max_ts": existing["t"].max().isoformat(),
            "sha256": old_sha,
        }

        if args.no_write:
            payload["status"] = "DRY_RUN"
        elif audit["appended_rows"] == 0:
            payload["status"] = "UP_TO_DATE"
        else:
            backup = write_atomic(canonical_path, candidate)
            payload["status"] = "UPDATED"
            payload["backup"] = str(backup)
            payload["after"] = {
                "rows": int(len(candidate)),
                "max_ts": candidate["t"].max().isoformat(),
                "sha256": sha256(canonical_path),
            }
            if args.drive_remote:
                if not args.rclone_config:
                    raise RuntimeError("--rclone-config required with --drive-remote")
                payload["drive_sync"] = sync_drive(
                    canonical_path,
                    remote=args.drive_remote,
                    rclone_config=Path(args.rclone_config).expanduser(),
                )

        write_json_atomic(status_path, payload)
        if canonical_path.exists() and status_path.exists():
            preserve_owner_mode(status_path, canonical_path)
        print(json.dumps(payload, indent=2, default=str))
        return 0
    except Exception as exc:
        payload["status"] = "ERROR_FAIL_CLOSED"
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)
        write_json_atomic(status_path, payload)
        if canonical_path.exists() and status_path.exists():
            preserve_owner_mode(status_path, canonical_path)
        print(json.dumps(payload, indent=2, default=str))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
