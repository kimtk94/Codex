"""Synthetic-only CSS workflow model for the G16 sandbox.

IMPORTANT: This is NOT the Novogene production engine. It verifies fixture
behaviour and adapter contracts, not production end-to-end correctness.
No customer records, sockets, external credentials or production imports.
"""
from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path


class IsolationError(RuntimeError):
    pass


def assert_fixture_mode() -> None:
    if os.environ.get("G16_SYNTHETIC_ONLY") != "1":
        raise IsolationError("synthetic mode required")


def assert_tmp_database(path: Path) -> None:
    assert_fixture_mode()
    path = Path(path)
    root = Path("/tmp").resolve()
    if path.is_symlink() or not path.resolve().is_relative_to(root) or path.resolve() == root:
        raise IsolationError("SQLite path must be private to disposable /tmp")
    if not path.parent.is_dir():
        raise IsolationError("fixture directory missing")


@dataclass(frozen=True)
class SyntheticMail:
    uid: str
    message_id: str | None
    project: str
    stage: str
    sample: str | None = None

    def validate(self) -> None:
        if not self.uid.startswith("test:") or not self.project.startswith("TEST-"):
            raise IsolationError("only synthetic identifiers allowed")
        if self.message_id and not self.message_id.startswith("synthetic:"):
            raise IsolationError("non-synthetic message id")
        if self.sample and not self.sample.startswith("SYN-"):
            raise IsolationError("non-synthetic sample id")


class FakeMail:
    def __init__(self, messages: list[SyntheticMail]):
        self.messages = list(messages)
        for item in self.messages:
            item.validate()

    def receive(self) -> list[SyntheticMail]:
        assert_fixture_mode()
        return list(self.messages)


class FakeCRM:
    def __init__(self, inquiries: dict[str, str] | None = None):
        self.inquiries = inquiries or {}
        if any(not p.startswith("TEST-") for p in self.inquiries):
            raise IsolationError("CRM fixture must be synthetic")

    def pending(self) -> list[tuple[str, str]]:
        assert_fixture_mode()
        return sorted(self.inquiries.items())


class FakeSheets:
    """In-memory writer. Raises before mutation on injected failure.

    This models one failure case; it does not provide cross-service
    atomicity with a real Google Sheets API.
    """
    def __init__(self):
        self.portfolio = ()
        self.actions = ()
        self.writes = 0
        self.fail_next = False

    def publish(self, portfolio: tuple, actions: tuple) -> bool:
        assert_fixture_mode()
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("synthetic-sheet-write-failed")
        if (portfolio, actions) == (self.portfolio, self.actions):
            return False
        self.portfolio, self.actions = portfolio, actions
        self.writes += 1
        return True


