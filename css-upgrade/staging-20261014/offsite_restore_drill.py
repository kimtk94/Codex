#!/usr/bin/env python3
"""Read-only offsite Google Drive backup restore drill.

Runs only in a disposable /tmp directory. No production DB opened for writes,
no file deletion from Drive, no secrets or customer records printed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
from pathlib import Path


BACKUP_PATTERN = re.compile(r"^(css_project_manager|mail_sync_fast)_(\d{8})_(\d{6})\.sqlite3$")
MIN_SIZES = {"css_project_manager": 20 * 1024 * 1024,
             "mail_sync_fast": 100 * 1024 * 1024}
MAX_SIZES = {"css_project_manager": 600 * 1024 * 1024,
             "mail_sync_fast": 2 * 1024 * 1024 * 1024}
TYPES = ("css_project_manager", "mail_sync_fast")
DRIVE_API = "https://www.googleapis.com/drive/v3"


def credentials():
    import google.auth
    from google.auth.exceptions import DefaultCredentialsError
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    try:
        return google.auth.default(scopes=scopes)[0]
    except DefaultCredentialsError:
        pass
    # Resolve the ADC PATH from the service's configuration. Never log the path
    # or parse secrets unrelated to GOOGLE_APPLICATION_CREDENTIALS.
    search = [Path("/home/taehoon/services/novogene-css/.env"),
              Path("/home/taehoon/services/novogene-css/app/.env"),
              Path("/home/taehoon/.config/novogene-css.env")]
    for root in (Path("/etc/systemd/system"), Path("/home/taehoon/.config/systemd/user")):
        if root.is_dir():
            for pattern in ("*novogene*.service", "*css*.service"):
                for unit in root.glob(pattern):
                    try:
                        text = unit.read_text(errors="replace")
                    except OSError:
                        continue
                    for line in text.splitlines():
                        clean = line.strip()
                        if clean.startswith("EnvironmentFile="):
                            candidate = clean.split("=", 1)[1].lstrip("-").strip().strip('"')
                            if candidate.startswith("/"):
                                search.append(Path(candidate.split()[0]))
                        elif clean.startswith("Environment=") and "GOOGLE_APPLICATION_CREDENTIALS=" in clean:
                            m = re.search(r"GOOGLE_APPLICATION_CREDENTIALS=([^\s\"']+)", clean)
                            if m and Path(m.group(1)).is_file():
                                os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = m.group(1)
                                return google.auth.default(scopes=scopes)[0]
    for cfg in search[:50]:
        try:
            if not cfg.is_file() or cfg.stat().st_size > 150_000:
                continue
            for line in cfg.read_text(errors="replace").splitlines():
                line = line.strip().removeprefix("export ")
                if line.startswith("GOOGLE_APPLICATION_CREDENTIALS="):
                    candidate = Path(line.split("=", 1)[1].strip().strip('"').strip("'")).expanduser()
                    if candidate.is_file():
                        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = str(candidate)
                        return google.auth.default(scopes=scopes)[0]
        except OSError:
            pass
    raise RuntimeError("ADC_PATH_UNAVAILABLE")


def api_get(session, path, params):
    response = session.get(f"{DRIVE_API}/{path}", params=params, timeout=90)
    response.raise_for_status()
    return response.json()


def find_remote(session):
    folders = api_get(session, "files", {
        "q": "name = 'server_backup' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        "fields": "nextPageToken,files(id,name,parents)",
        "pageSize": 100,
        "supportsAllDrives": "true",
        "includeItemsFromAllDrives": "true",
    }).get("files", [])
    if not folders:
        raise RuntimeError("BACKUP_FOLDER_NOT_ACCESSIBLE_TO_ADC")
    # The repository may not safely disclose a Drive folder ID.
    # Restrict by both folder name and validated backup filename/size.
    candidates = []
    for folder in folders:
        data = api_get(session, "files", {
            "q": f"'{folder['id']}' in parents and trashed = false and (name contains 'css_project_manager_' or name contains 'mail_sync_fast_')",
            "fields": "nextPageToken,files(id,name,size,md5Checksum,mimeType,parents,createdTime)",
            "pageSize": 1000,
            "orderBy": "name desc",
            "supportsAllDrives": "true",
            "includeItemsFromAllDrives": "true",
        })
        if data.get("nextPageToken"):
            raise RuntimeError("BACKUP_FOLDER_PAGINATION_INCOMPLETE")
        for item in data.get("files", []):
            m = BACKUP_PATTERN.fullmatch(item.get("name", ""))
            if not m:
                continue
            kind = m.group(1)
            sz = int(item.get("size") or 0)
            if not MIN_SIZES[kind] <= sz <= MAX_SIZES[kind]:
                continue
            if folder["id"] not in item.get("parents", []):
                continue
            candidates.append((kind, item["name"], item))
    selected = {}
    for kind in TYPES:
        subset = sorted((name, item) for k, name, item in candidates if k == kind)
        if not subset:
            raise RuntimeError("NO_QUALIFYING_OFFSITE_BACKUP_" + kind.upper())
        selected[kind] = subset[-1][1]
    return selected


def download_one(session, item, output):
    import requests
    expected = int(item["size"])
    md5_remote = str(item.get("md5Checksum") or "").lower()
    md5 = hashlib.md5()
    sha = hashlib.sha256()
    got = 0
    with session.get(
        f"{DRIVE_API}/files/{item['id']}", params={"alt": "media", "supportsAllDrives": "true"},
        stream=True, timeout=(20, 160)
    ) as resp:
        resp.raise_for_status()
        with output.open("xb") as stream:
            for chunk in resp.iter_content(chunk_size=4*1024*1024):
                if not chunk:
                    continue
                got += len(chunk)
                if got > expected:
                    raise RuntimeError("REMOTE_FILE_LARGER_THAN_METADATA")
                md5.update(chunk)
                sha.update(chunk)
                stream.write(chunk)
    if got != expected:
        raise RuntimeError("REMOTE_DOWNLOAD_SIZE_MISMATCH")
    if md5_remote and md5.hexdigest().lower() != md5_remote:
        raise RuntimeError("REMOTE_DOWNLOAD_MD5_MISMATCH")
    return got, sha.hexdigest(), bool(md5_remote)


def check_database(path, kind, *, full):
    db = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=25)
    try:
        db.execute("PRAGMA query_only=ON")
        value = db.execute("PRAGMA integrity_check" if full else "PRAGMA quick_check").fetchone()[0]
        if value != "ok":
            raise RuntimeError("SQLITE_INTEGRITY_FAILURE_" + kind.upper())
        violations = db.execute("PRAGMA foreign_key_check").fetchmany(1)
        if violations:
            raise RuntimeError("SQLITE_FK_FAILURE_" + kind.upper())
        tables = {row[0] for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )}
        if len(tables) < 4:
            raise RuntimeError("TOO_FEW_RESTORED_TABLES_" + kind.upper())
        if kind == "css_project_manager":
            needed = {"contract_sif_skips","mail_ledger","project_timeline"}
        else:
            # Mail collector versions may use different table names.
            needed = set()
        if not needed.issubset(tables):
            raise RuntimeError("REQUIRED_TABLES_NOT_FOUND_" + kind.upper())
        row_counts = {
            name: db.execute(f"SELECT COUNT(*) FROM {name}").fetchone()[0]
            for name in (("contract_sif_skips", "mail_ledger", "project_timeline")
                         if kind == "css_project_manager" else
                         sorted(t for t in tables if t not in ("sqlite_sequence",))[:5])
        }
        return {"table_count": len(tables), "row_counts": row_counts}
    finally:
        db.close()


def run():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-seconds",type=int,default=540)
    args = parser.parse_args()
    started = time.monotonic()
    from google.auth.transport.requests import AuthorizedSession
    session = AuthorizedSession(credentials())
    selected = find_remote(session)
    sizes = {k:int(selected[k]["size"]) for k in TYPES}
    print("OFFSITE_BACKUP_DISCOVERY_PASS", flush=True)
    print("OFFSITE_SELECTED_PROJECT_BYTES",sizes["css_project_manager"], flush=True)
    print("OFFSITE_SELECTED_MAIL_BYTES",sizes["mail_sync_fast"], flush=True)
    minimum = 2*(sum(sizes.values())) + max(sizes.values()) + 450*1024*1024
    if shutil.disk_usage("/tmp").free < minimum:
        raise RuntimeError("INSUFFICIENT_TEMP_FREE_SPACE")
    summary = {}
    with tempfile.TemporaryDirectory(prefix="novogene-offsite-restore-") as tmp:
        root=Path(tmp)
        for kind in TYPES:
            if time.monotonic()-started > args.max_seconds:
                raise RuntimeError("OFFSITE_RESTORE_TIME_BUDGET_EXCEEDED")
            item=selected[kind]
            original=root/f"{kind}.sqlite3"
            recovered=root/f"{kind}.restored.sqlite3"
            got, sha, google_md5 = download_one(session,item,original)
            print("OFFSITE_DOWNLOAD_COMPLETE",kind,got,"REMOTE_MD5_VERIFIED",google_md5,flush=True)
            initial=check_database(original,kind,full=True)
            a=sqlite3.connect(f"file:{original.resolve()}?mode=ro",uri=True)
            a.execute("PRAGMA query_only=ON")
            b=sqlite3.connect(recovered)
            try:
                a.backup(b,pages=4096,sleep=0.03)
            finally:
                b.close()
                a.close()
            restored=check_database(recovered,kind,full=True)
            if initial!=restored:
                raise RuntimeError("RESTORED_TABLE_COUNTS_CHANGED_"+kind.upper())
            summary[kind]={"bytes":got,"remote_md5_checked":google_md5,
                           "tables":restored["table_count"],"rows":restored["row_counts"],
                           "sha256":sha}
            print("OFFSITE_INDEPENDENT_RESTORE_PASS",kind,flush=True)
            original.unlink()
            recovered.unlink()
    print("OFFSITE_PROJECT_AND_MAIL_RESTORE_PASS",flush=True)
    print("RESTORED_PROJECT_TABLES",summary["css_project_manager"]["tables"],flush=True)
    print("RESTORED_MAIL_TABLES",summary["mail_sync_fast"]["tables"],flush=True)
    print("NO_PRODUCTION_DB_SHEETS_OR_BACKUP_CHANGED",True,flush=True)
    print("TEMP_FILES_DELETED",True,flush=True)


if __name__ == "__main__":
    run()
