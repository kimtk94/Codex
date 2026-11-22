"""Synthetic-only regression tests: no private invoices, mailbox, or Sheet writes."""
import json
import unittest
from automation.css_mail import invoice_provenance_triage as triage

SCAN = "2026-11-22T08:35:12+00:00"


def qq(number, month="2026-11", uid="401"):
    return {"invoice_number": number, "issued_month": month, "amount_krw": "1100",
            "amea_project_id": "AMEA-TEST", "h_project_id": "H-TEST",
            "po_reference": "PO-TEST", "imap_uid": uid}


def css(number, month="2026-11"):
    return {"invoice_number": number, "invoice_month": month, "amount_krw": "1100"}


def ext(number, uid="401", when="2026-11-22T07:00:00+00:00", key=None):
    return {"invoice_number": number, "amount_krw": "1100",
            "project_id": "AMEA-TEST", "h_project_number": "H-TEST",
            "po_reference": "PO-TEST", "imap_uid": uid,
            "ingest_key": key or ("K" + number),
            "received_at": "2026-11-21T08:00:00+00:00",
            "validation_status": "FILENAME_PARSED",
            "extracted_at_utc": when}


def ingest(e):
    return {"ingest_key": e["ingest_key"], "imap_uid": e["imap_uid"],
            "uidvalidity": "123456", "folder": "INBOX", "direction": "INBOUND",
            "from_email": "css@novogene-amea.com",
            "subject": "Notice: Invoice Issued & Statement Confirmed",
            "in_reply_to": ""}


def cursor(uid="500"):
    return [{"year": "2026", "folder": "INBOX",
             "uidvalidity": "123456", "last_uid": uid}]


def projects():
    return [{"project_id": "AMEA-TEST", "institution": "Test Institute"}]


def tracker():
    return [{"project_id": "AMEA-TEST", "Responsible Sales": "Sales Person"}]


