"""Synthetic tests only; no business data or source calls."""
import copy
import json
import unittest
from unittest.mock import patch
import global_relationship_coverage as g

P="AMEA2026000001"
Q="AMEA2026000002"
H="H209SC26000001"
X="X209SC26000001-Z01"
X2="X209SC26000001-Z02"
S="SAM20260000001"
CMS="209126000001"
QID="QID-2026-000001"
QUOTE="a0PAbc123456789"
OPP="OPP-2026-000001"

def rows():
    return {name:[] for name in g.SOURCES}

class CoverageTests(unittest.TestCase):
    def test_literal_keys_not_column_label_or_name(self):
        self.assertEqual(g.keys(QID,"QID"),({("QID",QID)},"OBSERVED"))
        self.assertEqual(g.keys(QID,"AMEA"),(set(),"FORMAT_REVIEW"))
        self.assertEqual(g.keys(QUOTE+"AAA","QUOTE_OBJECT"),({("QUOTE_OBJECT",QUOTE)},"OBSERVED"))
        self.assertEqual(g.keys(QUOTE.upper(),"QUOTE_OBJECT"),(set(),"FORMAT_REVIEW"))
        self.assertEqual(g.keys("006123456789012","OPP_REF"),(set(),"FORMAT_REVIEW"))
        self.assertEqual(g.keys("OPP-2026-1","OPP_ANY"),({("OPP_REF","OPP-2026-1")},"OBSERVED"))

    def test_union_preserves_outside_baseline_without_owner_filter(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S}]
        s["BI Project Lifecycle Overview"]=[{"AMEA":Q,"Project / Sub-project":X}]
        s["Feishu Latest Outstanding"]=[{"Quotation Number":Q,"Project Number":"X209SC26000001",
                                           "CMS Invoice Number":CMS,"Sales":"OTHER_SALES"}]
        before=copy.deepcopy(s)
        out=g.coverage(s)
        self.assertEqual(out["core_amea_union"],2)
        self.assertEqual(out["css_sif_amea_baseline"],1)
        self.assertEqual(out["core_amea_outside_css_sif"],1)
        self.assertEqual(out["observed_reference_edges"]["CMS->AMEA"],1)
        self.assertEqual(out["observed_reference_edges"]["CMS->X_REPORTED"],1)
        self.assertEqual(out["observed_reference_edges"]["X_PROJECT->AMEA"],1)
        self.assertFalse(out["owner_filter_applied"])
        self.assertEqual(out["business_writes"],0)
        self.assertEqual(s,before)
        for ident in (P,Q,X,H,S,CMS):
            self.assertNotIn(ident,json.dumps(out))

    def test_multix_and_multisam_no_cross_product(self):
        s=rows()
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H+";H209SC26000002",
                                      "sam_numbers":S+";SAM20260000002"}]
        s["BI Project Lifecycle Overview"]=[{"AMEA":P,"Project / Sub-project":x} for x in (X,X2)]
        out=g.coverage(s)
        e=out["observed_reference_edges"]
        self.assertEqual(e["AMEA->H"],2)
        self.assertEqual(e["AMEA->SAM"],2)
        self.assertEqual(e["X_PROJECT->AMEA"],2)
        self.assertNotIn("H->SAM",e)
        self.assertNotIn("X_PROJECT->SAM",e)
        self.assertEqual(out["multiple_parent_candidate_review"],{})

    def test_conflicting_amea_preserved_and_reviewed(self):
        s=rows()
        s["BI Project Lifecycle Overview"]=[{"AMEA":a,"Project / Sub-project":X} for a in (P,Q)]
        out=g.coverage(s)
        self.assertEqual(out["observed_reference_edges"]["X_PROJECT->AMEA"],2)
        self.assertEqual(out["multiple_parent_candidate_review"],{"X_PROJECT->AMEA":1})
        self.assertEqual(out["relationship_certification"],"NOT_ATTESTED_BY_THIS_AUDIT")

    def test_quote_alias_and_repeated_line_dedup(self):
        s=rows()
        s["Quote Portfolio"]=[{"Approved AMEA ID":P,"Quote QID":QID,
                               "Salesforce Quote ID (18)":QUOTE+"AAA","Opportunity ID":OPP}]
        s["SFDC Quote Export"]=[{"Salesforce Record ID":QUOTE,"AMEA Quotation ID":QID,
                                   "Opportunity ID":OPP,"Account ID":"","Contact ID":""}]
        line={"SFDC Quotation ID":QID,"Quotation Product ID":"QD-2026-01",
              "Opportunity ID":OPP,"Contact ID":"","*Account Id":""}
        s["SFDC Email Quotation Raw"]=[line,line.copy()]
        out=g.coverage(s)
        self.assertEqual(out["observed_reference_edges"]["QID->QUOTE_OBJECT"],1)
        self.assertEqual(out["multi_source_observed_edges"]["QID->QUOTE_OBJECT"],1)
        self.assertEqual(out["observed_reference_edges"]["QID->OPP_REF"],1)
        self.assertEqual(out["observed_reference_edges"]["QID->QUOTE_PRODUCT_REF"],1)
        self.assertEqual(out["distinct_typed_identifiers"]["AMEA"],1)

    def test_empty_sources_and_group_receipts_no_inferred_payment(self):
        s=rows()
        s["Feishu Latest Receipts"]=[{"CMS No.":CMS+";209126000002","CMS No. [2]":"",
                                      "CMS No. [3]":""}]
        out=g.coverage(s)
        self.assertEqual(out["distinct_typed_identifiers"]["CMS"],2)
        self.assertEqual(out["observed_reference_edges"],{})
        self.assertEqual(out["sources"]["SFDC Raw - Account"]["population_status"],"NO_ROWS_OBSERVED")
        self.assertEqual(out["field_observation_counts"]["Feishu Latest Receipts"]["CMS No. [2]"],{"EMPTY":1})

    def test_partial_malformed_list_not_promoted(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H+";bad",
                                       "sam_numbers":""}]
        out=g.coverage(s)
        self.assertEqual(out["distinct_typed_identifiers"]["H"],1)
        self.assertNotIn("AMEA->H",out["observed_reference_edges"])
        self.assertEqual(out["field_observation_counts"]["CSS Project Dashboard"]["h_project_numbers"],
                         {"PARTIAL_FORMAT_REVIEW":1})

    def test_missing_tab_or_fields_fail_closed(self):
        s=rows()
        del s["CSS Project Dashboard"]
        with self.assertRaisesRegex(g.CoverageError,"SOURCE_SET_INCOMPLETE"):
            g.coverage(s)
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P}]
        with self.assertRaisesRegex(g.CoverageError,"SOURCE_FIELDS_INCOMPLETE"):
            g.coverage(s)

