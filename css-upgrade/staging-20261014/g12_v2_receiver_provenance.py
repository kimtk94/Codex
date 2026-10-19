"""Conservative G12 V2 receiver provenance audit, synthetic or SHA-pinned AST only.

Reports *counts*, not source, identifiers, literals, or row/customer contents.
No receiver category proves runtime object type or Sheets writer safety.
"""
from __future__ import annotations
import ast
from collections import Counter, defaultdict

WRITER_METHODS = frozenset(("update", "sort", "clear", "resize",
    "batch_update", "batch_clear", "update_cells", "append_rows",
    "insert_rows", "delete_rows", "format", "batch_format"))
SHEET_WORDS = frozenset(("ws", "worksheet", "sheet", "sheets",
    "spreadsheet", "gspread", "gsheet"))


def _target_name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return _target_name(node.value) + "." + node.attr
    return ""


def _looks_sheet(node):
    return bool(SHEET_WORDS.intersection(
        _target_name(node).lower().replace(".", "_").split("_")))


def _collect_bindings(fn):
    """Capture all variable stores, including conditionals, loops and walrus."""
    stores=defaultdict(list)
    class Bind(ast.NodeVisitor):
        def visit_FunctionDef(self,node):
            if node is fn:
                self.generic_visit(node)
        visit_AsyncFunctionDef=visit_FunctionDef
        def visit_ClassDef(self,node):
            return
        def visit_Lambda(self,node):
            return
        def visit_Name(self,node):
            if isinstance(node.ctx,(ast.Store,ast.Del)):
                stores[node.id].append(node)
    Bind().visit(fn)
    return stores


def _direct_assignments(fn):
    assigned=defaultdict(list)
    for stmt in fn.body:
        if isinstance(stmt,ast.Assign):
            for target in stmt.targets:
                if isinstance(target,ast.Name):
                    assigned[target.id].append(stmt.value)
        elif isinstance(stmt,ast.AnnAssign) and isinstance(stmt.target,ast.Name):
            assigned[stmt.target.id].append(stmt.value)
    return assigned


def _call_hint(node,fn,stores,direct):
    if not isinstance(node,ast.Name):
        return type(node).__name__.upper()+"_RECEIVER_UNKNOWN"
    key=node.id
    params=fn.args
    arg_names={a.arg for a in params.posonlyargs+params.args+params.kwonlyargs}
    if params.vararg: arg_names.add(params.vararg.arg)
    if params.kwarg: arg_names.add(params.kwarg.arg)
    if key in arg_names:
        return "PARAMETER_UNRESOLVED"
    writes=stores.get(key,[])
    assignments=direct.get(key,[])
    if len(writes)==1 and len(assignments)==1:
        expr=assignments[0]
        if isinstance(expr,(ast.Dict,ast.List,ast.Tuple,ast.Set)):
            return "SINGLE_BINDING_CONTAINER_LITERAL_HINT"
        if isinstance(expr,(ast.DictComp,ast.ListComp,ast.SetComp)):
            return "SINGLE_BINDING_COMPREHENSION_HINT"
        if isinstance(expr,ast.Call):
            if isinstance(expr.func,ast.Name) and expr.func.id in (
                    "dict","list","set"):
                return "SINGLE_BINDING_BUILTIN_NAME_CONSTRUCTOR_HINT"
            return "SINGLE_BINDING_CALL_RESULT_UNKNOWN"
        return "SINGLE_BINDING_OTHER_ASSIGNMENT_UNKNOWN"
    if len(writes)>1:
        return "MULTIPLE_BINDINGS_OR_REASSIGNMENT"
    if len(writes)==1:
        return "NESTED_OR_COMPLEX_BINDING"
    return "NO_LOCAL_BINDING_IDENTIFIED"


def audit_receiver_provenance(raw):
    tree=ast.parse(raw)
    evidence=Counter()
    method_counts=Counter()
    all_calls=0
    for fn in ast.walk(tree):
        if not isinstance(fn,(ast.FunctionDef,ast.AsyncFunctionDef)):
            continue
        stores=_collect_bindings(fn)
        direct=_direct_assignments(fn)
        class Scan(ast.NodeVisitor):
            def visit_FunctionDef(self,node):
                if node is fn:
                    self.generic_visit(node)
            visit_AsyncFunctionDef=visit_FunctionDef
            def visit_ClassDef(self,node):
                return
            def visit_Lambda(self,node):
                return
            def visit_Call(self,node):
                nonlocal all_calls
                if isinstance(node.func,ast.Attribute):
                    method=node.func.attr
                    if method in WRITER_METHODS and not _looks_sheet(node.func.value):
                        label=_call_hint(node.func.value,fn,stores,direct)
                        evidence[label]+=1
                        method_counts[method]+=1
                        all_calls+=1
                self.generic_visit(node)
        Scan().visit(fn)
    return {
        "unclassified_site_count":all_calls,
        "method_counts":dict(sorted(method_counts.items())),
        "provenance_hint_counts":dict(sorted(evidence.items())),
        "runtime_type_proven":False,
        "confirmed_non_sheet_sinks":0,
        "confirmed_sheet_sinks":0,
        "compiled_or_executed_css":False,
        "release_authorized":False,
    }
