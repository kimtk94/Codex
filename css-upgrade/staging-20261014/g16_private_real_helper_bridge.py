"""Private G16 helper bridge; run ONLY inside the rootless Bubblewrap sandbox.

Source is a read-only bind-mounted private server file. NEVER import the CSS
module or collector, call main(), copy source, or emit code, inputs or values.
The public repository contains only this synthetic-only test harness.
"""
from __future__ import annotations

import ast
import builtins
import copy
import hashlib
import os
from pathlib import Path
import re

EXPECTED_SHA = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
SOURCE = Path("/private/css.py")
TARGETS = ("clean_text", "normalize_text", "checkbox_is_checked",
           "canonical_sif_project_id", "stable_record_id")
SAFE_BUILTINS = {
    k: getattr(builtins, k) for k in
    ("str", "bool", "int", "float", "len", "any", "all", "min", "max",
     "isinstance", "tuple", "list", "dict", "set", "sorted", "abs", "round")
}
SAFE_CALLS = {
    "str", "bool", "int", "float", "len", "any", "all", "min", "max",
    "isinstance", "tuple", "list", "dict", "set", "sorted", "abs", "round",
    "clean_text", "normalize_text", "checkbox_is_checked",
    "canonical_sif_project_id", "stable_record_id",
    "re.search", "re.match", "re.fullmatch", "re.compile",
    "hashlib.md5", "hashlib.sha256",
    "str.strip", "str.lower", "str.upper",
}
SAFE_ATTRIBUTES = {
    "strip", "lower", "upper", "replace", "split", "startswith",
    "endswith", "group", "find", "join", "encode", "hexdigest",
    "isdigit", "isnumeric", "casefold", "get", "groups",
}
BANNED = (
    ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal, ast.With,
    ast.AsyncWith, ast.Raise, ast.Try, ast.Delete, ast.Await,
    ast.Yield, ast.YieldFrom, ast.NamedExpr, ast.Lambda, ast.ClassDef,
)

def callable_name(value: ast.AST) -> str:
    if isinstance(value, ast.Name):
        return value.id
    if isinstance(value, ast.Attribute):
        if value.attr not in SAFE_ATTRIBUTES and not (
            isinstance(value.value, ast.Name) and
            value.value.id in ("re", "hashlib")
        ):
            return "<unknown>"
        return (callable_name(value.value) + "." + value.attr
                if isinstance(value.value, ast.Name) else "<method>")
    return "<method>" if isinstance(value, ast.Call) else "<unknown>"


def safe_function(func: ast.FunctionDef) -> bool:
    if func.decorator_list:
        return False
    if any(not isinstance(value, ast.Constant)
           for value in list(func.args.defaults) +
           [v for v in func.args.kw_defaults if v is not None]):
        return False
    for child in ast.walk(func):
        if isinstance(child, BANNED):
            return False
        # A non-called attribute can leak Python internals just as a method can.
        # Only explicitly enumerated methods and direct approved module calls
        # are eligible; reject every dunder and unknown attribute expression.
        if isinstance(child, ast.Attribute):
            explicit = (isinstance(child.value, ast.Name) and
                        child.value.id in ("re", "hashlib") and
                        child.value.id + "." + child.attr in SAFE_CALLS)
            if child.attr not in SAFE_ATTRIBUTES and not explicit:
                return False
            if child.attr.startswith("_"):
                return False
        if isinstance(child, ast.Call):
            n = callable_name(child.func)
            if not (n in SAFE_CALLS or
                    (n == "<method>" and isinstance(child.func, ast.Attribute)
                     and child.func.attr in SAFE_ATTRIBUTES)):
                return False
    return True


def stripped_copy(func: ast.FunctionDef) -> ast.FunctionDef:
    value = copy.deepcopy(func)
    value.decorator_list = []
    value.returns = None
    for arg in (value.args.posonlyargs + value.args.args +
                value.args.kwonlyargs + ([value.args.vararg] if value.args.vararg else []) +
                ([value.args.kwarg] if value.args.kwarg else [])):
        arg.annotation = None
    return value


def check(cond: bool, marker: str) -> None:
    if not cond:
        raise RuntimeError("G16_PRIVATE_REAL_HELPER_FAILED_" + marker)
    print("G16_PRIVATE_REAL_HELPER_PASS_" + marker)


