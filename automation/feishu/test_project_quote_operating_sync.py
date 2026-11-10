#!/usr/bin/env python3
"""Offline-only safety checks for derived project tables (no Feishu access)."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_quote_operating_sync import source_row, validate_sources, number, equal_row, FIELDS

def record(key,name,stage="Sample QC review",progress="40.0"):
    return {"record_id":"rec_"+key,"fields":{
      "Source Key":key,"Quote Full Name":name,"Institution":"Univ.",
      "Customer":"Customer","Current Stage":stage,"Progress %":progress,
      "Next Action":"Confirm QC","Invoice Gross M KRW":"",
      "Outstanding Balance M KRW":"","Quote Match State":"SFDC_EXACT_VERIFIED"}}

class QuoteProjectTests(unittest.TestCase):
    def test_quote_is_first_column(self):
        self.assertEqual(FIELDS[0][0],"Quote Name")
        self.assertEqual(FIELDS[0][1],1)
    def test_quote_amount_stays_unverified_and_blank(self):
        row=source_row(record("A1","Korea-1-test"))
        self.assertEqual(row["Quote Name"],"Korea-1-test")
        self.assertEqual(row["진행률 (%)"],40.0)
        self.assertNotIn("Quote 금액 (K USD)",row)
        self.assertIn("UNVERIFIED",row["견적 금액 검증"])
    def test_absent_invoice_and_progress_never_become_zero(self):
        row=source_row(record("A2","Korea-2-test",progress=""))
        self.assertNotIn("진행률 (%)",row)
        self.assertNotIn("Invoice 조회액 (M KRW, VAT 포함)",row)
        self.assertNotIn("미수금 조회액 (M KRW)",row)
    def test_invoice_and_outstanding_keep_separate(self):
        rec=record("A3","Korea-3-test")
        rec["fields"]["Invoice Gross M KRW"]="2.50"
        rec["fields"]["Outstanding Balance M KRW"]="0.30"
        row=source_row(rec)
        self.assertEqual(row["Invoice 조회액 (M KRW, VAT 포함)"],2.5)
        self.assertEqual(row["미수금 조회액 (M KRW)"],0.3)
        self.assertNotIn("Quote 금액 (K USD)",row)
    def test_numeric_boundary(self):
        with self.assertRaisesRegex(RuntimeError,"SOURCE_AMOUNT_OUT_OF_RANGE"):
            number("101",0,100)
        with self.assertRaisesRegex(RuntimeError,"INVALID_NUMERIC_SOURCE"):
            number("not verified",0,100)
    def test_duplicate_view_name_prevented(self):
        original=[record("ID"+str(i),"Quote"+str(i)) for i in range(150)]
        active=[record("ID1","Duplicate"),record("ID2","Duplicate")]
        with self.assertRaisesRegex(RuntimeError,"VIEW_IDENTIFIERS_NOT_UNIQUE"):
            validate_sources(original,{"active":active,"billing":[record("ID10","Unique")]})
    def test_cross_view_overlap_prevented(self):
        original=[record("ID"+str(i),"Quote"+str(i)) for i in range(150)]
        with self.assertRaisesRegex(RuntimeError,"VIEW_LIFECYCLE_OVERLAP"):
            validate_sources(original,{"active":[original[1]],"billing":[original[1]]})
    def test_idempotent_rows(self):
        row=source_row(record("A4","Korea-4-test"))
        self.assertTrue(equal_row(dict(row),row))
        self.assertFalse(equal_row({**row,"현재 공정":"SIF requested"},row))
    def test_stale_quote_money_fails_equality(self):
        row=source_row(record("A5","Korea-5-test"))
        self.assertFalse(equal_row({**row,"Quote 금액 (K USD)":10.0},row))

if __name__=="__main__":unittest.main()
