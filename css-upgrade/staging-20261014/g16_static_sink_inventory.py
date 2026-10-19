"""Read-only, aggregate-only AST sink inventory for a PRIVATE CSS server source.

Never imports target modules, executes target functions, emits source text,
customer data, credential values, filenames or function names to logs.
This is a conservative candidate inventory, not proof of full sink coverage.
"""
from __future__ import annotations

import ast
import collections
import hashlib
import json
import os
from pathlib import Path

EXPECTED_DASHBOARD_SHA256 = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
CATEGORIES = {
    "sql": ("sqlite", ".execute", ".executemany", ".executescript", ".commit", ".rollback",
            "db_", "connect_db", "savepoint", "upsert", "prepare_runtime_db"),
    "sheets": ("gspread", "worksheet", "spreadsheet", "sheet_", "batch_update",
               "batch_get", "update_cells", "overwrite_dataframe", "open_by_key",
               "apply_operational_sheet_formats", "publish_system_health"),
    "mail": ("imap", "smtp", "gmail", "mail_", "mailbox", "collector",
             "sendmail", "send_message", "sync_sent", "sync_reply"),
    "crm": ("salesforce", "sfdc", "crm_", "simple_salesforce"),
    "network": ("requests.", "httpx.", "urllib.request", "urlopen",
                "socket.", "urllib3.", "aiohttp."),
    "auth": ("oauth", "credentials", "authorize", "authenticate", "token_refresh"),
    "filesystem": ("open(", ".open", ".read_text", ".read_bytes", ".write_text",
                   ".write_bytes", "shutil.", "os.replace", ".mkdir",
                   ".unlink", "backup_", "save_json", "path.write"),
    "subprocess": ("subprocess.", "os.system", "popen", "pip_install"),
    "runtime_lock": ("fcntl.", "flock", "lockfile", "filelock", "systemd"),
}
DYNAMIC = ("getattr", "setattr", "eval", "exec", "__import__", "importlib.import_module")
CODE_EXTENSIONS = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def name_of(expr: ast.AST) -> str:
    """Only an expression's callable name; no arguments or constant values."""
    if isinstance(expr, ast.Name):
        return expr.id
    if isinstance(expr, ast.Attribute):
        return name_of(expr.value) + "." + expr.attr
    if isinstance(expr, ast.Call):
        return name_of(expr.func) + "()"  # never render arguments
    return "<dynamic>"


def candidate_categories(name: str) -> set[str]:
    lower = name.lower()
    return {category for category, needles in CATEGORIES.items()
            if any(needle in lower for needle in needles)}


def walk_statements_excluding_defs(statements: list[ast.stmt]):
    """Visit expressions that execute at module import; skip function bodies."""
    for stmt in statements:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for expr in list(stmt.decorator_list) + list(stmt.args.defaults) + [
                x for x in stmt.args.kw_defaults if x is not None
            ]:
                yield from ast.walk(expr)
            continue
        if isinstance(stmt, ast.ClassDef):
            for expr in list(stmt.decorator_list) + list(stmt.bases):
                yield from ast.walk(expr)
            for member in stmt.body:
                if not isinstance(member, CODE_EXTENSIONS):
                    yield from ast.walk(member)
            continue
        if (isinstance(stmt, ast.If) and isinstance(stmt.test, ast.Compare)
            and isinstance(stmt.test.left, ast.Name)
            and stmt.test.left.id == "__name__"
            and len(stmt.test.comparators) == 1
            and isinstance(stmt.test.comparators[0], ast.Constant)
            and stmt.test.comparators[0].value == "__main__"):
            yield from ast.walk(stmt.test)
            yield from walk_statements_excluding_defs(stmt.orelse)
            continue
        yield from ast.walk(stmt)


