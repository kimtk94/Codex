"""Offline synthetic tests; no Feishu/Sheets/QQ calls or customer data."""
import copy
import datetime as dt
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import project_health_check as h

NOW = dt.datetime(2026, 11, 24, 12, tzinfo=h.KST)
P = "AMEA2026000001"
Q = "AMEA2026000002"
H = "H209SC26000001"
X = "X209SC26000001-Z01"
X2 = "X209SC26000001-Z02"
SAM = "SAM20260000001"
CMS = "209126000001"
KEY = "a" * 64


def board(pid=P, **fields):
    return {"Source Key": "PROJECT:"+pid, "AMEA": pid,
            h.COVERAGE: h.CURRENT, "PM Data Check": "CHECKED",
            "PM Quote Link": "EXACT_QUOTE_SNAPSHOT",
            "PM X Link": "EXACT_LIFECYCLE_ONLY",
            "Workflow Lane": "PRODUCTION_ACTIVE", **fields}


def link(kind, state, amea="", contract="", x="", sam=""):
    return {"Source Key":"LINK:"+kind+":"+":".join(v for v in (amea,contract,x,sam) if v),
            "Link Type":kind, "Link State":state, "AMEA":amea,
            "H Contract":contract, "X Project":x, "SAM":sam,
            "Record State":"CURRENT"}


def registry(x=X, pid=P, contract=H, state="EXACT_LIFECYCLE"):
    return {"Source Key":"X:"+x, "X Project":x, "H Contract":contract,
            "AMEA":pid, "AMEA Link State":state, "Record State":"CURRENT"}


def fixture():
    return {
        h.BOARD:[board()],
        h.REGISTRY:[registry()],
        h.LINKS:[
            link("AMEA_H","EXACT_CSS",P,H),
            link("H_X","EXACT_FEISHU_ONLINE",contract=H,x=X),
            link("AMEA_X","EXACT_LIFECYCLE",P,H,X),
            link("AMEA_SAM","EXACT_SINGLE_X_CHAIN",P,x=X,sam=SAM),
        ],
        h.INVOICE:[],h.PO:[],h.MAIL:[],
    }


def manifest():
    return [{"Source":name,"Source Date":"2026-11-24","Synced At KST":NOW.isoformat(),
             "Source ID":"synthetic","Rows":"20","Schema":schema}
            for name,(schema,_,_) in h.MIRRORS.items()]


def reports():
    return [{"Entity":entity,"Source Kind":"QQ IMAP","State":"PRESERVED_NO_NEW_REPORT",
             "Content SHA256":KEY,"Source Received KST":"2026-11-24 10:00:00 KST",
             "Ingest Checked KST":"2026-11-24 11:00:00 KST"}
            for entity in ("Leads","Opportunities","Quotation")]


def inspect(t=None,m=None,r=None):
    return h.assess(fixture() if t is None else t,manifest() if m is None else m,
                    reports() if r is None else r,NOW)


def payment(t, lane="PAYMENT_FOLLOWUP", balance="0"):
    t[h.BOARD]=[board(**{"Workflow Lane":lane,"Payment Owner Scope":"MY_VERIFIED",
        "Payment Invoice No":CMS,"Invoice Gross KRW":"1000","Outstanding Balance KRW":balance,
        "Completion Evidence":"CSS_EXPLICIT_FINAL_HANDOFF",
        "Receipt Source":"FEISHU_LATEST_PAYMENT_RECEIPT",
        "Receipt Verification Status":"SOURCE_EXACT_VERIFIED",
        "Receipt Verified By":"AUTO_FEISHU_EXACT_CMS_AMOUNT",
        "Receipt Verified At":"2026-11-24","Bank Receipt Reference":"synthetic-reference",
        "Verified Invoice KRW":"1000","Verified Received KRW":"1000",
        "Receipt Source Snapshot Date":"2026-11-24","Outstanding Source Snapshot Date":"2026-11-24"})]
    t[h.INVOICE]=[{"Source Key":"INVOICE:"+CMS,"CMS Invoice":CMS,"AMEA":P,"X Project":X,
       "Owner Scope":"MY_VERIFIED","Invoice Link State":"EXACT_X_AMEA_CMS",
       "Invoice Gross KRW Incl VAT":"1000","Outstanding Balance KRW":balance,"Record State":"CURRENT"}]


def direct_po(**fields):
    return {"Project ID":P,"Contract Source":"CSS","Contract Mail Key":KEY,
            "Contract Notice UTC":"2026-11-23T00:00:00+00:00",
            "PO Status":"PO_RECEIVED_NOTICE","PO Followup Queue":"PO_FILE_REVIEW",**fields}


