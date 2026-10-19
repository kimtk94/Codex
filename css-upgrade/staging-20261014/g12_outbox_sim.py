"""G12 synthetic dual-store recovery experiment (NOT production CSS).

Models a durable SQLite outbox and a fake idempotent Sheets sink. This
demonstrates proposed recovery semantics only. Real Sheets does not provide
a transactional commit with SQLite and must NOT be assumed to implement this.
Run only inside a no-network, readonly container with disposable /tmp.
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from g16_synthetic_pipeline import IsolationError, assert_tmp_database, assert_fixture_mode


class DeliveryConflict(IsolationError):
    pass


@dataclass(frozen=True)
class Command:
    delivery_key: str
    project: str
    revision: int
    expected_version: int
    payload: dict
    digest: str


def payload_digest(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def validate_payload(project: str, revision: int, expected_version: int, payload: dict) -> None:
    assert_fixture_mode()
    if not isinstance(project, str) or not project.startswith("TEST-"):
        raise IsolationError("only synthetic projects may be queued")
    if type(revision) is not int or revision < 1 or type(expected_version) is not int or expected_version < 0:
        raise IsolationError("invalid synthetic version")
    if not isinstance(payload, dict) or set(payload) != {"stage", "prepayment", "action"}:
        raise IsolationError("unexpected synthetic payload schema")
    if (not isinstance(payload["stage"], str) or not payload["stage"].startswith("SYN-")
        or type(payload["prepayment"]) is not bool
        or payload["action"] not in ("FOLLOWUP", "HOLD", "SKIP", "QC", "NONE")):
        raise IsolationError("non-synthetic payload value")


class Outbox:
    def __init__(self, path: Path):
        assert_tmp_database(path)
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS outbox (
              project TEXT NOT NULL,
              revision INTEGER NOT NULL,
              expected_version INTEGER NOT NULL,
              delivery_key TEXT NOT NULL UNIQUE,
              payload TEXT NOT NULL,
              digest TEXT NOT NULL,
              acked INTEGER NOT NULL DEFAULT 0,
              attempts INTEGER NOT NULL DEFAULT 0,
              PRIMARY KEY(project, revision));
        """)
        self.fail_ack_once = set()

    def close(self) -> None:
        self.db.close()

    def enqueue(self, project: str, revision: int, expected_version: int, payload: dict) -> str:
        validate_payload(project, revision, expected_version, payload)
        body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        digest = payload_digest(payload)
        key = hashlib.sha256((project + "|" + str(revision) + "|" + digest).encode()).hexdigest()
        self.db.execute("BEGIN IMMEDIATE")
        try:
            existing = self.db.execute(
                "SELECT delivery_key,digest,expected_version FROM outbox WHERE project=? AND revision=?",
                (project, revision)
            ).fetchone()
            if existing is not None:
                if existing != (key, digest, expected_version):
                    raise DeliveryConflict("conflicting revision or sheet precondition")
            else:
                self.db.execute(
                    "INSERT INTO outbox (project,revision,expected_version,delivery_key,payload,digest) "
                    "VALUES (?,?,?,?,?,?)",
                    (project, revision, expected_version, key, body, digest)
                )
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
        return key

    def pending(self) -> list[Command]:
        assert_fixture_mode()
        rows = self.db.execute(
            "SELECT delivery_key,project,revision,expected_version,payload,digest "
            "FROM outbox WHERE acked=0 ORDER BY project,revision"
        ).fetchall()
        result = []
        for key, project, revision, expected, encoded, digest in rows:
            payload = json.loads(encoded)
            validate_payload(project, revision, expected, payload)
            if payload_digest(payload) != digest:
                raise IsolationError("outbox integrity mismatch")
            result.append(Command(key, project, revision, expected, payload, digest))
        return result

    def acknowledge(self, key: str) -> None:
        assert_fixture_mode()
        if key in self.fail_ack_once:
            self.fail_ack_once.remove(key)
            raise RuntimeError("synthetic_sqlite_ack_failure")
        self.db.execute(
            "UPDATE outbox SET acked=1,attempts=attempts+1 WHERE delivery_key=?", (key,)
        )

    def count(self, acked: bool | None = None) -> int:
        if acked is None:
            return self.db.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
        return self.db.execute("SELECT COUNT(*) FROM outbox WHERE acked=?", (int(acked),)).fetchone()[0]


class FakeCASheets:
    """Synthetic CAS + delivery receipt; not a real Google Sheets transaction."""
    def __init__(self):
        self.rows = {}  # project => (version, payload)
        self.receipts = {}  # delivery_key => payload digest
        self.physical_writes = 0
        self.fail_before = set()
        self.fail_after = set()

    def apply(self, command: Command) -> bool:
        assert_fixture_mode()
        validate_payload(command.project, command.revision, command.expected_version, command.payload)
        old_receipt = self.receipts.get(command.delivery_key)
        if old_receipt is not None:
            if old_receipt != command.digest:
                raise DeliveryConflict("reused delivery receipt with different payload")
            return False
        if command.delivery_key in self.fail_before:
            self.fail_before.remove(command.delivery_key)
            raise RuntimeError("synthetic_sheet_before_write_failure")
        actual_version, _ = self.rows.get(command.project, (0, None))
        if actual_version != command.expected_version:
            raise DeliveryConflict("manual edit or concurrent write version conflict")
        self.rows[command.project] = (actual_version + 1, dict(command.payload))
        self.receipts[command.delivery_key] = command.digest
        self.physical_writes += 1
        if command.delivery_key in self.fail_after:
            self.fail_after.remove(command.delivery_key)
            raise RuntimeError("synthetic_sheet_response_lost_after_write")
        return True

    def manual_edit(self, project: str):
        if not project.startswith("TEST-"):
            raise IsolationError("manual fixture project is not synthetic")
        version, payload = self.rows.get(project, (0, None))
        self.rows[project] = (version + 1, payload)


def deliver_once(outbox: Outbox, sheet: FakeCASheets) -> tuple[int, int]:
    """Return newly applied and idempotently replayed fake writes.

    Propagates failures and retains unacknowledged intents for retry.
    """
    applied = replayed = 0
    for command in outbox.pending():
        did_write = sheet.apply(command)
        outbox.acknowledge(command.delivery_key)
        applied += int(did_write)
        replayed += int(not did_write)
    return applied, replayed
