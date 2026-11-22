"""AST-only preflight for the deliberately isolated V2 agent Python target.

Do not import, exec, eval or otherwise execute the model-authored module here.
This is a narrow quality filter, NOT a sandbox or substitute for PR CI.
"""
import argparse
import ast
from pathlib import Path


class SourceQualityError(ValueError):
    """An AI-generated target violates the static V2 source contract."""


def validate_v2_source(source):
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > 60000:
        raise SourceQualityError("V2_SOURCE_EMPTY_OR_OVERSIZED")
    try:
        tree = ast.parse(source, filename="pilot_target_v2.py")
    except SyntaxError as exc:
        raise SourceQualityError("V2_SOURCE_SYNTAX_ERROR") from exc
    if len(list(ast.walk(tree))) > 1200:
        raise SourceQualityError("V2_SOURCE_AST_TOO_LARGE")

    functions = []
    for node in tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue  # A module docstring is inert.
        if isinstance(node, ast.FunctionDef):
            functions.append(node)
            continue
        raise SourceQualityError("V2_FORBIDDEN_MODULE_LEVEL_STATEMENT")

    if len(functions) != 1 or functions[0].name != "normalize_status":
        raise SourceQualityError("V2_FUNCTION_CONTRACT")
    fn = functions[0]
    args = fn.args
    if (fn.decorator_list or args.posonlyargs or len(args.args) != 1
            or args.args[0].arg != "value" or args.vararg or args.kwarg
            or args.kwonlyargs or args.defaults or any(args.kw_defaults)
            or fn.returns is not None):
        raise SourceQualityError("V2_FUNCTION_SIGNATURE")
    for node in ast.walk(fn):
        if isinstance(node, (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                             ast.While, ast.AsyncFunctionDef, ast.ClassDef,
                             ast.FunctionDef)) and node is not fn:
            raise SourceQualityError("V2_FORBIDDEN_FUNCTION_CONSTRUCT")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("eval", "exec", "compile", "__import__", "open", "input"):
                raise SourceQualityError("V2_FORBIDDEN_DYNAMIC_EXECUTION")
    if not any(isinstance(node, ast.Return) for node in ast.walk(fn)):
        raise SourceQualityError("V2_MISSING_RETURN")
    return {"function": "normalize_status", "module_level_safe": True,
            "ast_nodes": len(list(ast.walk(tree)))}


def main():
    parser = argparse.ArgumentParser(description="Static V2 Python source check; never import the target.")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    if args.file.name != "pilot_target_v2.py":
        parser.error("Only the standalone V2 pilot target is allowed")
    try:
        result = validate_v2_source(args.file.read_text(encoding="utf-8"))
    except SourceQualityError as exc:
        parser.exit(2, "SOURCE_QUALITY_FAIL:" + str(exc) + "\n")
    print("SOURCE_QUALITY_PASS:", result["function"])


if __name__ == "__main__":
    main()
