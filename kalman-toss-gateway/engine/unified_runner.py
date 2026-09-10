"""Runtime bootstrap for the validated Unified Colab server port.

The generated source is stored as LZMA+base64 chunks beside this file. The
bootstrap validates the exact chunk set, Base64 alphabet/length, encoded
length and source SHA-256 before executing anything.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import lzma
import re
from pathlib import Path

EXPECTED_SHA256 = "e1d68ef0744b1083be8c4ba32908f090e0f0b70742cb224df75c9596d06540f8"
EXPECTED_ENCODED_LENGTH = 70688
EXPECTED_PARTS = [f"_unified_payload_{i:02d}.b64" for i in range(15)]

_here = Path(__file__).resolve().parent
_parts = sorted(_here.glob("_unified_payload_*.b64"))
_names = [p.name for p in _parts]
if _names != EXPECTED_PARTS:
    raise RuntimeError(
        "Unified server payload file set mismatch. "
        f"expected={EXPECTED_PARTS!r}, actual={_names!r}"
    )

_encoded_parts: list[str] = []
for _part in _parts:
    try:
        _text = _part.read_text(encoding="ascii")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{_part.name}: payload is not ASCII") from exc

    _compact = "".join(_text.split())
    _bad = sorted(set(re.sub(r"[A-Za-z0-9+/=]", "", _compact)))
    if _bad:
        raise RuntimeError(
            f"{_part.name}: invalid Base64 characters found: {_bad!r}"
        )
    if len(_compact) % 4 != 0:
        raise RuntimeError(
            f"{_part.name}: Base64 length {len(_compact)} is not divisible by 4"
        )
    _encoded_parts.append(_compact)

_encoded = "".join(_encoded_parts)
if len(_encoded) != EXPECTED_ENCODED_LENGTH:
    raise RuntimeError(
        "Unified payload encoded length mismatch: "
        f"{len(_encoded)} != {EXPECTED_ENCODED_LENGTH}"
    )

try:
    _packed = base64.b64decode(_encoded, validate=True)
except binascii.Error as exc:
    raise RuntimeError(f"Unified payload Base64 decode failed: {exc}") from exc

try:
    _source = lzma.decompress(_packed)
except lzma.LZMAError as exc:
    raise RuntimeError("Unified payload LZMA decompression failed") from exc

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
