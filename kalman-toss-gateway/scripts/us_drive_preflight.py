#!/usr/bin/env python3
"""Read-only Drive preflight for Kalman US pipeline; never reads secret contents.

Exit: 0 accessible, 20 transient EIO exhausted, 21 permissions,
22 missing path, 23 unexpected filesystem error. Does not modify runtime state.
"""
from __future__ import annotations

import argparse
import errno
import os
import sys
import time
from pathlib import Path

DEFAULT_PATH = "/content/drive/MyDrive/Upbit_BTC/private/investment_hub_ingest_secret.txt"
RETRYABLE = {errno.EIO}


def check(path: Path, retries: int = 3, sleep=time.sleep, stat=None) -> int:
    stat = stat or (lambda: path.stat())
    for attempt in range(1, retries + 1):
        try:
            info = stat()
            if not info.st_mode:
                raise OSError(errno.EIO, "invalid stat mode")
            print(f"DRIVE_PREFLIGHT_PASS attempt={attempt}")
            return 0
        except OSError as exc:
            code = exc.errno
            if code in (errno.EACCES, errno.EPERM):
                print("DRIVE_PREFLIGHT_FAIL reason=PERMISSION", file=sys.stderr)
                return 21
            if code == errno.ENOENT:
                print("DRIVE_PREFLIGHT_FAIL reason=MISSING", file=sys.stderr)
                return 22
            if code not in RETRYABLE:
                print(f"DRIVE_PREFLIGHT_FAIL reason=OTHER errno={code}", file=sys.stderr)
                return 23
            if attempt == retries:
                print("DRIVE_PREFLIGHT_FAIL reason=EIO_EXHAUSTED", file=sys.stderr)
                return 20
            print(f"DRIVE_PREFLIGHT_RETRY reason=EIO attempt={attempt}", file=sys.stderr)
            sleep(min(2 ** (attempt - 1), 4))
    return 23


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default=DEFAULT_PATH)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()
    if not 1 <= args.retries <= 5:
        parser.error("--retries must be between 1 and 5")
    return check(Path(args.path), retries=args.retries)


if __name__ == "__main__":
    sys.exit(main())
