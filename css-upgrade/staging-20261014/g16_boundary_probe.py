"""Synthetic-only OS boundary probe for CSS G16.

Never imports production CSS, never opens a production database or spreadsheet,
never accepts mail/CRM credentials, and contains no customer data.
This confirms only the disposable-container boundary, NOT full-engine isolation.
"""
from __future__ import annotations

import errno
import os
import socket
import sys
from pathlib import Path

TEST_NET_HOST = "198.51.100.1"  # RFC 5737 TEST-NET-2, no traffic sent
BANNED_ENV_VARS = (
    "SERVER_SSH_KEY", "SSH_KEY", "GOOGLE_APPLICATION_CREDENTIALS",
    "GMAIL_PASSWORD", "SMTP_PASSWORD", "OPENAI_API_KEY",
    "SFDC_CLIENT_SECRET", "SALESFORCE_CLIENT_SECRET",
)

def require(condition: bool, code: str) -> None:
    if not condition:
        raise SystemExit("G16_BOUNDARY_FAIL_" + code)

def readonly_mount(path: str) -> bool:
    return bool(os.statvfs(path).f_flag & os.ST_RDONLY)

def main() -> None:
    require(os.environ.get("G16_SYNTHETIC_ONLY") == "1", "SYNTHETIC_MODE")
    require(not any(key in os.environ for key in BANNED_ENV_VARS), "SECRET_ENV")
    print("G16_NO_PRODUCTION_CREDENTIALS_PASS")

    fixture = Path("/input/g16_boundary_probe.py")
    require(fixture.is_file(), "FIXTURE_MISSING")
    require(readonly_mount("/"), "ROOTFS_RW")
    require(readonly_mount("/input"), "INPUT_RW")
    print("G16_ROOTFS_AND_INPUT_READONLY_PASS")

    # Test an outbound route without sending a packet. UDP connect only
    # checks route availability; it does not transmit application data.
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect((TEST_NET_HOST, 9))
        except OSError as exc:
            require(exc.errno in (errno.ENETUNREACH, errno.EHOSTUNREACH),
                    "NETWORK_ERROR_UNEXPECTED")
        else:
            raise SystemExit("G16_BOUNDARY_FAIL_OUTBOUND_ROUTE_EXISTS")
    print("G16_NETWORK_EGRESS_DENIED_PASS")

    for protected in (Path("/input/new-data"), Path("/etc/g16-audit-probe")):
        try:
            protected.write_text("synthetic-only")
        except OSError:
            pass
        else:
            protected.unlink(missing_ok=True)
            raise SystemExit("G16_BOUNDARY_FAIL_WRITE_PROTECTION")
    print("G16_PROTECTED_PATH_WRITES_DENIED_PASS")

    require(not Path("/home/taehoon/services/novogene-css").exists(),
            "PRODUCTION_PATH_VISIBLE")
    require(not Path("/srv/novogene-css").exists(), "ALTERNATE_PRODUCTION_PATH_VISIBLE")
    print("G16_PRODUCTION_PATHS_NOT_MOUNTED_PASS")

    scratch = Path("/tmp/g16-synthetic-temp")
    scratch.write_text("synthetic")
    require(scratch.read_text() == "synthetic", "TEMP_FIXTURE")
    scratch.unlink()
    print("G16_DISPOSABLE_TMPFS_PASS")
    print("G16_CONTAINER_BOUNDARY_PROBE_PASS")
    print("G12_FULL_ENGINE_NOT_EXECUTED")
    print("G16_ALL_SINKS_NOT_YET_VERIFIED")

if __name__ == "__main__":
    main()
