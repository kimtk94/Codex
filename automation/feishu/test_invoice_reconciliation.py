"""Synthetic tests only. No real customer data or API access."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from invoice_reconciliation import reconcile, operational_status
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

# User-confirmed business priority: Outstanding = unpaid; issued invoice = operationally okay.
statuses=operational_status(["AMEA1","AMEA2","AMEA3",""], [{"project_id":"AMEA1"},{"project_id":"AMEA2"}], [{"project_id":"AMEA1"}])
assert [x["operational_status"] for x in statuses]==[
    "OUTSTANDING_UNPAID",
    "INVOICE_ISSUED_OK_PAYMENT_UNVERIFIED",
    "REVIEW_NO_INVOICE_NO_OUTSTANDING",
    "REVIEW_MISSING_PROJECT_ID",
]
amount_test,_=reconcile([{"invoice_number":"INV004","amount_krw":"4,438,500 KRW"}],[{"invoice_number":"INV004","invoice_amount_krw":"4438500"}])
assert amount_test[0]["status"]=="MATCHED_EXACT_ID"
bad_test,_=reconcile([{"invoice_number":"INV005","amount_krw":"NOT_AVAILABLE"}],[{"invoice_number":"INV005","invoice_amount_krw":"1000"}])
assert bad_test[0]["status"]=="REVIEW_AMOUNT_UNPARSEABLE"
