import copy
import datetime as dt
import json
import unittest
import statement_issuance_forecast as m

X="X209SC26000001-Z01"
J="J001-"+X
J2="J002-"+X
AMEA="AMEA2026000001"
NOTICE="Notice: Final Report & Statement Ready for Confirmation "
ISSUE="Notice: Invoice Issued & Statement Confirmed "
NOW=dt.datetime(2026,11,30,12,tzinfo=m.KST)

def mail(j=J, date="2026-11-28T10:00:00+09:00", uid="100", subject=None, **kw):
    return {**{"ingest_key":"key-"+uid,"imap_uid":uid,"folder":"INBOX","uidvalidity":"1",
               "received_at":date,"from_email":"css@novogene-amea.com","subject":subject or NOTICE+j,
               "direction":"INBOUND","in_reply_to":""},**kw}

def amount(j=J,date="2026-11-28T10:00:00+09:00",uid="100",krw=11000):
    return {"statement_key":j,"project_x":j[5:],"statement_no":j[:4],"amount_krw":krw,
            "currency":"KRW","notice_at":date,"imap_uid":uid,"uidvalidity":"1",
            "validation_status":"AMOUNT_VERIFIED","subject":NOTICE+j}

def project(x=X,krw=10000,month="2026-11",**kw):
    return {**{"Project / Sub-project":x,"AMEA":AMEA,"Expected Revenue Month":month,
               "Invoice Count":0,"Billing Classification":"PROJECT FORECAST",
               "Estimated KRW (existing)":krw,"Open Statement Numbers":"","Latest Statement Notice":""},**kw}

def invoice(j=J,krw=11000,ident="209126000001"):
    return {"invoice_number":ident,"amount_krw":krw,"attachment_filename":
            f"Tax Invoice-{ident}-H209SC26000001-PO1-{AMEA}-KRW{krw}.pdf",
            "subject":ISSUE+j,"received_at":"2026-11-29T10:00:00+09:00",
            "imap_uid":"110","validation_status":"FILENAME_PARSED"}

def src():
    return {k:[] for k in m.SPECS}

