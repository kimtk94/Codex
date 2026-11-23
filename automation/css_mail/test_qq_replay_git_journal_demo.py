"""Synthetic Git-ref CAS and journal contract, no internet or live finance data."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor

from automation.css_mail.qq_replay_git_journal_demo import (
    DEMO_KEY, REF_PREFIX, ZERO_SHA, _cas, _git, _read, _sim_case,
    demo, opaque_identity, validate_transition,
)


def fixture():
    secret=b"private-SYNTHETIC-only-key-12345678901234567890"
    key,payload=opaque_identity(secret,_sim_case())
    ref=REF_PREFIX+key
    prepared={"schema_version":1,"case_key":key,"payload_digest":payload,
              "attempt_nonce":"synthetic_nonce_1234","revision":1,
              "state":"PREPARED"}
    return secret,ref,prepared


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="qq-replay-synthetic-")
        self.root=Path(self.temp.name)/"journal.git"
        r=subprocess.run(["git","init","--bare","--quiet",str(self.root)],
                         capture_output=True,text=True,timeout=12)
        self.assertEqual(r.returncode,0)

    def tearDown(self):
        self.temp.cleanup()

    def test_hmac_identity_changes_on_source_epoch_and_amount(self):
        secret,ref,event=fixture()
        c=_sim_case()
        c["uidvalidity"]="1099"
        epoch_key,_=opaque_identity(secret,c)
        c=_sim_case()
        c["amount_krw"]="54321"
        same_id,changed_digest=opaque_identity(secret,c)
        self.assertNotEqual(ref,REF_PREFIX+epoch_key)
        self.assertEqual(ref,REF_PREFIX+same_id)
        self.assertNotEqual(event["payload_digest"],changed_digest)

    def test_no_test_key_or_weak_key_could_be_real(self):
        c=_sim_case()
        for key in (DEMO_KEY,b"weak",b"",None):
            with self.assertRaisesRegex(ValueError,"JOURNAL_PRODUCTION_HMAC_KEY_NOT_CONFIGURED"):
                opaque_identity(key,c)

    def test_atomic_create_ref_accepts_one_and_rejects_duplicate(self):
        _,ref,e=fixture()
        self.assertTrue(_cas(self.root,ref,e,ZERO_SHA))
        self.assertFalse(_cas(self.root,ref,e,ZERO_SHA))
        got,sha=_read(self.root,ref)
        self.assertEqual(got,e)
        self.assertRegex(sha,"^[a-f0-9]{40}$")

    def test_two_simultaneous_claims_only_one_wins(self):
        _,ref,e=fixture()
        rival={**e,"attempt_nonce":"synthetic_second_1234"}
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(_cas,self.root,ref,x,ZERO_SHA)
                     for x in (e,rival)]
            results=[f.result() for f in futures]
        self.assertEqual(sorted(results),[False,True])
        found,_=_read(self.root,ref)
        self.assertIn(found["attempt_nonce"],
                      {e["attempt_nonce"],rival["attempt_nonce"]})

    def test_unknown_after_claim_never_reclaims(self):
        _,ref,e=fixture()
        self.assertTrue(_cas(self.root,ref,e,ZERO_SHA))
        # Simulates a lost HTTP response: the writer cannot safely reissue
        # a stage append based on a missing response.
        found,_=_read(self.root,ref)
        self.assertIsNotNone(found)
        self.assertFalse(_cas(self.root,ref,e,ZERO_SHA))

    def test_transitions_are_strict_and_terminal(self):
        _,_,e=fixture()
        unknown={**e,"revision":2,"state":"WRITE_UNKNOWN"}
        verified={**unknown,"revision":3,"state":"VERIFIED"}
        aborted={**e,"revision":2,"state":"ABORTED"}
        self.assertEqual(validate_transition(None,e),"SIMULATED_TRANSITION_OK")
        self.assertEqual(validate_transition(e,unknown),"SIMULATED_TRANSITION_OK")
        self.assertEqual(validate_transition(unknown,verified),"SIMULATED_TRANSITION_OK")
        self.assertEqual(validate_transition(e,aborted),"SIMULATED_TRANSITION_OK")
        self.assertEqual(validate_transition(unknown,{**unknown,"revision":3,"state":"ABORTED"}),
                         "RECEIPT_INVALID_TRANSITION_HOLD")
        self.assertEqual(validate_transition(verified,{**verified,"revision":4,"state":"PREPARED"}),
                         "RECEIPT_INVALID_TRANSITION_HOLD")
        self.assertEqual(validate_transition(aborted,{**aborted,"revision":3,"state":"PREPARED"}),
                         "RECEIPT_INVALID_TRANSITION_HOLD")

    def test_digest_and_nonce_mutations_block(self):
        _,_,e=fixture()
        for changed in ({**e,"revision":2,"state":"WRITE_UNKNOWN","payload_digest":"b"*64},
                        {**e,"revision":2,"state":"WRITE_UNKNOWN","attempt_nonce":"another_nonce_12345"}):
            self.assertEqual(validate_transition(e,changed),"RECEIPT_BINDING_CHANGED_HOLD")

    def test_revision_skips_and_invalid_receipts_block(self):
        _,_,e=fixture()
        self.assertEqual(validate_transition(e,{**e,"revision":4,"state":"WRITE_UNKNOWN"}),
                         "RECEIPT_SEQUENCE_MISMATCH_HOLD")
        self.assertEqual(validate_transition(None,{**e,"state":"VERIFIED"}),
                         "RECEIPT_INVALID_TRANSITION_HOLD")
        self.assertEqual(validate_transition(None,{**e,"schema_version":2}),
                         "RECEIPT_INVALID_HOLD")
        self.assertEqual(validate_transition(None,{**e,"revision":True}),
                         "RECEIPT_INVALID_HOLD")

    def test_ref_update_can_compare_and_swap_old_revision(self):
        _,ref,e=fixture()
        self.assertTrue(_cas(self.root,ref,e,ZERO_SHA))
        before,sha=_read(self.root,ref)
        nxt={**e,"revision":2,"state":"WRITE_UNKNOWN"}
        self.assertEqual(validate_transition(before,nxt),"SIMULATED_TRANSITION_OK")
        self.assertTrue(_cas(self.root,ref,nxt,sha))
        self.assertFalse(_cas(self.root,ref,nxt,sha))
        after,_=_read(self.root,ref)
        self.assertEqual(after,nxt)

    def test_demo_public_output_contains_only_counts(self):
        result=demo()
        self.assertEqual(result["synthetic_claim_succeeded"],1)
        self.assertEqual(result["duplicate_create_ref_blocked"],1)
        self.assertEqual(result["uncertain_reply_would_hold"],1)
        self.assertEqual(result["live_github_refs_written"],0)
        self.assertEqual(result["live_sheets_writes"],0)
        self.assertEqual(result["authenticated_receipts_verified"],0)
        self.assertEqual(result["production_status"],"HOLD")
        self.assertNotIn("209126999001",json.dumps(result))
        self.assertNotIn("synthetic_nonce",json.dumps(result))


if __name__=="__main__":
    unittest.main()