def main() -> None:
    check(os.environ.get("G16_SYNTHETIC_ONLY") == "1", "SYNTHETIC_MODE")
    check(not Path("/home/taehoon").exists(), "PRODUCTION_HOME_HIDDEN")
    check(not Path("/root").exists(), "ROOT_HOME_HIDDEN")
    check(SOURCE.is_file(), "READONLY_SOURCE_MOUNT")
    original = SOURCE.read_bytes()
    check(hashlib.sha256(original).hexdigest() == EXPECTED_SHA, "SOURCE_SHA")
    tree = ast.parse(original)
    names = {node.name: node for node in tree.body if isinstance(node, ast.FunctionDef)}
    vetted = {name: names[name] for name in TARGETS
              if name in names and safe_function(names[name])}
    print("G16_PRIVATE_HELPERS_PRESENT", sum(x in names for x in TARGETS))
    print("G16_PRIVATE_HELPERS_STATIC_ALLOWLISTED", len(vetted))
    for name in TARGETS:
        node = names.get(name)
        if node is None:
            continue
        print("G16_PRIVATE_HELPER_STATIC_ELIGIBLE_" + name.upper(), name in vetted)
        roots = {}
        for call in (n for n in ast.walk(node) if isinstance(n, ast.Call)):
            callname = callable_name(call.func)
            root = callname.split(".")[0] if "." in callname else callname
            category = (root if root in ("pd", "re", "hashlib", "unicodedata", "datetime", "json")
                        else ("safe_builtin" if root in SAFE_BUILTINS else
                              "local_helper" if root in TARGETS else "other"))
            roots[category] = roots.get(category, 0) + 1
        print("G16_PRIVATE_HELPER_DEPENDENCY_CLASSES_" + name.upper(),
              ",".join(k + ":" + str(v) for k, v in sorted(roots.items())))
    namespace = {"__builtins__": SAFE_BUILTINS, "re": re, "hashlib": hashlib}
    for value in vetted.values():
        node = stripped_copy(value)
        ast.fix_missing_locations(node)
        exec(compile(ast.Module(body=[node], type_ignores=[]),
                     "private-pure-helper-ast", "exec"), namespace)
    passing = 0
    for name, args, condition in [
        ("clean_text", ("  TEST-A  ",), lambda x: x == "TEST-A"),
        ("normalize_text", ("  TesT-A  ",), lambda x: x == "test-a"),
        ("checkbox_is_checked", ("TRUE",), lambda x: bool(x)),
        ("canonical_sif_project_id", ("AMEA2026100001",),
         lambda x: x == "AMEA2026100001"),
    ]:
        if name not in vetted:
            print("G16_PRIVATE_REAL_HELPER_UNVERIFIED_" + name.upper())
            continue
        try:
            result = namespace[name](*args)
            success = condition(result)
        except Exception as e:
            print("G16_PRIVATE_HELPER_EXCEPTION_KIND_" + name.upper(), type(e).__name__)
            success = False
        if success:
            check(True, name.upper())
            passing += 1
        else:
            print("G16_PRIVATE_REAL_HELPER_UNVERIFIED_" + name.upper())
    check(passing >= 2, "MINIMUM_TWO_PURE_HELPERS")
    # Do not treat two unrelated passing helpers as proof that the
    # adapter entrypoint itself was verified.
    check("clean_text" in vetted and
          "clean_text" in namespace and
          passing >= 2,
          "REAL_TRANSFORM_CONTRACT_VERIFIED")

    # Connect a SHA-vetted *real extracted helper* to the strict, synthetic
    # Sheets adapter. No production ID or data is passed to any adapter.
    from g16_mock_ports import PortBundle
    from g16_synthetic_pipeline import SyntheticMail
    root = Path("/tmp/g16_real_helper_probe")
    root.mkdir(mode=0o700)
    bundle = PortBundle(
        [SyntheticMail("test:a", "synthetic:a", "TEST-A", "SIF requested")],
        {"TEST-A": "synthetic-inquiry"}, root)
    label = namespace["clean_text"]("  TEST-A  ")
    check(label == "TEST-A", "REAL_TO_MOCK_TRANSFORM")
    check(bundle.sheets.publish(((label, "SIF requested", 1, ""),),
                                ((label, "CRM_INQUIRY"),)),
          "REAL_TO_MOCK_SHEET_PUBLISH")
    check(bundle.sheets.writes == 1, "FAKE_SHEET_ONLY")
    print("G16_PRIVATE_REAL_HELPERS_TESTED", passing)
    print("G16_FULL_MAIN_NOT_EXECUTED")
    print("G16_G12_REMAINS_NOT_RUN")
    print("G16_NO_REAL_SHEETS_DB_MAIL_CRM_WRITES")


if __name__ == "__main__":
    main()
