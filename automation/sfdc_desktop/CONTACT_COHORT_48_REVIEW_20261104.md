# Salesforce Korean Contact cohort verification — 2026-11-04

Scope: 48 distinct explicitly Korean-labelled Contact candidates from the historical 180-Opportunity sample, not all Salesforce contacts.

Authenticated read-only checks completed: 48 of 48.
Verified name, email, Contact ID, Account ID and existing Opportunity association: **38**.
HOLD pending additional independent name/relationship evidence: **10**.
Not checked: **0**.

Three new batches covering the last 28 unreviewed candidates produced:
- Batch at offset 20: 8 PASS, 2 name-display HOLD.
- Batch at offset 30: 8 PASS, 2 HOLD (one name-display, one Account-link check).
- Batch at offset 40: 7 PASS, 1 name-display HOLD.

Diagnostic of all 10 HOLDs: expected full display names were not visible on Contact Details at recheck. No identity criteria were relaxed or inferred.

The existing private web Contact JSON contains 38 accepted aliases. Local module readback: 38/38 exact Contact and Account matches, 35 distinct Korean names, 3 homonym groups, no displayed-name-plus-institution-plus-suffix collisions.

Reconciliation tool: `audit_korean_contact_cohort_private.py`. Source and output records remain under the private workstation's `.sfdc_desktop` folder; no personally identifying data is committed or logged. Three original HOLDs are explicitly treated as historic cases lacking the new attempt ledger, not as untested records.

No Salesforce Save, Update, Create, or Production web deployment was performed.

Remaining: recheck 10 HOLD identities using independent official Contact fields; expand beyond the historical 180-Opportunity source into the 1,013 in-scope Opportunities; integrate authenticated read-only server-side lookup instead of manual local JSON.
