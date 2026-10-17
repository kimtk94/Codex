"""CSS read-only AST callsite ownership context audit (no CSS import).

Only emits known-tab references, source line numbers, bounded aggregate counts
and sanitized AST shapes. Never prints arbitrary literals, source, credentials,
customer/project data, or private function bodies. A matching tab reference in
a function is contextual evidence, NOT proof that any call targets that tab.
"""
from __future__ import annotations
import ast
import collections
import hashlib
import json
import os
from pathlib import Path

SOURCE = Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py")
SHA = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
TABS = {
    "CSS Project Dashboard":"dashboard",
    "CSS Contract-SIF Tracker":"sif_tracker",
    "CSS Contract-SIF Skipped":"sif_skipped",
    "CSS Manual Exclusions":"manual_exclusions",
}
HIGH_RISK = frozenset(("batch_clear","clear","resize","sort","set_with_dataframe","overwrite_dataframe","delete_rows","insert_rows"))
WRITE_METHODS = HIGH_RISK | frozenset(("update","batch_update","update_cells","append_rows","format","batch_format"))
SHEET_HINT = ("ws","sheet","worksheet","spread","gspread")

def name(expr):
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return name(expr.value)+"."+expr.attr
    return ""

def identify_named_tab_constants(tree):
    """One-hop direct module constant aliases to a known title only."""
    symbols={}
    for node in tree.body:
        if not isinstance(node,(ast.Assign,ast.AnnAssign)):
            continue
        value=node.value
        if isinstance(value,ast.Constant) and isinstance(value.value,str) and value.value in TABS:
            tab=TABS[value.value]
        elif isinstance(value,ast.Name) and value.id in symbols:
            tab=symbols[value.id]
        else:
            continue
        targets=node.targets if isinstance(node,ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target,ast.Name):
                symbols[target.id]=tab
    return symbols

def reference_tabs(fn, module_symbols):
    """Contextual reference within function, not established write destination."""
    out=set()
    for node in ast.walk(fn):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value in TABS:
            out.add(TABS[node.value])
        elif isinstance(node,ast.Name) and node.id in module_symbols:
            out.add(module_symbols[node.id])
    return sorted(out)

def inspect(source:bytes):
    tree=ast.parse(source)
    symbols=identify_named_tab_constants(tree)
    result=[]
    all_candidates=collections.Counter()
    function_counts=collections.Counter()
    for node in tree.body:
        if not isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        context=reference_tabs(node,symbols)
        for call in ast.walk(node):
            if not isinstance(call,ast.Call):
                continue
            callpath=name(call.func)
            method=callpath.split(".")[-1]
            if method not in WRITE_METHODS:
                continue
            if method in ("update","batch_update","clear","resize","sort","format") and not any(
                key in callpath.lower() for key in SHEET_HINT
            ):
                continue
            risk="structural_or_full_rewrite" if method in HIGH_RISK else "unknown_value_or_format"
            if method=="append_rows":
                risk="append"
            all_candidates[risk]+=1
            function_counts["main" if node.name=="main" else "helper"]+=1
            if risk=="structural_or_full_rewrite" or context:
                arg_shapes=[type(arg).__name__ for arg in call.args[:3]]
                result.append({
                    "line":call.lineno,
                    "method":method,
                    "scope":"main" if node.name=="main" else "helper",
                    "risk":risk,
                    "tab_references_in_same_function":context,
                    "tab_reference_is_write_target_proof":False,
                    "first_three_arg_shapes":arg_shapes,
                    "keyword_arg_count":len(call.keywords),
                })
    return {
        "source_sha256":hashlib.sha256(source).hexdigest(),
        "module_known_tab_constants":dict(sorted(collections.Counter(symbols.values()).items())),
        "candidate_methods_by_risk":dict(sorted(all_candidates.items())),
        "candidate_methods_by_scope":dict(sorted(function_counts.items())),
        "contextual_sites":sorted(result,key=lambda x:x["line"])[:100],
        "sites_truncated":len(result)>100,
        "call_target_or_field_masks_proven":False,
        "all_writer_paths_exhaustively_classified":False,
        "source_or_function_executed":False,
        "external_writes_performed":False,
    }

def main():
    if os.environ.get("G12_STATIC_CONTEXT_READONLY")!="1":
        raise SystemExit("G12_AUDIT_FLAG_REQUIRED")
    content=SOURCE.read_bytes()
    if hashlib.sha256(content).hexdigest()!=SHA:
        raise SystemExit("G12_SOURCE_FINGERPRINT_CHANGED")
    print("G12_WRITER_CONTEXT_BEGIN")
    print(json.dumps(inspect(content),sort_keys=True,separators=(",",":")))
    print("G12_WRITER_CONTEXT_END")
    print("G12_STATIC_READ_ONLY_NO_SOURCE_IMPORTED")

if __name__=="__main__":
    main()
