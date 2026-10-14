"""Fail-closed boundary primitives for Novogene CSS *synthetic* canary checks.

This module does NOT run CSS main(), import the collector, or authorize production.
It is a policy / test harness, not a complete OS/network sandbox.
"""
from __future__ import annotations

import ast
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import FrozenSet, Mapping


class IsolationViolation(RuntimeError):
    """Any potential route to a production resource must abort."""


RISKY_IMPORT_CALLS = frozenset({
    "subprocess.run", "subprocess.check_call", "sqlite3.connect",
    "gspread.authorize", "publish_mail_state_to_drive",
    "imaplib.IMAP4_SSL", "smtplib.SMTP", "smtplib.SMTP_SSL",
})


def audit_import_time_calls(source: str) -> tuple[str, ...]:
    """Parse source without importing it; flag unsafe module-level calls."""
    tree = ast.parse(source)
    found = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        # The canonical __name__ guard is not evaluated when imported.
        if isinstance(node, ast.If) and any(
            isinstance(x, ast.Name) and x.id == "__name__"
            for x in ast.walk(node.test)
        ):
            continue
        for call in ast.walk(node):
            if not isinstance(call, ast.Call):
                continue
            try:
                name = ast.unparse(call.func)
            except Exception:
                continue
            if name in RISKY_IMPORT_CALLS:
                found.add(name)
    return tuple(sorted(found))


def refuse_unsafe_import(module_source: str) -> None:
    risks = audit_import_time_calls(module_source)
    if risks:
        raise IsolationViolation("module import refused: " + ",".join(risks))


@dataclass(frozen=True)
class CanaryPolicy:
    root: Path
    canary_sheet_id: str
    forbidden_sheet_ids: FrozenSet[str]
    paths: Mapping[str, Path]
    allowed_tabs: FrozenSet[str]
    network_mail_disabled: bool
    external_drive_writes_disabled: bool
    salesforce_writes_disabled: bool

    def validate(self) -> None:
        root = Path(self.root).resolve()
        temp_root = Path(tempfile.gettempdir()).resolve()
        if root == temp_root or not root.is_relative_to(temp_root):
            raise IsolationViolation("isolated root must be a dedicated temporary subdirectory")
        if not root.is_dir() or root.is_symlink():
            raise IsolationViolation("isolated root must exist and must not be a symlink")
        canary = str(self.canary_sheet_id).strip()
        if not canary or canary in self.forbidden_sheet_ids:
            raise IsolationViolation("canary spreadsheet collides with production")
        if len(self.allowed_tabs) == 0:
            raise IsolationViolation("no synthetic tabs allowlisted")
        if not all((self.network_mail_disabled, self.external_drive_writes_disabled,
                    self.salesforce_writes_disabled)):
            raise IsolationViolation("external writes are not disabled")
        mandatory = {"project_db", "mail_db", "backup_dir", "log_dir", "output_dir"}
        if set(self.paths) != mandatory:
            raise IsolationViolation("every persistent output path must be isolated")
        seen = set()
        for name, item in self.paths.items():
            path = Path(item)
            resolved = path.resolve(strict=False)
            if resolved == root or not resolved.is_relative_to(root):
                raise IsolationViolation(f"unsafe path: {name}")
            if resolved in seen:
                raise IsolationViolation("two sinks share a file or directory")
            seen.add(resolved)
            if path.is_symlink():
                raise IsolationViolation(f"symlink sink: {name}")
        for name in ("project_db", "mail_db"):
            path = Path(self.paths[name])
            if not path.is_file() or path.stat().st_size < 1:
                raise IsolationViolation(f"missing isolated input DB: {name}")

    def allow_sheet(self, sheet_id: str) -> bool:
        self.validate()
        if sheet_id != self.canary_sheet_id:
            raise IsolationViolation("spreadsheet ID not allowlisted")
        return True

    def allow_tab(self, tab: str) -> bool:
        if tab not in self.allowed_tabs:
            raise IsolationViolation("tab not allowlisted")
        return True


class AllowlistedSheetsClient:
    """Minimal wrapper for *selected function tests*; never for whole main()."""

    def __init__(self, raw_client, policy: CanaryPolicy):
        policy.validate()
        self._raw = raw_client
        self._policy = policy

    def open_by_key(self, key: str):
        self._policy.allow_sheet(key)
        return AllowlistedSpreadsheet(self._raw.open_by_key(key), self._policy)

    def __getattr__(self, name: str):
        raise IsolationViolation(f"Sheets API access must use open_by_key, not {name}")


class AllowlistedSpreadsheet:
    def __init__(self, raw_sheet, policy: CanaryPolicy):
        self._raw = raw_sheet
        self._policy = policy

    def worksheet(self, name: str):
        self._policy.allow_tab(name)
        return self._raw.worksheet(name)

    def __getattr__(self, name: str):
        raise IsolationViolation(f"disallowed spreadsheet surface: {name}")


class NoOutbound:
    """Tripwire. Not a substitute for container-level egress blocking."""

    def __getattr__(self, name: str):
        raise IsolationViolation(f"outbound API refused: {name}")


def run_full_main(*_args, **_kwargs):
    """Production main() has no verified complete isolation adapter."""
    raise IsolationViolation("FULL_MAIN_BLOCKED: verify all file, DB, mail and network sinks first")
