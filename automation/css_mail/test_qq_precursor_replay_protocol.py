"""Credential-free safety tests for seven QQ replay approval contracts."""
import datetime as dt
import json
import subprocess
import sys
import unittest
from pathlib import Path

from automation.css_mail.qq_precursor_replay_protocol import (
    evaluate_case, plan_cases, reconcile_uncertain_attempt, _fingerprint
)

NOW=dt.datetime(2026,11,22,15,0,tzinfo=dt.timezone.utc)
def case(n="209126000001"):
    return {"invoice_number":n, "amount_krw":"1000", "imap_folder":"INBOX",
            "imap_uid":"410", "uidvalidity":"1234", "evidence":"OFFICIAL"}
def snaps():
    v={"cursor":[{"folder":"INBOX","uidvalidity":"1234","last_uid":"500"}],
       "audit":[{"status":"SCAN_COMPLETE"}],"qq":[],"css":[]}
    return v,{"cursor":[x.copy() for x in v["cursor"]],
              "audit":[x.copy() for x in v["audit"]],"qq":[],"css":[]}
def approval(c,**changes):
    a={k:c[k] for k in ("invoice_number","amount_krw","imap_folder",
                        "imap_uid","uidvalidity")}
    a.update({"scope":"QQ_STAGE_ONLY","tab":"QQ 2026 Invoice Backfill",
              "decision":"APPROVED","nonce":"SYNTHETIC_NONCE_1234",
              "approved_at":"2026-11-22T14:30:00+00:00",
              "expires_at":"2026-11-22T16:30:00+00:00",
              "evidence_digest":_fingerprint(c)})
    a.update(changes)
    return a

class ProtocolTests(unittest.TestCase):
    def test_seven_have_no_approval_and_no_writes(self):
        cc=[case("209126%06d"%i) for i in range(1,8)]
        before,after=snaps()
        result=plan_cases(cc,{},before,after,
                          {c["invoice_number"]:True for c in cc},NOW)
        self.assertEqual(result["replay_protocol_cases"],7)
        self.assertEqual(result["replay_protocol_holds"],7)
        self.assertEqual(result["replay_protocol_approval_absent"],7)
        self.assertEqual(result["replay_protocol_stage_writes"],0)
        self.assertEqual(result["replay_protocol_cursor_writes"],0)
        self.assertEqual(result["replay_protocol_canonical_writes"],0)
        self.assertEqual(result["replay_protocol_status"],"HOLD")
        self.assertNotIn("209126",json.dumps(result))
    def test_binding_uid_epoch_amount_and_source_digest(self):
        c=case();b,a=snaps()
        for kw in ({"imap_uid":"999"}, {"uidvalidity":"55"},
                   {"amount_krw":"999"},{"evidence_digest":b"bad"}):
            self.assertEqual(evaluate_case(c,approval(c,**kw),b,a,True,NOW),
                             "APPROVAL_BINDING_INVALID")
    def test_scope_expiry_and_unverified_approval(self):
        c=case();b,a=snaps()
        self.assertEqual(evaluate_case(c,approval(c,scope="REVENUE"),b,a,True,NOW),
                         "APPROVAL_SCOPE_INVALID")
        self.assertEqual(evaluate_case(c,approval(c,expires_at="2026-11-22T12:00:00Z"),
                                       b,a,True,NOW),"APPROVAL_EXPIRED")
        self.assertEqual(evaluate_case(c,approval(c),b,a,True,NOW),"APPROVAL_UNTRUSTED")
        # Even an externally asserted proof is not a verified single-writer lock.
        self.assertEqual(evaluate_case(c,approval(c,_authenticated_approval_proof=True),
                                       b,a,True,NOW),"SERIALIZATION_UNPROVEN")
    def test_cursor_change_sink_insert_and_missing_source(self):
        c=case();b,a=snaps()
        a["cursor"][0]["last_uid"]="501"
        self.assertEqual(evaluate_case(c,None,b,a,True,NOW),"CURSOR_CHANGED")
        b,a=snaps();a["qq"]=[{"invoice_number":c["invoice_number"],"amount_krw":"1000"}]
        self.assertEqual(evaluate_case(c,None,b,a,True,NOW),"SINK_ALREADY_PRESENT")
        b,a=snaps()
        self.assertEqual(evaluate_case(c,None,b,a,False,NOW),"SOURCE_UNVERIFIED")
    def test_nonce_reuse_and_missing_proofs_cannot_be_authorized(self):
        a,b=snaps();c1=case();c2=case("209126000002")
        with self.assertRaisesRegex(ValueError,"REPLAY_APPROVAL_NONCE_REUSED"):
            plan_cases([c1,c2],
                       {c1["invoice_number"]:approval(c1),
                        c2["invoice_number"]:approval(c2)},
                       a,b,{c1["invoice_number"]:True,c2["invoice_number"]:True},NOW)
        with self.assertRaisesRegex(ValueError,"REPLAY_PROOF_OR_APPROVAL_SCOPE_INVALID"):
            plan_cases([c1],{},a,b,{},NOW)
    def test_no_epoch_guess_and_source_snapshot_drift(self):
        c=case();b,a=snaps()
        c["uidvalidity"]="9999"
        self.assertEqual(evaluate_case(c,approval(c),b,a,True,NOW),"SOURCE_UNVERIFIED")
        c=case();b,a=snaps()
        a["extract"]=[{"invoice_number":c["invoice_number"],"amount_krw":"5000"}]
        self.assertEqual(evaluate_case(c,approval(c),b,a,True,NOW),"SNAPSHOT_CHANGED")

    def test_script_import_can_load_safety_contract(self):
        import automation.css_mail.qq_precursor_replay_protocol as protocol
        path=Path(protocol.__file__).resolve().parent
        completed=subprocess.run([sys.executable,"-c",
            "from qq_precursor_replay_protocol import plan_cases; assert callable(plan_cases)"],
            cwd=path,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
            text=True,timeout=10)
        self.assertEqual(completed.returncode,0, "direct-script import failed")

    def test_crash_after_append_before_receipt_is_never_retried(self):
        base=case()
        expected={**base, "issued_month":"", "amea_project_id":"A",
                  "h_project_id":"H", "po_reference":"P",
                  "filename":"invoice.pdf"}
        b,a=snaps()
        self.assertEqual(reconcile_uncertain_attempt(expected,[],b["cursor"],a["cursor"]),
                         "ABSENT_RETRY_REQUIRES_NEW_REVIEW")
        self.assertEqual(reconcile_uncertain_attempt(expected,[expected],b["cursor"],a["cursor"]),
                         "EXACT_ROW_PRESENT_RECEIPT_UNVERIFIED_HOLD")
        self.assertEqual(reconcile_uncertain_attempt(expected,[expected,expected],
                                                     b["cursor"],a["cursor"]),"DUPLICATE_HOLD")
        self.assertEqual(reconcile_uncertain_attempt(expected,
                         [{**expected,"amount_krw":"1001"}],b["cursor"],a["cursor"]),
                         "CONFLICT_HOLD")
        a["cursor"][0]["last_uid"]="501"
        self.assertEqual(reconcile_uncertain_attempt(expected,[expected],
                                                     b["cursor"],a["cursor"]),
                         "CURSOR_CHANGED_HOLD")

if __name__=="__main__":
    unittest.main()
