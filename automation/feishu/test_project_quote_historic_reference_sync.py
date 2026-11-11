#!/usr/bin/env python3
"""All synthetic values. No remote APIs called."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_quote_historic_reference_sync import (
    historical_fields,historical_same,mutation,preflight,VERIFIED_STATUS,REF_FIELDS
)
from project_quote_qid_money_audit import portfolio_index,header_index

QID="QID-2026-11-10-292701"
RID="a0P123456789012"
AMEA="AMEA2026000123"
NAME="Korea-University-10-mRNA"
def board(name=NAME,quote_status="SFDC_EXACT_VERIFIED",key="PROJECT:"+AMEA):
    return {"fields":{"AMEA":AMEA,"Quote Full Name":name,"Source Key":key,
                      "Quote Match State":quote_status}}
def ref(amount="10000"):
    return {"Approved AMEA ID":AMEA,"Quote Name":NAME,"Quote QID":QID,
            "Salesforce Quote ID (18)":RID,"Quote USD":amount,
            "Active":"ACTIVE","Approval Match":"APPROVED"}
def header(amount="10000",currency="USD"):
    return {"AMEA Quotation ID":QID,"Salesforce Record ID":RID,
            "Exclude Tax After Discount USD":amount,
            "CurrencyIsoCode":currency,"IsActive":"TRUE"}
def calculate(boardrow=None,portfolio=None,headers=None):
    return historical_fields(boardrow or board(),
         portfolio_index(portfolio if portfolio is not None else [ref()]),
         header_index(headers if headers is not None else [header()]),"2026-10-24")

class TestHistoricalReference(unittest.TestCase):
    def test_value_only_historic_with_date(self):
        x=calculate()
        self.assertEqual(x["SFDC Quote QID"],QID)
        self.assertEqual(x["과거 Quote 참고 금액 (K USD, VAT 제외)"],10.0)
        self.assertEqual(x["과거 Quote 금액 기준일"],"2026-10-24")
        self.assertEqual(x["과거 Quote 금액 상태"],VERIFIED_STATUS)
        self.assertNotIn("Quote 금액 (K USD)",x)
    def test_unverified_project_never_gets_amount(self):
        x=calculate(boardrow=board(quote_status="CSS_ORIGINAL_UNVERIFIED"))
        self.assertNotIn("과거 Quote 참고 금액 (K USD, VAT 제외)",x)
        self.assertNotIn("SFDC Quote QID",x)
    def test_1500_ratio_not_evidence_for_conversion(self):
        x=calculate(portfolio=[ref(amount="15000000")])
        self.assertNotIn("과거 Quote 참고 금액 (K USD, VAT 제외)",x)
        self.assertIn("RATIO_NEAR_1500",x["과거 Quote 금액 상태"])
    def test_krw_header_is_not_usd_reference(self):
        x=calculate(headers=[header(currency="KRW")])
        self.assertNotIn("과거 Quote 참고 금액 (K USD, VAT 제외)",x)
    def test_invalid_qid_or_missing_header_must_hold(self):
        x=calculate(headers=[])
        self.assertNotIn("과거 Quote 참고 금액 (K USD, VAT 제외)",x)
        self.assertEqual(x["과거 Quote 금액 상태"],"SFDC_EXPORT_MISSING_OR_DUPLICATE")
    def test_equal_and_revoked_reference(self):
        x=calculate()
        self.assertTrue(historical_same(dict(x),x))
        no=calculate(portfolio=[])
        m=mutation(x,no)
        self.assertIsNone(m["과거 Quote 참고 금액 (K USD, VAT 제외)"])
        self.assertIsNone(m["과거 Quote 금액 기준일"])
        self.assertEqual(m["과거 Quote 금액 상태"],no["과거 Quote 금액 상태"])
    def test_same_records_do_not_update(self):
        x=calculate()
        self.assertEqual(mutation(x,x),{})
    def test_cross_lifecycle_preflight_blocked(self):
        rows={"active":[board()],"billing":[board()]}
        with self.assertRaisesRegex(RuntimeError,"SOURCE_VIEW_LIFECYCLE_OVERLAP"):
            preflight(rows,{"active":("Active","v1"),"billing":("Billing","v2")},
                     {"Active":"t1","Billing":"t2"})
    def test_field_types(self):
        self.assertEqual(REF_FIELDS["과거 Quote 참고 금액 (K USD, VAT 제외)"],2)
        self.assertEqual(REF_FIELDS["SFDC Quote QID"],1)

if __name__=="__main__":
    unittest.main()
