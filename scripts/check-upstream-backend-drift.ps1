param(
    [string]$BaseRef = "upstream/main",
    [string]$HeadRef = "HEAD"
)

$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Set-Location -LiteralPath $Root

function Resolve-GitRef {
    param([string]$Ref)

    $resolved = git rev-parse --verify $Ref 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $resolved) {
        throw "Unable to resolve git ref '$Ref'. Fetch the remote first or pass a valid local ref."
    }

    return $resolved.Trim()
}

function Get-Category {
    param([string]$Path)

    if ($Path -match '^server/.*/src/main/resources/db/migration/' -or $Path -match '^server/.*/db/migration/') {
        return "database-migration-or-schema"
    }
    if ($Path -match '^server/' -and $Path -match '\.(java|kt|xml|properties|yml|yaml)$') {
        return "java-backend-contract-or-behavior"
    }
    if ($Path -match '^server-python/' -or $Path -match '^alembic/' -or $Path -eq 'alembic.ini') {
        return "python-backend-runtime"
    }
    if ($Path -match '^web/' -or $Path -match '^document/' -or $Path -match '^docs/skillhub/' -or $Path -match '^openapi') {
        return "frontend-or-api-client-expectation"
    }
    if ($Path -match '^scanner/' -or $Path -match '^cli/') {
        return "scanner-cli-or-other-runtime"
    }
    if ($Path -match '^\.github/' -or $Path -match '(^|/)Dockerfile' -or $Path -match 'compose|docker-compose|Makefile|pom.xml|package.json|pnpm-lock.yaml|uv.lock|pyproject.toml') {
        return "docs-config-or-ci"
    }
    if ($Path -match '^docs/' -or $Path -match '^README' -or $Path -match '^AGENTS\.md$' -or $Path -match '^CONTRIBUTING\.md$') {
        return "docs-config-or-ci"
    }

    return "scanner-cli-or-other-runtime"
}

function Get-TriageHint {
    param([string]$Category)

    switch ($Category) {
        "java-backend-contract-or-behavior" { return "port-to-python-now if security, auth, API contract, lifecycle, publish/review, or data-integrity behavior changed; otherwise defer-with-reason" }
        "database-migration-or-schema" { return "port-to-python-now before launch through Python-owned schema migration work" }
        "frontend-or-api-client-expectation" { return "port-to-python-now when API contract or proxy expectations changed; accept-non-backend for docs/UI-only changes" }
        "python-backend-runtime" { return "review directly in Python; keep explicit tests and result note" }
        "docs-config-or-ci" { return "accept-non-backend unless it changes runtime, deployment, or CI gates for Python" }
        default { return "defer-with-reason or accept-non-backend unless it affects Python runtime behavior" }
    }
}

$baseSha = Resolve-GitRef -Ref $BaseRef
$headSha = Resolve-GitRef -Ref $HeadRef
$changes = git diff --name-status "$BaseRef...$HeadRef"
if ($LASTEXITCODE -ne 0) {
    throw "git diff failed for '$BaseRef...$HeadRef'"
}

$items = foreach ($line in $changes) {
    if (-not $line.Trim()) {
        continue
    }

    $parts = $line -split "`t"
    $status = $parts[0]
    $path = if ($status -match '^R|^C') { $parts[-1] } else { $parts[1] }
    $category = Get-Category -Path $path

    [pscustomobject]@{
        Status = $status
        Path = $path
        Category = $category
        Triage = Get-TriageHint -Category $category
    }
}

Write-Output "# Upstream Backend Drift Report"
Write-Output ""
Write-Output "BaseRef: $BaseRef ($baseSha)"
Write-Output "HeadRef: $HeadRef ($headSha)"
Write-Output "ComparedWith: git diff --name-status $BaseRef...$HeadRef"
Write-Output ""

if (-not $items) {
    Write-Output "No changed files."
    exit 0
}

$orderedCategories = @(
    "java-backend-contract-or-behavior",
    "database-migration-or-schema",
    "frontend-or-api-client-expectation",
    "python-backend-runtime",
    "docs-config-or-ci",
    "scanner-cli-or-other-runtime"
)

Write-Output "## Summary"
foreach ($category in $orderedCategories) {
    $count = @($items | Where-Object { $_.Category -eq $category }).Count
    Write-Output "- $category`: $count"
}
Write-Output ""

foreach ($category in $orderedCategories) {
    $categoryItems = @($items | Where-Object { $_.Category -eq $category } | Sort-Object Path)
    if ($categoryItems.Count -eq 0) {
        continue
    }

    Write-Output "## $category"
    Write-Output ""
    Write-Output "Triage: $($categoryItems[0].Triage)"
    Write-Output ""
    foreach ($item in $categoryItems) {
        Write-Output "- $($item.Status) $($item.Path)"
    }
    Write-Output ""
}