class ProjectRelationshipTests(unittest.TestCase):
    def test_prepayment_expands_population_without_board_or_owner_filter(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S}]
        s["Feishu Latest Prepayments"]=[{"Quotation Number":Q,"Project Number":"X209SC26000999",
                                          "CMS Invoice Number":CMS,"Sales":"OTHER_SALES"}]
        out,details=g.project_relationships(s)
        self.assertEqual(out["core"]["amea"],1)
        self.assertEqual(out["expanded"]["amea"],2)
        self.assertEqual(out["outside_baseline"]["amea"],1)
        self.assertEqual(out["expanded"]["finance_x"],1)
        self.assertEqual(details[1]["x_observation_state"],"FINANCE_X_REFERENCE_ONLY")
        self.assertFalse(out["owner_filter_applied"])
        self.assertNotIn(CMS,json.dumps(out))

    def test_h_root_candidate_and_exact_lifecycle_separate(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H+"-B01","sam_numbers":S}]
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X},
                                    {"Contract Number":H,"Sub-Project Number":X2}]
        out,details=g.project_relationships(s)
        self.assertEqual(details[0]["current_h_candidates"],{X:["H_ROOT_CANDIDATE_ONLY"],X2:["H_ROOT_CANDIDATE_ONLY"]})
        self.assertEqual(out["expanded"]["any_direct_x"],0)
        s["BI Project Lifecycle Overview"]=[{"AMEA":P,"Project / Sub-project":X}]
        out,details=g.project_relationships(s)
        self.assertEqual(details[0]["current_online_exact_lifecycle_x"],[X])
        self.assertEqual(details[0]["current_h_candidates"],{X2:["H_ROOT_CANDIDATE_ONLY"]})

    def test_finance_base_and_suffixed_reference_not_inferred(self):
        s=rows()
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X},
                                    {"Contract Number":H,"Sub-Project Number":X2}]
        s["Feishu Latest Outstanding"]=[{"Quotation Number":P,"Project Number":"X209SC26000001",
                                          "CMS Invoice Number":CMS}]
        s["Feishu Latest eTax"]=[{"Quotation Number":P,"Project Number":"X209SC26000001-Z03",
                                  "CMS Invoice Num":CMS}]
        out,details=g.project_relationships(s)
        candidates=details[0]["finance_x_candidates"]
        self.assertEqual(candidates[0]["current_x_candidates"],[X,X2])
        self.assertEqual(candidates[1]["current_x_candidates"],[])
        self.assertEqual(details[0]["current_online_exact_lifecycle_x"],[])
        self.assertEqual(details[0]["invoice_cms"],[CMS])

    def test_shared_reference_kept_and_receipt_not_payment(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":p,"h_project_numbers":H,"sam_numbers":S} for p in (P,Q)]
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X}]
        s["Feishu Latest Outstanding"]=[{"Quotation Number":p,"Project Number":"X209SC26000001",
                                          "CMS Invoice Number":CMS} for p in (P,Q)]
        s["Feishu Latest Receipts"]=[{"CMS No.":CMS+";209126000002","CMS No. [2]":"","CMS No. [3]":""}]
        out,details=g.project_relationships(s)
        self.assertEqual(out["shared_reference_counts"]["CMS"],1)
        self.assertEqual(out["shared_reference_counts"]["H_ROOT"],1)
        self.assertEqual(out["expanded"]["receipt_cms_reference"],2)
        self.assertEqual(details[0]["current_h_candidates"],{X:["SHARED_H_ROOT_REVIEW"]})
        self.assertEqual(details[0]["receipt_cms_references"],{CMS:["GROUP_OR_PARTIAL_CMS_CELL_REFERENCE"]})
        self.assertEqual(out["payment_status"],"NOT_ATTESTED_BY_REFERENCE_OBSERVATION")

    def test_invalid_anchor_not_silently_dropped_and_partial_reference_review(self):
        s=rows()
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H+";bad","sam_numbers":S},
                                     {"project_id":"","h_project_numbers":H,"sam_numbers":S}]
        out,details=g.project_relationships(s)
        self.assertEqual(out["rows_without_valid_amea"]["CSS Project Timeline"],
                         {"EMPTY_AMEA":1,"WITH_H_REFERENCE":1,"WITH_SAM_REFERENCE":1})
        self.assertEqual(details[0]["refs"]["H"],{H:["CSS Project Timeline"]})
        self.assertTrue(any(r["state"]=="PARTIAL_FORMAT_REVIEW" for r in details[0]["field_review"]))

    def test_private_report_disabled_in_ci(self):
        with patch.dict("os.environ",{"GITHUB_ACTIONS":"true"}):
            with self.assertRaisesRegex(g.CoverageError,"FORBIDDEN_IN_CI"):
                g.private_project_report("/not-created.json",{},[])

