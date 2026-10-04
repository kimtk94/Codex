import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts" / "css_to_vault.py"
spec = importlib.util.spec_from_file_location("css_to_vault", MODULE)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class CssToVaultTest(unittest.TestCase):
    def test_canonical_sheet_overrides_latest_db_event(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            db = root / "css.sqlite3"
            con = sqlite3.connect(db)
            con.execute("""
                CREATE TABLE project_timeline (
                  project_id TEXT, uid TEXT, received_at TEXT, stage TEXT,
                  stage_order INTEGER, progress_percent INTEGER, checkpoint TEXT,
                  action_required INTEGER, sample_count INTEGER, planned_samples INTEGER,
                  h_project_numbers TEXT, sam_numbers TEXT, batch_numbers TEXT,
                  institution TEXT, service TEXT, project_description TEXT,
                  subject TEXT, from_email TEXT, recipient_to TEXT, cc TEXT,
                  processed_at TEXT, PRIMARY KEY(project_id, uid)
                )
            """)
            con.execute("""
                CREATE TABLE tax_invoices (
                  invoice_key TEXT PRIMARY KEY, uid TEXT, source_row INTEGER,
                  received_at TEXT, invoice_month TEXT, invoice_number TEXT,
                  h_project_number TEXT, project_id TEXT, po_reference TEXT,
                  currency TEXT, amount_krw INTEGER, institution TEXT, service TEXT,
                  project_description TEXT, attachment_filename TEXT, subject TEXT,
                  processed_at TEXT
                )
            """)
            con.execute("""
                INSERT INTO project_timeline
                (project_id, uid, received_at, stage, progress_percent, checkpoint,
                 action_required, planned_samples, institution, service,
                 project_description, subject, processed_at)
                VALUES ('AMEA1','1','2026-10-04','Data ready',90,'download',0,24,
                        'Yonsei Univ.','mRNA-Seq','Korea-Yonsei Univ.-24-mRNA-WOBI-ChoInYoung',
                        'Data ready notice','2026-10-04')
            """)
            con.commit(); con.close()

            snapshot = {
                "fetched_at": "2026-10-04T10:00:00Z",
                "project_dashboard": [
                    ["exclude","attention","project_id","institution","customer_name","service","project_description","current_stage","progress_percent","latest_checkpoint","latest_action_required","planned_samples","latest_confirmed_samples","latest_email_at","latest_subject"],
                    ["FALSE","No","AMEA1","Yonsei Univ.","ChoInYoung","mRNA-Seq","Korea-Yonsei Univ.-24-mRNA-WOBI-ChoInYoung","Completed","100","Statement confirmed","No","24","24","2026-10-04","notice"],
                ],
                "action_center": [
                    ["status","priority","due_date","task_id","task_type","project_id","institution","customer_name","service","reason"],
                    ["미검토","긴급","2026-10-05","ACT-1","QC 확인","AMEA1","Yonsei Univ.","ChoInYoung","mRNA-Seq","Review QC"],
                ],
                "customer_360": [],
                "web_export": [],
            }
            snap = root / "snapshot.json"
            snap.write_text(json.dumps(snapshot), encoding="utf-8")
            vault = root / "vault"
            mod.build(db, vault, snap)

            project = (vault / "02_CSS" / "Projects" / "AMEA1.md").read_text(encoding="utf-8")
            self.assertIn('stage: "Completed"', project)
            self.assertIn("Customer: [[02_CSS/Customers/ChoInYoung|ChoInYoung]]", project)
            action = (vault / "02_CSS" / "Actions" / "ACT-1.md").read_text(encoding="utf-8")
            self.assertIn("Review QC", action)
            dashboard = (vault / "00_HOME" / "CSS_DASHBOARD.md").read_text(encoding="utf-8")
            self.assertIn("Completed projects: **1**", dashboard)


if __name__ == "__main__":
    unittest.main()
