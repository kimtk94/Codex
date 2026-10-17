"""Strict *synthetic-only* adapters for CSS G16 fixture testing.

This is NOT a production API shim. It must never be used with live source,
customer data, external credentials, mailboxes or production DBs. Containers
must separately enforce --network none and --read-only.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
from collections import Counter
from pathlib import Path

from g16_synthetic_pipeline import (
    FakeCRM, FakeMail, FakeSheets, IsolationError, SyntheticMail,
    assert_fixture_mode, assert_tmp_database,
)


class DeniedOperation(IsolationError):
    pass


class OperationLedger:
    """Count method names only; never log payloads, email contents or SQL."""
    def __init__(self):
        self._counts = Counter()

    def record(self, category: str, operation: str):
        self._counts[(category, operation)] += 1

    def summary(self) -> dict[str, int]:
        return {"%s_%s" % k: v for k, v in sorted(self._counts.items())}


class ClosedPort:
    def __getattr__(self, name: str):
        raise DeniedOperation("unregistered adapter operation denied")


class SheetsPort(ClosedPort):
    def __init__(self, ledger: OperationLedger):
        assert_fixture_mode()
        self._memory = FakeSheets()
        self._ledger = ledger

    def publish(self, portfolio: tuple, actions: tuple) -> bool:
        assert_fixture_mode()
        for record in portfolio:
            if not isinstance(record, tuple) or not record or not isinstance(record[0], str) or not record[0].startswith("TEST-"):
                raise DeniedOperation("non-synthetic Sheets portfolio")
        for record in actions:
            if not isinstance(record, tuple) or len(record) != 2 or not str(record[0]).startswith("TEST-"):
                raise DeniedOperation("non-synthetic Sheets action")
        self._ledger.record("sheets", "publish")
        return self._memory.publish(portfolio, actions)

    @property
    def portfolio(self) -> tuple:
        return self._memory.portfolio

    @property
    def actions(self) -> tuple:
        return self._memory.actions

    @property
    def writes(self) -> int:
        return self._memory.writes

    def fail_next_write(self) -> None:
        self._memory.fail_next = True


class MailPort(ClosedPort):
    def __init__(self, messages: list[SyntheticMail], ledger: OperationLedger):
        assert_fixture_mode()
        self._mail = FakeMail(messages)
        self._ledger = ledger

    def receive(self) -> list[SyntheticMail]:
        assert_fixture_mode()
        self._ledger.record("mail", "receive")
        return self._mail.receive()


class CRMPort(ClosedPort):
    def __init__(self, inquiries: dict[str, str], ledger: OperationLedger):
        assert_fixture_mode()
        self._crm = FakeCRM(inquiries)
        self._ledger = ledger

    def pending(self) -> list[tuple[str, str]]:
        assert_fixture_mode()
        self._ledger.record("crm", "pending")
        return self._crm.pending()


class GuardedCursor(ClosedPort):
    def __init__(self, cursor: sqlite3.Cursor):
        self._cursor = cursor

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()


class GuardedConnection(ClosedPort):
    """Tiny SQL fixture seam; prohibit attaching external DB and script escapes."""
    _single = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|BEGIN|COMMIT|ROLLBACK)\b", re.I)
    _bootstrap = re.compile(r"^\s*CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\b", re.I)
    _forbidden = re.compile(
        r"\b(ATTACH|DETACH|VACUUM|LOAD_EXTENSION|CREATE\s+TRIGGER|ALTER\s+TABLE|DROP\s+TABLE)\b",
        re.I,
    )

    def __init__(self, conn: sqlite3.Connection, ledger: OperationLedger):
        self._conn = conn
        self._ledger = ledger

    def _check(self, sql: str):
        assert_fixture_mode()
        if not isinstance(sql, str) or self._forbidden.search(sql):
            raise DeniedOperation("unsafe synthetic SQL")
        if sql.strip().upper() == "PRAGMA FOREIGN_KEYS=ON":
            return
        if ";" in sql or not self._single.match(sql):
            raise DeniedOperation("SQL outside fixture allowlist")

    def execute(self, sql: str, params=()):
        self._check(sql)
        self._ledger.record("sqlite", "execute")
        return GuardedCursor(self._conn.execute(sql, params))

    def executemany(self, sql: str, rows):
        self._check(sql)
        self._ledger.record("sqlite", "executemany")
        return GuardedCursor(self._conn.executemany(sql, rows))

    def executescript(self, sql: str):
        assert_fixture_mode()
        statements = [item.strip() for item in sql.split(";") if item.strip()]
        if not statements or not all(self._bootstrap.match(s) and not self._forbidden.search(s) for s in statements):
            raise DeniedOperation("non-bootstrap SQL script")
        self._ledger.record("sqlite", "schema_fixture")
        return GuardedCursor(self._conn.executescript(sql))

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, typ, val, traceback):
        if typ is not None:
            self._conn.rollback()
        else:
            self._conn.commit()
        return False


class SQLitePort(ClosedPort):
    def __init__(self, ledger: OperationLedger):
        assert_fixture_mode()
        self._ledger = ledger

    def connect(self, path: Path) -> GuardedConnection:
        assert_tmp_database(path)
        resolved = Path(path).resolve()
        if not Path(path).parent.resolve().is_relative_to(Path("/tmp")):
            raise DeniedOperation("SQLite fixture parent escaped")
        self._ledger.record("sqlite", "connect")
        return GuardedConnection(
            sqlite3.connect(str(resolved), isolation_level=None), self._ledger
        )


class FilesPort(ClosedPort):
    """Write only aggregate integer/boolean metrics to a disposable /tmp directory."""
    _name = re.compile(r"^[a-z][a-z0-9_]{0,40}\.json$")
    _metric = re.compile(r"^[a-z][a-z0-9_]{0,64}$")

    def __init__(self, root: Path, ledger: OperationLedger):
        assert_fixture_mode()
        p = Path(root)
        if p.is_symlink() or not p.is_dir() or not p.resolve().is_relative_to(Path("/tmp").resolve()):
            raise DeniedOperation("files fixture path outside disposable tmp")
        self._root = p
        self._ledger = ledger

    def write_metrics(self, filename: str, metrics: dict[str, int | bool]):
        assert_fixture_mode()
        if not self._name.fullmatch(filename):
            raise DeniedOperation("unallowlisted fixture filename")
        if not isinstance(metrics, dict) or not all(
            isinstance(key, str) and self._metric.fullmatch(key)
            and type(value) in (int, bool)
            for key, value in metrics.items()
        ):
            raise DeniedOperation("only aggregate synthetic metrics accepted")
        target = self._root / filename
        if target.is_symlink() or not target.resolve().parent == self._root.resolve():
            raise DeniedOperation("unsafe output target")
        self._ledger.record("files", "metrics_write")
        target.write_text(json.dumps(metrics, sort_keys=True), encoding="utf-8")


class PortBundle(ClosedPort):
    def __init__(self, messages: list[SyntheticMail], inquiries: dict[str, str], files_root: Path):
        assert_fixture_mode()
        self.ledger = OperationLedger()
        self.mail = MailPort(messages, self.ledger)
        self.crm = CRMPort(inquiries, self.ledger)
        self.sheets = SheetsPort(self.ledger)
        self.sqlite = SQLitePort(self.ledger)
        self.files = FilesPort(files_root, self.ledger)