class InvoiceProvenanceTests(unittest.TestCase):
    def test_lineage_owner_scope_and_cursor_split(self):
        q1 = qq("209126000001")
        q2 = qq("209126000002", month="", uid="402")
        e1 = ext("209126000001")
        e2 = ext("209126000002", uid="402")
        e3 = ext("209126000003", uid="410")
        e4 = ext("209126000004", uid="700",
                 when="2026-11-22T11:20:36+00:00")
        records = [e1, e2, e3, e4]
        i = {x["ingest_key"]: ingest(x) for x in records}
        result = triage.summarize(
            [q1, q2], [css("209126000009")], records,
            cursor(), projects(), tracker(), i, SCAN)
        self.assertEqual(result["provenance_lineage"]["four_key_match"], 1)
        self.assertEqual(result["provenance_lineage"]["project_context_match"], 1)
        self.assertEqual(result["provenance_lineage"]["sales_owner_candidate_present"], 1)
        self.assertEqual(result["provenance_lineage"]["owner_approval_verified"], 0)
        self.assertEqual(result["provenance_lineage"]["private_invoice_proof_receipts_verified"], 0)
        self.assertEqual(result["blank_qq_month"]["rows"], 1)
        self.assertEqual(result["blank_qq_month"]["uid_matches"], 1)
        self.assertEqual(result["blank_qq_month"]["original_issue_month_verified"], 0)
        self.assertEqual(result["unlinked_extract"]["all_years_unlinked"], 2)
        self.assertEqual(result["unlinked_extract"]["prior_official_header"], 1)
        self.assertEqual(result["unlinked_extract"]["after_official_header"], 1)
        self.assertEqual(result["business_writes"], 0)
        serialized = json.dumps(result)
        for secret in ["209126000001", "AMEA-TEST", "Test Institute", "Sales Person",
                       "css@novogene-amea.com", "123456"]:
            self.assertNotIn(secret, serialized)

    def test_blank_month_uid_conflict_not_auto_corrected(self):
        source=qq("209126000002", month="", uid="404")
        extract=ext("209126000002",uid="402")
        r=triage.summarize([source],[css("209126000009")],[extract],
                           cursor(),projects(),tracker(),
                           {extract["ingest_key"]:ingest(extract)},SCAN)
        self.assertEqual(r["blank_qq_month"]["uid_conflicts"], 1)
        self.assertEqual(r["blank_qq_month"]["other_fields_match"], 1)
        self.assertEqual(r["blank_qq_month"]["original_issue_month_verified"], 0)

    def test_wrong_uid_epoch_blocks_false_cursor_gap(self):
        before=ext("209126000003",uid="410")
        source=ingest(before)
        source["uidvalidity"]="654321"
        with self.assertRaisesRegex(ValueError,"INGEST_OFFICIAL_SOURCE_INCONSISTENT"):
            triage.summarize([qq("209126000001")],[css("209126000009")],
                             [before],cursor(),projects(),tracker(),
                             {before["ingest_key"]:source},SCAN)

    def test_wrong_mail_issuer_blocks(self):
        before=ext("209126000003",uid="410")
        source=ingest(before)
        source["from_email"]="unknown@example.com"
        with self.assertRaisesRegex(ValueError,"INGEST_OFFICIAL_SOURCE_INCONSISTENT"):
            triage.summarize([qq("209126000001")],[css("209126000009")],
                             [before],cursor(),projects(),tracker(),
                             {before["ingest_key"]:source},SCAN)

    def test_duplicate_source_id_blocks(self):
        with self.assertRaisesRegex(ValueError,"EXTRACT_DUPLICATE_ID"):
            triage.summarize([qq("209126000001")],[css("209126000009")],
                             [ext("209126000002"),ext("209126000002")],
                             cursor(),projects(),tracker(),{},SCAN)

    def test_missing_approver_is_not_substituted_by_action_owner(self):
        source=qq("209126000001")
        extract=ext("209126000001")
        r=triage.summarize([source],[css("209126000009")],[extract],
                           cursor(),projects(),[{"project_id":"NONMATCH","Responsible Sales":""}],{},SCAN)
        self.assertEqual(r["provenance_lineage"]["sales_owner_candidate_present"],0)
        self.assertEqual(r["provenance_lineage"]["owner_approval_verified"],0)

    def test_source_keys_select_only_blank_or_unlinked(self):
        e1=ext("209126000001")
        e2=ext("209126000002")
        e3=ext("209126000003")
        keys=triage.source_relevant_keys(
            [qq("209126000001"),qq("209126000002",month="")],
            [css("209126000009")],[e1,e2,e3])
        self.assertEqual(keys,{e2["ingest_key"],e3["ingest_key"]})

    def test_readonly_ingest_subset_two_requests(self):
        key="KEY_ONLY"
        class Response:
            def __init__(self,body): self.body=body
            def raise_for_status(self): return None
            def json(self): return self.body
        class Session:
            def __init__(self): self.calls=[]
            def get(self,url,**kwargs):
                self.calls.append((url,kwargs))
                if "batchGet" not in url:
                    return Response({"values":[["ingest_key"],[key]]})
                return Response({"valueRanges":[{"values":[
                    [key,"message","401","INBOX","123456","2026-11-22T00:00:00Z",
                     "css@novogene-amea.com","","",
                     "Notice: Invoice Issued & Statement Confirmed"]
                ]}]})
        session=Session()
        got=triage.load_ingest_subset(session,"FAKE_SHEET_ID",{key},bound=100)
        self.assertEqual(len(session.calls),2)
        self.assertEqual(got[key]["uidvalidity"],"123456")
        self.assertEqual(got[key]["from_email"],"css@novogene-amea.com")
        self.assertNotIn("POST",json.dumps(session.calls))

    def test_missing_ingest_key_blocks(self):
        class R:
            def raise_for_status(self): pass
            def json(self): return {"values":[["ingest_key"],["OTHER_KEY"]]}
        class S:
            def get(self,*args,**kwargs): return R()
        with self.assertRaisesRegex(ValueError,"INGEST_EVIDENCE_MISSING"):
            triage.load_ingest_subset(S(),"FAKE_ID",{"MISSING_KEY"})

    def test_owner_candidates_multiple_disagree_are_ambiguous(self):
        src=qq("209126000001")
        x=ext("209126000001")
        t=[{"project_id":"AMEA-TEST","Responsible Sales":"A"},
           {"project_id":"AMEA-TEST","Responsible Sales":"B"}]
        r=triage.summarize([src],[css("209126000009")],[x],cursor(),
                           projects(),t,{},SCAN)
        self.assertEqual(r["provenance_lineage"]["sales_owner_candidate_present"],0)
        self.assertEqual(r["provenance_lineage"]["sales_owner_candidate_ambiguous"],1)


if __name__ == "__main__":
    unittest.main()
