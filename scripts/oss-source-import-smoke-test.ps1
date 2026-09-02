param(
    [string]$ComposeProject = "skillhub-oss-import-smoke",
    [string]$PythonImage = "python:3.8-bookworm",
    [int]$WebPort = 58080,
    [int]$SubpathWebPort = 58082,
    [switch]$KeepTemporaryRoot
)

$ErrorActionPreference = "Stop"
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$composeFiles = @(
    "-p", $ComposeProject,
    "--env-file", (Join-Path $repoRoot ".env.release.example"),
    "-f", (Join-Path $repoRoot "compose.release.yml"),
    "-f", (Join-Path $repoRoot "docker-compose.oss-source-import-test.yml")
)
$runId = ([guid]::NewGuid().ToString("N")).Substring(0, 12)
$prefix = "oss-smoke-$runId"
$namespaceSlug = "oss-skillhub-smoke-fixture-$runId"
$repositoryUrl = "https://github.com/skillhub-smoke/fixture-$runId"
$internalRepositoryUrl = "https://gitlab.internal/dev/fixture-$runId.git"
$internalRepositoryCredentialedUrl = "https://smoke-user:smoke-p%40ss@gitlab.internal/dev/fixture-$runId.git"
$actorId = "$prefix-importer"
$ownerId = "$prefix-owner"
$triggerId = "$prefix-trigger"
$triggerTwoId = "$prefix-trigger2"
$serviceId = "svc_$runId"
$serviceCode = "oss-smoke-$runId"
$rawToken = "st_${prefix}_token"
$temporaryRoot = Join-Path ([IO.Path]::GetTempPath()) "skillhub-oss-import-$runId"
$pipeline = Join-Path $temporaryRoot "pipeline"
$checkout = Join-Path $temporaryRoot "checkout"
$reports = Join-Path $temporaryRoot "reports"

function Invoke-Compose {
    param([string[]]$Arguments)
    & docker compose @composeFiles @Arguments
    if ($LASTEXITCODE -ne 0) { throw "docker compose failed: $($Arguments -join ' ')" }
}

function Invoke-Psql {
    param([string]$Sql, [switch]$TuplesOnly)
    $arguments = @("exec", "-T", "postgres", "psql", "-v", "ON_ERROR_STOP=1")
    if ($TuplesOnly) { $arguments += @("-At") }
    $arguments += @("-U", "skillhub", "-d", "skillhub")
    $output = $Sql | & docker compose @composeFiles @arguments
    if ($LASTEXITCODE -ne 0) { throw "PostgreSQL smoke assertion failed" }
    return $output
}

function Assert-Equal {
    param($Actual, $Expected, [string]$Message)
    if ($Actual -ne $Expected) { throw "$Message. Expected '$Expected', got '$Actual'." }
}

function Assert-ComposeContract {
    $configJson = & docker compose @composeFiles config --format json
    if ($LASTEXITCODE -ne 0) { throw "Unable to render the OSS source import Compose contract" }
    $config = $configJson | ConvertFrom-Json

    Assert-Equal $config.services.postgres.environment.POSTGRES_PASSWORD `
        "skillhub_smoke_db" "Smoke PostgreSQL password"
    Assert-Equal $config.services.redis.environment.REDIS_PASSWORD `
        "skillhub_smoke_redis" "Smoke Redis password"
    Assert-Equal $config.services.server.environment.SKILLHUB_DATABASE_URL `
        "postgresql+asyncpg://skillhub:skillhub_smoke_db@postgres:5432/skillhub" `
        "Smoke backend database URL"
    Assert-Equal $config.services.server.environment.SPRING_DATA_REDIS_PASSWORD `
        "skillhub_smoke_redis" "Smoke backend Redis password"
    Assert-Equal ($config.services.postgres.ports | Where-Object target -eq 5432).published `
        "55432" "Smoke PostgreSQL host port"
    Assert-Equal ($config.services.redis.ports | Where-Object target -eq 6379).published `
        "56379" "Smoke Redis host port"
    Assert-Equal ($config.services.server.ports | Where-Object target -eq 8080).published `
        "58081" "Smoke backend host port"
    Assert-Equal ($config.services.web.ports | Where-Object target -eq 80).published `
        "58080" "Smoke root web host port"
    Assert-Equal ($config.services.'web-subpath'.ports | Where-Object target -eq 80).published `
        "58082" "Smoke subpath web host port"
}

