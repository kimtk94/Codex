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

if __name__=="__main__":
    unittest.main()
