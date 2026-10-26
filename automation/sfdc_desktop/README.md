# Salesforce Desktop RPA — P0 (API-free)

**Status: safe proof of concept.** This does not write Salesforce records. No Salesforce API is used. UI access does not establish Create/Edit access. Requires organization's authorization for UI automation.

## Architecture

Existing Codex CSS / SFDC / Google Sheets jobs -> reviewed CSV queue -> Windows Playwright UI worker -> human verifies form -> later approved save + result ledger.

CSV is a temporary integration boundary; do not add a duplicate source-of-truth Sheet. Once verified, map to existing SFDC Action Center / Opportunity data and write back a status ledger using the established Google Sheets authentication.

## Windows setup (PowerShell)

```powershell
git clone https://github.com/kimtk94/Codex.git
cd Codex
git switch feat/sfdc-playwright-desktop-p0
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r automation\sfdc_desktop\requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe automation\sfdc_desktop\runner.py --url "https://YOURDOMAIN.lightning.force.com/lightning/page/home" --mode audit
```

Chrome must be installed (channel=chrome); if not, remove channel setting and run Playwright Chromium. Log in manually with MFA in visible browser, then hit Enter in PowerShell. Only use company-approved endpoints.

## Queue contract (local CSV)

`source_id,object_type,record_key,Name,Subject,Description,Phone,Email,StageName,CloseDate,Amount`.

- `source_id`: CSS/Sheet stable event identifier; `record_key`: canonical business duplicate key.
- `object_type`: Account, Contact, Opportunity or Task.
- All values must be validated and deduplicated upstream. Never include passwords or session tokens.
- Do not commit CSV, UI selectors, Playwright profile, customer data, or session recordings.
- `--mode queue-check --queue path.csv` validates queue locally without launching a browser.
- `--mode fill --allow-fill --queue path.csv --mapping local_mapping.json` navigates and fills *only*. Never clicks Save.
- Mapping is per-org and must be inspected from live Salesforce UI. Do not guess selectors.

## Before enabling Save (P1 gate)

1. Capture allowed Salesforce navigation, New/Edit button visibility and real Create/Edit rights for each target object.
2. Establish a stable field mapping for the active Lightning page; test in Sandbox or with disposable records under authorization.
3. Implement record lookups and record-key idempotency; never blindly retry a Save after timeout.
4. Verify saved record detail URL/ID, Sheet ledger write-back, and exclusive queue claiming to avoid duplicates.
5. Explicit approval for Quote / Contract and bulk mutations, redact logs and apply rate limits. Do not attempt CAPTCHA/MFA bypass.
6. Ensure Windows interactive session stays unlocked where required; use Windows Task Scheduler only after reliable UI tests.

## Reuse the existing Opportunity catalog (read-only)

The source is the existing Google Sheet `SFDC_Automation_Followup_2026`,
tab `SFDC Opportunity Template Catalog`. No new CSV is necessary.

On Windows, use a Git-enabled terminal, or portable Git using its full executable path:

```powershell
& "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe" pull origin feat/sfdc-playwright-desktop-p0
py -3.12 -m pip install -r automation\sfdc_desktop\requirements.txt
$env:GOOGLE_APPLICATION_CREDENTIALS = "$env:USERPROFILE\.config\sfdc-google-reader.json"
py -3.12 automation\sfdc_desktop\catalog_reuse.py --account "Yonsei" --service "mRNA" --top 10 --output "$env:LOCALAPPDATA\sfdc_catalog_matches.json"
```

The service account must already have access to the Sheet. The JSON key must stay
outside the repo and must never be committed or sent to chat. You may use the
existing company-approved Google authentication mechanism instead by configuring
`GOOGLE_SERVICE_ACCOUNT_JSON` in the environment.

Optional offline mode: `--csv path.csv`. Search results are **historical** and do
not validate Salesforce Lookup relations, permissions, or current opportunity status.
The draft intentionally leaves amount, close date, stage, and service blank. The
command never submits anything to Salesforce.

### Single-command read-only catalog smoke test (Windows)

From the Git clone (not a ZIP directory), run:

```powershell
$ErrorActionPreference = "Stop"
$repo = "$env:USERPROFILE\Codex\Codex-SFDC-Git"
Set-Location $repo
if (-not (Test-Path ".git")) { throw "Clone the GitHub repository first; this is not a Git working tree." }
$git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
if (-not $git) { $git = "$env:LOCALAPPDATA\Programs\PortableGit\cmd\git.exe" }
if (-not (Test-Path $git)) { throw "Git is not installed in a known location." }
& $git pull --ff-only origin feat/sfdc-playwright-desktop-p0
if ($LASTEXITCODE -ne 0) { throw "Git pull failed" }
py -3.12 -m pip install -r automation\sfdc_desktop\requirements.txt
py -3.12 -m pytest automation\sfdc_desktop -q
py -3.12 automation\sfdc_desktop\catalog_reuse.py --account "Yonsei" --service "mRNA" --top 5 --output "$env:LOCALAPPDATA\sfdc_catalog_matches.json"
```

The catalog command first tries the configured service account (environment variable),
then Google Application Default Credentials (ADC). If no credentials are available,
the command fails safely without Salesforce writes. Grant read permission to the
existing account as appropriate; never paste credential JSON into chat or commit it.
