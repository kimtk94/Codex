import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from sfdc_quote_contact_candidate_audit import audit
q=[{"matched_opportunity_name":" Project Alpha "},{"matched_opportunity_name":"Project B"},{"matched_opportunity_name":""}]
o=[{"Opportunity Name":"project alpha","Main Contact":"A"},{"Opportunity Name":"Project B","Main Contact":"B"},{"Opportunity Name":"PROJECT B","Main Contact":"C"}]
r=audit(q,o)
assert r["UNIQUE_NAME_WITH_CONTACT_CANDIDATE"]==1
assert r["AMBIGUOUS_OPPORTUNITY_NAME"]==1
assert r["NO_OPPORTUNITY_NAME"]==1
assert r["VERIFIED_CONTACT_ATTRIBUTIONS"]==0
print("QUOTE_CONTACT_CANDIDATE_TEST: PASS")
