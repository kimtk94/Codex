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
        self.assertEqual(rows[0]["projection_health"],"LIMITED_OBSERVED_CHECKS_PASS")
        self.assertEqual(rows[0]["source_metadata_status"],"WITHIN_CHECKED_METADATA_LIMITS")
        self.assertEqual(rows[0]["review_basis"],"NO_OBSERVED_REVIEW")
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
        summary, rows = inspect(r=r)
        row = rows[0]
        warning = "REVIEW_QUOTE_REPORT_RECEIPT_METADATA"
        self.assertIn(warning, row["reasons"])
        self.assertIn(warning, row["source_metadata_reasons"])
        self.assertNotIn(warning, row["projection_reasons"])
        self.assertEqual(row["health"], "REVIEW")
        self.assertEqual(row["projection_health"], "LIMITED_OBSERVED_CHECKS_PASS")
        self.assertEqual(row["source_metadata_status"], "ADVISORY_REVIEW")
        self.assertEqual(summary["review_basis_counts"], {"SOURCE_METADATA_ONLY": 1})

    def test_shared_report_warning_does_not_hide_project_review_or_carryover(self):
        t = fixture()
        t[h.BOARD].extend([board(Q), board("AMEA2026000003", **{h.COVERAGE: "CARRYOVER_REVIEW"})])
        r = reports()
        r[-1]["Source Received KST"] = "2026-11-23 10:00:00 KST"
        summary, rows = inspect(t, r=r)
        self.assertEqual(summary["project_counts"], {"REVIEW": 2, "NOT_CURRENT_OR_UNCLASSIFIED": 1})
        self.assertEqual(summary["projection_counts"], {"LIMITED_OBSERVED_CHECKS_PASS": 1,
                         "REVIEW": 1, "NOT_CURRENT_OR_UNCLASSIFIED": 1})
        self.assertEqual(summary["review_basis_counts"], {"SOURCE_METADATA_ONLY": 1,
                         "BOTH": 1, "NOT_ASSESSED": 1})
        self.assertEqual(summary["source_metadata_reason_counts"], {"REVIEW_QUOTE_REPORT_RECEIPT_METADATA": 2})
        self.assertIn("REVIEW_X_CHAIN", rows[1]["projection_reasons"])
        self.assertEqual(rows[2]["source_metadata_status"], "NOT_ASSESSED")
        self.assertEqual(sum(summary["review_basis_counts"].values()), len(t[h.BOARD]))

    def test_source_review_does_not_downgrade_conflict(self):
        t = fixture()
        t[h.PO] = [direct_po(**{"Submission Inference": "CONFLICT_REVIEW"})]
        summary, rows = inspect(t, m=[])
        row = rows[0]
        self.assertEqual(row["health"], "CONFLICT_REVIEW")
        self.assertEqual(row["projection_health"], "CONFLICT_REVIEW")
        self.assertEqual(row["review_basis"], "BOTH")
        self.assertIn("CONFLICT_PO_NOTICE", row["projection_reasons"])
        self.assertIn("REVIEW_ONLINE_MIRROR_METADATA", row["source_metadata_reasons"])

    def test_finance_metadata_scope_and_other_source_warnings(self):
        m = [row for row in manifest() if row["Source"] not in {"Payment Outstanding", "Prepayments"}]
        row = inspect(m=m)[1][0]
        self.assertNotIn("REVIEW_FINANCE_MIRROR_METADATA", row["source_metadata_reasons"])
        self.assertIn("REVIEW_PREPAYMENT_MIRROR_METADATA", row["source_metadata_reasons"])
        t = fixture()
        payment(t)
        row = inspect(t, m=m)[1][0]
        self.assertIn("REVIEW_FINANCE_MIRROR_METADATA", row["source_metadata_reasons"])
        self.assertNotIn("REVIEW_FINANCE_MIRROR_METADATA", row["projection_reasons"])

    def test_archive_missing_metadata_and_observed_snapshot_mismatch_are_separate(self):
        t = fixture()
        payment(t, "PAID_ARCHIVED")
        m = [row for row in manifest() if row["Source"] != "Payment Receipt"]
        row = inspect(t, m=m)[1][0]
        self.assertIn("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT", row["source_metadata_reasons"])
        self.assertNotIn("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT", row["projection_reasons"])
        self.assertEqual(row["invoice"], "INVOICE_OR_RECEIPT_REVIEW")
        t[h.BOARD][0]["Outstanding Source Snapshot Date"] = "2026-11-20"
        row = inspect(t, m=m)[1][0]
        self.assertIn("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT", row["projection_reasons"])
        self.assertIn("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT", row["source_metadata_reasons"])
        self.assertEqual(row["reasons"].count("REVIEW_ARCHIVE_RECEIPT_SNAPSHOT"), 1)

    def test_project_only_without_global_metadata_warning(self):
        t = fixture()
        t[h.LINKS] = []
        summary, rows = inspect(t)
        self.assertEqual(rows[0]["review_basis"], "PROJECT_ONLY")
        self.assertEqual(summary["projection_counts"], {"REVIEW": 1})
        self.assertEqual(summary["source_metadata_reason_counts"], {})


