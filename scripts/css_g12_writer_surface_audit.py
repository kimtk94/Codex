"""G12 read-only AST audit of CSS Sheets writer call sites.

Do not import or run production CSS. Emits bounded method classifications and
source line numbers but never source text, call arguments, or private values.
It is conservative: a callsite candidate is not proof of a real write and
absence of findings does not establish isolation or user-field safety.
"""
from __future__ import annotations

import ast
import collections
import hashlib
import json
import os
from pathlib import Path

SOURCE = Path("/home/taehoon/services/novogene-css/app/Novogene_Mail_CSS_DashBoard_server.py")
EXPECTED_SHA256 = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
CONTROL_TABS = (
    "CSS Project Dashboard",
    "CSS Contract-SIF Tracker",
    "CSS Contract-SIF Skipped",
    "CSS Manual Exclusions",
)
CONTROL_IDENTIFIERS = frozenset({
    "df_dashboard", "df_dashboard_portfolio", "df_sample_intake",
    "df_sample_intake_skipped", "df_manual_exclusions",
    "SAMPLE_INTAKE_SHEET_NAME", "SAMPLE_INTAKE_SKIPPED_SHEET_NAME",
    "DASHBOARD_SHEET_NAME", "MANUAL_EXCLUSIONS_SHEET_NAME",
})
# These are candidate API methods or helper conventions, not conclusive proof.
METHODS = frozenset({
    "overwrite_dataframe", "set_with_dataframe", "update_cells",
    "batch_update", "batch_clear", "clear", "resize", "sort",
    "insert_rows", "delete_rows", "append_rows", "update",
    "update_dataframe", "write_dataframe", "write_dataframe_to_sheet",
    "sync_dataframe_to_sheet", "write_sheet", "update_sheet",
    "format", "batch_format",
})
STRUCTURAL = frozenset({
    "batch_clear", "clear", "resize", "sort", "insert_rows",
    "delete_rows", "set_with_dataframe", "overwrite_dataframe",
})
APPEND = frozenset({"append_rows"})
AMBIGUOUS = frozenset({"update", "clear", "sort", "format", "resize", "batch_update"})
SHEET_HINTS = ("ws", "sheet", "spread", "worksheet", "gspread")


def function_path(node):
    """Attribute call shape only. Literal expressions are never rendered."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = function_path(node.value)
        return (left + "." if left else "") + node.attr
    return ""


def identifier_refs(call):
    refs = set()
    for value in (*call.args, *(kw.value for kw in call.keywords)):
        for n in ast.walk(value):
            if isinstance(n, ast.Name) and n.id in CONTROL_IDENTIFIERS:
                refs.add(n.id)
    return sorted(refs)


def extract(source: bytes):
    tree = ast.parse(source, type_comments=False)
    sites = []
    counters = collections.Counter()
    class Visitor(ast.NodeVisitor):
        def __init__(self):
            self.scope = []
        def visit_FunctionDef(self, node):
            self.scope.append("main" if node.name == "main" else "helper")
            self.generic_visit(node)
            self.scope.pop()
        visit_AsyncFunctionDef = visit_FunctionDef

        def visit_Call(self, node):
            name = function_path(node.func)
            method = name.rsplit(".", 1)[-1]
            if method in METHODS:
                # Generic dict.update/sort/format must not be called a Sheet
                # writer unless their call surface contains a Sheets hint.
                if method not in AMBIGUOUS or any(h in name.lower() for h in SHEET_HINTS):
                    scope = self.scope[-1] if self.scope else "import"
                    kind = (
                        "DESTRUCTIVE_OR_FULL_REWRITE_CANDIDATE" if method in STRUCTURAL
                        else "STRUCTURAL_APPEND_CANDIDATE" if method in APPEND
                        else "API_EFFECT_UNKNOWN"
                    )
                    counters[kind] += 1
                    sites.append({
                        "line": node.lineno, "scope": scope,
                        "method": method, "risk": kind,
                        "known_frame_refs": identifier_refs(node),
                    })
            self.generic_visit(node)

    Visitor().visit(tree)
    return {
        "source_sha256": hashlib.sha256(source).hexdigest(),
        "parsed": True,
        "candidate_count": len(sites),
        "risk_counts": dict(sorted(counters.items())),
        "sites": sorted(sites, key=lambda r: (r["line"], r["method"]))[:150],
        "sites_truncated": len(sites) > 150,
        "high_risk_sheet_protection_proven": False,
        "actual_writer_ranges_proven": False,
        "production_source_executed": False,
        "source_text_exposed": False,
    }


def main():
    if os.environ.get("CSS_G12_STATIC_READONLY") != "1":
        raise SystemExit("AUDIT_FLAG_REQUIRED")
    source = SOURCE.read_bytes()
    if hashlib.sha256(source).hexdigest() != EXPECTED_SHA256:
        raise SystemExit("SOURCE_SHA_MISMATCH_FAIL_CLOSED")
    print("G12_WRITER_SURFACE_AUDIT_BEGIN")
    print(json.dumps(extract(source), sort_keys=True, separators=(",", ":")))
    print("G12_WRITER_SURFACE_AUDIT_END")
    print("G12_NO_SOURCE_EXECUTED_OR_MODIFIED")


if __name__ == "__main__":
    main()
