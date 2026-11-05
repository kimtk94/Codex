# Existing Opportunity no-Save pilot — 2026-11-02 KST

## Verified scope
- Authorized device: NGKR-SAL-TH. Authenticated browser: dedicated Chrome profile, CDP loopback only.
- An existing Opportunity was uniquely resolved through **Opportunity > Related > Quotation > exact-QID Salesforce report > one business Opportunity ID**. Source proof: `verified_live_quotation_report_bridge.json` on the workstation only.
- The live Opportunity **Details** screen exposed inline Edit controls for Opportunity Name, Account Name, Main Contact, Stage, Amount, Close Date and Service Line.
- Clicking the inline Account editor exposed **one Account Name lookup** and **one Main Contact lookup** with the correct search prompts. Existing selections appeared as read-only comboboxes, while End User Account/Contact were editable search controls.
- Both editor probes were ended with **Cancel**. No Salesforce Save and no Lookup selection.
- A no-change fill-only pilot opened the Opportunity Name editor, typed **the exact unchanged existing value**, confirmed the value remained equal, and clicked **Cancel**. No actual change was submitted.
- The actual Details field links contained exactly **one labeled Account Name link** with an 18-character Salesforce Account `001...` ID and **one labeled Main Contact link** with an 18-character Salesforce Contact `003...` ID. A separate global Account link was excluded by the field-label gate.

## Code / reproducible checks
- `audit_existing_opportunity_no_save.py`: validates the exact verified Opportunity route, rejects pre-existing edit sessions, inspects lookup controls, performs no-change name fill and Cancel, and saves redacted audit metadata locally.
- `capture_existing_lookup_links.py`: strictly resolves the Account/Contact record IDs from the correct Details fields, requiring one correct ID per label and rejecting global/unlabeled or End User links.
- `test_existing_opportunity_no_save.py` and `test_existing_lookup_record_links.py`: synthetic regressions for wrong IDs, invalid bridge, duplicate or mislabeled links, and pre-existing unsaved editors.
- Windows Desktop RPA `python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q`: **113 tests PASS**.
- Direct local audit scripts: both exited **0**.
- Source branch: `feat/sfdc-playwright-desktop-p0`, PR #263; Windows worktree synced to `e05d043`.

## Private evidence
Only on the Windows PC (never commit or attach to CI):
- `%USERPROFILE%\.sfdc_desktop\verified_live_quotation_report_bridge.json`
- `%USERPROFILE%\.sfdc_desktop\existing_opportunity_no_save_audit.json`
- `%USERPROFILE%\.sfdc_desktop\existing_lookup_record_ids_private.json`

These contain exact record IDs or private operational evidence. GitHub holds **code, redacted status and synthetic fixtures only**.

## Remaining gates
1. The **UI structure and existing target Account/Contact IDs are verified for this specific Opportunity**, not permission to select a new customer for a new Opportunity. A new Opportunity Lookup must be matched to the intended Account/Contact record ID and validated after selection, never only by display name.
2. Changes to actual deal values require reviewed user input; never inherit historical amount, stage or close date automatically.
3. Salesforce Save remains prohibited until explicit pilot approval, duplicate/idempotency controls, record identity preflight, post-save readback and ledger updates are implemented. In the meantime, safe tests use unchanged values and Cancel.
4. Before every replay, recheck the live device, authenticated session, exact Salesforce record route, current bridge, and that no pre-existing editor is open.

## Replaying on the authorized desktop
```powershell
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
$git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe"
& $git -C $repo pull --ff-only origin feat/sfdc-playwright-desktop-p0
Set-Location $repo
python -m unittest discover -s automation/sfdc_desktop -p "test_*.py" -q
python automation/sfdc_desktop/audit_existing_opportunity_no_save.py
python automation/sfdc_desktop/capture_existing_lookup_links.py
```
