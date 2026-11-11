from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from research.quant_stack.prediction_market_leadlag_v0 import load_asset_history
from research.quant_stack.prediction_market_oos_v0 import (
    evaluate_frozen_hypothesis,
    load_spec,
)


DEFAULT_REPO = "DineshKumar8399/polymarket-orderbook-dataset"
TAG_RE = re.compile(r"^data-(\d{4})-(\d{2})-(\d{2})$")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def run_checked(args: list[str], *, cwd: Path | None = None) -> str:
    proc = subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = (proc.stderr or "").strip()
        stdout = (proc.stdout or "").strip()
        raise RuntimeError(
            f"command failed rc={proc.returncode}: {' '.join(args)}\n"
            f"stdout={stdout[-1000:]}\nstderr={stderr[-1000:]}"
        )
    return proc.stdout


def parse_tag_date(tag: str) -> tuple[int, int, int] | None:
    m = TAG_RE.match(tag)
    if not m:
        return None
    return tuple(int(x) for x in m.groups())


def is_newer_release(latest_tag: str, discovery_tag: str) -> bool:
    latest_date = parse_tag_date(latest_tag)
    discovery_date = parse_tag_date(discovery_tag)
    if latest_date is not None and discovery_date is not None:
        return latest_date > discovery_date
    return latest_tag != discovery_tag


def latest_release(repo: str) -> dict[str, Any]:
    raw = run_checked(["gh", "api", f"repos/{repo}/releases/latest"])
    payload = json.loads(raw)
    return {
        "tag_name": payload.get("tag_name"),
        "published_at": payload.get("published_at"),
        "html_url": payload.get("html_url"),
        "assets": [
            {
                "name": x.get("name"),
                "size": x.get("size"),
                "digest": x.get("digest"),
                "updated_at": x.get("updated_at"),
            }
            for x in payload.get("assets", [])
        ],
    }


def select_archive_asset(release: dict[str, Any]) -> dict[str, Any]:
    candidates = [
        x
        for x in release.get("assets", [])
        if str(x.get("name") or "").startswith("polymarket-orderbook-")
        and str(x.get("name") or "").endswith(".tar.zst")
    ]
    if len(candidates) != 1:
        raise RuntimeError(
            f"expected exactly one orderbook tar.zst asset, found {len(candidates)}"
        )
    asset = candidates[0]
    digest = str(asset.get("digest") or "")
    if not digest.startswith("sha256:"):
        raise RuntimeError("release asset is missing GitHub sha256 digest")
    return asset


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def validate_archive_digest(path: Path, digest: str) -> str:
    expected = digest.split(":", 1)[1].lower()
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(
            f"archive sha256 mismatch expected={expected} actual={actual}"
        )
    return actual


def parquet_range(path: Path, symbol: str) -> dict[str, Any]:
    if not path.exists():
        return {
            "exists": False,
            "rows": 0,
            "min_ts": None,
            "max_ts": None,
        }
    frame = load_asset_history(path, symbol)
    if frame.empty:
        return {
            "exists": True,
            "rows": 0,
            "min_ts": None,
            "max_ts": None,
        }
    return {
        "exists": True,
        "rows": int(len(frame)),
        "min_ts": frame["ts"].min().isoformat(),
        "max_ts": frame["ts"].max().isoformat(),
    }


def refresh_asset_from_drive(
    *,
    remote: str,
    local_path: Path,
    rclone_config: Path,
    symbol: str,
) -> dict[str, Any]:
    before = parquet_range(local_path, symbol)
    local_path.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="kalman-pm-asset-") as td:
        candidate = Path(td) / local_path.name
        run_checked(
            [
                "rclone",
                "copyto",
                remote,
                str(candidate),
                "--config",
                str(rclone_config),
            ]
        )
        after = parquet_range(candidate, symbol)
        if not after["exists"] or after["rows"] == 0 or after["max_ts"] is None:
            raise RuntimeError("Drive asset candidate is empty or invalid")

        if before["max_ts"] is not None:
            if pd.Timestamp(after["max_ts"]) < pd.Timestamp(before["max_ts"]):
                raise RuntimeError(
                    "Drive asset regressed in time; refusing to replace local canonical"
                )

        candidate_sha = sha256(candidate)
        local_sha = sha256(local_path) if local_path.exists() else None
        replaced = candidate_sha != local_sha
        if replaced:
            tmp = local_path.with_suffix(local_path.suffix + ".tmp")
            shutil.copy2(candidate, tmp)
            tmp.replace(local_path)

    current = parquet_range(local_path, symbol)
    return {
        "source": remote,
        "before": before,
        "after": current,
        "replaced": replaced,
        "sha256": sha256(local_path),
    }


