#!/usr/bin/env python3
"""Fail-closed X identity, sample and invoice lineage regressions."""
import copy
import unittest
from x_project_lineage import build,LINK_SCHEMAS,x_base,h_root,owner

A="AMEA2026092814"
X="X209SC26099997-Z01"
H="H209SC26099997"
SAM="SAM20260928001"
CMS="209126000914"

def fixtures():
    return {
      "CSS Project Dashboard":[{
        "project_id":A,"h_project_numbers":H+" | "+H+"-B01",
        "sam_numbers":SAM,"current_stage":"Invoice issued",
        "progress_percent":"100"}],
      "CSS Project Timeline":[{"project_id":A,"h_project_numbers":H,
                               "sam_numbers":SAM,"stage":"Sample received"}],
      "BI Project Lifecycle Overview":[{
        "AMEA":A,"Project / Sub-project":X,
        "Feishu Status (latest)":"Abnormal","CSS Progress %":"100"}],
      "Feishu Latest Online":[{
        "Sub-Project Number":X,"Contract Number":H,"Sales":"Kim Taehoon",
        "Project Status":"Abnormal","Progression Details":"SAM on re-sequencing",
        "Remaining Lead Time-Calendar Days":"5","Staging Name":"PMP"}],
      "Feishu Latest eTax":[{
        "CMS Invoice Num":CMS,"Project Number":"X209SC26099997",
        "Quotation Number":A,"Sales":"Kim Taehoon","Amount":"1006500"}],
      "Feishu Latest Outstanding":[{
        "CMS Invoice Number":CMS,"Project Number":"X209SC26099997",
        "Quotation Number":A,"Sales":"Kim Taehoon","Invoice Amount":"1006500",
        "Balance":"1006500"}],
    }

class XProjectLineageTests(unittest.TestCase):
    def test_exact_links_and_no_amea_percentage_projection(self):
        data,audit=build(fixtures())
        self.assertEqual(audit["x"],1)
        self.assertEqual(audit["exact_amea_x"],1)
        self.assertEqual(audit["linked_sam"],1)
        self.assertEqual(audit["exact_invoices"],1)
        row=data["X Project Registry"][0]
        self.assertEqual(row["AMEA"],A)
        self.assertEqual(row["H Contract"],H)
        self.assertEqual(row["SAM Linked"],1)
        self.assertEqual(row["Progress Bar"],"미확인")
        self.assertNotIn("Progress %",row)
        self.assertEqual(row["Progress Phase"],"진행 단계 미확인")
        self.assertEqual(row["Invoice Gross KRW Incl VAT"],1006500)
        self.assertEqual(row["Owner Scope"],"MY_VERIFIED")
        self.assertEqual(data["X Invoice Ledger"][0]["Invoice Link State"],
                         "EXACT_X_AMEA_CMS")
    def test_sam_multiple_ameas_not_assigned_to_an_x(self):
        s=fixtures()
        s["CSS Project Dashboard"].append({
            "project_id":"AMEA2026110999","h_project_numbers":"H209SC26109999",
            "sam_numbers":SAM})
        data,audit=build(s)
        sam=[x for x in data["AMEA H X SAM Link"] if x["Link Type"]=="AMEA_SAM"]
        self.assertTrue(all(x["X Project"]=="" for x in sam))
        self.assertTrue(all(x["Link State"]=="SHARED_SAM_REVIEW" for x in sam))
        self.assertEqual(audit["linked_sam"],0)
    def test_multiple_z_projects_block_invoice_amount_attribution(self):
        s=fixtures()
        s["Feishu Latest Online"].append({
            **s["Feishu Latest Online"][0],
            "Sub-Project Number":"X209SC26099997-Z02"
        })
        s["BI Project Lifecycle Overview"].append({
            "AMEA":A,"Project / Sub-project":"X209SC26099997-Z02"
        })
        data,audit=build(s)
        self.assertEqual(audit["exact_invoices"],0)
        self.assertEqual(data["X Invoice Ledger"][0]["Invoice Link State"],
                         "MULTI_Z_REVIEW")
        self.assertTrue(all(row["Invoice Linked"]==0 for row in data["X Project Registry"]))
        self.assertTrue(all(row["SAM Linked"]==0 for row in data["X Project Registry"]))
    def test_h_contract_candidate_not_verified_directly(self):
        s=fixtures()
        s["BI Project Lifecycle Overview"]=[]
        data,audit=build(s)
        self.assertEqual(data["X Project Registry"][0]["AMEA Link State"],
                         "UNIQUE_H_CANDIDATE")
        self.assertEqual(data["X Project Registry"][0]["SAM Linked"],0)
        self.assertEqual(audit["exact_invoices"],0)
    def test_conflicting_sales_safely_quarantines_invoice(self):
        s=fixtures()
        s["Feishu Latest Outstanding"][0]["Sales"]="Other Sales"
        data,audit=build(s)
        self.assertEqual(data["X Invoice Ledger"][0]["Invoice Link State"],
                         "INVOICE_SOURCE_CONFLICT")
        self.assertEqual(data["X Invoice Ledger"][0]["Owner Scope"],
                         "OWNER_UNVERIFIED")
        self.assertEqual(audit["exact_invoices"],0)
    def test_invoice_without_cms_is_not_guessed(self):
        s=fixtures()
        s["Feishu Latest Outstanding"][0]["CMS Invoice Number"]=""
        s["Feishu Latest eTax"][0]["CMS Invoice Num"]=""
        data,audit=build(s)
        self.assertEqual(audit["invoice"],0)
        self.assertEqual(data["X Project Registry"][0]["Invoice Linked"],0)
    def test_h_suffix_is_version_not_separate_contract(self):
        self.assertEqual(h_root(H+"-B01"),H)
        self.assertEqual(x_base("X209SC26099997-Z02"),"X209SC26099997")
    def test_exact_owner_does_not_include_teammates(self):
        self.assertEqual(owner(" Kim Taehoon "),"MY_VERIFIED")
        self.assertEqual(owner("Kim Taehoon Jr"),"OTHER_SALES")
        self.assertEqual(owner("Other Sales"),"OTHER_SALES")
        self.assertEqual(owner(""),"OWNER_UNVERIFIED")
    def test_no_cross_ameax_when_lifecycle_conflicts(self):
        s=fixtures()
        s["BI Project Lifecycle Overview"][0]["AMEA"]="AMEA2026110999"
        data,audit=build(s)
        row=data["X Project Registry"][0]
        self.assertEqual(row["AMEA Link State"],"CONFLICT_LIFECYCLE_CSS_H")
        self.assertEqual(audit["linked_sam"],0)
        self.assertEqual(audit["exact_invoices"],0)
    def test_schema_source_key_unique_and_non_destructive(self):
        data,audit=build(fixtures())
        self.assertEqual(len(LINK_SCHEMAS),3)
        for name,rows in data.items():
            self.assertEqual(len(rows),len({r["Source Key"] for r in rows}))
            self.assertIn(name,LINK_SCHEMAS)
            schema={x for x,_ in LINK_SCHEMAS[name]}
            self.assertTrue(all(set(r).issubset(schema) for r in rows))
if __name__=="__main__":unittest.main()
