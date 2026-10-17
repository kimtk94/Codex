"""Pinned read-only G12 V2 heuristic coverage audit. Never executes CSS source."""
from __future__ import annotations
import ast
import hashlib
import json
import os
from pathlib import Path

from css_g12_writer_surface_audit import extract, function_path

SOURCE = Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py")
PIN = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
METHODS = frozenset(("clear","batch_clear","resize","sort","update","batch_update",
                     "update_cells","append_rows","delete_rows","insert_rows",
                     "format","batch_format"))
FUNCTIONS = frozenset(("set_with_dataframe","overwrite_dataframe",
                       "write_dataframe_to_sheet","sync_dataframe_to_sheet"))
HINTS = ("ws","worksheet","sheet","spread")
DYNAMIC = frozenset(("getattr","setattr","eval","exec","__import__","globals",
                     "locals","vars","compile"))

def audit(source: bytes) -> dict:
    raw = extract(source)
    tree = ast.parse(source)
    targets = {(s["line"],s["method"]) for s in raw["sites"]}
    if raw["candidate_count"] != 28 or raw["sites_truncated"] or len(targets) != 28:
        raise ValueError("FAIL_CLOSED_SOURCE_CALLSITE_INVENTORY_CHANGED")
    classified = []
    dynamic_count = 0
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call):
            continue
        path = function_path(node.func)
        method = path.rsplit(".",1)[-1]
        if method in DYNAMIC:
            dynamic_count += 1
        if (node.lineno,method) not in targets:
            continue
        classified_as = "UNCLASSIFIED"
        if isinstance(node.func,ast.Name) and method in FUNCTIONS and node.args:
            classified_as = "HEURISTICALLY_WRAPPED"
        elif isinstance(node.func,ast.Attribute) and method in METHODS:
            receiver = function_path(node.func.value).lower()
            if any(h in receiver for h in HINTS):
                classified_as = "HEURISTICALLY_WRAPPED"
        classified.append({"line":node.lineno,"method":method,"classification":classified_as})
    classified.sort(key=lambda x:(x["line"],x["method"]))
    if len(classified)!=len(targets):
        raise ValueError("FAIL_CLOSED_MISSING_WRITER_CANDIDATES")
    unclassified = [x for x in classified if x["classification"]=="UNCLASSIFIED"]
    return {
        "source_sha256":hashlib.sha256(source).hexdigest(),
        "candidate_count":len(classified),
        "v2_heuristically_wrapped":len(classified)-len(unclassified),
        "v2_unclassified":len(unclassified),
        "unclassified_sites":unclassified,
        "dynamic_builtin_calls":dynamic_count,
        "all_28_intercepted":len(unclassified)==0,
        "full_sink_isolation_proven":False,
        "receiver_identity_or_write_range_proven":False,
        "production_source_executed":False,
        "production_files_modified":False,
        "release_authorized":False,
    }

def main():
    if os.environ.get("CSS_G12_V2_COVERAGE_READONLY")!="1":
        raise SystemExit("FAIL_CLOSED_AUDIT_FLAG_REQUIRED")
    data=SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest()!=PIN:
        raise SystemExit("FAIL_CLOSED_PRODUCTION_SOURCE_CHANGED")
    print("G12_V2_COVERAGE_BEGIN")
    print(json.dumps(audit(data),sort_keys=True,separators=(",",":")))
    print("G12_V2_COVERAGE_END")
    print("CSS_SOURCE_NEVER_IMPORTED_NO_WRITES")

if __name__=="__main__":
    main()
