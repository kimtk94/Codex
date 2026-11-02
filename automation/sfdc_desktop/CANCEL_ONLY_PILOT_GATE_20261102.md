# SFDC Existing Opportunity — Cancel-only changed-value pilot gate
Date: 2026-11-02 (Asia/Seoul)

## Current status
- Source record uniquely linked through Opportunity > Related > Quotation > Salesforce live report.
- Existing Account (001...) and Main Contact (003...) record-link evidence stored PRIVATELY on NGKR-SAL-TH.
- Private change-review template exists, but **no actual changed values are approved**; reviewed flag is false and proposed changes are empty.
- No Salesforce Save or customer data change was executed.

## Added code
- `rehearse_existing_change_cancel.py`: strict **existing Opportunity** changed-value rehearsal with no Save functionality. Connects only to local authorized Chrome CDP.
- Requires two independent private request flags:
  - `reviewed_current_deal_values = true`, accompanied by explicitly reviewed expected-before and changed values.
  - `fill_only_pilot_approved = true` AND `approved_fill_only_request_uid` matching the request UID.
- Requires a versioned private ledger and rejects duplicate UID / identical change intent under another UID. Live current Opportunity, Account and Contact ID are revalidated before any field.
- Supports only `Opportunity Name`, `Amount` and `Close Date`. Stage, currency, lookups, Progress Description and other fields remain blocked pending separate mapping/tests.
- For each field: uniquely locate the editor; **compare the currently displayed input to reviewed expected-before inside that same edit session**; fill the reviewed proposed value; check the displayed value; click **Cancel in finally**; open a fresh editor to verify the original input was restored and Cancel again. No Save click exists in the module.
- Any missing approval, changed/stale before-value, wrong input, autoformat surprise, ambiguous control or incomplete cancel results in HOLD / safe abort (or exception with no Save).
- Logs redact all customer names, values and native record IDs. Private report saved under `%USERPROFILE%\.sfdc_desktop\cancel_only_rehearsal_private.json`.

## Actual validation
- Desktop full unittest discovery: **208/208 PASS**.
- Synthetic mocked UI tests: approved reviewed field, stale changed-by-another-user, autoformatted new value, fail during fill, wrong field, Amount/Close Date correct input selection, mismatch after Cancel, and duplicate/unreviewed request. All assert **Save never clicked**.
- Execution against current private unreviewed request: **HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED**, **0 fields rehearsed**, **0 Save**; no authenticated Chrome connection on this HOLD path.
- Local workstation: branch `feat/sfdc-playwright-desktop-p0` at or beyond commit `eff7084`.
- The existing customer/private review JSON was not modified by this implementation. Code and synthetic tests only are committed to GitHub PR #263.

## Remaining tasks
1. **Actual changed-value fill-only pilot** needs real new deal values reviewed by the owner for that exact verified Opportunity. Use private template and validate live current-before values. Until approval, do not type synthetic changes in actual Salesforce.
2. **Save/post-save verification** is a separate future operation requiring explicit Save approval, idempotency lock and durable ledger, collision checks, exact post-save reload and Account/Contact/field readback. None of these grant permission to click Save today.

## Run on authorized workstation
```powershell
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/rehearse_existing_change_cancel.py
```

Expected until manually reviewed: `HOLD_REVIEW_OR_PILOT_APPROVAL_REQUIRED` / no Salesforce action. Never upload private JSON/customer identifiers, browser credentials or session profile to GitHub.