class RegistryReferenceTests(unittest.TestCase):
    def fixture(self):
        s=rows()
        q=g.quote18(QUOTE)
        r={"link_key":"synthetic-link","left_system":"CSS","left_entity":"Invoice",
           "left_record_id":CMS,"right_system":"SFDC","right_entity":"Quote","right_record_id":QUOTE,
           "sfdc_quote_id":QUOTE,"amea_quote_id":P,"invoice_number":CMS,
           "matching_method":"SOURCE_RESOLVED_ID","verification_status":"SOURCE_RESOLVED_ACTIVE_UNVERIFIED",
           "verified_at":"","account_id":"","contact_id":"","opportunity_id":"","project_id":P}
        s[g.REGISTRY_NAME]=[r]
        s["Quote Portfolio"]=[{"Salesforce Quote ID (18)":q,"Approved AMEA ID":P,
                               "Quote QID":QID,"Opportunity ID":OPP,"Active":"ACTIVE"}]
        s["SFDC Quote Export"]=[{"Salesforce Record ID":q,"AMEA Quotation ID":QID,
                                 "Opportunity ID":OPP,"Account ID":"","Contact ID":""}]
        s["SFDC Verified Relations"]=[{"Quotation ID":QID,"Opportunity ID":OPP,"Lead Converted ID":""}]
        s["SFDC Email Opportunities Raw"]=[{"Opportunity ID":OPP,"Lead Converted ID":"","Account ID":""}]
        e={"Payment & Tax Invoice":[{"Invoice Number":CMS,"SFDC Quote ID":QUOTE,"AMEA Project ID":P}],
           "CSS Tax Invoice List":[{"invoice_number":CMS,"project_id":P}],
           "CSS Tax Invoice Extract":[{"invoice_number":CMS,"project_id":P}]}
        return s,e

    def test_15_and_valid_18_normalize_exactly_and_case_preserved(self):
        q=g.quote18(QUOTE)
        self.assertEqual(len(q),18)
        self.assertEqual(g.quote18(q),q)
        self.assertNotEqual(g.quote18(QUOTE.replace("Abc","abc")),q)
        self.assertEqual(g.quote18(q[:-1]+("B" if q[-1]=="A" else "A")),"")

    def test_exact_normalized_registry_and_invoice_document_reference(self):
        s,e=self.fixture()
        before=copy.deepcopy((s,e))
        out=g.registry_reference_audit(s,e)
        self.assertEqual(out["quote_reference_states"],{"EXACT_NORMALIZED_QUOTE_AMEA_QID_OPP":1})
        self.assertEqual(out["payment_reference_states"],{"EXACT_INVOICE_DOCUMENT_QUOTE_AMEA":1})
        self.assertEqual(out["unique_exact_quote_payment_triples"],1)
        self.assertEqual(out["diagnostic_counts"]["stored_active_unverified"],1)
        self.assertEqual(out["invoice_document_reference_states"]["CSS Tax Invoice Extract"],
                         {"EXACT_INVOICE_DOCUMENT_AMEA":1})
        self.assertEqual(out["report_reference_observations"]["OPP_REPORT_UNIQUE"],1)
        self.assertEqual(out["cms_identity"],"NOT_INFERRED_FROM_DOCUMENT_NUMBER")
        self.assertEqual(out["business_writes"],0)
        self.assertEqual((s,e),before)
        for ident in (P,CMS,QUOTE,QID,OPP):
            self.assertNotIn(ident,json.dumps(out))

    def test_distinct_relation_types_do_not_double_count_invoice_triple(self):
        s,e=self.fixture()
        r=dict(s[g.REGISTRY_NAME][0],link_key="second",left_entity="QuoteApproval",
               left_record_id=P,right_system="CSS",right_entity="Invoice",right_record_id=CMS)
        s[g.REGISTRY_NAME].append(r)
        out=g.registry_reference_audit(s,e)
        self.assertEqual(out["rows"],2)
        self.assertEqual(out["unique_invoice_quote_amea_triples"],1)
        self.assertEqual(out["unique_exact_quote_payment_triples"],1)
        self.assertEqual(out["diagnostic_counts"]["quote_and_payment_reference_exact_rows"],2)

    def test_conflicting_quote_qid_or_parent_is_review(self):
        s,e=self.fixture()
        s["SFDC Quote Export"].append(dict(s["SFDC Quote Export"][0],
            **{"Salesforce Record ID":g.quote18("a0P123456789012")}))
        self.assertEqual(g.registry_reference_audit(s,e)["quote_reference_states"],
                         {"QID_OPPORTUNITY_REFERENCE_REVIEW":1})
        s,e=self.fixture()
        s["Quote Portfolio"][0]["Approved AMEA ID"]=Q
        self.assertEqual(g.registry_reference_audit(s,e)["quote_reference_states"],
                         {"PORTFOLIO_AMEA_REVIEW":1})

    def test_bad_endpoint_or_checksum_not_linked(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME][0]["right_record_id"]="a0P123456789012"
        self.assertEqual(g.registry_reference_audit(s,e)["quote_reference_states"],
                         {"REGISTRY_ENDPOINT_REVIEW":1})

    def test_document_parent_conflicts_and_missing_not_zero_or_paid(self):
        s,e=self.fixture()
        e["Payment & Tax Invoice"].append(dict(e["Payment & Tax Invoice"][0],**{"AMEA Project ID":Q}))
        e["CSS Tax Invoice Extract"]=[]
        e["CSS Tax Invoice List"].append({"invoice_number":CMS,"project_id":Q})
        out=g.registry_reference_audit(s,e)
        self.assertEqual(out["payment_reference_states"],{"INVOICE_DOCUMENT_PARENT_REVIEW":1})
        self.assertEqual(out["invoice_document_reference_states"]["CSS Tax Invoice List"],
                         {"INVOICE_DOCUMENT_AMEA_REVIEW":1})
        self.assertEqual(out["invoice_document_reference_states"]["CSS Tax Invoice Extract"],
                         {"INVOICE_DOCUMENT_NOT_OBSERVED":1})
        self.assertEqual(out["unique_exact_quote_payment_triples"],0)

    def test_document_reference_not_added_to_cms_observation(self):
        s,e=self.fixture()
        out=g.coverage(s)
        self.assertEqual(out["distinct_typed_identifiers"]["INVOICE_DOCUMENT_REF"],1)
        self.assertNotIn("CMS",out["distinct_typed_identifiers"])
        self.assertNotIn("CMS->AMEA",out["observed_reference_edges"])

    def test_mixed_case_opportunity_format_accepts_exact_literal_only(self):
        s,e=self.fixture()
        opp="Opp-2026-000001"
        for name in ("Quote Portfolio","SFDC Quote Export","SFDC Verified Relations","SFDC Email Opportunities Raw"):
            s[name][0]["Opportunity ID"]=opp
        self.assertEqual(g.registry_reference_audit(s,e)["quote_reference_states"],
                         {"EXACT_NORMALIZED_QUOTE_AMEA_QID_OPP":1})
        s["SFDC Quote Export"][0]["Opportunity ID"]=opp.upper()
        self.assertEqual(g.registry_reference_audit(s,e)["quote_reference_states"],
                         {"QID_OPPORTUNITY_REFERENCE_REVIEW":1})

    def test_expansion_partitions_existing_and_reference_only(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME]=[]
        e["Payment & Tax Invoice"]=[]
        s["Quote Portfolio"][0]["Opportunity ID"]="Opp-2026-000001"
        s["SFDC Quote Export"][0]["Opportunity ID"]="Opp-2026-000001"
        s["BI Project Lifecycle Overview"]=[{"AMEA":Q,"Project / Sub-project":X}]
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X}]
        _,details=g.project_relationships(s)
        out=g.registry_expansion_audit(s,e,details)
        self.assertEqual(out["outside_registry_amea"],2)
        self.assertEqual(out["candidate_partition"],{"EXACT_QUOTE_REFERENCE_ONLY":1,
                        "EXACT_CURRENT_LIFECYCLE_NO_QUOTE":1})
        self.assertEqual(out["exact_document_quote_candidate_triples"],0)
        self.assertEqual(out["business_writes"],0)
        self.assertNotIn(P,json.dumps(out))
        self.assertNotIn(Q,json.dumps(out))

    def test_expansion_document_candidate_requires_exact_parent_and_no_conflict(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME]=[]
        _,details=g.project_relationships(s)
        out=g.registry_expansion_audit(s,e,details)
        self.assertEqual(out["candidate_partition"],{"EXACT_DOCUMENT_QUOTE_REFERENCE_CANDIDATE":1})
        self.assertEqual(out["exact_document_quote_candidate_triples"],1)
        e["Payment & Tax Invoice"].append(dict(e["Payment & Tax Invoice"][0],**{"SFDC Quote ID":""}))
        out=g.registry_expansion_audit(s,e,details)
        self.assertEqual(out["candidate_partition"],{"EXACT_QUOTE_REFERENCE_ONLY":1})
        self.assertEqual(out["exact_document_quote_candidate_triples"],0)

    def test_expansion_multiple_portfolio_does_not_choose_quote(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME]=[]
        s["Quote Portfolio"].append(dict(s["Quote Portfolio"][0],
            **{"Salesforce Quote ID (18)":g.quote18("a0P123456789012")}))
        _,details=g.project_relationships(s)
        out=g.registry_expansion_audit(s,e,details)
        self.assertEqual(out["candidate_partition"],{"MULTI_QUOTE_NO_EXACT_REFERENCE_REVIEW":1})

    def multi_fixture(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME]=[]
        e["Payment & Tax Invoice"]=[]
        s["SFDC Quote Export"][0].update({"IsActive":"1","Account ID":"account-one",
                                         "Contact ID":"contact-one"})
        other_quote=g.quote18("a0P123456789012")
        other_qid="QID-2026-000002"
        s["Quote Portfolio"].append(dict(s["Quote Portfolio"][0],
            **{"Salesforce Quote ID (18)":other_quote,"Quote QID":other_qid,"Active":"INACTIVE"}))
        s["SFDC Quote Export"].append(dict(s["SFDC Quote Export"][0],
            **{"Salesforce Record ID":other_quote,"AMEA Quotation ID":other_qid,"IsActive":"0"}))
        s["SFDC Verified Relations"].append(dict(s["SFDC Verified Relations"][0],
                                                **{"Quotation ID":other_qid}))
        return s,e

    def multi_audit(self,s,e):
        _,details=g.project_relationships(s)
        return g.registry_expansion_audit(s,e,details)

    def test_multi_quote_same_opportunity_preserves_both_rows(self):
        s,e=self.multi_fixture()
        before=copy.deepcopy((s,e))
        out=self.multi_audit(s,e)
        multi=out["multi_quote_reference_audit"]
        self.assertEqual(out["candidate_partition"],{"MULTI_QUOTE_EXACT_SINGLE_OPPORTUNITY":1})
        self.assertEqual(multi["quote_row_states"],{"EXACT_QUOTE_REFERENCE":2})
        self.assertEqual(multi["counts"]["exact_quote_rows"],2)
        self.assertEqual(multi["counts"]["activity_agreement_rows"],2)
        self.assertEqual(multi["counts"]["groups_all_verified_relation_refs_exact"],1)
        self.assertEqual(multi["observed_active_labels_per_fully_exact_amea"],{"1":1})
        self.assertEqual(multi["primary_quote_selection"],"NOT_PERFORMED")
        self.assertEqual(out["fully_exact_single_or_multi_quote_projects"],1)
        self.assertEqual(out["distinct_opportunity_refs_single_and_fully_exact_multi"],1)
        self.assertEqual(out["exact_document_quote_candidate_triples"],0)
        self.assertEqual((s,e),before)
        self.assertNotIn(P,json.dumps(out))
        self.assertNotIn(QUOTE,json.dumps(out))

    def test_multi_quote_account_contact_variation_is_review_not_merge(self):
        s,e=self.multi_fixture()
        s["SFDC Quote Export"][1].update({"Account ID":"account-two","Contact ID":"contact-two"})
        out=self.multi_audit(s,e)["multi_quote_reference_audit"]["counts"]
        self.assertEqual(out["groups_multiple_account_refs_review"],1)
        self.assertEqual(out["groups_multiple_contact_refs_review"],1)
        self.assertEqual(out["groups_single_opportunity_ref"],1)

    def test_multi_quote_different_opportunity_is_review(self):
        s,e=self.multi_fixture()
        s["Quote Portfolio"][1]["Opportunity ID"]="Opp-2026-000002"
        s["SFDC Quote Export"][1]["Opportunity ID"]="Opp-2026-000002"
        out=self.multi_audit(s,e)
        self.assertEqual(out["candidate_partition"],{"MULTI_QUOTE_EXACT_MULTIPLE_OPPORTUNITY_REVIEW":1})
        self.assertEqual(out["multi_quote_reference_audit"]["counts"]["groups_multiple_opportunity_refs_review"],1)
        self.assertEqual(out["distinct_opportunity_refs_single_and_fully_exact_multi"],2)

    def test_multi_quote_partial_reference_stays_review(self):
        s,e=self.multi_fixture()
        s["SFDC Quote Export"].pop()
        out=self.multi_audit(s,e)
        self.assertEqual(out["candidate_partition"],{"MULTI_QUOTE_PARTIAL_REFERENCE_REVIEW":1})
        self.assertEqual(out["multi_quote_reference_audit"]["counts"]["exact_quote_rows"],1)
        self.assertEqual(out["fully_exact_single_or_multi_quote_projects"],0)

    def test_multi_quote_activity_disagreement_or_unknown_is_not_certification(self):
        s,e=self.multi_fixture()
        s["SFDC Quote Export"][0]["IsActive"]="0"
        s["SFDC Quote Export"][1]["IsActive"]=""
        out=self.multi_audit(s,e)["multi_quote_reference_audit"]
        self.assertEqual(out["counts"]["groups_with_activity_mismatch"],1)
        self.assertEqual(out["counts"]["groups_with_activity_not_assessed"],1)
        self.assertEqual(out["primary_quote_selection"],"NOT_PERFORMED")

    def nonquote_audit(self,s):
        _,details=g.project_relationships(s)
        return g.registry_nonquote_project_audit(s,details)

    def test_nonquote_exact_lifecycle_and_finance_base_remain_separate(self):
        s=rows()
        s["BI Project Lifecycle Overview"]=[{"AMEA":P,"Project / Sub-project":X}]
        s["Feishu Latest Online"]=[{"Contract Number":H+"-B01","Sub-Project Number":X}]
        for name,field in (("Feishu Latest Outstanding","CMS Invoice Number"),
                           ("Feishu Latest eTax","CMS Invoice Num")):
            s[name]=[{"Quotation Number":P,"Project Number":"X209SC26000001",field:CMS}]
        s["Feishu Latest Receipts"]=[{"CMS No.":CMS,"CMS No. [2]":"","CMS No. [3]":""}]
        out=self.nonquote_audit(s)
        current=out["cohorts"]["CURRENT_LIFECYCLE"]
        self.assertEqual(out["outside_registry_without_portfolio_amea"],1)
        self.assertEqual(out["distinct_exact_current_lifecycle_x"],1)
        self.assertEqual(out["distinct_exact_online_x_h_reference_pairs"],1)
        self.assertEqual(current["counts"]["finance_candidate_intersects_exact_lifecycle_x"],1)
        self.assertEqual(current["counts"]["same_reported_x_in_outstanding_and_etax"],1)
        self.assertEqual(current["counts"]["receipt_single_cms_cell_reference"],1)
        self.assertEqual(current["counts"]["all_exact_x_have_unique_online_h_reference"],1)
        self.assertEqual(out["payment_owner_issuance_certification"],"NOT_ATTESTED")
        for ident in (P,H,X,CMS):
            self.assertNotIn(ident,json.dumps(out))

    def test_nonquote_duplicate_online_rows_do_not_certify_h_chain(self):
        s=rows()
        s["BI Project Lifecycle Overview"]=[{"AMEA":P,"Project / Sub-project":X}]
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X}]*2
        out=self.nonquote_audit(s)
        self.assertEqual(out["distinct_exact_current_lifecycle_x"],1)
        self.assertEqual(out["distinct_exact_online_x_h_reference_pairs"],0)
        self.assertEqual(out["cohorts"]["CURRENT_LIFECYCLE"]["counts"]["online_h_reference_review"],1)

    def test_nonquote_missing_current_does_not_infer_historical_completion(self):
        s=rows()
        s["Feishu Latest Outstanding"]=[{"Quotation Number":P,"Project Number":X,"CMS Invoice Number":CMS},
                                        {"Quotation Number":Q,"Project Number":X2,"CMS Invoice Number":"209126000002"}]
        s["BI Project Lifecycle Overview"]=[{"AMEA":Q,"Project / Sub-project":X2}]
        s["Feishu Latest Receipts"]=[{"CMS No.":CMS+";209126000002","CMS No. [2]":"","CMS No. [3]":""}]
        out=self.nonquote_audit(s)
        self.assertEqual(out["cohorts"]["X_REVIEW"]["reference_states"],
                         {"FINANCE_NO_CURRENT_X":1,"LIFECYCLE_X_NOT_CURRENT":1})
        self.assertEqual(out["cohorts"]["X_REVIEW"]["counts"]["receipt_group_or_partial_cms_cell_reference"],2)
        self.assertEqual(out["historical_status"],"NOT_INFERRED_FROM_CURRENT_ONLINE_ABSENCE")
        self.assertEqual(out["business_writes"],0)

    def test_nonquote_suffix_and_shared_lifecycle_remain_review(self):
        s=rows()
        s["Feishu Latest Online"]=[{"Contract Number":H,"Sub-Project Number":X}]
        s["BI Project Lifecycle Overview"]=[{"AMEA":pid,"Project / Sub-project":X} for pid in (P,Q)]
        s["Feishu Latest Outstanding"]=[{"Quotation Number":P,"Project Number":X2,"CMS Invoice Number":CMS}]
        out=self.nonquote_audit(s)
        self.assertEqual(out["cohorts"]["X_REVIEW"]["reference_states"],{"SHARED_LIFECYCLE_REVIEW":2})
        self.assertEqual(out["cohorts"]["X_REVIEW"]["counts"]["finance_reported_x_without_current_candidate"],1)
        self.assertEqual(out["distinct_exact_current_lifecycle_x"],0)

    def test_nonquote_excludes_registry_and_portfolio_and_retains_h_only(self):
        s,e=self.fixture()
        s["Quote Portfolio"][0]["Approved AMEA ID"]=Q
        third="AMEA2026000003"
        s["CSS Project Timeline"]=[{"project_id":pid,"h_project_numbers":H,"sam_numbers":S}
                                   for pid in (P,Q,third)]
        out=self.nonquote_audit(s)
        self.assertEqual(out["outside_registry_without_portfolio_amea"],1)
        self.assertEqual(out["cohorts"]["NO_DIRECT_X"]["counts"]["has_h"],1)
        self.assertEqual(out["cohorts"]["NO_DIRECT_X"]["counts"]["shared_reference_review"],1)

    def historical_audit(self,s):
        _,details=g.project_relationships(s)
        return g.registry_historical_h_sam_audit(s,details)

    def test_h_sam_literal_agreement_and_dates_not_pair_or_status(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S}]
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S,
                                     "received_at":"2025-10-01T01:00:00+09:00"},
                                    {"project_id":P,"h_project_numbers":H,"sam_numbers":S,
                                     "received_at":"2026-03-01 10:00:00"}]
        before=copy.deepcopy(s)
        out=self.historical_audit(s)
        self.assertEqual(out["reference_states"],{"H_AND_SAM_CORROBORATED_LITERAL_REFERENCES":1})
        self.assertEqual(out["distinct_h_contract_refs"],1)
        self.assertEqual(out["distinct_sam_refs"],1)
        self.assertEqual(out["timeline_rows_with_h_and_sam"],2)
        self.assertEqual(out["latest_parseable_timeline_year_counts"],{"2026":1})
        self.assertEqual(out["h_sam_pair_assignment"],"NOT_INFERRED_FROM_COOCCURRENCE")
        self.assertEqual(out["same_stream_agreement"],"NOT_INDEPENDENT_EVIDENCE")
        self.assertEqual(out["current_or_completed_status"],"NOT_ATTESTED")
        self.assertEqual(s,before)
        self.assertEqual(out["business_writes"],0)
        for ident in (P,H,S):
            self.assertNotIn(ident,json.dumps(out))

    def test_h_sam_shared_root_and_sample_do_not_merge_amea(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H+"-B01","sam_numbers":S}]
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H+"-B01","sam_numbers":S},
                                    {"project_id":Q,"h_project_numbers":H+"-B02","sam_numbers":S}]
        out=self.historical_audit(s)
        self.assertEqual(out["reference_states"],{"SHARED_H_OR_SAM_REVIEW":2})
        self.assertEqual(out["distinct_h_contract_refs"],2)
        self.assertEqual(out["distinct_shared_h_roots"],1)
        self.assertEqual(out["distinct_shared_sam_refs"],1)

    def test_h_sam_partial_format_is_review_and_not_clean_cooccurrence(self):
        s=rows()
        s["CSS Project Dashboard"]=[{"project_id":P,"h_project_numbers":H,"sam_numbers":S}]
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H+";bad","sam_numbers":S,
                                     "received_at":"2026-02-30"}]
        out=self.historical_audit(s)
        self.assertEqual(out["reference_states"],{"H_SAM_FORMAT_REVIEW":1})
        self.assertEqual(out["timeline_rows_with_h_and_sam"],0)
        self.assertEqual(out["latest_parseable_timeline_year_counts"],{"UNKNOWN":1})

    def test_h_sam_h_root_match_not_exact_suffix_or_x_assignment(self):
        s=rows()
        s["CSS Project Timeline"]=[{"project_id":P,"h_project_numbers":H+"-B01","sam_numbers":""}]
        s["Feishu Latest Online"]=[{"Contract Number":H+"-B02","Sub-Project Number":X}]
        out=self.historical_audit(s)
        self.assertEqual(out["reference_states"],{"H_TIMELINE_REFERENCE_ONLY":1})
        self.assertEqual(out["counts"]["h_root_observed_in_current_online"],1)
        self.assertNotIn("exact_h_observed_in_current_online",out["counts"])
        self.assertEqual(out["current_or_completed_status"],"NOT_ATTESTED")

    def test_h_sam_excludes_quote_registry_and_direct_x(self):
        s,e=self.fixture()
        s["Quote Portfolio"][0]["Approved AMEA ID"]=Q
        third="AMEA2026000003"
        fourth="AMEA2026000004"
        s["CSS Project Timeline"]=[{"project_id":pid,"h_project_numbers":H,"sam_numbers":S}
                                   for pid in (P,Q,third,fourth)]
        s["BI Project Lifecycle Overview"]=[{"AMEA":third,"Project / Sub-project":X}]
        out=self.historical_audit(s)
        self.assertEqual(out["amea"],1)
        self.assertEqual(out["reference_states"],{"SHARED_H_OR_SAM_REVIEW":1})

    def test_duplicate_registry_key_fails_closed(self):
        s,e=self.fixture()
        s[g.REGISTRY_NAME].append(s[g.REGISTRY_NAME][0].copy())
        with self.assertRaisesRegex(g.CoverageError,"REGISTRY_LINK_KEY_INVALID_OR_DUPLICATE"):
            g.registry_reference_audit(s,e)

if __name__=="__main__":
    unittest.main()
