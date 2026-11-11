#!/usr/bin/env python3
"""Preflight for an explicitly provided CSS source bundle. Never imports or executes CSS."""
import argparse, ast, hashlib, json
from pathlib import Path

EXPECTED = "a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"

def inspect_source(path, expected=EXPECTED):
    path = Path(path)
    if not path.is_file() or path.is_symlink():
        raise ValueError("SOURCE_MISSING_OR_SYMLINK")
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected:
        raise ValueError("SOURCE_SHA_MISMATCH")
    tree = ast.parse(raw, filename=str(path))
    funcs = {node.name for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if "main" not in funcs:
        raise ValueError("MAIN_MISSING")
    return {"source_sha256": actual, "function_count": len(funcs),
            "ast_only": True, "source_executed": False, "import_executed": False}

def selftest():
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "synthetic.py"
        p.write_text("def main():\n    raise RuntimeError('MUST_NOT_RUN')\n")
        digest = hashlib.sha256(p.read_bytes()).hexdigest()
        assert inspect_source(p, digest)["source_executed"] is False
        try:
            inspect_source(p)
        except ValueError as exc:
            assert str(exc) == "SOURCE_SHA_MISMATCH"
        else:
            raise AssertionError("UNVERIFIED_SOURCE_ACCEPTED")
        p.write_text("def harmless(): pass\n")
        try:
            inspect_source(p, hashlib.sha256(p.read_bytes()).hexdigest())
        except ValueError as exc:
            assert str(exc) == "MAIN_MISSING"
        else:
            raise AssertionError("SOURCE_WITHOUT_MAIN_ACCEPTED")
        s = Path(d) / "link.py"
        s.symlink_to(p)
        try:
            inspect_source(s, hashlib.sha256(p.read_bytes()).hexdigest())
        except ValueError as exc:
            assert str(exc) == "SOURCE_MISSING_OR_SYMLINK"
        else:
            raise AssertionError("SYMLINK_ACCEPTED")
    print("CSS_SOURCE_ADMISSION_SELFTEST_PASS", flush=True)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--source")
    args = ap.parse_args()
    if args.selftest:
        selftest()
    elif args.source:
        print(json.dumps(inspect_source(args.source), sort_keys=True))
    else:
        ap.error("Use --selftest or --source. Source is never fetched automatically.")
