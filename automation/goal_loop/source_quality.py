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
    # The actual CI discovered a model returning the uppercased input
    # unchanged. An identity normalizer contains no canonical PASS/FAIL
    # output constants, and cannot satisfy V2's exact categorical contract.
    # This is only a cheap *necessary* AST check: it does not prove behavior,
    # replace independent tests or execute generated code.
    output_literals = {
        node.value for node in ast.walk(fn)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
        and node.value in ("PASS", "FAIL", "HOLD")
    }
    missing = {"PASS", "FAIL", "HOLD"} - output_literals
    if missing:
        raise SourceQualityError("V2_MISSING_CANONICAL_OUTPUTS:" + ",".join(sorted(missing)))
    return {"function": "normalize_status", "module_level_safe": True,
            "canonical_outputs_present": True,
            "ast_nodes": len(list(ast.walk(tree)))}


def validate_v3_source(source):
    """AST-only checks for one nonproduction synthetic quote summarizer.

    Never import, eval, exec or call the untrusted model-authored module here.
    A green static result does not establish behavioral correctness.
    """
    if not isinstance(source, str) or not source.strip() or len(source.encode("utf-8")) > 60000:
        raise SourceQualityError("V3_SOURCE_EMPTY_OR_OVERSIZED")
    try:
        tree = ast.parse(source, filename="pilot_quote_summary_v3.py")
    except SyntaxError as exc:
        raise SourceQualityError("V3_SOURCE_SYNTAX_ERROR") from exc
    nodes = list(ast.walk(tree))
    if len(nodes) > 1500:
        raise SourceQualityError("V3_SOURCE_AST_TOO_LARGE")
    functions = []
    for node in tree.body:
        if (isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)):
            continue  # Harmless module docstring.
        if not isinstance(node, ast.FunctionDef):
            raise SourceQualityError("V3_FORBIDDEN_MODULE_LEVEL_STATEMENT")
        functions.append(node)
    if len(functions) != 1 or functions[0].name != "summarize_quotes":
        raise SourceQualityError("V3_FUNCTION_CONTRACT")
    fn = functions[0]
    args = fn.args
    if (fn.decorator_list or args.posonlyargs or len(args.args) != 1
            or args.args[0].arg != "rows" or args.args[0].annotation is not None
            or args.vararg or args.kwarg or args.kwonlyargs or args.defaults
            or any(args.kw_defaults) or fn.returns is not None):
        raise SourceQualityError("V3_FUNCTION_SIGNATURE")
    forbidden = (ast.Import, ast.ImportFrom, ast.Global, ast.Nonlocal,
                 ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda, ast.Yield,
                 ast.YieldFrom, ast.Await)
    blocked_names = {"eval", "exec", "compile", "__import__", "open", "input",
                     "breakpoint", "getattr", "setattr", "delattr", "globals",
                     "locals", "vars"}
    blocked_attrs = {"system", "popen", "run", "Popen", "write_text",
                     "write_bytes", "read_text", "read_bytes", "unlink",
                     "remove", "rmdir", "mkdir"}
    for node in ast.walk(fn):
        if isinstance(node, forbidden):
            raise SourceQualityError("V3_FORBIDDEN_FUNCTION_CONSTRUCT")
        if isinstance(node, ast.FunctionDef) and node is not fn:
            raise SourceQualityError("V3_NESTED_FUNCTION")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id in blocked_names:
                raise SourceQualityError("V3_FORBIDDEN_DYNAMIC_CALL")
            if isinstance(node.func, ast.Attribute) and node.func.attr in blocked_attrs:
                raise SourceQualityError("V3_FORBIDDEN_SIDE_EFFECT_CALL")
        if isinstance(node, ast.Attribute) and node.attr.startswith("__"):
            raise SourceQualityError("V3_FORBIDDEN_DUNDER_ACCESS")
    if not any(isinstance(node, ast.Return) for node in ast.walk(fn)):
        raise SourceQualityError("V3_MISSING_RETURN")
    return {"function": "summarize_quotes", "module_level_safe": True,
            "ast_nodes": len(nodes)}


def main():
    parser = argparse.ArgumentParser(description="Static V2 Python source check; never import the target.")
    parser.add_argument("file", type=Path)
    args = parser.parse_args()
    validators = {
        "pilot_target_v2.py": validate_v2_source,
        "pilot_quote_summary_v3.py": validate_v3_source,
    }
    if args.file.name not in validators:
        parser.error("Only the isolated V2/V3 pilot targets are allowed")
    try:
        result = validators[args.file.name](args.file.read_text(encoding="utf-8"))
    except SourceQualityError as exc:
        parser.exit(2, "SOURCE_QUALITY_FAIL:" + str(exc) + "\n")
    print("SOURCE_QUALITY_PASS:", result["function"])


if __name__ == "__main__":
    main()