class OwnerScopeCoverageTests(unittest.TestCase):
    def test_owner_scope_partitions_and_no_private_identifiers(self):
        t = fixture()
        t[h.REGISTRY][0]["Owner Scope"] = "MY_VERIFIED"
        outside = registry(X2, Q)
        outside["Owner Scope"] = "OTHER_SALES"
        t[h.REGISTRY].append(outside)
        missing = registry("X209SC26000003", "")
        missing["Owner Scope"] = "private-provider-value"
        t[h.REGISTRY].append(missing)
        t[h.INVOICE] = [
            {"Source Key": "INVOICE:" + CMS, "CMS Invoice": CMS,
             "AMEA": Q, "X Base": "X209SC26000999", "X Project": "",
             "Owner Scope": "MY_VERIFIED", "Invoice Link State": "X_NOT_IN_ONLINE",
             "Record State": "CURRENT"},
            {"Source Key": "INVOICE:209126000002", "CMS Invoice": "209126000002",
             "AMEA": Q, "X Base": "X209SC26000001", "X Project": X2,
             "Owner Scope": "OTHER_SALES", "Invoice Link State": "EXACT_X_AMEA_CMS",
             "Record State": "CURRENT"},
            {"Source Key": "INVOICE:209126000003", "CMS Invoice": "209126000003",
             "AMEA": Q, "Owner Scope": "OWNER_UNVERIFIED",
             "Invoice Link State": "private-provider-value", "Record State": "CURRENT"},
        ]
        before = copy.deepcopy(t)
        summary, _ = inspect(t)
        cov = summary["board_coverage_by_owner"]
        self.assertEqual(summary["unassigned_current_x"], 2)
        self.assertEqual(summary["unassigned_current_invoices"], 3)
        self.assertEqual(cov["x"]["board_present"], 1)
        self.assertEqual(cov["x"]["board_absent_by_owner_scope"]["MY_VERIFIED"]["records"], 0)
        self.assertEqual(cov["x"]["board_absent_by_owner_scope"]["OTHER_SALES"]["records"], 1)
        self.assertEqual(cov["x"]["board_absent_by_owner_scope"]["UNCLASSIFIED"]["board_relation_counts"],
                         {"AMEA_EMPTY": 1})
        own = cov["invoice"]["board_absent_by_owner_scope"]["MY_VERIFIED"]
        self.assertEqual(own["distinct_valid_amea"], 1)
        self.assertEqual(own["registry_relation_counts"], {"X_BASE_NOT_IN_CURRENT_REGISTRY": 1})
        self.assertEqual(cov["invoice"]["board_absent_by_owner_scope"]["OTHER_SALES"]["registry_relation_counts"],
                         {"X_WITHOUT_BOARD_AMEA": 1})
        self.assertEqual(cov["invoice"]["board_absent_by_owner_scope"]["OWNER_UNVERIFIED"]["link_state_counts"],
                         {"UNCLASSIFIED": 1})
        self.assertEqual(sum(v["records"] for v in cov["invoice"]["board_absent_by_owner_scope"].values()), 3)
        self.assertEqual(t, before)
        for forbidden in (P, Q, X, CMS, "private-provider-value"):
            self.assertNotIn(forbidden, json.dumps(cov))

    def test_invoice_registry_candidates_are_not_exact_links(self):
        pids = {P: board()}
        r = registry()
        r["Owner Scope"] = "MY_VERIFIED"
        regs = {X: r}
        base = "X209SC26000001"
        invoice = {"AMEA": Q, "X Base": base, "X Project": "", "Owner Scope": "MY_VERIFIED"}
        def category():
            out = h.orphan_scope_counts(pids, regs, {CMS: invoice})
            return out["invoice"]["board_absent_by_owner_scope"]["MY_VERIFIED"]["registry_relation_counts"]
        self.assertEqual(category(), {"X_BASE_ONE_CURRENT_CANDIDATE": 1})
        regs[X2] = registry(X2)
        self.assertEqual(category(), {"X_BASE_MULTIPLE_CURRENT_CANDIDATES": 1})
        invoice["X Project"] = X
        self.assertEqual(category(), {"X_AMEA_DISAGREEMENT": 1})
        invoice["X Project"] = ""
        invoice["X Base"] = X
        self.assertEqual(category(), {"X_BASE_FORMAT_REVIEW": 1})
        invoice["X Base"] = ""
        self.assertEqual(category(), {"X_BASE_NOT_OBSERVED": 1})

    def test_retained_records_excluded_and_unknown_scope_not_other_sales(self):
        t = fixture()
        orphan = registry(X2, Q)
        orphan["Owner Scope"] = "OWNER_UNVERIFIED"
        t[h.REGISTRY].append(orphan)
        retained = registry("X209SC26000003", Q)
        retained["Record State"] = "SOURCE_NOT_IN_LATEST"
        retained["Owner Scope"] = "MY_VERIFIED"
        t[h.REGISTRY].append(retained)
        cov = inspect(t)[0]["board_coverage_by_owner"]["x"]
        self.assertEqual(cov["current_records"], 2)
        self.assertEqual(cov["board_absent"], 1)
        self.assertEqual(cov["board_absent_by_owner_scope"]["OWNER_UNVERIFIED"]["records"], 1)
        self.assertEqual(cov["board_absent_by_owner_scope"]["MY_VERIFIED"]["records"], 0)


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

    def test_declared_total_over_bound_stops_immediately(self):
        calls = []
        def api(method, path, token, action):
            calls.append(method)
            return {"items": [{}], "has_more": True, "page_token": "next",
                    "total": h.DEFAULT_MAX_PAGES * h.PAGE_SIZE + 1}
        with self.assertRaisesRegex(h.HealthError, "BOUND_EXCEEDED"):
            h.strict_pages(api, "token", "/records", "test")
        self.assertEqual(calls, ["GET"])

    def test_large_mail_identity_is_read_in_full_not_truncated(self):
        # Synthetic ledger above the old 20,000-row ceiling; no real mail.
        import urllib.parse
        total = 31500
        source = fixture()
        ids = {name:(h.PROJECT_BOARD if name==h.BOARD else "tblTest"+str(i))
               for i,name in enumerate(h.SCHEMAS)}
        calls = []
        def api(method, path, token, action):
            self.assertEqual(method,"GET")
            p, query = path.split("?", 1)
            params = urllib.parse.parse_qs(query)
            if p == "/root/tables":
                rows = [{"name":n, "table_id":tid} for n,tid in ids.items()]
            else:
                name = next(n for n,tid in ids.items() if "/"+tid+"/" in p)
                if p.endswith("/fields"):
                    rows = [{"field_name":k,"type":2 if k in h.NUMERIC_FIELDS else 1}
                            for k in h.SCHEMAS[name]]
                elif name == h.MAIL:
                    calls.append(method)
                    start = int(params.get("page_token", ["0"])[0])
                    size = int(params["page_size"][0])
                    self.assertEqual(size, h.PAGE_SIZE)
                    end = min(start + size, total)
                    rows = [{"record_id":"rec"+str(i),
                             "fields":{"Mail Key":format(i,"064x"),"Project ID":P}}
                            for i in range(start,end)]
                    return {"items":rows,"has_more":end<total,
                            "page_token":str(end),"total":total}
                else:
                    rows = [{"record_id":"rec"+str(i),"fields":r}
                            for i,r in enumerate(source[name])]
            return {"items":rows,"has_more":False,"total":len(rows)}
        data = h.read_tables(api,"token","/root")
        self.assertEqual(len(data[h.MAIL]),total)
        self.assertEqual(len(calls),315)
        self.assertEqual(data[h.MAIL][-1]["Mail Key"],format(total-1,"064x"))

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
