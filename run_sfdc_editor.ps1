# SFDC desktop launcher: pull branch, prepare current deal, and start local editor.
# Run from any location in the Codex-SFDC-Git working tree.
param(
 [string]$RunId = "40300179306",
 [switch]$NoPull,
 [switch]$FillBlanks,
 [switch]$OpenSalesforce
)
$ErrorActionPreference="Stop"
$repoRoot=(git -C $PSScriptRoot rev-parse --show-toplevel).Trim()
if ($LASTEXITCODE -ne 0 -or -not $repoRoot) { throw "Run this script in the Codex Git repository." }
Set-Location $repoRoot
$branch="feat/sfdc-playwright-desktop-p0"
$current=(git branch --show-current).Trim()
if ($current -ne $branch) { throw "Expected branch $branch, currently $current. Switch branches manually to avoid overwriting work." }
if (-not $NoPull) {
 git fetch origin $branch
 if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }
 git pull --ff-only origin $branch
 if ($LASTEXITCODE -ne 0) { throw "git pull --ff-only failed; resolve locally, no overwrite attempted." }
}
$base=Join-Path $env:LOCALAPPDATA "SFDC\Catalog\$RunId"
$draft=Join-Path $base "verified_existing_to_new_draft.json"
$values=Join-Path $base "current_deal.json"
if (-not (Test-Path $draft)) { throw "Existing verified source draft not found: $draft" }
$pyArgs=@("-3.12","automation\sfdc_desktop\prepare_editable_deal.py","--draft",$draft,"--output",$values)
if ($FillBlanks) { $pyArgs+= "--fill-blanks" }
& py @pyArgs
if ($LASTEXITCODE -ne 0) { throw "Could not prepare editable deal." }
$editorUrl="http://127.0.0.1:8765"
Write-Host "Opening editor: $editorUrl"
Write-Host "Use the 'save and fill open New Opportunity' button after reviewing all deal values."
Write-Host "Salesforce Save is NEVER clicked by this launcher."
if ($OpenSalesforce) { Start-Process "https://novogene.lightning.force.com/lightning/o/Opportunity/list" }
& py -3.12 "automation\sfdc_desktop\deal_editor.py" --values $values --open-browser
if ($LASTEXITCODE -ne 0) { throw "Local editor exited with an error" }
