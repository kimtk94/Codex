#!/usr/bin/env python3
"""Fail-closed AST admission for selected CSS functions. No import, exec or production writes."""
import argparse, ast, hashlib, json
from pathlib import Path

SOURCE_SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
ALLOWED=("load_active_contract_sif_skips","collect_active_prepayment_project_ids",
         "build_contract_sif_skip_history","split_contract_sif_active_and_skipped",
         "build_action_center_output","build_review_queue_output")
BLOCKED_CALLS={"exec","eval","compile","__import__","subprocess.run","os.system",
               "sqlite3.connect","requests.post","smtplib.SMTP","gspread.authorize"}

def inventory(raw, expected=SOURCE_SHA):
    if hashlib.sha256(raw).hexdigest()!=expected: raise ValueError("CSS_SOURCE_SHA_MISMATCH")
    root=ast.parse(raw)
    found={}
    for node in root.body:
        if isinstance(node,(ast.FunctionDef,ast.AsyncFunctionDef)) and node.name in ALLOWED:
            if node.name in found: raise ValueError("DUPLICATE_FUNCTION_"+node.name)
            if not isinstance(node,ast.FunctionDef) or node.decorator_list:
                raise ValueError("UNSAFE_DEFINITION_"+node.name)
            # Function defaults, annotations and decorators may execute during def creation.
            defaults=list(node.args.defaults)+[x for x in node.args.kw_defaults if x is not None]
            for default in defaults:
                try:
                    ast.literal_eval(default)
                except (ValueError,TypeError,MemoryError,RecursionError):
                    raise ValueError("UNSAFE_DEFAULT_"+node.name) from None
            if node.returns is not None or any(a.annotation is not None for a in
                   node.args.posonlyargs+node.args.args+node.args.kwonlyargs) or (
                   node.args.vararg is not None and node.args.vararg.annotation is not None) or (
                   node.args.kwarg is not None and node.args.kwarg.annotation is not None):
                raise ValueError("UNSAFE_ANNOTATION_"+node.name)
            calls={ast.unparse(n.func) for n in ast.walk(node) if isinstance(n,ast.Call)}
            found[node.name]={"line":node.lineno,"call_count":len(calls),
                              "blocked_call_names":sorted(calls & BLOCKED_CALLS),
                              "body_sha256":hashlib.sha256(ast.dump(node,include_attributes=False).encode()).hexdigest()}
    if set(found)!=set(ALLOWED): raise ValueError("MISSING_FUNCTIONS:"+",".join(sorted(set(ALLOWED)-set(found))))
    if any(v["blocked_call_names"] for v in found.values()):
        raise ValueError("DIRECT_BLOCKED_CALLS_DETECTED")
    return {"admission":"STATIC_AST_ONLY","source_sha256":expected,"selected_count":len(found),
            "source_imported":False,"functions_executed":False,"functions":found}

def selftest():
    body="\n".join(f"def {name}(x):\n    return x\n" for name in ALLOWED).encode()
    digest=hashlib.sha256(body).hexdigest()
    assert inventory(body,digest)["selected_count"]==len(ALLOWED)
    safe=body.replace(b"(x):",b"(x=None):",1)
    assert inventory(safe,hashlib.sha256(safe).hexdigest())["selected_count"]==len(ALLOWED)
    cases=[(body,b"wrong".hex(),"CSS_SOURCE_SHA_MISMATCH"),
           (body.replace(b"return x",b"return eval('1')",1),None,"DIRECT_BLOCKED_CALLS_DETECTED"),
           (body.replace(b"def "+ALLOWED[0].encode()+b"(x):",b"def "+ALLOWED[0].encode()+b"(x=eval(1)):"),None,"UNSAFE_DEFAULT_")]
    for raw,wrong,expected_error in cases:
        try: inventory(raw,wrong or hashlib.sha256(raw).hexdigest())
        except ValueError as ex: assert str(ex).startswith(expected_error),(ex,expected_error)
        else: raise AssertionError("FAIL_OPEN_"+expected_error)
    print("CSS_SELECTED_FUNCTION_STATIC_ADMISSION_PASS",flush=True)

if __name__=="__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--selftest",action="store_true")
    ap.add_argument("--source")
    args=ap.parse_args()
    if args.selftest: selftest()
    elif args.source:
        p=Path(args.source)
        if p.is_symlink() or not p.is_file(): raise SystemExit("SOURCE_PATH_DENIED")
        print(json.dumps(inventory(p.read_bytes()),ensure_ascii=False,sort_keys=True))
    else: ap.error("Supply --selftest or --source")
