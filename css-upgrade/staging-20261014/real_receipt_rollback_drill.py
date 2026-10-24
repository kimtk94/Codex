import argparse,ast,hashlib,sqlite3,subprocess,tempfile,importlib.util
from pathlib import Path
import pandas as pd
from zoneinfo import ZoneInfo

SHA="a7c395be330bc1128f8164cdac1d75a7c27fd35398e46ff5589271ebf0bae840"
CANDIDATE="3963b6cbd60205c2738943e4b28e2a88a1987776bfdda05ee8cba269d6ea3806"
PATCH_NAMES=("novogene_sif_history_candidate.patch","novogene_sif_manual_override_collision.patch","novogene_sif_portfolio_visibility.patch","novogene_sif_independent_actions.patch","novogene_sif_atomic_auto_skip.patch","novogene_css_hold_replay_guard.patch","novogene_css_one_shot_receipts.patch","novogene_css_snapshot_conflict_guard.patch")
passes=[]
def require(ok,key):
    if not ok:raise AssertionError(key)
    passes.append(key)
    print("COMBINED_MIGRATION_PASS",key,flush=True)

def main():
    a=argparse.ArgumentParser()
    a.add_argument("--source",required=True)
    a.add_argument("--db",required=True)
    a.add_argument("--patch-dir",required=True)
    a.add_argument("--helper",required=True)
    x=a.parse_args()
    raw=Path(x.source).read_bytes()
    require(hashlib.sha256(raw).hexdigest()==SHA,"ORIGINAL_SOURCE_IDENTITY")
    with tempfile.TemporaryDirectory(prefix="css-real-migration-") as directory:
        root=Path(directory)
        live=sqlite3.connect("file:"+str(Path(x.db).resolve())+"?mode=ro",uri=True,timeout=30)
        live.execute("PRAGMA query_only=ON")
        database=root/"css_project.sqlite3"
        cloned=sqlite3.connect(database,timeout=30)
        live.backup(cloned,pages=4096,sleep=.02)
        live.close()
        tables=[r[0] for r in cloned.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        require(len(tables)>=26,"PRODUCTION_SCHEMA_CLONED")
        counts={n:cloned.execute('SELECT COUNT(*) FROM "'+n.replace('"','""')+'"').fetchone()[0] for n in tables}
        require(cloned.execute("PRAGMA integrity_check").fetchone()[0]=="ok","BASELINE_INTEGRITY")
        staged=root/"Novogene_Mail_CSS_DashBoard.py"
        staged.write_bytes(raw)
        patches=[Path(x.patch_dir)/n for n in PATCH_NAMES]
        for i,p in enumerate(patches,1):
            z=subprocess.run(["git","apply","--check",str(p.resolve())],cwd=root,capture_output=True,text=True)
            require(z.returncode==0,"PATCH_CHECK_"+str(i))
            z=subprocess.run(["git","apply",str(p.resolve())],cwd=root,capture_output=True,text=True)
            require(z.returncode==0,"PATCH_APPLIED_"+str(i))
        candidate=staged.read_bytes()
        require(hashlib.sha256(candidate).hexdigest()==CANDIDATE,"EIGHT_PATCH_SHA")
        tree=ast.parse(candidate)
        spec=importlib.util.spec_from_file_location("css_sync_fixture",x.helper)
        helper=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(helper)
        ns=helper.extract(candidate)
        pid="AMEA2099555123"
        cloned.execute("SAVEPOINT control_cycle")
        try:
            ns["_sync_overview_snooze_actions_from_records"](
                cloned,pd.DataFrame([{"project_id":pid,"latest_uid":"SYNTH"}]),
                [{"AMEA Project":pid,"Normal Action":"Hold","Hold Days":"2"}],[],
                now=pd.Timestamp("2026-10-17T12:00:00+09:00"))
            cloned.execute("RELEASE SAVEPOINT control_cycle")
            cloned.commit()
        except:
            cloned.execute("ROLLBACK TO SAVEPOINT control_cycle")
            cloned.execute("RELEASE SAVEPOINT control_cycle")
            raise
        record=cloned.execute("SELECT source,signature FROM overview_control_receipts WHERE project_id=?",(pid,)).fetchone()
        require(record==("priority","hold:2"),"REAL_FUNCTION_CREATED_RECEIPT")
        require(cloned.execute("SELECT mode FROM overview_project_snoozes WHERE project_id=?",(pid,)).fetchone()[0]=="hold","REAL_FUNCTION_CREATED_HOLD")
        require(all(cloned.execute('SELECT COUNT(*) FROM "'+n.replace('"','""')+'"').fetchone()[0]==v+(1 if n=="overview_project_snoozes" else 0) for n,v in counts.items()),"EXISTING_ROWS_PRESERVED")
        require(cloned.execute("PRAGMA integrity_check").fetchone()[0]=="ok","MIGRATED_INTEGRITY")
        cloned.close()
        for i,p in reversed(list(enumerate(patches,1))):
            z=subprocess.run(["git","apply","-R",str(p.resolve())],cwd=root,capture_output=True,text=True)
            require(z.returncode==0,"SOURCE_REVERSE_"+str(i))
        require(staged.read_bytes()==raw,"SOURCE_BYTE_EXACT_ROLLBACK")
        # Execute actual LEGACY sync helper against the migrated clone.
        # Only the safe AST-extracted function is used; never import/run main.
        legacy_ns=helper.extract(raw)
        legacy=sqlite3.connect(database)
        baseline_receipt=legacy.execute(
            "SELECT source,signature,consumed_at FROM overview_control_receipts WHERE project_id=?",
            (pid,)).fetchone()
        baseline_count=legacy.execute(
            "SELECT COUNT(*) FROM overview_project_snoozes").fetchone()[0]
        # Legacy release should continue to function without querying/dropping
        # the extra receipt table. This deliberately tests reverse compatibility.
        legacy.execute("SAVEPOINT legacy_cycle")
        try:
            legacy_ns["_sync_overview_snooze_actions_from_records"](
                legacy,pd.DataFrame([{"project_id":pid,"latest_uid":"SYNTH"}]),
                [{"AMEA Project":pid,"Normal Action":"Release","Hold Days":""}],[],
                now=pd.Timestamp("2026-10-17T12:01:00+09:00"))
            legacy.execute("RELEASE SAVEPOINT legacy_cycle")
            legacy.commit()
        except:
            legacy.execute("ROLLBACK TO SAVEPOINT legacy_cycle")
            legacy.execute("RELEASE SAVEPOINT legacy_cycle")
            raise
        require(legacy.execute("SELECT COUNT(*) FROM overview_project_snoozes").fetchone()[0]
                ==baseline_count-1,"LEGACY_FUNCTION_RELEASES_SYNTHETIC_HOLD")
        require(legacy.execute("SELECT source,signature,consumed_at FROM overview_control_receipts WHERE project_id=?",
                 (pid,)).fetchone()==baseline_receipt,"LEGACY_FUNCTION_PRESERVES_RECEIPT")
        # Restore one synthetic Hold for the existing row-count checks while
        # keeping the receipt untouched.
        legacy_ns["_upsert_overview_snooze"](
            legacy,pid,"hold","2026-10-19T12:00:00+09:00",
            "SYNTHETIC_MAIL","2026-10-17T12:02:00+09:00")
        legacy.commit()
        require(legacy.execute("SELECT COUNT(*) FROM overview_project_snoozes").fetchone()[0]
                ==baseline_count,"LEGACY_HELPER_REINSERTS_HOLD")

        require(legacy.execute("SELECT signature FROM overview_control_receipts WHERE project_id=?",(pid,)).fetchone()[0]=="hold:2","RECEIPT_RETAINED_AFTER_SOURCE_ROLLBACK")
        require(all(legacy.execute('SELECT COUNT(*) FROM "'+n.replace('"','""')+'"').fetchone()[0]==v+(1 if n=="overview_project_snoozes" else 0) for n,v in counts.items()),"LEGACY_TABLE_COUNTS_PRESERVED")
        require(legacy.execute("PRAGMA integrity_check").fetchone()[0]=="ok","POST_ROLLBACK_DB_INTEGRITY")
        legacy.close()
        require(hashlib.sha256(Path(x.source).read_bytes()).hexdigest()==SHA,"PRODUCTION_SOURCE_UNMODIFIED")
    print("REAL_FUNCTION_AND_SOURCE_ROLLBACK_PASS",len(passes),flush=True)
    print("TEMP_CLONE_DELETED",True,flush=True)
    print("NO_PRODUCTION_WRITES",True,flush=True)

if __name__=="__main__":main()
