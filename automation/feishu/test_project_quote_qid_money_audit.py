#!/usr/bin/env python3
"""Unit checks for amount matching. Synthetic records only."""
import sys
import unittest
from decimal import Decimal
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from project_quote_qid_money_audit import (
    portfolio_index, quote_reference, price_evidence, audit,
)

AMEA="AMEA2026000123"
NAME="Korea-Institution-Project-mRNA"
QID="QID-2026-11-10-XXXX"
RECORD="a0P123456789012"

def board(status="SFDC_EXACT_VERIFIED",name=NAME):
    return {"fields":{"AMEA":AMEA,"Quote Full Name":name,"Quote Match State":status}}

def portfolio(quote_name=NAME,amount="100",active="ACTIVE",approved="APPROVED"):
    return {"Approved AMEA ID":AMEA,"Quote Name":quote_name,"Quote QID":QID,
            "Salesforce Quote ID (18)":RECORD,"Quote USD":amount,
            "Active":active,"Approval Match":approved}

def header(amount="100",currency="USD",active="TRUE",record=RECORD):
    return {"AMEA Quotation ID":QID,"Salesforce Record ID":record,
            "CurrencyIsoCode":currency,"IsActive":active,
            "Exclude Tax After Discount USD":amount}

class TestMoneyCrosswalk(unittest.TestCase):
    def test_exact_amea_quote_qid(self):
        hit,status=quote_reference(board(),[portfolio()])
        self.assertEqual(status,"QID_REFERENCE_EXACT")
        self.assertEqual(hit["qid"],QID)
    def test_css_fallback_never_money(self):
        hit,state=quote_reference(board(status="CSS_ORIGINAL_UNVERIFIED"),[portfolio()])
        self.assertIsNone(hit)
    def test_name_mismatch_never_money(self):
        hit,state=quote_reference(board(),[portfolio(quote_name="Wrong")])
        self.assertIsNone(hit)
        self.assertEqual(state,"PORTFOLIO_NAME_MISMATCH")
    def test_inactive_rejected(self):
        hit,state=quote_reference(board(),[portfolio(active="INACTIVE")])
        self.assertEqual(state,"PORTFOLIO_NOT_ACTIVE_APPROVED")
    def test_conflicting_qid_rejected(self):
        row=portfolio()
        other=dict(row,**{"Quote QID":"QID-2026-11-10-YYYY"})
        hit,state=quote_reference(board(),[row,other])
        self.assertEqual(state,"PORTFOLIO_AMBIGUOUS_QID_OR_RECORD")
    def test_export_sfid_mismatch(self):
        hit,_=quote_reference(board(),[portfolio()])
        state,amount=price_evidence(hit,{QID:[header(record="a0P123456789099")]})
        self.assertEqual(state,"SFDC_RECORD_ID_MISMATCH")
        self.assertIsNone(amount)
    def test_near_1500_is_not_proof_of_fx(self):
        hit,_=quote_reference(board(),[portfolio(amount="150000")])
        state,amount=price_evidence(hit,{QID:[header(amount="100",currency="KRW")]})
        self.assertEqual(state,"REFERENCE_ONLY_RATIO_NEAR_1500_KRW")
        self.assertEqual(amount,Decimal("100"))
        report=audit([board()],[portfolio(amount="150000")],[header(currency="KRW")],1,10)
        self.assertEqual(report["quote_amount_verified_rows"],0)
        self.assertFalse(report["safe_to_display_final_quote_amount"])
    def test_portfolio_dual_names_held(self):
        hit,state=quote_reference(board(),[portfolio(amount="10"),portfolio(amount="20")])
        self.assertEqual(state,"PORTFOLIO_AMOUNT_CONFLICT")
    def test_uniqueness_of_qid_reference(self):
        idx=portfolio_index([portfolio()])
        self.assertEqual(len(idx[AMEA]),1)

if __name__=="__main__":
    unittest.main()
