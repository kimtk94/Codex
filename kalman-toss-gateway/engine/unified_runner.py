"""Runtime bootstrap for the validated Unified Colab server port.

The generated source is stored as LZMA+base64 chunks beside this file. The
SHA-256 guard fails closed if any chunk is modified or incomplete.
"""
from __future__ import annotations

import base64
import hashlib
import lzma
from pathlib import Path

EXPECTED_SHA256 = "e1d68ef0744b1083be8c4ba32908f090e0f0b70742cb224df75c9596d06540f8"

_here = Path(__file__).resolve().parent
_parts = sorted(_here.glob("_unified_payload_*.b64"))
if not _parts:
    raise RuntimeError("Unified server payload is missing")

_encoded = "".join(p.read_text(encoding="ascii").strip() for p in _parts)
_source = lzma.decompress(base64.b64decode(_encoded))
_actual_sha256 = hashlib.sha256(_source).hexdigest()
if _actual_sha256 != EXPECTED_SHA256:
    raise RuntimeError(
        f"Unified server payload integrity check failed: {_actual_sha256} != {EXPECTED_SHA256}"
    )

exec(
    compile(_source.decode("utf-8"), "Investment_Hub_Unified_Colab_v1.server.py", "exec"),
    globals(),
    globals(),
)