class CrosswalkTests(unittest.TestCase):
    def test_limited_pass_and_no_sensitive_summary(self):
        t=fixture()
        t[h.MAIL]=[{"Mail Key":KEY,"Project ID":P,"Project Link":"PROJECT_ID_EXACT",
                    "Review State":"OK","Relationship Status":"LINKED",
                    "Evidence Tier":"EXACT_PROJECT_ONLY","Subject":"private subject"}]
        before=copy.deepcopy(t)
        summary, rows=inspect(t)
        self.assertEqual(rows[0]["health"],"LIMITED_OBSERVED_CHECKS_PASS")
        self.assertEqual(rows[0]["x_chain"],"EXACT_OBSERVED_CHAIN")
        self.assertEqual(rows[0]["sam_exact_count"],1)
        self.assertEqual(rows[0]["mail_exact_count"],1)
        self.assertEqual(rows[0]["po"],"NO_DIRECT_TRACKER_EVIDENCE")
        self.assertEqual(t,before)
        self.assertEqual(summary["business_writes"],0)
        self.assertNotIn(P,json.dumps(summary))
        self.assertNotIn(KEY,json.dumps(summary))
        self.assertNotIn("private subject",json.dumps((summary,rows)))
        self.assertIn("X Registry",summary["source_freshness_unattested"])

    def test_h_only_candidate_does_not_count_as_exact(self):
        t=fixture()
        t[h.REGISTRY]=[registry(state="UNIQUE_H_CANDIDATE")]
        t[h.LINKS][2]["Link State"]="UNIQUE_H_CANDIDATE"
        row=inspect(t)[1][0]
        self.assertEqual(row["x_exact_count"],0)
        self.assertEqual(row["sam_exact_count"],0)
        self.assertEqual(row["health"],"REVIEW")

    def test_shared_h_or_conflicting_h_x_blocks_exact_chain(self):
        for extra in (link("AMEA_H","EXACT_CSS",Q,H),
                      link("H_X","EXACT_FEISHU_ONLINE",contract="H209SC26000002",x=X)):
            t=fixture()
            t[h.LINKS].append(extra)
            row=inspect(t)[1][0]
            self.assertEqual(row["x_chain"],"CONFLICT")
            self.assertIn("CONFLICT_X_PARENT",row["reasons"])

    def test_missing_registry_and_retained_link_excluded(self):
        t=fixture()
        t[h.REGISTRY][0]["Record State"]="SOURCE_NOT_IN_LATEST"
        self.assertIn("REVIEW_X_MISSING_REGISTRY",inspect(t)[1][0]["reasons"])
        t[h.LINKS][2]["Record State"]="SOURCE_NOT_IN_LATEST"
        self.assertEqual(inspect(t)[1][0]["x_exact_count"],0)

    def test_multi_x_never_auto_allocates_sam(self):
        t=fixture()
        t[h.REGISTRY].append(registry(X2))
        t[h.LINKS].extend([link("H_X","EXACT_FEISHU_ONLINE",contract=H,x=X2),
                           link("AMEA_X","EXACT_LIFECYCLE",P,H,X2)])
        row=inspect(t)[1][0]
        self.assertEqual(row["x_exact_count"],2)
        self.assertEqual(row["sam_exact_count"],0)
        self.assertIn("REVIEW_SAM_CHAIN",row["reasons"])

    def test_shared_sam_never_accepted(self):
        t=fixture()
        t[h.LINKS].append(link("AMEA_SAM","EXACT_SINGLE_X_CHAIN",Q,x=X,sam=SAM))
        self.assertEqual(inspect(t)[1][0]["sam_exact_count"],0)

    def test_po_related_scope_is_not_direct_file_proof(self):
        t=fixture()
        t[h.PO]=[direct_po(**{"Project ID":H})]
        self.assertEqual(inspect(t)[1][0]["po"],"RELATED_SCOPE_ONLY")
        t[h.PO]=[direct_po(**{"PO Followup Queue":"PO_SUBMITTED_INFERRED"})]
        self.assertEqual(inspect(t)[1][0]["po"],"DOWNSTREAM_INFERENCE_ONLY")

    def test_po_attestation_and_conflict(self):
        t=fixture()
        verified=direct_po(**{"PO Document Verification":"FILE_VERIFIED",
                              "PO Document Reference":"synthetic-file","PO Verified By":"reviewer",
                              "PO Verified At":"2026-11-24T00:00:00+00:00"})
        t[h.PO]=[verified]
        self.assertEqual(inspect(t)[1][0]["po"],"DIRECT_FILE_ATTESTED")
        verified["Submission Inference"]="CONFLICT_REVIEW"
        self.assertEqual(inspect(t)[1][0]["health"],"CONFLICT_REVIEW")
        verified.pop("Submission Inference")
        verified["PO Verified At"]="2026-11-24"
        self.assertEqual(inspect(t)[1][0]["po"],"INCOMPLETE_FILE_ATTESTATION")

    def test_mail_review_not_unanswered_customer_claim(self):
        t=fixture()
        t[h.MAIL]=[{"Mail Key":KEY,"Project ID":P,"Project Link":"PROJECT_ID_EXACT",
                    "Review State":"REVIEW","Relationship Status":"REVIEW",
                    "Evidence Tier":"CONFLICT_REVIEW"}]
        row=inspect(t)[1][0]
        self.assertEqual(row["mail_exact_count"],0)
        self.assertIn("REVIEW_MAIL_IDENTITY",row["reasons"])

    def test_invoice_set_and_money_agree_but_no_new_paid_decision(self):
        t=fixture()
        payment(t)
        summary, rows=inspect(t)
        self.assertEqual(rows[0]["invoice"],"EXACT_OBSERVED_INVOICE_SET")
        self.assertEqual(rows[0]["health"],"LIMITED_OBSERVED_CHECKS_PASS")
        self.assertNotIn(CMS,json.dumps((summary,rows)))
        self.assertNotIn("1000",json.dumps(rows))
        self.assertEqual(t[h.BOARD][0]["Workflow Lane"],"PAYMENT_FOLLOWUP")

    def test_invoice_set_and_amount_conflicts(self):
        t=fixture()
        payment(t)
        t[h.INVOICE][0]["Invoice Gross KRW Incl VAT"]="900"
        self.assertIn("CONFLICT_INVOICE_GROSS",inspect(t)[1][0]["reasons"])
        t[h.INVOICE][0]["Invoice Gross KRW Incl VAT"]="1000"
        t[h.INVOICE][0]["Outstanding Balance KRW"]="5"
        self.assertIn("CONFLICT_INVOICE_BALANCE",inspect(t)[1][0]["reasons"])
        t[h.INVOICE]=[]
        self.assertIn("REVIEW_INVOICE_SET_OR_CHAIN",inspect(t)[1][0]["reasons"])

    def test_shared_cms_cannot_be_counted_for_two_ameas(self):
        t=fixture()
        payment(t)
        t[h.BOARD].append(board(Q,**{"Payment Owner Scope":"MY_VERIFIED","Payment Invoice No":CMS}))
        rows=inspect(t)[1]
        self.assertTrue(all("CONFLICT_SHARED_BOARD_INVOICE" in r["reasons"] for r in rows))

    def test_blank_balance_is_not_zero(self):
        t=fixture()
        payment(t)
        t[h.INVOICE][0]["Outstanding Balance KRW"]=""
        self.assertIn("REVIEW_INVOICE_BALANCE_COVERAGE",inspect(t)[1][0]["reasons"])

    def test_archive_requires_evidence_and_rechecks_current_balance(self):
        t=fixture()
        payment(t,"PAID_ARCHIVED","5")
        row=inspect(t)[1][0]
        self.assertIn("CONFLICT_ARCHIVE_POSITIVE_BALANCE",row["reasons"])
        t[h.BOARD][0]["Receipt Source Snapshot Date"]="2026-11-20"
        self.assertIn("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT",inspect(t)[1][0]["reasons"])
        t[h.BOARD][0]["Receipt Verification Status"]="UNVERIFIED"
        self.assertIn("REVIEW_ARCHIVE_RECEIPT",inspect(t)[1][0]["reasons"])

    def test_payment_owner_scope_and_carryover(self):
        t=fixture()
        payment(t)
        t[h.BOARD][0]["Payment Owner Scope"]="OTHER_SALES"
        row=inspect(t)[1][0]
        self.assertEqual(row["invoice"],"OUTSIDE_VERIFIED_OWNER_SCOPE")
        self.assertIn("REVIEW_PAYMENT_OWNER_SCOPE",row["reasons"])
        t[h.BOARD][0][h.COVERAGE]="CARRYOVER_REVIEW"
        row=inspect(t)[1][0]
        self.assertEqual(row["health"],"NOT_CURRENT_OR_UNCLASSIFIED")
        self.assertNotIn("invoice",row)

    def test_duplicate_and_bad_identity_refused(self):
        t=fixture()
        t[h.BOARD].append(board())
        with self.assertRaisesRegex(h.HealthError,"DUPLICATE"):
            inspect(t)
        t=fixture()
        t[h.REGISTRY][0]["Source Key"]="X:wrong"
        with self.assertRaisesRegex(h.HealthError,"X_IDENTITY"):
            inspect(t)


