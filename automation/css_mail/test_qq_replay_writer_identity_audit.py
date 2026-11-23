"""Synthetic writer identity baseline drift tests, no real names or network."""
import io,json,os,unittest
from contextlib import redirect_stdout
from unittest import mock
from automation.css_mail.qq_replay_writer_identity_audit import (
    BASELINE_LABEL,HEADER,_rows_from_sheet,compare_identity_snapshot,main
)

def sample():
    rows=[];perms=[]
    principals=[
        ("original_owner@example.invalid","owner"),
        ("staff@example.invalid","writer"),
        ("sa1@one.iam.gserviceaccount.com","writer"),
        ("sa2@two.iam.gserviceaccount.com","writer"),
    ]
    for i,(email,role) in enumerate(principals,1):
        rows.append({"No.":str(i),"Principal Email (private)":email,
                     "Permission Type":"user","Permission Role":role,
                     "Observed Baseline":BASELINE_LABEL,"Owner Review":"PENDING",
                     "Notes":""})
        perms.append({"id":"id_"+str(i),"type":"user",
                      "emailAddress":email,"role":role})
    return rows,perms

class IdentityTests(unittest.TestCase):
    def test_all_four_match_but_still_hold(self):
        r=compare_identity_snapshot(*sample())
        self.assertEqual(r["identity_match_count"],4)
        self.assertEqual(r["identity_snapshot_exact_match"],1)
        self.assertEqual(r["owner_review_pending_count"],4)
        self.assertEqual(r["identity_allowlist_verified"],0)
        self.assertEqual(r["all_external_writers_excluded"],0)
        self.assertFalse(r["can_execute_replay"])
        self.assertNotIn("original_owner",json.dumps(r))
    def test_same_counts_different_account_detected(self):
        rows,live=sample()
        live[1]["emailAddress"]="replacement@example.invalid"
        r=compare_identity_snapshot(rows,live)
        self.assertEqual(r["identity_match_count"],3)
        self.assertEqual(r["identity_missing_count"],1)
        self.assertEqual(r["identity_unexpected_count"],1)
        self.assertEqual(r["reason_code"],"WRITER_IDENTITY_DRIFT_HOLD")
    def test_unchanged_count_role_swap_detected(self):
        rows,live=sample()
        live[0]["role"]="writer";live[1]["role"]="owner"
        r=compare_identity_snapshot(rows,live)
        self.assertEqual(r["identity_match_count"],2)
        self.assertEqual(r["identity_missing_count"],2)
    def test_add_remove_user_detected(self):
        rows,live=sample()
        extra={**live[-1],"id":"fresh","emailAddress":"new@example.invalid"}
        self.assertEqual(compare_identity_snapshot(rows,live+[extra])["identity_unexpected_count"],1)
        self.assertEqual(compare_identity_snapshot(rows,live[:-1])["identity_missing_count"],1)
    def test_all_owner_accepted_does_not_authorize(self):
        rows,live=sample()
        for x in rows:x["Owner Review"]="ACCEPT"
        r=compare_identity_snapshot(rows,live)
        self.assertEqual(r["owner_review_accept_count"],4)
        self.assertEqual(r["identity_allowlist_verified"],0)
        self.assertEqual(r["actual_qq_stage_writes"],0)
    def test_invalid_baseline_is_blocked(self):
        for k,v in (("Owner Review","APPLY"),("No.","9"),
                    ("Observed Baseline","2025"),("Permission Role","reader")):
            rows,live=sample();rows[1][k]=v
            self.assertEqual(compare_identity_snapshot(rows,live)["reason_code"],
                             "PRIVATE_IDENTITY_BASELINE_INVALID")
        rows,live=sample()
        rows[1]["Principal Email (private)"]=rows[0]["Principal Email (private)"]
        self.assertEqual(compare_identity_snapshot(rows,live)["identity_match_count"],0)
    def test_invalid_live_fields_fail_closed(self):
        for changed in ({"id":None},{"id":"id_1"},{"role":"reader"},
                        {"type":"group"},{"emailAddress":None},{"deleted":True}):
            rows,live=sample();live[1]={**live[1],**changed}
            self.assertEqual(compare_identity_snapshot(rows,live)["reason_code"],
                             "LIVE_PERMISSION_INVENTORY_INVALID")
    def test_header_exact_and_bounded(self):
        rows,live=sample()
        matrix=[list(HEADER)]+[[r[k] for k in HEADER] for r in rows]
        parsed=_rows_from_sheet(matrix)
        self.assertEqual(len(parsed),4)
        self.assertEqual(compare_identity_snapshot(parsed,live)["identity_match_count"],4)
        with self.assertRaisesRegex(ValueError,"SCHEMA_INVALID"):
            _rows_from_sheet([list(reversed(HEADER))]+matrix[1:])
    def test_missing_credentials_is_hold(self):
        out=io.StringIO()
        with mock.patch.dict(os.environ,{"CKD_DRIVE_SA_JSON":""}),redirect_stdout(out):
            self.assertEqual(main(),0)
        r=json.loads(out.getvalue().split("=",1)[1])
        self.assertEqual(r["reason_code"],"PRIVATE_IDENTITY_MONITOR_NOT_CONFIGURED")
        self.assertEqual(r["actual_qq_stage_writes"],0)

if __name__=="__main__":
    unittest.main()
