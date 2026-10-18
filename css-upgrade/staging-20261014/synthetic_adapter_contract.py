#!/usr/bin/env python3
"""Synthetic-only CSS effect-adapter contract test. No CSS import or live API."""
import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

class MemorySheets:
    def __init__(self): self.tabs = {}
    def overwrite(self, tab, rows):
        if not tab.startswith("SYNTHETIC_"): raise PermissionError("PRODUCTION_SHEET_FORBIDDEN")
        canonical = json.loads(json.dumps(rows, ensure_ascii=False))
        changed = self.tabs.get(tab) != canonical
        if changed: self.tabs[tab] = canonical
        return changed
    def read(self, tab): return self.tabs[tab]

class MemoryMail:
    def __init__(self): self.drafts = []; self.sent = []
    def draft(self, to, subject):
        if not to.endswith("@example.invalid"): raise PermissionError("REAL_RECIPIENT_FORBIDDEN")
        self.drafts.append((to, subject))
    def send(self, *args, **kwargs): raise PermissionError("OUTBOUND_EMAIL_FORBIDDEN")

def scenario(root):
    db = root / "synthetic.sqlite3"
    con = sqlite3.connect(db)
    con.executescript("""
        CREATE TABLE projects(project_id TEXT PRIMARY KEY, stage TEXT NOT NULL, prepayment INTEGER NOT NULL);
        CREATE TABLE skips(project_id TEXT PRIMARY KEY, mode TEXT NOT NULL);
    """)
    projects = [
        ("SYN-001", "SIF requested", 1),
        ("SYN-002", "SIF revision required", 1),
        ("SYN-003", "Sample QC", 1),
        ("SYN-004", "SIF requested", 0),
        ("SYN-005", "SIF requested", 1),
    ]
    con.executemany("INSERT INTO projects VALUES(?,?,?)", projects)
    con.execute("INSERT INTO skips VALUES('SYN-005','hold')")
    con.commit()
    sheets, mail = MemorySheets(), MemoryMail()
    def compute():
        rows = con.execute("SELECT project_id,stage,prepayment FROM projects ORDER BY project_id").fetchall()
        manual = dict(con.execute("SELECT project_id,mode FROM skips"))
        result = []
        for pid, stage, prepaid in rows:
            suppress = bool(prepaid and stage in ("SIF requested", "SIF revision required"))
            result.append({"project_id": pid, "stage": stage, "attention": not suppress,
                           "portfolio_visible": True, "manual_mode": manual.get(pid)})
        return result
    before = compute()
    assert len(before) == 5
    assert [r["project_id"] for r in before if not r["attention"]] == ["SYN-001","SYN-002","SYN-005"]
    assert next(r for r in before if r["project_id"]=="SYN-005")["manual_mode"] == "hold"
    assert sheets.overwrite("SYNTHETIC_CSS", before)
    assert not sheets.overwrite("SYNTHETIC_CSS", before)
    assert sheets.read("SYNTHETIC_CSS") == before
    con.execute("UPDATE projects SET stage='Sample QC' WHERE project_id='SYN-001'")
    con.commit()
    after = compute()
    assert next(r for r in after if r["project_id"]=="SYN-001")["attention"]
    assert sheets.overwrite("SYNTHETIC_CSS", after)
    mail.draft("test@example.invalid", "Synthetic SIF Followup")
    assert len(mail.drafts)==1 and not mail.sent
    for action in (lambda: sheets.overwrite("CSS Contract-SIF Tracker", []),
                   lambda: mail.draft("customer@gmail.com","No"),
                   lambda: mail.send("test@example.invalid","No")):
        try: action()
        except PermissionError: pass
        else: raise AssertionError("UNSAFE_SINK_ACCEPTED")
    integrity=con.execute("PRAGMA integrity_check").fetchone()[0]
    assert integrity=="ok"
    con.close()
    payload=json.dumps({"projects":len(after),"attention_count":sum(x["attention"] for x in after),
                        "sheet_rewrites":2,"mail_sent":len(mail.sent),
                        "db_integrity":integrity,"mode":"SYNTHETIC_ADAPTER_CONTRACT_ONLY",
                        "css_main_executed":False},sort_keys=True)
    return payload

def main():
    assert not os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    with tempfile.TemporaryDirectory(dir="/tmp") as temp:
        a=scenario(Path(temp))
        b=scenario(Path(temp))
        assert a==b,"NONDETERMINISTIC_FIXTURE"
        print("CSS_SYNTHETIC_ADAPTER_CONTRACT_PASS",a,flush=True)

if __name__=="__main__": main()
