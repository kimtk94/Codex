# SFDC existing-Opportunity Save journal — 2026-11-02 checkpoint

## Progress and authority
- Existing Opportunity identity was verified using Related Quotation → exact-QID Salesforce report → matching business Opportunity ID. Existing Account and Main Contact ID links were validated locally.
- Name/Amount/Close Date same-value fill + Cancel and private change-review template were previously tested.
- **No reviewed actual changed values** and **no authorization to Save**. The private review template remains unapproved. Do not click Salesforce Save.
- New work is a **durable offline state journal and safety contracts**, not a Salesforce save executor.

## Implemented
- `manual_save_journal.py`:
  - Strict use of the dedicated private PC ledger `%USERPROFILE%\.sfdc_desktop\operation_ledger_private.json`. Missing or corrupt existing file fails closed; never silently starts a new history.
  - Atomic directory lock prevents concurrent operations. Abandoned lock remains a HOLD requiring manual investigation; it is **never auto-stolen by timeout**.
  - Local JSON ledger replacement uses write→flush→fsync→atomic replace; rejects duplicate request UID, fingerprint or same change intent under another request UID.
  - Reservation requires previously verified preflight, fresh before-value evidence and specific external Save approval. Reservation is only `PREPARED` and **never performs Save**.
  - Pure state transitions distinguish manual external Save start, unknown result, readback required, and matching readback awaiting further review. `WRITE_OUTCOME_UNKNOWN` cannot transition back into automatic Save retry. Even a matching supplied readback JSON becomes `READBACK_MATCH_REVIEW_REQUIRED`, **not VERIFIED**.
  - No Salesforce API, browser credentials, screenshot, or save button interaction.
- `inspect_save_journal.py`: read-only local ledger health with **only counts/states**, no raw record IDs or private field values.
- `test_manual_save_journal.py` and `test_inspect_save_journal.py`: synthetic temp-directory tests for duplicate UIDs/intents, corrupt ledger, stale lock, atomic replace failure, unknown result, wrong Account/Contact readback, and incomplete manual verification.

## Actual validation
- Authorized Windows device `NGKR-SAL-TH`: **235/235** Desktop RPA unit tests PASS.
- GitHub Actions `Salesforce Desktop RPA P0 tests` run **41451439084 SUCCESS** (commit `6322799`).
- Read-only journal health inspection on the actual PC:
  - `total_requests=0`
  - `lock_present=false`
  - `unresolved_operation_count=0`
  - `status=LEDGER_READ_ONLY_VALID`
  - `save_allowed=false`, no CRM Save.
- Customer records, exact Salesforce IDs, browser session and private ledger/templates are stored only on the Windows PC; GitHub contains only synthetic tests and redacted status.
- Feature branch `feat/sfdc-playwright-desktop-p0`, PR #263.

## Safe commands (on authorized Windows workstation)

```powershell
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/inspect_save_journal.py
python automation/sfdc_desktop/rehearse_existing_change_cancel.py
```

The last command must remain `HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED` until actual changes are explicitly reviewed. The journal health command is read-only; healthy journal status does **not** authorize CRM Save.

## Remaining blockers
1. A human-reviewed actual changed-value fill-only pilot for the exact existing Opportunity, then verified Cancel with original value restored. This has **not** occurred.
2. Separate approval for production Save, and a true authenticated browser read-after-reload implementation with trustworthy evidence and durable manual review. This has **not** occurred. Never treat mocked or user-supplied readback JSON as proof of an actual Save.