function Invoke-Importer {
    param(
        [string]$BaseUrl,
        [string]$TriggerLogin,
        [string]$ReportName,
        [string]$JobId
    )
    $handoffPath = Join-Path $pipeline "pull-code.env"
    $handoffLines = @(
        "SKILLHUB_SOURCE_REPOSITORY_URL=$repositoryUrl",
        "SKILLHUB_SOURCE_REF_TYPE=BRANCH",
        "SKILLHUB_SOURCE_REF=main",
        "SKILLHUB_DEV_GITLAB_REPOSITORY_URL=$internalRepositoryCredentialedUrl",
        "SKILLHUB_DEV_GITLAB_BRANCH=main",
        "SKILLHUB_SOURCE_SCAN_STATUS=PASSED",
        "SKILLHUB_SOURCE_SCAN_ID=scan-$JobId",
        "SKILLHUB_IMPORT_TRIGGER_PROVIDER_CODE=keycloak",
        "SKILLHUB_IMPORT_TRIGGER_LOGIN_NAME=$TriggerLogin"
    )
    [IO.File]::WriteAllLines($handoffPath, $handoffLines, [Text.UTF8Encoding]::new($false))
    $dockerArguments = @(
        "run", "--rm",
        "--network", "${ComposeProject}_default",
        "-v", "${pipeline}:/pipeline:ro",
        "-v", "${checkout}:/dev-source:ro",
        "-v", "${reports}:/reports",
        "-e", "SKILLHUB_BASE_URL=$BaseUrl",
        "-e", "SKILLHUB_SERVICE_TOKEN=$rawToken",
        "-e", "SKILLHUB_NAMESPACE_OWNER_LOGIN_NAME=$ownerId",
        "-e", "SKILLHUB_IMPORT_REPORT_PATH=/reports/$ReportName",
        "-e", "CI_PROJECT_DIR=/pipeline",
        "-e", "CI_JOB_TOKEN=smoke-job-token",
        "-e", "CI_PIPELINE_ID=$runId",
        "-e", "CI_JOB_ID=$JobId",
        "-e", "GIT_CONFIG_COUNT=1",
        "-e", "GIT_CONFIG_KEY_0=url.file:///dev-source.insteadOf",
        "-e", "GIT_CONFIG_VALUE_0=$internalRepositoryUrl",
        "-e", "GIT_ALLOW_PROTOCOL=file",
        $PythonImage,
        "/bin/sh", "/pipeline/deploy/gitlab/oss-source-import.sh"
    )
    $jobLogLines = [Collections.Generic.List[string]]::new()
    & docker @dockerArguments | ForEach-Object {
        $line = [string]$_
        $jobLogLines.Add($line)
        Write-Host $line
    }
    $dockerExitCode = $LASTEXITCODE
    $jobLog = $jobLogLines -join [Environment]::NewLine
    if (
        $jobLog.Contains($rawToken) -or
        $jobLog.Contains("smoke-job-token") -or
        $jobLog.Contains("smoke-user") -or
        $jobLog.Contains("smoke-p%40ss") -or
        $jobLog.Contains("smoke-p@ss")
    ) {
        throw "GitLab job log leaked a credential"
    }
    if ($dockerExitCode -ne 0) {
        Get-Content (Join-Path $reports $ReportName)
        throw "Importer failed for $ReportName"
    }
    foreach ($expectedEvent in @(
        "event=importer_started",
        "event=import_completed",
        "event=report_written",
        "event=importer_finished"
    )) {
        if (-not $jobLog.Contains($expectedEvent)) {
            throw "GitLab job log is missing $expectedEvent"
        }
    }
    $reportContent = Get-Content (Join-Path $reports $ReportName) -Raw
    if (
        $reportContent.Contains("smoke-job-token") -or
        $reportContent.Contains("smoke-user") -or
        $reportContent.Contains("smoke-p%40ss") -or
        $reportContent.Contains("smoke-p@ss")
    ) {
        throw "Internal GitLab credential leaked into $ReportName"
    }
    return $reportContent | ConvertFrom-Json
}

