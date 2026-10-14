"""Fail-closed, read-only cached-token preflight for broker audit.

Does not call Toss OAuth, alter cache/locks, or emit token content.
This helper alone does not query broker endpoints.
"""
from __future__ import annotations
import json
import time
from pathlib import Path

def token_preflight(cache_path: str | Path, *, now: float | None = None) -> dict:
    current = time.time() if now is None else float(now)
    path = Path(cache_path)
    try:
        if not path.is_file():
            return {"status":"BLOCKED","reason":"CACHE_ABSENT"}
        with path.open("r", encoding="utf-8") as handle:
            raw=json.load(handle)
        token=raw.get("access_token")
        expires_at=float(raw.get("expires_at",0))
        if not isinstance(token,str) or not token.strip():
            return {"status":"BLOCKED","reason":"TOKEN_MISSING"}
        if expires_at-current <= 60:
            return {"status":"BLOCKED","reason":"TOKEN_EXPIRED_OR_NEAR_EXPIRY"}
        return {"status":"READY","reason":"VALID_CACHED_TOKEN","remaining_seconds":int(expires_at-current)}
    except (OSError,ValueError,TypeError,json.JSONDecodeError):
        return {"status":"BLOCKED","reason":"CACHE_UNREADABLE"}
