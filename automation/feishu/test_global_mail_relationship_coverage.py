import hashlib
import json
import unittest
from unittest.mock import patch
import global_mail_relationship_coverage as m
import global_relationship_coverage as g

P="AMEA2026000001"
Q="AMEA2026000002"
H="H209SC26000001"
MID="<one@example.invalid>"
TUPLE="INBOX|123|456"
KEY=hashlib.sha256(TUPLE.encode()).hexdigest()
OTHER="a"*64

def sources():
    return {k:[] for k in g.SOURCES}

def tables():
    return {k:[] for k in m.TABLE_FIELDS}

def canonical(**kwargs):
    return {"canonical_key":"imap:"+TUPLE,"source_table":"CSS Git Ingest",
            "imap_folder":"INBOX","uidvalidity":"123","imap_uid":"456","message_id":MID,
            "amea_numbers":P,"h_project_numbers":H,"sam_numbers":"","invoice_numbers":"",
            "subject":"","direction":"INBOUND","from_email":"customer@example.invalid",**kwargs}

class MailTests(unittest.TestCase):
    def test_exact_tuple_crosswalk_not_message_id_merge(self):
        c=[canonical(),canonical(canonical_key="legacy:All Emails:2",source_table="All Emails",
                                imap_folder="",uidvalidity="",imap_uid="")]
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID},{"Mail Key":OTHER,"Message ID":MID}]
        out=m.audit(c,t,sources())
        self.assertEqual(out["canonical"]["rows"],2)
        self.assertEqual(out["canonical"]["duplicate_message_id_groups"],1)
        self.assertEqual(out["qq_canonical_crosswalk"]["EXACT_IMAP_TUPLE_KEY"],1)
        self.assertEqual(out["qq_canonical_crosswalk"]["MESSAGE_ID_MULTIPLE_CANDIDATES_ONLY"],1)
        self.assertEqual(out["project_reference_population"]["mail_only"],1)
        self.assertNotIn(P,json.dumps(out))
        self.assertNotIn(MID,json.dumps(out))

    def test_invalid_tuple_fails_and_legacy_is_not_hashed(self):
        with self.assertRaisesRegex(m.MailAuditError,"TUPLE_MISMATCH"):
            m.canonical_key(canonical(uidvalidity="999"))
        self.assertEqual(m.canonical_key(canonical(canonical_key="legacy:All Emails:2",
                        source_table="All Emails"))[1],None)

    def test_preserve_multiple_project_refs_and_suffixes(self):
        row=canonical(amea_numbers=P+";"+Q,subject=P+"-2 / "+Q+"-BAD / X209SC26000001-Z03")
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":""}]
        out=m.audit([row],tables(),s)
        self.assertEqual(out["project_reference_population"]["union"],3)
        self.assertEqual(out["project_reference_population"]["mail_only"],2)
        self.assertEqual(out["canonical"]["reference_rows"]["STRUCTURED_SUBJECT_DIFFERENCE_AMEA"],1)
        self.assertEqual(out["canonical"]["reference_rows"]["ANY_X_PROJECT"],1)
        self.assertFalse(m.subject_refs("phone 12345678901")["CMS"])

    def test_key_conflict_and_crm_namespace(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":"<different@example.invalid>"}]
        t[m.CRM]=[{"Mail Key":OTHER,"Message ID":MID}]
        t[m.PO]=[{"Contract Source":"CRM","Contract Mail Key":OTHER,
                   "PO Notice Source":"CSS","PO Mail Key":OTHER}]
        out=m.audit([canonical()],t,sources())
        self.assertEqual(out["qq_canonical_crosswalk"]["EXACT_KEY_MESSAGE_ID_CONFLICT"],1)
        self.assertEqual(out["crm_canonical_message_id_candidates"]["MESSAGE_ID_ONE_CANDIDATE_ONLY"],1)
        self.assertEqual(out["tracker_mail_references"][m.PO+"|Contract Mail Key|SOURCE_KEY_OBSERVED"],1)
        self.assertEqual(out["tracker_mail_references"][m.PO+"|PO Mail Key|SOURCE_KEY_NOT_OBSERVED"],1)

    def test_multi_contact_email_reference_not_auto_assignment(self):
        s=sources()
        s["SFDC Email Leads Raw"]=[{"Email":"customer@example.invalid","Contact ID":"003123456789012",
                                     "Lead ID":"00Q123456789012"}]
        s["SFDC Email Quotation Raw"]=[{"Email":"customer@example.invalid","Contact ID":"003123456789013"}]
        out=m.audit([canonical()],tables(),s)
        self.assertEqual(out["canonical"]["reference_rows"]["CONTACT_EMAIL_REFERENCE_MULTIPLE"],1)
        self.assertEqual(out["canonical"]["reference_rows"]["LEAD_EMAIL_REFERENCE_ONE"],1)
        self.assertFalse(out["owner_filter_applied"])

    def test_duplicate_keys_fail(self):
        with self.assertRaisesRegex(m.MailAuditError,"CANONICAL_DUPLICATE"):
            m.audit([canonical(),canonical()],tables(),sources())


class UnmatchedProjectReferenceTests(unittest.TestCase):
    def test_direct_nonmail_and_canonical_membership_no_assignment(self):
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":""}]
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"AMEA":P,"H Project":H}]
        t[m.IDENTITY]=[{"Mail Key":KEY,"Project Link":"PROJECT_ID_UNMATCHED"}]
        c=[canonical()]
        out=m.audit(c,t,s)["unmatched_project_reference_audit"]
        self.assertEqual(out["population"]["UNMATCHED_PROJECT_ID"],1)
        self.assertEqual(out["nonmail_reference_state"],{"DIRECT_AMEA_OBSERVED_NONMAIL":1})
        self.assertEqual(out["canonical_any_reference"],{"AMEA_AND_H_OBSERVED":1})
        self.assertEqual(out["other_canonical_record"],{"ONLY_SAME_KEY_OR_KNOWN_SAME_MESSAGE_ID":1})
        self.assertEqual(t[m.IDENTITY][0]["Project Link"],"PROJECT_ID_UNMATCHED")
        self.assertNotIn(P,json.dumps(out))
        self.assertNotIn(H,json.dumps(out))

    def test_same_message_id_legacy_not_other_record_evidence(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"AMEA":P}]
        t[m.IDENTITY]=[{"Mail Key":KEY,"Project Link":"PROJECT_ID_UNMATCHED"}]
        legacy=canonical(canonical_key="legacy:All Emails:2",source_table="All Emails",
                         imap_folder="",uidvalidity="",imap_uid="")
        out=m.audit([canonical(),legacy],t,sources())["unmatched_project_reference_audit"]
        self.assertEqual(out["legacy_amea_reference"],{"AT_LEAST_ONE_AMEA_IN_LEGACY":1})
        self.assertEqual(out["other_canonical_record"],{"ONLY_SAME_KEY_OR_KNOWN_SAME_MESSAGE_ID":1})
        legacy["message_id"]="<different@example.invalid>"
        out=m.audit([canonical(),legacy],t,sources())["unmatched_project_reference_audit"]
        self.assertEqual(out["other_canonical_record"],{"OTHER_KEY_WITHOUT_KNOWN_SAME_MESSAGE_ID":1})

    def test_preserve_partial_and_multiple_amea_references(self):
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":""}]
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"AMEA":P+";"+Q}]
        t[m.IDENTITY]=[{"Mail Key":KEY,"Project Link":"PROJECT_ID_UNMATCHED"}]
        out=m.audit([canonical()],t,s)["unmatched_project_reference_audit"]
        self.assertEqual(out["canonical_amea_literal"],{"PARTIAL_OBSERVED":1})
        self.assertEqual(out["nonmail_reference_state"],{"PARTIAL_AMEA_CANDIDATE":1})
        self.assertEqual(out["population"]["MULTIPLE_LITERAL_AMEA"],1)

    def test_h_candidate_exact_suffix_and_multi_amea_not_cross_joined(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"H Project":H+"-B01"},
                 {"Mail Key":OTHER,"Message ID":"<other@example.invalid>","H Project":H}]
        t[m.IDENTITY]=[{"Mail Key":k,"Project Link":"PROJECT_ID_UNMATCHED"} for k in (KEY,OTHER)]
        out=m.audit([canonical(amea_numbers=P+";"+Q)],t,sources())["unmatched_project_reference_audit"]
        self.assertEqual(out["canonical_h_literal"],{"NONE_OBSERVED":1,"ALL_OBSERVED":1})
        self.assertEqual(out["canonical_h_amea_candidates"],{"NO_COOBSERVED_AMEA":2})
        self.assertEqual(out["canonical_any_reference"],{"NO_STRUCTURED_CANONICAL_REFERENCE":1,
                         "H_ONLY_OBSERVED":1})

    def test_absent_source_and_existing_link_preserved(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"AMEA":P}]
        t[m.IDENTITY]=[{"Mail Key":KEY,"Project Link":"PROJECT_ID_EXACT","Project ID":P},
                       {"Mail Key":OTHER,"Project Link":"PROJECT_ID_UNMATCHED"}]
        out=m.audit([canonical()],t,sources())["unmatched_project_reference_audit"]
        self.assertEqual(out["population"],{"OTHER_IDENTITY_STATE_NOT_ASSESSED":1,
                         "UNMATCHED_PROJECT_ID":1,"SOURCE_QQ_NOT_OBSERVED":1})
        self.assertEqual(out["nonmail_reference_state"],{})

    def test_h_root_candidate_is_not_direct_amea(self):
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":""}]
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"Message ID":MID,"H Project":H+"-B01"}]
        t[m.IDENTITY]=[{"Mail Key":KEY,"Project Link":"PROJECT_ID_UNMATCHED"}]
        out=m.audit([canonical()],t,s)["unmatched_project_reference_audit"]
        self.assertEqual(out["nonmail_reference_state"],{"H_ROOT_ONE_CANDIDATE":1})
        self.assertEqual(out["canonical_h_literal"],{"NONE_OBSERVED":1})
        self.assertEqual(out["nonmail_and_canonical_reference"],{"NONMAIL_ONLY":1})

if __name__=="__main__":
    unittest.main()
