"""Synthetic, isolated tests for *real* SFDC native Save click admission.

Tests never reach Salesforce or read operator files. Candidate and evidence
are fabricated and stored under a temporary folder only.
"""
from __future__ import annotations
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from native_save_transaction import (
    sha_canonical, paths, load_verified_request, check_candidate_binding,
    create_session, consume_session, before_click, after_click, read_journal,
    mark_unknown, exclusive_transaction, release_lock,
)
from test_oppo_quote_save_preflight import fixture, ASOF


def local_fixture(base):
    candidate,evidence=fixture()
    original=["Process-2020-01-01-00001","Process-2020-01-01-00002",
              "Process-2020-01-01-00003"]
    candidate["products"][0]["source_reference_product_id"]="QPRODUCT-SYNTHETIC-01"
    q={
        "reference":{"qid":"QID-2026-11-01-123456",
                     "sourceQuoteId":"a0P000000000001","opportunityId":"006000000000001"},
        "proposed":{
            "name":candidate["opportunity_name"],
            "date":candidate["request_date_kst"],
            "closeDate":candidate["close_date_kst"],
            "description":candidate["description"],
            "accountMode":"KEEP",
            "account":{"id":candidate["account_id"],"name":"Synthetic University"},
            "contact":{"id":candidate["contact_id"],"name":"Synthetic Researcher"},
            "products":[{
                "id":"QPRODUCT-SYNTHETIC-01","serviceLabel":"Synthetic mRNA",
                "samples":"48","productionGb":"6",
                "sampleUnitKrw":"200000","cloudUnitKrw":"30000",
                "processIds":original,"processNames":["A","B","C"]
            }],"quoteFeeMode":"EXCLUDE",
            "quoteFeeLines":[]
        },"review":{"preflightStatus":"PREVIEW_READY","missing":[]}
    }
    request_id=sha_canonical(q)
    entry={"requestId":request_id,"canonical":q,
           "state":"AWAITING_OPERATOR_APPROVAL","approved":False,
           "requestedWrite":False,"salesforceWrite":False,
           "savePermitted":False,"status":"PENDING_APPROVAL"}
    file=paths(request_id,str(base))
    file["queue"].parent.mkdir(parents=True,exist_ok=True)
    file["root"].mkdir(parents=True,exist_ok=True)
    for k,obj in (("queue",entry),("candidate",candidate),("evidence",evidence)):
        file[k].write_text(json.dumps(obj,ensure_ascii=False,separators=(",",":")),encoding="utf8")
    return request_id,file,candidate,evidence,q


class NativeSaveTransactionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home=Path(self.tmp.name)
        self.rid,self.files,self.candidate,self.evidence,self.original=local_fixture(self.home)
    def loaded(self):
        return load_verified_request(self.rid,str(self.home),asof_utc=ASOF)
    def test_exact_queue_hash_and_authenticated_price_gates(self):
        review,found=self.loaded()
        self.assertEqual(review["status"],"VALIDATED_RECORD")
        self.assertIsNotNone(found)
        self.assertEqual(review["net_krw"],"9690000")
        self.assertTrue(review["approval_digest"].startswith("SFDC-REVIEW-"))
        self.assertEqual(review["native_product_process_rows"],3)
    def test_changed_queued_rate_or_name_cannot_save(self):
        self.candidate["opportunity_name"]="New synthetic name swapped"
        self.files["candidate"].write_text(json.dumps(self.candidate),encoding="utf8")
        response,_=self.loaded()
        self.assertEqual(response["code"],"REQUEST_BINDING_OPPORTUNITY_NAME")
    def test_invalid_contact_identity_cannot_save(self):
        self.candidate["contact_id"]="003000000000002"
        self.files["candidate"].write_text(json.dumps(self.candidate),encoding="utf8")
        response,_=self.loaded()
        self.assertEqual(response["code"],"REQUEST_BINDING_CONTACT_ID")
    def test_changed_process_ids_rejected_even_when_amount_matches(self):
        self.candidate["products"][0]["processes"][0]["process_id"]="Process-2020-01-01-99999"
        self.files["candidate"].write_text(json.dumps(self.candidate),encoding="utf8")
        response,_=self.loaded()
        self.assertEqual(response["code"],"PROCESS_REFERENCE_SET_CHANGED")
    def test_unverified_current_prices_and_duplicate_hold(self):
        self.evidence["current_native_krw_rates_verified"]=False
        self.evidence["duplicate_check"]["matching_quotations"]=1
        self.files["evidence"].write_text(json.dumps(self.evidence),encoding="utf8")
        response,_=self.loaded()
        self.assertEqual(response["code"],"SAVE_PREFLIGHT_HOLD")
        self.assertIn("DUPLICATE_OR_AMBIGUOUS_EXISTING_RECORD",response["reasons"])
        self.assertIn("UNVERIFIED_CURRENT_NATIVE_KRW_RATES_VERIFIED",response["reasons"])
    def test_one_use_nonce_exact_snapshot_and_replay(self):
        review,_=self.loaded()
        nonce=create_session(self.files,review,"OPPORTUNITY","snapshot-v1",now=2000)
        self.assertEqual(len(nonce),48)
        self.assertEqual(consume_session(self.files,review,"OPPORTUNITY",nonce,
          review["approval_digest"],snapshot="changed",now=2001),
          "NATIVE_FORM_CHANGED_SINCE_PRECHECK")
        self.assertIsNone(consume_session(self.files,review,"OPPORTUNITY",nonce,
          review["approval_digest"],snapshot="snapshot-v1",now=2001))
        self.assertEqual(consume_session(self.files,review,"OPPORTUNITY",nonce,
          review["approval_digest"],snapshot="snapshot-v1",now=2002),
          "SAVE_SESSION_REPLAY_OR_MISMATCH")
    def test_expired_nonce_cannot_click(self):
        review,_=self.loaded()
        nonce=create_session(self.files,review,"OPPORTUNITY","original",now=2000)
        self.assertEqual(consume_session(self.files,review,"OPPORTUNITY",nonce,
          review["approval_digest"],snapshot="original",now=2181),
          "SAVE_SESSION_EXPIRED")
    def test_opportunity_then_quotation_save_journal_requires_parent_id(self):
        review,_=self.loaded()
        self.assertEqual(read_journal(self.files)["state"],"NOT_STARTED")
        self.assertEqual(before_click(self.files,"QUOTATION",review,opportunity_id=None),
                         "QUOTATION_PARENT_NOT_VERIFIED")
        self.assertIsNone(before_click(self.files,"OPPORTUNITY",review))
        self.assertEqual(read_journal(self.files)["state"],"OPPORTUNITY_CLICK_STARTED")
        self.assertEqual(before_click(self.files,"OPPORTUNITY",review),
                         "OPPORTUNITY_ALREADY_ATTEMPTED_OR_SAVED")
        self.assertTrue(after_click(self.files,"OPPORTUNITY","006000000000002"))
        self.assertEqual(before_click(self.files,"QUOTATION",review,
          opportunity_id="006000000000003"),"QUOTATION_PARENT_NOT_VERIFIED")
        self.assertIsNone(before_click(self.files,"QUOTATION",review,
          opportunity_id="006000000000002"))
        self.assertTrue(after_click(self.files,"QUOTATION","a0P000000000002"))
        self.assertEqual(read_journal(self.files)["state"],"QUOTATION_SAVED")
        self.assertEqual(read_journal(self.files)["opportunity_id"],"006000000000002")
    def test_unknown_after_click_blocks_retries(self):
        review,_=self.loaded()
        self.assertIsNone(before_click(self.files,"OPPORTUNITY",review))
        mark_unknown(self.files)
        self.assertEqual(read_journal(self.files)["state"],"UNKNOWN_AFTER_CLICK")
        self.assertEqual(before_click(self.files,"OPPORTUNITY",review),
                         "OPPORTUNITY_ALREADY_ATTEMPTED_OR_SAVED")
    def test_concurrent_double_click_lock_cannot_execute(self):
        with exclusive_transaction(self.files):
            with self.assertRaises(FileExistsError):
                with exclusive_transaction(self.files):
                    self.fail("must never enter concurrent transaction")
        # Leaving a lock in place would prevent a restarted writer until review.
        self.assertTrue((self.files["root"]/"writer.lock").exists())
        release_lock(self.files)
        self.assertFalse((self.files["root"]/"writer.lock").exists())
    def test_queue_provenance_digest_cannot_be_forged(self):
        raw=json.loads(self.files["queue"].read_text(encoding="utf8"))
        raw["canonical"]["proposed"]["name"]="TAMPERED NAME"
        self.files["queue"].write_text(json.dumps(raw),encoding="utf8")
        result,_=self.loaded()
        self.assertEqual(result["code"],"QUEUE_DIGEST_MISMATCH")
    def test_missing_private_evidence_fail_closed(self):
        self.files["evidence"].unlink()
        result,_=self.loaded()
        self.assertEqual(result["code"],"PRIVATE_APPROVED_SOURCE_UNAVAILABLE")
    def test_unknown_stage_does_not_advance_journal(self):
        review,_=self.loaded()
        self.assertEqual(before_click(self.files,"UNKNOWN",review),"INVALID_STAGE")
        self.assertEqual(read_journal(self.files)["state"],"NOT_STARTED")


if __name__=="__main__":unittest.main()