def ensure_release_archive(
    *,
    repo: str,
    tag: str,
    asset: dict[str, Any],
    data_root: Path,
) -> dict[str, Any]:
    release_root = data_root / "releases" / tag
    extract_root = release_root / "extracted"
    release_root.mkdir(parents=True, exist_ok=True)
    archive_path = release_root / str(asset["name"])

    downloaded = False
    if not archive_path.exists():
        run_checked(
            [
                "gh",
                "release",
                "download",
                tag,
                "--repo",
                repo,
                "--pattern",
                str(asset["name"]),
                "--dir",
                str(release_root),
            ]
        )
        downloaded = True

    actual_sha = validate_archive_digest(archive_path, str(asset["digest"]))

    required = [
        extract_root / "markets.parquet",
        extract_root / "data_quality.parquet",
        extract_root / "watch_quotes.parquet",
        extract_root / "quotes",
    ]
    extracted = False
    if not all(x.exists() for x in required):
        if extract_root.exists():
            shutil.rmtree(extract_root)
        extract_root.mkdir(parents=True, exist_ok=True)
        run_checked(
            ["tar", "--zstd", "-xf", str(archive_path), "-C", str(extract_root)]
        )
        extracted = True

    missing = [str(x) for x in required if not x.exists()]
    if missing:
        raise RuntimeError(f"release extraction missing required paths: {missing}")

    return {
        "release_root": str(release_root),
        "archive_path": str(archive_path),
        "extract_root": str(extract_root),
        "downloaded": downloaded,
        "extracted": extracted,
        "sha256": actual_sha,
    }


def build_release_canonical(
    *,
    app_root: Path,
    extract_root: Path,
    tag: str,
    data_root: Path,
    config: Path,
) -> dict[str, Any]:
    out_dir = data_root / "canonical" / tag
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "prediction_macro_v0.parquet"

    if not output.exists():
        raw = run_checked(
            [
                sys.executable,
                "-m",
                "research.quant_stack.prediction_market_archive_v0",
                "--archive-root",
                str(extract_root),
                "--output",
                str(output),
                "--config",
                str(config),
            ],
            cwd=app_root,
        )
        try:
            build_summary = json.loads(raw)
        except json.JSONDecodeError:
            build_summary = {"raw_output": raw[-4000:]}
    else:
        build_summary = {"status": "REUSED_EXISTING_CANONICAL"}

    frame = pd.read_parquet(output, columns=["ts"])
    ts = pd.to_datetime(frame["ts"], utc=True, errors="coerce").dropna()
    return {
        "output": str(output),
        "rows": int(len(frame)),
        "min_ts": ts.min().isoformat() if len(ts) else None,
        "max_ts": ts.max().isoformat() if len(ts) else None,
        "sha256": sha256(output),
        "build": build_summary,
    }


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8")
    tmp.replace(path)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Prediction-market frozen OOS release watcher v0")
    p.add_argument("--app-root", required=True)
    p.add_argument("--spec", required=True)
    p.add_argument("--config", required=True)
    p.add_argument("--repo", default=DEFAULT_REPO)
    p.add_argument(
        "--data-root",
        default="/home/taehoon/kalman-data/prediction-market",
    )
    p.add_argument(
        "--qqq-local",
        default="/home/taehoon/kalman-data/market/1h/QQQ_1h_2017plus.parquet",
    )
    p.add_argument(
        "--qqq-drive",
        default="gdrive:US_ETF/history_1h/QQQ_1h_2017plus.parquet",
    )
    p.add_argument(
        "--rclone-config",
        default="/home/taehoon/.config/rclone/rclone.conf",
    )
    p.add_argument(
        "--status",
        default="/home/taehoon/kalman-data/prediction-market/oos-watch-v0/latest.json",
    )
    p.add_argument(
        "--lock",
        default="/home/taehoon/kalman-data/prediction-market/oos-watch-v0/watch.lock",
    )
    p.add_argument("--bootstrap-iterations", type=int, default=5000)
    return p.parse_args()


