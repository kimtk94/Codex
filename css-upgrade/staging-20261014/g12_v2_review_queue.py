"""G12 read-only 55-site review queue: sanitized line/method/shape only.

Analyze original source AST, never import or run CSS. The queue contains no
identifiers, literal arguments, file paths, customer data, or source snippets.
Risk priority and receiver provenance are review HINTS, never evidence of
Sheets mutation or a safe runtime type. No automatic release allowlist.
"""
from __future__ import annotations

import ast
from collections import Counter

from g12_css_ast_guard_v2 import SHEET_METHODS, FUNCTION_WRITERS, _looks_like_sheet_receiver, _name
from g12_v2_receiver_provenance import _collect_bindings, _direct_assignments, _call_hint

STRUCTURAL = frozenset(("sort", "clear", "batch_clear", "resize",
                        "delete_rows", "insert_rows"))
UNKNOWN_TARGET = frozenset(("Call", "Subscript", "Attribute"))


def _scope_of(node, parents):
    cursor = node
    while cursor in parents:
        cursor = parents[cursor]
        if isinstance(cursor, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return cursor
    return None


def _priority(method, shape, provenance):
    if method in STRUCTURAL:
        return "P0_STRUCTURAL_RECEIVER_REVIEW"
    if shape in UNKNOWN_TARGET:
        return "P0_INDIRECT_RECEIVER_REVIEW"
    if provenance in ("MULTIPLE_BINDINGS_OR_REASSIGNMENT",
                      "NESTED_OR_COMPLEX_BINDING",
                      "PARAMETER_UNRESOLVED",
                      "NO_LOCAL_BINDING_IDENTIFIED"):
        return "P1_AMBIGUOUS_BINDING_REVIEW"
    if provenance == "SINGLE_BINDING_CALL_RESULT_UNKNOWN":
        return "P1_CALL_RESULT_REVIEW"
    # No category, including literal container, is considered proven safe.
    return "P2_UNVERIFIED_CONTAINER_OR_OTHER"


def build_queue(source: bytes):
    tree=ast.parse(source)
    parents={}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parents[child]=node
    cache={}
    entries=[]
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func=node.func
        method=_name(func).rsplit(".",1)[-1]
        if isinstance(func, ast.Name) and method in FUNCTION_WRITERS:
            if node.args:
                continue
            owner=None
            shape="MissingArgument"
        elif isinstance(func, ast.Attribute) and method in SHEET_METHODS:
            owner=func.value
            if _looks_like_sheet_receiver(_name(owner).lower()):
                continue
            shape=type(owner).__name__
        else:
            continue
        scope=_scope_of(node,parents)
        if scope is None:
            provenance="MODULE_SCOPE_UNRESOLVED"
            scope_class="module"
        else:
            if scope not in cache:
                cache[scope]=(_collect_bindings(scope),_direct_assignments(scope))
            stores, direct=cache[scope]
            provenance=_call_hint(owner,scope,stores,direct) if owner is not None else "MISSING_ARGUMENT"
            scope_class="main" if scope.name == "main" else "helper"
        entries.append({
            "line":node.lineno,
            "method":method,
            "receiver_shape":shape,
            "provenance":provenance,
            "scope":scope_class,
            "priority":_priority(method,shape,provenance),
            "destination_proven":False,
            "safe_to_ignore":False,
        })
    entries.sort(key=lambda row:(row["line"],row["method"],row["receiver_shape"]))
    signature_counts=Counter()
    for row in entries:
        token=(row["line"],row["method"])
        signature_counts[token]+=1
        row["occurrence"]=signature_counts[token]
    count_by_method=Counter(item["method"] for item in entries)
    count_by_shape=Counter(item["receiver_shape"] for item in entries)
    count_by_priority=Counter(item["priority"] for item in entries)
    count_by_provenance=Counter(item["provenance"] for item in entries)
    return {
        "candidate_count":len(entries),
        "counts_by_method":dict(sorted(count_by_method.items())),
        "counts_by_shape":dict(sorted(count_by_shape.items())),
        "counts_by_priority":dict(sorted(count_by_priority.items())),
        "counts_by_provenance":dict(sorted(count_by_provenance.items())),
        "review_queue":sorted(
            entries,key=lambda row:(
                0 if row["priority"].startswith("P0") else
                1 if row["priority"].startswith("P1") else 2,
                row["line"],row["method"],row["occurrence"])),
        "source_executed":False,
        "write_destination_proven":False,
        "automatic_allowlist_count":0,
        "release_authorized":False,
    }