class SourceMetadataTests(unittest.TestCase):
    def test_old_source_with_fresh_sync_not_fresh(self):
        m=manifest()
        next(row for row in m if row["Source"]=="Payment Outstanding")["Source Date"]="2026-09-01"
        result=h.manifest_health(m,NOW)
        self.assertEqual(result["Payment Outstanding"]["state"],"OUTSIDE_ADVISORY_LIMIT")
        self.assertEqual(result["Online-Project"]["live_parity"],"NOT_RECHECKED")

    def test_future_or_unzoned_and_duplicate_manifest(self):
        m=manifest()
        m[0]["Synced At KST"]="2026-11-25T12:00:00+09:00"
        self.assertEqual(h.manifest_health(m,NOW)["Online-Project"]["state"],"INVALID_MANIFEST_METADATA")
        m[0]["Synced At KST"]="2026-11-24T12:00:00"
        self.assertEqual(h.manifest_health(m,NOW)["Online-Project"]["state"],"INVALID_MANIFEST_METADATA")
        m.append(m[0].copy())
        self.assertEqual(h.manifest_health(m,NOW)["Online-Project"]["state"],"MISSING_OR_DUPLICATE_MANIFEST")

    def test_sfdc_receipt_age_not_check_age_or_export_date(self):
        r=reports()
        r[-1]["Source Received KST"]="2026-11-23 10:00:00 KST"
        meta=h.sfdc_health(r,NOW)["Quotation"]
        self.assertEqual(meta["state"],"RECEIPT_AGE_OVER_6H")
        self.assertEqual(meta["quote_export_time"],"NOT_ATTESTED")
        self.assertEqual(meta["report_hash"],"NOT_RECOMPUTED")
        self.assertIn("REVIEW_QUOTE_REPORT_RECEIPT_METADATA",inspect(r=r)[1][0]["reasons"])


