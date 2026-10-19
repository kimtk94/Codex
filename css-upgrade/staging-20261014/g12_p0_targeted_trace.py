"""Read-only targeted AST provenance for selected G12 P0 call sites.

Outputs sanitized structural findings only; never source text, private
identifiers, string literals or executed CSS module behavior.
"""
import ast
from collections import Counter

TARGET_LINES={19275,5108,5116,8417,8420}
def analyze(raw):
    tree=ast.parse(raw)
    parents={c:p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    funcs={n.name:n for n in tree.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
    report=[]
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call) or node.lineno not in TARGET_LINES:
            continue
        if not isinstance(node.func,ast.Attribute) or node.func.attr not in ("sort","update"):
            continue
        recv=node.func.value
        scope=node
        while scope in parents and not isinstance(scope,(ast.FunctionDef,ast.AsyncFunctionDef)):
            scope=parents[scope]
        kind="UNKNOWN"
        definitions=0
        return_shapes=Counter()
        if isinstance(recv,ast.Name) and isinstance(scope,(ast.FunctionDef,ast.AsyncFunctionDef)):
            bindings=[]
            for stmt in ast.walk(scope):
                if isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id==recv.id for t in stmt.targets):
                    bindings.append(stmt.value)
            definitions=len(bindings)
            if len(bindings)==1 and isinstance(bindings[0],ast.List):kind="DIRECT_LIST_ASSIGNMENT"
            elif len(bindings)>1:kind="MULTIPLE_ASSIGNMENTS"
            elif len(bindings)==0:kind="NO_SIMPLE_ASSIGNMENT"
            else:kind="OTHER_ASSIGNMENT"
        elif isinstance(recv,ast.Call):
            kind="CALL_RESULT"
            if isinstance(recv.func,ast.Name):
                callee=funcs.get(recv.func.id)
                if callee:
                    for r in ast.walk(callee):
                        if isinstance(r,ast.Return):
                            return_shapes[type(r.value).__name__ if r.value is not None else "None"]+=1
        report.append({"line":node.lineno,"method":node.func.attr,
                       "receiver_category":kind,"simple_assignments":definitions,
                       "callee_return_expression_shapes":dict(return_shapes),
                       "runtime_type_proven":False,"sheet_target_proven":False})
    report.sort(key=lambda x:x["line"])
    return {"selected_sites":report,"site_count":len(report),
            "source_executed":False,"safe_sites_confirmed":0,
            "release_authorized":False}
