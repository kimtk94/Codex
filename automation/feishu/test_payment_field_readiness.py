"""Synthetic tests of Payment field readiness. No Feishu credentials or customer data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
from payment_table_audit import field_readiness

fields=[
 {"field_name":"Invoice Number"},
 {"field_name":"Invoice Amount"},
 {"field_name":"Payment Date"},
]
assert field_readiness(fields)=={"invoice_id":True,"amount":True,"payment_evidence":True}
assert field_readiness([{"field_name":"Invoice Number"}])=={"invoice_id":True,"amount":False,"payment_evidence":False}
assert field_readiness([{"field_name":"세금계산서 번호"},{"field_name":"미수금"},{"field_name":"입금액"}])=={"invoice_id":True,"amount":True,"payment_evidence":True}
assert field_readiness([{"field_name":"Unrelated"}])=={"invoice_id":False,"amount":False,"payment_evidence":False}
print("PAYMENT_FIELD_READINESS_SYNTHETIC_TEST: PASS")
