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


def triage_local_receivers(raw):
    """Syntactic hints only; never claim actual receiver type or Sheet safety."""
    import ast
    from collections import Counter
    from g12_css_ast_guard_v2 import SHEET_METHODS, SHEET_HINTS, _name
    stats=Counter()
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope=[]
        def visit_FunctionDef(self,node):
            self.scope.append(node)
            self.generic_visit(node)
            self.scope.pop()
        visit_AsyncFunctionDef=visit_FunctionDef
        def visit_Call(self,node):
            if isinstance(node.func,ast.Attribute) and node.func.attr in SHEET_METHODS:
                receiver=node.func.value
                if not any(h in _name(receiver).lower() for h in SHEET_HINTS):
                    shape=type(receiver).__name__
                    hint=shape.upper()+"_UNRESOLVED"
                    if isinstance(receiver,ast.Name) and self.scope:
                        fn=self.scope[-1]
                        args=fn.args
                        params={a.arg for a in args.posonlyargs+args.args+args.kwonlyargs}
                        if args.vararg:params.add(args.vararg.arg)
                        if args.kwarg:params.add(args.kwarg.arg)
                        if receiver.id in params:
                            hint="FUNCTION_PARAMETER_UNRESOLVED"
                        else:
                            assignments=[
                                stmt.value for stmt in fn.body
                                if isinstance(stmt,ast.Assign)
                                for target in stmt.targets
                                if isinstance(target,ast.Name) and target.id==receiver.id
                            ]
                            if len(assignments)==1:
                                value=assignments[0]
                                if isinstance(value,ast.Dict):
                                    hint="LOCAL_DICT_LITERAL_HINT"
                                elif isinstance(value,ast.List):
                                    hint="LOCAL_LIST_LITERAL_HINT"
                                elif isinstance(value,ast.DictComp):
                                    hint="LOCAL_DICT_COMPREHENSION_HINT"
                                elif isinstance(value,ast.ListComp):
                                    hint="LOCAL_LIST_COMPREHENSION_HINT"
                                elif isinstance(value,ast.Call):
                                    hint="LOCAL_CALL_ASSIGNMENT_UNRESOLVED"
                                else:
                                    hint="NAME_OTHER_ASSIGNMENT_UNRESOLVED"
                            else:
                                hint="NAME_NO_UNIQUE_DIRECT_ASSIGNMENT"
                    stats[node.func.attr+":"+hint]+=1
            self.generic_visit(node)
    Visitor().visit(ast.parse(raw))
    return dict(sorted(stats.items()))

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
    triage=triage_local_receivers(raw)
    if sum(triage.values()) != summary["unknown_writer_candidates"]:
        raise SystemExit("G12_TRIAGE_COVERAGE_MISMATCH")
    result={
        "source_sha256":summary["source_sha256"],
        "in_memory_compile":"PASS",
        "instrumented_calls":summary["known_writer_calls_instrumented"],
        "unclassified_candidate_calls":summary["unknown_writer_candidates"],
        "unclassified_method_counts":summary["unknown_method_counts"],
        "unclassified_receiver_shapes":summary["unknown_receiver_shapes"],
        "unclassified_local_hints":triage,
        "local_hints_are_runtime_proof":False,
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
