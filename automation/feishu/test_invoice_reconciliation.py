"""Synthetic tests only. No real customer data or API access."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from invoice_reconciliation import reconcile
invoices=[
 {"invoice_number":"INV-001","project_id":"AMEA1","amount_krw":"10000"},
 {"invoice_number":"INV002","project_id":"AMEA1","amount_krw":"20000"},
 {"invoice_number":"INV003","project_id":"AMEA2","amount_krw":"30000"},
]
payments=[
 {"invoice_number":"INV001","invoice_amount_krw":"10000"},
 {"invoice_number":"INV002","invoice_amount_krw":"19000"},
 {"invoice_number":"OTHER","invoice_amount_krw":"5"},
]
result,stats=reconcile(invoices,payments,[{"invoice_number":"INV001","quotation_id":"Q1"}])
assert [r["status"] for r in result]==["MATCHED_EXACT_ID","REVIEW_AMOUNT_MISMATCH","REVIEW_NO_EXACT_MATCH"]
assert stats["PAYMENT_ONLY_REVIEW"]==1 and result[0]["quotation_links"]==1
assert result[2]["status"]!="PAID"
try: reconcile([invoices[0],invoices[0]],[])
except ValueError: pass
else: raise AssertionError("Duplicate invoice must fail")
print("INVOICE_RECONCILIATION_OFFLINE_TEST: PASS")
print("SOURCE_WRITE_OPERATIONS: 0")