def inventory(source: bytes) -> dict:
    tree = ast.parse(source, type_comments=False)
    functions = {n.name: n for n in tree.body
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    edges: dict[str, set[str]] = {}
    counters = collections.Counter()
    import_calls = [name_of(n.func) for n in walk_statements_excluding_defs(tree.body)
                    if isinstance(n, ast.Call)]
    for n in import_calls:
        for cat in candidate_categories(n):
            counters["import." + cat] += 1
    unknown_import = sum(not candidate_categories(n) for n in import_calls)
    for fname, fn in functions.items():
        edges[fname] = set()
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            callname = name_of(node.func)
            shortname = callname.split(".")[-1]
            if callname in functions:
                edges[fname].add(callname)
            # Approximate local calls through qualified helper wrappers.
            elif shortname in functions:
                edges[fname].add(shortname)
    reachable = set()
    frontier = ["main"] if "main" in functions else []
    while frontier:
        f = frontier.pop()
        if f in reachable:
            continue
        reachable.add(f)
        frontier.extend(edges.get(f, ()) - reachable)
    overall = collections.Counter()
    reachable_c = collections.Counter()
    exception_c = collections.Counter()
    dynamic_sites = 0
    unresolved_indirect_calls = 0
    all_call_sites = 0
    for name, fn in functions.items():
        # Catch modules with nested methods but do not pretend their reachability is proven.
        for node in ast.walk(fn):
            if not isinstance(node, ast.Call):
                continue
            all_call_sites += 1
            callname = name_of(node.func)
            cats = candidate_categories(callname)
            for cat in cats:
                overall[cat] += 1
                if name in reachable:
                    reachable_c[cat] += 1
            if callname in DYNAMIC or callname == "<dynamic>":
                dynamic_sites += 1
            if not cats and callname not in functions and callname.split(".")[-1] not in functions:
                unresolved_indirect_calls += 1
        for handler in (node for node in ast.walk(fn) if isinstance(node, ast.ExceptHandler)):
            for node in ast.walk(handler):
                if isinstance(node, ast.Call):
                    for cat in candidate_categories(name_of(node.func)):
                        exception_c[cat] += 1
    # Hash raw source only; return aggregates, never names, literals or code.
    return {
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "parsed_functions": len(functions),
        "has_main": "main" in functions,
        "reachable_helpers_approx": len(reachable),
        "all_function_call_sites": all_call_sites,
        "unknown_indirect_call_sites": unresolved_indirect_calls,
        "dynamic_call_sites": dynamic_sites,
        "module_import_call_sites": len(import_calls),
        "module_import_unclassified": unknown_import,
        "candidate_sinks_all_functions": dict(sorted(overall.items())),
        "candidate_sinks_main_reachable_approx": dict(sorted(reachable_c.items())),
        "candidate_sinks_exception_handlers": dict(sorted(exception_c.items())),
        "candidate_sinks_import_time": {k[7:]: v for k, v in sorted(counters.items())},
        "classification_is_exhaustive": False,
        "module_import_or_main_executed": False,
    }


def main() -> None:
    if os.environ.get("G16_AST_AUDIT_READONLY") != "1":
        raise SystemExit("FAIL_CLOSED_AUDIT_FLAG_REQUIRED")
    root = Path("/home/taehoon/services/novogene-css/app")
    dashboard = root / "Novogene_Mail_CSS_DashBoard_server.py"
    collector = root / "Novogene_Mail_Collector_server.py"
    if not dashboard.is_file() or not collector.is_file():
        raise SystemExit("FAIL_CLOSED_EXPECTED_SOURCE_MISSING")
    source = dashboard.read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_DASHBOARD_SHA256:
        raise SystemExit("FAIL_CLOSED_SOURCE_CHANGED")
    summaries = {
        "dashboard": inventory(source),
        "collector": inventory(collector.read_bytes()),
    }
    print("G16_AST_STATIC_AGGREGATE_BEGIN")
    print(json.dumps(summaries, ensure_ascii=True, sort_keys=True, separators=(",", ":")))
    print("G16_AST_STATIC_AGGREGATE_END")
    print("G16_NO_SOURCE_EXPORTED_NO_FUNCTION_EXECUTION")
    print("G16_FULL_SINK_COVERAGE_NOT_PROVEN")


if __name__ == "__main__":
    main()
