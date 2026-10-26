param(
    [string]$OpportunityId = "",
    [long]$RunId = 0,
    [string]$Account = "",
    [string]$Service = "",
    [string]$Contact = "",
    [string]$Repo = "kimtk94/Codex",
    [string]$OutputDir = "$env:LOCALAPPDATA\SFDC\Catalog"
)
$ErrorActionPreference = "Stop"
if (-not ($RunId -gt 0 -or $OpportunityId.Trim() -or $Account.Trim() -or $Service.Trim() -or $Contact.Trim())) {
    throw "Provide -OpportunityId or at least one of -Account, -Service, -Contact."
}
if ($OpportunityId -and $OpportunityId -notmatch '^[A-Za-z0-9]{15}([A-Za-z0-9]{3})?$') {
    throw "OpportunityId must be 15 or 18 alphanumeric characters."
}
$gh = Get-Command gh.exe -ErrorAction SilentlyContinue
if (-not $gh) { throw "GitHub CLI (gh) is required." }
& gh auth status --hostname github.com 1>$null
if ($LASTEXITCODE -ne 0) { throw "GitHub CLI is not authenticated. Run: gh auth login" }
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
$workflow = "sfdc-opportunity-search.yml"
if ($RunId -gt 0) {
    $id = $RunId
    $metaJson = & gh run view $id --repo $Repo --json workflowName,event,headBranch
    if ($LASTEXITCODE -ne 0) { throw "Unable to verify existing run identity." }
    $meta = $metaJson | ConvertFrom-Json
    if ($meta.event -ne "workflow_dispatch" -or $meta.headBranch -ne "main" -or $meta.workflowName -ne "SFDC Opportunity Similarity Search") {
        throw "Run does not match expected SFDC workflow, event or branch."
    }
} else {
    $start = [DateTimeOffset]::UtcNow
    $inputs = @("-f", "opportunity_id=$OpportunityId", "-f", "account=$Account", "-f", "service=$Service", "-f", "contact=$Contact")
    & gh workflow run $workflow --repo $Repo --ref main @inputs
    if ($LASTEXITCODE -ne 0) { throw "Could not dispatch workflow." }
    Start-Sleep -Seconds 4
    $runsJson = & gh run list --repo $Repo --workflow $workflow --event workflow_dispatch --limit 10 --json databaseId,createdAt,status,headBranch
    if ($LASTEXITCODE -ne 0) { throw "Failed to list workflow runs" }
    $recent = @((($runsJson | Out-String) | ConvertFrom-Json) | Where-Object {
        $_.headBranch -eq "main" -and ([DateTimeOffset]::Parse([string]$_.createdAt)) -ge $start.AddSeconds(-10)
    })
    if ($recent.Count -ne 1) { throw "Run identity ambiguous (matches=$($recent.Count)). Use -RunId with GitHub's printed run number." }
    $id = $recent[0].databaseId
}
& gh run watch $id --repo $Repo --exit-status
if ($LASTEXITCODE -ne 0) { throw "GitHub Actions run failed: $id" }
$destination = Join-Path $OutputDir ([string]$id)
New-Item -ItemType Directory -Force -Path $destination | Out-Null
& gh run download $id --repo $Repo --name sfdc-catalog-matches --dir $destination
if ($LASTEXITCODE -ne 0) { throw "Artifact download failed: $id" }
$report = Join-Path $destination "matches.json"
if (-not (Test-Path $report)) { throw "Artifact matches.json missing" }
$data = Get-Content $report -Raw -Encoding UTF8 | ConvertFrom-Json
if ($null -ne $data.catalog_audit) {
    $audit = $data.catalog_audit
    Write-Host "CATALOG AUDIT: rows=$($audit.rows) valid_ids=$($audit.valid_id_rows) distinct=$($audit.distinct_valid_ids) duplicates=$($audit.duplicate_id_rows) missing_or_invalid=$($audit.missing_or_invalid_id_rows)"
    Write-Host "CREATED DATE RANGE (raw text): $($audit.earliest_created_date_as_text) ... $($audit.latest_created_date_as_text)"
}
if ($data.salesforce_save_performed -ne $false) { throw "Unexpected report safety flag" }
if ($OpportunityId) {
    if (@($data.matches).Count -eq 0) {
        Write-Host "NOT_FOUND: Opportunity ID is absent from Catalog; see $report"
        Write-Host "No Salesforce record was saved."
        return
    }
    if (@($data.matches).Count -ne 1) { throw "Ambiguous Opportunity ID matches; refusing auto-link." }
    $returnedId = [string]$data.matches[0].opportunity_id
    if ($returnedId.Length -lt 15 -or $returnedId.Substring(0,15) -cne $OpportunityId.Substring(0,15)) {
        throw "Downloaded match does not correspond to requested Opportunity ID."
    }
}
Write-Host "SUCCESS: $(@($data.matches).Count) candidates. Report: $report"
Write-Host "No Salesforce record was saved."
