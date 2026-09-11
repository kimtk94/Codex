from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pandas as pd


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, path)


def write_snapshot(
    frame: pd.DataFrame,
    path: Path,
    *,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    """Atomically write a Parquet snapshot and JSON provenance sidecar."""
    path = path.expanduser()
    if path.suffix.lower() != ".parquet":
        raise ValueError("snapshot path must end with .parquet")

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    frame.to_parquet(tmp, index=False)
    checksum = file_sha256(tmp)
    os.replace(tmp, path)

    manifest = {
        **metadata,
        "snapshot_path": str(path),
        "snapshot_sha256": checksum,
        "snapshot_rows": int(len(frame)),
        "written_at": pd.Timestamp.now(tz="UTC").isoformat(),
    }
    atomic_json(path.with_suffix(".metadata.json"), manifest)
    return manifest
