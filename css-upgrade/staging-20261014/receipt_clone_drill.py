import sqlite3,tempfile
from pathlib import Path
def run(db_file):
    with tempfile.TemporaryDirectory(prefix="css-receipt-drill-") as directory:
        source=sqlite3.connect("file:"+str(Path(db_file).resolve())+"?mode=ro",uri=True)
        source.execute("PRAGMA query_only=ON")
        replica=sqlite3.connect(str(Path(directory)/"replica.sqlite3"))
        source.backup(replica)
        source.close()
        before={r[0]:replica.execute('SELECT COUNT(*) FROM "'+r[0]+'"').fetchone()[0]
                for r in replica.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
        replica.execute("CREATE TABLE IF NOT EXISTS overview_control_receipts (project_id TEXT NOT NULL,source TEXT NOT NULL,signature TEXT NOT NULL,consumed_at TEXT NOT NULL,PRIMARY KEY(project_id,source))")
        replica.execute("INSERT INTO overview_control_receipts VALUES ('AMEA2099555123','priority','hold:2','2026-10-17')")
        replica.commit()
        assert replica.execute("PRAGMA integrity_check").fetchone()[0]=="ok"
        assert not replica.execute("PRAGMA foreign_key_check").fetchmany(1)
        assert all(replica.execute('SELECT COUNT(*) FROM "'+k+'"').fetchone()[0]==v for k,v in before.items())
        replica.close()
        restored=sqlite3.connect(str(Path(directory)/"replica.sqlite3"))
        assert restored.execute("SELECT COUNT(*) FROM overview_control_receipts").fetchone()[0]==1
        assert restored.execute("PRAGMA quick_check").fetchone()[0]=="ok"
        restored.close()
        print("CLONED_RECEIPT_MIGRATION_PASS",len(before))
if __name__=="__main__":
    import sys
    run(sys.argv[1])