def main() -> int:
    args = parse_args()
    app_root = Path(args.app_root).resolve()
    spec_path = Path(args.spec).resolve()
    config_path = Path(args.config).resolve()
    data_root = Path(args.data_root).resolve()
    status_path = Path(args.status).resolve()
    lock_path = Path(args.lock).resolve()
    qqq_local = Path(args.qqq_local).resolve()
    rclone_config = Path(args.rclone_config).resolve()

    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_handle = lock_path.open("a+")
    try:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        print(json.dumps({"status": "SKIPPED_LOCKED"}, indent=2))
        return 0

    spec, spec_sha = load_spec(spec_path)
    discovery_tag = str(spec["discovery"]["source_release"])
    discovery_cutoff = pd.Timestamp(spec["discovery"]["data_end_utc"])

    payload: dict[str, Any] = {
        "schema": "kalman-prediction-market-oos-watch-v0.1",
        "checked_at_utc": utc_now(),
        "research_only": True,
        "spec_sha256": spec_sha,
        "hypothesis_id": spec["hypothesis_id"],
        "discovery_release": discovery_tag,
        "discovery_cutoff": discovery_cutoff.isoformat(),
        "production_promotion": False,
        "r51_mutated": False,
        "trade_execution": False,
    }

    try:
        asset_refresh = refresh_asset_from_drive(
            remote=args.qqq_drive,
            local_path=qqq_local,
            rclone_config=rclone_config,
            symbol=str(spec["hypothesis"]["symbol"]),
        )
        payload["asset_refresh"] = asset_refresh

        release = latest_release(args.repo)
        payload["latest_release"] = release
        latest_tag = str(release.get("tag_name") or "")
        if not latest_tag:
            raise RuntimeError("latest release has no tag_name")

        if not is_newer_release(latest_tag, discovery_tag):
            payload["status"] = "NO_NEW_RELEASE"
            write_json_atomic(status_path, payload)
            print(json.dumps(payload, indent=2, default=str))
            return 0

        asset = select_archive_asset(release)
        archive = ensure_release_archive(
            repo=args.repo,
            tag=latest_tag,
            asset=asset,
            data_root=data_root,
        )
        payload["archive"] = archive

        canonical = build_release_canonical(
            app_root=app_root,
            extract_root=Path(archive["extract_root"]),
            tag=latest_tag,
            data_root=data_root,
            config=config_path,
        )
        payload["canonical"] = canonical

        if canonical["max_ts"] is None or pd.Timestamp(canonical["max_ts"]) <= discovery_cutoff:
            payload["status"] = "NEW_RELEASE_NO_TRUE_OOS_ROWS"
            write_json_atomic(status_path, payload)
            print(json.dumps(payload, indent=2, default=str))
            return 0

        prediction = pd.read_parquet(canonical["output"])
        asset_frame = load_asset_history(qqq_local, str(spec["hypothesis"]["symbol"]))
        result, rows = evaluate_frozen_hypothesis(
            prediction,
            asset_frame,
            spec,
            bootstrap_iterations=args.bootstrap_iterations,
        )
        payload["oos"] = result
        payload["status"] = result["status"]

        out_dir = data_root / "oos-watch-v0" / latest_tag
        out_dir.mkdir(parents=True, exist_ok=True)
        if not rows.empty:
            rows.to_parquet(out_dir / "oos_aligned_rows.parquet", index=False)
        write_json_atomic(out_dir / "oos_summary.json", result)
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2, default=str))
        return 0
    except Exception as exc:
        payload["status"] = "ERROR_FAIL_CLOSED"
        payload["error_type"] = type(exc).__name__
        payload["error"] = str(exc)
        write_json_atomic(status_path, payload)
        print(json.dumps(payload, indent=2, default=str))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
