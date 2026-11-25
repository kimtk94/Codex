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

class BoundedReadTests(unittest.TestCase):
    class Response:
        def __init__(self,status,payload=None,headers=None):
            self.status_code=status
            self.ok=200<=status<300
            self.payload=payload
            self.headers=headers or {}
        def json(self):
            if isinstance(self.payload,Exception):
                raise self.payload
            return self.payload

    def test_permission_error_is_sanitized_and_never_retried(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.return_value=self.Response(403,{"private":"DO_NOT_LOG"})
        with patch.object(m.time,"sleep") as sleep:
            with self.assertRaisesRegex(m.MailSheetsReadError,
                    "phase=KEY_SCAN rows=10000 failure=HTTP_403") as cm:
                m.get_json(session,"https://private.invalid/SECRET","KEY_SCAN",10000)
        self.assertNotIn("SECRET",str(cm.exception))
        self.assertFalse(cm.exception.can_split)
        session.get.assert_called_once()
        sleep.assert_not_called()

    def test_transient_quota_retries_then_succeeds(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.side_effect=[self.Response(429),self.Response(200,{"valueRanges":[]})]
        with patch.object(m.time,"sleep") as sleep:
            self.assertEqual(m.get_json(session,"synthetic","PAYLOAD",2000),{"valueRanges":[]})
        self.assertEqual(session.get.call_count,2)
        sleep.assert_called_once_with(65)

    def test_quota_retry_after_respected(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.side_effect=[self.Response(429,headers={"Retry-After":"90"}),
                                 self.Response(200,{})]
        with patch.object(m.time,"sleep") as sleep:
            self.assertEqual(m.get_json(session,"synthetic","PAYLOAD",2000),{})
        sleep.assert_called_once_with(90)

    def test_quota_retry_after_over_budget_stops_without_split(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.return_value=self.Response(429,headers={"Retry-After":"181"})
        with patch.object(m.time,"sleep") as sleep:
            with self.assertRaisesRegex(m.MailSheetsReadError,"HTTP_429_RETRY_AFTER_BOUND") as cm:
                m.get_json(session,"synthetic","PAYLOAD",2000)
        self.assertFalse(cm.exception.can_split)
        session.get.assert_called_once()
        sleep.assert_not_called()

    def test_quota_retry_after_date_and_invalid_header(self):
        from email.utils import format_datetime
        import datetime as dt
        until=dt.datetime.now(dt.timezone.utc)+dt.timedelta(seconds=100)
        delay=m.quota_cooldown(self.Response(429,headers={"Retry-After":format_datetime(until)}))
        self.assertGreater(delay,65)
        self.assertLessEqual(delay,100)
        for raw in ("invalid", "1", ""):
            self.assertEqual(m.quota_cooldown(self.Response(429,headers={"Retry-After":raw})),65)

    def test_pacer_spaces_requests_without_sleep_after_slow_response(self):
        from unittest.mock import Mock
        now=[0.0]
        def advance(seconds):
            now[0]+=seconds
        with patch.object(m.time,"monotonic",side_effect=lambda:now[0]), \
                patch.object(m.time,"sleep",side_effect=advance) as sleep:
            pacer=m.ReadPacer()
            pacer.wait()
            pacer.wait()
            self.assertEqual(now[0],2.0)
            now[0]+=5
            pacer.wait()
            sleep.assert_called_once_with(2.0)

    def test_every_get_attempt_is_paced(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.side_effect=[self.Response(503),self.Response(429),self.Response(200,{})]
        pacer=Mock()
        with patch.object(m.time,"sleep") as sleep:
            self.assertEqual(m.get_json(session,"synthetic","PAYLOAD",2000,pacer),{})
        self.assertEqual(pacer.wait.call_count,3)
        self.assertEqual(session.get.call_count,3)
        self.assertEqual([call.args[0] for call in sleep.call_args_list],[2,65])

    def test_transport_failure_retries_without_leaking_details(self):
        from unittest.mock import Mock
        session=Mock()
        session.get.side_effect=OSError("SECRET_URL")
        with patch.object(m.time,"sleep") as sleep:
            with self.assertRaisesRegex(m.MailSheetsReadError,"failure=TRANSPORT") as cm:
                m.get_json(session,"synthetic","PAYLOAD",2000)
        self.assertTrue(cm.exception.can_split)
        self.assertNotIn("SECRET_URL",str(cm.exception))
        self.assertEqual(session.get.call_count,3)
        self.assertEqual(sleep.call_count,2)

    def test_invalid_json_is_not_accepted(self):
        from unittest.mock import Mock
        session=Mock()
        for payload,code in ((ValueError("SECRET"),"INVALID_JSON"),([], "INVALID_JSON_SHAPE")):
            session.get.return_value=self.Response(200,payload)
            with self.assertRaisesRegex(m.MailSheetsReadError,"failure="+code) as cm:
                m.get_json(session,"synthetic","META")
            self.assertFalse(cm.exception.can_split)
            self.assertNotIn("SECRET",str(cm.exception))

    def test_split_preserves_contiguous_rows_and_column_ranges(self):
        calls=[]
        def read(ranges,phase,rows):
            calls.append((ranges,phase,rows))
            if rows>250:
                raise m.MailSheetsReadError(phase,rows,"HTTP_413",True)
            return [[["ok"]],[]]
        batches=list(m.bounded_reads(read,"PAYLOAD",2,501,(("A","I"),("K","M"))))
        self.assertEqual([(a,b) for a,b,_ in batches],[(2,251),(252,501)])
        self.assertEqual(calls[1][0],["A2:I251","K2:M251"])
        self.assertEqual(calls[2][0],["A252:I501","K252:M501"])

    def test_quota_or_auth_error_never_splits(self):
        from unittest.mock import Mock
        for status in (403,429):
            read=Mock(side_effect=m.MailSheetsReadError("KEY_SCAN",10000,"HTTP_"+str(status)))
            with self.assertRaises(m.MailSheetsReadError):
                list(m.bounded_reads(read,"KEY_SCAN",2,10001,(("A","B"),)))
            read.assert_called_once()

    def test_split_bound_fails_instead_of_truncating(self):
        from unittest.mock import Mock
        read=Mock(side_effect=m.MailSheetsReadError("PAYLOAD",2000,"HTTP_504",True))
        with self.assertRaises(m.MailSheetsReadError):
            list(m.bounded_reads(read,"PAYLOAD",2,2001,(("A","I"),)))
        self.assertEqual(read.call_count,m.MAX_SPLIT_DEPTH+1)

    def test_failed_right_half_does_not_silently_pass(self):
        def read(ranges,phase,rows):
            if rows>250:
                raise m.MailSheetsReadError(phase,rows,"HTTP_413",True)
            if ranges[0].startswith("A252:"):
                raise m.MailSheetsReadError(phase,rows,"HTTP_403")
            return [[["ok"]]]
        with self.assertRaisesRegex(m.MailSheetsReadError,"HTTP_403"):
            list(m.bounded_reads(read,"PAYLOAD",2,501,(("A","I"),)))

class MailOnlyReferenceTests(unittest.TestCase):
    def result(self,rows,table=None,source=None):
        return m.audit(rows,table if table is not None else tables(),
                       source if source is not None else sources())["mail_only_reference_audit"]

    def test_singleton_typed_refs_and_untyped_invoice_separation(self):
        row=canonical(subject="X209SC26000001-Z03 CMS 209126000001 Invoice 209126000002",
                      sam_numbers="SAM20260000001",invoice_numbers="209126000003",
                      received_at="2025-06-01T10:00:00+09:00")
        out=self.result([row])
        self.assertEqual(out["mail_only_amea"],1)
        self.assertEqual(out["candidate_partition"],{"EXACT_X_LITERAL_COOBSERVATION":1})
        self.assertEqual(out["amea_with_typed_coobservations"],{
            "H":1,"SAM":1,"X_PROJECT":1,"EXPLICIT_CMS_NUMBER":1,
            "INVOICE_LABELLED_NUMBER":1,"STRUCTURED_INVOICE_NUMBER":1})
        self.assertEqual(out["latest_parseable_mail_date_year_counts"],{"2025":1})
        self.assertEqual(out["invoice_number_cms_crosswalk"],"NOT_INFERRED")
        for value in (P,H,"209126000001",MID):
            self.assertNotIn(value,json.dumps(out))

    def test_multi_amea_does_not_cross_join_h_sam_or_x(self):
        out=self.result([canonical(amea_numbers=P+";"+Q,
                                    subject="X209SC26000001-Z01",sam_numbers="SAM20260000001")])
        self.assertEqual(out["candidate_partition"],{"AMBIGUOUS_OR_FORMAT_REVIEW_ONLY":2})
        self.assertEqual(out["amea_with_typed_coobservations"],{})
        self.assertEqual(out["review_and_evidence_flags"]["MULTIPLE_AMEA_ROW_REVIEW"],2)

    def test_subject_only_and_qq_only_members_are_included(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":OTHER,"Subject":Q+" QID-2026-000001"}]
        out=self.result([canonical(amea_numbers="",h_project_numbers="",subject=P)],t)
        self.assertEqual(out["mail_only_amea"],2)
        self.assertEqual(out["candidate_partition"],{"SINGLE_AMEA_NO_OTHER_CLEAN_REFERENCE":1,
                                                     "QID_LITERAL_COOBSERVATION":1})
        self.assertEqual(out["source_population"],{"STAGING":1,m.QQ:1})

    def test_exact_tuple_conflicting_amea_excludes_both_clean_edges(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"AMEA":Q,"H Project":H}]
        out=self.result([canonical()],t)
        self.assertEqual(out["candidate_partition"],{"AMBIGUOUS_OR_FORMAT_REVIEW_ONLY":2})
        self.assertEqual(out["review_and_evidence_flags"]["EXACT_TUPLE_AMEA_DIFFERENCE_REVIEW"],2)
        self.assertEqual(out["amea_with_typed_coobservations"],{})

    def test_exact_tuple_match_is_one_key_not_independent_evidence(self):
        t=tables()
        t[m.QQ]=[{"Mail Key":KEY,"AMEA":P,"H Project":H,"Message ID":MID}]
        out=self.result([canonical()],t)
        self.assertEqual(out["source_surfaces_per_amea"],{"2":1})
        self.assertNotIn("MULTIPLE_SINGLETON_RECORD_KEYS_NOT_INDEPENDENCE_PROOF",
                         out["review_and_evidence_flags"])
        self.assertEqual(out["candidate_partition"],{"H_OR_SAM_LITERAL_COOBSERVATION":1})

    def test_other_amea_h_root_and_known_project_do_not_merge(self):
        s=sources()
        s["CSS Project Dashboard"]=[{"project_id":Q,"h_project_numbers":H+"-B01","sam_numbers":""}]
        out=self.result([canonical(h_project_numbers=H+"-B02")],source=s)
        self.assertEqual(out["mail_only_amea"],1)
        self.assertEqual(out["review_and_evidence_flags"]["OTHER_AMEA_H_ROOT_REVIEW"],1)
        self.assertNotIn("OTHER_AMEA_TYPED_LITERAL_REVIEW",out["review_and_evidence_flags"])

    def test_malformed_related_field_and_bare_numeric_subject_not_promoted(self):
        out=self.result([canonical(h_project_numbers=H+";bad",subject="phone 209126000001")])
        self.assertEqual(out["candidate_partition"],{"SINGLE_AMEA_NO_OTHER_CLEAN_REFERENCE":1})
        self.assertEqual(out["amea_with_typed_coobservations"],{})
        self.assertEqual(out["review_and_evidence_flags"]["RELATED_FIELD_REVIEW"],1)

if __name__=="__main__":
    unittest.main()