class ReadOnlyBoundaryTests(unittest.TestCase):
    def test_complete_pagination_and_only_get(self):
        pages=iter([{"items":[{"x":1}],"has_more":True,"page_token":"p2","total":2},
                    {"items":[{"x":2}],"has_more":False,"total":2}])
        def api(method,path,token,action):
            self.assertEqual(method,"GET")
            return next(pages)
        self.assertEqual(len(h.strict_pages(api,"token","/records","test")),2)

    def test_cycle_and_truncated_total_fail_closed(self):
        def loop(method,path,token,action):
            return {"items":[{}],"has_more":True,"page_token":"same"}
        with self.assertRaisesRegex(h.HealthError,"CURSOR"):
            h.strict_pages(loop,"token","/records","test")
        def incomplete(method,path,token,action):
            return {"items":[{}],"has_more":False,"total":2}
        with self.assertRaisesRegex(h.HealthError,"COUNT_MISMATCH"):
            h.strict_pages(incomplete,"token","/records","test")

    def test_catalog_schema_and_record_boundaries(self):
        names={name:(h.PROJECT_BOARD if name==h.BOARD else "tblTest"+str(i))
               for i,name in enumerate(h.SCHEMAS)}
        source=fixture()
        def api(method,path,token,action):
            self.assertEqual(method,"GET")
            p=path.split("?")[0]
            if p=="/root/tables":
                items=[{"name":n,"table_id":tid} for n,tid in names.items()]
            else:
                name=next(n for n,tid in names.items() if "/"+tid+"/" in p)
                if p.endswith("/fields"):
                    items=[{"field_name":k,"type":2 if k in h.NUMERIC_FIELDS else 1}
                           for k in h.SCHEMAS[name]]
                else:
                    items=[{"record_id":"rec"+str(i),"fields":r} for i,r in enumerate(source[name])]
            return {"items":items,"has_more":False,"total":len(items)}
        self.assertEqual(h.read_tables(api,"token","/root")[h.BOARD][0]["AMEA"],P)
        names[h.BOARD]="tblWrong"
        with self.assertRaisesRegex(h.HealthError,"TABLE_ID"):
            h.read_tables(api,"token","/root")

    def test_private_report_never_ci_or_overwrites(self):
        with patch.dict(os.environ,{"GITHUB_ACTIONS":"true"}):
            with self.assertRaisesRegex(h.HealthError,"FORBIDDEN_IN_CI"):
                h.local_report("/tmp/unused",{},[])
        with patch.dict(os.environ,{},clear=True), tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/"private.json"
            h.local_report(str(target),{"test":1},[])
            self.assertEqual(json.loads(target.read_text())["summary"],{"test":1})
            with self.assertRaises(FileExistsError):
                h.local_report(str(target),{},[])
            with self.assertRaisesRegex(h.HealthError,"OUTSIDE_REPO"):
                h.local_report(str(Path(h.__file__).resolve().parent/"forbidden.json"),{},[])


if __name__ == "__main__":
    unittest.main()
