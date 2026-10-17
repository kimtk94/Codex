"""Aggregate-only AST audit of CSS dynamic dispatch and possible Sheet bypass.

Never import or execute CSS. Only count known Python dispatch primitives and
allowlisted method categories. Never print source/identifiers/literals.
"""
from __future__ import annotations
import ast
from collections import Counter

PRIMITIVES = frozenset((
    "getattr", "setattr", "eval", "exec", "__import__",
    "globals", "locals", "vars", "compile"
))
SHEET_METHODS = frozenset((
    "update","batch_update","update_cells","clear","batch_clear",
    "resize","sort","set_with_dataframe","append_rows","delete_rows",
    "insert_rows","format","batch_format"
))
OBJECT_TOKENS = frozenset((
    "ws","sheet","sheets","worksheet","spreadsheet","gspread","gsheet"
))


def _name(expr):
    if isinstance(expr,ast.Name):
        return expr.id
    if isinstance(expr,ast.Attribute):
        head=_name(expr.value)
        return (head+"." if head else "")+expr.attr
    return ""


def _sheet_hint(expr):
    pieces=_name(expr).lower().replace(".","_").split("_")
    return bool(OBJECT_TOKENS.intersection(pieces))


def inspect_dispatch(source):
    tree=ast.parse(source)
    methods=Counter()
    primitives=Counter()
    sheet_hints=Counter()
    direct_invocations=Counter()
    unresolved=0
    for call in ast.walk(tree):
        if not isinstance(call,ast.Call):
            continue
        f=call.func
        if not isinstance(f,ast.Name) or f.id not in PRIMITIVES:
            if isinstance(f,ast.Call) and isinstance(f.func,ast.Name) and f.func.id=="getattr":
                direct_invocations["CALL_OF_GETATTR_RESULT"]+=1
            continue
        primitives[f.id]+=1
        if f.id not in ("getattr","setattr"):
            unresolved+=1
            continue
        second=call.args[1] if len(call.args)>=2 else None
        if isinstance(second,ast.Constant) and isinstance(second.value,str):
            method=second.value
            if method in SHEET_METHODS:
                methods[method]+=1
                if call.args and _sheet_hint(call.args[0]):
                    sheet_hints[method]+=1
            else:
                methods["OTHER_LITERAL_METHOD"]+=1
        else:
            methods["DYNAMIC_METHOD_ARGUMENT"]+=1
            unresolved+=1
    return {
        "total_dynamic_primitive_calls":sum(primitives.values()),
        "primitive_counts":dict(sorted(primitives.items())),
        "attribute_target_method_counts":dict(sorted(methods.items())),
        "sheet_name_hint_counts":dict(sorted(sheet_hints.items())),
        "direct_getattr_result_invocations":sum(direct_invocations.values()),
        "dynamic_target_unresolved":unresolved,
        "all_dynamic_sheet_sinks_intercepted":False,
        "method_literal_is_actual_sheet_call_proof":False,
        "source_imported_or_executed":False,
        "live_system_modified":False,
        "release_authorized":False,
    }
