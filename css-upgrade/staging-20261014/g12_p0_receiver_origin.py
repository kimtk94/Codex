"""Read-only P0 16-site receiver origin hints. No private source output."""
import ast
from collections import Counter
from g12_v2_review_queue import build_queue, _scope_of
from g12_css_ast_guard_v2 import _name

def inspect_p0(raw):
    tree=ast.parse(raw)
    queue=build_queue(raw)
    target={(r["line"],r["method"]) for r in queue["review_queue"] if r["priority"].startswith("P0")}
    parents={c:p for p in ast.walk(tree) for c in ast.iter_child_nodes(p)}
    results=[]
    for call in ast.walk(tree):
        if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Attribute):
            continue
        key=(call.lineno,call.func.attr)
        if key not in target:continue
        receiver=call.func.value
        fn=_scope_of(call,parents)
        evidence="UNRESOLVED"
        if isinstance(receiver,ast.Name) and fn:
            stores=[]
            for n in ast.walk(fn):
                if isinstance(n,ast.Name) and n.id==receiver.id and isinstance(n.ctx,(ast.Store,ast.Del)):
                    stores.append(n)
            if len(stores)==1:
                for stmt in ast.walk(fn):
                    if isinstance(stmt,ast.Assign) and any(isinstance(t,ast.Name) and t.id==receiver.id for t in stmt.targets):
                        if isinstance(stmt.value,ast.List):evidence="SINGLE_LIST_LITERAL_ASSIGNMENT"
                        elif isinstance(stmt.value,ast.Dict):evidence="SINGLE_DICT_LITERAL_ASSIGNMENT"
                        elif isinstance(stmt.value,ast.Call):evidence="SINGLE_CALL_ASSIGNMENT"
                        break
            elif len(stores)>1:evidence="MULTIPLE_BINDINGS"
        elif isinstance(receiver,ast.Call):
            evidence="DIRECT_CALL_RETURN"
        elif isinstance(receiver,ast.Subscript):
            evidence="INDEXED_OBJECT"
        results.append({"line":call.lineno,"method":call.func.attr,"origin_hint":evidence,"runtime_type_proven":False,"sheet_destination_proven":False})
    results.sort(key=lambda x:x["line"])
    if len(results)!=len(target):
        raise ValueError("P0_REVIEW_PARITY_FAILED")
    return {"p0_sites":results,"counts":dict(Counter(x["origin_hint"] for x in results)),
            "all_receiver_types_proven":False,"all_sheet_targets_proven":False,
            "source_executed":False,"release_authorized":False}
