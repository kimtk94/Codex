# SFDC reloaded Opportunity readback — checkpoint (2026-11-03 KST)

## Summary
On the authenticated Windows workstation `NGKR-SAL-TH`, the previously proven existing Salesforce Opportunity was reloaded and **read without any Save**. The live result agrees with a prior private change-review reference and the existing Account / Main Contact record links. No actual changed-value pilot or CRM Save was performed.

## Live validation
- One exact existing Opportunity tab and zero pre-existing Save/Cancel edit controls before the run.
- The first attempt after reload exposed a Salesforce Lightning render race: the field input appeared before the Cancel button was detectable. The helper `make_existing_change_template.current_value` now explicitly waits for the Cancel action to become visible before reading. The temporary editor left open on the failed first attempt was dismissed via **Cancel**; the subsequent run succeeded.
- A fresh reload then re-read exactly **3 fields** (`Opportunity Name`, `Amount`, `Close Date`) through existing edit-form read and **Cancel**. No new values were filled.
- Exact native `006` Opportunity ID matched previous authoritative ID proof; exact `001` Account and `003` Main Contact field IDs matched their earlier verified references.
- All 3 current field values exactly matched their earlier private template reference values.
- Current live UI post-run: **1 target Opportunity tab, 0 Save and 0 Cancel controls**.
- Current snapshot is `post_save_attested=false` / `salesforce_save_performed=false`; it does **not** imply or prove a prior Salesforce Save. The business Opportunity ID comes from the **previously verified Quotation report bridge**, not from a freshly refetched Quotation report.

## New implementation
- `capture_existing_opportunity_snapshot.py` creates a strictly validated, private reloaded snapshot, refuses stale-page capture and prior file overwrite, checks target and linked Account/Contact IDs, and compares two snapshots for drift. Return `SNAPSHOTS_MATCH_NOT_PROOF_OF_SAVE` expressly does not indicate CRM write success.
- `review_existing_readback_snapshot.py` is an **offline-only** comparator of a reviewed change request, preflight fingerprint, explicit Save approval, local ledger state, and a fresh UI snapshot captured **after** a separately recorded external Save event. It returns only `READBACK_CONTENT_MATCH_REVIEW_REQUIRED` (or HOLD); it cannot certify Salesforce Save completion, and never changes CRM or the ledger.
- Both have synthetic test suites for absent/invalid attestations, changed IDs, changed fields, stale timestamps, duplicate/missing operation evidence, and no approval.
- The change-review template is currently **unapproved and unchanged**; the real local comparator returned **`HOLD_CHANGE_REVIEW_MISSING`**, and did not attempt an external Save.

## Local-only sensitive artifacts
- `%USERPROFILE%\.sfdc_desktop\opportunity_reloaded_snapshot_20261103_PRIVATE.json`: contains real field values and native IDs; never upload.
- `%USERPROFILE%\.sfdc_desktop\readback_review_20261103_PRIVATE.json`: safe HOLD result.
- Existing business-ID bridge, account/contact link evidence, review template, and operation ledger remain in the same private workstation directory.
- No private customer data, cookies, exact record IDs, quotation IDs, or field values are in GitHub.

## Tests and permissions
- Windows `python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q`: **276/276 PASS**.
- Code branch `feat/sfdc-playwright-desktop-p0`, PR #263.
- **Salesforce Save not executed.** No lookup selection, no Opportunity data modifications, no new customer email.
- GH Actions `Salesforce Desktop RPA P0 tests`: see associated branch workflow.

## Remaining critical work
1. Obtain genuinely reviewed new deal values for the exact record; run approved cancel-only fill rehearsal; confirm Cancel restored original values.
2. A separate explicit authorization and human-supervised first Salesforce Save; then fresh browser readback, duplicate reconciliation, and final ledger review. Offline evidence alone does not authorize Save or mark a record VERIFIED.

## Safe read-only replay
```powershell
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/capture_existing_opportunity_snapshot.py --output "$env:USERPROFILE\.sfdc_desktop\opportunity_reloaded_snapshot_NEW_PRIVATE.json"
python automation/sfdc_desktop/review_existing_readback_snapshot.py --output "$env:USERPROFILE\.sfdc_desktop\readback_review_NEW_PRIVATE.json"
```

For the last command, an unapproved request must return HOLD without accessing any Save approval.
