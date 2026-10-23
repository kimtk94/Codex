#!/usr/bin/env python3
"""Fail closed unless the actual public outbound IP is NTIS-approved."""
import ipaddress
import os
import urllib.request

approved = os.environ.get("NTIS_APPROVED_IP", "").strip()
if not approved:
    raise SystemExit("NTIS_APPROVED_IP is not configured")
ipaddress.ip_address(approved)
req = urllib.request.Request(
    "https://api.ipify.org",
    headers={"User-Agent": "ntis-egress-preflight/1.0"},
)
try:
    with urllib.request.urlopen(req, timeout=12) as res:
        actual = res.read(100).decode("ascii").strip()
    ipaddress.ip_address(actual)
except Exception as exc:
    raise SystemExit(f"Outbound IP detection failed: {type(exc).__name__}") from None
if actual != approved:
    raise SystemExit("Outbound IP does not match the NTIS-approved address; refusing API call")
print("NTIS outbound IP matches the registered address")
