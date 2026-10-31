"""Synthetic monthly Feishu eTAX discovery tests."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from etax_monthly_audit import parse_etax_month,select_etax,generic_etax_candidates,undated_candidate_schema

assert parse_etax_month("eTAX - Oct Invoice",2026)==(2026,10)
assert parse_etax_month("eTAX - Nov Invoice",2026)==(2026,11)
assert parse_etax_month("eTAX 2026-12 Invoice",2026)==(2026,12)
assert parse_etax_month("Payment Outstanding 10.20",2026) is None
assert parse_etax_month("eTAX - Oct Invoice",2026)!=(2026,11)
assert select_etax([{"name":"eTAX - Oct Invoice","table_id":"a"},{"name":"eTAX - Sep Invoice","table_id":"b"}],2026,10)[0]["table_id"]=="a"
assert select_etax([],2026,10)==(None,0)
assert select_etax([{"name":"eTAX - Oct Invoice"},{"name":"eTAX - Oct Invoice"}],2026,10)==(None,2)
assert parse_etax_month("eTAX 2026-11 Oct Invoice",2026) is None
assert parse_etax_month("eTAX - Jan Invoice",2027)==(2027,1)
print("ETAX_MONTHLY_SYNTHETIC_TEST: PASS")

assert parse_etax_month("eTax-Invoice",2026) is None
assert len(generic_etax_candidates([{"name":"eTax-Invoice","table_id":"present"}]))==1
assert generic_etax_candidates([{"name":"Payment Outstanding 10.20"},{"name":"eTAX - Oct Invoice"}])==[]
assert len(generic_etax_candidates([{"name":"eTax-Invoice"},{"name":"eTax Invoice"}]))==2
assert undated_candidate_schema([{"field_name":"CMS Invoice Number"},{"field_name":"Invoice Date"}])=={"invoice_id_schema":True,"issue_date_schema":True}
assert undated_candidate_schema([{"field_name":"Customer Name"}])=={"invoice_id_schema":False,"issue_date_schema":False}
print("ETAX_UNDATED_BASE_CANDIDATE_SYNTHETIC_TEST: PASS")
