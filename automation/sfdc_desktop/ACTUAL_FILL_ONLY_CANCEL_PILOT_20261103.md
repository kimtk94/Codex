# Salesforce existing Opportunity — Authorized fill-only pilot (2026-11-03 KST)

## Real Salesforce result

**PASS: temporary Opportunity Name fill → Cancel → original value restored → fresh page reload confirms original value.**

On the authorized Windows workstation `NGKR-SAL-TH`, the user explicitly requested a **fill-only and Cancel** pilot for one already independently verified existing Salesforce Opportunity and specified the temporary replacement name `Korea-test`. The approved scope was **only** a reversible UI input rehearsal, not Salesforce Save.

Observed actual Salesforce UI proof:
- Verified exact target using the existing local authoritative Related-Quotation + Salesforce Report business-ID bridge.
- Confirmed prior private baselines and previously verified native Account/Main Contact lookup IDs.
- Before opening the editor: one unique target Opportunity tab and zero Save/Cancel editing controls.
- Opened the exact Opportunity Name editor. Existing value matched the previously verified baseline; the newly specified temporary value appeared in the input control.
- Clicked **Cancel**. The editor closed.
- Reopened the field without typing any value and confirmed the original value was restored; clicked Cancel again.
- Reloaded the exact Salesforce Opportunity page. Confirmed original Opportunity Name persisted, native Account and Contact links remained unchanged, and no unsaved editor was open afterward.
- **Never clicked Salesforce Save**, never changed a lookup, never sent customer email. No committed CRM change.
- Actual private result: `PASS_TEMPORARY_FILL_CANCEL_RESTORED`.

## Lightning race fix

The first attempt surfaced an existing Salesforce Lightning rendering race: the editable input can appear before the Cancel footer is visible, leading to a Cancel lookup error. The open editor was safely dismissed and presence of zero Save/Cancel controls reconfirmed. The implementation `rehearse_existing_change_cancel.rehearsal_field` was then hardened to **wait for a unique visible Cancel before any changed-value input**. Its fake UI tests were updated. After this fix, the real user-authorized pilot passed and all post-Cancel/reload checks succeeded.

## Tests and source

- Windows full `automation/sfdc_desktop` suite: **304 tests OK, 2 skipped** due to Windows symlink privilege limitations; failures 0.
- GitHub Actions Salesforce Desktop RPA P0 tests: **run 41567265675 SUCCESS**.
- Implementation branch: `feat/sfdc-playwright-desktop-p0` (PR #263); fix commit `8f38a11`.
- The private audit is stored solely in `%USERPROFILE%\.sfdc_desktop\fill_only_korea_test_result_20261103_PRIVATE.json`; original customer name, native Salesforce IDs, browser session, quotation evidence and private ledger are **not uploaded** to GitHub.
- The existing private change-review template and operation ledger were not rewritten by this pilot. Save remains disabled in the pilot code.

## Remaining milestone

The authorized fill-only test milestone for this record is complete. **Actual Salesforce Save remains a separate operation and needs explicit authorization**, reviewed final value(s), idempotent operation reservation and real post-Save readback/ledger confirmation. The present pilot explicitly did not authorize a Save.