class FixtureEngine:
    SIF = frozenset({"SIF requested", "SIF revision required"})

    def __init__(self, db_path: Path, sqlite_factory=None):
        assert_tmp_database(db_path)
        self.db = (sqlite_factory.connect(db_path) if sqlite_factory is not None
                   else sqlite3.connect(str(db_path), isolation_level=None))
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
          CREATE TABLE IF NOT EXISTS projects(
            project TEXT PRIMARY KEY, stage TEXT NOT NULL, prepayment INTEGER NOT NULL);
          CREATE TABLE IF NOT EXISTS mail_ledger(
            uid TEXT PRIMARY KEY, message_id TEXT, project TEXT NOT NULL,
            FOREIGN KEY(project) REFERENCES projects(project));
          CREATE TABLE IF NOT EXISTS timeline(
            project TEXT NOT NULL, event_key TEXT NOT NULL, stage TEXT NOT NULL,
            PRIMARY KEY(project,event_key),
            FOREIGN KEY(project) REFERENCES projects(project));
          CREATE TABLE IF NOT EXISTS snoozes(
            project TEXT PRIMARY KEY, mode TEXT NOT NULL,
            FOREIGN KEY(project) REFERENCES projects(project));
        """)

    def close(self) -> None:
        self.db.close()

    def bootstrap(self, projects: list[tuple[str, str, bool]]) -> None:
        for pid, stage, _ in projects:
            if not pid.startswith("TEST-") or not stage:
                raise IsolationError("non-synthetic project fixture")
        with self.db:
            self.db.execute("BEGIN")
            try:
                self.db.executemany(
                    "INSERT INTO projects VALUES(?,?,?)",
                    [(pid, stage, int(prepay)) for pid, stage, prepay in projects]
                )
                self.db.execute("COMMIT")
            except Exception:
                self.db.execute("ROLLBACK")
                raise

    def set_manual(self, project: str, mode: str) -> None:
        assert_fixture_mode()
        if not project.startswith("TEST-") or mode not in ("Hold", "Skip", "Release"):
            raise IsolationError("invalid manual fixture")
        if mode == "Release":
            self.db.execute("DELETE FROM snoozes WHERE project=? AND mode IN ('Hold','Skip')", (project,))
        else:
            self.db.execute(
                "INSERT INTO snoozes(project,mode) VALUES(?,?) ON CONFLICT(project) DO UPDATE SET mode=excluded.mode",
                (project, mode)
            )

    def set_stage(self, project: str, stage: str) -> None:
        if not project.startswith("TEST-") or not stage:
            raise IsolationError("non-synthetic stage fixture")
        self.db.execute("UPDATE projects SET stage=? WHERE project=?", (stage, project))

    def counts(self) -> tuple[int, int, int]:
        return tuple(self.db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                     for table in ("mail_ledger", "timeline", "snoozes"))

    def snooze_mode(self, project: str) -> str | None:
        result = self.db.execute("SELECT mode FROM snoozes WHERE project=?", (project,)).fetchone()
        return result[0] if result else None

    def run(self, mail: FakeMail, crm: FakeCRM, sheet: FakeSheets) -> bool:
        """All fixture SQLite writes roll back for a pre-publish sheet failure."""
        assert_fixture_mode()
        self.db.execute("BEGIN")
        try:
            for item in mail.receive():
                prior = self.db.execute(
                    "SELECT message_id,project FROM mail_ledger WHERE uid=?", (item.uid,)
                ).fetchone()
                if prior is not None and prior != (item.message_id, item.project):
                    raise IsolationError("conflicting reuse of a synthetic mail UID")
                self.db.execute(
                    "INSERT OR IGNORE INTO mail_ledger(uid,message_id,project) VALUES(?,?,?)",
                    (item.uid, item.message_id, item.project),
                )
                event = (
                    "sample:" + item.sample
                    if item.sample
                    else ("message:" + item.message_id.lower()
                          if item.message_id else "uid:" + item.uid)
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO timeline(project,event_key,stage) VALUES(?,?,?)",
                    (item.project, event, item.stage),
                )
            projects = self.db.execute(
                "SELECT project,stage,prepayment FROM projects ORDER BY project"
            ).fetchall()
            for pid, stage, prepay in projects:
                current = self.snooze_mode(pid)
                if current in ("Hold", "Skip"):
                    continue
                if prepay and stage in self.SIF:
                    self.db.execute(
                        "INSERT INTO snoozes(project,mode) VALUES(?, 'auto_prepayment') "
                        "ON CONFLICT(project) DO UPDATE SET mode='auto_prepayment'",
                        (pid,),
                    )
                elif current == "auto_prepayment":
                    self.db.execute(
                        "DELETE FROM snoozes WHERE project=? AND mode='auto_prepayment'", (pid,)
                    )
            portfolio = tuple((pid, stage, prepay, self.snooze_mode(pid) or "")
                              for pid, stage, prepay in projects)
            actions = []
            for pid, stage, prepay in projects:
                if self.snooze_mode(pid) in ("Hold", "Skip"):
                    continue
                if stage in self.SIF and not (prepay and self.snooze_mode(pid) == "auto_prepayment"):
                    actions.append((pid, "SIF_FOLLOWUP"))
                elif stage == "Sample QC review":
                    actions.append((pid, "QC_REVIEW"))
            # CRM inquiries remain independent of SIF Prepayment suppression.
            actions += [(pid, "CRM_INQUIRY") for pid, _ in crm.pending()]
            changed = sheet.publish(portfolio, tuple(sorted(actions)))
            self.db.execute("COMMIT")
            return changed
        except BaseException:
            self.db.execute("ROLLBACK")
            raise
