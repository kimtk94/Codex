# Salesforce Desktop RPA — Independent Reloads & Private Output Gate (2026-11-03 KST)

## Progress and safety
The authenticated, previously verified existing Salesforce Opportunity was read twice using the existing non-writing Snapshot CLI on the authorized Windows PC `NGKR-SAL-TH`. There is **no changed-value pilot approval** and **no CRM Save**. No production write readiness is claimed.

## Verified live outcome
- Original read-only snapshot: `opportunity_reloaded_snapshot_20261103_PRIVATE.json`.
- Second **independent live page reload and snapshot**: `opportunity_reloaded_snapshot_20261103_repeat_PRIVATE.json`.
- The first and second capture timestamps differed by approximately **2,473 seconds** (41 minutes), and were separately generated from Salesforce UI on the authorized desktop.
- The exact target Opportunity, existing Account and Main Contact native record links, and all three supported fields (`Opportunity Name`, `Amount`, `Close Date`) were identical.
- The direct existing snapshot comparator returned `SNAPSHOTS_MATCH_NOT_PROOF_OF_SAVE`.
- The new paired freshness comparator returned **`TWO_RELOADED_BASELINES_MATCH_NOT_SAVE_PROOF`**; it rejects timestamp reversal, duplicate timestamps, reload gaps exceeding two hours, age exceeding four hours, timezone-less/too-far-future timestamps, ID/link differences, field drift, malformed snapshots and fake post-Save attestation.
- Existing private operation ledger read-only health: **0 entries**, **0 unresolved operations**, no lock, `save_allowed=false`.
- **No Salesforce Save, lookup choice, field change or customer email was performed.**

## New code and regression tests
- `capture_existing_opportunity_snapshot.py`: customer-bearing snapshot outputs restricted to new filenames ending `_PRIVATE.json` directly inside the Windows user's `~/.sfdc_desktop` directory. Reject repository paths, arbitrary output directories, relative/traversal paths, dotfiles, existing outputs, symlinks and linked private directories.
- `test_snapshot_private_output.py`: 10 privacy-output tests; two Windows symlink tests are skipped when symlink creation is not available.
- `verify_reloaded_snapshot_pair.py`: compares two **time-ordered, recently captured, independently reloaded** snapshots offline. Produces counts/status only. It never attests a Salesforce Save.
- `test_verify_reloaded_snapshot_pair.py`: 18 synthetic regression tests of identity, time, field and no-Save contracts.

## Tests
- Windows full Desktop RPA suite: **304 tests completed successfully**, **2 skipped** due to Windows symlink creation limitations.
- GitHub Actions `Salesforce Desktop RPA P0 tests`, run **41566152123 SUCCESS**; Vercel CSS-Kalman Change Scope Audit also SUCCESS at commit `7418c06`.
- All code and synthetic fixtures are on `feat/sfdc-playwright-desktop-p0`, PR #263.
- Actual private customer data, Salesforce record IDs, source values, browser credentials, Chrome session and ledger are **never committed to GitHub or uploaded as CI artifacts**.

## Private files (on NGKR-SAL-TH only)
- `%USERPROFILE%\.sfdc_desktop\opportunity_reloaded_snapshot_20261103_PRIVATE.json`
- `%USERPROFILE%\.sfdc_desktop\opportunity_reloaded_snapshot_20261103_repeat_PRIVATE.json`
- `%USERPROFILE%\.sfdc_desktop\independent_reloads_audit_20261103_PRIVATE.json`

## Next gates
1. Exact real new deal values require user review, target/link verification and a separately approved Cancel-only pilot. Existing private change template is unapproved and contains no proposed changes.
2. An actual Save requires separate explicit authorization, durable reservation, duplicate/in-flight lock and real post-Save browser reload/readback, plus human review. Matching before-state snapshots never authorize or prove Save.

## Safe local repeat on authorized workstation
```powershell
$repo="$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git="$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/inspect_save_journal.py
python automation/sfdc_desktop/verify_reloaded_snapshot_pair.py --first "$env:USERPROFILE\.sfdc_desktop\opportunity_reloaded_snapshot_20261103_PRIVATE.json" --second "$env:USERPROFILE\.sfdc_desktop\opportunity_reloaded_snapshot_20261103_repeat_PRIVATE.json" --output "$env:USERPROFILE\.sfdc_desktop\independent_reloads_audit_NEW_PRIVATE.json"
```

If the previous snapshots have aged out, expect HOLD and obtain new independent live reloads; do not suppress the freshness condition.
