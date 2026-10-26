param(
    [string]$OpportunityId = "",
    [string]$Account = "",
    [string]$Service = "",
    [string]$Contact = "",
    [string]$Repo = "kimtk94/Codex",
    [string]$OutputDir = "$env:LOCALAPPDATA\SFDC\Catalog"
)
$ErrorActionPreference = "Stop"
if (-not ($OpportunityId.Trim() -or $Account.Trim() -or $Service.Trim() -or $Contact.Trim())) {
    throw "Provide -OpportunityId or at least one of -Account, -Service, -Contact."
}
if ($OpportunityId -and $OpportunityId -notmatch '^[A-Za-z0-9]{15}([A-Za-z0-9]{3})? -ErrorAction SilentlyContinue
if (-not $gh) { throw "GitHub CLI (gh) is required. Install with winget install GitHub.cli or use https://cli.github.com/ ; then run gh auth login." }
& gh auth status --hostname github.com 1>$null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated. Run: gh auth login" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$workflow = "sfdc-opportunity-search.yml"
$start = [DateTimeOffset]::UtcNow
$inputs = @("-f", "opportunity_id=$OpportunityId", "-f", "account=$Account", "-f", "service=$Service", "-f", "contact=$Contact")
& gh workflow run $workflow --repo $Repo --ref main @inputs
if ($LASTEXITCODE -ne 0) { throw "Could not dispatch workflow." }
# Find the run for this invocation; if uncertain, stop instead of downloading another user's artifact.
Start-Sleep -Seconds 4
$runs = & gh run list --repo $Repo --workflow $workflow --event workflow_dispatch --limit 10 --json databaseId,createdAt,status,headBranch
if ($LASTEXITCODE -ne 0) { throw "Failed to list workflow runs" }
$recent = @($runs | ConvertFrom-Json | Where-Object {
    $_.headBranch -eq "main" -and ([DateTimeOffset]$_.createdAt) -ge $start.AddSeconds(-10)
})
if ($recent.Count -ne 1) { throw "Run identity ambiguous (matches=$($recent.Count)). Use GitHub Actions run link to select the exact run." }
$id = $recent[0].databaseId
& gh run watch $id --repo $Repo --exit-status
if ($LASTEXITCODE -ne 0) { throw "GitHub Actions run failed: $id" }
$destination = Join-Path $OutputDir ([string]$id)
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& gh run download $id --repo $Repo --name sfdc-catalog-matches --dir $destination
if ($LASTEXITCODE -ne 0) { throw "Artifact download failed: $id" }
$report = Join-Path $destination "matches.json"
if (-not (Test-Path $report)) { throw "Artifact matches.json missing" }
$data = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
if ($data.salesforce_save_performed -ne $false) { throw "Unexpected report safety flag" }
if ($OpportunityId) {
    if ($data.matches.Count -ne 1 -or $data.matches[0].opportunity_id.Substring(0,15) -cne $OpportunityId.Substring(0,15)) {
        throw "Downloaded match does not correspond to requested Opportunity ID."
    }
}
Write-Host "SUCCESS: $($data.matches.Count) candidates. Report: $report"
Write-Host "No Salesforce record was saved."
) {
    throw "OpportunityId must be 15 or 18 alphanumeric characters."
}
$gh = Get-Command gh.exe -ErrorAction SilentlyContinue
if (-not $gh) { throw "GitHub CLI (gh) is required. Install with winget install GitHub.cli or use https://cli.github.com/ ; then run gh auth login." }
& gh auth status --hostname github.com 1>$null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated. Run: gh auth login" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$workflow = "sfdc-opportunity-search.yml"
$start = [DateTimeOffset]::UtcNow
$inputs = @("-f", "account=$Account", "-f", "service=$Service", "-f", "contact=$Contact")
& gh workflow run $workflow --repo $Repo --ref main @inputs
if ($LASTEXITCODE -ne 0) { throw "Could not dispatch workflow." }
# Find the run for this invocation; if uncertain, stop instead of downloading another user's artifact.
Start-Sleep -Seconds 4
$runs = & gh run list --repo $Repo --workflow $workflow --event workflow_dispatch --limit 10 --json databaseId,createdAt,status,headBranch
if ($LASTEXITCODE -ne 0) { throw "Failed to list workflow runs" }
$recent = @($runs | ConvertFrom-Json | Where-Object {
    $_.headBranch -eq "main" -and ([DateTimeOffset]$_.createdAt) -ge $start.AddSeconds(-10)
})
if ($recent.Count -ne 1) { throw "Run identity ambiguous (matches=$($recent.Count)). Use GitHub Actions run link to select the exact run." }
$id = $recent[0].databaseId
& gh run watch $id --repo $Repo --exit-status
if ($LASTEXITCODE -ne 0) { throw "GitHub Actions run failed: $id" }
$destination = Join-Path $OutputDir ([string]$id)
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& gh run download $id --repo $Repo --name sfdc-catalog-matches --dir $destination
if ($LASTEXITCODE -ne 0) { throw "Artifact download failed: $id" }
$report = Join-Path $destination "matches.json"
if (-not (Test-Path $report)) { throw "Artifact matches.json missing" }
$data = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
if ($data.salesforce_save_performed -ne $false) { throw "Unexpected report safety flag" }
Write-Host "SUCCESS: $($data.matches.Count) candidates. Report: $report"
Write-Host "No Salesforce record was saved."
