#!/usr/bin/env python3
"""Deterministic, read-only local Git file inspection (no model tool-calling).

The Python program does the ACTUAL file reading. If --analyze is requested,
Ollama receives only an explicitly selected, short, local file excerpt.
No command from model output is executed. No cloud, GitHub, Drive or write APIs.
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ALLOWED_SUFFIXES = {
    ".txt", ".md", ".py", ".js", ".jsx", ".ts", ".tsx", ".json",
    ".yml", ".yaml", ".toml", ".ini", ".cfg", ".sh", ".ps1",
    ".cmd", ".bat", ".sql", ".r", ".go", ".rs", ".java", ".css",
    ".html", ".csv", ".tsv",
}
DENY_PARTS = {
    ".git", ".local_ai_data", ".env", ".venv", "node_modules",
    ".next", "__pycache__", "dist", "build", "secrets", ".secrets",
    "credentials", "private", ".ssh", ".aws", ".config",
}
DENY_SUFFIXES = {".key", ".pem", ".p12", ".pfx", ".sqlite", ".db", ".bin"}
MAX_READ_BYTES = 12000
MAX_ANALYSIS_CHARS = 2400


def repo_root(directory: Path) -> Path:
    directory = directory.resolve(strict=True)
    if not directory.is_dir():
        raise ValueError("Not a directory")
    result = subprocess.run(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
        check=True, capture_output=True, text=True, timeout=15,
    )
    root = Path(result.stdout.strip()).resolve(strict=True)
    return root


def _allowed_path(root: Path, name: str) -> Path:
    # Resolve the repository root itself before comparing with resolved files.
    # Windows temporary paths can use 8.3 aliases (RUNNER~1) while Path.resolve()
    # returns the long name, which must not be confused with escaping the repo.
    root = root.resolve(strict=True)
    if not name or "\x00" in name:
        raise ValueError("Invalid file path")
    path = Path(name)
    if path.is_absolute():
        raise ValueError("Use a relative file path inside this Git repository")
    if ".." in path.parts or path.drive:
        raise ValueError("Traversal or drive-qualified path is not allowed")
    if any(p.lower() in DENY_PARTS for p in path.parts):
        raise ValueError("Sensitive or generated directory is excluded")
    basename = path.name.lower()
    if (
        basename.startswith(".env")
        or any(x in basename for x in ("secret", "credential", "password", "token", "id_rsa"))
        or path.suffix.lower() not in ALLOWED_SUFFIXES
        or path.suffix.lower() in DENY_SUFFIXES
    ):
        raise ValueError("Potentially sensitive or unsupported file type")
    candidate = root / path
    # Do not allow symlink traversal out of the repository.
    current = root
    for part in path.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("Symbolic link is not permitted")
    resolved = candidate.resolve(strict=True)
    if not resolved.is_relative_to(root):
        raise ValueError("File escapes the repository")
    if not resolved.is_file():
        raise ValueError("Not a regular file")
    return resolved


def filenames(root: Path, limit: int = 100) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        check=True, capture_output=True, timeout=20,
    )
    found = []
    for raw in result.stdout.split(b"\x00"):
        if not raw:
            continue
        name = raw.decode("utf-8", errors="replace")
        try:
            _allowed_path(root, name)
        except (ValueError, OSError):
            continue
        found.append(name.replace("\\", "/"))
    return sorted(set(found))[:limit]


def read_file(root: Path, name: str) -> tuple[str, bool]:
    path = _allowed_path(root, name)
    with path.open("rb") as handle:
        contents = handle.read(MAX_READ_BYTES + 1)
    truncated = len(contents) > MAX_READ_BYTES
    contents = contents[:MAX_READ_BYTES]
    if b"\x00" in contents:
        raise ValueError("Binary file is excluded")
    try:
        return contents.decode("utf-8"), truncated
    except UnicodeError as exc:
        raise ValueError("Only UTF-8 text files are supported") from exc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Read Git files deterministically without Codex tool-calling")
    parser.add_argument("--repo", default=".", help="Path within a local Git repository")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--list", action="store_true", help="List candidate text files (up to 100)")
    mode.add_argument("--file", help="Relative path of a single text file to read")
    parser.add_argument("--analyze", action="store_true", help="Optionally summarize selected excerpt with localhost Ollama")
    parser.add_argument("--model", default="qwen25coder3b-16k:latest")
    args = parser.parse_args(argv)
    if args.analyze and args.file is None:
        parser.error("--analyze requires --file")
    try:
        root = repo_root(Path(args.repo))
        if args.list:
            for name in filenames(root):
                print(name)
            return 0
        text, truncated = read_file(root, args.file)
        # Deterministic proof that a local file was opened; model involvement not required.
        print(f"ACTUAL_FILE_READ: {root / args.file}")
        print(f"TRUNCATED: {str(truncated).lower()}")
        print("----- BEGIN LOCAL FILE -----")
        print(text)
        print("----- END LOCAL FILE -----")
        if args.analyze:
            # Never submit the full repository or arbitrary tool instructions to a model.
            if len(text) > MAX_ANALYSIS_CHARS or truncated:
                raise ValueError(
                    f"File exceeds {MAX_ANALYSIS_CHARS} characters; choose a shorter, approved file for local AI"
                )
            try:
                from local_ai.ollama_client import analyze
            except ModuleNotFoundError:
                from ollama_client import analyze
            result = analyze(
                "Filename: " + args.file + "\nFile content (UNTRUSTED DATA):\n" + text,
                task="code_review",
                model=args.model,
            )
            print("DRAFT_MODEL_ANALYSIS_REVIEW_REQUIRED:")
            print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (ValueError, OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