try {
    Assert-ComposeContract
    New-Item -ItemType Directory -Path $checkout, $reports -Force | Out-Null
    Copy-Item -Path (Join-Path $repoRoot "tests\fixtures\oss-source-repository\*") -Destination $checkout -Recurse
    $pipelineShellRoot = New-Item -ItemType Directory -Path (Join-Path $pipeline "deploy\gitlab") -Force
    $pipelineImporterRoot = New-Item -ItemType Directory -Path (Join-Path $pipeline "tools\oss-source-importer") -Force
    $pipelinePackageRoot = New-Item -ItemType Directory `
        -Path (Join-Path $pipelineImporterRoot.FullName "src\skillhub_oss_importer") -Force
    Copy-Item -LiteralPath (Join-Path $repoRoot "deploy\gitlab\oss-source-import.sh") `
        -Destination $pipelineShellRoot.FullName
    Copy-Item -LiteralPath (Join-Path $repoRoot "tools\oss-source-importer\run_import.py") `
        -Destination $pipelineImporterRoot.FullName
    Copy-Item -Path (Join-Path $repoRoot "tools\oss-source-importer\src\skillhub_oss_importer\*.py") `
        -Destination $pipelinePackageRoot.FullName
    & git -C $checkout init -q --initial-branch=main
    & git -C $checkout config user.email smoke@example.test
    & git -C $checkout config user.name "SkillHub Smoke"
    & git -C $checkout add .
    & git -C $checkout commit -qm "Initial OSS fixture"
    $initialCommit = (& git -C $checkout rev-parse HEAD).Trim()

    $sha256 = [System.Security.Cryptography.SHA256]::Create()
    try {
        $tokenHashBytes = $sha256.ComputeHash([System.Text.Encoding]::UTF8.GetBytes($rawToken))
    }
    finally {
        $sha256.Dispose()
    }
    $tokenHash = ([BitConverter]::ToString($tokenHashBytes)).Replace("-", "").ToLowerInvariant()
    Invoke-Psql @"
INSERT INTO user_account (id, display_name, email, status) VALUES
('$actorId','OSS Smoke Importer','$actorId@example.test','ACTIVE'),
('$ownerId','OSS Smoke Owner','$ownerId@example.test','ACTIVE'),
('$triggerId','OSS Smoke Trigger','$triggerId@example.test','ACTIVE'),
('$triggerTwoId','OSS Smoke Trigger Two','$triggerTwoId@example.test','ACTIVE');
INSERT INTO identity_binding (user_id, provider_code, subject, login_name, extra_json) VALUES
('$ownerId','keycloak','$ownerId-subject','$ownerId','{}'::jsonb),
('$triggerId','keycloak','$triggerId-subject','$triggerId','{}'::jsonb),
('$triggerTwoId','keycloak','$triggerTwoId-subject','$triggerTwoId','{}'::jsonb);
INSERT INTO user_role_binding (user_id, role_id)
SELECT '$actorId', id FROM role WHERE code='SUPER_ADMIN';
INSERT INTO service_principal (id, code, display_name, status, created_by_user_id)
VALUES ('$serviceId','$serviceCode','OSS Smoke Importer','ACTIVE','$actorId');
INSERT INTO service_token (
  service_principal_id, name, token_prefix, token_hash, scope_json,
  created_by_user_id, expires_at
)
VALUES (
  '$serviceId','OSS Smoke Importer','st_oss_smoke','$tokenHash','["source:import"]'::jsonb,
  '$actorId',CURRENT_TIMESTAMP + INTERVAL '1 day'
);
"@ | Out-Null

    $first = Invoke-Importer "http://web" $triggerId "first.json" "1"
    Assert-Equal $first.status "SUCCESS" "First import status"
    Assert-Equal $first.commitSha $initialCommit "Cloned Dev GitLab commit"
    Assert-Equal $first.scanStatus "PASSED" "Source scan status"
    Assert-Equal $first.sourceRefType "BRANCH" "Upstream source ref type"
    Assert-Equal $first.sourceRef "main" "Upstream source branch"
    Assert-Equal $first.skills.Count 3 "Discovered skill count"
    Assert-Equal (($first.skills.submission.outcome | Where-Object { $_ -eq "IMPORTED" }).Count) 3 "Imported count"

    $databaseEvidence = "0"
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $databaseEvidence = Invoke-Psql @"
SELECT COUNT(*) FROM namespace n
JOIN skill s ON s.namespace_id=n.id
JOIN skill_version sv ON sv.skill_id=s.id
JOIN review_task rt ON rt.skill_version_id=sv.id
JOIN security_audit sa ON sa.skill_version_id=sv.id
JOIN local_oss_skill_version_source source ON source.skill_version_id=sv.id
JOIN audit_log audit ON audit.target_type='SKILL_VERSION' AND audit.target_id=sv.id
  AND audit.action='SOURCE_IMPORT_SKILL_VERSION'
WHERE n.slug='$namespaceSlug'
  AND s.owner_id='$triggerId'
  AND rt.submitted_by='$triggerId'
  AND audit.actor_user_id IS NULL
  AND audit.actor_service_principal_id='$serviceId'
  AND source.imported_by='$triggerId'
  AND source.imported_by_service_principal_id='$serviceId'
  AND source.repository_revision_sha='$initialCommit';
"@ -TuplesOnly
        if ($databaseEvidence.Trim() -eq "3") { break }
        Start-Sleep -Seconds 1
    }
    Assert-Equal $databaseEvidence.Trim() "3" "Database identity, provenance, review, and scanner evidence"

    $membershipEvidence = (Invoke-Psql @"
SELECT string_agg(nm.user_id || ':' || nm.role, ',' ORDER BY nm.user_id)
FROM namespace_member nm
JOIN namespace n ON n.id=nm.namespace_id
WHERE n.slug='$namespaceSlug' AND nm.role IN ('OWNER','ADMIN');
"@ -TuplesOnly).Trim()
    Assert-Equal $membershipEvidence "$actorId`:ADMIN,$ownerId`:OWNER" "OSS namespace owner and platform admin"
    $triggerMembership = (Invoke-Psql @"
SELECT nm.role FROM namespace_member nm
JOIN namespace n ON n.id=nm.namespace_id
WHERE n.slug='$namespaceSlug' AND nm.user_id='$triggerId';
"@ -TuplesOnly).Trim()
    Assert-Equal $triggerMembership "MEMBER" "Pipeline initiator keeps non-management membership"

    $minioObjects = & docker run --rm --network "${ComposeProject}_default" --entrypoint /bin/sh `
        minio/mc:RELEASE.2025-07-21T05-28-08Z -c `
        "mc alias set smoke http://minio:9000 skillhub-smoke skillhub-smoke-secret >/dev/null && mc ls --recursive smoke/skillhub-oss-import-smoke"
    if ($LASTEXITCODE -ne 0 -or ($minioObjects -join "`n") -notmatch "bundle.zip") {
        throw "MinIO package objects were not found"
    }

    $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
    Invoke-RestMethod -Uri "http://localhost:$WebPort/api/v1/auth/local/login" -Method Post `
        -ContentType "application/json" -Body '{"username":"admin","password":"SmokeAdminPass123!"}' `
        -WebSession $session | Out-Null
    $reviewId = [int](Invoke-Psql @"
SELECT rt.id FROM review_task rt
JOIN local_oss_skill_version_source source ON source.skill_version_id=rt.skill_version_id
JOIN local_oss_skill_source skill_source ON skill_source.id=source.skill_source_id
WHERE skill_source.source_path='skills/alpha' AND rt.status='PENDING'
ORDER BY rt.id DESC LIMIT 1;
"@ -TuplesOnly).Trim()
    $reviewDetail = Invoke-RestMethod -Uri "http://localhost:$WebPort/api/v1/reviews/$reviewId/skill-detail" `
        -WebSession $session -Headers @{"X-Request-Id"="$prefix-review-detail"}
    Assert-Equal $reviewDetail.data.sourceProvenance.repositoryRevisionSha $initialCommit "Review provenance SHA"
    Invoke-RestMethod -Uri "http://localhost:$WebPort/api/v1/reviews/$reviewId/approve" -Method Post `
        -ContentType "application/json" -Body '{"comment":"OSS source smoke approved"}' -WebSession $session `
        -Headers @{"X-Request-Id"="$prefix-approve"} | Out-Null
    $coordinate = $first.skills[0].submission.coordinate.TrimStart("@") -split "/", 2
    $version = $first.skills[0].submission.version
    $publicDetail = Invoke-RestMethod -Uri "http://localhost:$WebPort/api/v1/skills/$($coordinate[0])/$($coordinate[1])/versions/$version"
    Assert-Equal $publicDetail.data.status "PUBLISHED" "Approved version status"
    Assert-Equal $publicDetail.data.sourceProvenance.repositoryRevisionSha $initialCommit "Published provenance SHA"

    $retry = Invoke-Importer "http://web" $triggerId "retry.json" "2"
    Assert-Equal (($retry.skills.validation.outcome | Where-Object { $_ -notlike "SKIPPED_*" }).Count) 0 "Retry outcomes"

    Add-Content -LiteralPath (Join-Path $checkout "skills\alpha\reference.md") `
        -Value "`nChanged only by the source-import smoke."
    & git -C $checkout add skills/alpha/reference.md
    & git -C $checkout commit -qm "Change Alpha only"
    $changedCommit = (& git -C $checkout rev-parse HEAD).Trim()
    $changed = Invoke-Importer "http://web-subpath/skillhub" $triggerTwoId "changed.json" "3"
    Assert-Equal $changed.commitSha $changedCommit "Changed Dev GitLab commit"
    $alpha = $changed.skills | Where-Object sourcePath -eq "skills/alpha"
    Assert-Equal $alpha.submission.outcome "IMPORTED" "Changed Alpha outcome"
    if ($alpha.submission.version -notmatch "^\d{14}$") {
        throw "Changed Alpha version is not a UTC timestamp: $($alpha.submission.version)"
    }
    Assert-Equal $alpha.submission.stableOwner.loginName $null "Stable owner response hides internal identity coordinates"
    Assert-Equal $alpha.submission.reviewSubmitter.loginName $triggerTwoId "Second review submitter"
    Assert-Equal (($changed.skills | Where-Object sourcePath -ne "skills/alpha" | Where-Object { $_.validation.outcome -notlike "SKIPPED_*" }).Count) 0 "Unchanged skill outcomes"

    $health = Invoke-RestMethod -Uri "http://localhost:$SubpathWebPort/skillhub/api/v1/health"
    Assert-Equal $health.data.message "UP" "Subpath proxy health"
    Write-Output "OSS source import smoke passed: run=$runId initial=$initialCommit changed=$changedCommit"
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        if ($KeepTemporaryRoot) {
            Write-Output "OSS source import smoke temporary root retained: $temporaryRoot"
        }
        else {
            $resolvedTemporary = [IO.Path]::GetFullPath($temporaryRoot)
            $systemTemporary = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
            if (-not $resolvedTemporary.StartsWith($systemTemporary, [StringComparison]::OrdinalIgnoreCase)) {
                throw "Refusing to remove non-temporary smoke path: $resolvedTemporary"
            }
            Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
        }
    }
}
