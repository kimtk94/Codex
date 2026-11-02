# SFDC Existing Opportunity — Live Before-Value and Save Contract (2026-11-02)

## Verified state
- Prior read-only evidence established one exact Salesforce Opportunity via its Related Quotation and a live, exact-QID-filtered Salesforce report. Private Salesforce/Novogene identifiers remain only on NGKR-SAL-TH.
- Account and Contact field-linked record IDs were captured from the current Opportunity Details UI and verified.
- Same-value Name, Amount and Close Date edits were tested in Salesforce and each ended with **Cancel**, never Save.
- Current private review template exists but contains **no approved changes**: `reviewed_current_deal_values=false`, `changes={}`.

## New fail-closed modules
- `verify_existing_live_before.py`: requires a reviewed request, exact native and business record identity, Account/Contact ID match, a complete versioned private operation ledger and a fresh Salesforce UI check of each proposed field's **exact before-value**. Differences in formatting or value result in HOLD instead of automatic conversion. All read-only editor openings end with Cancel. There is **no changed-value fill** or Save in this module.
- `save_readback_contract.py`: pure offline simulation of future Save approval, processing-state ledger and strict post-save readback. Even if all synthetic evidence passes, the module **never returns save_allowed=true** and has **no CRM I/O**.
- `prepare_existing_change_review.py`: now calculates two hashes: request-specific `operation_fingerprint` and a request-UID-independent `change_intent_fingerprint` to reject duplicate business changes submitted under a new UID.
- Synthetic tests verify wrong/missing IDs, stale/changed before-values, no/invalid ledger, duplicate UIDs, duplicate intent across UIDs, unknown in-flight write outcome, missing Save approval, and post-save record/Account/Contact/field mismatch.

## Actual execution outcome
- Windows Desktop RPA unit tests **193/193 PASS**.
- Running the new verifier against the existing PRIVATE unreviewed template returned **HOLD_REVIEW_REQUIRED**; live before-read was not attempted, no Salesforce fields were changed, no Save.
- Initialized `%USERPROFILE%\.sfdc_desktop\operation_ledger_private.json` with `{"version":"sfdc-local-operation-ledger-v1","entries":[]}`, validated 0 entries. The bootstrap preserves any existing ledger rather than overwriting it.
- Customer names, actual field values, exact record IDs, browser tokens and private ledger never enter GitHub or CI artifacts.
- Feature branch: `feat/sfdc-playwright-desktop-p0`, PR #263.

## Outstanding operational gates
1. **Real changed-value fill-only pilot**: Requires explicit reviewed current deal fields; current draft has none. No arbitrary synthetic value is used in the live CRM. The exact UI before-value check is ready but has not been exercised against a reviewed change request.
2. **Actual Save**: Still unauthorized and not implemented in these modules. Must separately establish user-approved record and values, safe in-flight lock, collision check, observed field-after-fill check, idempotent retry behavior, post-Save page reload, detailed record/linked-Account/Contact readback, and durable ledger verification. Save must remain unavailable until those gates pass.

## Run on authorized Windows desktop
```powershell
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/verify_existing_live_before.py
```

An unreviewed template must return `HOLD_REVIEW_REQUIRED`; this is the correct safe result, not a defect.