class StatementForecastTests(unittest.TestCase):
    def test_month_rollover_and_replace_without_vat_mix(self):
        s=src()
        s[m.MAIL]=[mail()]
        s[m.STATEMENT]=[amount()]
        s[m.PROJECT]=[project()]
        s[m.MONTHLY]=[{"Month":"2026-11","Forecast KRW":10000,"Forecast Projects":1,
                       "Open Statement Count":0,"Pending Verified KRW":0,
                       "Snapshot KST":"2026-11-30 09:00:00 KST"}]
        before=copy.deepcopy(s)
        out,details=m.audit(s,NOW)
        self.assertEqual(details["statement_members"][0]["estimated_auto_issue_date"],"2026-12-03")
        self.assertTrue(out["months"]["2026-11"]["published_forecast_parity"])
        self.assertEqual(out["months"]["2026-11"]["general_forecast_after_statement_hold"]["krw"],0)
        self.assertEqual(out["months"]["2026-11"]["held_project_estimate_not_added_to_statement"]["krw"],10000)
        self.assertEqual(out["months"]["2026-12"]["statement_expected_by_issue_month"]["verified_amount_krw_vat_basis_unknown"],11000)
        self.assertEqual(out["business_writes"],0)
        self.assertEqual(s,before)
        self.assertNotIn(J,json.dumps(out))

    def test_pending_unknown_mail_only_is_not_zero_or_dropped(self):
        s=src();s[m.MAIL]=[mail(date="2026-11-20T10:00:00+09:00")]
        out,details=m.audit(s,NOW)
        self.assertEqual(out["pending_without_lifecycle"],1)
        self.assertEqual(out["months"]["2026-11"]["statement_expected_by_issue_month"]["amount_unknown_count"],1)
        self.assertEqual(details["statement_members"][0]["due_state"],"DUE_OR_PAST_DATE")
        self.assertIsNone(details["statement_members"][0]["verified_statement_krw_vat_basis_unknown"])

    def test_issue_notice_without_extract_not_pending(self):
        s=src();s[m.MAIL]=[mail(),mail(uid="101",date="2026-11-29T10:00:00+09:00",subject=ISSUE+J)]
        s[m.STATEMENT]=[amount()];s[m.PROJECT]=[project()]
        out,details=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{"ISSUE_NOTICE_AMOUNT_REVIEW":1})
        self.assertEqual(out["baseline_forecast_held_x"],1)
        self.assertEqual(out["active_pending_x"],0)

    def test_invoice_only_holds_stale_general_forecast(self):
        s=src();s[m.INVOICE]=[invoice()];s[m.PROJECT]=[project()]
        out,details=m.audit(s,NOW)
        self.assertEqual(out["statement_source_keys"],0)
        self.assertEqual(out["billing_evidence_keys"],1)
        self.assertEqual(out["verified_invoice_keys_without_ready_notice"],1)
        self.assertEqual(out["statement_states"],{"ISSUED_VERIFIED":1})
        self.assertEqual(out["baseline_forecast_held_x"],1)
        self.assertEqual(out["months"]["2026-11"]["general_forecast_after_statement_hold"]["krw"],0)
        self.assertEqual(out["months"]["2026-11"]["held_project_estimate_not_added_to_statement"]["krw"],10000)
        self.assertEqual(details["statement_members"][0]["invoice_count"],1)
        self.assertEqual(details["statement_members"][0]["expected_issue_month"],"")
        self.assertIsNone(details["statement_members"][0]["verified_statement_krw_vat_basis_unknown"])
        self.assertEqual(out["active_pending_x"],0)

    def test_issue_notice_only_holds_forecast_without_inventing_amount(self):
        s=src();s[m.MAIL]=[mail(subject=ISSUE+J)];s[m.PROJECT]=[project()]
        out,d=m.audit(s,NOW)
        self.assertEqual(out["issue_notice_keys_without_ready_notice"],1)
        self.assertEqual(out["evidence_only_keys_without_ready_or_open_projection"],1)
        self.assertEqual(out["statement_states"],{"ISSUE_NOTICE_AMOUNT_REVIEW":1})
        self.assertEqual(out["baseline_forecast_held_x"],1)
        self.assertEqual(out["active_pending_x"],0)
        self.assertEqual(d["statement_members"][0]["invoice_count"],0)
        self.assertIsNone(d["statement_members"][0]["verified_statement_krw_vat_basis_unknown"])

    def test_cancel_only_is_review_not_pending(self):
        s=src();s[m.MAIL]=[mail(subject="Notice: Statement cancelled "+J)]
        s[m.PROJECT]=[project()]
        out,_=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{"CANCELLATION_REVIEW":1})
        self.assertEqual(out["active_pending_x"],0)
        self.assertEqual(out["baseline_forecast_held_x"],1)

    def test_issue_and_invoice_only_same_key_deduplicated(self):
        s=src();s[m.MAIL]=[mail(subject=ISSUE+J)]
        s[m.INVOICE]=[invoice()];s[m.PROJECT]=[project()]
        out,d=m.audit(s,NOW)
        self.assertEqual(out["billing_evidence_keys"],1)
        self.assertEqual(out["statement_states"],{"ISSUED_VERIFIED":1})
        self.assertEqual(len(d["statement_members"]),1)

    def test_invoice_only_does_not_hold_unrelated_exact_x(self):
        s=src();s[m.INVOICE]=[invoice()]
        s[m.PROJECT]=[project(),project(x="X209SC26000001-Z02",krw=20000)]
        out,_=m.audit(s,NOW)
        self.assertEqual(out["baseline_forecast_held_x"],1)
        self.assertEqual(out["months"]["2026-11"]["general_forecast_after_statement_hold"]["krw"],20000)

    def test_future_invoice_not_counted_as_observed_issue(self):
        s=src();s[m.INVOICE]=[dict(invoice(),received_at="2026-12-01T10:00:00+09:00")]
        s[m.PROJECT]=[project()]
        out,_=m.audit(s,NOW)
        self.assertEqual(out["source_review"]["INVOICE_AFTER_AS_OF"],1)
        self.assertEqual(out["billing_evidence_keys"],0)
        self.assertEqual(out["baseline_forecast_held_x"],0)
        self.assertEqual(out["months"]["2026-11"]["general_forecast_after_statement_hold"]["krw"],10000)

    def test_issued_and_separate_j_preserved(self):
        s=src();s[m.MAIL]=[mail(),mail(j=J2,uid="102")]
        s[m.STATEMENT]=[amount(),amount(j=J2,uid="102",krw=22000)]
        s[m.INVOICE]=[invoice()]
        s[m.PROJECT]=[project(**{"Invoice Count":1,"Billing Classification":"ISSUED (BALANCE UNVERIFIED)"})]
        out,details=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{"ISSUED_VERIFIED":1,"STATEMENT_PENDING_VERIFIED_AMOUNT":1})
        self.assertEqual(out["months"]["2026-12"]["statement_expected_by_issue_month"]["verified_amount_krw_vat_basis_unknown"],22000)

    def test_revision_and_duplicate_notice_do_not_silently_reuse_amount(self):
        s=src();s[m.MAIL]=[mail(),mail(uid="101",date="2026-11-29T10:00:00+09:00")]
        s[m.STATEMENT]=[amount()]
        out,d=m.audit(s,NOW)
        self.assertEqual(d["statement_members"][0]["estimated_auto_issue_date"],"2026-12-03")
        self.assertEqual(out["statement_states"],{"STATEMENT_PENDING_AMOUNT_UNKNOWN":1})
        s[m.MAIL][1]["subject"]="Notice: Revised Statement "+J
        out,d=m.audit(s,NOW)
        self.assertEqual(d["statement_members"][0]["estimated_auto_issue_date"],"2026-12-04")
        self.assertTrue(d["statement_members"][0]["revised_notice_observed"])

    def test_wrong_uid_or_reply_cannot_verify_pending(self):
        s=src();s[m.MAIL]=[mail()];s[m.STATEMENT]=[amount(uid="999")]
        out,_=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{"STATEMENT_PENDING_AMOUNT_UNKNOWN":1})
        s[m.MAIL]=[mail(in_reply_to="reply")];out,_=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{})
        self.assertEqual(out["source_review"]["AMOUNT_REFERENCE_WITHOUT_NOTICE_OR_INVOICE"],1)

    def test_cancellation_and_existing_lifecycle_missing_notice_held(self):
        s=src();s[m.MAIL]=[mail(),mail(uid="101",date="2026-11-29T10:00:00+09:00",subject="Notice: Statement cancelled "+J)]
        s[m.PROJECT]=[project(**{"Open Statement Numbers":"J002"})]
        out,_=m.audit(s,NOW)
        self.assertEqual(out["statement_states"],{"CANCELLATION_REVIEW":1,"DIRECT_NOTICE_MISSING_REVIEW":1})

    def test_conflicting_invoice_key_and_amount_fail(self):
        s=src();s[m.MAIL]=[mail(),mail(j=J2,uid="101")];s[m.INVOICE]=[invoice(),invoice(j=J2)]
        with self.assertRaisesRegex(m.ReviewError,"INVOICE_IDENTITY_CONFLICT"):
            m.audit(s,NOW)

if __name__=="__main__":
    unittest.main()
