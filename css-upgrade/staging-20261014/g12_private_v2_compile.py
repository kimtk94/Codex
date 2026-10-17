"""Compile pinned private CSS through staged V2 AST; never execute compiled code.

Run only in G16 rootless no-network Bubblewrap with private source mounted
read-only. Returns aggregate counters only; emits no source or customer data.
"""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
from types import CodeType
from g12_css_ast_guard_v2 import guard_ast, EXPECTED_SHA

SOURCE=Path("/private/css.py")
def main():
    if os.environ.get("G16_SYNTHETIC_ONLY")!="1":
        raise SystemExit("G12_PRIVATE_COMPILE_MISSING_ISOLATION_FLAG")
    if Path("/home/taehoon").exists():
        raise SystemExit("G12_PRIVATE_COMPILE_HOST_HOME_VISIBLE")
    if not SOURCE.is_file():
        raise SystemExit("G12_PRIVATE_COMPILE_SOURCE_NOT_MOUNTED")
    raw=SOURCE.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_SHA:
        raise SystemExit("G12_PRIVATE_COMPILE_SOURCE_SHA_CHANGED")
    code,summary=guard_ast(raw,exact_sha=EXPECTED_SHA,reject_unclassified=False)
    if not isinstance(code,CodeType):
        raise SystemExit("G12_PRIVATE_COMPILE_INVALID_CODE_RESULT")
    try:
        strict_code, strict_summary=guard_ast(
            raw,exact_sha=EXPECTED_SHA,reject_unclassified=True)
        strict_accepted=isinstance(strict_code,CodeType)
    except RuntimeError as exc:
        if "G12_UNCLASSIFIED_WRITER_CANDIDATES" not in str(exc):
            raise
        strict_accepted=False
    result={
        "source_sha256":summary["source_sha256"],
        "in_memory_compile":"PASS",
        "instrumented_calls":summary["known_writer_calls_instrumented"],
        "unclassified_candidate_calls":summary["unknown_writer_candidates"],
        "strict_unclassified_gate_accepted":strict_accepted,
        "real_css_main_executed":False,
        "production_module_imported":False,
        "all_writer_sinks_intercepted_proven":False,
        "google_sheets_sqlite_atomicity_proven":False,
        "live_system_modified":False,
        "release_authorized":False,
    }
    print("G12_PRIVATE_V2_COMPILE_BEGIN")
    print(json.dumps(result,sort_keys=True,separators=(",",":")))
    print("G12_PRIVATE_V2_COMPILE_END")
    print("G12_NO_EXECUTION_NO_NETWORK_NO_LIVE_WRITES")
if __name__=="__main__":
    main()
