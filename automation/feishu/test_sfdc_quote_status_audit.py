"""Synthetic regression; no Google account or client data."""
import sys,types
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sfdc_quote_status_audit import audit
summary=audit(
 [{"quotation_id":"AMEA1","salesforce_record_id":"a123"},
  {"quotation_id":"AMEA2","salesforce_record_id":"a124"}],
 [{"quotation_id":"AMEA1"},{"quotation_id":"AMEA2"},{"quotation_id":""}],
 [{"is_active":"","opportunity_id":""}])
assert summary["QUOTE_LINK_RESULT_COUNTS"]=={"MISSING_QUOTATION_ID":1,"QUOTE_ID_RESOLVED":2}
assert summary["ACTIVE_TRUE_EVIDENCE_ROWS"]==0
assert summary["CONTACT_ATTRIBUTIONS"]==0
print("QUOTE_STATUS_AUDIT_SYNTHETIC: PASS")
