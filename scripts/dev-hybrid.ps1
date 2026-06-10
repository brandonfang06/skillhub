param(
    [ValidateSet('up', 'down', 'status', 'verify-labels-smoke', 'verify-files-smoke', 'verify-detail-smoke', 'verify-search-smoke', 'verify-clawhub-search-smoke', 'verify-clawhub-resolve-smoke', 'verify-clawhub-skill-smoke', 'verify-clawhub-list-smoke', 'verify-auth-me-smoke', 'verify-auth-detail-smoke', 'verify-owner-preview-detail-smoke', 'verify-owner-preview-version-smoke', 'verify-owner-preview-files-smoke', 'verify-file-content-smoke', 'verify-download-smoke', 'verify-owner-preview-resolve-smoke', 'verify-owner-preview-compare-smoke', 'verify-publish-foundation-smoke', 'verify-publish-dry-run-smoke', 'verify-publish-storage-foundation-smoke', 'verify-publish-db-foundation-smoke', 'verify-publish-side-effects-foundation-smoke', 'verify-publish-replacement-foundation-smoke', 'verify-publish-transaction-split-smoke', 'verify-publish-orchestration-foundation-smoke', 'verify-publish-http-validate-smoke', 'verify-publish-cli-write-direct-smoke', 'verify-publish-scanner-handoff-smoke', 'verify-publish-cli-replacement-lookup-smoke', 'verify-publish-pending-auto-withdraw-smoke', 'verify-publish-storage-failure-cleanup-smoke', 'verify-cli-publish-write-ownership-smoke', 'verify-portal-publish-write-ownership-smoke', 'verify-root-legacy-publish-write-ownership-smoke', 'verify-publish-scanner-result-processing-smoke', 'verify-publish-scan-task-worker-boundary-smoke', 'verify-publish-scan-consumer-runtime-smoke', 'verify-publish-scanner-http-client-smoke', 'verify-publish-scan-daemon-supervisor-smoke', 'verify-review-approve-smoke', 'verify-review-reject-withdraw-smoke', 'verify-review-submit-smoke', 'verify-review-list-smoke', 'verify-review-detail-smoke', 'verify-review-skill-detail-smoke', 'verify-review-file-smoke', 'verify-review-download-smoke', 'verify-promotion-read-smoke', 'verify-promotion-submit-reject-smoke', 'verify-promotion-approve-smoke', 'verify-skill-lifecycle-archive-smoke', 'verify-skill-version-delete-smoke', 'verify-skill-version-withdraw-review-smoke', 'verify-skill-confirm-publish-smoke', 'verify-skill-submit-review-smoke', 'verify-skill-rerelease-smoke', 'verify-admin-skill-hide-unhide-smoke', 'verify-admin-version-yank-smoke', 'verify-skill-star-smoke', 'verify-skill-subscription-smoke', 'verify-skill-rating-smoke', 'verify-my-social-lists-smoke', 'verify-notification-read-smoke', 'verify-notification-preferences-smoke', 'verify-my-skills-smoke', 'verify-namespace-read-smoke', 'verify-namespace-member-read-smoke', 'verify-namespace-member-mutation-smoke', 'verify-namespace-transfer-ownership-smoke', 'verify-namespace-profile-lifecycle-smoke', 'verify-admin-label-definition-smoke', 'verify-admin-user-management-smoke', 'verify-governance-workbench-smoke', 'e2e-smoke', 'e2e')]
    [string]$Action = 'up'
)

$ErrorActionPreference = 'Stop'

$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$DevDir = Join-Path $Root '.dev'
$JavaPidFile = Join-Path $DevDir 'server.pid'
$PythonPidFile = Join-Path $DevDir 'python.pid'
$WebPidFile = Join-Path $DevDir 'web.pid'
$JavaLog = Join-Path $DevDir 'server.log'
$PythonLog = Join-Path $DevDir 'python.log'
$WebLog = Join-Path $DevDir 'web.log'
$PlaywrightBrowsersPath = Join-Path $DevDir 'ms-playwright'
$JavaStoragePath = Join-Path $DevDir 'java-storage'

$WebUrl = 'http://localhost:3000'
$JavaUrl = 'http://localhost:8080'
$PythonUrl = 'http://localhost:8081'
$ScannerUrl = 'http://localhost:8000'

function Ensure-DevDir {
    New-Item -ItemType Directory -Force -Path $DevDir | Out-Null
}

function Join-CmdArguments {
    param([string[]]$Arguments)

    $escapedArgs = foreach ($argument in $Arguments) {
        $escaped = $argument.Replace('"', '\"')
        if ($escaped -match '[\s&()^|<>"]') {
            '"{0}"' -f $escaped
        } else {
            $escaped
        }
    }

    return ($escapedArgs -join ' ')
}

function Test-ProcessRunning {
    param([string]$PidFile)

    if (-not (Test-Path -LiteralPath $PidFile)) {
        return $false
    }

    $rawPid = (Get-Content -LiteralPath $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1)
    if (-not $rawPid -or -not ($rawPid -match '^\d+$')) {
        Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return $false
    }

    try {
        Get-Process -Id ([int]$rawPid) -ErrorAction Stop | Out-Null
        return $true
    } catch {
        Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return $false
    }
}

function Stop-ManagedProcess {
    param([string]$PidFile)

    if (-not (Test-ProcessRunning -PidFile $PidFile)) {
        Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
        return
    }

    $processId = [int](Get-Content -LiteralPath $PidFile | Select-Object -First 1)
    Stop-ProcessTree -ProcessId $processId
    Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
}

function Stop-ProcessTree {
    param([int]$ProcessId)

    $taskkill = Get-Command taskkill.exe -ErrorAction SilentlyContinue
    if ($taskkill) {
        & cmd.exe /d /c "taskkill.exe /F /T /PID $ProcessId >NUL 2>NUL"
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "taskkill could not stop PID ${ProcessId}."
        }
    }

    if (Get-Process -Id $ProcessId -ErrorAction SilentlyContinue) {
        Stop-Process -Id $ProcessId -Force -ErrorAction SilentlyContinue
    }
}

function Stop-ProcessOnPort {
    param([int]$Port)

    $listeners = netstat -ano |
        Select-String ":$Port\s" |
        ForEach-Object { ($_ -split '\s+')[-1] } |
        Where-Object { $_ -match '^\d+$' } |
        Sort-Object -Unique

    foreach ($listenerPid in $listeners) {
        $processId = [int]$listenerPid
        if ($processId -le 0 -or $processId -eq $PID) {
            continue
        }

        Stop-ProcessTree -ProcessId $processId
        if (Get-Process -Id $processId -ErrorAction SilentlyContinue) {
            Write-Warning "Could not stop process $processId on port $Port. If it was started from an elevated session, close it manually or reboot once."
        }
    }
}

function Start-ManagedProcess {
    param(
        [string]$Name,
        [string]$PidFile,
        [string]$LogFile,
        [string]$WorkingDirectory,
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    Ensure-DevDir
    if (Test-ProcessRunning -PidFile $PidFile) {
        $existingPid = Get-Content -LiteralPath $PidFile | Select-Object -First 1
        Write-Host "$Name already running with PID $existingPid"
        return
    }

    New-Item -ItemType File -Force -Path $LogFile | Out-Null
    $errorLogFile = "$LogFile.err"
    New-Item -ItemType File -Force -Path $errorLogFile | Out-Null
    $arguments = Join-CmdArguments -Arguments $ArgumentList
    $command = 'cd /d "{0}" && "{1}" {2} 1> "{3}" 2> "{4}"' -f $WorkingDirectory, $FilePath, $arguments, $LogFile, $errorLogFile
    $process = Start-Process `
        -FilePath 'cmd.exe' `
        -ArgumentList @('/d', '/c', $command) `
        -WindowStyle Hidden `
        -PassThru

    Set-Content -LiteralPath $PidFile -Value $process.Id
    Write-Host "Started $Name with PID $($process.Id)"
}

function Wait-ForUrl {
    param(
        [string]$Name,
        [string]$Url,
        [int]$Attempts = 60
    )

    Write-Host "Waiting for $Name on $Url ..."
    for ($i = 1; $i -le $Attempts; $i++) {
        try {
            Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 3 | Out-Null
            Write-Host "$Name ready."
            return
        } catch {
            Start-Sleep -Seconds 2
        }
    }

    throw "$Name did not become ready at $Url"
}

function Resolve-GitShell {
    $candidate = 'C:\Program Files\Git\bin\sh.exe'
    if (Test-Path -LiteralPath $candidate) {
        return $candidate
    }

    $command = Get-Command sh -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    throw 'Git sh.exe is required to start the Java backend on Windows.'
}

function Resolve-JavaHome {
    if ($env:JAVA_HOME -and (Test-Path -LiteralPath (Join-Path $env:JAVA_HOME 'bin\java.exe'))) {
        return $env:JAVA_HOME
    }

    $candidates = @(
        'C:\Program Files\Eclipse Adoptium',
        'C:\Program Files\Microsoft',
        'C:\Program Files\Java',
        'C:\Program Files\JetBrains\PyCharm 2025.2.1.1\jbr',
        'C:\Program Files\JetBrains\PyCharm Community Edition 2023.3.4\jbr'
    )

    foreach ($candidate in $candidates) {
        if (-not (Test-Path -LiteralPath $candidate)) {
            continue
        }

        if (Test-Path -LiteralPath (Join-Path $candidate 'bin\java.exe')) {
            return $candidate
        }

        $javaHome = Get-ChildItem -LiteralPath $candidate -Directory -ErrorAction SilentlyContinue |
            Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'bin\java.exe') } |
            Sort-Object Name -Descending |
            Select-Object -First 1
        if ($javaHome) {
            return $javaHome.FullName
        }
    }

    throw 'Java 21 JDK is required to start the Java backend. Install it with: winget install --id EclipseAdoptium.Temurin.21.JDK -e'
}

function Test-CommandAvailable {
    param([string]$Name)

    return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

function Invoke-NativeCommand {
    param(
        [string]$FilePath,
        [string[]]$Arguments
    )

    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed with exit code ${LASTEXITCODE}: $FilePath $($Arguments -join ' ')"
    }
}

function Invoke-DockerComposeRequired {
    param([string[]]$Arguments)

    if (-not (Test-CommandAvailable -Name 'docker')) {
        throw 'Docker CLI is required for hybrid local dependencies, but docker was not found in PATH.'
    }

    Invoke-NativeCommand -FilePath 'docker' -Arguments $Arguments
}

function Invoke-WebDeps {
    $webDir = Join-Path $Root 'web'
    $corepackHome = 'C:\tmp\corepack'
    $pnpmStore = Join-Path $DevDir 'pnpm-store'
    New-Item -ItemType Directory -Force -Path $corepackHome | Out-Null
    New-Item -ItemType Directory -Force -Path $pnpmStore | Out-Null
    New-Item -ItemType Directory -Force -Path $PlaywrightBrowsersPath | Out-Null
    $env:COREPACK_HOME = $corepackHome
    $env:CI = 'true'
    $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
    Push-Location $webDir
    try {
        Invoke-NativeCommand -FilePath 'corepack' -Arguments @(
            'pnpm',
            'install',
            '--frozen-lockfile',
            '--config.confirmModulesPurge=false',
            '--store-dir',
            $pnpmStore
        )
    } finally {
        Pop-Location
    }
}

function Install-PlaywrightBrowsers {
    Push-Location (Join-Path $Root 'web')
    try {
        $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('install', 'chromium')
    } finally {
        Pop-Location
    }
}

function Start-Hybrid {
    Ensure-DevDir

    Invoke-DockerComposeRequired -Arguments @('compose', '-p', 'skillhub', 'up', '-d', '--wait', '--remove-orphans')
    Invoke-WebDeps

    $shell = Resolve-GitShell
    $javaHome = Resolve-JavaHome
    $env:JAVA_HOME = $javaHome
    $env:JAVA_BIN = Join-Path $javaHome 'bin\java.exe'
    $env:Path = (Join-Path $javaHome 'bin') + ';' + $env:Path
    $mavenRepo = Join-Path $DevDir 'm2-repository'
    New-Item -ItemType Directory -Force -Path $mavenRepo | Out-Null
    New-Item -ItemType Directory -Force -Path $JavaStoragePath | Out-Null
    $env:MAVEN_OPTS = "-Dmaven.repo.local=$mavenRepo"
    $env:STORAGE_BASE_PATH = $JavaStoragePath
    $serverDir = Join-Path $Root 'server'
    Start-ManagedProcess `
        -Name 'Java backend' `
        -PidFile $JavaPidFile `
        -LogFile $JavaLog `
        -WorkingDirectory $serverDir `
        -FilePath $shell `
        -ArgumentList @('-lc', './scripts/run-dev-app.sh')

    $pythonCommand = '$env:UV_CACHE_DIR = ''.uv-cache''; uv run uvicorn app.main:app --host 0.0.0.0 --port 8081 --reload'
    Start-ManagedProcess `
        -Name 'Python backend' `
        -PidFile $PythonPidFile `
        -LogFile $PythonLog `
        -WorkingDirectory (Join-Path $Root 'server-python') `
        -FilePath 'powershell.exe' `
        -ArgumentList @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', $pythonCommand)

    $vitePath = Join-Path $Root 'web\node_modules\.bin\vite.CMD'
    Start-ManagedProcess `
        -Name 'Vite frontend' `
        -PidFile $WebPidFile `
        -LogFile $WebLog `
        -WorkingDirectory (Join-Path $Root 'web') `
        -FilePath $vitePath `
        -ArgumentList @('--host', '0.0.0.0', '--strictPort')

    Wait-ForUrl -Name 'Java backend' -Url "$JavaUrl/actuator/health" -Attempts 60
    Wait-ForUrl -Name 'Python backend' -Url "$PythonUrl/api/v1/health" -Attempts 30
    Wait-ForUrl -Name 'Scanner' -Url "$ScannerUrl/health" -Attempts 30
    Wait-ForUrl -Name 'Vite frontend' -Url $WebUrl -Attempts 60
    Wait-ForUrl -Name 'Vite proxy to Python health route' -Url "$WebUrl/api/v1/health" -Attempts 15

    Write-Host 'Hybrid local environment is ready:'
    Write-Host "  Web UI:         $WebUrl"
    Write-Host "  Java Backend:   $JavaUrl"
    Write-Host "  Python Backend: $PythonUrl"
    Write-Host "  Scanner:        $ScannerUrl"
    Write-Host 'Logs:'
    Write-Host "  Java Backend:   $JavaLog"
    Write-Host "  Python Backend: $PythonLog"
    Write-Host "  Frontend:       $WebLog"
}

function Stop-Hybrid {
    Stop-ManagedProcess -PidFile $JavaPidFile
    Stop-ManagedProcess -PidFile $PythonPidFile
    Stop-ManagedProcess -PidFile $WebPidFile
    Stop-ProcessOnPort -Port 8080
    Stop-ProcessOnPort -Port 8081
    Stop-ProcessOnPort -Port 3000
    if (Test-CommandAvailable -Name 'docker') {
        docker compose -p skillhub down --remove-orphans
    } else {
        Write-Warning 'Docker CLI not available; dependency services were not stopped by this script.'
    }
}

function Show-Status {
    if (Test-CommandAvailable -Name 'docker') {
        docker compose -p skillhub ps
    } else {
        Write-Warning 'Docker CLI not available; dependency service status unavailable.'
    }
    Write-Host ''
    Write-Host "Java backend:   $(if (Test-ProcessRunning -PidFile $JavaPidFile) { 'running' } else { 'stopped' })"
    Write-Host "Python backend: $(if (Test-ProcessRunning -PidFile $PythonPidFile) { 'running' } else { 'stopped' })"
    Write-Host "Vite frontend:  $(if (Test-ProcessRunning -PidFile $WebPidFile) { 'running' } else { 'stopped' })"
}

function Invoke-HybridE2E {
    param([string]$Config)

    Start-Hybrid
    Install-PlaywrightBrowsers
    Push-Location (Join-Path $Root 'web')
    try {
        $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', $Config)
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableContractJson {
    param([object]$Response)

    return ($Response | Select-Object code,msg,data | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableAuthMeContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            userId = $Response.data.userId
            displayName = $Response.data.displayName
            email = $Response.data.email
            avatarUrl = $Response.data.avatarUrl
            oauthProvider = $Response.data.oauthProvider
            platformRoles = @($Response.data.platformRoles | Sort-Object)
        }
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableDetailContractJson {
    param([object]$Response)

    $json = ($Response | Select-Object code,msg,data | ConvertTo-Json -Depth 50 -Compress)
    $json = [regex]::Replace($json, '("ratingAvg":-?\d+\.\d*?[1-9])0+(?=[,}])', '$1')
    return [regex]::Replace($json, '("ratingAvg":-?\d+)\.0+(?=[,}])', '$1')
}

function ConvertTo-StableSearchContractJson {
    param([object]$Response)

    return ConvertTo-StableDetailContractJson -Response $Response
}

function ConvertTo-StablePlainJson {
    param([object]$Response)

    return ($Response | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-PostgresSql {
    param([string]$Sql)

    Invoke-NativeCommand -FilePath 'docker' -Arguments @(
        'compose',
        '-p',
        'skillhub',
        'exec',
        '-T',
        'postgres',
        'psql',
        '-U',
        'skillhub',
        '-d',
        'skillhub',
        '-v',
        'ON_ERROR_STOP=1',
        '-c',
        $Sql
    )
}

function Invoke-PostgresScalar {
    param([string]$Sql)

    $output = & docker compose -p skillhub exec -T postgres psql -U skillhub -d skillhub -t -A -v ON_ERROR_STOP=1 -c $Sql
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres scalar query failed with exit code ${LASTEXITCODE}: $Sql"
    }
    return ($output | Where-Object { $_ -and $_.Trim() -ne '' } | Select-Object -First 1).Trim()
}

function Ensure-FilesContractFixture {
    $objects = @{
        'fixtures/files/1.0.0/SKILL.md' = '# Stable fixture'
        'fixtures/files/1.0.0/src/main.py' = 'print("stable fixture")'
        'fixtures/files/1.2.0/README.md' = '# Latest fixture'
        'fixtures/files/1.2.0/SKILL.md' = '# Latest skill fixture'
    }

    foreach ($entry in $objects.GetEnumerator()) {
        $relativePath = $entry.Key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        Set-Content -LiteralPath $targetPath -Value $entry.Value
    }

    $sql = @'
DO $$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-fixture-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
    old_version_id BIGINT;
    latest_version_row_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Fixture User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        download_count,
        star_count,
        rating_avg,
        rating_count,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        ns_id,
        'codex-files-fixture-20260607224000',
        'Codex files fixture',
        'Fixture for file metadata contract comparison',
        fixture_user_id,
        'PUBLIC',
        'ACTIVE',
        0,
        0,
        0.00,
        0,
        fixture_user_id,
        fixture_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = fixture_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        fixture_skill_id,
        '1.0.0',
        'PUBLISHED',
        'stable fixture',
        jsonb_build_object('name', 'files-fixture', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/main.py')),
        2,
        456,
        '2026-06-07T09:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T09:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO old_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        fixture_skill_id,
        '1.2.0',
        'PUBLISHED',
        'latest fixture',
        jsonb_build_object('name', 'files-fixture', 'version', '1.2.0'),
        jsonb_build_array(jsonb_build_object('path', 'README.md'), jsonb_build_object('path', 'SKILL.md')),
        2,
        579,
        '2026-06-07T10:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T10:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO latest_version_row_id;

    UPDATE skill
    SET latest_version_id = latest_version_row_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (old_version_id, 'SKILL.md', 123, 'text/markdown', repeat('a', 64), 'fixtures/files/1.0.0/SKILL.md'),
        (old_version_id, 'src/main.py', 333, 'text/x-python', repeat('b', 64), 'fixtures/files/1.0.0/src/main.py'),
        (latest_version_row_id, 'README.md', 111, 'text/markdown', repeat('c', 64), 'fixtures/files/1.2.0/README.md'),
        (latest_version_row_id, 'SKILL.md', 468, 'text/markdown', repeat('d', 64), 'fixtures/files/1.2.0/SKILL.md')
    ON CONFLICT (version_id, file_path) DO UPDATE
        SET file_size = EXCLUDED.file_size,
            content_type = EXCLUDED.content_type,
            sha256 = EXCLUDED.sha256,
            storage_key = EXCLUDED.storage_key;

    INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
    VALUES (fixture_skill_id, 'stable', old_version_id, fixture_user_id)
    ON CONFLICT (skill_id, tag_name) DO UPDATE
        SET version_id = EXCLUDED.version_id,
            updated_at = CURRENT_TIMESTAMP;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Ensure-DetailContractFixture {
    $sql = @'
DO $$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-detail-owner';
    ns_id BIGINT;
    archived_ns_id BIGINT;
    fixture_skill_id BIGINT;
    hidden_skill_id BIGINT;
    no_latest_skill_id BIGINT;
    archived_skill_id BIGINT;
    old_version_id BIGINT;
    latest_version_row_id BIGINT;
    draft_version_id BIGINT;
    hidden_version_id BIGINT;
    archived_version_id BIGINT;
    label_row_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Detail Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-archived-detail', 'Codex Archived Detail', 'TEAM', 'ARCHIVED', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ARCHIVED',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO archived_ns_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        download_count,
        star_count,
        subscription_count,
        rating_avg,
        rating_count,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        ns_id,
        'codex-detail-fixture-20260607230000',
        'Codex Detail Fixture',
        'Fixture for public skill detail contract comparison',
        fixture_user_id,
        'PUBLIC',
        'ACTIVE',
        7,
        3,
        2,
        4.50,
        4,
        fixture_user_id,
        fixture_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            download_count = 7,
            star_count = 3,
            subscription_count = 2,
            rating_avg = 4.50,
            rating_count = 4,
            updated_by = fixture_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        ns_id,
        'codex-detail-hidden-20260607230000',
        'Codex Hidden Detail Fixture',
        'Hidden fixture',
        fixture_user_id,
        'PUBLIC',
        'ACTIVE',
        fixture_user_id,
        fixture_user_id,
        TRUE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = TRUE,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO hidden_skill_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        latest_version_id,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        ns_id,
        'codex-detail-no-latest-20260607230000',
        'Codex No Latest Detail Fixture',
        'No latest fixture',
        fixture_user_id,
        'PUBLIC',
        'ACTIVE',
        NULL,
        fixture_user_id,
        fixture_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET visibility = 'PUBLIC',
            status = 'ACTIVE',
            latest_version_id = NULL,
            hidden = FALSE,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO no_latest_skill_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        archived_ns_id,
        'codex-detail-archived-20260607230000',
        'Codex Archived Detail Fixture',
        'Archived namespace fixture',
        fixture_user_id,
        'PUBLIC',
        'ACTIVE',
        fixture_user_id,
        fixture_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO archived_skill_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        fixture_skill_id,
        '1.0.0',
        'PUBLISHED',
        'older public detail fixture',
        jsonb_build_object('name', 'detail-fixture', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1,
        123,
        '2026-06-07T09:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T09:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO old_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        fixture_skill_id,
        '1.2.0',
        'PUBLISHED',
        'latest public detail fixture',
        jsonb_build_object('name', 'detail-fixture', 'version', '1.2.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1,
        456,
        '2026-06-07T10:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T10:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO latest_version_row_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        fixture_skill_id,
        '2.0.0-draft',
        'DRAFT',
        'anonymous users must not see this preview',
        jsonb_build_object('name', 'detail-fixture', 'version', '2.0.0-draft'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1,
        789,
        fixture_user_id,
        '2026-06-07T11:00:00Z'::timestamptz,
        FALSE,
        FALSE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'DRAFT',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            created_at = EXCLUDED.created_at,
            bundle_ready = FALSE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO draft_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        hidden_skill_id,
        '1.0.0',
        'PUBLISHED',
        0,
        0,
        '2026-06-07T10:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T10:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO hidden_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES (
        archived_skill_id,
        '1.0.0',
        'PUBLISHED',
        0,
        0,
        '2026-06-07T10:00:00Z'::timestamptz,
        fixture_user_id,
        '2026-06-07T10:00:00Z'::timestamptz,
        TRUE,
        TRUE,
        'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO archived_version_id;

    UPDATE skill
    SET latest_version_id = latest_version_row_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    UPDATE skill
    SET latest_version_id = hidden_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = hidden_skill_id;

    UPDATE skill
    SET latest_version_id = archived_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = archived_skill_id;

    INSERT INTO label_definition (slug, type, visible_in_filter, sort_order, created_by)
    VALUES ('codex-detail-featured', 'RECOMMENDED', TRUE, 10, fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET type = 'RECOMMENDED',
            visible_in_filter = TRUE,
            sort_order = 10,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO label_row_id;

    INSERT INTO label_translation (label_id, locale, display_name)
    VALUES (label_row_id, 'en', 'Codex Detail Featured')
    ON CONFLICT (label_id, locale) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill_label (skill_id, label_id, created_by)
    VALUES (fixture_skill_id, label_row_id, fixture_user_id)
    ON CONFLICT (skill_id, label_id) DO NOTHING;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Ensure-SearchContractFixture {
    $sql = @'
DO $$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-search-owner';
    ns_id BIGINT;
    archived_ns_id BIGINT;
    alpha_skill_id BIGINT;
    beta_skill_id BIGINT;
    gamma_skill_id BIGINT;
    hidden_skill_id BIGINT;
    archived_skill_id BIGINT;
    alpha_version_id BIGINT;
    beta_version_id BIGINT;
    gamma_version_id BIGINT;
    hidden_version_id BIGINT;
    archived_version_id BIGINT;
    label_row_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Search Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-archived-search', 'Codex Archived Search', 'TEAM', 'ARCHIVED', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ARCHIVED',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO archived_ns_id;

    INSERT INTO label_definition (slug, type, visible_in_filter, sort_order, created_by)
    VALUES ('codex-search-featured', 'RECOMMENDED', TRUE, 20, fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET type = 'RECOMMENDED',
            visible_in_filter = TRUE,
            sort_order = 20,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO label_row_id;

    INSERT INTO label_translation (label_id, locale, display_name)
    VALUES (label_row_id, 'en', 'Codex Search Featured')
    ON CONFLICT (label_id, locale) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by,
        hidden, created_at, updated_at
    )
    VALUES (
        ns_id, 'codex-search-alpha-20260607233000', 'Codex Search Alpha Fixture',
        'codex-search-fixture alpha summary codex-search-alpha-unique',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 11, 4, 4.75, 8,
        fixture_user_id, fixture_user_id, FALSE,
        '2026-06-07T08:00:00Z'::timestamptz, '2026-06-07T11:00:00Z'::timestamptz
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            download_count = 11,
            star_count = 4,
            rating_avg = 4.75,
            rating_count = 8,
            hidden = FALSE,
            updated_at = '2026-06-07T11:00:00Z'::timestamptz
    RETURNING id INTO alpha_skill_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by,
        hidden, created_at, updated_at
    )
    VALUES (
        ns_id, 'codex-search-beta-20260607233000', 'Codex Search Beta Fixture',
        'codex-search-fixture beta summary',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 7, 2, 4.25, 6,
        fixture_user_id, fixture_user_id, FALSE,
        '2026-06-07T08:00:00Z'::timestamptz, '2026-06-07T10:00:00Z'::timestamptz
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            download_count = 7,
            star_count = 2,
            rating_avg = 4.25,
            rating_count = 6,
            hidden = FALSE,
            updated_at = '2026-06-07T10:00:00Z'::timestamptz
    RETURNING id INTO beta_skill_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by,
        hidden, created_at, updated_at
    )
    VALUES (
        ns_id, 'codex-search-gamma-20260607233000', 'Codex Search Gamma Fixture',
        'codex-search-fixture gamma summary',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 3, 1, 4.95, 3,
        fixture_user_id, fixture_user_id, FALSE,
        '2026-06-07T08:00:00Z'::timestamptz, '2026-06-07T09:00:00Z'::timestamptz
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            download_count = 3,
            star_count = 1,
            rating_avg = 4.95,
            rating_count = 3,
            hidden = FALSE,
            updated_at = '2026-06-07T09:00:00Z'::timestamptz
    RETURNING id INTO gamma_skill_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        created_by, updated_by, hidden
    )
    VALUES (
        ns_id, 'codex-search-hidden-20260607233000', 'Codex Search Hidden Fixture',
        'codex-search-fixture hidden summary',
        fixture_user_id, 'PUBLIC', 'ACTIVE',
        fixture_user_id, fixture_user_id, TRUE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = TRUE,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO hidden_skill_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        created_by, updated_by, hidden
    )
    VALUES (
        archived_ns_id, 'codex-search-archived-20260607233000', 'Codex Search Archived Fixture',
        'codex-search-fixture archived summary',
        fixture_user_id, 'PUBLIC', 'ACTIVE',
        fixture_user_id, fixture_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO archived_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at,
        bundle_ready, download_ready, requested_visibility
    )
    VALUES
        (alpha_skill_id, '1.0.0', 'PUBLISHED', 'alpha search fixture',
         jsonb_build_object('name', 'search-alpha', 'version', '1.0.0'),
         jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
         1, 100, '2026-06-07T11:00:00Z'::timestamptz, fixture_user_id,
         '2026-06-07T11:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'),
        (beta_skill_id, '1.0.0', 'PUBLISHED', 'beta search fixture',
         jsonb_build_object('name', 'search-beta', 'version', '1.0.0'),
         jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
         1, 100, '2026-06-07T10:00:00Z'::timestamptz, fixture_user_id,
         '2026-06-07T10:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'),
        (gamma_skill_id, '1.0.0', 'PUBLISHED', 'gamma search fixture',
         jsonb_build_object('name', 'search-gamma', 'version', '1.0.0'),
         jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
         1, 100, '2026-06-07T09:00:00Z'::timestamptz, fixture_user_id,
         '2026-06-07T09:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'),
        (hidden_skill_id, '1.0.0', 'PUBLISHED', 'hidden search fixture',
         jsonb_build_object('name', 'search-hidden', 'version', '1.0.0'),
         jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
         1, 100, '2026-06-07T09:00:00Z'::timestamptz, fixture_user_id,
         '2026-06-07T09:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'),
        (archived_skill_id, '1.0.0', 'PUBLISHED', 'archived search fixture',
         jsonb_build_object('name', 'search-archived', 'version', '1.0.0'),
         jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
         1, 100, '2026-06-07T09:00:00Z'::timestamptz, fixture_user_id,
         '2026-06-07T09:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC')
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC';

    SELECT id INTO alpha_version_id FROM skill_version WHERE skill_id = alpha_skill_id AND version = '1.0.0';
    SELECT id INTO beta_version_id FROM skill_version WHERE skill_id = beta_skill_id AND version = '1.0.0';
    SELECT id INTO gamma_version_id FROM skill_version WHERE skill_id = gamma_skill_id AND version = '1.0.0';
    SELECT id INTO hidden_version_id FROM skill_version WHERE skill_id = hidden_skill_id AND version = '1.0.0';
    SELECT id INTO archived_version_id FROM skill_version WHERE skill_id = archived_skill_id AND version = '1.0.0';

    UPDATE skill SET latest_version_id = alpha_version_id WHERE id = alpha_skill_id;
    UPDATE skill SET latest_version_id = beta_version_id WHERE id = beta_skill_id;
    UPDATE skill SET latest_version_id = gamma_version_id WHERE id = gamma_skill_id;
    UPDATE skill SET latest_version_id = hidden_version_id WHERE id = hidden_skill_id;
    UPDATE skill SET latest_version_id = archived_version_id WHERE id = archived_skill_id;

    INSERT INTO skill_label (skill_id, label_id, created_by)
    VALUES
        (alpha_skill_id, label_row_id, fixture_user_id),
        (beta_skill_id, label_row_id, fixture_user_id)
    ON CONFLICT (skill_id, label_id) DO NOTHING;

    INSERT INTO skill_search_document (
        skill_id, namespace_id, namespace_slug, owner_id, title, summary, keywords,
        search_text, visibility, status, updated_at
    )
    VALUES
        (alpha_skill_id, ns_id, 'global', fixture_user_id, 'Codex Search Alpha Fixture',
         'codex-search-fixture alpha summary codex-search-alpha-unique',
         'codex-search-featured alpha', 'codex-search-fixture codex-search-alpha-unique',
         'PUBLIC', 'ACTIVE', '2026-06-07T11:00:00Z'::timestamptz),
        (beta_skill_id, ns_id, 'global', fixture_user_id, 'Codex Search Beta Fixture',
         'codex-search-fixture beta summary',
         'codex-search-featured beta', 'codex-search-fixture',
         'PUBLIC', 'ACTIVE', '2026-06-07T10:00:00Z'::timestamptz),
        (gamma_skill_id, ns_id, 'global', fixture_user_id, 'Codex Search Gamma Fixture',
         'codex-search-fixture gamma summary',
         'gamma', 'codex-search-fixture',
         'PUBLIC', 'ACTIVE', '2026-06-07T09:00:00Z'::timestamptz),
        (hidden_skill_id, ns_id, 'global', fixture_user_id, 'Codex Search Hidden Fixture',
         'codex-search-fixture hidden summary',
         'hidden', 'codex-search-fixture',
         'PUBLIC', 'ACTIVE', '2026-06-07T09:00:00Z'::timestamptz),
        (archived_skill_id, archived_ns_id, 'codex-archived-search', fixture_user_id, 'Codex Search Archived Fixture',
         'codex-search-fixture archived summary',
         'archived', 'codex-search-fixture',
         'PUBLIC', 'ACTIVE', '2026-06-07T09:00:00Z'::timestamptz)
    ON CONFLICT (skill_id) DO UPDATE
        SET namespace_id = EXCLUDED.namespace_id,
            namespace_slug = EXCLUDED.namespace_slug,
            owner_id = EXCLUDED.owner_id,
            title = EXCLUDED.title,
            summary = EXCLUDED.summary,
            keywords = EXCLUDED.keywords,
            search_text = EXCLUDED.search_text,
            visibility = EXCLUDED.visibility,
            status = EXCLUDED.status,
            updated_at = EXCLUDED.updated_at;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-LabelsContractComparison {
    $java = Invoke-RestMethod "$JavaUrl/api/v1/labels"
    $python = Invoke-RestMethod "$PythonUrl/api/v1/labels"
    $proxyV1 = Invoke-RestMethod "$WebUrl/api/v1/labels"
    $proxyWeb = Invoke-RestMethod "$WebUrl/api/web/labels"

    $javaStable = ConvertTo-StableContractJson -Response $java
    $pythonStable = ConvertTo-StableContractJson -Response $python
    $proxyV1Stable = ConvertTo-StableContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableContractJson -Response $proxyWeb

    $result = [ordered]@{
        javaStatus = [ordered]@{
            code = $java.code
            msg = $java.msg
            count = @($java.data).Count
        }
        pythonStatus = [ordered]@{
            code = $python.code
            msg = $python.msg
            count = @($python.data).Count
        }
        proxyV1Status = [ordered]@{
            code = $proxyV1.code
            msg = $proxyV1.msg
            count = @($proxyV1.data).Count
        }
        proxyWebStatus = [ordered]@{
            code = $proxyWeb.code
            msg = $proxyWeb.msg
            count = @($proxyWeb.data).Count
        }
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'labels-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.javaMatchesPython) {
        throw 'Java and Python labels contracts differ. See .dev/labels-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxyV1) {
        throw 'Vite /api/v1/labels proxy does not match Python. See .dev/labels-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxyWeb) {
        throw 'Vite /api/web/labels proxy does not match Python. See .dev/labels-contract-result.json.'
    }
}

function Invoke-HttpStatus {
    param([string]$Url)

    try {
        $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 10
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Invoke-DetailContractComparison {
    Ensure-DetailContractFixture

    $slug = 'codex-detail-fixture-20260607230000'
    $hiddenSlug = 'codex-detail-hidden-20260607230000'
    $noLatestSlug = 'codex-detail-no-latest-20260607230000'
    $archivedNamespace = 'codex-archived-detail'
    $archivedSlug = 'codex-detail-archived-20260607230000'

    Write-Host "Comparing public skill detail contract..."
    $java = Invoke-RestMethod "$JavaUrl/api/v1/skills/global/$slug"
    $python = Invoke-RestMethod "$PythonUrl/api/v1/skills/global/$slug"
    $proxyV1 = Invoke-RestMethod "$WebUrl/api/v1/skills/global/$slug"
    $proxyWeb = Invoke-RestMethod "$WebUrl/api/web/skills/global/$slug"

    $javaStable = ConvertTo-StableDetailContractJson -Response $java
    $pythonStable = ConvertTo-StableDetailContractJson -Response $python
    $proxyV1Stable = ConvertTo-StableDetailContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableDetailContractJson -Response $proxyWeb

    $hiddenJavaStatus = Invoke-HttpStatus "$JavaUrl/api/v1/skills/global/$hiddenSlug"
    $hiddenPythonStatus = Invoke-HttpStatus "$PythonUrl/api/v1/skills/global/$hiddenSlug"
    $noLatestJavaStatus = Invoke-HttpStatus "$JavaUrl/api/v1/skills/global/$noLatestSlug"
    $noLatestPythonStatus = Invoke-HttpStatus "$PythonUrl/api/v1/skills/global/$noLatestSlug"
    $archivedJavaStatus = Invoke-HttpStatus "$JavaUrl/api/v1/skills/$archivedNamespace/$archivedSlug"
    $archivedPythonStatus = Invoke-HttpStatus "$PythonUrl/api/v1/skills/$archivedNamespace/$archivedSlug"

    $result = [ordered]@{
        fixtureSlug = $slug
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        publicDetail = [ordered]@{
            id = $python.data.id
            slug = $python.data.slug
            ownerDisplayName = $python.data.ownerDisplayName
            labels = @($python.data.labels).Count
            headlineVersion = $python.data.headlineVersion.version
            publishedVersion = $python.data.publishedVersion.version
            ownerPreviewVersion = $python.data.ownerPreviewVersion
            resolutionMode = $python.data.resolutionMode
        }
        hidden = [ordered]@{
            javaStatus = $hiddenJavaStatus
            pythonStatus = $hiddenPythonStatus
            matches = ($hiddenJavaStatus -eq $hiddenPythonStatus)
        }
        noLatest = [ordered]@{
            javaStatus = $noLatestJavaStatus
            pythonStatus = $noLatestPythonStatus
            matches = ($noLatestJavaStatus -eq $noLatestPythonStatus)
        }
        archivedNamespace = [ordered]@{
            javaStatus = $archivedJavaStatus
            pythonStatus = $archivedPythonStatus
            matches = ($archivedJavaStatus -eq $archivedPythonStatus)
        }
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'detail-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.javaMatchesPython) {
        throw 'Java and Python detail contracts differ. See .dev/detail-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 skill detail does not match Python. See .dev/detail-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web skill detail does not match Python. See .dev/detail-contract-result.json.'
    }
    if (-not $result.hidden.matches -or -not $result.noLatest.matches -or -not $result.archivedNamespace.matches) {
        throw 'Detail negative-case statuses differ. See .dev/detail-contract-result.json.'
    }
}

function Invoke-SearchContractComparison {
    Ensure-SearchContractFixture

    $cases = @(
        [ordered]@{ name = 'defaultNewest'; query = '?q=codex-search-fixture&sort=newest&page=0&size=5' },
        [ordered]@{ name = 'relevanceSingle'; query = '?q=codex-search-alpha-unique&sort=relevance&page=0&size=5' },
        [ordered]@{ name = 'namespaceFilter'; query = '?q=codex-search-fixture&namespace=global&sort=newest&page=0&size=5' },
        [ordered]@{ name = 'labelFilter'; query = '?q=codex-search-fixture&label=codex-search-featured&sort=newest&page=0&size=5' },
        [ordered]@{ name = 'downloadsSort'; query = '?q=codex-search-fixture&sort=downloads&page=0&size=5' },
        [ordered]@{ name = 'ratingSort'; query = '?q=codex-search-fixture&sort=rating&page=0&size=5' },
        [ordered]@{ name = 'invalidPagination'; query = '?q=codex-search-fixture&sort=newest&page=-1&size=0' }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing portal skill search contract: $($case.name)"
        $query = $case.query
        $java = Invoke-RestMethod "$JavaUrl/api/web/skills$query"
        $python = Invoke-RestMethod "$PythonUrl/api/web/skills$query"
        $proxyWeb = Invoke-RestMethod "$WebUrl/api/web/skills$query"

        $javaStable = ConvertTo-StableSearchContractJson -Response $java
        $pythonStable = ConvertTo-StableSearchContractJson -Response $python
        $proxyWebStable = ConvertTo-StableSearchContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            query = $query
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            total = $python.data.total
            page = $python.data.page
            size = $python.data.size
            slugs = @($python.data.items | ForEach-Object { $_.slug })
        }
    }

    $v1Response = Invoke-RestMethod "$WebUrl/api/v1/skills?page=0&limit=1"
    $v1HasPortalEnvelope = [bool]($v1Response.PSObject.Properties['code'] -and $v1Response.PSObject.Properties['data'])
    $v1HasClawHubShape = [bool]($v1Response.PSObject.Properties['items'] -and -not $v1HasPortalEnvelope)

    $result = [ordered]@{
        cases = $caseResults
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        v1SkillsRemainsJava = $v1HasClawHubShape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'search-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python portal search contracts differ. See .dev/search-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web/skills does not match Python. See .dev/search-contract-result.json.'
    }
    if (-not $result.v1SkillsRemainsJava) {
        throw 'Vite /api/v1/skills no longer has the Java ClawHub list shape. See .dev/search-contract-result.json.'
    }
}

function Invoke-ClawHubSearchContractComparison {
    Ensure-SearchContractFixture

    $query = '?q=codex-search-alpha-unique&page=0&limit=5'
    Write-Host "Comparing ClawHub search contract..."
    $java = Invoke-RestMethod "$JavaUrl/api/v1/search$query"
    $python = Invoke-RestMethod "$PythonUrl/api/v1/search$query"
    $proxy = Invoke-RestMethod "$WebUrl/api/v1/search$query"

    $javaStable = ConvertTo-StablePlainJson -Response $java
    $pythonStable = ConvertTo-StablePlainJson -Response $python
    $proxyStable = ConvertTo-StablePlainJson -Response $proxy

    $v1Skills = Invoke-RestMethod "$WebUrl/api/v1/skills?page=0&limit=1"
    $v1HasPortalEnvelope = [bool]($v1Skills.PSObject.Properties['code'] -and $v1Skills.PSObject.Properties['data'])
    $v1HasClawHubShape = [bool]($v1Skills.PSObject.Properties['items'] -and -not $v1HasPortalEnvelope)

    $result = [ordered]@{
        query = $query
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        v1SkillsRemainsJava = $v1HasClawHubShape
        resultCount = @($python.results).Count
        firstSlug = if (@($python.results).Count -gt 0) { $python.results[0].slug } else { $null }
        plainShape = [bool]($python.PSObject.Properties['results'] -and -not $python.PSObject.Properties['code'])
    }

    $resultPath = Join-Path $DevDir 'clawhub-search-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.javaMatchesPython) {
        throw 'Java and Python ClawHub search contracts differ. See .dev/clawhub-search-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxy) {
        throw 'Vite proxy /api/v1/search does not match Python. See .dev/clawhub-search-contract-result.json.'
    }
    if (-not $result.v1SkillsRemainsJava) {
        throw 'Vite /api/v1/skills no longer has the Java ClawHub list shape. See .dev/clawhub-search-contract-result.json.'
    }
    if (-not $result.plainShape) {
        throw 'Python /api/v1/search is not returning the plain ClawHub response shape.'
    }
}

function Invoke-HttpStatusNoRedirect {
    param(
        [string]$Url,
        [string]$Method = 'GET',
        [hashtable]$Headers = @{}
    )

    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = $Method
        $request.AllowAutoRedirect = $false
        $request.Timeout = 10000
        foreach ($header in $Headers.GetEnumerator()) {
            $request.Headers[$header.Key] = [string]$header.Value
        }
        if ($Method -in @('POST', 'PUT', 'PATCH')) {
            $request.ContentLength = 0
        }
        $response = $request.GetResponse()
        try {
            return [int]$response.StatusCode
        } finally {
            $response.Close()
        }
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $response = $_.Exception.Response
            try {
                return [int]$response.StatusCode
            } finally {
                $response.Close()
            }
        }
        throw
    } catch {
        $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers $Headers -UseBasicParsing -TimeoutSec 10
        return [int]$response.StatusCode
    }
}

function Invoke-ClawHubResolveContractComparison {
    Ensure-SearchContractFixture

    $slug = 'codex-search-alpha-20260607233000'
    $query = "?slug=$slug&version=latest"
    $pathQuery = "?version=latest"
    Write-Host "Comparing ClawHub resolve contract..."

    $javaQuery = Invoke-RestMethod "$JavaUrl/api/v1/resolve$query"
    $pythonQuery = Invoke-RestMethod "$PythonUrl/api/v1/resolve$query"
    $proxyQuery = Invoke-RestMethod "$WebUrl/api/v1/resolve$query"

    $javaPath = Invoke-RestMethod "$JavaUrl/api/v1/resolve/$slug$pathQuery"
    $pythonPath = Invoke-RestMethod "$PythonUrl/api/v1/resolve/$slug$pathQuery"
    $proxyPath = Invoke-RestMethod "$WebUrl/api/v1/resolve/$slug$pathQuery"

    $javaQueryStable = ConvertTo-StablePlainJson -Response $javaQuery
    $pythonQueryStable = ConvertTo-StablePlainJson -Response $pythonQuery
    $proxyQueryStable = ConvertTo-StablePlainJson -Response $proxyQuery
    $javaPathStable = ConvertTo-StablePlainJson -Response $javaPath
    $pythonPathStable = ConvertTo-StablePlainJson -Response $pythonPath
    $proxyPathStable = ConvertTo-StablePlainJson -Response $proxyPath

    $downloadStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/download/$slug"
    $skillDetail = Invoke-RestMethod "$WebUrl/api/v1/skills/$slug"
    $skillDetailIsClawHub = [bool]($skillDetail.PSObject.Properties['skill'] -and $skillDetail.PSObject.Properties['latestVersion'] -and -not $skillDetail.PSObject.Properties['code'])

    $result = [ordered]@{
        slug = $slug
        query = [ordered]@{
            javaMatchesPython = ($javaQueryStable -eq $pythonQueryStable)
            pythonMatchesProxy = ($pythonQueryStable -eq $proxyQueryStable)
            matchVersion = if ($pythonQuery.match) { $pythonQuery.match.version } else { $null }
            latestVersion = if ($pythonQuery.latestVersion) { $pythonQuery.latestVersion.version } else { $null }
        }
        path = [ordered]@{
            javaMatchesPython = ($javaPathStable -eq $pythonPathStable)
            pythonMatchesProxy = ($pythonPathStable -eq $proxyPathStable)
            matchVersion = if ($pythonPath.match) { $pythonPath.match.version } else { $null }
            latestVersion = if ($pythonPath.latestVersion) { $pythonPath.latestVersion.version } else { $null }
        }
        plainShape = [bool]($pythonQuery.PSObject.Properties['match'] -and $pythonQuery.PSObject.Properties['latestVersion'] -and -not $pythonQuery.PSObject.Properties['code'])
        downloadRemainsJava = ($downloadStatus -eq 302)
        v1SkillDetailRemainsJava = $skillDetailIsClawHub
    }

    $resultPath = Join-Path $DevDir 'clawhub-resolve-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.query.javaMatchesPython -or -not $result.path.javaMatchesPython) {
        throw 'Java and Python ClawHub resolve contracts differ. See .dev/clawhub-resolve-contract-result.json.'
    }
    if (-not $result.query.pythonMatchesProxy -or -not $result.path.pythonMatchesProxy) {
        throw 'Vite proxy /api/v1/resolve does not match Python. See .dev/clawhub-resolve-contract-result.json.'
    }
    if (-not $result.plainShape) {
        throw 'Python /api/v1/resolve is not returning the plain ClawHub response shape.'
    }
    if (-not $result.downloadRemainsJava) {
        throw 'Vite /api/v1/download no longer has Java redirect behavior. See .dev/clawhub-resolve-contract-result.json.'
    }
    if (-not $result.v1SkillDetailRemainsJava) {
        throw 'Vite /api/v1/skills/{canonicalSlug} no longer has the Java ClawHub skill shape. See .dev/clawhub-resolve-contract-result.json.'
    }
}

function Invoke-ClawHubSkillContractComparison {
    Ensure-SearchContractFixture

    $slug = 'codex-search-alpha-20260607233000'
    Write-Host "Comparing ClawHub skill detail contract..."
    $java = Invoke-RestMethod "$JavaUrl/api/v1/skills/$slug"
    $python = Invoke-RestMethod "$PythonUrl/api/v1/skills/$slug"
    $proxy = Invoke-RestMethod "$WebUrl/api/v1/skills/$slug"

    $javaStable = ConvertTo-StablePlainJson -Response $java
    $pythonStable = ConvertTo-StablePlainJson -Response $python
    $proxyStable = ConvertTo-StablePlainJson -Response $proxy

    $v1Skills = Invoke-RestMethod "$WebUrl/api/v1/skills?page=0&limit=1"
    $v1HasPortalEnvelope = [bool]($v1Skills.PSObject.Properties['code'] -and $v1Skills.PSObject.Properties['data'])
    $v1HasClawHubListShape = [bool]($v1Skills.PSObject.Properties['items'] -and -not $v1HasPortalEnvelope)

    $deleteJavaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$slug" 'DELETE'
    $deleteProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$slug" 'DELETE'
    $undeleteJavaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$slug/undelete" 'POST'
    $undeleteProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$slug/undelete" 'POST'
    $downloadStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/download/$slug"

    $result = [ordered]@{
        slug = $slug
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        plainShape = [bool]($python.PSObject.Properties['skill'] -and $python.PSObject.Properties['latestVersion'] -and -not $python.PSObject.Properties['code'])
        skillSlug = $python.skill.slug
        latestVersion = if ($python.latestVersion) { $python.latestVersion.version } else { $null }
        v1SkillsListRemainsJava = $v1HasClawHubListShape
        downloadRemainsJava = ($downloadStatus -eq 302)
        deleteRemainsJava = ($deleteJavaStatus -eq $deleteProxyStatus)
        undeleteRemainsJava = ($undeleteJavaStatus -eq $undeleteProxyStatus)
        javaMutationStatuses = [ordered]@{
            delete = $deleteJavaStatus
            undelete = $undeleteJavaStatus
        }
        proxyMutationStatuses = [ordered]@{
            delete = $deleteProxyStatus
            undelete = $undeleteProxyStatus
        }
    }

    $resultPath = Join-Path $DevDir 'clawhub-skill-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.javaMatchesPython) {
        throw 'Java and Python ClawHub skill detail contracts differ. See .dev/clawhub-skill-contract-result.json.'
    }
    if (-not $result.pythonMatchesProxy) {
        throw 'Vite proxy /api/v1/skills/{canonicalSlug} does not match Python. See .dev/clawhub-skill-contract-result.json.'
    }
    if (-not $result.plainShape) {
        throw 'Python /api/v1/skills/{canonicalSlug} is not returning the plain ClawHub skill response shape.'
    }
    if (-not $result.v1SkillsListRemainsJava) {
        throw 'Vite /api/v1/skills list no longer has the Java ClawHub list shape. See .dev/clawhub-skill-contract-result.json.'
    }
    if (-not $result.downloadRemainsJava) {
        throw 'Vite /api/v1/download no longer has Java redirect behavior. See .dev/clawhub-skill-contract-result.json.'
    }
    if (-not $result.deleteRemainsJava -or -not $result.undeleteRemainsJava) {
        throw 'ClawHub mutation routes no longer match Java status behavior. See .dev/clawhub-skill-contract-result.json.'
    }
}

function Invoke-ClawHubListContractComparison {
    Ensure-SearchContractFixture

    $cases = @(
        [ordered]@{ name = 'newest'; query = '?page=0&limit=5&sort=newest' },
        [ordered]@{ name = 'downloads'; query = '?page=0&limit=5&sort=downloads' },
        [ordered]@{ name = 'rating'; query = '?page=0&limit=5&sort=rating' }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        $query = $case.query
        Write-Host "Comparing ClawHub skills list contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl/api/v1/skills$query"
        $python = Invoke-RestMethod "$PythonUrl/api/v1/skills$query"
        $proxy = Invoke-RestMethod "$WebUrl/api/v1/skills$query"

        $javaStable = ConvertTo-StablePlainJson -Response $java
        $pythonStable = ConvertTo-StablePlainJson -Response $python
        $proxyStable = ConvertTo-StablePlainJson -Response $proxy

        $caseResults += [ordered]@{
            name = $case.name
            query = $query
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxy = ($pythonStable -eq $proxyStable)
            plainShape = [bool]($python.PSObject.Properties['items'] -and -not $python.PSObject.Properties['code'])
            itemCount = @($python.items).Count
            nextCursor = $python.nextCursor
            firstSlug = if (@($python.items).Count -gt 0) { $python.items[0].slug } else { $null }
        }
    }

    $slug = 'codex-search-alpha-20260607233000'
    $postJavaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills" 'POST'
    $postProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills" 'POST'
    $deleteJavaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$slug" 'DELETE'
    $deleteProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$slug" 'DELETE'
    $downloadStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/download/$slug"

    $result = [ordered]@{
        cases = $caseResults
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxy = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxy })
        plainShape = -not [bool]($caseResults | Where-Object { -not $_.plainShape })
        rootPostRemainsJava = ($postJavaStatus -eq $postProxyStatus)
        deleteRemainsJava = ($deleteJavaStatus -eq $deleteProxyStatus)
        downloadRemainsJava = ($downloadStatus -eq 302)
        javaMutationStatuses = [ordered]@{
            post = $postJavaStatus
            delete = $deleteJavaStatus
        }
        proxyMutationStatuses = [ordered]@{
            post = $postProxyStatus
            delete = $deleteProxyStatus
        }
    }

    $resultPath = Join-Path $DevDir 'clawhub-list-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python ClawHub list contracts differ. See .dev/clawhub-list-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxy) {
        throw 'Vite proxy /api/v1/skills does not match Python. See .dev/clawhub-list-contract-result.json.'
    }
    if (-not $result.rootPostRemainsJava -or -not $result.deleteRemainsJava) {
        throw 'ClawHub mutation routes no longer match Java status behavior. See .dev/clawhub-list-contract-result.json.'
    }
    if (-not $result.plainShape) {
        throw 'Python /api/v1/skills is not returning the plain ClawHub list response shape.'
    }
    if (-not $result.downloadRemainsJava) {
        throw 'Vite /api/v1/download no longer has Java redirect behavior. See .dev/clawhub-list-contract-result.json.'
    }
}

function Invoke-FilesContractComparison {
    Ensure-FilesContractFixture

    $slug = "codex-files-fixture-20260607224000"
    $version = "1.2.0"
    $tag = "stable"
    $tagLatest = "latest"

    Write-Host "Comparing version files metadata contract..."
    $javaVer = Invoke-RestMethod "$JavaUrl/api/v1/skills/global/$slug/versions/$version/files"
    $pythonVer = Invoke-RestMethod "$PythonUrl/api/v1/skills/global/$slug/versions/$version/files"
    $proxyVerV1 = Invoke-RestMethod "$WebUrl/api/v1/skills/global/$slug/versions/$version/files"
    $proxyVerWeb = Invoke-RestMethod "$WebUrl/api/web/skills/global/$slug/versions/$version/files"

    $javaVerStable = ConvertTo-StableContractJson -Response $javaVer
    $pythonVerStable = ConvertTo-StableContractJson -Response $pythonVer
    $proxyVerV1Stable = ConvertTo-StableContractJson -Response $proxyVerV1
    $proxyVerWebStable = ConvertTo-StableContractJson -Response $proxyVerWeb

    Write-Host "Comparing tag stable files metadata contract..."
    $javaTag = Invoke-RestMethod "$JavaUrl/api/v1/skills/global/$slug/tags/$tag/files"
    $pythonTag = Invoke-RestMethod "$PythonUrl/api/v1/skills/global/$slug/tags/$tag/files"
    $proxyTagV1 = Invoke-RestMethod "$WebUrl/api/v1/skills/global/$slug/tags/$tag/files"
    $proxyTagWeb = Invoke-RestMethod "$WebUrl/api/web/skills/global/$slug/tags/$tag/files"

    $javaTagStable = ConvertTo-StableContractJson -Response $javaTag
    $pythonTagStable = ConvertTo-StableContractJson -Response $pythonTag
    $proxyTagV1Stable = ConvertTo-StableContractJson -Response $proxyTagV1
    $proxyTagWebStable = ConvertTo-StableContractJson -Response $proxyTagWeb

    Write-Host "Comparing tag latest files metadata contract..."
    $javaTagLatest = Invoke-RestMethod "$JavaUrl/api/v1/skills/global/$slug/tags/$tagLatest/files"
    $pythonTagLatest = Invoke-RestMethod "$PythonUrl/api/v1/skills/global/$slug/tags/$tagLatest/files"
    $proxyTagLatestV1 = Invoke-RestMethod "$WebUrl/api/v1/skills/global/$slug/tags/$tagLatest/files"
    $proxyTagLatestWeb = Invoke-RestMethod "$WebUrl/api/web/skills/global/$slug/tags/$tagLatest/files"

    $javaTagLatestStable = ConvertTo-StableContractJson -Response $javaTagLatest
    $pythonTagLatestStable = ConvertTo-StableContractJson -Response $pythonTagLatest
    $proxyTagLatestV1Stable = ConvertTo-StableContractJson -Response $proxyTagLatestV1
    $proxyTagLatestWebStable = ConvertTo-StableContractJson -Response $proxyTagLatestWeb

    $result = [ordered]@{
        versionFiles = [ordered]@{
            javaMatchesPython = ($javaVerStable -eq $pythonVerStable)
            pythonMatchesProxyV1 = ($pythonVerStable -eq $proxyVerV1Stable)
            pythonMatchesProxyWeb = ($pythonVerStable -eq $proxyVerWebStable)
        }
        tagStableFiles = [ordered]@{
            javaMatchesPython = ($javaTagStable -eq $pythonTagStable)
            pythonMatchesProxyV1 = ($pythonTagStable -eq $proxyTagV1Stable)
            pythonMatchesProxyWeb = ($pythonTagStable -eq $proxyTagWebStable)
        }
        tagLatestFiles = [ordered]@{
            javaMatchesPython = ($javaTagLatestStable -eq $pythonTagLatestStable)
            pythonMatchesProxyV1 = ($pythonTagLatestStable -eq $proxyTagLatestV1Stable)
            pythonMatchesProxyWeb = ($pythonTagLatestStable -eq $proxyTagLatestWebStable)
        }
    }

    $resultPath = Join-Path $DevDir 'files-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.versionFiles.javaMatchesPython -or -not $result.tagStableFiles.javaMatchesPython -or -not $result.tagLatestFiles.javaMatchesPython) {
        throw 'Java and Python files contracts differ. See .dev/files-contract-result.json.'
    }
    if (-not $result.versionFiles.pythonMatchesProxyV1 -or -not $result.tagStableFiles.pythonMatchesProxyV1 -or -not $result.tagLatestFiles.pythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1/.../files does not match Python. See .dev/files-contract-result.json.'
    }
    if (-not $result.versionFiles.pythonMatchesProxyWeb -or -not $result.tagStableFiles.pythonMatchesProxyWeb -or -not $result.tagLatestFiles.pythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web/.../files does not match Python. See .dev/files-contract-result.json.'
    }
}

function Invoke-HybridLabelsSmokeVerification {
    try {
        Start-Hybrid
        Invoke-LabelsContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridFilesSmokeVerification {
    try {
        Start-Hybrid
        Invoke-FilesContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridDetailSmokeVerification {
    try {
        Start-Hybrid
        Invoke-DetailContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridSearchSmokeVerification {
    try {
        Start-Hybrid
        Invoke-SearchContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridClawHubSearchSmokeVerification {
    try {
        Start-Hybrid
        Invoke-ClawHubSearchContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridClawHubResolveSmokeVerification {
    try {
        Start-Hybrid
        Invoke-ClawHubResolveContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridClawHubSkillSmokeVerification {
    try {
        Start-Hybrid
        Invoke-ClawHubSkillContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridClawHubListSmokeVerification {
    try {
        Start-Hybrid
        Invoke-ClawHubListContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-AuthContractFixture {
    $sql = @'
DO $$
DECLARE
    super_admin_role_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('local-user', 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        ('local-admin', 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    SELECT id INTO super_admin_role_id
    FROM role
    WHERE code = 'SUPER_ADMIN';

    IF super_admin_role_id IS NOT NULL THEN
        INSERT INTO user_role_binding (user_id, role_id)
        VALUES ('local-admin', super_admin_role_id)
        ON CONFLICT (user_id, role_id) DO NOTHING;
    END IF;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-HttpStatusWithHeaders {
    param(
        [string]$Url,
        [hashtable]$Headers = @{}
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 10
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Invoke-AuthMeContractComparison {
    Ensure-AuthContractFixture

    $users = @('local-user', 'local-admin')
    $caseResults = @()
    foreach ($userId in $users) {
        $headers = @{ 'X-Mock-User-Id' = $userId }

        Write-Host "Comparing auth/me contract for $userId..."
        $java = Invoke-RestMethod "$JavaUrl/api/v1/auth/me" -Headers $headers
        $python = Invoke-RestMethod "$PythonUrl/api/v1/auth/me" -Headers $headers
        $proxy = Invoke-RestMethod "$WebUrl/api/v1/auth/me" -Headers $headers

        $javaStable = ConvertTo-StableAuthMeContractJson -Response $java
        $pythonStable = ConvertTo-StableAuthMeContractJson -Response $python
        $proxyStable = ConvertTo-StableAuthMeContractJson -Response $proxy

        $caseResults += [ordered]@{
            userId = $userId
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxy = ($pythonStable -eq $proxyStable)
            roles = @($python.data.platformRoles | Sort-Object)
            javaStable = $javaStable
            pythonStable = $pythonStable
            proxyStable = $proxyStable
        }
    }

    $javaNoHeaderStatus = Invoke-HttpStatusWithHeaders "$JavaUrl/api/v1/auth/me"
    $pythonNoHeaderStatus = Invoke-HttpStatusWithHeaders "$PythonUrl/api/v1/auth/me"
    $proxyNoHeaderStatus = Invoke-HttpStatusWithHeaders "$WebUrl/api/v1/auth/me"

    $javaMethods = Invoke-RestMethod "$JavaUrl/api/v1/auth/methods"
    $proxyMethods = Invoke-RestMethod "$WebUrl/api/v1/auth/methods"
    $javaMethodsStable = ConvertTo-StableContractJson -Response $javaMethods
    $proxyMethodsStable = ConvertTo-StableContractJson -Response $proxyMethods

    $result = [ordered]@{
        cases = $caseResults
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxy = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxy })
        noHeaderStatuses = [ordered]@{
            java = $javaNoHeaderStatus
            python = $pythonNoHeaderStatus
            proxy = $proxyNoHeaderStatus
        }
        noHeaderMatches = ($javaNoHeaderStatus -eq 401 -and $pythonNoHeaderStatus -eq 401 -and $proxyNoHeaderStatus -eq 401)
        authMethodsRemainsJava = ($javaMethodsStable -eq $proxyMethodsStable)
    }

    $resultPath = Join-Path $DevDir 'auth-me-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python auth/me contracts differ. See .dev/auth-me-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxy) {
        throw 'Vite proxy /api/v1/auth/me does not match Python. See .dev/auth-me-contract-result.json.'
    }
    if (-not $result.noHeaderMatches) {
        throw 'Missing mock-user auth/me status behavior is not 401 across Java/Python/Vite. See .dev/auth-me-contract-result.json.'
    }
    if (-not $result.authMethodsRemainsJava) {
        throw 'Vite /api/v1/auth/methods no longer matches Java. See .dev/auth-me-contract-result.json.'
    }
}

function Invoke-HybridAuthMeSmokeVerification {
    try {
        Start-Hybrid
        Invoke-AuthMeContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-AuthDetailContractFixture {
    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    global_ns_id BIGINT;
    team_ns_id BIGINT;
    global_skill_id BIGINT;
    team_skill_id BIGINT;
    blocked_skill_id BIGINT;
    global_version_id BIGINT;
    team_version_id BIGINT;
    blocked_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO global_ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-auth-detail-team', 'Codex Auth Detail Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        download_count,
        star_count,
        subscription_count,
        rating_avg,
        rating_count,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        global_ns_id,
        'codex-auth-detail-global-20260608',
        'Codex Auth Detail Global',
        'Global auth detail fixture',
        local_user_id,
        'PUBLIC',
        'ACTIVE',
        0,
        0,
        0,
        0.00,
        0,
        local_user_id,
        local_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO global_skill_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        download_count,
        star_count,
        subscription_count,
        rating_avg,
        rating_count,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        team_ns_id,
        'codex-auth-detail-team-20260608',
        'Codex Auth Detail Team Skill',
        'Team auth detail fixture',
        local_user_id,
        'PUBLIC',
        'ACTIVE',
        0,
        0,
        0,
        0.00,
        0,
        local_user_id,
        local_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_skill_id;

    INSERT INTO skill (
        namespace_id,
        slug,
        display_name,
        summary,
        owner_id,
        visibility,
        status,
        download_count,
        star_count,
        subscription_count,
        rating_avg,
        rating_count,
        created_by,
        updated_by,
        hidden
    )
    VALUES (
        team_ns_id,
        'codex-auth-detail-blocked-20260608',
        'Codex Auth Detail Blocked Skill',
        'Blocked promotion auth detail fixture',
        local_user_id,
        'PUBLIC',
        'ACTIVE',
        0,
        0,
        0,
        0.00,
        0,
        local_user_id,
        local_user_id,
        FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO blocked_skill_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES
        (
            global_skill_id,
            '1.0.0',
            'PUBLISHED',
            'global auth detail fixture',
            jsonb_build_object('name', 'auth-detail-global', 'version', '1.0.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1,
            100,
            '2026-06-08T01:00:00Z'::timestamptz,
            local_user_id,
            '2026-06-08T01:00:00Z'::timestamptz,
            TRUE,
            TRUE,
            'PUBLIC'
        )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO global_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES
        (
            team_skill_id,
            '1.0.0',
            'PUBLISHED',
            'team auth detail fixture',
            jsonb_build_object('name', 'auth-detail-team', 'version', '1.0.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1,
            100,
            '2026-06-08T01:05:00Z'::timestamptz,
            local_user_id,
            '2026-06-08T01:05:00Z'::timestamptz,
            TRUE,
            TRUE,
            'PUBLIC'
        )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO team_version_id;

    INSERT INTO skill_version (
        skill_id,
        version,
        status,
        changelog,
        parsed_metadata_json,
        manifest_json,
        file_count,
        total_size,
        published_at,
        created_by,
        created_at,
        bundle_ready,
        download_ready,
        requested_visibility
    )
    VALUES
        (
            blocked_skill_id,
            '1.0.0',
            'PUBLISHED',
            'blocked auth detail fixture',
            jsonb_build_object('name', 'auth-detail-blocked', 'version', '1.0.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1,
            100,
            '2026-06-08T01:10:00Z'::timestamptz,
            local_user_id,
            '2026-06-08T01:10:00Z'::timestamptz,
            TRUE,
            TRUE,
            'PUBLIC'
        )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO blocked_version_id;

    UPDATE skill
    SET latest_version_id = global_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = global_skill_id;

    UPDATE skill
    SET latest_version_id = team_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = team_skill_id;

    UPDATE skill
    SET latest_version_id = blocked_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = blocked_skill_id;

    INSERT INTO promotion_request (
        source_skill_id,
        source_version_id,
        target_namespace_id,
        status,
        submitted_by
    )
    VALUES (
        blocked_skill_id,
        blocked_version_id,
        global_ns_id,
        'PENDING',
        local_user_id
    )
    ON CONFLICT (source_version_id) WHERE status = 'PENDING' DO UPDATE
        SET status = 'PENDING',
            target_namespace_id = EXCLUDED.target_namespace_id,
            submitted_by = EXCLUDED.submitted_by,
            submitted_at = CURRENT_TIMESTAMP;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-AuthenticatedDetailContractComparison {
    Ensure-AuthDetailContractFixture

    $cases = @(
        [ordered]@{ name = 'anonymousGlobal'; path = '/api/v1/skills/global/codex-auth-detail-global-20260608'; headers = @{} },
        [ordered]@{ name = 'ownerGlobal'; path = '/api/v1/skills/global/codex-auth-detail-global-20260608'; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'ownerTeam'; path = '/api/v1/skills/codex-auth-detail-team/codex-auth-detail-team-20260608'; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminTeam'; path = '/api/v1/skills/codex-auth-detail-team/codex-auth-detail-team-20260608'; headers = @{ 'X-Mock-User-Id' = 'local-admin' } },
        [ordered]@{ name = 'promotionBlockedTeam'; path = '/api/v1/skills/codex-auth-detail-team/codex-auth-detail-blocked-20260608'; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing authenticated skill detail contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableDetailContractJson -Response $java
        $pythonStable = ConvertTo-StableDetailContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableDetailContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableDetailContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            flags = [ordered]@{
                canManageLifecycle = $python.data.canManageLifecycle
                canSubmitPromotion = $python.data.canSubmitPromotion
                canInteract = $python.data.canInteract
                canReport = $python.data.canReport
            }
        }
    }

    $result = [ordered]@{
        cases = $caseResults
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'auth-detail-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python authenticated detail contracts differ. See .dev/auth-detail-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 authenticated detail does not match Python. See .dev/auth-detail-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web authenticated detail does not match Python. See .dev/auth-detail-contract-result.json.'
    }
}

function Invoke-HybridAuthenticatedDetailSmokeVerification {
    try {
        Start-Hybrid
        Invoke-AuthenticatedDetailContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewDetailContractFixture {
    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    rejected_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-preview-team', 'Codex Owner Preview Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-preview-20260608', 'Codex Owner Preview Skill',
        'Owner preview detail fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner preview published fixture',
        jsonb_build_object('name', 'owner-preview', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '2026-06-08T02:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T02:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'REJECTED', 'owner preview rejected fixture',
        jsonb_build_object('name', 'owner-preview', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 110, NULL, local_user_id, '2026-06-08T02:30:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'REJECTED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO rejected_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM review_task
    WHERE skill_version_id = rejected_version_id
      AND status = 'REJECTED';

    INSERT INTO review_task (
        skill_version_id, namespace_id, status, submitted_by, reviewed_by,
        review_comment, submitted_at, reviewed_at
    )
    VALUES (
        rejected_version_id, team_ns_id, 'REJECTED', local_user_id, local_admin_id,
        'metadata missing', '2026-06-08T02:31:00Z'::timestamptz,
        '2026-06-08T02:40:00Z'::timestamptz
    );
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewDetailContractComparison {
    Ensure-OwnerPreviewDetailContractFixture

    $path = '/api/v1/skills/codex-owner-preview-team/codex-owner-preview-20260608'
    $cases = @(
        [ordered]@{ name = 'anonymous'; path = $path; headers = @{} },
        [ordered]@{ name = 'owner'; path = $path; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdmin'; path = $path; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing owner preview detail contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableDetailContractJson -Response $java
        $pythonStable = ConvertTo-StableDetailContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableDetailContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableDetailContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            projection = [ordered]@{
                headlineStatus = if ($null -ne $python.data.headlineVersion) { $python.data.headlineVersion.status } else { $null }
                publishedStatus = if ($null -ne $python.data.publishedVersion) { $python.data.publishedVersion.status } else { $null }
                ownerPreviewStatus = if ($null -ne $python.data.ownerPreviewVersion) { $python.data.ownerPreviewVersion.status } else { $null }
                ownerPreviewReviewComment = $python.data.ownerPreviewReviewComment
                resolutionMode = $python.data.resolutionMode
                canInteract = $python.data.canInteract
            }
        }
    }

    $anonymous = $caseResults | Where-Object { $_.name -eq 'anonymous' } | Select-Object -First 1
    $owner = $caseResults | Where-Object { $_.name -eq 'owner' } | Select-Object -First 1
    $namespaceAdmin = $caseResults | Where-Object { $_.name -eq 'namespaceAdmin' } | Select-Object -First 1
    $shape = [ordered]@{
        anonymousHidesPreview = ($null -eq $anonymous.projection.ownerPreviewStatus)
        ownerSeesRejectedPreview = ($owner.projection.ownerPreviewStatus -eq 'REJECTED')
        ownerSeesReviewComment = ($owner.projection.ownerPreviewReviewComment -eq 'metadata missing')
        namespaceAdminSeesRejectedPreview = ($namespaceAdmin.projection.ownerPreviewStatus -eq 'REJECTED')
        publishedHeadlineKept = (
            $owner.projection.headlineStatus -eq 'PUBLISHED' -and
            $owner.projection.publishedStatus -eq 'PUBLISHED' -and
            $owner.projection.resolutionMode -eq 'PUBLISHED' -and
            $owner.projection.canInteract -eq $true
        )
    }

    $result = [ordered]@{
        cases = $caseResults
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-detail-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview detail contracts differ. See .dev/owner-preview-detail-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview detail does not match Python. See .dev/owner-preview-detail-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview detail does not match Python. See .dev/owner-preview-detail-contract-result.json.'
    }
    if (-not $result.shape.anonymousHidesPreview -or
        -not $result.shape.ownerSeesRejectedPreview -or
        -not $result.shape.ownerSeesReviewComment -or
        -not $result.shape.namespaceAdminSeesRejectedPreview -or
        -not $result.shape.publishedHeadlineKept) {
        throw 'Owner preview detail shape check failed. See .dev/owner-preview-detail-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewDetailSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewDetailContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewVersionContractFixture {
    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-version-team', 'Codex Owner Version Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-version-20260608', 'Codex Owner Version Skill',
        'Owner preview version fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner version published fixture',
        jsonb_build_object('name', 'owner-version', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '2026-06-08T03:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T03:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES
        (
            fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'owner version pending fixture',
            jsonb_build_object('name', 'owner-version', 'version', '1.1.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            2, 110, NULL, local_user_id, '2026-06-08T03:20:00Z'::timestamptz,
            TRUE, FALSE, 'PUBLIC'
        ),
        (
            fixture_skill_id, '1.2.0', 'REJECTED', 'owner version rejected fixture',
            jsonb_build_object('name', 'owner-version', 'version', '1.2.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            3, 120, NULL, local_user_id, '2026-06-08T03:30:00Z'::timestamptz,
            TRUE, FALSE, 'PUBLIC'
        )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = EXCLUDED.status,
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = EXCLUDED.bundle_ready,
            download_ready = EXCLUDED.download_ready,
            requested_visibility = EXCLUDED.requested_visibility;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewVersionContractComparison {
    Ensure-OwnerPreviewVersionContractFixture

    $basePath = '/api/v1/skills/codex-owner-version-team/codex-owner-version-20260608'
    $listCases = @(
        [ordered]@{ name = 'anonymousList'; path = "$basePath/versions"; headers = @{} },
        [ordered]@{ name = 'ownerList'; path = "$basePath/versions"; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminList'; path = "$basePath/versions"; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $listResults = @()
    foreach ($case in $listCases) {
        Write-Host "Comparing owner preview version list contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableDetailContractJson -Response $java
        $pythonStable = ConvertTo-StableDetailContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableDetailContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableDetailContractJson -Response $proxyWeb

        $listResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            statuses = @($python.data.items | ForEach-Object { $_.status })
        }
    }

    $detailPath = "$basePath/versions/1.1.0"
    $detailCases = @(
        [ordered]@{ name = 'ownerPendingDetail'; path = $detailPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPendingDetail'; path = $detailPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $detailResults = @()
    foreach ($case in $detailCases) {
        Write-Host "Comparing owner preview version detail contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableDetailContractJson -Response $java
        $pythonStable = ConvertTo-StableDetailContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableDetailContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableDetailContractJson -Response $proxyWeb

        $detailResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            status = $python.data.status
            version = $python.data.version
        }
    }

    $anonymousPendingStatus = [ordered]@{
        java = Invoke-HttpStatusWithHeaders "$JavaUrl$detailPath"
        python = Invoke-HttpStatusWithHeaders "$PythonUrl$detailPath"
        proxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$detailPath"
        proxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($detailPath -replace '^/api/v1/', '/api/web/')"
    }

    $anonymousList = $listResults | Where-Object { $_.name -eq 'anonymousList' } | Select-Object -First 1
    $ownerList = $listResults | Where-Object { $_.name -eq 'ownerList' } | Select-Object -First 1
    $shape = [ordered]@{
        anonymousListPublishedOnly = (@($anonymousList.statuses) -join ',') -eq 'PUBLISHED'
        ownerListIncludesPreviewStates = (@($ownerList.statuses) -join ',') -eq 'PUBLISHED,REJECTED,PENDING_REVIEW'
        anonymousPendingDetailStatusesMatch = (
            $anonymousPendingStatus.java -eq $anonymousPendingStatus.python -and
            $anonymousPendingStatus.python -eq $anonymousPendingStatus.proxyV1 -and
            $anonymousPendingStatus.python -eq $anonymousPendingStatus.proxyWeb
        )
    }

    $allCases = @($listResults) + @($detailResults)
    $result = [ordered]@{
        listCases = $listResults
        detailCases = $detailResults
        anonymousPendingDetailStatus = $anonymousPendingStatus
        allJavaMatchesPython = -not [bool]($allCases | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($allCases | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($allCases | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-version-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview version contracts differ. See .dev/owner-preview-version-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview version does not match Python. See .dev/owner-preview-version-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview version does not match Python. See .dev/owner-preview-version-contract-result.json.'
    }
    if (-not $result.shape.anonymousListPublishedOnly -or
        -not $result.shape.ownerListIncludesPreviewStates -or
        -not $result.shape.anonymousPendingDetailStatusesMatch) {
        throw 'Owner preview version shape check failed. See .dev/owner-preview-version-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewVersionSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewVersionContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewFilesContractFixture {
    $objects = @{
        'fixtures/owner-preview-files/1.0.0/SKILL.md' = '# Owner preview files published fixture'
        'fixtures/owner-preview-files/1.0.0/README.md' = '# Published file metadata'
        'fixtures/owner-preview-files/1.1.0/SKILL.md' = '# Owner preview files pending fixture'
        'fixtures/owner-preview-files/1.1.0/src/pending.py' = 'print("pending owner preview")'
    }

    foreach ($entry in $objects.GetEnumerator()) {
        $relativePath = $entry.Key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        Set-Content -LiteralPath $targetPath -Value $entry.Value
    }

    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    pending_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-files-team', 'Codex Owner Files Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-files-20260608', 'Codex Owner Files Skill',
        'Owner preview file metadata fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner files published fixture',
        jsonb_build_object('name', 'owner-files', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'README.md'), jsonb_build_object('path', 'SKILL.md')),
        2, 210, '2026-06-08T04:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T04:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'owner files pending fixture',
        jsonb_build_object('name', 'owner-files', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/pending.py')),
        2, 310, NULL, local_user_id, '2026-06-08T04:20:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (published_version_id, pending_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (published_version_id, 'README.md', 88, 'text/markdown', repeat('1', 64), 'fixtures/owner-preview-files/1.0.0/README.md'),
        (published_version_id, 'SKILL.md', 122, 'text/markdown', repeat('2', 64), 'fixtures/owner-preview-files/1.0.0/SKILL.md'),
        (pending_version_id, 'SKILL.md', 144, 'text/markdown', repeat('3', 64), 'fixtures/owner-preview-files/1.1.0/SKILL.md'),
        (pending_version_id, 'src/pending.py', 166, 'text/x-python', repeat('4', 64), 'fixtures/owner-preview-files/1.1.0/src/pending.py');
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewFilesContractComparison {
    Ensure-OwnerPreviewFilesContractFixture

    $basePath = '/api/v1/skills/codex-owner-files-team/codex-owner-files-20260608'
    $publishedPath = "$basePath/versions/1.0.0/files"
    $pendingPath = "$basePath/versions/1.1.0/files"
    $cases = @(
        [ordered]@{ name = 'anonymousPublishedFiles'; path = $publishedPath; headers = @{} },
        [ordered]@{ name = 'ownerPendingFiles'; path = $pendingPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPendingFiles'; path = $pendingPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing owner preview files metadata contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableContractJson -Response $java
        $pythonStable = ConvertTo-StableContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            filePaths = @($python.data | ForEach-Object { $_.filePath })
        }
    }

    $anonymousPendingStatus = [ordered]@{
        java = Invoke-HttpStatusWithHeaders "$JavaUrl$pendingPath"
        python = Invoke-HttpStatusWithHeaders "$PythonUrl$pendingPath"
        proxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$pendingPath"
        proxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($pendingPath -replace '^/api/v1/', '/api/web/')"
    }

    $anonymousPublished = $caseResults | Where-Object { $_.name -eq 'anonymousPublishedFiles' } | Select-Object -First 1
    $ownerPending = $caseResults | Where-Object { $_.name -eq 'ownerPendingFiles' } | Select-Object -First 1
    $shape = [ordered]@{
        anonymousPublishedFilesSorted = (@($anonymousPublished.filePaths) -join ',') -eq 'README.md,SKILL.md'
        ownerPendingFilesSorted = (@($ownerPending.filePaths) -join ',') -eq 'SKILL.md,src/pending.py'
        anonymousPendingStatusesMatch = (
            $anonymousPendingStatus.java -eq $anonymousPendingStatus.python -and
            $anonymousPendingStatus.python -eq $anonymousPendingStatus.proxyV1 -and
            $anonymousPendingStatus.python -eq $anonymousPendingStatus.proxyWeb
        )
    }

    $result = [ordered]@{
        cases = $caseResults
        anonymousPendingStatus = $anonymousPendingStatus
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-files-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview files metadata contracts differ. See .dev/owner-preview-files-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview files metadata does not match Python. See .dev/owner-preview-files-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview files metadata does not match Python. See .dev/owner-preview-files-contract-result.json.'
    }
    if (-not $result.shape.anonymousPublishedFilesSorted -or
        -not $result.shape.ownerPendingFilesSorted -or
        -not $result.shape.anonymousPendingStatusesMatch) {
        throw 'Owner preview files metadata shape check failed. See .dev/owner-preview-files-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewFilesSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewFilesContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewTagFilesContractFixture {
    $objects = @{
        'fixtures/owner-preview-tag-files/1.0.0/SKILL.md' = '# Owner preview tag files published fixture'
        'fixtures/owner-preview-tag-files/1.0.0/README.md' = '# Published tag file metadata'
        'fixtures/owner-preview-tag-files/1.1.0/SKILL.md' = '# Owner preview tag files pending fixture'
        'fixtures/owner-preview-tag-files/1.1.0/src/pending.py' = 'print("pending tag owner preview")'
    }

    foreach ($entry in $objects.GetEnumerator()) {
        $relativePath = $entry.Key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        Set-Content -LiteralPath $targetPath -Value $entry.Value
    }

    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    pending_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-tag-files-team', 'Codex Owner Tag Files Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-tag-files-20260608', 'Codex Owner Tag Files Skill',
        'Owner preview tag file metadata fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner tag files published fixture',
        jsonb_build_object('name', 'owner-tag-files', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'README.md'), jsonb_build_object('path', 'SKILL.md')),
        2, 210, '2026-06-08T05:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T05:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'owner tag files pending fixture',
        jsonb_build_object('name', 'owner-tag-files', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/pending.py')),
        2, 310, NULL, local_user_id, '2026-06-08T05:20:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (published_version_id, pending_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (published_version_id, 'README.md', 90, 'text/markdown', repeat('a', 64), 'fixtures/owner-preview-tag-files/1.0.0/README.md'),
        (published_version_id, 'SKILL.md', 120, 'text/markdown', repeat('b', 64), 'fixtures/owner-preview-tag-files/1.0.0/SKILL.md'),
        (pending_version_id, 'SKILL.md', 140, 'text/markdown', repeat('c', 64), 'fixtures/owner-preview-tag-files/1.1.0/SKILL.md'),
        (pending_version_id, 'src/pending.py', 170, 'text/x-python', repeat('d', 64), 'fixtures/owner-preview-tag-files/1.1.0/src/pending.py');

    INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
    VALUES
        (fixture_skill_id, 'stable', published_version_id, local_user_id),
        (fixture_skill_id, 'preview', pending_version_id, local_user_id)
    ON CONFLICT (skill_id, tag_name) DO UPDATE
        SET version_id = EXCLUDED.version_id,
            updated_at = CURRENT_TIMESTAMP;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewTagFilesContractComparison {
    Ensure-OwnerPreviewTagFilesContractFixture

    $basePath = '/api/v1/skills/codex-owner-tag-files-team/codex-owner-tag-files-20260608'
    $publishedPath = "$basePath/tags/stable/files"
    $pendingPath = "$basePath/tags/preview/files"
    $publishedCases = @(
        [ordered]@{ name = 'anonymousPublishedTagFiles'; path = $publishedPath; headers = @{} },
        [ordered]@{ name = 'ownerPublishedTagFiles'; path = $publishedPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPublishedTagFiles'; path = $publishedPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )
    $pendingStatusCases = @(
        [ordered]@{ name = 'anonymousPendingTagFiles'; path = $pendingPath; headers = @{} },
        [ordered]@{ name = 'ownerPendingTagFiles'; path = $pendingPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPendingTagFiles'; path = $pendingPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $publishedResults = @()
    foreach ($case in $publishedCases) {
        Write-Host "Comparing owner preview tag files contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableContractJson -Response $java
        $pythonStable = ConvertTo-StableContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableContractJson -Response $proxyWeb

        $publishedResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            filePaths = @($python.data | ForEach-Object { $_.filePath })
        }
    }

    $pendingResults = @()
    foreach ($case in $pendingStatusCases) {
        Write-Host "Comparing owner preview tag files rejection contract: $($case.name)"
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $statuses = [ordered]@{
            java = Invoke-HttpStatusWithHeaders "$JavaUrl$($case.path)" -Headers $case.headers
            python = Invoke-HttpStatusWithHeaders "$PythonUrl$($case.path)" -Headers $case.headers
            proxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$($case.path)" -Headers $case.headers
            proxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$proxyWebPath" -Headers $case.headers
        }
        $pendingResults += [ordered]@{
            name = $case.name
            statuses = $statuses
            statusesMatch = (
                $statuses.java -eq $statuses.python -and
                $statuses.python -eq $statuses.proxyV1 -and
                $statuses.python -eq $statuses.proxyWeb
            )
        }
    }

    $anonymousPublished = $publishedResults | Where-Object { $_.name -eq 'anonymousPublishedTagFiles' } | Select-Object -First 1
    $shape = [ordered]@{
        publishedFilesSorted = (@($anonymousPublished.filePaths) -join ',') -eq 'README.md,SKILL.md'
        allPendingStatusesMatch = -not [bool]($pendingResults | Where-Object { -not $_.statusesMatch })
        allPendingRejected = -not [bool]($pendingResults | Where-Object { $_.statuses.java -ne 400 })
    }

    $result = [ordered]@{
        publishedCases = $publishedResults
        pendingStatusCases = $pendingResults
        allJavaMatchesPython = -not [bool]($publishedResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($publishedResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($publishedResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-tag-files-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview tag files metadata contracts differ. See .dev/owner-preview-tag-files-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview tag files metadata does not match Python. See .dev/owner-preview-tag-files-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview tag files metadata does not match Python. See .dev/owner-preview-tag-files-contract-result.json.'
    }
    if (-not $result.shape.publishedFilesSorted -or
        -not $result.shape.allPendingStatusesMatch -or
        -not $result.shape.allPendingRejected) {
        throw 'Owner preview tag files metadata shape check failed. See .dev/owner-preview-tag-files-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewTagFilesSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewTagFilesContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HttpContentContract {
    param(
        [string]$Url,
        [hashtable]$Headers = @{}
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $Url)
        foreach ($header in $Headers.GetEnumerator()) {
            $request.Headers.Add([string]$header.Key, [string]$header.Value)
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $contentType = ''
        if ($response.Content.Headers.ContentType) {
            $contentType = $response.Content.Headers.ContentType.MediaType
        }
        return [ordered]@{
            status = [int]$response.StatusCode
            contentType = $contentType
            bodyBase64 = [System.Convert]::ToBase64String($bytes)
            byteLength = $bytes.Length
        }
    } finally {
        $client.Dispose()
    }
}

function Ensure-FileContentContractFixture {
    $objects = @(
        [ordered]@{ key = 'fixtures/file-content/1.0.0/README.md'; bytes = [System.Text.Encoding]::UTF8.GetBytes("# Published file content`n") },
        [ordered]@{ key = 'fixtures/file-content/1.0.0/bin.dat'; bytes = [byte[]](0, 1, 2, 3, 255) },
        [ordered]@{ key = 'fixtures/file-content/1.1.0/SKILL.md'; bytes = [System.Text.Encoding]::UTF8.GetBytes("# Pending file content`n") },
        [ordered]@{ key = 'fixtures/file-content/1.1.0/src/pending.py'; bytes = [System.Text.Encoding]::UTF8.GetBytes("print('pending file content')`n") }
    )

    foreach ($entry in $objects) {
        $relativePath = $entry.key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        [System.IO.File]::WriteAllBytes($targetPath, $entry.bytes)
    }

    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    pending_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-file-content-team', 'Codex File Content Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-file-content-20260608', 'Codex File Content Skill',
        'File content contract fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'file content published fixture',
        jsonb_build_object('name', 'file-content', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'README.md'), jsonb_build_object('path', 'bin.dat')),
        2, 30, '2026-06-08T06:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T06:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'file content pending fixture',
        jsonb_build_object('name', 'file-content', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/pending.py')),
        2, 50, NULL, local_user_id, '2026-06-08T06:20:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (published_version_id, pending_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (published_version_id, 'README.md', 25, 'text/markdown', repeat('a', 64), 'fixtures/file-content/1.0.0/README.md'),
        (published_version_id, 'bin.dat', 5, 'application/octet-stream', repeat('b', 64), 'fixtures/file-content/1.0.0/bin.dat'),
        (pending_version_id, 'SKILL.md', 23, 'text/markdown', repeat('c', 64), 'fixtures/file-content/1.1.0/SKILL.md'),
        (pending_version_id, 'src/pending.py', 30, 'text/x-python', repeat('d', 64), 'fixtures/file-content/1.1.0/src/pending.py');

    INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
    VALUES
        (fixture_skill_id, 'stable', published_version_id, local_user_id),
        (fixture_skill_id, 'preview', pending_version_id, local_user_id)
    ON CONFLICT (skill_id, tag_name) DO UPDATE
        SET version_id = EXCLUDED.version_id,
            updated_at = CURRENT_TIMESTAMP;
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-FileContentContractComparison {
    Ensure-FileContentContractFixture

    $basePath = '/api/v1/skills/codex-file-content-team/codex-file-content-20260608'
    $contentCases = @(
        [ordered]@{ name = 'anonymousPublishedVersionText'; path = "$basePath/versions/1.0.0/file?path=README.md"; headers = @{} },
        [ordered]@{ name = 'anonymousPublishedVersionBinary'; path = "$basePath/versions/1.0.0/file?path=bin.dat"; headers = @{} },
        [ordered]@{ name = 'ownerPendingVersionText'; path = "$basePath/versions/1.1.0/file?path=SKILL.md"; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPendingVersionText'; path = "$basePath/versions/1.1.0/file?path=SKILL.md"; headers = @{ 'X-Mock-User-Id' = 'local-admin' } },
        [ordered]@{ name = 'anonymousPublishedTagText'; path = "$basePath/tags/stable/file?path=README.md"; headers = @{} },
        [ordered]@{ name = 'ownerPublishedTagText'; path = "$basePath/tags/stable/file?path=README.md"; headers = @{ 'X-Mock-User-Id' = 'local-user' } }
    )
    $statusCases = @(
        [ordered]@{ name = 'anonymousPendingVersionStatus'; path = "$basePath/versions/1.1.0/file?path=SKILL.md"; headers = @{} },
        [ordered]@{ name = 'ownerPendingTagStatus'; path = "$basePath/tags/preview/file?path=SKILL.md"; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPendingTagStatus'; path = "$basePath/tags/preview/file?path=SKILL.md"; headers = @{ 'X-Mock-User-Id' = 'local-admin' } },
        [ordered]@{ name = 'missingFileStatus'; path = "$basePath/versions/1.0.0/file?path=missing.md"; headers = @{} }
    )

    $contentResults = @()
    foreach ($case in $contentCases) {
        Write-Host "Comparing file content contract: $($case.name)"
        $java = Invoke-HttpContentContract "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-HttpContentContract "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-HttpContentContract "$WebUrl$($case.path)" -Headers $case.headers

        $contentResults += [ordered]@{
            name = $case.name
            javaMatchesPython = (($java | ConvertTo-Json -Depth 10) -eq ($python | ConvertTo-Json -Depth 10))
            pythonMatchesProxyV1 = (($python | ConvertTo-Json -Depth 10) -eq ($proxyV1 | ConvertTo-Json -Depth 10))
            java = $java
            python = $python
            proxyV1 = $proxyV1
        }
    }

    $statusResults = @()
    foreach ($case in $statusCases) {
        Write-Host "Comparing file content rejection contract: $($case.name)"
        $java = Invoke-HttpContentContract "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-HttpContentContract "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-HttpContentContract "$WebUrl$($case.path)" -Headers $case.headers
        $statusResults += [ordered]@{
            name = $case.name
            java = $java.status
            python = $python.status
            proxyV1 = $proxyV1.status
            statusesMatch = ($java.status -eq $python.status -and $python.status -eq $proxyV1.status)
        }
    }

    $result = [ordered]@{
        contentCases = $contentResults
        statusCases = $statusResults
        allJavaMatchesPython = -not [bool]($contentResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($contentResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allStatusesMatch = -not [bool]($statusResults | Where-Object { -not $_.statusesMatch })
        allExpectedRejections = -not [bool]($statusResults | Where-Object { $_.java -ne 400 })
        comparedFields = @('status', 'contentType', 'bodyBase64', 'byteLength')
    }

    $resultPath = Join-Path $DevDir 'file-content-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python file content contracts differ. See .dev/file-content-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 file content does not match Python. See .dev/file-content-contract-result.json.'
    }
    if (-not $result.allStatusesMatch -or -not $result.allExpectedRejections) {
        throw 'File content rejection status check failed. See .dev/file-content-contract-result.json.'
    }
}

function Invoke-HybridFileContentSmokeVerification {
    try {
        Start-Hybrid
        Invoke-FileContentContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Write-ZipFile {
    param(
        [string]$Path,
        [hashtable]$Entries
    )

    Add-Type -AssemblyName System.IO.Compression
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    if (Test-Path -LiteralPath $Path) {
        Remove-Item -Force -LiteralPath $Path
    }
    $stream = [System.IO.File]::Open($Path, [System.IO.FileMode]::CreateNew)
    try {
        $zip = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Create)
        try {
            foreach ($entry in $Entries.GetEnumerator() | Sort-Object Name) {
                $zipEntry = $zip.CreateEntry([string]$entry.Key)
                $entryStream = $zipEntry.Open()
                try {
                    $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$entry.Value)
                    $entryStream.Write($bytes, 0, $bytes.Length)
                } finally {
                    $entryStream.Dispose()
                }
            }
        } finally {
            $zip.Dispose()
        }
    } finally {
        $stream.Dispose()
    }
}

function Normalize-DownloadContentType {
    param([string]$ContentType)

    if (-not $ContentType) {
        return ''
    }
    $normalized = $ContentType.ToLowerInvariant()
    if ($normalized -eq 'application/zip' -or $normalized -eq 'application/x-zip-compressed' -or $normalized -eq 'application/octet-stream') {
        return 'application/zip'
    }
    return $normalized
}

function Read-ZipEntriesFromBytes {
    param([byte[]]$Bytes)

    if ($Bytes.Length -eq 0) {
        return @()
    }

    Add-Type -AssemblyName System.IO.Compression
    $stream = [System.IO.MemoryStream]::new($Bytes)
    try {
        $archive = [System.IO.Compression.ZipArchive]::new($stream, [System.IO.Compression.ZipArchiveMode]::Read)
        try {
            $entries = @()
            foreach ($entry in $archive.Entries | Sort-Object FullName) {
                $entryStream = $entry.Open()
                try {
                    $buffer = [System.IO.MemoryStream]::new()
                    try {
                        $entryStream.CopyTo($buffer)
                        $entries += [ordered]@{
                            name = $entry.FullName
                            bodyBase64 = [System.Convert]::ToBase64String($buffer.ToArray())
                        }
                    } finally {
                        $buffer.Dispose()
                    }
                } finally {
                    $entryStream.Dispose()
                }
            }
            return $entries
        } finally {
            $archive.Dispose()
        }
    } catch {
        return @()
    } finally {
        $stream.Dispose()
    }
}

function Test-DownloadContractsMatch {
    param(
        [object]$Left,
        [object]$Right,
        [bool]$CompareZipEntries = $false
    )

    if ($Left.status -ne $Right.status -or
        $Left.location -ne $Right.location -or
        $Left.contentType -ne $Right.contentType -or
        $Left.contentDisposition -ne $Right.contentDisposition) {
        return $false
    }

    if ($CompareZipEntries) {
        return (($Left.zipEntries | ConvertTo-Json -Depth 20 -Compress) -eq ($Right.zipEntries | ConvertTo-Json -Depth 20 -Compress))
    }

    return ($Left.byteLength -eq $Right.byteLength -and $Left.bodyBase64 -eq $Right.bodyBase64)
}

function Invoke-HttpDownloadContract {
    param(
        [string]$Url,
        [hashtable]$Headers = @{},
        [bool]$AllowRedirect = $true
    )

    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $handler.AllowAutoRedirect = $AllowRedirect
    $client = [System.Net.Http.HttpClient]::new($handler)
    try {
        $request = [System.Net.Http.HttpRequestMessage]::new([System.Net.Http.HttpMethod]::Get, $Url)
        foreach ($header in $Headers.GetEnumerator()) {
            $request.Headers.Add([string]$header.Key, [string]$header.Value)
        }
        $response = $client.SendAsync($request).GetAwaiter().GetResult()
        $bytes = $response.Content.ReadAsByteArrayAsync().GetAwaiter().GetResult()
        $contentType = ''
        if ($response.Content.Headers.ContentType) {
            $contentType = $response.Content.Headers.ContentType.MediaType
        }
        $contentDisposition = ''
        if ($response.Content.Headers.ContentDisposition) {
            $contentDisposition = $response.Content.Headers.ContentDisposition.ToString()
        }
        $location = ''
        if ($response.Headers.Location) {
            $location = $response.Headers.Location.ToString()
        }
        return [ordered]@{
            status = [int]$response.StatusCode
            location = $location
            contentType = Normalize-DownloadContentType -ContentType $contentType
            contentDisposition = $contentDisposition
            bodyBase64 = [System.Convert]::ToBase64String($bytes)
            byteLength = $bytes.Length
            zipEntries = Read-ZipEntriesFromBytes -Bytes $bytes
        }
    } finally {
        $client.Dispose()
        $handler.Dispose()
    }
}

function Get-DownloadCounters {
    $sql = @"
SELECT
  s.download_count || ',' ||
  COALESCE((SELECT download_count FROM skill_version_stats WHERE skill_version_id = sv10.id), 0) || ',' ||
  COALESCE((SELECT download_count FROM skill_version_stats WHERE skill_version_id = sv11.id), 0)
FROM skill s
JOIN namespace n ON n.id = s.namespace_id
JOIN skill_version sv10 ON sv10.skill_id = s.id AND sv10.version = '1.0.0'
JOIN skill_version sv11 ON sv11.skill_id = s.id AND sv11.version = '1.1.0'
WHERE n.slug = 'codex-download-team'
  AND s.slug = 'codex-download-20260608'
  AND s.owner_id = 'local-user';
"@
    $raw = Invoke-PostgresScalar -Sql $sql
    $parts = $raw.Split(',')
    return [ordered]@{
        skill = [int64]$parts[0]
        version100 = [int64]$parts[1]
        version110 = [int64]$parts[2]
    }
}

function Ensure-DownloadContractFixture {
    $fallbackObjects = @(
        [ordered]@{ key = 'fixtures/download/1.1.0/SKILL.md'; value = "# Download fallback skill`n" },
        [ordered]@{ key = 'fixtures/download/1.1.0/src/main.py'; value = "print('download fallback')`n" }
    )
    foreach ($entry in $fallbackObjects) {
        $relativePath = $entry.key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        [System.IO.File]::WriteAllBytes($targetPath, [System.Text.Encoding]::UTF8.GetBytes($entry.value))
    }

    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    bundle_version_id BIGINT;
    fallback_version_id BIGINT;
    pending_version_id BIGINT;
    missing_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-download-team', 'Codex Download Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-download-20260608', 'Codex Download Skill',
        'Download contract fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            download_count = 0,
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'download bundle fixture',
        jsonb_build_object('name', 'download-fixture', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '2026-06-08T08:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T08:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO bundle_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PUBLISHED', 'download fallback fixture',
        jsonb_build_object('name', 'download-fixture', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/main.py')),
        2, 200, '2026-06-08T09:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T09:00:00Z'::timestamptz, FALSE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = FALSE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO fallback_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.2.0', 'PENDING_REVIEW', 'download pending fixture',
        jsonb_build_object('name', 'download-fixture', 'version', '1.2.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 120, NULL, local_user_id, '2026-06-08T10:00:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '2.0.0', 'PUBLISHED', 'download missing fixture',
        jsonb_build_object('name', 'download-fixture', 'version', '2.0.0'),
        jsonb_build_array(),
        0, 0, '2026-06-08T11:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T11:00:00Z'::timestamptz, FALSE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            file_count = 0,
            total_size = 0,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = FALSE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO missing_version_id;

    UPDATE skill
    SET latest_version_id = bundle_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (bundle_version_id, fallback_version_id, pending_version_id, missing_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (fallback_version_id, 'SKILL.md', 25, 'text/markdown', repeat('7', 64), 'fixtures/download/1.1.0/SKILL.md'),
        (fallback_version_id, 'src/main.py', 27, 'text/x-python', repeat('8', 64), 'fixtures/download/1.1.0/src/main.py');

    INSERT INTO skill_tag (skill_id, tag_name, version_id, created_by)
    VALUES (fixture_skill_id, 'stable', bundle_version_id, local_user_id)
    ON CONFLICT (skill_id, tag_name) DO UPDATE
        SET version_id = EXCLUDED.version_id,
            updated_at = CURRENT_TIMESTAMP;

    DELETE FROM skill_version_stats
    WHERE skill_id = fixture_skill_id;
END $$;
'@

    Invoke-PostgresSql -Sql $sql

    $idsSql = @"
SELECT s.id || ',' || sv10.id || ',' || sv12.id
FROM skill s
JOIN namespace n ON n.id = s.namespace_id
JOIN skill_version sv10 ON sv10.skill_id = s.id AND sv10.version = '1.0.0'
JOIN skill_version sv12 ON sv12.skill_id = s.id AND sv12.version = '1.2.0'
WHERE n.slug = 'codex-download-team'
  AND s.slug = 'codex-download-20260608'
  AND s.owner_id = 'local-user';
"@
    $ids = (Invoke-PostgresScalar -Sql $idsSql).Split(',')
    $skillId = $ids[0]
    $bundleVersionId = $ids[1]
    $pendingVersionId = $ids[2]

    $bundlePath = Join-Path $JavaStoragePath "packages\$skillId\$bundleVersionId\bundle.zip"
    Write-ZipFile -Path $bundlePath -Entries @{
        'SKILL.md' = "# Download bundle skill`n"
    }
    $pendingBundlePath = Join-Path $JavaStoragePath "packages\$skillId\$pendingVersionId\bundle.zip"
    Write-ZipFile -Path $pendingBundlePath -Entries @{
        'SKILL.md' = "# Download pending skill`n"
    }
}

function Invoke-DownloadContractComparison {
    Ensure-DownloadContractFixture

    $basePath = '/api/v1/skills/codex-download-team/codex-download-20260608'
    $redirectCases = @(
        [ordered]@{ name = 'clawhubPathLatest'; path = '/api/v1/download/codex-download-team--codex-download-20260608'; expectedLocation = "$basePath/download" },
        [ordered]@{ name = 'clawhubPathVersion'; path = '/api/v1/download/codex-download-team--codex-download-20260608?version=1.0.0'; expectedLocation = "$basePath/versions/1.0.0/download" },
        [ordered]@{ name = 'clawhubQueryLatest'; path = '/api/v1/download?slug=codex-download-team--codex-download-20260608&version=latest'; expectedLocation = "$basePath/download" },
        [ordered]@{ name = 'clawhubQueryVersion'; path = '/api/v1/download?slug=codex-download-team--codex-download-20260608&version=1.0.0'; expectedLocation = "$basePath/versions/1.0.0/download" }
    )

    $redirectResults = @()
    foreach ($case in $redirectCases) {
        Write-Host "Comparing download redirect contract: $($case.name)"
        $java = Invoke-HttpDownloadContract "$JavaUrl$($case.path)" -AllowRedirect $false
        $python = Invoke-HttpDownloadContract "$PythonUrl$($case.path)" -AllowRedirect $false
        $proxy = Invoke-HttpDownloadContract "$WebUrl$($case.path)" -AllowRedirect $false
        $redirectResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($java.status -eq $python.status -and $java.location -eq $python.location)
            pythonMatchesProxy = ($python.status -eq $proxy.status -and $python.location -eq $proxy.location)
            expectedLocation = ($python.location -eq $case.expectedLocation)
            java = $java
            python = $python
            proxy = $proxy
        }
    }

    $beforeCounters = Get-DownloadCounters
    $contentCases = @(
        [ordered]@{ name = 'portalLatestBundle'; path = "$basePath/download"; headers = @{} },
        [ordered]@{ name = 'portalExplicitBundle'; path = "$basePath/versions/1.0.0/download"; headers = @{} },
        [ordered]@{ name = 'portalTagBundle'; path = "$basePath/tags/stable/download"; headers = @{} },
        [ordered]@{ name = 'portalFallbackZip'; path = "$basePath/versions/1.1.0/download"; headers = @{} },
        [ordered]@{ name = 'ownerPendingBundle'; path = "$basePath/versions/1.2.0/download"; headers = @{ 'X-Mock-User-Id' = 'local-user' } }
    )

    $contentResults = @()
    foreach ($case in $contentCases) {
        Write-Host "Comparing download stream contract: $($case.name)"
        $java = Invoke-HttpDownloadContract "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-HttpDownloadContract "$PythonUrl$($case.path)" -Headers $case.headers
        $proxy = Invoke-HttpDownloadContract "$WebUrl$($case.path)" -Headers $case.headers
        $compareZipEntries = $case.name -eq 'portalFallbackZip'
        $contentResults += [ordered]@{
            name = $case.name
            javaMatchesPython = Test-DownloadContractsMatch -Left $java -Right $python -CompareZipEntries $compareZipEntries
            pythonMatchesProxy = Test-DownloadContractsMatch -Left $python -Right $proxy -CompareZipEntries $compareZipEntries
            comparedByZipEntries = $compareZipEntries
            java = $java
            python = $python
            proxy = $proxy
        }
    }
    $afterCounters = Get-DownloadCounters

    $statusCases = @(
        [ordered]@{ name = 'missingBundleNoFiles'; path = "$basePath/versions/2.0.0/download"; headers = @{} },
        [ordered]@{ name = 'anonymousPendingRejected'; path = "$basePath/versions/1.2.0/download"; headers = @{} }
    )
    $statusResults = @()
    foreach ($case in $statusCases) {
        Write-Host "Comparing download rejection contract: $($case.name)"
        $java = Invoke-HttpDownloadContract "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-HttpDownloadContract "$PythonUrl$($case.path)" -Headers $case.headers
        $proxy = Invoke-HttpDownloadContract "$WebUrl$($case.path)" -Headers $case.headers
        $statusResults += [ordered]@{
            name = $case.name
            java = $java.status
            python = $python.status
            proxy = $proxy.status
            statusesMatch = ($java.status -eq $python.status -and $python.status -eq $proxy.status)
        }
    }

    $counterDelta = [ordered]@{
        skill = $afterCounters.skill - $beforeCounters.skill
        version100 = $afterCounters.version100 - $beforeCounters.version100
        version110 = $afterCounters.version110 - $beforeCounters.version110
    }
    $expectedCounterDelta = [ordered]@{
        skill = 12
        version100 = 9
        version110 = 3
    }

    $result = [ordered]@{
        redirectCases = $redirectResults
        contentCases = $contentResults
        statusCases = $statusResults
        beforeCounters = $beforeCounters
        afterCounters = $afterCounters
        counterDelta = $counterDelta
        expectedCounterDelta = $expectedCounterDelta
        allRedirectsJavaMatchPython = -not [bool]($redirectResults | Where-Object { -not $_.javaMatchesPython })
        allRedirectsPythonMatchProxy = -not [bool]($redirectResults | Where-Object { -not $_.pythonMatchesProxy })
        allRedirectLocationsExpected = -not [bool]($redirectResults | Where-Object { -not $_.expectedLocation })
        allContentJavaMatchesPython = -not [bool]($contentResults | Where-Object { -not $_.javaMatchesPython })
        allContentPythonMatchesProxy = -not [bool]($contentResults | Where-Object { -not $_.pythonMatchesProxy })
        allStatusesMatch = -not [bool]($statusResults | Where-Object { -not $_.statusesMatch })
        countersMatchExpected = (
            $counterDelta.skill -eq $expectedCounterDelta.skill -and
            $counterDelta.version100 -eq $expectedCounterDelta.version100 -and
            $counterDelta.version110 -eq $expectedCounterDelta.version110
        )
        comparedFields = @('status', 'Location', 'Content-Type', 'Content-Disposition', 'byteLength', 'bodyBase64', 'counterDelta')
    }

    $resultPath = Join-Path $DevDir 'download-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allRedirectsJavaMatchPython -or -not $result.allRedirectsPythonMatchProxy -or -not $result.allRedirectLocationsExpected) {
        throw 'Download redirect contract check failed. See .dev/download-contract-result.json.'
    }
    if (-not $result.allContentJavaMatchesPython -or -not $result.allContentPythonMatchesProxy) {
        throw 'Download stream contract check failed. See .dev/download-contract-result.json.'
    }
    if (-not $result.allStatusesMatch) {
        throw 'Download rejection status check failed. See .dev/download-contract-result.json.'
    }
    if (-not $result.countersMatchExpected) {
        throw 'Download counter delta check failed. See .dev/download-contract-result.json.'
    }
}

function Invoke-HybridDownloadSmokeVerification {
    try {
        Start-Hybrid
        Invoke-DownloadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewResolveContractFixture {
    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    pending_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-resolve-team', 'Codex Owner Resolve Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-resolve-20260608', 'Codex Owner Resolve Skill',
        'Owner preview resolve fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner resolve published fixture',
        jsonb_build_object('name', 'owner-resolve', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '2026-06-08T05:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T05:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'owner resolve pending fixture',
        jsonb_build_object('name', 'owner-resolve', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 110, NULL, local_user_id, '2026-06-08T05:20:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (published_version_id, pending_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (published_version_id, 'SKILL.md', 100, 'text/markdown', repeat('5', 64), 'fixtures/owner-preview-resolve/1.0.0/SKILL.md'),
        (pending_version_id, 'SKILL.md', 110, 'text/markdown', repeat('6', 64), 'fixtures/owner-preview-resolve/1.1.0/SKILL.md');
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewResolveContractComparison {
    Ensure-OwnerPreviewResolveContractFixture

    $basePath = '/api/v1/skills/codex-owner-resolve-team/codex-owner-resolve-20260608/resolve'
    $publishedPath = "$basePath`?version=1.0.0"
    $pendingPath = "$basePath`?version=1.1.0"
    $cases = @(
        [ordered]@{ name = 'anonymousPublishedResolve'; path = $publishedPath; headers = @{} },
        [ordered]@{ name = 'ownerPublishedResolve'; path = $publishedPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPublishedResolve'; path = $publishedPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing owner preview resolve contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableContractJson -Response $java
        $pythonStable = ConvertTo-StableContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            version = $python.data.version
            downloadUrl = $python.data.downloadUrl
        }
    }

    $pendingStatus = [ordered]@{
        anonymousJava = Invoke-HttpStatusWithHeaders "$JavaUrl$pendingPath"
        anonymousPython = Invoke-HttpStatusWithHeaders "$PythonUrl$pendingPath"
        anonymousProxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$pendingPath"
        anonymousProxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($pendingPath -replace '^/api/v1/', '/api/web/')"
        ownerJava = Invoke-HttpStatusWithHeaders "$JavaUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        ownerPython = Invoke-HttpStatusWithHeaders "$PythonUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        ownerProxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        ownerProxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($pendingPath -replace '^/api/v1/', '/api/web/')" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        namespaceAdminJava = Invoke-HttpStatusWithHeaders "$JavaUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-admin' }
        namespaceAdminPython = Invoke-HttpStatusWithHeaders "$PythonUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-admin' }
        namespaceAdminProxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$pendingPath" -Headers @{ 'X-Mock-User-Id' = 'local-admin' }
        namespaceAdminProxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($pendingPath -replace '^/api/v1/', '/api/web/')" -Headers @{ 'X-Mock-User-Id' = 'local-admin' }
    }

    $published = $caseResults | Select-Object -First 1
    $shape = [ordered]@{
        publishedVersionResolved = ($published.version -eq '1.0.0')
        publishedDownloadUrlKept = ($published.downloadUrl -eq '/api/v1/skills/codex-owner-resolve-team/codex-owner-resolve-20260608/versions/1.0.0/download')
        anonymousPendingStatusesMatch = (
            $pendingStatus.anonymousJava -eq $pendingStatus.anonymousPython -and
            $pendingStatus.anonymousPython -eq $pendingStatus.anonymousProxyV1 -and
            $pendingStatus.anonymousPython -eq $pendingStatus.anonymousProxyWeb
        )
        ownerPendingStatusesMatch = (
            $pendingStatus.ownerJava -eq $pendingStatus.ownerPython -and
            $pendingStatus.ownerPython -eq $pendingStatus.ownerProxyV1 -and
            $pendingStatus.ownerPython -eq $pendingStatus.ownerProxyWeb
        )
        namespaceAdminPendingStatusesMatch = (
            $pendingStatus.namespaceAdminJava -eq $pendingStatus.namespaceAdminPython -and
            $pendingStatus.namespaceAdminPython -eq $pendingStatus.namespaceAdminProxyV1 -and
            $pendingStatus.namespaceAdminPython -eq $pendingStatus.namespaceAdminProxyWeb
        )
    }

    $result = [ordered]@{
        cases = $caseResults
        pendingStatus = $pendingStatus
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-resolve-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview resolve contracts differ. See .dev/owner-preview-resolve-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview resolve does not match Python. See .dev/owner-preview-resolve-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview resolve does not match Python. See .dev/owner-preview-resolve-contract-result.json.'
    }
    if (-not $result.shape.publishedVersionResolved -or
        -not $result.shape.publishedDownloadUrlKept -or
        -not $result.shape.anonymousPendingStatusesMatch -or
        -not $result.shape.ownerPendingStatusesMatch -or
        -not $result.shape.namespaceAdminPendingStatusesMatch) {
        throw 'Owner preview resolve shape check failed. See .dev/owner-preview-resolve-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewResolveSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewResolveContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Ensure-OwnerPreviewCompareContractFixture {
    $objects = @{
        'fixtures/owner-preview-compare/1.0.0/SKILL.md' = "name: compare`nold`ncommon"
        'fixtures/owner-preview-compare/1.1.0/SKILL.md' = "name: compare`nnew`ncommon"
        'fixtures/owner-preview-compare/1.1.0/README.md' = "# Added preview file"
    }

    foreach ($entry in $objects.GetEnumerator()) {
        $relativePath = $entry.Key -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        Set-Content -LiteralPath $targetPath -Value $entry.Value
    }

    $sql = @'
DO $$
DECLARE
    local_user_id VARCHAR(128) := 'local-user';
    local_admin_id VARCHAR(128) := 'local-admin';
    team_ns_id BIGINT;
    fixture_skill_id BIGINT;
    published_version_id BIGINT;
    pending_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        (local_user_id, 'Local User', 'local-user@example.com', '', 'ACTIVE'),
        (local_admin_id, 'Local Admin', 'local-admin@example.com', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('codex-owner-compare-team', 'Codex Owner Compare Team', 'TEAM', 'ACTIVE', local_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            type = 'TEAM',
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_ns_id, local_user_id, 'OWNER'),
        (team_ns_id, local_admin_id, 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
        SET role = EXCLUDED.role,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, hidden
    )
    VALUES (
        team_ns_id, 'codex-owner-compare-20260608', 'Codex Owner Compare Skill',
        'Owner preview compare fixture', local_user_id, 'PUBLIC', 'ACTIVE',
        0, 0, 0, 0.00, 0, local_user_id, local_user_id, FALSE
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            summary = EXCLUDED.summary,
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            hidden = FALSE,
            updated_by = local_user_id,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'owner compare published fixture',
        jsonb_build_object('name', 'owner-compare', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 24, '2026-06-08T06:00:00Z'::timestamptz, local_user_id,
        '2026-06-08T06:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PUBLISHED',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = EXCLUDED.published_at,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = TRUE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO published_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'PENDING_REVIEW', 'owner compare pending fixture',
        jsonb_build_object('name', 'owner-compare', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'README.md')),
        2, 44, NULL, local_user_id, '2026-06-08T06:20:00Z'::timestamptz,
        TRUE, FALSE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
        SET status = 'PENDING_REVIEW',
            changelog = EXCLUDED.changelog,
            parsed_metadata_json = EXCLUDED.parsed_metadata_json,
            manifest_json = EXCLUDED.manifest_json,
            file_count = EXCLUDED.file_count,
            total_size = EXCLUDED.total_size,
            published_at = NULL,
            created_at = EXCLUDED.created_at,
            bundle_ready = TRUE,
            download_ready = FALSE,
            requested_visibility = 'PUBLIC'
    RETURNING id INTO pending_version_id;

    UPDATE skill
    SET latest_version_id = published_version_id,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = fixture_skill_id;

    DELETE FROM skill_file
    WHERE version_id IN (published_version_id, pending_version_id);

    INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key)
    VALUES
        (published_version_id, 'SKILL.md', 24, 'text/markdown', repeat('7', 64), 'fixtures/owner-preview-compare/1.0.0/SKILL.md'),
        (pending_version_id, 'README.md', 20, 'text/markdown', repeat('8', 64), 'fixtures/owner-preview-compare/1.1.0/README.md'),
        (pending_version_id, 'SKILL.md', 24, 'text/markdown', repeat('9', 64), 'fixtures/owner-preview-compare/1.1.0/SKILL.md');
END $$;
'@

    Invoke-PostgresSql -Sql $sql
}

function Invoke-OwnerPreviewCompareContractComparison {
    Ensure-OwnerPreviewCompareContractFixture

    $basePath = '/api/v1/skills/codex-owner-compare-team/codex-owner-compare-20260608/versions/compare'
    $previewPath = "$basePath`?from=1.0.0&to=1.1.0"
    $samePath = "$basePath`?from=1.0.0&to=1.0.0"
    $cases = @(
        [ordered]@{ name = 'ownerPreviewCompare'; path = $previewPath; headers = @{ 'X-Mock-User-Id' = 'local-user' } },
        [ordered]@{ name = 'namespaceAdminPreviewCompare'; path = $previewPath; headers = @{ 'X-Mock-User-Id' = 'local-admin' } }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Comparing owner preview version compare contract: $($case.name)"
        $java = Invoke-RestMethod "$JavaUrl$($case.path)" -Headers $case.headers
        $python = Invoke-RestMethod "$PythonUrl$($case.path)" -Headers $case.headers
        $proxyV1 = Invoke-RestMethod "$WebUrl$($case.path)" -Headers $case.headers
        $proxyWebPath = $case.path -replace '^/api/v1/', '/api/web/'
        $proxyWeb = Invoke-RestMethod "$WebUrl$proxyWebPath" -Headers $case.headers

        $javaStable = ConvertTo-StableContractJson -Response $java
        $pythonStable = ConvertTo-StableContractJson -Response $python
        $proxyV1Stable = ConvertTo-StableContractJson -Response $proxyV1
        $proxyWebStable = ConvertTo-StableContractJson -Response $proxyWeb

        $caseResults += [ordered]@{
            name = $case.name
            javaMatchesPython = ($javaStable -eq $pythonStable)
            pythonMatchesProxyV1 = ($pythonStable -eq $proxyV1Stable)
            pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
            summary = $python.data.summary
            filePaths = @($python.data.files | ForEach-Object { $_.path })
        }
    }

    $previewStatus = [ordered]@{
        anonymousJava = Invoke-HttpStatusWithHeaders "$JavaUrl$previewPath"
        anonymousPython = Invoke-HttpStatusWithHeaders "$PythonUrl$previewPath"
        anonymousProxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$previewPath"
        anonymousProxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($previewPath -replace '^/api/v1/', '/api/web/')"
    }

    $sameVersionStatus = [ordered]@{
        java = Invoke-HttpStatusWithHeaders "$JavaUrl$samePath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        python = Invoke-HttpStatusWithHeaders "$PythonUrl$samePath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        proxyV1 = Invoke-HttpStatusWithHeaders "$WebUrl$samePath" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
        proxyWeb = Invoke-HttpStatusWithHeaders "$WebUrl$($samePath -replace '^/api/v1/', '/api/web/')" -Headers @{ 'X-Mock-User-Id' = 'local-user' }
    }

    $ownerCase = $caseResults | Where-Object { $_.name -eq 'ownerPreviewCompare' } | Select-Object -First 1
    $shape = [ordered]@{
        previewSummaryMatchesFixture = (
            $ownerCase.summary.totalFiles -eq 2 -and
            $ownerCase.summary.addedFiles -eq 1 -and
            $ownerCase.summary.modifiedFiles -eq 1 -and
            $ownerCase.summary.removedFiles -eq 0
        )
        previewFilesSorted = (@($ownerCase.filePaths) -join ',') -eq 'README.md,SKILL.md'
        anonymousPreviewStatusesMatch = (
            $previewStatus.anonymousJava -eq $previewStatus.anonymousPython -and
            $previewStatus.anonymousPython -eq $previewStatus.anonymousProxyV1 -and
            $previewStatus.anonymousPython -eq $previewStatus.anonymousProxyWeb
        )
        sameVersionStatusesMatch = (
            $sameVersionStatus.java -eq $sameVersionStatus.python -and
            $sameVersionStatus.python -eq $sameVersionStatus.proxyV1 -and
            $sameVersionStatus.python -eq $sameVersionStatus.proxyWeb
        )
    }

    $result = [ordered]@{
        cases = $caseResults
        previewStatus = $previewStatus
        sameVersionStatus = $sameVersionStatus
        allJavaMatchesPython = -not [bool]($caseResults | Where-Object { -not $_.javaMatchesPython })
        allPythonMatchesProxyV1 = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyV1 })
        allPythonMatchesProxyWeb = -not [bool]($caseResults | Where-Object { -not $_.pythonMatchesProxyWeb })
        shape = $shape
        comparedFields = @('code', 'msg', 'data')
    }

    $resultPath = Join-Path $DevDir 'owner-preview-compare-contract-result.json'
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allJavaMatchesPython) {
        throw 'Java and Python owner preview compare contracts differ. See .dev/owner-preview-compare-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyV1) {
        throw 'Vite proxy /api/v1 owner preview compare does not match Python. See .dev/owner-preview-compare-contract-result.json.'
    }
    if (-not $result.allPythonMatchesProxyWeb) {
        throw 'Vite proxy /api/web owner preview compare does not match Python. See .dev/owner-preview-compare-contract-result.json.'
    }
    if (-not $result.shape.previewSummaryMatchesFixture -or
        -not $result.shape.previewFilesSorted -or
        -not $result.shape.anonymousPreviewStatusesMatch -or
        -not $result.shape.sameVersionStatusesMatch) {
        throw 'Owner preview compare shape check failed. See .dev/owner-preview-compare-contract-result.json.'
    }
}

function Invoke-HybridOwnerPreviewCompareSmokeVerification {
    try {
        Start-Hybrid
        Invoke-OwnerPreviewCompareContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-PublishFoundationPackageTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_package.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishFoundationContractComparison {
    param([string]$ResultFileName = 'publish-foundation-contract-result.json')

    $cases = @(
        [ordered]@{ name = 'clawHubRootPublish'; path = '/api/v1/skills'; method = 'POST' },
        [ordered]@{ name = 'legacyPublish'; path = '/api/v1/publish'; method = 'POST' },
        [ordered]@{ name = 'portalV1NamespacePublish'; path = '/api/v1/skills/global/publish'; method = 'POST' },
        [ordered]@{ name = 'portalWebNamespacePublish'; path = '/api/web/skills/global/publish'; method = 'POST' }
    )

    $caseResults = @()
    foreach ($case in $cases) {
        Write-Host "Checking publish route ownership: $($case.method) $($case.path)"
        $javaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$($case.path)" -Method $case.method
        $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$($case.path)" -Method $case.method

        $caseResults += [ordered]@{
            name = $case.name
            method = $case.method
            path = $case.path
            javaStatus = $javaStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaStatus -eq $proxyStatus)
        }
    }

    $result = [ordered]@{
        cases = $caseResults
        allProxyMatchesJava = -not [bool]($caseResults | Where-Object { -not $_.proxyMatchesJava })
        pythonPublishRoutesRemainUnowned = $true
        comparedFields = @('status')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.allProxyMatchesJava) {
        throw "Publish ownership check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridPublishFoundationSmokeVerification {
    try {
        Invoke-PublishFoundationPackageTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-PublishDryRunTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_dry_run.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishStorageFoundationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_storage.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishDbFoundationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_transaction.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishSideEffectsFoundationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_side_effects.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishReplacementFoundationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_replacement.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishTransactionSplitTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_transaction.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishOrchestrationFoundationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_orchestration.py', '-q')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishHttpValidateTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_publish_http_validate.py', 'tests/test_publish_dry_run.py', 'tests/test_publish_package.py', '-q')
    } finally {
        Pop-Location
    }
}

function New-PublishValidateFixtureZip {
    param(
        [string]$SkillName = 'Codex Validate Skill',
        [string]$Version = '1.0.0',
        [string]$FilePrefix = 'publish-validate-fixture'
    )

    $zipPath = Join-Path $DevDir "$FilePrefix.zip"
    $fixtureDir = Join-Path $DevDir $FilePrefix
    if (Test-Path -LiteralPath $fixtureDir) {
        Remove-Item -LiteralPath $fixtureDir -Recurse -Force
    }
    if (Test-Path -LiteralPath $zipPath) {
        Remove-Item -LiteralPath $zipPath -Force
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $fixtureDir 'src') | Out-Null
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $skillMd = @"
---
name: $SkillName
description: Publish fixture for $SkillName
version: $Version
---
# $SkillName
"@
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir 'SKILL.md'), $skillMd, $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir 'src/main.py'), "print('validate')`n", $utf8NoBom)
    $fixtureItems = Get-ChildItem -LiteralPath $fixtureDir
    Compress-Archive -LiteralPath $fixtureItems.FullName -DestinationPath $zipPath -Force
    return $zipPath
}

function Invoke-MultipartPostJson {
    param(
        [string]$Url,
        [string]$FilePath,
        [hashtable]$Headers = @{},
        [string]$Visibility = 'PUBLIC'
    )

    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $client = [System.Net.Http.HttpClient]::new($handler)
    foreach ($key in $Headers.Keys) {
        $client.DefaultRequestHeaders.Remove($key) | Out-Null
        $client.DefaultRequestHeaders.Add($key, [string]$Headers[$key])
    }

    $content = [System.Net.Http.MultipartFormDataContent]::new()
    $fileBytes = [System.IO.File]::ReadAllBytes($FilePath)
    $fileContent = [System.Net.Http.ByteArrayContent]::new($fileBytes)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse('application/zip')
    $content.Add($fileContent, 'file', [System.IO.Path]::GetFileName($FilePath))
    $content.Add([System.Net.Http.StringContent]::new($Visibility), 'visibility')

    try {
        $response = $client.PostAsync($Url, $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsedBody = $null
        if ($body) {
            try {
                $parsedBody = $body | ConvertFrom-Json
            } catch {
                $parsedBody = $body
            }
        }
        return [ordered]@{
            status = [int]$response.StatusCode
            body = $parsedBody
        }
    } finally {
        $content.Dispose()
        $client.Dispose()
    }
}

function New-ClawHubMultipartFixtureDirectory {
    param(
        [string]$SkillName = 'Codex ClawHub Skill',
        [string]$Version = '1.0.0',
        [string]$FilePrefix = 'clawhub-publish-fixture'
    )

    $fixtureDir = Join-Path $DevDir $FilePrefix
    if (Test-Path -LiteralPath $fixtureDir) {
        Remove-Item -LiteralPath $fixtureDir -Recurse -Force
    }

    New-Item -ItemType Directory -Force -Path (Join-Path $fixtureDir 'src') | Out-Null
    $utf8NoBom = [System.Text.UTF8Encoding]::new($false)
    $skillMd = @"
---
name: $SkillName
description: ClawHub multipart fixture for $SkillName
version: $Version
---
# $SkillName
"@
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir 'SKILL.md'), $skillMd, $utf8NoBom)
    [System.IO.File]::WriteAllText((Join-Path $fixtureDir 'src/main.py'), "print('clawhub')`n", $utf8NoBom)
    return $fixtureDir
}

function Add-FilePart {
    param(
        [System.Net.Http.MultipartFormDataContent]$Content,
        [string]$FieldName,
        [string]$Path,
        [string]$FileName,
        [string]$ContentType
    )

    $fileBytes = [System.IO.File]::ReadAllBytes($Path)
    $fileContent = [System.Net.Http.ByteArrayContent]::new($fileBytes)
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse($ContentType)
    $Content.Add($fileContent, $FieldName, $FileName)
}

function Invoke-LegacyPublishPostJson {
    param(
        [string]$Url,
        [string]$FilePath,
        [string]$Namespace,
        [hashtable]$Headers = @{}
    )

    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $client = [System.Net.Http.HttpClient]::new($handler)
    foreach ($key in $Headers.Keys) {
        $client.DefaultRequestHeaders.Remove($key) | Out-Null
        $client.DefaultRequestHeaders.Add($key, [string]$Headers[$key])
    }

    $content = [System.Net.Http.MultipartFormDataContent]::new()
    Add-FilePart -Content $content -FieldName 'file' -Path $FilePath -FileName ([System.IO.Path]::GetFileName($FilePath)) -ContentType 'application/zip'
    $content.Add([System.Net.Http.StringContent]::new($Namespace), 'namespace')
    $content.Add([System.Net.Http.StringContent]::new('true'), 'confirmWarnings')

    try {
        $response = $client.PostAsync($Url, $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsedBody = $null
        if ($body) {
            try {
                $parsedBody = $body | ConvertFrom-Json
            } catch {
                $parsedBody = $body
            }
        }
        return [ordered]@{
            status = [int]$response.StatusCode
            body = $parsedBody
        }
    } finally {
        $content.Dispose()
        $client.Dispose()
    }
}

function Invoke-ClawHubRootPublishPostJson {
    param(
        [string]$Url,
        [string]$FixtureDir,
        [string]$PayloadJson,
        [hashtable]$Headers = @{}
    )

    Add-Type -AssemblyName System.Net.Http
    $handler = [System.Net.Http.HttpClientHandler]::new()
    $client = [System.Net.Http.HttpClient]::new($handler)
    foreach ($key in $Headers.Keys) {
        $client.DefaultRequestHeaders.Remove($key) | Out-Null
        $client.DefaultRequestHeaders.Add($key, [string]$Headers[$key])
    }

    $content = [System.Net.Http.MultipartFormDataContent]::new()
    $content.Add([System.Net.Http.StringContent]::new($PayloadJson), 'payload')
    $content.Add([System.Net.Http.StringContent]::new('true'), 'confirmWarnings')
    Add-FilePart -Content $content -FieldName 'files' -Path (Join-Path $FixtureDir 'SKILL.md') -FileName 'SKILL.md' -ContentType 'text/markdown'
    Add-FilePart -Content $content -FieldName 'files' -Path (Join-Path $FixtureDir 'src/main.py') -FileName 'src/main.py' -ContentType 'text/x-python'

    try {
        $response = $client.PostAsync($Url, $content).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        $parsedBody = $null
        if ($body) {
            try {
                $parsedBody = $body | ConvertFrom-Json
            } catch {
                $parsedBody = $body
            }
        }
        return [ordered]@{
            status = [int]$response.StatusCode
            body = $parsedBody
        }
    } finally {
        $content.Dispose()
        $client.Dispose()
    }
}

function Invoke-PublishHttpValidateContractComparison {
    param([string]$ResultFileName = 'publish-http-validate-contract-result.json')

    $zipPath = New-PublishValidateFixtureZip
    $headers = @{ 'X-Mock-User-Id' = 'local-admin' }
    $path = '/api/cli/v1/skills/global/publish/validate'

    Write-Host "Comparing publish validate route: POST $path"
    $java = Invoke-MultipartPostJson "$JavaUrl$path" -FilePath $zipPath -Headers $headers
    $python = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $zipPath -Headers $headers
    $proxy = Invoke-MultipartPostJson "$WebUrl$path" -FilePath $zipPath -Headers $headers

    $writeCases = @(
        [ordered]@{ name = 'clawHubDelete'; path = '/api/v1/skills/codex-unmigrated-delete'; method = 'DELETE' },
        [ordered]@{ name = 'clawHubUndelete'; path = '/api/v1/skills/codex-unmigrated-delete/undelete'; method = 'POST' }
    )

    $writeResults = @()
    foreach ($case in $writeCases) {
        $javaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$($case.path)" -Method $case.method
        $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$($case.path)" -Method $case.method
        $writeResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaStatus = $javaStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaStatus -eq $proxyStatus)
        }
    }

    $javaData = $java.body.data
    $pythonData = $python.body.data
    $proxyData = $proxy.body.data
    $result = [ordered]@{
        validate = [ordered]@{
            javaStatus = $java.status
            pythonStatus = $python.status
            proxyStatus = $proxy.status
            javaMatchesPython = (
                $java.status -eq $python.status -and
                $java.body.code -eq $python.body.code -and
                $javaData.valid -eq $pythonData.valid -and
                $javaData.resolvedSlug -eq $pythonData.resolvedSlug -and
                $javaData.resolvedVersion -eq $pythonData.resolvedVersion -and
                (@($javaData.errors) -join '|') -eq (@($pythonData.errors) -join '|') -and
                (@($javaData.warnings) -join '|') -eq (@($pythonData.warnings) -join '|')
            )
            pythonMatchesProxy = (
                $python.status -eq $proxy.status -and
                $python.body.code -eq $proxy.body.code -and
                $pythonData.valid -eq $proxyData.valid -and
                $pythonData.resolvedSlug -eq $proxyData.resolvedSlug -and
                $pythonData.resolvedVersion -eq $proxyData.resolvedVersion -and
                (@($pythonData.errors) -join '|') -eq (@($proxyData.errors) -join '|') -and
                (@($pythonData.warnings) -join '|') -eq (@($proxyData.warnings) -join '|')
            )
            java = $java
            python = $python
            proxy = $proxy
        }
        writeRoutes = $writeResults
        unmigratedMutationRoutesRemainJavaOwned = -not [bool]($writeResults | Where-Object { -not $_.proxyMatchesJava })
        comparedFields = @('status', 'code', 'data.valid', 'data.errors', 'data.warnings', 'data.resolvedSlug', 'data.resolvedVersion')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.validate.javaMatchesPython -or -not $result.validate.pythonMatchesProxy -or -not $result.unmigratedMutationRoutesRemainJavaOwned) {
        throw "Publish validate contract check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishScannerHandoffTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scanner_handoff.py',
            'tests/test_publish_orchestration.py',
            'tests/test_publish_side_effects.py',
            'tests/test_publish_http_validate.py',
            'tests/test_config.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishCliReplacementLookupTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_replacement.py',
            'tests/test_publish_http_validate.py',
            'tests/test_publish_orchestration.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishPendingAutoWithdrawTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_auto_withdraw.py',
            'tests/test_publish_orchestration.py',
            'tests/test_publish_http_validate.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishStorageFailureCleanupTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_orchestration.py',
            'tests/test_publish_http_validate.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-CliPublishWriteOwnershipTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_hybrid_makefile.py',
            'tests/test_publish_http_validate.py',
            '-q'
        )
    } finally {
        Pop-Location
    }

    Invoke-WebDeps
    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-PortalPublishWriteOwnershipTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_hybrid_makefile.py',
            'tests/test_publish_http_validate.py',
            '-q'
        )
    } finally {
        Pop-Location
    }

    Invoke-WebDeps
    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-RootLegacyPublishWriteOwnershipTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_hybrid_makefile.py',
            'tests/test_publish_http_validate.py',
            '-q'
        )
    } finally {
        Pop-Location
    }

    Invoke-WebDeps
    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScannerResultProcessingTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scanner_result.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScanTaskWorkerBoundaryTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scan_worker.py',
            'tests/test_publish_scanner_result.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScanConsumerRuntimeTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scan_consumer.py',
            'tests/test_publish_scan_worker.py',
            'tests/test_publish_scanner_result.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScannerHttpClientTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scanner_client.py',
            'tests/test_publish_scan_consumer.py',
            'tests/test_publish_scan_worker.py',
            'tests/test_publish_scanner_result.py',
            'tests/test_config.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScanDaemonSupervisorTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @(
            'run',
            'pytest',
            'tests/test_publish_scan_daemon.py',
            'tests/test_publish_scanner_client.py',
            'tests/test_publish_scan_consumer.py',
            'tests/test_publish_scan_worker.py',
            'tests/test_publish_scanner_result.py',
            'tests/test_config.py',
            'tests/test_hybrid_makefile.py',
            '-q'
        )
    } finally {
        Pop-Location
    }
}

function Invoke-PublishCliWriteDirectContractComparison {
    param([string]$ResultFileName = 'publish-cli-write-direct-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-admin' }
    $path = '/api/cli/v1/skills/global/publish'
    $version = "1.0.$suffix"
    $javaZip = New-PublishValidateFixtureZip -SkillName "Codex Java Write $suffix" -Version $version -FilePrefix "publish-java-write-$suffix"
    $pythonZip = New-PublishValidateFixtureZip -SkillName "Codex Python Write $suffix" -Version $version -FilePrefix "publish-python-write-$suffix"

    Write-Host "Comparing direct publish write route: POST $path"
    $java = Invoke-MultipartPostJson "$JavaUrl$path" -FilePath $javaZip -Headers $headers
    $python = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $pythonZip -Headers $headers
    $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$path" -Method 'POST'
    $javaProxyReferenceStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$path" -Method 'POST'

    $javaData = $java.body.data
    $pythonData = $python.body.data
    $result = [ordered]@{
        directWrite = [ordered]@{
            javaStatus = $java.status
            pythonStatus = $python.status
            javaReferenceSucceeded = ($java.status -eq 200 -and $java.body.code -eq 0)
            pythonSucceeded = ($python.status -eq 200 -and $python.body.code -eq 0)
            stableFieldsMatch = (
                $java.status -eq $python.status -and
                $java.body.code -eq $python.body.code -and
                $javaData.namespace -eq $pythonData.namespace -and
                $javaData.version -eq $pythonData.version -and
                $javaData.visibility -eq $pythonData.visibility
            )
            java = $java
            python = $python
        }
        proxyOwnership = [ordered]@{
            path = $path
            javaStatus = $javaProxyReferenceStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        comparedFields = @('status', 'code', 'data.namespace', 'data.version', 'data.visibility')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.directWrite.javaReferenceSucceeded -or
        -not $result.directWrite.pythonSucceeded -or
        -not $result.directWrite.stableFieldsMatch -or
        -not $result.proxyOwnership.proxyMatchesJava) {
        throw "Publish CLI write direct check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishCliReplacementLookupContractComparison {
    param([string]$ResultFileName = 'publish-cli-replacement-lookup-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $path = '/api/cli/v1/skills/global/publish'
    $version = "1.0.$suffix"
    $skillName = "Codex Replacement $suffix"
    $firstZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $version -FilePrefix "publish-replacement-first-$suffix"
    $secondZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $version -FilePrefix "publish-replacement-second-$suffix"

    Write-Host "Verifying direct publish replacement lookup route: POST $path"
    $first = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $firstZip -Headers $headers
    $slug = $first.body.data.slug
    $firstVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$version' LIMIT 1;"
    $firstBundle = Join-Path $JavaStoragePath "packages\$((Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' LIMIT 1;"))\$firstVersionId\bundle.zip"
    $firstBundleExistsBeforeReplacement = Test-Path -LiteralPath $firstBundle

    $second = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $secondZip -Headers $headers
    $versionCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$version';")
    $remainingVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$version' LIMIT 1;"
    $oldVersionGone = ($remainingVersionId -ne $firstVersionId)
    $oldBundleDeleted = -not (Test-Path -LiteralPath $firstBundle)
    $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$path" -Method 'POST'
    $javaProxyReferenceStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$path" -Method 'POST'

    $result = [ordered]@{
        first = $first
        second = $second
        db = [ordered]@{
            slug = $slug
            version = $version
            firstVersionId = $firstVersionId
            remainingVersionId = $remainingVersionId
            versionCount = $versionCount
            firstBundleExistsBeforeReplacement = $firstBundleExistsBeforeReplacement
            oldBundleDeleted = $oldBundleDeleted
            oldVersionGone = $oldVersionGone
        }
        proxyOwnership = [ordered]@{
            path = $path
            javaStatus = $javaProxyReferenceStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        checks = [ordered]@{
            firstSucceeded = ($first.status -eq 200 -and $first.body.code -eq 0)
            secondSucceeded = ($second.status -eq 200 -and $second.body.code -eq 0)
            sameSlugVersion = (
                $first.body.data.slug -eq $second.body.data.slug -and
                $first.body.data.version -eq $second.body.data.version
            )
            singleVersionRemains = ($versionCount -eq 1)
            oldVersionReplaced = $oldVersionGone
            oldStorageDeleted = ($firstBundleExistsBeforeReplacement -and $oldBundleDeleted)
            proxyStillJavaOwned = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        comparedFields = @('status', 'code', 'data.slug', 'data.version', 'db.versionCount', 'db.oldVersionGone', 'db.oldBundleDeleted')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.firstSucceeded -or
        -not $result.checks.secondSucceeded -or
        -not $result.checks.sameSlugVersion -or
        -not $result.checks.singleVersionRemains -or
        -not $result.checks.oldVersionReplaced -or
        -not $result.checks.oldStorageDeleted -or
        -not $result.checks.proxyStillJavaOwned) {
        throw "Publish CLI replacement lookup check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishPendingAutoWithdrawContractComparison {
    param([string]$ResultFileName = 'publish-pending-auto-withdraw-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $path = '/api/cli/v1/skills/global/publish'
    $skillName = "Codex Pending Withdraw $suffix"
    $firstVersion = "1.0.$suffix"
    $secondVersion = "1.1.$suffix"
    $firstZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $firstVersion -FilePrefix "publish-pending-withdraw-first-$suffix"
    $secondZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $secondVersion -FilePrefix "publish-pending-withdraw-second-$suffix"

    Write-Host "Verifying direct publish pending-review auto-withdraw route: POST $path"
    $first = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $firstZip -Headers $headers
    $slug = $first.body.data.slug
    $firstVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$firstVersion' LIMIT 1;"
    $firstStatusBefore = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $firstVersionId;"
    $reviewTaskCountBefore = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $firstVersionId AND status = 'PENDING';")

    $second = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $secondZip -Headers $headers
    $firstStatusAfter = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $firstVersionId;"
    $reviewTaskCountAfter = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $firstVersionId AND status = 'PENDING';")
    $secondVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$secondVersion' LIMIT 1;"
    $secondStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $secondVersionId;"
    $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$path" -Method 'POST'
    $javaProxyReferenceStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$path" -Method 'POST'

    $result = [ordered]@{
        first = $first
        second = $second
        db = [ordered]@{
            slug = $slug
            firstVersion = $firstVersion
            secondVersion = $secondVersion
            firstVersionId = $firstVersionId
            secondVersionId = $secondVersionId
            firstStatusBefore = $firstStatusBefore
            firstStatusAfter = $firstStatusAfter
            secondStatus = $secondStatus
            reviewTaskCountBefore = $reviewTaskCountBefore
            reviewTaskCountAfter = $reviewTaskCountAfter
        }
        proxyOwnership = [ordered]@{
            path = $path
            javaStatus = $javaProxyReferenceStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        checks = [ordered]@{
            firstSucceeded = ($first.status -eq 200 -and $first.body.code -eq 0)
            secondSucceeded = ($second.status -eq 200 -and $second.body.code -eq 0)
            sameSlug = ($first.body.data.slug -eq $second.body.data.slug)
            firstStartedPendingReview = ($firstStatusBefore -eq 'PENDING_REVIEW')
            firstMovedToUploaded = ($firstStatusAfter -eq 'UPLOADED')
            pendingReviewTaskDeleted = ($reviewTaskCountBefore -gt 0 -and $reviewTaskCountAfter -eq 0)
            secondCreated = -not [string]::IsNullOrWhiteSpace($secondVersionId)
            secondStillPendingReview = ($secondStatus -eq 'PENDING_REVIEW')
            proxyStillJavaOwned = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        comparedFields = @('status', 'code', 'data.slug', 'db.firstStatusBefore', 'db.firstStatusAfter', 'db.reviewTaskCountAfter', 'db.secondStatus')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.firstSucceeded -or
        -not $result.checks.secondSucceeded -or
        -not $result.checks.sameSlug -or
        -not $result.checks.firstStartedPendingReview -or
        -not $result.checks.firstMovedToUploaded -or
        -not $result.checks.pendingReviewTaskDeleted -or
        -not $result.checks.secondCreated -or
        -not $result.checks.secondStillPendingReview -or
        -not $result.checks.proxyStillJavaOwned) {
        throw "Publish pending auto-withdraw check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishStorageFailureCleanupContractComparison {
    param([string]$ResultFileName = 'publish-storage-failure-cleanup-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $path = '/api/cli/v1/skills/global/publish'
    $version = "1.0.$suffix"
    $skillName = "Codex Storage Failure $suffix"
    $zipPath = New-PublishValidateFixtureZip -SkillName $skillName -Version $version -FilePrefix "publish-storage-failure-$suffix"
    $expectedSlug = "codex-storage-failure-$suffix"

    Write-Host "Verifying Python publish storage failure rollback route: POST $path"
    $python = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $zipPath -Headers $headers

    $skillCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$expectedSlug' AND s.owner_id = 'local-user';")
    $versionCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$expectedSlug' AND s.owner_id = 'local-user';")
    $fileCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM skill_file sf JOIN skill_version sv ON sv.id = sf.version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$expectedSlug' AND s.owner_id = 'local-user';")
    $reviewTaskCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$expectedSlug' AND s.owner_id = 'local-user';")
    $securityAuditCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM security_audit sa JOIN skill_version sv ON sv.id = sa.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$expectedSlug' AND s.owner_id = 'local-user';")
    $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$path" -Method 'POST'
    $javaProxyReferenceStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$path" -Method 'POST'

    $result = [ordered]@{
        python = $python
        expectedSlug = $expectedSlug
        db = [ordered]@{
            skillCount = $skillCount
            versionCount = $versionCount
            fileCount = $fileCount
            reviewTaskCount = $reviewTaskCount
            securityAuditCount = $securityAuditCount
        }
        proxyOwnership = [ordered]@{
            path = $path
            javaStatus = $javaProxyReferenceStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        checks = [ordered]@{
            pythonFailed = ($python.status -ge 500)
            skillRolledBack = ($skillCount -eq 0)
            versionRolledBack = ($versionCount -eq 0)
            filesRolledBack = ($fileCount -eq 0)
            reviewTasksRolledBack = ($reviewTaskCount -eq 0)
            securityAuditsRolledBack = ($securityAuditCount -eq 0)
            proxyStillJavaOwned = ($javaProxyReferenceStatus -eq $proxyStatus)
        }
        comparedFields = @('status', 'db.skillCount', 'db.versionCount', 'db.fileCount', 'db.reviewTaskCount', 'db.securityAuditCount')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.pythonFailed -or
        -not $result.checks.skillRolledBack -or
        -not $result.checks.versionRolledBack -or
        -not $result.checks.filesRolledBack -or
        -not $result.checks.reviewTasksRolledBack -or
        -not $result.checks.securityAuditsRolledBack -or
        -not $result.checks.proxyStillJavaOwned) {
        throw "Publish storage failure rollback check failed. See .dev/$ResultFileName."
    }
}

function Invoke-CliPublishWriteOwnershipContractComparison {
    param([string]$ResultFileName = 'cli-publish-write-ownership-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $path = '/api/cli/v1/skills/global/publish'
    $sameVersion = "1.0.$suffix"
    $nextVersion = "1.1.$suffix"
    $skillName = "Codex Proxy Publish $suffix"
    $firstZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $sameVersion -FilePrefix "cli-proxy-publish-first-$suffix"
    $replacementZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $sameVersion -FilePrefix "cli-proxy-publish-replacement-$suffix"
    $nextZip = New-PublishValidateFixtureZip -SkillName $skillName -Version $nextVersion -FilePrefix "cli-proxy-publish-next-$suffix"

    Write-Host "Verifying CLI publish write ownership through Vite proxy: POST $path"
    $first = Invoke-MultipartPostJson "$WebUrl$path" -FilePath $firstZip -Headers $headers
    $slug = $first.body.data.slug
    $firstVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$sameVersion' LIMIT 1;"
    $firstBundle = Join-Path $JavaStoragePath "packages\$((Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' LIMIT 1;"))\$firstVersionId\bundle.zip"
    $firstBundleExistsBeforeReplacement = Test-Path -LiteralPath $firstBundle

    $replacement = Invoke-MultipartPostJson "$WebUrl$path" -FilePath $replacementZip -Headers $headers
    $sameVersionCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$sameVersion';")
    $replacementVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$sameVersion' LIMIT 1;"
    $replacementStatusBeforeNext = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $replacementVersionId;"
    $replacementReviewTaskCountBeforeNext = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $replacementVersionId AND status = 'PENDING';")
    $oldBundleDeleted = -not (Test-Path -LiteralPath $firstBundle)

    $next = Invoke-MultipartPostJson "$WebUrl$path" -FilePath $nextZip -Headers $headers
    $replacementStatusAfterNext = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $replacementVersionId;"
    $replacementReviewTaskCountAfterNext = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $replacementVersionId AND status = 'PENDING';")
    $nextVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND s.owner_id = 'local-user' AND sv.version = '$nextVersion' LIMIT 1;"
    $nextStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $nextVersionId;"

    $javaOwnedCases = @(
        [ordered]@{ name = 'clawHubDelete'; path = '/api/v1/skills/codex-unmigrated-delete'; method = 'DELETE' },
        [ordered]@{ name = 'clawHubUndelete'; path = '/api/v1/skills/codex-unmigrated-delete/undelete'; method = 'POST' }
    )
    $javaOwnedResults = @()
    foreach ($case in $javaOwnedCases) {
        $javaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$($case.path)" -Method $case.method
        $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$($case.path)" -Method $case.method
        $javaOwnedResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaStatus = $javaStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaStatus -eq $proxyStatus)
        }
    }

    $result = [ordered]@{
        first = $first
        replacement = $replacement
        next = $next
        db = [ordered]@{
            slug = $slug
            sameVersion = $sameVersion
            nextVersion = $nextVersion
            firstVersionId = $firstVersionId
            replacementVersionId = $replacementVersionId
            nextVersionId = $nextVersionId
            sameVersionCount = $sameVersionCount
            firstBundleExistsBeforeReplacement = $firstBundleExistsBeforeReplacement
            oldBundleDeleted = $oldBundleDeleted
            replacementStatusBeforeNext = $replacementStatusBeforeNext
            replacementStatusAfterNext = $replacementStatusAfterNext
            replacementReviewTaskCountBeforeNext = $replacementReviewTaskCountBeforeNext
            replacementReviewTaskCountAfterNext = $replacementReviewTaskCountAfterNext
            nextStatus = $nextStatus
        }
        javaOwnedRoutes = $javaOwnedResults
        checks = [ordered]@{
            firstProxyPublishSucceeded = ($first.status -eq 200 -and $first.body.code -eq 0)
            replacementProxyPublishSucceeded = ($replacement.status -eq 200 -and $replacement.body.code -eq 0)
            nextProxyPublishSucceeded = ($next.status -eq 200 -and $next.body.code -eq 0)
            sameSlugVersionReplaced = (
                $first.body.data.slug -eq $replacement.body.data.slug -and
                $first.body.data.version -eq $replacement.body.data.version -and
                $sameVersionCount -eq 1 -and
                $replacementVersionId -ne $firstVersionId
            )
            oldStorageDeleted = ($firstBundleExistsBeforeReplacement -and $oldBundleDeleted)
            pendingVersionAutoWithdrawn = (
                $replacementStatusBeforeNext -eq 'PENDING_REVIEW' -and
                $replacementStatusAfterNext -eq 'UPLOADED' -and
                $replacementReviewTaskCountBeforeNext -gt 0 -and
                $replacementReviewTaskCountAfterNext -eq 0
            )
            nextVersionPendingReview = ($nextStatus -eq 'PENDING_REVIEW')
            unmigratedMutationRoutesRemainJavaOwned = -not [bool]($javaOwnedResults | Where-Object { -not $_.proxyMatchesJava })
        }
        scannerResultBoundary = 'Scanner handoff is covered by Redis stream tests. Scanner result consumption remains a separate milestone.'
        comparedFields = @('status', 'code', 'data.slug', 'data.version', 'db.sameVersionCount', 'db.replacementStatusAfterNext', 'db.nextStatus')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.firstProxyPublishSucceeded -or
        -not $result.checks.replacementProxyPublishSucceeded -or
        -not $result.checks.nextProxyPublishSucceeded -or
        -not $result.checks.sameSlugVersionReplaced -or
        -not $result.checks.oldStorageDeleted -or
        -not $result.checks.pendingVersionAutoWithdrawn -or
        -not $result.checks.nextVersionPendingReview -or
        -not $result.checks.unmigratedMutationRoutesRemainJavaOwned) {
        throw "CLI publish write ownership check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PortalPublishWriteOwnershipContractComparison {
    param([string]$ResultFileName = 'portal-publish-write-ownership-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $v1Path = '/api/v1/skills/global/publish'
    $webPath = '/api/web/skills/global/publish'
    $v1Version = "1.0.$suffix"
    $webVersion = "1.1.$suffix"
    $v1SkillName = "Codex Portal V1 $suffix"
    $webSkillName = "Codex Portal Web $suffix"
    $v1Zip = New-PublishValidateFixtureZip -SkillName $v1SkillName -Version $v1Version -FilePrefix "portal-v1-publish-$suffix"
    $webZip = New-PublishValidateFixtureZip -SkillName $webSkillName -Version $webVersion -FilePrefix "portal-web-publish-$suffix"

    Write-Host "Verifying portal publish write ownership through Vite proxy"
    $v1 = Invoke-MultipartPostJson "$WebUrl$v1Path" -FilePath $v1Zip -Headers $headers
    $web = Invoke-MultipartPostJson "$WebUrl$webPath" -FilePath $webZip -Headers $headers

    $v1Slug = $v1.body.data.slug
    $webSlug = $web.body.data.slug
    $v1VersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$v1Slug' AND s.owner_id = 'local-user' AND sv.version = '$v1Version' LIMIT 1;"
    $webVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$webSlug' AND s.owner_id = 'local-user' AND sv.version = '$webVersion' LIMIT 1;"
    $v1Status = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $v1VersionId;"
    $webStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $webVersionId;"
    $v1ReviewTaskCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $v1VersionId AND status = 'PENDING';")
    $webReviewTaskCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $webVersionId AND status = 'PENDING';")

    $javaOwnedCases = @(
        [ordered]@{ name = 'clawHubDelete'; path = '/api/v1/skills/codex-unmigrated-delete'; method = 'DELETE' },
        [ordered]@{ name = 'clawHubUndelete'; path = '/api/v1/skills/codex-unmigrated-delete/undelete'; method = 'POST' }
    )
    $javaOwnedResults = @()
    foreach ($case in $javaOwnedCases) {
        $javaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$($case.path)" -Method $case.method
        $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$($case.path)" -Method $case.method
        $javaOwnedResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaStatus = $javaStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaStatus -eq $proxyStatus)
        }
    }

    $result = [ordered]@{
        v1 = $v1
        web = $web
        db = [ordered]@{
            v1Slug = $v1Slug
            webSlug = $webSlug
            v1Version = $v1Version
            webVersion = $webVersion
            v1VersionId = $v1VersionId
            webVersionId = $webVersionId
            v1Status = $v1Status
            webStatus = $webStatus
            v1ReviewTaskCount = $v1ReviewTaskCount
            webReviewTaskCount = $webReviewTaskCount
        }
        javaOwnedRoutes = $javaOwnedResults
        checks = [ordered]@{
            v1ProxyPublishSucceeded = ($v1.status -eq 200 -and $v1.body.code -eq 0)
            webProxyPublishSucceeded = ($web.status -eq 200 -and $web.body.code -eq 0)
            v1VersionCreated = -not [string]::IsNullOrWhiteSpace($v1VersionId)
            webVersionCreated = -not [string]::IsNullOrWhiteSpace($webVersionId)
            v1PendingReview = ($v1Status -eq 'PENDING_REVIEW' -and $v1ReviewTaskCount -eq 1)
            webPendingReview = ($webStatus -eq 'PENDING_REVIEW' -and $webReviewTaskCount -eq 1)
            unmigratedMutationRoutesRemainJavaOwned = -not [bool]($javaOwnedResults | Where-Object { -not $_.proxyMatchesJava })
        }
        comparedFields = @('status', 'code', 'data.slug', 'data.version', 'db.v1Status', 'db.webStatus')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.v1ProxyPublishSucceeded -or
        -not $result.checks.webProxyPublishSucceeded -or
        -not $result.checks.v1VersionCreated -or
        -not $result.checks.webVersionCreated -or
        -not $result.checks.v1PendingReview -or
        -not $result.checks.webPendingReview -or
        -not $result.checks.unmigratedMutationRoutesRemainJavaOwned) {
        throw "Portal publish write ownership check failed. See .dev/$ResultFileName."
    }
}

function Invoke-RootLegacyPublishWriteOwnershipContractComparison {
    param([string]$ResultFileName = 'root-legacy-publish-write-ownership-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $legacyPath = '/api/v1/publish'
    $rootPath = '/api/v1/skills'
    $legacyVersion = "1.2.$suffix"
    $rootVersion = "1.3.$suffix"
    $legacyZip = New-PublishValidateFixtureZip -SkillName "Codex Legacy Publish $suffix" -Version $legacyVersion -FilePrefix "legacy-publish-$suffix"
    $rootDir = New-ClawHubMultipartFixtureDirectory -SkillName "Codex Root Publish $suffix" -Version $rootVersion -FilePrefix "root-publish-$suffix"
    $rootPayload = [ordered]@{
        namespace = 'global'
        slug = "codex-root-publish-$suffix"
        displayName = "Codex Root Publish $suffix"
        version = $rootVersion
    } | ConvertTo-Json -Compress

    Write-Host "Verifying root and legacy publish ownership through Vite proxy"
    $legacy = Invoke-LegacyPublishPostJson "$WebUrl$legacyPath" -FilePath $legacyZip -Namespace 'global' -Headers $headers
    $root = Invoke-ClawHubRootPublishPostJson "$WebUrl$rootPath" -FixtureDir $rootDir -PayloadJson $rootPayload -Headers $headers

    $legacyVersionId = [string]$legacy.body.versionId
    $rootVersionId = [string]$root.body.versionId
    $legacyStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $legacyVersionId;"
    $rootStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $rootVersionId;"
    $legacyNamespace = Invoke-PostgresScalar -Sql "SELECT n.slug FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE sv.id = $legacyVersionId;"
    $rootNamespace = Invoke-PostgresScalar -Sql "SELECT n.slug FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE sv.id = $rootVersionId;"
    $legacyReviewTaskCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $legacyVersionId AND status = 'PENDING';")
    $rootReviewTaskCount = [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM review_task WHERE skill_version_id = $rootVersionId AND status = 'PENDING';")

    $javaOwnedCases = @(
        [ordered]@{ name = 'clawHubDelete'; path = '/api/v1/skills/codex-unmigrated-delete'; method = 'DELETE' },
        [ordered]@{ name = 'clawHubUndelete'; path = '/api/v1/skills/codex-unmigrated-delete/undelete'; method = 'POST' }
    )
    $javaOwnedResults = @()
    foreach ($case in $javaOwnedCases) {
        $javaStatus = Invoke-HttpStatusNoRedirect "$JavaUrl$($case.path)" -Method $case.method
        $proxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl$($case.path)" -Method $case.method
        $javaOwnedResults += [ordered]@{
            name = $case.name
            path = $case.path
            javaStatus = $javaStatus
            proxyStatus = $proxyStatus
            proxyMatchesJava = ($javaStatus -eq $proxyStatus)
        }
    }

    $result = [ordered]@{
        legacy = $legacy
        root = $root
        db = [ordered]@{
            legacyVersionId = $legacyVersionId
            rootVersionId = $rootVersionId
            legacyStatus = $legacyStatus
            rootStatus = $rootStatus
            legacyNamespace = $legacyNamespace
            rootNamespace = $rootNamespace
            legacyReviewTaskCount = $legacyReviewTaskCount
            rootReviewTaskCount = $rootReviewTaskCount
        }
        javaOwnedRoutes = $javaOwnedResults
        checks = [ordered]@{
            legacyProxyPublishSucceeded = ($legacy.status -eq 200 -and $legacy.body.ok -eq $true)
            rootProxyPublishSucceeded = ($root.status -eq 200 -and $root.body.ok -eq $true)
            legacyClawHubResponseShape = (
                -not [string]::IsNullOrWhiteSpace($legacyVersionId) -and
                -not [string]::IsNullOrWhiteSpace([string]$legacy.body.skillId)
            )
            rootClawHubResponseShape = (
                -not [string]::IsNullOrWhiteSpace($rootVersionId) -and
                -not [string]::IsNullOrWhiteSpace([string]$root.body.skillId)
            )
            legacyPendingReview = ($legacyStatus -eq 'PENDING_REVIEW' -and $legacyReviewTaskCount -eq 1)
            rootPendingReview = ($rootStatus -eq 'PENDING_REVIEW' -and $rootReviewTaskCount -eq 1)
            namespaceMatches = ($legacyNamespace -eq 'global' -and $rootNamespace -eq 'global')
            unmigratedMutationRoutesRemainJavaOwned = -not [bool]($javaOwnedResults | Where-Object { -not $_.proxyMatchesJava })
        }
        comparedFields = @('status', 'ok', 'skillId', 'versionId', 'db.status', 'db.namespace', 'db.reviewTaskCount')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.legacyProxyPublishSucceeded -or
        -not $result.checks.rootProxyPublishSucceeded -or
        -not $result.checks.legacyClawHubResponseShape -or
        -not $result.checks.rootClawHubResponseShape -or
        -not $result.checks.legacyPendingReview -or
        -not $result.checks.rootPendingReview -or
        -not $result.checks.namespaceMatches -or
        -not $result.checks.unmigratedMutationRoutesRemainJavaOwned) {
        throw "Root and legacy publish write ownership check failed. See .dev/$ResultFileName."
    }
}

function Invoke-ApplyScanResultFixture {
    param(
        [string]$VersionId,
        [string]$ScanId,
        [string]$Verdict,
        [string]$FindingsCount,
        [string]$MaxSeverity,
        [string]$FindingsJson,
        [string]$Duration,
        [string]$ScannerSource = 'fixture'
    )

    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        $env:PYTHONPATH = '.'
        $findingsFile = Join-Path $DevDir "scan-result-findings-$VersionId.json"
        Set-Content -LiteralPath $findingsFile -Value $FindingsJson
        $output = & uv @(
            'run',
            'python',
            'scripts/apply_scan_result_fixture.py',
            '--version-id',
            $VersionId,
            '--scanner-type',
            'skill-scanner',
            '--scan-id',
            $ScanId,
            '--verdict',
            $Verdict,
            '--findings-count',
            $FindingsCount,
            '--max-severity',
            $MaxSeverity,
            '--findings-file',
            $findingsFile,
            '--duration',
            $Duration,
            '--scanner-source',
            $ScannerSource
        )
        if ($LASTEXITCODE -ne 0) {
            throw "Scanner result fixture apply failed with exit code ${LASTEXITCODE}"
        }
        return (($output | Select-Object -Last 1) | ConvertFrom-Json)
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScannerResultProcessingContractComparison {
    param([string]$ResultFileName = 'publish-scanner-result-processing-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $slug = "codex-scan-result-$suffix"
    $sql = @"
DO `$`$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-scan-result-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Scan Result User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by, hidden
    )
    VALUES (
        ns_id, '$slug', 'Codex scan result fixture', 'Fixture for scanner result processing',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, fixture_user_id, fixture_user_id, FALSE
    )
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'SCANNING',
        jsonb_build_object('name', 'scan-result-public', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 10, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PUBLIC'
    );

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.1.0', 'SCANNING',
        jsonb_build_object('name', 'scan-result-private', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 10, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PRIVATE'
    );
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $publicVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.0.0' LIMIT 1;"
    $privateVersionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.1.0' LIMIT 1;"

    Invoke-PostgresSql -Sql "INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at) VALUES ($publicVersionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP), ($privateVersionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);"

    $publicApply = Invoke-ApplyScanResultFixture `
        -VersionId $publicVersionId `
        -ScanId "scan-public-$suffix" `
        -Verdict 'SAFE' `
        -FindingsCount '0' `
        -MaxSeverity 'LOW' `
        -FindingsJson '[]' `
        -Duration '1.25'
    $privateApply = Invoke-ApplyScanResultFixture `
        -VersionId $privateVersionId `
        -ScanId "scan-private-$suffix" `
        -Verdict 'DANGEROUS' `
        -FindingsCount '1' `
        -MaxSeverity 'HIGH' `
        -FindingsJson '[{"rule":"credential","severity":"HIGH"}]' `
        -Duration '2.5'

    $publicStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $publicVersionId;"
    $privateStatus = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $privateVersionId;"
    $publicAudit = Invoke-PostgresScalar -Sql "SELECT scan_id || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $publicVersionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $privateAudit = Invoke-PostgresScalar -Sql "SELECT scan_id || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $privateVersionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $privateFindings = Invoke-PostgresScalar -Sql "SELECT findings::text FROM security_audit WHERE skill_version_id = $privateVersionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"

    $result = [ordered]@{
        publicApply = $publicApply
        privateApply = $privateApply
        db = [ordered]@{
            slug = $slug
            publicVersionId = $publicVersionId
            privateVersionId = $privateVersionId
            publicStatus = $publicStatus
            privateStatus = $privateStatus
            publicAudit = $publicAudit
            privateAudit = $privateAudit
            privateFindings = $privateFindings
        }
        checks = [ordered]@{
            publicMovedToPendingReview = ($publicStatus -eq 'PENDING_REVIEW')
            privateMovedToUploaded = ($privateStatus -eq 'UPLOADED')
            publicApplyMatches = ($publicApply.previousStatus -eq 'SCANNING' -and $publicApply.newStatus -eq 'PENDING_REVIEW' -and $publicApply.statusChanged -eq $true)
            privateApplyMatches = ($privateApply.previousStatus -eq 'SCANNING' -and $privateApply.newStatus -eq 'UPLOADED' -and $privateApply.statusChanged -eq $true)
            publicAuditUpdated = ($publicAudit -eq "scan-public-$suffix|SAFE|true|0|LOW|true")
            privateAuditUpdated = ($privateAudit -eq "scan-private-$suffix|DANGEROUS|false|1|HIGH|true")
            privateFindingsPersisted = ($privateFindings -match '"credential"' -and $privateFindings -match '"HIGH"')
        }
        comparedFields = @('audit.scan_id', 'audit.verdict', 'audit.is_safe', 'audit.findings_count', 'audit.scanned_at', 'version.status')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.publicMovedToPendingReview -or
        -not $result.checks.privateMovedToUploaded -or
        -not $result.checks.publicApplyMatches -or
        -not $result.checks.privateApplyMatches -or
        -not $result.checks.publicAuditUpdated -or
        -not $result.checks.privateAuditUpdated -or
        -not $result.checks.privateFindingsPersisted) {
        throw "Publish scanner result processing check failed. See .dev/$ResultFileName."
    }
}

function Invoke-ProcessScanTaskWorkerFixture {
    param(
        [string]$FieldsFile,
        [string]$StorageBasePath,
        [string]$ScanTempDir,
        [string]$ScanId,
        [string]$Verdict,
        [string]$FindingsCount,
        [string]$MaxSeverity,
        [string]$FindingsJson,
        [string]$Duration,
        [string]$ScannerSource = 'fixture'
    )

    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        $env:PYTHONPATH = '.'
        $findingsFile = Join-Path $DevDir "scan-worker-findings-$ScanId.json"
        Set-Content -LiteralPath $findingsFile -Value $FindingsJson
        $output = & uv @(
            'run',
            'python',
            'scripts/process_scan_task_fixture.py',
            '--fields-file',
            $FieldsFile,
            '--storage-base-path',
            $StorageBasePath,
            '--scan-temp-dir',
            $ScanTempDir,
            '--scan-id',
            $ScanId,
            '--verdict',
            $Verdict,
            '--findings-count',
            $FindingsCount,
            '--max-severity',
            $MaxSeverity,
            '--findings-file',
            $findingsFile,
            '--duration',
            $Duration,
            '--scanner-source',
            $ScannerSource
        )
        if ($LASTEXITCODE -ne 0) {
            throw "Scan task worker fixture failed with exit code ${LASTEXITCODE}"
        }
        return (($output | Select-Object -Last 1) | ConvertFrom-Json)
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScanTaskWorkerBoundaryContractComparison {
    param([string]$ResultFileName = 'publish-scan-task-worker-boundary-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $slug = "codex-scan-worker-$suffix"
    $streamKey = 'skillhub:scan:requests'
    Invoke-RedisCli -Arguments @('DEL', $streamKey) | Out-Null

    $sql = @"
DO `$`$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-scan-worker-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Scan Worker User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by, hidden
    )
    VALUES (
        ns_id, '$slug', 'Codex scan worker fixture', 'Fixture for scan worker boundary',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, fixture_user_id, fixture_user_id, FALSE
    )
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'SCANNING',
        jsonb_build_object('name', 'scan-worker', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 10, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PUBLIC'
    );
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $versionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.0.0' LIMIT 1;"
    $skillId = Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' LIMIT 1;"
    Invoke-PostgresSql -Sql "INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at) VALUES ($versionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);"

    $bundleKey = "packages/$skillId/$versionId/bundle.zip"
    $bundlePath = Join-Path $JavaStoragePath ($bundleKey -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundlePath) | Out-Null
    Set-Content -LiteralPath $bundlePath -Value "scan-worker-bundle-$suffix"

    Invoke-RedisCli -Arguments @(
        'XADD',
        $streamKey,
        '*',
        'taskId',
        "scan-worker-$suffix",
        'versionId',
        $versionId,
        'bundleKey',
        $bundleKey,
        'scannerType',
        'skill-scanner'
    ) | Out-Null
    $entry = Read-RedisStreamFirstEntry -StreamKey $streamKey
    if ($null -eq $entry) {
        throw "No Redis scan worker task was published to $streamKey."
    }

    $fieldsPath = Join-Path $DevDir "scan-worker-fields-$suffix.json"
    $entry.fields | ConvertTo-Json -Depth 10 | Set-Content -LiteralPath $fieldsPath
    $scanTempDir = Join-Path $DevDir 'python-scan-worker-temp'
    $worker = Invoke-ProcessScanTaskWorkerFixture `
        -FieldsFile $fieldsPath `
        -StorageBasePath $JavaStoragePath `
        -ScanTempDir $scanTempDir `
        -ScanId "scan-worker-result-$suffix" `
        -Verdict 'SAFE' `
        -FindingsCount '0' `
        -MaxSeverity 'LOW' `
        -FindingsJson '[]' `
        -Duration '1.75'

    $status = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $versionId;"
    $audit = Invoke-PostgresScalar -Sql "SELECT scan_id || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $tempFiles = @(Get-ChildItem -LiteralPath $scanTempDir -File -ErrorAction SilentlyContinue)

    $result = [ordered]@{
        redis = $entry
        worker = $worker
        db = [ordered]@{
            slug = $slug
            skillId = $skillId
            versionId = $versionId
            status = $status
            audit = $audit
            bundleKey = $bundleKey
            stagedFileCountAfterWorker = $tempFiles.Count
        }
        checks = [ordered]@{
            streamFieldsParsed = ($entry.fields.versionId -eq $versionId -and $entry.fields.bundleKey -eq $bundleKey)
            workerMovedToPendingReview = ($worker.previousStatus -eq 'SCANNING' -and $worker.newStatus -eq 'PENDING_REVIEW' -and $worker.statusChanged -eq $true)
            auditUpdated = ($audit -eq "scan-worker-result-$suffix|SAFE|true|0|LOW|true")
            versionMovedToPendingReview = ($status -eq 'PENDING_REVIEW')
            stagedBundleCleaned = ($tempFiles.Count -eq 0)
        }
        comparedFields = @('redis.versionId', 'redis.bundleKey', 'worker.newStatus', 'audit.scan_id', 'version.status')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.streamFieldsParsed -or
        -not $result.checks.workerMovedToPendingReview -or
        -not $result.checks.auditUpdated -or
        -not $result.checks.versionMovedToPendingReview -or
        -not $result.checks.stagedBundleCleaned) {
        throw "Publish scan task worker boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-ConsumeScanTaskFixture {
    param(
        [string]$StorageBasePath,
        [string]$ScanTempDir,
        [string]$StreamKey,
        [string]$GroupName,
        [string]$ConsumerName,
        [string]$ScanId,
        [string]$Verdict,
        [string]$FindingsCount,
        [string]$MaxSeverity,
        [string]$FindingsJson,
        [string]$Duration,
        [string]$ScannerSource = 'fixture'
    )

    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        $env:PYTHONPATH = '.'
        $findingsFile = Join-Path $DevDir "scan-consumer-findings-$ScanId.json"
        Set-Content -LiteralPath $findingsFile -Value $FindingsJson
        $output = & uv @(
            'run',
            'python',
            'scripts/consume_scan_task_fixture.py',
            '--storage-base-path',
            $StorageBasePath,
            '--scan-temp-dir',
            $ScanTempDir,
            '--stream-key',
            $StreamKey,
            '--group-name',
            $GroupName,
            '--consumer-name',
            $ConsumerName,
            '--scan-id',
            $ScanId,
            '--verdict',
            $Verdict,
            '--findings-count',
            $FindingsCount,
            '--max-severity',
            $MaxSeverity,
            '--findings-file',
            $findingsFile,
            '--duration',
            $Duration,
            '--scanner-source',
            $ScannerSource
        )
        if ($LASTEXITCODE -ne 0) {
            throw "Scan consumer fixture failed with exit code ${LASTEXITCODE}"
        }
        return (($output | Select-Object -Last 1) | ConvertFrom-Json)
    } finally {
        Pop-Location
    }
}

function Invoke-PublishScanConsumerRuntimeContractComparison {
    param([string]$ResultFileName = 'publish-scan-consumer-runtime-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $slug = "codex-scan-consumer-$suffix"
    $streamKey = "skillhub:scan:requests:consumer:$suffix"
    $groupName = "skillhub-scan-workers-$suffix"
    $consumerName = "scanner-python-$suffix"
    Invoke-RedisCli -Arguments @('DEL', $streamKey) | Out-Null

    $sql = @"
DO `$`$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-scan-consumer-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Scan Consumer User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by, hidden
    )
    VALUES (
        ns_id, '$slug', 'Codex scan consumer fixture', 'Fixture for scan consumer runtime',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, fixture_user_id, fixture_user_id, FALSE
    )
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'SCANNING',
        jsonb_build_object('name', 'scan-consumer', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 10, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PUBLIC'
    );
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $versionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.0.0' LIMIT 1;"
    $skillId = Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' LIMIT 1;"
    Invoke-PostgresSql -Sql "INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at) VALUES ($versionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);"

    $bundleKey = "packages/$skillId/$versionId/bundle.zip"
    $bundlePath = Join-Path $JavaStoragePath ($bundleKey -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundlePath) | Out-Null
    Set-Content -LiteralPath $bundlePath -Value "scan-consumer-bundle-$suffix"

    Invoke-RedisCli -Arguments @(
        'XADD',
        $streamKey,
        '*',
        'taskId',
        "scan-consumer-$suffix",
        'versionId',
        $versionId,
        'bundleKey',
        $bundleKey,
        'scannerType',
        'skill-scanner'
    ) | Out-Null

    $scanTempDir = Join-Path $DevDir 'python-scan-consumer-temp'
    $consumer = Invoke-ConsumeScanTaskFixture `
        -StorageBasePath $JavaStoragePath `
        -ScanTempDir $scanTempDir `
        -StreamKey $streamKey `
        -GroupName $groupName `
        -ConsumerName $consumerName `
        -ScanId "scan-consumer-result-$suffix" `
        -Verdict 'SAFE' `
        -FindingsCount '0' `
        -MaxSeverity 'LOW' `
        -FindingsJson '[]' `
        -Duration '1.5'

    $status = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $versionId;"
    $audit = Invoke-PostgresScalar -Sql "SELECT scan_id || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $pending = @(Invoke-RedisCli -Arguments @('XPENDING', $streamKey, $groupName))
    $tempFiles = @(Get-ChildItem -LiteralPath $scanTempDir -File -ErrorAction SilentlyContinue)

    $result = [ordered]@{
        consumer = $consumer
        redis = [ordered]@{
            streamKey = $streamKey
            groupName = $groupName
            pending = $pending
        }
        db = [ordered]@{
            slug = $slug
            skillId = $skillId
            versionId = $versionId
            status = $status
            audit = $audit
            bundleKey = $bundleKey
            stagedFileCountAfterConsumer = $tempFiles.Count
        }
        checks = [ordered]@{
            consumerProcessedOne = ($consumer.processed -eq 1 -and $consumer.acknowledged -eq 1 -and $consumer.retried -eq 0 -and $consumer.failed -eq 0)
            scannerSawOneTask = ($consumer.scannerSeenTasks -eq 1)
            versionMovedToPendingReview = ($status -eq 'PENDING_REVIEW')
            auditUpdated = ($audit -eq "scan-consumer-result-$suffix|SAFE|true|0|LOW|true")
            streamHasNoPending = ($pending.Count -ge 1 -and $pending[0] -eq '0')
            stagedBundleCleaned = ($tempFiles.Count -eq 0)
        }
        comparedFields = @('consumer.processed', 'consumer.acknowledged', 'audit.scan_id', 'version.status', 'redis.pending')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.consumerProcessedOne -or
        -not $result.checks.scannerSawOneTask -or
        -not $result.checks.versionMovedToPendingReview -or
        -not $result.checks.auditUpdated -or
        -not $result.checks.streamHasNoPending -or
        -not $result.checks.stagedBundleCleaned) {
        throw "Publish scan consumer runtime check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishScannerHttpClientContractComparison {
    param([string]$ResultFileName = 'publish-scanner-http-client-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $slug = "codex-scanner-http-$suffix"
    $streamKey = "skillhub:scan:requests:http:$suffix"
    $groupName = "skillhub-scan-workers-http-$suffix"
    $consumerName = "scanner-python-http-$suffix"
    Invoke-RedisCli -Arguments @('DEL', $streamKey) | Out-Null

    $sql = @"
DO `$`$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-scanner-http-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Scanner Http User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by, hidden
    )
    VALUES (
        ns_id, '$slug', 'Codex scanner http fixture', 'Fixture for scanner HTTP client',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, fixture_user_id, fixture_user_id, FALSE
    )
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'SCANNING',
        jsonb_build_object('name', 'scanner-http', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        2, 100, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PUBLIC'
    );
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $versionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.0.0' LIMIT 1;"
    $skillId = Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' LIMIT 1;"
    Invoke-PostgresSql -Sql "INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at) VALUES ($versionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);"

    $bundleKey = "packages/$skillId/$versionId/bundle.zip"
    $bundlePath = Join-Path $JavaStoragePath ($bundleKey -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundlePath) | Out-Null
    $zipPath = New-PublishValidateFixtureZip -SkillName "Codex Scanner Http $suffix" -Version '1.0.0' -FilePrefix "publish-scanner-http-$suffix"
    Copy-Item -LiteralPath $zipPath -Destination $bundlePath -Force

    Invoke-RedisCli -Arguments @(
        'XADD',
        $streamKey,
        '*',
        'taskId',
        "scanner-http-$suffix",
        'versionId',
        $versionId,
        'bundleKey',
        $bundleKey,
        'scannerType',
        'skill-scanner'
    ) | Out-Null

    $scanTempDir = Join-Path $DevDir 'python-scanner-http-temp'
    $consumer = Invoke-ConsumeScanTaskFixture `
        -StorageBasePath $JavaStoragePath `
        -ScanTempDir $scanTempDir `
        -StreamKey $streamKey `
        -GroupName $groupName `
        -ConsumerName $consumerName `
        -ScanId "unused-fixture-$suffix" `
        -Verdict 'SAFE' `
        -FindingsCount '0' `
        -MaxSeverity 'LOW' `
        -FindingsJson '[]' `
        -Duration '1.0' `
        -ScannerSource 'http'

    $status = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $versionId;"
    $audit = Invoke-PostgresScalar -Sql "SELECT scan_id || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $scanId = Invoke-PostgresScalar -Sql "SELECT scan_id FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    $pending = @(Invoke-RedisCli -Arguments @('XPENDING', $streamKey, $groupName))
    $tempFiles = @(Get-ChildItem -LiteralPath $scanTempDir -File -ErrorAction SilentlyContinue)

    $result = [ordered]@{
        consumer = $consumer
        redis = [ordered]@{
            streamKey = $streamKey
            groupName = $groupName
            pending = $pending
        }
        db = [ordered]@{
            slug = $slug
            skillId = $skillId
            versionId = $versionId
            status = $status
            audit = $audit
            scanId = $scanId
            bundleKey = $bundleKey
            stagedFileCountAfterConsumer = $tempFiles.Count
        }
        checks = [ordered]@{
            consumerUsedHttpScanner = ($consumer.scannerSource -eq 'http' -and $consumer.processed -eq 1 -and $consumer.acknowledged -eq 1 -and $consumer.retried -eq 0 -and $consumer.failed -eq 0)
            scannerReturnedRealScanId = (-not [string]::IsNullOrWhiteSpace([string]$scanId) -and $scanId -notlike 'unused-fixture-*')
            versionLeftScanning = ($status -ne 'SCANNING')
            auditUpdated = ($audit -match '\|true\|\d+\|.*\|true$')
            streamHasNoPending = ($pending.Count -ge 1 -and $pending[0] -eq '0')
            stagedBundleCleaned = ($tempFiles.Count -eq 0)
        }
        comparedFields = @('consumer.scannerSource', 'consumer.processed', 'audit.scan_id', 'version.status', 'redis.pending')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.consumerUsedHttpScanner -or
        -not $result.checks.scannerReturnedRealScanId -or
        -not $result.checks.versionLeftScanning -or
        -not $result.checks.auditUpdated -or
        -not $result.checks.streamHasNoPending -or
        -not $result.checks.stagedBundleCleaned) {
        throw "Publish scanner HTTP client check failed. See .dev/$ResultFileName."
    }
}

function Invoke-PublishScanDaemonSupervisorContractComparison {
    param([string]$ResultFileName = 'publish-scan-daemon-supervisor-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $slug = "codex-scan-daemon-$suffix"
    $streamKey = $env:SKILLHUB_SCAN_STREAM_KEY
    $groupName = $env:SKILLHUB_SCAN_CONSUMER_GROUP_NAME

    $sql = @"
DO `$`$
DECLARE
    fixture_user_id VARCHAR(128) := 'codex-scan-daemon-user';
    ns_id BIGINT;
    fixture_skill_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES (fixture_user_id, 'Codex Scan Daemon User', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', fixture_user_id)
    ON CONFLICT (slug) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            status = 'ACTIVE',
            updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status,
        download_count, star_count, rating_avg, rating_count, created_by, updated_by, hidden
    )
    VALUES (
        ns_id, '$slug', 'Codex scan daemon fixture', 'Fixture for scan daemon supervisor',
        fixture_user_id, 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, fixture_user_id, fixture_user_id, FALSE
    )
    RETURNING id INTO fixture_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'SCANNING',
        jsonb_build_object('name', 'scan-daemon', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        2, 100, fixture_user_id, CURRENT_TIMESTAMP, TRUE, TRUE, 'PUBLIC'
    );
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $versionId = Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' AND sv.version = '1.0.0' LIMIT 1;"
    $skillId = Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = 'global' AND s.slug = '$slug' LIMIT 1;"
    Invoke-PostgresSql -Sql "INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at) VALUES ($versionId, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);"

    $bundleKey = "packages/$skillId/$versionId/bundle.zip"
    $bundlePath = Join-Path $JavaStoragePath ($bundleKey -replace '/', [System.IO.Path]::DirectorySeparatorChar)
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundlePath) | Out-Null
    $zipPath = New-PublishValidateFixtureZip -SkillName "Codex Scan Daemon $suffix" -Version '1.0.0' -FilePrefix "publish-scan-daemon-$suffix"
    Copy-Item -LiteralPath $zipPath -Destination $bundlePath -Force

    Invoke-RedisCli -Arguments @(
        'XADD',
        $streamKey,
        '*',
        'taskId',
        "scan-daemon-$suffix",
        'versionId',
        $versionId,
        'bundleKey',
        $bundleKey,
        'scannerType',
        'skill-scanner'
    ) | Out-Null

    $deadline = (Get-Date).AddSeconds(45)
    $status = 'SCANNING'
    $audit = ''
    $scanId = ''
    do {
        Start-Sleep -Milliseconds 750
        $status = Invoke-PostgresScalar -Sql "SELECT status FROM skill_version WHERE id = $versionId;"
        $audit = Invoke-PostgresScalar -Sql "SELECT COALESCE(scan_id, 'pending') || '|' || verdict || '|' || is_safe || '|' || findings_count || '|' || COALESCE(max_severity, '') || '|' || (scanned_at IS NOT NULL) FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
        $scanId = Invoke-PostgresScalar -Sql "SELECT COALESCE(scan_id, 'pending') FROM security_audit WHERE skill_version_id = $versionId AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 1;"
    } while ($status -eq 'SCANNING' -and (Get-Date) -lt $deadline)

    $pending = @(Invoke-RedisCli -Arguments @('XPENDING', $streamKey, $groupName))
    $scanTempDir = "$JavaStoragePath-scan-temp"
    $tempFiles = @(Get-ChildItem -LiteralPath $scanTempDir -File -ErrorAction SilentlyContinue)

    $result = [ordered]@{
        daemon = [ordered]@{
            enabled = $env:SKILLHUB_SCAN_CONSUMER_ENABLED
            streamKey = $streamKey
            groupName = $groupName
        }
        redis = [ordered]@{
            pending = $pending
        }
        db = [ordered]@{
            slug = $slug
            skillId = $skillId
            versionId = $versionId
            status = $status
            audit = $audit
            scanId = $scanId
            bundleKey = $bundleKey
            stagedFileCountAfterDaemon = $tempFiles.Count
        }
        checks = [ordered]@{
            daemonEnabled = ($env:SKILLHUB_SCAN_CONSUMER_ENABLED -eq 'true')
            versionLeftScanning = ($status -ne 'SCANNING')
            scannerReturnedRealScanId = (-not [string]::IsNullOrWhiteSpace([string]$scanId))
            auditUpdated = ($audit -match '\|true\|\d+\|.*\|true$')
            streamHasNoPending = ($pending.Count -ge 1 -and $pending[0] -eq '0')
            stagedBundleCleaned = ($tempFiles.Count -eq 0)
        }
        comparedFields = @('daemon.enabled', 'audit.scan_id', 'version.status', 'redis.pending')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.daemonEnabled -or
        -not $result.checks.versionLeftScanning -or
        -not $result.checks.scannerReturnedRealScanId -or
        -not $result.checks.auditUpdated -or
        -not $result.checks.streamHasNoPending -or
        -not $result.checks.stagedBundleCleaned) {
        throw "Publish scan daemon supervisor check failed. See .dev/$ResultFileName."
    }
}

function Invoke-RedisCli {
    param([string[]]$Arguments)

    $output = & docker @('compose', '-p', 'skillhub', 'exec', '-T', 'redis', 'redis-cli', '--raw') @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "redis-cli failed: $($Arguments -join ' ')"
    }
    return @($output)
}

function Read-RedisStreamFirstEntry {
    param([string]$StreamKey)

    $lines = @(Invoke-RedisCli -Arguments @('XRANGE', $StreamKey, '-', '+', 'COUNT', '1'))
    if ($lines.Count -eq 0) {
        return $null
    }

    $fields = [ordered]@{}
    for ($index = 1; $index -lt ($lines.Count - 1); $index += 2) {
        $fields[$lines[$index]] = $lines[$index + 1]
    }

    return [ordered]@{
        id = $lines[0]
        fields = $fields
    }
}

function Invoke-PublishScannerHandoffContractComparison {
    param([string]$ResultFileName = 'publish-scanner-handoff-contract-result.json')

    $streamKey = 'skillhub:scan:requests'
    Invoke-RedisCli -Arguments @('DEL', $streamKey) | Out-Null

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $headers = @{ 'X-Mock-User-Id' = 'local-user' }
    $path = '/api/cli/v1/skills/global/publish'
    $version = "1.0.$suffix"
    $zipPath = New-PublishValidateFixtureZip -SkillName "Codex Scanner Handoff $suffix" -Version $version -FilePrefix "publish-scanner-handoff-$suffix"

    Write-Host "Verifying Python scanner handoff route: POST $path"
    $python = Invoke-MultipartPostJson "$PythonUrl$path" -FilePath $zipPath -Headers $headers
    $entry = Read-RedisStreamFirstEntry -StreamKey $streamKey
    if ($null -eq $entry) {
        throw "No Redis scan task was published to $streamKey."
    }

    $fields = $entry.fields
    $result = [ordered]@{
        python = $python
        redis = $entry
        checks = [ordered]@{
            pythonSucceeded = ($python.status -eq 200 -and $python.body.code -eq 0)
            taskIdPresent = -not [string]::IsNullOrWhiteSpace([string]$fields.taskId)
            versionIdPresent = -not [string]::IsNullOrWhiteSpace([string]$fields.versionId)
            uploadModeUsesBundleKey = (
                -not [string]::IsNullOrWhiteSpace([string]$fields.bundleKey) -and
                [string]::IsNullOrWhiteSpace([string]$fields.skillPath)
            )
            publisherMatches = ($fields.publisherId -eq 'local-user')
            createdAtMillisPresent = -not [string]::IsNullOrWhiteSpace([string]$fields.createdAtMillis)
            scannerTypeMatches = ($fields.scannerType -eq 'skill-scanner')
            bundleKeyMatchesJavaShape = ([string]$fields.bundleKey -match '^packages/\d+/\d+/bundle\.zip$')
        }
        comparedFields = @('taskId', 'versionId', 'bundleKey', 'publisherId', 'createdAtMillis', 'scannerType')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.pythonSucceeded -or
        -not $result.checks.taskIdPresent -or
        -not $result.checks.versionIdPresent -or
        -not $result.checks.uploadModeUsesBundleKey -or
        -not $result.checks.publisherMatches -or
        -not $result.checks.createdAtMillisPresent -or
        -not $result.checks.scannerTypeMatches -or
        -not $result.checks.bundleKeyMatchesJavaShape) {
        throw "Publish scanner handoff check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridPublishDryRunSmokeVerification {
    try {
        Invoke-PublishDryRunTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-dry-run-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishStorageFoundationSmokeVerification {
    try {
        Invoke-PublishStorageFoundationTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-storage-foundation-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishDbFoundationSmokeVerification {
    try {
        Invoke-PublishDbFoundationTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-db-foundation-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishSideEffectsFoundationSmokeVerification {
    try {
        Invoke-PublishSideEffectsFoundationTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-side-effects-foundation-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishReplacementFoundationSmokeVerification {
    try {
        Invoke-PublishReplacementFoundationTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-replacement-foundation-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishTransactionSplitSmokeVerification {
    try {
        Invoke-PublishTransactionSplitTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-transaction-split-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishOrchestrationFoundationSmokeVerification {
    try {
        Invoke-PublishOrchestrationFoundationTests
        Start-Hybrid
        Invoke-PublishFoundationContractComparison -ResultFileName 'publish-orchestration-foundation-contract-result.json'
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishHttpValidateSmokeVerification {
    try {
        Invoke-PublishHttpValidateTests
        Start-Hybrid
        Invoke-PublishHttpValidateContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishCliWriteDirectSmokeVerification {
    try {
        Invoke-PublishHttpValidateTests
        Start-Hybrid
        Invoke-PublishCliWriteDirectContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScannerHandoffSmokeVerification {
    $previousScannerEnabled = $env:SKILLHUB_SECURITY_SCANNER_ENABLED
    $previousScannerMode = $env:SKILLHUB_SECURITY_SCANNER_MODE
    $previousRedisUrl = $env:SKILLHUB_REDIS_URL
    $previousStreamKey = $env:SKILLHUB_SCAN_STREAM_KEY
    try {
        $env:SKILLHUB_SECURITY_SCANNER_ENABLED = 'true'
        $env:SKILLHUB_SECURITY_SCANNER_MODE = 'upload'
        $env:SKILLHUB_REDIS_URL = 'redis://localhost:6379'
        $env:SKILLHUB_SCAN_STREAM_KEY = 'skillhub:scan:requests'
        Invoke-PublishScannerHandoffTests
        Start-Hybrid
        Invoke-PublishScannerHandoffContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $previousScannerEnabled) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_ENABLED -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_ENABLED = $previousScannerEnabled }
        if ($null -eq $previousScannerMode) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_MODE -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_MODE = $previousScannerMode }
        if ($null -eq $previousRedisUrl) { Remove-Item Env:\SKILLHUB_REDIS_URL -ErrorAction SilentlyContinue } else { $env:SKILLHUB_REDIS_URL = $previousRedisUrl }
        if ($null -eq $previousStreamKey) { Remove-Item Env:\SKILLHUB_SCAN_STREAM_KEY -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_STREAM_KEY = $previousStreamKey }
        Stop-Hybrid
    }
}

function Invoke-HybridPublishCliReplacementLookupSmokeVerification {
    try {
        Invoke-PublishCliReplacementLookupTests
        Start-Hybrid
        Invoke-PublishCliReplacementLookupContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishPendingAutoWithdrawSmokeVerification {
    try {
        Invoke-PublishPendingAutoWithdrawTests
        Start-Hybrid
        Invoke-PublishPendingAutoWithdrawContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishStorageFailureCleanupSmokeVerification {
    $previousStorageBasePath = $env:SKILLHUB_STORAGE_BASE_PATH
    $blockedStoragePath = Join-Path $DevDir 'python-storage-blocker'
    try {
        Ensure-DevDir
        if (Test-Path -LiteralPath $blockedStoragePath) {
            Remove-Item -LiteralPath $blockedStoragePath -Recurse -Force
        }
        Set-Content -LiteralPath $blockedStoragePath -Value 'not-a-directory'
        $env:SKILLHUB_STORAGE_BASE_PATH = $blockedStoragePath

        Invoke-PublishStorageFailureCleanupTests
        Start-Hybrid
        Invoke-PublishStorageFailureCleanupContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $previousStorageBasePath) { Remove-Item Env:\SKILLHUB_STORAGE_BASE_PATH -ErrorAction SilentlyContinue } else { $env:SKILLHUB_STORAGE_BASE_PATH = $previousStorageBasePath }
        Stop-Hybrid
    }
}

function Invoke-HybridCliPublishWriteOwnershipSmokeVerification {
    try {
        Invoke-CliPublishWriteOwnershipTests
        Start-Hybrid
        Invoke-CliPublishWriteOwnershipContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPortalPublishWriteOwnershipSmokeVerification {
    try {
        Invoke-PortalPublishWriteOwnershipTests
        Start-Hybrid
        Invoke-PortalPublishWriteOwnershipContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridRootLegacyPublishWriteOwnershipSmokeVerification {
    try {
        Invoke-RootLegacyPublishWriteOwnershipTests
        Start-Hybrid
        Invoke-RootLegacyPublishWriteOwnershipContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScannerResultProcessingSmokeVerification {
    try {
        Invoke-PublishScannerResultProcessingTests
        Start-Hybrid
        Invoke-PublishScannerResultProcessingContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScanTaskWorkerBoundarySmokeVerification {
    try {
        Invoke-PublishScanTaskWorkerBoundaryTests
        Start-Hybrid
        Invoke-PublishScanTaskWorkerBoundaryContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScanConsumerRuntimeSmokeVerification {
    try {
        Invoke-PublishScanConsumerRuntimeTests
        Start-Hybrid
        Invoke-PublishScanConsumerRuntimeContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScannerHttpClientSmokeVerification {
    $previousScannerMode = $env:SKILLHUB_SECURITY_SCANNER_MODE
    $previousScannerBaseUrl = $env:SKILLHUB_SECURITY_SCANNER_BASE_URL
    $previousScannerScanPath = $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH
    try {
        $env:SKILLHUB_SECURITY_SCANNER_MODE = 'upload'
        $env:SKILLHUB_SECURITY_SCANNER_BASE_URL = 'http://localhost:8000'
        $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH = '/scan-upload'
        Invoke-PublishScannerHttpClientTests
        Start-Hybrid
        Invoke-PublishScannerHttpClientContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $previousScannerMode) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_MODE -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_MODE = $previousScannerMode }
        if ($null -eq $previousScannerBaseUrl) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_BASE_URL -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_BASE_URL = $previousScannerBaseUrl }
        if ($null -eq $previousScannerScanPath) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_SCAN_PATH -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH = $previousScannerScanPath }
        Stop-Hybrid
    }
}

function Invoke-HybridPublishScanDaemonSupervisorSmokeVerification {
    $previousScanConsumerEnabled = $env:SKILLHUB_SCAN_CONSUMER_ENABLED
    $previousScanConsumerGroupName = $env:SKILLHUB_SCAN_CONSUMER_GROUP_NAME
    $previousScanConsumerName = $env:SKILLHUB_SCAN_CONSUMER_NAME
    $previousScanConsumerBlockMs = $env:SKILLHUB_SCAN_CONSUMER_BLOCK_MS
    $previousScanConsumerReclaimMinIdleMs = $env:SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS
    $previousScanStreamKey = $env:SKILLHUB_SCAN_STREAM_KEY
    $previousScannerMode = $env:SKILLHUB_SECURITY_SCANNER_MODE
    $previousScannerBaseUrl = $env:SKILLHUB_SECURITY_SCANNER_BASE_URL
    $previousScannerScanPath = $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH
    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    try {
        $env:SKILLHUB_SCAN_CONSUMER_ENABLED = 'true'
        $env:SKILLHUB_SCAN_CONSUMER_GROUP_NAME = "skillhub-scan-daemon-$suffix"
        $env:SKILLHUB_SCAN_CONSUMER_NAME = "scanner-python-daemon-$suffix"
        $env:SKILLHUB_SCAN_CONSUMER_BLOCK_MS = '250'
        $env:SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS = '5000'
        $env:SKILLHUB_SCAN_STREAM_KEY = "skillhub:scan:requests:daemon:$suffix"
        $env:SKILLHUB_SECURITY_SCANNER_MODE = 'upload'
        $env:SKILLHUB_SECURITY_SCANNER_BASE_URL = 'http://localhost:8000'
        $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH = '/scan-upload'
        Invoke-PublishScanDaemonSupervisorTests
        Start-Hybrid
        Invoke-PublishScanDaemonSupervisorContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        if ($null -eq $previousScanConsumerEnabled) { Remove-Item Env:\SKILLHUB_SCAN_CONSUMER_ENABLED -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_CONSUMER_ENABLED = $previousScanConsumerEnabled }
        if ($null -eq $previousScanConsumerGroupName) { Remove-Item Env:\SKILLHUB_SCAN_CONSUMER_GROUP_NAME -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_CONSUMER_GROUP_NAME = $previousScanConsumerGroupName }
        if ($null -eq $previousScanConsumerName) { Remove-Item Env:\SKILLHUB_SCAN_CONSUMER_NAME -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_CONSUMER_NAME = $previousScanConsumerName }
        if ($null -eq $previousScanConsumerBlockMs) { Remove-Item Env:\SKILLHUB_SCAN_CONSUMER_BLOCK_MS -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_CONSUMER_BLOCK_MS = $previousScanConsumerBlockMs }
        if ($null -eq $previousScanConsumerReclaimMinIdleMs) { Remove-Item Env:\SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_CONSUMER_RECLAIM_MIN_IDLE_MS = $previousScanConsumerReclaimMinIdleMs }
        if ($null -eq $previousScanStreamKey) { Remove-Item Env:\SKILLHUB_SCAN_STREAM_KEY -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SCAN_STREAM_KEY = $previousScanStreamKey }
        if ($null -eq $previousScannerMode) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_MODE -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_MODE = $previousScannerMode }
        if ($null -eq $previousScannerBaseUrl) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_BASE_URL -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_BASE_URL = $previousScannerBaseUrl }
        if ($null -eq $previousScannerScanPath) { Remove-Item Env:\SKILLHUB_SECURITY_SCANNER_SCAN_PATH -ErrorAction SilentlyContinue } else { $env:SKILLHUB_SECURITY_SCANNER_SCAN_PATH = $previousScannerScanPath }
        Stop-Hybrid
    }
}

function Invoke-ReviewApproveTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_approve.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-ReviewApprovePostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$Comment
    )

    $body = @{ comment = $Comment } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function ConvertTo-StableReviewTaskContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            namespace = $Response.data.namespace
            version = $Response.data.version
            status = $Response.data.status
            submittedBy = $Response.data.submittedBy
            reviewedBy = $Response.data.reviewedBy
            reviewComment = $Response.data.reviewComment
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-ReviewApproveContractComparison {
    param([string]$ResultFileName = 'review-approve-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-approve-$suffix"
    $reviewerId = "codex-reviewer-$suffix"
    $submitterId = "codex-review-submitter-$suffix"
    $comment = "approve-$suffix"
    $javaSlug = "java-approve-$suffix"
    $pythonSlug = "python-approve-$suffix"
    $proxySlug = "proxy-approve-$suffix"
    $proxyWebSlug = "proxy-web-approve-$suffix"

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    java_skill_id BIGINT;
    python_skill_id BIGINT;
    proxy_skill_id BIGINT;
    proxy_web_skill_id BIGINT;
    java_version_id BIGINT;
    python_version_id BIGINT;
    proxy_version_id BIGINT;
    proxy_web_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$reviewerId', 'Codex Review Approver', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_account (id, display_name, status)
    VALUES ('$submitterId', 'Codex Review Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Approve', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$submitterId', 'MEMBER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES (ns_id, '$javaSlug', 'Draft Java Approve', 'Before approve', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')
    RETURNING id INTO java_skill_id;
    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES (ns_id, '$pythonSlug', 'Draft Python Approve', 'Before approve', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')
    RETURNING id INTO python_skill_id;
    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES (ns_id, '$proxySlug', 'Draft Proxy Approve', 'Before approve', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')
    RETURNING id INTO proxy_skill_id;
    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES (ns_id, '$proxyWebSlug', 'Draft Proxy Web Approve', 'Before approve', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')
    RETURNING id INTO proxy_web_skill_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        java_skill_id, '1.0.0', 'PENDING_REVIEW',
        jsonb_build_object('name', 'Approved Skill', 'description', 'Approved by review'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
    )
    RETURNING id INTO java_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        python_skill_id, '1.0.0', 'PENDING_REVIEW',
        jsonb_build_object('name', 'Approved Skill', 'description', 'Approved by review'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
    )
    RETURNING id INTO python_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        proxy_skill_id, '1.0.0', 'PENDING_REVIEW',
        jsonb_build_object('name', 'Approved Skill', 'description', 'Approved by review'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
    )
    RETURNING id INTO proxy_version_id;

    INSERT INTO skill_version (
        skill_id, version, status, parsed_metadata_json, manifest_json,
        file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
    )
    VALUES (
        proxy_web_skill_id, '1.0.0', 'PENDING_REVIEW',
        jsonb_build_object('name', 'Approved Skill', 'description', 'Approved by review'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
    )
    RETURNING id INTO proxy_web_version_id;

    INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
    VALUES
        (java_version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP),
        (python_version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP),
        (proxy_version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP),
        (proxy_web_version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP);
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $javaReviewTaskId = Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$javaSlug' LIMIT 1;"
    $pythonReviewTaskId = Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$pythonSlug' LIMIT 1;"
    $proxyReviewTaskId = Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$proxySlug' LIMIT 1;"
    $proxyWebReviewTaskId = Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$proxyWebSlug' LIMIT 1;"

    $java = Invoke-ReviewApprovePostJson "$JavaUrl/api/v1/reviews/$javaReviewTaskId/approve" $reviewerId $comment
    $python = Invoke-ReviewApprovePostJson "$PythonUrl/api/v1/reviews/$pythonReviewTaskId/approve" $reviewerId $comment
    $proxyV1 = Invoke-ReviewApprovePostJson "$WebUrl/api/v1/reviews/$proxyReviewTaskId/approve" $reviewerId $comment
    $proxyWeb = Invoke-ReviewApprovePostJson "$WebUrl/api/web/reviews/$proxyWebReviewTaskId/approve" $reviewerId $comment

    $javaStable = ConvertTo-StableReviewTaskContractJson -Response $java
    $pythonStable = ConvertTo-StableReviewTaskContractJson -Response $python
    $proxyStable = ConvertTo-StableReviewTaskContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableReviewTaskContractJson -Response $proxyWeb

    $javaDb = Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || (sv.published_at IS NOT NULL) || '|' || (s.latest_version_id = sv.id) || '|' || s.visibility || '|' || s.display_name || '|' || s.summary || '|' || COALESCE(s.updated_by, '') FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id WHERE rt.id = $javaReviewTaskId;"
    $pythonDb = Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || (sv.published_at IS NOT NULL) || '|' || (s.latest_version_id = sv.id) || '|' || s.visibility || '|' || s.display_name || '|' || s.summary || '|' || COALESCE(s.updated_by, '') FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id WHERE rt.id = $pythonReviewTaskId;"
    $proxyDb = Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || (sv.published_at IS NOT NULL) || '|' || (s.latest_version_id = sv.id) || '|' || s.visibility || '|' || s.display_name || '|' || s.summary || '|' || COALESCE(s.updated_by, '') FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id WHERE rt.id = $proxyReviewTaskId;"
    $proxyWebDb = Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || (sv.published_at IS NOT NULL) || '|' || (s.latest_version_id = sv.id) || '|' || s.visibility || '|' || s.display_name || '|' || s.summary || '|' || COALESCE(s.updated_by, '') FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id WHERE rt.id = $proxyWebReviewTaskId;"
    $pythonAudit = Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'REVIEW_TASK' AND target_id = $pythonReviewTaskId AND action = 'REVIEW_APPROVE' ORDER BY created_at DESC LIMIT 1;"
    $rejectProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyReviewTaskId/reject" -Method 'POST'
    $detailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyReviewTaskId" -Method 'GET'

    $expectedDbSuffix = "APPROVED|PUBLISHED|true|true|NAMESPACE_ONLY|Approved Skill|Approved by review|$reviewerId"
    $result = [ordered]@{
        namespace = $namespace
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        javaDb = $javaDb
        pythonDb = $pythonDb
        proxyDb = $proxyDb
        proxyWebDb = $proxyWebDb
        pythonAudit = $pythonAudit
        javaOwnedBoundaries = [ordered]@{
            rejectStatus = $rejectProxyStatus
            detailStatus = $detailProxyStatus
        }
        checks = [ordered]@{
            javaDbApproved = ($javaDb -eq $expectedDbSuffix)
            pythonDbApproved = ($pythonDb -eq $expectedDbSuffix)
            proxyDbApproved = ($proxyDb -eq $expectedDbSuffix)
            proxyWebDbApproved = ($proxyWebDb -eq $expectedDbSuffix)
            auditRecorded = ($pythonAudit -match '^REVIEW_APPROVE\|REVIEW_TASK\|')
            rejectRemainsJavaOwned = ($rejectProxyStatus -ne 404)
            detailRemainsJavaOwned = ($detailProxyStatus -ne 404)
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.javaMatchesPython -or -not $result.pythonMatchesProxy -or -not $result.pythonMatchesProxyWeb) {
        throw "Review approve response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.javaDbApproved -or -not $result.checks.pythonDbApproved -or -not $result.checks.proxyDbApproved -or -not $result.checks.proxyWebDbApproved -or -not $result.checks.auditRecorded) {
        throw "Review approve database/audit check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewApproveSmokeVerification {
    try {
        Invoke-ReviewApproveTests
        Start-Hybrid
        Invoke-ReviewApproveContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewRejectWithdrawTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-ReviewWithdrawPostJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId }
}

function Invoke-ReviewRejectWithdrawContractComparison {
    param([string]$ResultFileName = 'review-reject-withdraw-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-rw-$suffix"
    $reviewerId = "codex-reviewer-$suffix"
    $submitterId = "codex-submitter-$suffix"
    $comment = "reject-$suffix"
    $slugs = @(
        "java-reject-$suffix",
        "python-reject-$suffix",
        "proxy-reject-$suffix",
        "proxy-web-reject-$suffix",
        "java-withdraw-$suffix",
        "python-withdraw-$suffix",
        "proxy-withdraw-$suffix",
        "proxy-web-withdraw-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Draft $($_)', 'Before review', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$reviewerId', 'Codex Review Reviewer', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_account (id, display_name, status)
    VALUES ('$submitterId', 'Codex Review Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Reject Withdraw', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$submitterId', 'MEMBER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Review Lifecycle Skill', 'description', 'Review lifecycle check'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP);
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-ReviewTaskId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-VersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaRejectTaskId = Get-ReviewTaskId $slugs[0]
    $pythonRejectTaskId = Get-ReviewTaskId $slugs[1]
    $proxyRejectTaskId = Get-ReviewTaskId $slugs[2]
    $proxyWebRejectTaskId = Get-ReviewTaskId $slugs[3]
    $javaWithdrawTaskId = Get-ReviewTaskId $slugs[4]
    $pythonWithdrawTaskId = Get-ReviewTaskId $slugs[5]
    $proxyWithdrawTaskId = Get-ReviewTaskId $slugs[6]
    $proxyWebWithdrawTaskId = Get-ReviewTaskId $slugs[7]
    $javaWithdrawVersionId = Get-VersionId $slugs[4]
    $pythonWithdrawVersionId = Get-VersionId $slugs[5]
    $proxyWithdrawVersionId = Get-VersionId $slugs[6]
    $proxyWebWithdrawVersionId = Get-VersionId $slugs[7]

    $javaReject = Invoke-ReviewApprovePostJson "$JavaUrl/api/v1/reviews/$javaRejectTaskId/reject" $reviewerId $comment
    $pythonReject = Invoke-ReviewApprovePostJson "$PythonUrl/api/v1/reviews/$pythonRejectTaskId/reject" $reviewerId $comment
    $proxyReject = Invoke-ReviewApprovePostJson "$WebUrl/api/v1/reviews/$proxyRejectTaskId/reject" $reviewerId $comment
    $proxyWebReject = Invoke-ReviewApprovePostJson "$WebUrl/api/web/reviews/$proxyWebRejectTaskId/reject" $reviewerId $comment

    $javaWithdraw = Invoke-ReviewWithdrawPostJson "$JavaUrl/api/v1/reviews/$javaWithdrawTaskId/withdraw" $submitterId
    $pythonWithdraw = Invoke-ReviewWithdrawPostJson "$PythonUrl/api/v1/reviews/$pythonWithdrawTaskId/withdraw" $submitterId
    $proxyWithdraw = Invoke-ReviewWithdrawPostJson "$WebUrl/api/v1/reviews/$proxyWithdrawTaskId/withdraw" $submitterId
    $proxyWebWithdraw = Invoke-ReviewWithdrawPostJson "$WebUrl/api/web/reviews/$proxyWebWithdrawTaskId/withdraw" $submitterId

    $javaRejectStable = ConvertTo-StableReviewTaskContractJson -Response $javaReject
    $pythonRejectStable = ConvertTo-StableReviewTaskContractJson -Response $pythonReject
    $proxyRejectStable = ConvertTo-StableReviewTaskContractJson -Response $proxyReject
    $proxyWebRejectStable = ConvertTo-StableReviewTaskContractJson -Response $proxyWebReject
    $javaWithdrawStable = ConvertTo-StableContractJson -Response $javaWithdraw
    $pythonWithdrawStable = ConvertTo-StableContractJson -Response $pythonWithdraw
    $proxyWithdrawStable = ConvertTo-StableContractJson -Response $proxyWithdraw
    $proxyWebWithdrawStable = ConvertTo-StableContractJson -Response $proxyWebWithdraw

    function Get-RejectDb([string]$TaskId) {
        return Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || COALESCE(rt.reviewed_by, '') || '|' || COALESCE(rt.review_comment, '') FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id WHERE rt.id = $TaskId;"
    }
    function Get-WithdrawDb([string]$TaskId, [string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT (NOT EXISTS (SELECT 1 FROM review_task WHERE id = $TaskId)) || '|' || sv.status || '|' || COALESCE(s.updated_by, '') FROM skill_version sv JOIN skill s ON s.id = sv.skill_id WHERE sv.id = $VersionId;"
    }

    $javaRejectDb = Get-RejectDb $javaRejectTaskId
    $pythonRejectDb = Get-RejectDb $pythonRejectTaskId
    $proxyRejectDb = Get-RejectDb $proxyRejectTaskId
    $proxyWebRejectDb = Get-RejectDb $proxyWebRejectTaskId
    $javaWithdrawDb = Get-WithdrawDb $javaWithdrawTaskId $javaWithdrawVersionId
    $pythonWithdrawDb = Get-WithdrawDb $pythonWithdrawTaskId $pythonWithdrawVersionId
    $proxyWithdrawDb = Get-WithdrawDb $proxyWithdrawTaskId $proxyWithdrawVersionId
    $proxyWebWithdrawDb = Get-WithdrawDb $proxyWebWithdrawTaskId $proxyWebWithdrawVersionId
    $pythonRejectAudit = Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'REVIEW_TASK' AND target_id = $pythonRejectTaskId AND action = 'REVIEW_REJECT' ORDER BY created_at DESC LIMIT 1;"
    $pythonWithdrawAudit = Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'REVIEW_TASK' AND target_id = $pythonWithdrawTaskId AND action = 'REVIEW_WITHDRAW' ORDER BY created_at DESC LIMIT 1;"
    $detailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyRejectTaskId" -Method 'GET'
    $submitProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews" -Method 'POST'

    $expectedRejectDb = "REJECTED|REJECTED|$reviewerId|$comment"
    $expectedWithdrawDb = "true|UPLOADED|$submitterId"
    $result = [ordered]@{
        namespace = $namespace
        reject = [ordered]@{
            javaMatchesPython = ($javaRejectStable -eq $pythonRejectStable)
            pythonMatchesProxy = ($pythonRejectStable -eq $proxyRejectStable)
            pythonMatchesProxyWeb = ($pythonRejectStable -eq $proxyWebRejectStable)
            javaDb = $javaRejectDb
            pythonDb = $pythonRejectDb
            proxyDb = $proxyRejectDb
            proxyWebDb = $proxyWebRejectDb
            pythonAudit = $pythonRejectAudit
        }
        withdraw = [ordered]@{
            javaMatchesPython = ($javaWithdrawStable -eq $pythonWithdrawStable)
            pythonMatchesProxy = ($pythonWithdrawStable -eq $proxyWithdrawStable)
            pythonMatchesProxyWeb = ($pythonWithdrawStable -eq $proxyWebWithdrawStable)
            javaDb = $javaWithdrawDb
            pythonDb = $pythonWithdrawDb
            proxyDb = $proxyWithdrawDb
            proxyWebDb = $proxyWebWithdrawDb
            pythonAudit = $pythonWithdrawAudit
        }
        javaOwnedBoundaries = [ordered]@{
            detailStatus = $detailProxyStatus
            submitStatus = $submitProxyStatus
        }
        checks = [ordered]@{
            rejectResponsesMatch = ($javaRejectStable -eq $pythonRejectStable -and $pythonRejectStable -eq $proxyRejectStable -and $pythonRejectStable -eq $proxyWebRejectStable)
            withdrawResponsesMatch = ($javaWithdrawStable -eq $pythonWithdrawStable -and $pythonWithdrawStable -eq $proxyWithdrawStable -and $pythonWithdrawStable -eq $proxyWebWithdrawStable)
            rejectDbApproved = ($javaRejectDb -eq $expectedRejectDb -and $pythonRejectDb -eq $expectedRejectDb -and $proxyRejectDb -eq $expectedRejectDb -and $proxyWebRejectDb -eq $expectedRejectDb)
            withdrawDbApproved = ($javaWithdrawDb -eq $expectedWithdrawDb -and $pythonWithdrawDb -eq $expectedWithdrawDb -and $proxyWithdrawDb -eq $expectedWithdrawDb -and $proxyWebWithdrawDb -eq $expectedWithdrawDb)
            rejectAuditRecorded = ($pythonRejectAudit -match '^REVIEW_REJECT\|REVIEW_TASK\|')
            withdrawAuditRecorded = ($pythonWithdrawAudit -match '^REVIEW_WITHDRAW\|REVIEW_TASK\|')
            detailRemainsJavaOwned = ($detailProxyStatus -ne 404)
            submitRemainsJavaOwned = ($submitProxyStatus -ne 404)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.rejectResponsesMatch -or -not $result.checks.withdrawResponsesMatch) {
        throw "Review reject/withdraw response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.rejectDbApproved -or -not $result.checks.withdrawDbApproved -or -not $result.checks.rejectAuditRecorded -or -not $result.checks.withdrawAuditRecorded) {
        throw "Review reject/withdraw database/audit check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewRejectWithdrawSmokeVerification {
    try {
        Invoke-ReviewRejectWithdrawTests
        Start-Hybrid
        Invoke-ReviewRejectWithdrawContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewSubmitTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-ReviewSubmitPostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$SkillVersionId
    )

    $body = @{ skillVersionId = [long]$SkillVersionId } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function Invoke-ReviewSubmitContractComparison {
    param([string]$ResultFileName = 'review-submit-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-submit-$suffix"
    $submitterId = "codex-submit-owner-$suffix"
    $slugs = @(
        "java-submit-$suffix",
        "python-submit-$suffix",
        "proxy-submit-$suffix",
        "proxy-web-submit-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Submit $($_)', 'Before submit', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$submitterId', 'Codex Review Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Submit', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$submitterId', 'MEMBER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'UPLOADED',
            jsonb_build_object('name', 'Submit Skill', 'description', 'Submit review check'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
        );
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-VersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-ReviewTaskIdByVersion([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT id FROM review_task WHERE skill_version_id = $VersionId AND status = 'PENDING' ORDER BY id DESC LIMIT 1;"
    }
    function Get-SubmitDb([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT rt.status || '|' || sv.status || '|' || rt.submitted_by FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id WHERE sv.id = $VersionId AND rt.status = 'PENDING' ORDER BY rt.id DESC LIMIT 1;"
    }

    $javaVersionId = Get-VersionId $slugs[0]
    $pythonVersionId = Get-VersionId $slugs[1]
    $proxyVersionId = Get-VersionId $slugs[2]
    $proxyWebVersionId = Get-VersionId $slugs[3]

    $java = Invoke-ReviewSubmitPostJson "$JavaUrl/api/v1/reviews" $submitterId $javaVersionId
    $python = Invoke-ReviewSubmitPostJson "$PythonUrl/api/v1/reviews" $submitterId $pythonVersionId
    $proxyV1 = Invoke-ReviewSubmitPostJson "$WebUrl/api/v1/reviews" $submitterId $proxyVersionId
    $proxyWeb = Invoke-ReviewSubmitPostJson "$WebUrl/api/web/reviews" $submitterId $proxyWebVersionId

    $javaStable = ConvertTo-StableReviewTaskContractJson -Response $java
    $pythonStable = ConvertTo-StableReviewTaskContractJson -Response $python
    $proxyStable = ConvertTo-StableReviewTaskContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableReviewTaskContractJson -Response $proxyWeb

    $javaTaskId = Get-ReviewTaskIdByVersion $javaVersionId
    $pythonTaskId = Get-ReviewTaskIdByVersion $pythonVersionId
    $proxyTaskId = Get-ReviewTaskIdByVersion $proxyVersionId
    $proxyWebTaskId = Get-ReviewTaskIdByVersion $proxyWebVersionId

    $javaDb = Get-SubmitDb $javaVersionId
    $pythonDb = Get-SubmitDb $pythonVersionId
    $proxyDb = Get-SubmitDb $proxyVersionId
    $proxyWebDb = Get-SubmitDb $proxyWebVersionId
    $pythonAudit = Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'REVIEW_TASK' AND target_id = $pythonTaskId AND action = 'REVIEW_SUBMIT' ORDER BY created_at DESC LIMIT 1;"
    $listProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews" -Method 'GET'
    $detailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId" -Method 'GET'

    $expectedDb = "PENDING|PENDING_REVIEW|$submitterId"
    $result = [ordered]@{
        namespace = $namespace
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        taskIds = [ordered]@{
            java = $javaTaskId
            python = $pythonTaskId
            proxy = $proxyTaskId
            proxyWeb = $proxyWebTaskId
        }
        javaDb = $javaDb
        pythonDb = $pythonDb
        proxyDb = $proxyDb
        proxyWebDb = $proxyWebDb
        pythonAudit = $pythonAudit
        javaOwnedBoundaries = [ordered]@{
            listStatus = $listProxyStatus
            detailStatus = $detailProxyStatus
        }
        checks = [ordered]@{
            responsesMatch = ($javaStable -eq $pythonStable -and $pythonStable -eq $proxyStable -and $pythonStable -eq $proxyWebStable)
            dbSubmitted = ($javaDb -eq $expectedDb -and $pythonDb -eq $expectedDb -and $proxyDb -eq $expectedDb -and $proxyWebDb -eq $expectedDb)
            auditRecorded = ($pythonAudit -match '^REVIEW_SUBMIT\|REVIEW_TASK\|')
            listRemainsJavaOwned = ($listProxyStatus -ne 404)
            detailRemainsJavaOwned = ($detailProxyStatus -ne 404)
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.responsesMatch) {
        throw "Review submit response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.dbSubmitted -or -not $result.checks.auditRecorded) {
        throw "Review submit database/audit check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.listRemainsJavaOwned -or -not $result.checks.detailRemainsJavaOwned) {
        throw "Review submit route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewSubmitSmokeVerification {
    try {
        Invoke-ReviewSubmitTests
        Start-Hybrid
        Invoke-ReviewSubmitContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewListTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_list.py', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableReviewPageContractJson {
    param([object]$Response)

    $items = @()
    foreach ($item in $Response.data.items) {
        $items += [ordered]@{
            status = $item.status
            submittedBy = $item.submittedBy
            reviewedBy = $item.reviewedBy
            reviewComment = $item.reviewComment
        }
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            total = $Response.data.total
            page = $Response.data.page
            size = $Response.data.size
            itemCount = @($Response.data.items).Count
            items = $items
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-ReviewListGetJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method Get -Headers @{ 'X-Mock-User-Id' = $UserId }
}

function Invoke-ReviewListContractComparison {
    param([string]$ResultFileName = 'review-list-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-list-$suffix"
    $reviewerId = "codex-review-list-admin-$suffix"
    $submitterId = "codex-review-list-submitter-$suffix"

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
    skill_admin_role_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Review List Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Review List Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    SELECT id INTO skill_admin_role_id FROM role WHERE code = 'SKILL_ADMIN';
    IF skill_admin_role_id IS NOT NULL THEN
        INSERT INTO user_role_binding (user_id, role_id)
        VALUES ('$reviewerId', skill_admin_role_id)
        ON CONFLICT (user_id, role_id) DO NOTHING;
    END IF;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review List', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
            (ns_id, 'approved-$suffix', 'Approved Review List', 'Approved list', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId'),
            (ns_id, 'pending-$suffix', 'Pending Review List', 'Pending list', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId'),
            (ns_id, 'mine-$suffix', 'My Review List', 'Mine list', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Review List Skill', 'description', 'Review list check'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        IF skill_row.slug = 'approved-$suffix' THEN
            INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, reviewed_by, review_comment, submitted_at, reviewed_at)
            VALUES (version_id, ns_id, 'APPROVED', 1, '$submitterId', '$reviewerId', 'approved-$suffix', CURRENT_TIMESTAMP - INTERVAL '3 minutes', CURRENT_TIMESTAMP - INTERVAL '2 minutes');
        ELSE
            INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
            VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');
        END IF;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
    $namespaceId = Invoke-PostgresScalar -Sql "SELECT id FROM namespace WHERE slug = '$namespace';"
    $pendingTaskId = Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN namespace n ON n.id = rt.namespace_id WHERE n.slug = '$namespace' AND rt.status = 'PENDING' ORDER BY rt.id LIMIT 1;"

    $globalPath = "/api/v1/reviews?status=APPROVED&page=0&size=1&sortDirection=ASC"
    $pendingPath = "/api/v1/reviews/pending?namespaceId=$namespaceId&page=0&size=5"
    $myPath = "/api/v1/reviews/my-submissions?page=0&size=5"
    $webGlobalPath = "/api/web/reviews?status=APPROVED&page=0&size=1&sortDirection=ASC"
    $webPendingPath = "/api/web/reviews/pending?namespaceId=$namespaceId&page=0&size=5"
    $webMyPath = "/api/web/reviews/my-submissions?page=0&size=5"

    $javaGlobal = Invoke-ReviewListGetJson "$JavaUrl$globalPath" $reviewerId
    $pythonGlobal = Invoke-ReviewListGetJson "$PythonUrl$globalPath" $reviewerId
    $proxyGlobal = Invoke-ReviewListGetJson "$WebUrl$globalPath" $reviewerId
    $proxyWebGlobal = Invoke-ReviewListGetJson "$WebUrl$webGlobalPath" $reviewerId

    $javaPending = Invoke-ReviewListGetJson "$JavaUrl$pendingPath" $reviewerId
    $pythonPending = Invoke-ReviewListGetJson "$PythonUrl$pendingPath" $reviewerId
    $proxyPending = Invoke-ReviewListGetJson "$WebUrl$pendingPath" $reviewerId
    $proxyWebPending = Invoke-ReviewListGetJson "$WebUrl$webPendingPath" $reviewerId

    $javaMine = Invoke-ReviewListGetJson "$JavaUrl$myPath" $submitterId
    $pythonMine = Invoke-ReviewListGetJson "$PythonUrl$myPath" $submitterId
    $proxyMine = Invoke-ReviewListGetJson "$WebUrl$myPath" $submitterId
    $proxyWebMine = Invoke-ReviewListGetJson "$WebUrl$webMyPath" $submitterId

    $globalStable = [ordered]@{
        java = ConvertTo-StableReviewPageContractJson -Response $javaGlobal
        python = ConvertTo-StableReviewPageContractJson -Response $pythonGlobal
        proxy = ConvertTo-StableReviewPageContractJson -Response $proxyGlobal
        proxyWeb = ConvertTo-StableReviewPageContractJson -Response $proxyWebGlobal
    }
    $pendingStable = [ordered]@{
        java = ConvertTo-StableReviewPageContractJson -Response $javaPending
        python = ConvertTo-StableReviewPageContractJson -Response $pythonPending
        proxy = ConvertTo-StableReviewPageContractJson -Response $proxyPending
        proxyWeb = ConvertTo-StableReviewPageContractJson -Response $proxyWebPending
    }
    $mineStable = [ordered]@{
        java = ConvertTo-StableReviewPageContractJson -Response $javaMine
        python = ConvertTo-StableReviewPageContractJson -Response $pythonMine
        proxy = ConvertTo-StableReviewPageContractJson -Response $proxyMine
        proxyWeb = ConvertTo-StableReviewPageContractJson -Response $proxyWebMine
    }

    $detailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$pendingTaskId" -Method 'GET'
    $skillDetailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/web/reviews/$pendingTaskId/skill-detail" -Method 'GET'

    $result = [ordered]@{
        namespace = $namespace
        namespaceId = $namespaceId
        global = $globalStable
        pending = $pendingStable
        mySubmissions = $mineStable
        javaOwnedBoundaries = [ordered]@{
            detailStatus = $detailProxyStatus
            skillDetailStatus = $skillDetailProxyStatus
        }
        checks = [ordered]@{
            globalMatches = ($globalStable.java -eq $globalStable.python -and $globalStable.python -eq $globalStable.proxy -and $globalStable.python -eq $globalStable.proxyWeb)
            pendingMatches = ($pendingStable.java -eq $pendingStable.python -and $pendingStable.python -eq $pendingStable.proxy -and $pendingStable.python -eq $pendingStable.proxyWeb)
            mySubmissionsMatches = ($mineStable.java -eq $mineStable.python -and $mineStable.python -eq $mineStable.proxy -and $mineStable.python -eq $mineStable.proxyWeb)
            detailRemainsJavaOwned = ($detailProxyStatus -ne 404)
            skillDetailRemainsJavaOwned = ($skillDetailProxyStatus -ne 404)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.globalMatches -or -not $result.checks.pendingMatches -or -not $result.checks.mySubmissionsMatches) {
        throw "Review list response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.detailRemainsJavaOwned -or -not $result.checks.skillDetailRemainsJavaOwned) {
        throw "Review list route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewListSmokeVerification {
    try {
        Invoke-ReviewListTests
        Start-Hybrid
        Invoke-ReviewListContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewDetailTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_detail.py', 'tests/test_review_list.py', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-ReviewDetailContractComparison {
    param([string]$ResultFileName = 'review-detail-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-detail-$suffix"
    $reviewerId = "codex-review-detail-admin-$suffix"
    $submitterId = "codex-review-detail-submitter-$suffix"
    $slugs = @(
        "java-detail-$suffix",
        "python-detail-$suffix",
        "proxy-detail-$suffix",
        "proxy-web-detail-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Detail $($_)', 'Before detail', '$submitterId', 'PUBLIC', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Review Detail Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Review Detail Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Detail', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Review Detail Skill', 'description', 'Review detail check'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '$submitterId', CURRENT_TIMESTAMP, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-ReviewTaskId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaTaskId = Get-ReviewTaskId $slugs[0]
    $pythonTaskId = Get-ReviewTaskId $slugs[1]
    $proxyTaskId = Get-ReviewTaskId $slugs[2]
    $proxyWebTaskId = Get-ReviewTaskId $slugs[3]

    $java = Invoke-ReviewListGetJson "$JavaUrl/api/v1/reviews/$javaTaskId" $reviewerId
    $python = Invoke-ReviewListGetJson "$PythonUrl/api/v1/reviews/$pythonTaskId" $reviewerId
    $proxyV1 = Invoke-ReviewListGetJson "$WebUrl/api/v1/reviews/$proxyTaskId" $reviewerId
    $proxyWeb = Invoke-ReviewListGetJson "$WebUrl/api/web/reviews/$proxyWebTaskId" $reviewerId

    $javaStable = ConvertTo-StableReviewTaskContractJson -Response $java
    $pythonStable = ConvertTo-StableReviewTaskContractJson -Response $python
    $proxyStable = ConvertTo-StableReviewTaskContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableReviewTaskContractJson -Response $proxyWeb

    $skillDetailProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/skill-detail" -Method 'GET'
    $fileProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/file?path=SKILL.md" -Method 'GET'
    $downloadProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/download" -Method 'GET'

    $result = [ordered]@{
        namespace = $namespace
        taskIds = [ordered]@{
            java = $javaTaskId
            python = $pythonTaskId
            proxy = $proxyTaskId
            proxyWeb = $proxyWebTaskId
        }
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        javaOwnedBoundaries = [ordered]@{
            skillDetailStatus = $skillDetailProxyStatus
            fileStatus = $fileProxyStatus
            downloadStatus = $downloadProxyStatus
        }
        checks = [ordered]@{
            responsesMatch = ($javaStable -eq $pythonStable -and $pythonStable -eq $proxyStable -and $pythonStable -eq $proxyWebStable)
            skillDetailRemainsJavaOwned = ($skillDetailProxyStatus -ne 404)
            fileRemainsJavaOwned = ($fileProxyStatus -ne 404)
            downloadRemainsJavaOwned = ($downloadProxyStatus -ne 404)
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.responsesMatch) {
        throw "Review detail response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.skillDetailRemainsJavaOwned -or -not $result.checks.fileRemainsJavaOwned -or -not $result.checks.downloadRemainsJavaOwned) {
        throw "Review detail route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewDetailSmokeVerification {
    try {
        Invoke-ReviewDetailTests
        Start-Hybrid
        Invoke-ReviewDetailContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewSkillDetailTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_skill_detail.py', 'tests/test_review_detail.py', 'tests/test_review_list.py', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableReviewSkillLifecycleJson {
    param([object]$Version)

    if ($null -eq $Version) {
        return $null
    }

    return [ordered]@{
        version = $Version.version
        status = $Version.status
    }
}

function ConvertTo-StableReviewSkillDetailContractJson {
    param([object]$Response)

    $versions = @()
    foreach ($version in $Response.data.versions) {
        $versions += [ordered]@{
            version = $version.version
            status = $version.status
            changelog = $version.changelog
            fileCount = $version.fileCount
            totalSize = $version.totalSize
            hasPublishedAt = ($null -ne $version.publishedAt)
            downloadAvailable = $version.downloadAvailable
        }
    }

    $files = @()
    foreach ($file in $Response.data.files) {
        $files += [ordered]@{
            filePath = $file.filePath
            fileSize = $file.fileSize
            contentType = $file.contentType
            sha256 = $file.sha256
        }
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skill = [ordered]@{
                displayName = $Response.data.skill.displayName
                ownerId = $Response.data.skill.ownerId
                ownerDisplayName = $Response.data.skill.ownerDisplayName
                summary = $Response.data.skill.summary
                visibility = $Response.data.skill.visibility
                status = $Response.data.skill.status
                downloadCount = $Response.data.skill.downloadCount
                starCount = $Response.data.skill.starCount
                subscriptionCount = $Response.data.skill.subscriptionCount
                ratingAvg = $Response.data.skill.ratingAvg
                ratingCount = $Response.data.skill.ratingCount
                hidden = $Response.data.skill.hidden
                namespace = $Response.data.skill.namespace
                labelsCount = @($Response.data.skill.labels).Count
                canManageLifecycle = $Response.data.skill.canManageLifecycle
                canSubmitPromotion = $Response.data.skill.canSubmitPromotion
                canInteract = $Response.data.skill.canInteract
                canReport = $Response.data.skill.canReport
                headlineVersion = ConvertTo-StableReviewSkillLifecycleJson -Version $Response.data.skill.headlineVersion
                publishedVersion = ConvertTo-StableReviewSkillLifecycleJson -Version $Response.data.skill.publishedVersion
                ownerPreviewVersion = ConvertTo-StableReviewSkillLifecycleJson -Version $Response.data.skill.ownerPreviewVersion
                ownerPreviewReviewComment = $Response.data.skill.ownerPreviewReviewComment
                resolutionMode = $Response.data.skill.resolutionMode
            }
            versions = $versions
            files = $files
            documentationPath = $Response.data.documentationPath
            documentationContent = $Response.data.documentationContent
            downloadUrlKind = ($(if ($Response.data.downloadUrl -match '^/api/v1/reviews/\d+/download$') { 'review-download' } else { $Response.data.downloadUrl }))
            activeVersion = $Response.data.activeVersion
        }
    }

    $json = ($stable | ConvertTo-Json -Depth 50 -Compress)
    $json = [regex]::Replace($json, '("ratingAvg":-?\d+\.\d*?[1-9])0+(?=[,}])', '$1')
    return [regex]::Replace($json, '("ratingAvg":-?\d+)\.0+(?=[,}])', '$1')
}

function Write-ReviewSkillDetailStorageObjects {
    param([string]$Namespace)

    $rows = & docker compose -p skillhub exec -T postgres psql -U skillhub -d skillhub -t -A -F '|' -v ON_ERROR_STOP=1 -c "SELECT sf.storage_key, sf.file_path FROM skill_file sf JOIN skill_version sv ON sv.id = sf.version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$Namespace' AND sf.file_path IN ('README.md', 'SKILL.md') ORDER BY sf.id;"
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres storage-key query failed for review skill-detail fixture."
    }

    foreach ($line in $rows) {
        if (-not $line -or $line.Trim() -eq '') {
            continue
        }
        $parts = $line.Split('|', 2)
        $storageKey = $parts[0]
        $filePath = $parts[1]
        $relativePath = $storageKey -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        if ($filePath -eq 'README.md') {
            Set-Content -LiteralPath $targetPath -Value "# Review skill detail fixture"
        } else {
            Set-Content -LiteralPath $targetPath -Value "# Skill detail fixture"
        }
    }
}

function Invoke-ReviewSkillDetailContractComparison {
    param([string]$ResultFileName = 'review-skill-detail-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-skill-detail-$suffix"
    $reviewerId = "codex-review-skill-admin-$suffix"
    $submitterId = "codex-review-skill-submitter-$suffix"
    $slugs = @(
        "java-review-skill-$suffix",
        "python-review-skill-$suffix",
        "proxy-review-skill-$suffix",
        "proxy-web-review-skill-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Review Skill Detail', 'Review skill detail contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', 4, 2, 1, 4.50, 3, '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    published_version_id BIGINT;
    review_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Review Skill Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Review Skill Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Skill Detail', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (
            namespace_id, slug, display_name, summary, owner_id, visibility, status,
            download_count, star_count, subscription_count, rating_avg, rating_count,
            created_by, updated_by
        )
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at, bundle_ready,
            download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '0.9.0', 'PUBLISHED', 'stable',
            jsonb_build_object('name', 'Review Skill Detail', 'description', 'Stable'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 80, '2026-06-08T09:00:00Z'::timestamptz, '$submitterId',
            '2026-06-08T08:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO published_version_id;

        INSERT INTO skill_version (
            skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready,
            requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW', 'review me',
            jsonb_build_object('name', 'Review Skill Detail', 'description', 'Pending review'),
            jsonb_build_array(jsonb_build_object('path', 'README.md'), jsonb_build_object('path', 'SKILL.md')),
            3, 120, '$submitterId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, FALSE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO review_version_id;

        UPDATE skill SET latest_version_id = published_version_id WHERE id = skill_row.id;

        INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key, created_at)
        VALUES
            (review_version_id, 'README.md', 30, 'text/markdown', 'readme-sha', 'fixtures/review-skill-detail/' || skill_row.slug || '/README.md', CURRENT_TIMESTAMP),
            (review_version_id, 'SKILL.md', 23, 'text/markdown', 'skill-sha', 'fixtures/review-skill-detail/' || skill_row.slug || '/SKILL.md', CURRENT_TIMESTAMP),
            (review_version_id, 'missing.txt', 7, 'text/plain', 'missing-sha', 'fixtures/review-skill-detail/' || skill_row.slug || '/missing.txt', CURRENT_TIMESTAMP);

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (review_version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
    Write-ReviewSkillDetailStorageObjects -Namespace $namespace

    function Get-ReviewTaskId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaTaskId = Get-ReviewTaskId $slugs[0]
    $pythonTaskId = Get-ReviewTaskId $slugs[1]
    $proxyTaskId = Get-ReviewTaskId $slugs[2]
    $proxyWebTaskId = Get-ReviewTaskId $slugs[3]

    $java = Invoke-ReviewListGetJson "$JavaUrl/api/v1/reviews/$javaTaskId/skill-detail" $reviewerId
    $python = Invoke-ReviewListGetJson "$PythonUrl/api/v1/reviews/$pythonTaskId/skill-detail" $reviewerId
    $proxyV1 = Invoke-ReviewListGetJson "$WebUrl/api/v1/reviews/$proxyTaskId/skill-detail" $reviewerId
    $proxyWeb = Invoke-ReviewListGetJson "$WebUrl/api/web/reviews/$proxyWebTaskId/skill-detail" $reviewerId

    $javaStable = ConvertTo-StableReviewSkillDetailContractJson -Response $java
    $pythonStable = ConvertTo-StableReviewSkillDetailContractJson -Response $python
    $proxyStable = ConvertTo-StableReviewSkillDetailContractJson -Response $proxyV1
    $proxyWebStable = ConvertTo-StableReviewSkillDetailContractJson -Response $proxyWeb

    $fileProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/file?path=SKILL.md" -Method 'GET'
    $downloadProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/download" -Method 'GET'

    $result = [ordered]@{
        namespace = $namespace
        taskIds = [ordered]@{
            java = $javaTaskId
            python = $pythonTaskId
            proxy = $proxyTaskId
            proxyWeb = $proxyWebTaskId
        }
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        javaOwnedBoundaries = [ordered]@{
            fileStatus = $fileProxyStatus
            downloadStatus = $downloadProxyStatus
        }
        checks = [ordered]@{
            responsesMatch = ($javaStable -eq $pythonStable -and $pythonStable -eq $proxyStable -and $pythonStable -eq $proxyWebStable)
            fileRemainsJavaOwned = ($fileProxyStatus -ne 404)
            downloadRemainsJavaOwned = ($downloadProxyStatus -ne 404)
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.responsesMatch) {
        throw "Review skill-detail response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.fileRemainsJavaOwned -or -not $result.checks.downloadRemainsJavaOwned) {
        throw "Review skill-detail route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewSkillDetailSmokeVerification {
    try {
        Invoke-ReviewSkillDetailTests
        Start-Hybrid
        Invoke-ReviewSkillDetailContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewFileTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_file_content.py', 'tests/test_review_skill_detail.py', 'tests/test_review_detail.py', 'tests/test_review_list.py', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Get-BytesSha256Hex {
    param([byte[]]$Bytes)

    $sha = [System.Security.Cryptography.SHA256]::Create()
    try {
        $hash = $sha.ComputeHash($Bytes)
        return (($hash | ForEach-Object { $_.ToString('x2') }) -join '')
    } finally {
        $sha.Dispose()
    }
}

function Invoke-ReviewFileGetStableJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    $response = Invoke-WebRequest -Uri $Url -Method Get -Headers @{ 'X-Mock-User-Id' = $UserId } -UseBasicParsing
    $content = $response.Content
    if ($content -is [byte[]]) {
        $bytes = [byte[]]$content
    } else {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$content)
    }
    $stable = [ordered]@{
        statusCode = [int]$response.StatusCode
        contentType = ($response.Headers['Content-Type'] -split ';')[0]
        length = $bytes.Length
        sha256 = Get-BytesSha256Hex -Bytes $bytes
    }
    return ($stable | ConvertTo-Json -Depth 20 -Compress)
}

function Write-ReviewFileStorageObjects {
    param([string]$Namespace)

    $rows = & docker compose -p skillhub exec -T postgres psql -U skillhub -d skillhub -t -A -F '|' -v ON_ERROR_STOP=1 -c "SELECT sf.storage_key FROM skill_file sf JOIN skill_version sv ON sv.id = sf.version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$Namespace' AND sf.file_path = 'src/main.py' ORDER BY sf.id;"
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres storage-key query failed for review file fixture."
    }

    foreach ($line in $rows) {
        if (-not $line -or $line.Trim() -eq '') {
            continue
        }
        $relativePath = $line.Trim() -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        [System.IO.File]::WriteAllBytes($targetPath, [System.Text.Encoding]::UTF8.GetBytes("print('review file')`r`n"))
    }
}

function Invoke-ReviewFileContractComparison {
    param([string]$ResultFileName = 'review-file-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-file-$suffix"
    $reviewerId = "codex-review-file-admin-$suffix"
    $submitterId = "codex-review-file-submitter-$suffix"
    $slugs = @(
        "java-review-file-$suffix",
        "python-review-file-$suffix",
        "proxy-review-file-$suffix",
        "proxy-web-review-file-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Review File', 'Review file contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Review File Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Review File Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review File', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready,
            requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Review File', 'description', 'Pending review'),
            jsonb_build_array(jsonb_build_object('path', 'src/main.py')),
            1, 22, '$submitterId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, FALSE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key, created_at)
        VALUES (
            version_id, 'src/main.py', 22, 'text/x-python', 'review-file-sha',
            'fixtures/review-file/' || skill_row.slug || '/src/main.py', CURRENT_TIMESTAMP
        );

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
    Write-ReviewFileStorageObjects -Namespace $namespace

    function Get-ReviewTaskId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaTaskId = Get-ReviewTaskId $slugs[0]
    $pythonTaskId = Get-ReviewTaskId $slugs[1]
    $proxyTaskId = Get-ReviewTaskId $slugs[2]
    $proxyWebTaskId = Get-ReviewTaskId $slugs[3]

    $javaStable = Invoke-ReviewFileGetStableJson "$JavaUrl/api/v1/reviews/$javaTaskId/file?path=src/main.py" $reviewerId
    $pythonStable = Invoke-ReviewFileGetStableJson "$PythonUrl/api/v1/reviews/$pythonTaskId/file?path=src/main.py" $reviewerId
    $proxyStable = Invoke-ReviewFileGetStableJson "$WebUrl/api/v1/reviews/$proxyTaskId/file?path=src/main.py" $reviewerId
    $proxyWebStable = Invoke-ReviewFileGetStableJson "$WebUrl/api/web/reviews/$proxyWebTaskId/file?path=src/main.py" $reviewerId

    $invalidPathStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/file?path=../secret.txt" -Method 'GET' -Headers @{ 'X-Mock-User-Id' = $reviewerId }
    $downloadProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/download" -Method 'GET'

    $result = [ordered]@{
        namespace = $namespace
        taskIds = [ordered]@{
            java = $javaTaskId
            python = $pythonTaskId
            proxy = $proxyTaskId
            proxyWeb = $proxyWebTaskId
        }
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        boundaryStatuses = [ordered]@{
            invalidPathStatus = $invalidPathStatus
            downloadStatus = $downloadProxyStatus
        }
        checks = [ordered]@{
            fileBytesMatch = ($javaStable -eq $pythonStable -and $pythonStable -eq $proxyStable -and $pythonStable -eq $proxyWebStable)
            invalidPathRejected = ($invalidPathStatus -eq 400)
            downloadRemainsJavaOwned = ($downloadProxyStatus -ne 404)
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.fileBytesMatch -or -not $result.checks.invalidPathRejected) {
        throw "Review file content contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.downloadRemainsJavaOwned) {
        throw "Review file route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewFileSmokeVerification {
    try {
        Invoke-ReviewFileTests
        Start-Hybrid
        Invoke-ReviewFileContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-ReviewDownloadTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_review_download.py', 'tests/test_review_file_content.py', 'tests/test_review_skill_detail.py', 'tests/test_review_detail.py', 'tests/test_review_list.py', 'tests/test_review_submit.py', 'tests/test_review_approve.py', 'tests/test_review_reject_withdraw.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-ReviewDownloadGetStableJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    $response = Invoke-WebRequest -Uri $Url -Method Get -Headers @{ 'X-Mock-User-Id' = $UserId } -UseBasicParsing
    $content = $response.Content
    if ($content -is [byte[]]) {
        $bytes = [byte[]]$content
    } else {
        $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]$content)
    }
    $stable = [ordered]@{
        statusCode = [int]$response.StatusCode
        contentType = ($response.Headers['Content-Type'] -split ';')[0]
        contentDispositionKind = ($(if ($response.Headers['Content-Disposition'] -match '^attachment; filename="Review Download-1\.0\.0\.zip"$') { 'review-download-attachment' } else { $response.Headers['Content-Disposition'] }))
        length = $bytes.Length
        sha256 = Get-BytesSha256Hex -Bytes $bytes
    }
    return ($stable | ConvertTo-Json -Depth 20 -Compress)
}

function Write-ReviewDownloadStorageObjects {
    param([string]$Namespace)

    $rows = & docker compose -p skillhub exec -T postgres psql -U skillhub -d skillhub -t -A -F '|' -v ON_ERROR_STOP=1 -c "SELECT 'packages/' || s.id || '/' || sv.id || '/bundle.zip' AS bundle_key FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$Namespace' ORDER BY rt.id;"
    if ($LASTEXITCODE -ne 0) {
        throw "Postgres bundle-key query failed for review download fixture."
    }

    foreach ($line in $rows) {
        if (-not $line -or $line.Trim() -eq '') {
            continue
        }
        $relativePath = $line.Trim() -replace '/', [System.IO.Path]::DirectorySeparatorChar
        $targetPath = Join-Path $JavaStoragePath $relativePath
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $targetPath) | Out-Null
        [System.IO.File]::WriteAllBytes($targetPath, [System.Text.Encoding]::UTF8.GetBytes("review-download-bundle`r`n"))
    }
}

function Invoke-ReviewDownloadContractComparison {
    param([string]$ResultFileName = 'review-download-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-review-download-$suffix"
    $reviewerId = "codex-review-download-admin-$suffix"
    $submitterId = "codex-review-download-submitter-$suffix"
    $slugs = @(
        "java-review-download-$suffix",
        "python-review-download-$suffix",
        "proxy-review-download-$suffix",
        "proxy-web-review-download-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Review Download', 'Review download contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', 0, '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Review Download Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Review Download Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Review Download', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$reviewerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    FOR skill_row IN
        INSERT INTO skill (
            namespace_id, slug, display_name, summary, owner_id, visibility, status,
            download_count, created_by, updated_by
        )
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at, bundle_ready, download_ready,
            requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Review Download', 'description', 'Pending review'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 22, '$submitterId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, FALSE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
    Write-ReviewDownloadStorageObjects -Namespace $namespace

    function Get-ReviewTaskId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT rt.id FROM review_task rt JOIN skill_version sv ON sv.id = rt.skill_version_id JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    function Get-DownloadCount([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.download_count FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaTaskId = Get-ReviewTaskId $slugs[0]
    $pythonTaskId = Get-ReviewTaskId $slugs[1]
    $proxyTaskId = Get-ReviewTaskId $slugs[2]
    $proxyWebTaskId = Get-ReviewTaskId $slugs[3]

    $javaStable = Invoke-ReviewDownloadGetStableJson "$JavaUrl/api/v1/reviews/$javaTaskId/download" $reviewerId
    $pythonStable = Invoke-ReviewDownloadGetStableJson "$PythonUrl/api/v1/reviews/$pythonTaskId/download" $reviewerId
    $proxyStable = Invoke-ReviewDownloadGetStableJson "$WebUrl/api/v1/reviews/$proxyTaskId/download" $reviewerId
    $proxyWebStable = Invoke-ReviewDownloadGetStableJson "$WebUrl/api/web/reviews/$proxyWebTaskId/download" $reviewerId

    $unauthenticatedStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/reviews/$proxyTaskId/download" -Method 'GET'
    $counts = [ordered]@{
        java = Get-DownloadCount $slugs[0]
        python = Get-DownloadCount $slugs[1]
        proxy = Get-DownloadCount $slugs[2]
        proxyWeb = Get-DownloadCount $slugs[3]
    }

    $result = [ordered]@{
        namespace = $namespace
        taskIds = [ordered]@{
            java = $javaTaskId
            python = $pythonTaskId
            proxy = $proxyTaskId
            proxyWeb = $proxyWebTaskId
        }
        javaMatchesPython = ($javaStable -eq $pythonStable)
        pythonMatchesProxy = ($pythonStable -eq $proxyStable)
        pythonMatchesProxyWeb = ($pythonStable -eq $proxyWebStable)
        unauthenticatedStatus = $unauthenticatedStatus
        downloadCounts = $counts
        checks = [ordered]@{
            downloadsMatch = ($javaStable -eq $pythonStable -and $pythonStable -eq $proxyStable -and $pythonStable -eq $proxyWebStable)
            unauthenticatedRejected = ($unauthenticatedStatus -eq 401)
            countersUnchanged = ($counts.java -eq '0' -and $counts.python -eq '0' -and $counts.proxy -eq '0' -and $counts.proxyWeb -eq '0')
        }
        stable = [ordered]@{
            java = $javaStable
            python = $pythonStable
            proxy = $proxyStable
            proxyWeb = $proxyWebStable
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.downloadsMatch -or -not $result.checks.unauthenticatedRejected -or -not $result.checks.countersUnchanged) {
        throw "Review download contract check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridReviewDownloadSmokeVerification {
    try {
        Invoke-ReviewDownloadTests
        Start-Hybrid
        Invoke-ReviewDownloadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-PromotionReadTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_promotion_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StablePromotionContractJson {
    param([object]$Response)

    $data = $Response.data
    if ($null -ne $data.items) {
        $items = @()
        foreach ($item in $data.items) {
            $items += [ordered]@{
                sourceNamespace = $item.sourceNamespace
                sourceSkillSlug = ($(if ($item.sourceSkillSlug -match '^(java|python|proxy|proxy-web)-promotion-read-') { 'promotion-read-fixture' } else { $item.sourceSkillSlug }))
                sourceVersion = $item.sourceVersion
                targetNamespace = $item.targetNamespace
                targetSkillId = $item.targetSkillId
                status = $item.status
                submittedBy = ($(if ($item.submittedBy -match '^codex-promotion-read-submitter-') { 'promotion-read-submitter' } else { $item.submittedBy }))
                submittedByName = $item.submittedByName
                reviewedBy = $item.reviewedBy
                reviewedByName = $item.reviewedByName
                reviewComment = $item.reviewComment
            }
        }
        $items = @($items | Sort-Object { $_['sourceNamespace'] }, { $_['sourceSkillSlug'] }, { $_['submittedBy'] })
        $stableData = [ordered]@{
            total = $data.total
            page = $data.page
            size = $data.size
            itemCount = @($data.items).Count
            items = $items
        }
    } else {
        $stableData = [ordered]@{
            sourceNamespace = $data.sourceNamespace
            sourceSkillSlug = ($(if ($data.sourceSkillSlug -match '^(java|python|proxy|proxy-web)-promotion-read-') { 'promotion-read-fixture' } else { $data.sourceSkillSlug }))
            sourceVersion = $data.sourceVersion
            targetNamespace = $data.targetNamespace
            targetSkillId = $data.targetSkillId
            status = $data.status
            submittedBy = ($(if ($data.submittedBy -match '^codex-promotion-read-submitter-') { 'promotion-read-submitter' } else { $data.submittedBy }))
            submittedByName = $data.submittedByName
            reviewedBy = $data.reviewedBy
            reviewedByName = $data.reviewedByName
            reviewComment = $data.reviewComment
        }
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $stableData
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-PromotionReadContractComparison {
    param([string]$ResultFileName = 'promotion-read-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $sourceNamespace = "codex-promotion-read-$suffix"
    $reviewerId = "codex-promotion-read-admin-$suffix"
    $submitterId = "codex-promotion-read-submitter-$suffix"
    $slugs = @(
        "java-promotion-read-$suffix",
        "python-promotion-read-$suffix",
        "proxy-promotion-read-$suffix",
        "proxy-web-promotion-read-$suffix"
    )

    $valuesSql = ($slugs | ForEach-Object { "(source_ns_id, '$($_)', 'Promotion Read', 'Promotion read contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "
    $sql = @"
DO `$`$
DECLARE
    source_ns_id BIGINT;
    target_ns_id BIGINT;
    skill_admin_role_id BIGINT;
    skill_row RECORD;
    source_version_id BIGINT;
BEGIN
    INSERT INTO role (code, name, description, is_system)
    VALUES ('SKILL_ADMIN', 'Skill Admin', 'Skill review administrator', TRUE)
    ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO skill_admin_role_id;

    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$reviewerId', 'Codex Promotion Admin', 'ACTIVE'),
        ('$submitterId', 'Codex Promotion Submitter', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES ('$reviewerId', skill_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$sourceNamespace', 'Codex Promotion Source', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO source_ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO target_ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at, bundle_ready,
            download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED',
            jsonb_build_object('name', 'Promotion Read', 'description', 'Promotion read contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 80, '2026-06-09T09:00:00Z'::timestamptz, '$submitterId',
            '2026-06-09T08:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO source_version_id;

        UPDATE skill SET latest_version_id = source_version_id WHERE id = skill_row.id;

        INSERT INTO promotion_request (
            source_skill_id, source_version_id, target_namespace_id, status, version,
            submitted_by, submitted_at
        )
        VALUES (
            skill_row.id, source_version_id, target_ns_id, 'PENDING', 1,
            '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute'
        );
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-PromotionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT pr.id FROM promotion_request pr JOIN skill s ON s.id = pr.source_skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$sourceNamespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaPromotionId = Get-PromotionId $slugs[0]
    $pythonPromotionId = Get-PromotionId $slugs[1]
    $proxyPromotionId = Get-PromotionId $slugs[2]
    $proxyWebPromotionId = Get-PromotionId $slugs[3]

    $listPath = "/api/v1/promotions?status=PENDING&page=0&size=20"
    $webListPath = "/api/web/promotions?status=PENDING&page=0&size=20"
    $pendingPath = "/api/v1/promotions/pending?page=0&size=20"
    $webPendingPath = "/api/web/promotions/pending?page=0&size=20"

    $javaList = Invoke-ReviewListGetJson "$JavaUrl$listPath" $reviewerId
    $pythonList = Invoke-ReviewListGetJson "$PythonUrl$listPath" $reviewerId
    $proxyList = Invoke-ReviewListGetJson "$WebUrl$listPath" $reviewerId
    $proxyWebList = Invoke-ReviewListGetJson "$WebUrl$webListPath" $reviewerId

    $javaPending = Invoke-ReviewListGetJson "$JavaUrl$pendingPath" $reviewerId
    $pythonPending = Invoke-ReviewListGetJson "$PythonUrl$pendingPath" $reviewerId
    $proxyPending = Invoke-ReviewListGetJson "$WebUrl$pendingPath" $reviewerId
    $proxyWebPending = Invoke-ReviewListGetJson "$WebUrl$webPendingPath" $reviewerId

    $javaDetail = Invoke-ReviewListGetJson "$JavaUrl/api/v1/promotions/$javaPromotionId" $reviewerId
    $pythonDetail = Invoke-ReviewListGetJson "$PythonUrl/api/v1/promotions/$pythonPromotionId" $reviewerId
    $proxyDetail = Invoke-ReviewListGetJson "$WebUrl/api/v1/promotions/$proxyPromotionId" $reviewerId
    $proxyWebDetail = Invoke-ReviewListGetJson "$WebUrl/api/web/promotions/$proxyWebPromotionId" $reviewerId

    $stable = [ordered]@{
        list = [ordered]@{
            java = ConvertTo-StablePromotionContractJson -Response $javaList
            python = ConvertTo-StablePromotionContractJson -Response $pythonList
            proxy = ConvertTo-StablePromotionContractJson -Response $proxyList
            proxyWeb = ConvertTo-StablePromotionContractJson -Response $proxyWebList
        }
        pending = [ordered]@{
            java = ConvertTo-StablePromotionContractJson -Response $javaPending
            python = ConvertTo-StablePromotionContractJson -Response $pythonPending
            proxy = ConvertTo-StablePromotionContractJson -Response $proxyPending
            proxyWeb = ConvertTo-StablePromotionContractJson -Response $proxyWebPending
        }
        detail = [ordered]@{
            java = ConvertTo-StablePromotionContractJson -Response $javaDetail
            python = ConvertTo-StablePromotionContractJson -Response $pythonDetail
            proxy = ConvertTo-StablePromotionContractJson -Response $proxyDetail
            proxyWeb = ConvertTo-StablePromotionContractJson -Response $proxyWebDetail
        }
    }

    $submitProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions" -Method 'POST'
    $approveProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions/$proxyPromotionId/approve" -Method 'POST'
    $rejectProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/web/promotions/$proxyWebPromotionId/reject" -Method 'POST'
    $unauthenticatedStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions" -Method 'GET'

    $result = [ordered]@{
        namespace = $sourceNamespace
        promotionIds = [ordered]@{
            java = $javaPromotionId
            python = $pythonPromotionId
            proxy = $proxyPromotionId
            proxyWeb = $proxyWebPromotionId
        }
        javaOwnedBoundaries = [ordered]@{
            submitStatus = $submitProxyStatus
            approveStatus = $approveProxyStatus
            rejectStatus = $rejectProxyStatus
        }
        unauthenticatedStatus = $unauthenticatedStatus
        checks = [ordered]@{
            listResponsesMatch = ($stable.list.java -eq $stable.list.python -and $stable.list.python -eq $stable.list.proxy -and $stable.list.python -eq $stable.list.proxyWeb)
            pendingResponsesMatch = ($stable.pending.java -eq $stable.pending.python -and $stable.pending.python -eq $stable.pending.proxy -and $stable.pending.python -eq $stable.pending.proxyWeb)
            detailResponsesMatch = ($stable.detail.java -eq $stable.detail.python -and $stable.detail.python -eq $stable.detail.proxy -and $stable.detail.python -eq $stable.detail.proxyWeb)
            unauthenticatedRejected = ($unauthenticatedStatus -eq 401)
            writesRemainJavaOwned = ($submitProxyStatus -ne 404 -and $approveProxyStatus -ne 404 -and $rejectProxyStatus -ne 404)
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.checks.listResponsesMatch -or -not $result.checks.pendingResponsesMatch -or -not $result.checks.detailResponsesMatch) {
        throw "Promotion read response contract check failed. See .dev/$ResultFileName."
    }
    if (-not $result.checks.unauthenticatedRejected -or -not $result.checks.writesRemainJavaOwned) {
        throw "Promotion read route boundary check failed. See .dev/$ResultFileName."
    }
}

function Invoke-HybridPromotionReadSmokeVerification {
    try {
        Invoke-PromotionReadTests
        Start-Hybrid
        Invoke-PromotionReadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-PromotionSubmitRejectTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_promotion_write.py', 'tests/test_promotion_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-PromotionSubmitPostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$SourceSkillId,
        [string]$SourceVersionId,
        [string]$TargetNamespaceId
    )

    $body = @{
        sourceSkillId = [int64]$SourceSkillId
        sourceVersionId = [int64]$SourceVersionId
        targetNamespaceId = [int64]$TargetNamespaceId
    } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function ConvertTo-StablePromotionWriteContractJson {
    param(
        [object]$Response,
        [string]$SlugPrefix
    )

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            sourceNamespace = $Response.data.sourceNamespace
            sourceSkillSlug = ($(if ($Response.data.sourceSkillSlug -match "^$SlugPrefix") { 'promotion-write-fixture' } else { $Response.data.sourceSkillSlug }))
            sourceVersion = $Response.data.sourceVersion
            targetNamespace = $Response.data.targetNamespace
            targetSkillId = $Response.data.targetSkillId
            status = $Response.data.status
            submittedBy = $Response.data.submittedBy
            submittedByName = $Response.data.submittedByName
            reviewedBy = $Response.data.reviewedBy
            reviewedByName = $Response.data.reviewedByName
            reviewComment = $Response.data.reviewComment
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-PromotionSubmitRejectContractComparison {
    param([string]$ResultFileName = 'promotion-submit-reject-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $sourceNamespace = "codex-promotion-write-$suffix"
    $submitterId = "codex-promotion-write-submitter-$suffix"
    $reviewerId = "codex-promotion-write-admin-$suffix"
    $comment = "reject-$suffix"
    $submitSlugs = @(
        "java-promotion-submit-$suffix",
        "python-promotion-submit-$suffix",
        "proxy-promotion-submit-$suffix",
        "proxy-web-promotion-submit-$suffix"
    )
    $rejectSlugs = @(
        "java-promotion-reject-$suffix",
        "python-promotion-reject-$suffix",
        "proxy-promotion-reject-$suffix",
        "proxy-web-promotion-reject-$suffix"
    )
    $allSlugs = @($submitSlugs + $rejectSlugs)
    $valuesSql = ($allSlugs | ForEach-Object { "(source_ns_id, '$($_)', 'Promotion Write', 'Promotion write contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    source_ns_id BIGINT;
    target_ns_id BIGINT;
    skill_admin_role_id BIGINT;
    skill_row RECORD;
    source_version_id BIGINT;
BEGIN
    INSERT INTO role (code, name, description, is_system)
    VALUES ('SKILL_ADMIN', 'Skill Admin', 'Skill review administrator', TRUE)
    ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO skill_admin_role_id;

    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$submitterId', 'Codex Promotion Submitter', 'ACTIVE'),
        ('$reviewerId', 'Codex Promotion Admin', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES ('$reviewerId', skill_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$sourceNamespace', 'Codex Promotion Write Source', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO source_ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO target_ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at, bundle_ready,
            download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED',
            jsonb_build_object('name', 'Promotion Write', 'description', 'Promotion write contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 80, '2026-06-09T09:00:00Z'::timestamptz, '$submitterId',
            '2026-06-09T08:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO source_version_id;

        UPDATE skill SET latest_version_id = source_version_id WHERE id = skill_row.id;

        IF skill_row.slug LIKE '%promotion-reject-%' THEN
            INSERT INTO promotion_request (
                source_skill_id, source_version_id, target_namespace_id, status, version,
                submitted_by, submitted_at
            )
            VALUES (
                skill_row.id, source_version_id, target_ns_id, 'PENDING', 1,
                '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute'
            );
        END IF;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $targetNamespaceId = Invoke-PostgresScalar -Sql "SELECT id FROM namespace WHERE slug = 'global' LIMIT 1;"

    function Get-SkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$sourceNamespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-VersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$sourceNamespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-PromotionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT pr.id FROM promotion_request pr JOIN skill s ON s.id = pr.source_skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$sourceNamespace' AND s.slug = '$Slug' LIMIT 1;"
    }

    $javaSubmit = Invoke-PromotionSubmitPostJson "$JavaUrl/api/v1/promotions" $submitterId (Get-SkillId $submitSlugs[0]) (Get-VersionId $submitSlugs[0]) $targetNamespaceId
    $pythonSubmit = Invoke-PromotionSubmitPostJson "$PythonUrl/api/v1/promotions" $submitterId (Get-SkillId $submitSlugs[1]) (Get-VersionId $submitSlugs[1]) $targetNamespaceId
    $proxySubmit = Invoke-PromotionSubmitPostJson "$WebUrl/api/v1/promotions" $submitterId (Get-SkillId $submitSlugs[2]) (Get-VersionId $submitSlugs[2]) $targetNamespaceId
    $proxyWebSubmit = Invoke-PromotionSubmitPostJson "$WebUrl/api/web/promotions" $submitterId (Get-SkillId $submitSlugs[3]) (Get-VersionId $submitSlugs[3]) $targetNamespaceId

    $javaRejectId = Get-PromotionId $rejectSlugs[0]
    $pythonRejectId = Get-PromotionId $rejectSlugs[1]
    $proxyRejectId = Get-PromotionId $rejectSlugs[2]
    $proxyWebRejectId = Get-PromotionId $rejectSlugs[3]

    $javaReject = Invoke-ReviewApprovePostJson "$JavaUrl/api/v1/promotions/$javaRejectId/reject" $reviewerId $comment
    $pythonReject = Invoke-ReviewApprovePostJson "$PythonUrl/api/v1/promotions/$pythonRejectId/reject" $reviewerId $comment
    $proxyReject = Invoke-ReviewApprovePostJson "$WebUrl/api/v1/promotions/$proxyRejectId/reject" $reviewerId $comment
    $proxyWebReject = Invoke-ReviewApprovePostJson "$WebUrl/api/web/promotions/$proxyWebRejectId/reject" $reviewerId $comment

    function Get-PromotionDbState([string]$PromotionId) {
        return Invoke-PostgresScalar -Sql "SELECT status || '|' || submitted_by || '|' || COALESCE(reviewed_by, '') || '|' || COALESCE(review_comment, '') FROM promotion_request WHERE id = $PromotionId;"
    }
    function Get-PromotionAudit([string]$PromotionId, [string]$Action) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'PROMOTION_REQUEST' AND target_id = $PromotionId AND action = '$Action' ORDER BY created_at DESC LIMIT 1;"
    }
    function Get-PromotionNotification([string]$PromotionId) {
        return Invoke-PostgresScalar -Sql "SELECT user_id || '|' || category || '|' || entity_type || '|' || entity_id || '|' || title || '|' || body_json::text FROM user_notification WHERE entity_type = 'PROMOTION_REQUEST' AND entity_id = '$PromotionId' ORDER BY created_at DESC LIMIT 1;"
    }

    $pythonSubmitId = [string]$pythonSubmit.data.id
    $proxySubmitId = [string]$proxySubmit.data.id
    $pythonRejectIdString = [string]$pythonRejectId
    $proxyRejectIdString = [string]$proxyRejectId
    $proxyWebRejectIdString = [string]$proxyWebRejectId

    $approveProxyStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions/$proxyRejectId/approve" -Method 'POST'
    $unauthenticatedSubmitStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions" -Method 'POST'
    $unauthenticatedRejectStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions/$proxyRejectId/reject" -Method 'POST'

    $stable = [ordered]@{
        submit = [ordered]@{
            java = ConvertTo-StablePromotionWriteContractJson -Response $javaSubmit -SlugPrefix '(java|python|proxy|proxy-web)-promotion-submit-'
            python = ConvertTo-StablePromotionWriteContractJson -Response $pythonSubmit -SlugPrefix '(java|python|proxy|proxy-web)-promotion-submit-'
            proxy = ConvertTo-StablePromotionWriteContractJson -Response $proxySubmit -SlugPrefix '(java|python|proxy|proxy-web)-promotion-submit-'
            proxyWeb = ConvertTo-StablePromotionWriteContractJson -Response $proxyWebSubmit -SlugPrefix '(java|python|proxy|proxy-web)-promotion-submit-'
        }
        reject = [ordered]@{
            java = ConvertTo-StablePromotionWriteContractJson -Response $javaReject -SlugPrefix '(java|python|proxy|proxy-web)-promotion-reject-'
            python = ConvertTo-StablePromotionWriteContractJson -Response $pythonReject -SlugPrefix '(java|python|proxy|proxy-web)-promotion-reject-'
            proxy = ConvertTo-StablePromotionWriteContractJson -Response $proxyReject -SlugPrefix '(java|python|proxy|proxy-web)-promotion-reject-'
            proxyWeb = ConvertTo-StablePromotionWriteContractJson -Response $proxyWebReject -SlugPrefix '(java|python|proxy|proxy-web)-promotion-reject-'
        }
    }

    $result = [ordered]@{
        namespace = $sourceNamespace
        checks = [ordered]@{
            submitResponsesMatch = ($stable.submit.java -eq $stable.submit.python -and $stable.submit.python -eq $stable.submit.proxy -and $stable.submit.python -eq $stable.submit.proxyWeb)
            rejectResponsesMatch = ($stable.reject.java -eq $stable.reject.python -and $stable.reject.python -eq $stable.reject.proxy -and $stable.reject.python -eq $stable.reject.proxyWeb)
            submitDbState = ((Get-PromotionDbState $pythonSubmitId) -eq "PENDING|$submitterId||" -and (Get-PromotionDbState ([string]$proxySubmit.data.id)) -eq "PENDING|$submitterId||" -and (Get-PromotionDbState ([string]$proxyWebSubmit.data.id)) -eq "PENDING|$submitterId||")
            rejectDbState = ((Get-PromotionDbState $pythonRejectIdString) -eq "REJECTED|$submitterId|$reviewerId|$comment" -and (Get-PromotionDbState $proxyRejectIdString) -eq "REJECTED|$submitterId|$reviewerId|$comment" -and (Get-PromotionDbState $proxyWebRejectIdString) -eq "REJECTED|$submitterId|$reviewerId|$comment")
            submitAudit = ((Get-PromotionAudit $pythonSubmitId 'PROMOTION_SUBMIT') -like "PROMOTION_SUBMIT|PROMOTION_REQUEST|$pythonSubmitId|$submitterId|*" -and (Get-PromotionAudit $proxySubmitId 'PROMOTION_SUBMIT') -like "PROMOTION_SUBMIT|PROMOTION_REQUEST|$proxySubmitId|$submitterId|*")
            rejectAudit = ((Get-PromotionAudit $pythonRejectIdString 'PROMOTION_REJECT') -like "PROMOTION_REJECT|PROMOTION_REQUEST|$pythonRejectIdString|$reviewerId|*" -and (Get-PromotionAudit $proxyRejectIdString 'PROMOTION_REJECT') -like "PROMOTION_REJECT|PROMOTION_REQUEST|$proxyRejectIdString|$reviewerId|*")
            rejectNotification = ((Get-PromotionNotification $pythonRejectIdString) -like "$submitterId|PROMOTION|PROMOTION_REQUEST|$pythonRejectIdString|Promotion rejected|*" -and (Get-PromotionNotification $proxyRejectIdString) -like "$submitterId|PROMOTION|PROMOTION_REQUEST|$proxyRejectIdString|Promotion rejected|*")
            approveRemainsJavaOwned = ($approveProxyStatus -ne 404)
            unauthenticatedSubmitRejected = ($unauthenticatedSubmitStatus -eq 401)
            unauthenticatedRejectRejected = ($unauthenticatedRejectStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            approveProxyStatus = $approveProxyStatus
            unauthenticatedSubmitStatus = $unauthenticatedSubmitStatus
            unauthenticatedRejectStatus = $unauthenticatedRejectStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Promotion submit/reject contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridPromotionSubmitRejectSmokeVerification {
    try {
        Invoke-PromotionSubmitRejectTests
        Start-Hybrid
        Invoke-PromotionSubmitRejectContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-PromotionApproveTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_promotion_write.py', 'tests/test_promotion_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StablePromotionApproveContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            sourceNamespace = $Response.data.sourceNamespace
            sourceSkillSlug = ($(if ($Response.data.sourceSkillSlug -match '^(java|python|proxy|proxy-web)-promotion-approve-') { 'promotion-approve-fixture' } else { $Response.data.sourceSkillSlug }))
            sourceVersion = $Response.data.sourceVersion
            targetNamespace = $Response.data.targetNamespace
            targetSkillCreated = ($null -ne $Response.data.targetSkillId)
            status = $Response.data.status
            submittedBy = $Response.data.submittedBy
            submittedByName = $Response.data.submittedByName
            reviewedBy = $Response.data.reviewedBy
            reviewedByName = $Response.data.reviewedByName
            reviewComment = $Response.data.reviewComment
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-PromotionApproveContractComparison {
    param([string]$ResultFileName = 'promotion-approve-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $sourceNamespace = "codex-promotion-approve-$suffix"
    $submitterId = "codex-promotion-approve-submitter-$suffix"
    $reviewerId = "codex-promotion-approve-admin-$suffix"
    $comment = "approve-$suffix"
    $slugs = @(
        "java-promotion-approve-$suffix",
        "python-promotion-approve-$suffix",
        "proxy-promotion-approve-$suffix",
        "proxy-web-promotion-approve-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(source_ns_id, '$($_)', 'Promotion Approve', 'Promotion approve contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    source_ns_id BIGINT;
    target_ns_id BIGINT;
    skill_admin_role_id BIGINT;
    skill_row RECORD;
    source_version_id BIGINT;
BEGIN
    INSERT INTO role (code, name, description, is_system)
    VALUES ('SKILL_ADMIN', 'Skill Admin', 'Skill review administrator', TRUE)
    ON CONFLICT (code) DO UPDATE SET name = EXCLUDED.name
    RETURNING id INTO skill_admin_role_id;

    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$submitterId', 'Codex Promotion Submitter', 'ACTIVE'),
        ('$reviewerId', 'Codex Promotion Admin', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES ('$reviewerId', skill_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$sourceNamespace', 'Codex Promotion Approve Source', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO source_ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('global', 'Global', 'GLOBAL', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO target_ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at, bundle_ready,
            download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED', 'Initial',
            jsonb_build_object('name', 'Promotion Approve', 'description', 'Promotion approve contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/main.py')),
            2, 120, '2026-06-09T09:00:00Z'::timestamptz, '$submitterId',
            '2026-06-09T08:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO source_version_id;

        UPDATE skill SET latest_version_id = source_version_id WHERE id = skill_row.id;

        INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key, created_at)
        VALUES
            (source_version_id, 'SKILL.md', 80, 'text/markdown', 'sha-skill-' || skill_row.slug, 'skills/' || skill_row.id || '/' || source_version_id || '/SKILL.md', CURRENT_TIMESTAMP),
            (source_version_id, 'src/main.py', 40, 'text/x-python', 'sha-main-' || skill_row.slug, 'skills/' || skill_row.id || '/' || source_version_id || '/src/main.py', CURRENT_TIMESTAMP);

        INSERT INTO promotion_request (
            source_skill_id, source_version_id, target_namespace_id, status, version,
            submitted_by, submitted_at
        )
        VALUES (
            skill_row.id, source_version_id, target_ns_id, 'PENDING', 1,
            '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute'
        );
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-PromotionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT pr.id FROM promotion_request pr JOIN skill s ON s.id = pr.source_skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$sourceNamespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-TargetSkillId([string]$PromotionId) {
        return Invoke-PostgresScalar -Sql "SELECT target_skill_id FROM promotion_request WHERE id = $PromotionId;"
    }
    function Get-ApprovalPromotionDbState([string]$PromotionId) {
        return Invoke-PostgresScalar -Sql "SELECT status || '|' || submitted_by || '|' || COALESCE(reviewed_by, '') || '|' || COALESCE(review_comment, '') || '|' || (target_skill_id IS NOT NULL) FROM promotion_request WHERE id = $PromotionId;"
    }
    function Get-TargetSkillState([string]$TargetSkillId) {
        return Invoke-PostgresScalar -Sql "SELECT tn.slug || '|' || ts.slug || '|' || ts.visibility || '|' || ts.status || '|' || ts.owner_id || '|' || (ts.source_skill_id IS NOT NULL) || '|' || (ts.latest_version_id IS NOT NULL) || '|' || ts.display_name || '|' || ts.summary FROM skill ts JOIN namespace tn ON tn.id = ts.namespace_id WHERE ts.id = $TargetSkillId;"
    }
    function Get-TargetVersionState([string]$TargetSkillId) {
        return Invoke-PostgresScalar -Sql "SELECT version || '|' || status || '|' || requested_visibility || '|' || file_count || '|' || total_size || '|' || bundle_ready || '|' || download_ready || '|' || COALESCE(changelog, '') FROM skill_version WHERE skill_id = $TargetSkillId ORDER BY id DESC LIMIT 1;"
    }
    function Get-TargetFileState([string]$TargetSkillId) {
        return Invoke-PostgresScalar -Sql "SELECT COUNT(*) || '|' || bool_and(sf.storage_key LIKE 'skills/%') || '|' || string_agg(sf.file_path, ',' ORDER BY sf.file_path) FROM skill_file sf JOIN skill_version sv ON sv.id = sf.version_id WHERE sv.skill_id = $TargetSkillId;"
    }
    function Get-PromotionAudit([string]$PromotionId, [string]$Action) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'PROMOTION_REQUEST' AND target_id = $PromotionId AND action = '$Action' ORDER BY created_at DESC LIMIT 1;"
    }
    function Get-PromotionNotification([string]$PromotionId) {
        return Invoke-PostgresScalar -Sql "SELECT user_id || '|' || category || '|' || entity_type || '|' || entity_id || '|' || title || '|' || body_json::text FROM user_notification WHERE entity_type = 'PROMOTION_REQUEST' AND entity_id = '$PromotionId' ORDER BY created_at DESC LIMIT 1;"
    }

    $javaPromotionId = Get-PromotionId $slugs[0]
    $pythonPromotionId = Get-PromotionId $slugs[1]
    $proxyPromotionId = Get-PromotionId $slugs[2]
    $proxyWebPromotionId = Get-PromotionId $slugs[3]

    $java = Invoke-ReviewApprovePostJson "$JavaUrl/api/v1/promotions/$javaPromotionId/approve" $reviewerId $comment
    $python = Invoke-ReviewApprovePostJson "$PythonUrl/api/v1/promotions/$pythonPromotionId/approve" $reviewerId $comment
    $proxy = Invoke-ReviewApprovePostJson "$WebUrl/api/v1/promotions/$proxyPromotionId/approve" $reviewerId $comment
    $proxyWeb = Invoke-ReviewApprovePostJson "$WebUrl/api/web/promotions/$proxyWebPromotionId/approve" $reviewerId $comment

    $pythonTargetSkillId = Get-TargetSkillId $pythonPromotionId
    $proxyTargetSkillId = Get-TargetSkillId $proxyPromotionId
    $proxyWebTargetSkillId = Get-TargetSkillId $proxyWebPromotionId

    $unauthenticatedStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/promotions/$proxyPromotionId/approve" -Method 'POST'

    $stable = [ordered]@{
        java = ConvertTo-StablePromotionApproveContractJson -Response $java
        python = ConvertTo-StablePromotionApproveContractJson -Response $python
        proxy = ConvertTo-StablePromotionApproveContractJson -Response $proxy
        proxyWeb = ConvertTo-StablePromotionApproveContractJson -Response $proxyWeb
    }

    $result = [ordered]@{
        namespace = $sourceNamespace
        promotionIds = [ordered]@{
            java = $javaPromotionId
            python = $pythonPromotionId
            proxy = $proxyPromotionId
            proxyWeb = $proxyWebPromotionId
        }
        targetSkillIds = [ordered]@{
            python = $pythonTargetSkillId
            proxy = $proxyTargetSkillId
            proxyWeb = $proxyWebTargetSkillId
        }
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            approvalDbState = ((Get-ApprovalPromotionDbState $pythonPromotionId) -eq "APPROVED|$submitterId|$reviewerId|$comment|true" -and (Get-ApprovalPromotionDbState $proxyPromotionId) -eq "APPROVED|$submitterId|$reviewerId|$comment|true" -and (Get-ApprovalPromotionDbState $proxyWebPromotionId) -eq "APPROVED|$submitterId|$reviewerId|$comment|true")
            targetSkillState = ((Get-TargetSkillState $pythonTargetSkillId) -like "global|python-promotion-approve-$suffix|PUBLIC|ACTIVE|$submitterId|true|true|Promotion Approve|Promotion approve contract" -and (Get-TargetSkillState $proxyTargetSkillId) -like "global|proxy-promotion-approve-$suffix|PUBLIC|ACTIVE|$submitterId|true|true|Promotion Approve|Promotion approve contract" -and (Get-TargetSkillState $proxyWebTargetSkillId) -like "global|proxy-web-promotion-approve-$suffix|PUBLIC|ACTIVE|$submitterId|true|true|Promotion Approve|Promotion approve contract")
            targetVersionState = ((Get-TargetVersionState $pythonTargetSkillId) -eq "1.0.0|PUBLISHED|PUBLIC|2|120|true|true|Initial" -and (Get-TargetVersionState $proxyTargetSkillId) -eq "1.0.0|PUBLISHED|PUBLIC|2|120|true|true|Initial" -and (Get-TargetVersionState $proxyWebTargetSkillId) -eq "1.0.0|PUBLISHED|PUBLIC|2|120|true|true|Initial")
            targetFileState = ((Get-TargetFileState $pythonTargetSkillId) -eq "2|true|SKILL.md,src/main.py" -and (Get-TargetFileState $proxyTargetSkillId) -eq "2|true|SKILL.md,src/main.py" -and (Get-TargetFileState $proxyWebTargetSkillId) -eq "2|true|SKILL.md,src/main.py")
            approveAudit = ((Get-PromotionAudit $pythonPromotionId 'PROMOTION_APPROVE') -like "PROMOTION_APPROVE|PROMOTION_REQUEST|$pythonPromotionId|$reviewerId|*" -and (Get-PromotionAudit $proxyPromotionId 'PROMOTION_APPROVE') -like "PROMOTION_APPROVE|PROMOTION_REQUEST|$proxyPromotionId|$reviewerId|*")
            approveNotification = ((Get-PromotionNotification $pythonPromotionId) -like "$submitterId|PROMOTION|PROMOTION_REQUEST|$pythonPromotionId|Promotion approved|*" -and (Get-PromotionNotification $proxyPromotionId) -like "$submitterId|PROMOTION|PROMOTION_REQUEST|$proxyPromotionId|Promotion approved|*")
            unauthenticatedRejected = ($unauthenticatedStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            unauthenticatedStatus = $unauthenticatedStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Promotion approve contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridPromotionApproveSmokeVerification {
    try {
        Invoke-PromotionApproveTests
        Start-Hybrid
        Invoke-PromotionApproveContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillLifecycleArchiveTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillLifecycleArchivePostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$Reason
    )

    $body = @{ reason = $Reason } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function Invoke-SkillLifecycleUnarchivePostJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId }
}

function ConvertTo-StableSkillLifecycleContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionId = $Response.data.versionId
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillLifecycleArchiveContractComparison {
    param([string]$ResultFileName = 'skill-lifecycle-archive-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-lifecycle-$suffix"
    $ownerId = "codex-lifecycle-owner-$suffix"
    $managerId = "codex-lifecycle-admin-$suffix"
    $actorId = $ownerId
    $reason = "archive-$suffix"
    $archiveSlugs = @(
        "java-archive-$suffix",
        "python-archive-$suffix",
        "proxy-archive-$suffix",
        "proxy-web-archive-$suffix"
    )
    $unarchiveSlugs = @(
        "java-unarchive-$suffix",
        "python-unarchive-$suffix",
        "proxy-unarchive-$suffix",
        "proxy-web-unarchive-$suffix"
    )
    $archiveValuesSql = ($archiveSlugs | ForEach-Object { "(ns_id, '$($_)', 'Lifecycle Archive', 'Lifecycle archive contract', '$ownerId', 'NAMESPACE_ONLY', 'ACTIVE', '$ownerId', '$ownerId')" }) -join ",`n        "
    $unarchiveValuesSql = ($unarchiveSlugs | ForEach-Object { "(ns_id, '$($_)', 'Lifecycle Unarchive', 'Lifecycle unarchive contract', '$ownerId', 'NAMESPACE_ONLY', 'ARCHIVED', '$ownerId', '$ownerId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES
        ('$ownerId', 'Codex Lifecycle Owner', 'ACTIVE'),
        ('$managerId', 'Codex Lifecycle Admin', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Lifecycle', 'TEAM', 'ACTIVE', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$managerId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES
        $archiveValuesSql,
        $unarchiveValuesSql;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-SkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-SkillLifecycleState([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.status || '|' || COALESCE(s.updated_by, '') FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-SkillLifecycleAudit([string]$SkillId, [string]$Action) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL' AND target_id = $SkillId AND action = '$Action' ORDER BY created_at DESC LIMIT 1;"
    }

    $javaArchive = Invoke-SkillLifecycleArchivePostJson "$JavaUrl/api/v1/skills/$namespace/$($archiveSlugs[0])/archive" $actorId $reason
    $pythonArchive = Invoke-SkillLifecycleArchivePostJson "$PythonUrl/api/v1/skills/$namespace/$($archiveSlugs[1])/archive" $actorId $reason
    $proxyArchive = Invoke-SkillLifecycleArchivePostJson "$WebUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/archive" $actorId $reason
    $proxyWebArchive = Invoke-SkillLifecycleArchivePostJson "$WebUrl/api/web/skills/$namespace/$($archiveSlugs[3])/archive" $actorId $reason

    $javaUnarchive = Invoke-SkillLifecycleUnarchivePostJson "$JavaUrl/api/v1/skills/$namespace/$($unarchiveSlugs[0])/unarchive" $actorId
    $pythonUnarchive = Invoke-SkillLifecycleUnarchivePostJson "$PythonUrl/api/v1/skills/$namespace/$($unarchiveSlugs[1])/unarchive" $actorId
    $proxyUnarchive = Invoke-SkillLifecycleUnarchivePostJson "$WebUrl/api/v1/skills/$namespace/$($unarchiveSlugs[2])/unarchive" $actorId
    $proxyWebUnarchive = Invoke-SkillLifecycleUnarchivePostJson "$WebUrl/api/web/skills/$namespace/$($unarchiveSlugs[3])/unarchive" $actorId

    $pythonArchiveSkillId = Get-SkillId $archiveSlugs[1]
    $proxyArchiveSkillId = Get-SkillId $archiveSlugs[2]
    $proxyWebArchiveSkillId = Get-SkillId $archiveSlugs[3]
    $pythonUnarchiveSkillId = Get-SkillId $unarchiveSlugs[1]
    $proxyUnarchiveSkillId = Get-SkillId $unarchiveSlugs[2]
    $proxyWebUnarchiveSkillId = Get-SkillId $unarchiveSlugs[3]

    $deleteVersionBoundaryJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/versions/1.0.0" -Method 'DELETE'
    $deleteVersionBoundaryProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/versions/1.0.0" -Method 'DELETE'
    $rereleaseBoundaryJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/versions/1.0.0/rerelease" -Method 'POST'
    $rereleaseBoundaryProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/versions/1.0.0/rerelease" -Method 'POST'
    $unauthenticatedArchiveStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($archiveSlugs[2])/archive" -Method 'POST'

    $stableArchive = [ordered]@{
        java = ConvertTo-StableSkillLifecycleContractJson -Response $javaArchive
        python = ConvertTo-StableSkillLifecycleContractJson -Response $pythonArchive
        proxy = ConvertTo-StableSkillLifecycleContractJson -Response $proxyArchive
        proxyWeb = ConvertTo-StableSkillLifecycleContractJson -Response $proxyWebArchive
    }
    $stableUnarchive = [ordered]@{
        java = ConvertTo-StableSkillLifecycleContractJson -Response $javaUnarchive
        python = ConvertTo-StableSkillLifecycleContractJson -Response $pythonUnarchive
        proxy = ConvertTo-StableSkillLifecycleContractJson -Response $proxyUnarchive
        proxyWeb = ConvertTo-StableSkillLifecycleContractJson -Response $proxyWebUnarchive
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            archiveResponsesMatch = ($stableArchive.java -eq $stableArchive.python -and $stableArchive.python -eq $stableArchive.proxy -and $stableArchive.python -eq $stableArchive.proxyWeb)
            unarchiveResponsesMatch = ($stableUnarchive.java -eq $stableUnarchive.python -and $stableUnarchive.python -eq $stableUnarchive.proxy -and $stableUnarchive.python -eq $stableUnarchive.proxyWeb)
            archiveDbState = ((Get-SkillLifecycleState $archiveSlugs[1]) -eq "ARCHIVED|$actorId" -and (Get-SkillLifecycleState $archiveSlugs[2]) -eq "ARCHIVED|$actorId" -and (Get-SkillLifecycleState $archiveSlugs[3]) -eq "ARCHIVED|$actorId")
            unarchiveDbState = ((Get-SkillLifecycleState $unarchiveSlugs[1]) -eq "ACTIVE|$actorId" -and (Get-SkillLifecycleState $unarchiveSlugs[2]) -eq "ACTIVE|$actorId" -and (Get-SkillLifecycleState $unarchiveSlugs[3]) -eq "ACTIVE|$actorId")
            archiveAudit = ((Get-SkillLifecycleAudit $pythonArchiveSkillId 'ARCHIVE_SKILL') -like "ARCHIVE_SKILL|SKILL|$pythonArchiveSkillId|$actorId|*" -and (Get-SkillLifecycleAudit $proxyArchiveSkillId 'ARCHIVE_SKILL') -like "ARCHIVE_SKILL|SKILL|$proxyArchiveSkillId|$actorId|*" -and (Get-SkillLifecycleAudit $proxyWebArchiveSkillId 'ARCHIVE_SKILL') -like "ARCHIVE_SKILL|SKILL|$proxyWebArchiveSkillId|$actorId|*")
            unarchiveAudit = ((Get-SkillLifecycleAudit $pythonUnarchiveSkillId 'UNARCHIVE_SKILL') -eq "UNARCHIVE_SKILL|SKILL|$pythonUnarchiveSkillId|$actorId|" -and (Get-SkillLifecycleAudit $proxyUnarchiveSkillId 'UNARCHIVE_SKILL') -eq "UNARCHIVE_SKILL|SKILL|$proxyUnarchiveSkillId|$actorId|" -and (Get-SkillLifecycleAudit $proxyWebUnarchiveSkillId 'UNARCHIVE_SKILL') -eq "UNARCHIVE_SKILL|SKILL|$proxyWebUnarchiveSkillId|$actorId|")
            rereleaseBoundaryJavaOwned = ($rereleaseBoundaryJava -eq $rereleaseBoundaryProxy)
            unauthenticatedArchiveRejected = ($unauthenticatedArchiveStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            deleteVersionJava = $deleteVersionBoundaryJava
            deleteVersionProxy = $deleteVersionBoundaryProxy
            rereleaseJava = $rereleaseBoundaryJava
            rereleaseProxy = $rereleaseBoundaryProxy
            unauthenticatedArchiveStatus = $unauthenticatedArchiveStatus
        }
        stable = [ordered]@{
            archive = $stableArchive
            unarchive = $stableUnarchive
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill lifecycle archive contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillLifecycleArchiveSmokeVerification {
    try {
        Invoke-SkillLifecycleArchiveTests
        Start-Hybrid
        Invoke-SkillLifecycleArchiveContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillVersionDeleteTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_delete_version.py', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillVersionDeleteJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method Delete -Headers @{ 'X-Mock-User-Id' = $UserId }
}

function ConvertTo-StableSkillVersionDeleteContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Write-SkillVersionDeleteStorageFiles {
    param(
        [string]$SkillId,
        [string]$VersionId
    )

    $skillFile = Join-Path $JavaStoragePath "skills\$SkillId\$VersionId\SKILL.md"
    $bundleFile = Join-Path $JavaStoragePath "packages\$SkillId\$VersionId\bundle.zip"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillFile) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $bundleFile) | Out-Null
    Set-Content -LiteralPath $skillFile -Value "# delete fixture" -Encoding UTF8
    [System.IO.File]::WriteAllBytes($bundleFile, [System.Text.Encoding]::UTF8.GetBytes("delete bundle"))
}

function Test-SkillVersionDeleteStorageMissing {
    param(
        [string]$SkillId,
        [string]$VersionId
    )

    $skillFile = Join-Path $JavaStoragePath "skills\$SkillId\$VersionId\SKILL.md"
    $bundleFile = Join-Path $JavaStoragePath "packages\$SkillId\$VersionId\bundle.zip"
    return ((-not (Test-Path -LiteralPath $skillFile)) -and (-not (Test-Path -LiteralPath $bundleFile)))
}

function Invoke-SkillVersionDeleteContractComparison {
    param([string]$ResultFileName = 'skill-version-delete-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-version-delete-$suffix"
    $ownerId = "codex-version-delete-owner-$suffix"
    $slugs = @(
        "java-delete-$suffix",
        "python-delete-$suffix",
        "proxy-delete-$suffix",
        "proxy-web-delete-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Version Delete', 'Version delete contract', '$ownerId', 'NAMESPACE_ONLY', 'ACTIVE', '$ownerId', '$ownerId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    published_version_id BIGINT;
    delete_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$ownerId', 'Codex Version Delete Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Version Delete', 'TEAM', 'ACTIVE', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED',
            jsonb_build_object('name', 'Version Delete', 'description', 'Version delete contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '2026-06-09T08:00:00Z'::timestamptz, '$ownerId',
            '2026-06-09T07:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO published_version_id;

        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.1.0', 'UPLOADED',
            jsonb_build_object('name', 'Version Delete', 'description', 'Version delete contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 120, '$ownerId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO delete_version_id;

        INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key, created_at)
        VALUES (delete_version_id, 'SKILL.md', 120, 'text/markdown', 'sha-delete-' || skill_row.slug, 'skills/' || skill_row.id || '/' || delete_version_id || '/SKILL.md', CURRENT_TIMESTAMP);

        INSERT INTO security_audit (skill_version_id, scanner_type, verdict, is_safe, findings_count, findings, created_at)
        VALUES (delete_version_id, 'SKILL_SCANNER', 'SUSPICIOUS', FALSE, 0, '[]'::jsonb, CURRENT_TIMESTAMP);

        UPDATE skill SET latest_version_id = delete_version_id WHERE id = skill_row.id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-SkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-DeleteVersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '1.1.0' LIMIT 1;"
    }
    function Get-PublishedVersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '1.0.0' LIMIT 1;"
    }
    function Get-DeleteDbState([string]$Slug, [string]$DeletedVersionId, [string]$PublishedVersionId) {
        return Invoke-PostgresScalar -Sql "SELECT (NOT EXISTS (SELECT 1 FROM skill_version WHERE id = $DeletedVersionId)) || '|' || (NOT EXISTS (SELECT 1 FROM skill_file WHERE version_id = $DeletedVersionId)) || '|' || (EXISTS (SELECT 1 FROM security_audit WHERE skill_version_id = $DeletedVersionId AND deleted_at IS NOT NULL)) || '|' || (s.latest_version_id = $PublishedVersionId) || '|' || COALESCE(s.updated_by, '') FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug';"
    }
    function Get-DeleteAudit([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $VersionId AND action = 'DELETE_SKILL_VERSION' ORDER BY created_at DESC LIMIT 1;"
    }

    $skillIds = @{}
    $deleteVersionIds = @{}
    $publishedVersionIds = @{}
    foreach ($slug in $slugs) {
        $skillIds[$slug] = Get-SkillId $slug
        $deleteVersionIds[$slug] = Get-DeleteVersionId $slug
        $publishedVersionIds[$slug] = Get-PublishedVersionId $slug
        Write-SkillVersionDeleteStorageFiles -SkillId $skillIds[$slug] -VersionId $deleteVersionIds[$slug]
    }

    $java = Invoke-SkillVersionDeleteJson "$JavaUrl/api/v1/skills/$namespace/$($slugs[0])/versions/1.1.0" $ownerId
    $python = Invoke-SkillVersionDeleteJson "$PythonUrl/api/v1/skills/$namespace/$($slugs[1])/versions/1.1.0" $ownerId
    $proxy = Invoke-SkillVersionDeleteJson "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0" $ownerId
    $proxyWeb = Invoke-SkillVersionDeleteJson "$WebUrl/api/web/skills/$namespace/$($slugs[3])/versions/1.1.0" $ownerId

    Start-Sleep -Milliseconds 300

    $rereleaseJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $rereleaseProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $submitReviewJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" -Method 'POST'
    $submitReviewProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" -Method 'POST'
    $unauthenticatedDeleteStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0" -Method 'DELETE'

    $stable = [ordered]@{
        java = ConvertTo-StableSkillVersionDeleteContractJson -Response $java
        python = ConvertTo-StableSkillVersionDeleteContractJson -Response $python
        proxy = ConvertTo-StableSkillVersionDeleteContractJson -Response $proxy
        proxyWeb = ConvertTo-StableSkillVersionDeleteContractJson -Response $proxyWeb
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            dbState = ((Get-DeleteDbState $slugs[1] $deleteVersionIds[$slugs[1]] $publishedVersionIds[$slugs[1]]) -eq "true|true|true|true|$ownerId" -and (Get-DeleteDbState $slugs[2] $deleteVersionIds[$slugs[2]] $publishedVersionIds[$slugs[2]]) -eq "true|true|true|true|$ownerId" -and (Get-DeleteDbState $slugs[3] $deleteVersionIds[$slugs[3]] $publishedVersionIds[$slugs[3]]) -eq "true|true|true|true|$ownerId")
            audit = ((Get-DeleteAudit $deleteVersionIds[$slugs[1]]) -like "DELETE_SKILL_VERSION|SKILL_VERSION|$($deleteVersionIds[$slugs[1]])|$ownerId|*" -and (Get-DeleteAudit $deleteVersionIds[$slugs[2]]) -like "DELETE_SKILL_VERSION|SKILL_VERSION|$($deleteVersionIds[$slugs[2]])|$ownerId|*" -and (Get-DeleteAudit $deleteVersionIds[$slugs[3]]) -like "DELETE_SKILL_VERSION|SKILL_VERSION|$($deleteVersionIds[$slugs[3]])|$ownerId|*")
            storageDeleted = ((Test-SkillVersionDeleteStorageMissing -SkillId $skillIds[$slugs[1]] -VersionId $deleteVersionIds[$slugs[1]]) -and (Test-SkillVersionDeleteStorageMissing -SkillId $skillIds[$slugs[2]] -VersionId $deleteVersionIds[$slugs[2]]) -and (Test-SkillVersionDeleteStorageMissing -SkillId $skillIds[$slugs[3]] -VersionId $deleteVersionIds[$slugs[3]]))
            rereleaseBoundaryJavaOwned = ($rereleaseJava -eq $rereleaseProxy)
            submitReviewBoundaryJavaOwned = ($submitReviewJava -eq $submitReviewProxy)
            unauthenticatedDeleteRejected = ($unauthenticatedDeleteStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            rereleaseJava = $rereleaseJava
            rereleaseProxy = $rereleaseProxy
            submitReviewJava = $submitReviewJava
            submitReviewProxy = $submitReviewProxy
            unauthenticatedDeleteStatus = $unauthenticatedDeleteStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill version delete contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillVersionDeleteSmokeVerification {
    try {
        Invoke-SkillVersionDeleteTests
        Start-Hybrid
        Invoke-SkillVersionDeleteContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillVersionWithdrawReviewTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_withdraw_review.py', 'tests/test_skill_lifecycle_delete_version.py', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillVersionWithdrawReviewPostJson {
    param(
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId }
}

function ConvertTo-StableSkillVersionWithdrawReviewContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillVersionWithdrawReviewContractComparison {
    param([string]$ResultFileName = 'skill-version-withdraw-review-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-version-withdraw-$suffix"
    $submitterId = "codex-version-withdraw-owner-$suffix"
    $slugs = @(
        "java-withdraw-$suffix",
        "python-withdraw-$suffix",
        "proxy-withdraw-$suffix",
        "proxy-web-withdraw-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Version Withdraw', 'Version withdraw review contract', '$submitterId', 'NAMESPACE_ONLY', 'ACTIVE', '$submitterId', '$submitterId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$submitterId', 'Codex Version Withdraw Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Version Withdraw', 'TEAM', 'ACTIVE', '$submitterId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.1.0', 'PENDING_REVIEW',
            jsonb_build_object('name', 'Version Withdraw', 'description', 'Version withdraw review contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 120, '$submitterId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;

        INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
        VALUES (version_id, ns_id, 'PENDING', 1, '$submitterId', CURRENT_TIMESTAMP - INTERVAL '1 minute');

        UPDATE skill SET latest_version_id = version_id WHERE id = skill_row.id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-WithdrawVersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '1.1.0' LIMIT 1;"
    }
    function Get-WithdrawDbState([string]$Slug, [string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT sv.status || '|' || COALESCE(s.updated_by, '') || '|' || (NOT EXISTS (SELECT 1 FROM review_task WHERE skill_version_id = $VersionId AND status = 'PENDING')) FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.id = $VersionId;"
    }
    function Get-WithdrawAudit([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $VersionId AND action = 'REVIEW_WITHDRAW' ORDER BY created_at DESC LIMIT 1;"
    }

    $versionIds = @{}
    foreach ($slug in $slugs) {
        $versionIds[$slug] = Get-WithdrawVersionId $slug
    }

    $java = Invoke-SkillVersionWithdrawReviewPostJson "$JavaUrl/api/v1/skills/$namespace/$($slugs[0])/versions/1.1.0/withdraw-review" $submitterId
    $python = Invoke-SkillVersionWithdrawReviewPostJson "$PythonUrl/api/v1/skills/$namespace/$($slugs[1])/versions/1.1.0/withdraw-review" $submitterId
    $proxy = Invoke-SkillVersionWithdrawReviewPostJson "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/withdraw-review" $submitterId
    $proxyWeb = Invoke-SkillVersionWithdrawReviewPostJson "$WebUrl/api/web/skills/$namespace/$($slugs[3])/versions/1.1.0/withdraw-review" $submitterId

    $rereleaseJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $rereleaseProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $submitReviewPython = Invoke-SkillSubmitReviewUnauthenticatedStatus "$PythonUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" '1.1.0' 'PUBLIC'
    $submitReviewProxy = Invoke-SkillSubmitReviewUnauthenticatedStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" '1.1.0' 'PUBLIC'
    $confirmPublishPython = Invoke-SkillConfirmPublishUnauthenticatedStatus "$PythonUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" '1.1.0'
    $confirmPublishProxy = Invoke-SkillConfirmPublishUnauthenticatedStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" '1.1.0'
    $unauthenticatedWithdrawStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/withdraw-review" -Method 'POST'

    $stable = [ordered]@{
        java = ConvertTo-StableSkillVersionWithdrawReviewContractJson -Response $java
        python = ConvertTo-StableSkillVersionWithdrawReviewContractJson -Response $python
        proxy = ConvertTo-StableSkillVersionWithdrawReviewContractJson -Response $proxy
        proxyWeb = ConvertTo-StableSkillVersionWithdrawReviewContractJson -Response $proxyWeb
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            dbState = ((Get-WithdrawDbState $slugs[1] $versionIds[$slugs[1]]) -eq "UPLOADED|$submitterId|true" -and (Get-WithdrawDbState $slugs[2] $versionIds[$slugs[2]]) -eq "UPLOADED|$submitterId|true" -and (Get-WithdrawDbState $slugs[3] $versionIds[$slugs[3]]) -eq "UPLOADED|$submitterId|true")
            audit = ((Get-WithdrawAudit $versionIds[$slugs[1]]) -like "REVIEW_WITHDRAW|SKILL_VERSION|$($versionIds[$slugs[1]])|$submitterId|*" -and (Get-WithdrawAudit $versionIds[$slugs[2]]) -like "REVIEW_WITHDRAW|SKILL_VERSION|$($versionIds[$slugs[2]])|$submitterId|*" -and (Get-WithdrawAudit $versionIds[$slugs[3]]) -like "REVIEW_WITHDRAW|SKILL_VERSION|$($versionIds[$slugs[3]])|$submitterId|*")
            rereleaseBoundaryJavaOwned = ($rereleaseJava -eq $rereleaseProxy)
            submitReviewBoundaryStillPythonOwned = ($submitReviewPython -eq 401 -and $submitReviewProxy -eq 401)
            confirmPublishBoundaryStillPythonOwned = ($confirmPublishPython -eq 401 -and $confirmPublishProxy -eq 401)
            unauthenticatedWithdrawRejected = ($unauthenticatedWithdrawStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            rereleaseJava = $rereleaseJava
            rereleaseProxy = $rereleaseProxy
            submitReviewPython = $submitReviewPython
            submitReviewProxy = $submitReviewProxy
            confirmPublishPython = $confirmPublishPython
            confirmPublishProxy = $confirmPublishProxy
            unauthenticatedWithdrawStatus = $unauthenticatedWithdrawStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill version withdraw-review contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillVersionWithdrawReviewSmokeVerification {
    try {
        Invoke-SkillVersionWithdrawReviewTests
        Start-Hybrid
        Invoke-SkillVersionWithdrawReviewContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillConfirmPublishTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_confirm_publish.py', 'tests/test_skill_lifecycle_withdraw_review.py', 'tests/test_skill_lifecycle_delete_version.py', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillConfirmPublishPostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$Version
    )

    $body = @{ version = $Version } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function Invoke-SkillConfirmPublishUnauthenticatedStatus {
    param(
        [string]$Url,
        [string]$Version
    )

    $body = @{ version = $Version } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri $Url -Method Post -ContentType 'application/json' -Body $body | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillConfirmPublishContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillConfirmPublishContractComparison {
    param([string]$ResultFileName = 'skill-confirm-publish-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-confirm-publish-$suffix"
    $ownerId = "codex-confirm-owner-$suffix"
    $slugs = @(
        "java-confirm-$suffix",
        "python-confirm-$suffix",
        "proxy-confirm-$suffix",
        "proxy-web-confirm-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Confirm Publish', 'Confirm publish contract', '$ownerId', 'PRIVATE', 'ACTIVE', '$ownerId', '$ownerId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$ownerId', 'Codex Confirm Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Confirm Publish', 'TEAM', 'ACTIVE', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.1.0', 'UPLOADED',
            jsonb_build_object('name', 'Confirm Publish', 'description', 'Confirm publish contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 120, '$ownerId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, TRUE, 'PRIVATE'
        )
        RETURNING id INTO version_id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-ConfirmVersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '1.1.0' LIMIT 1;"
    }
    function Get-ConfirmDbState([string]$Slug, [string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT sv.status || '|' || (sv.published_at IS NOT NULL) || '|' || (s.latest_version_id = $VersionId) || '|' || COALESCE(s.updated_by, '') FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.id = $VersionId;"
    }
    function Get-ConfirmAudit([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $VersionId AND action = 'CONFIRM_PUBLISH' ORDER BY created_at DESC LIMIT 1;"
    }

    $versionIds = @{}
    foreach ($slug in $slugs) {
        $versionIds[$slug] = Get-ConfirmVersionId $slug
    }

    $java = Invoke-SkillConfirmPublishPostJson "$JavaUrl/api/v1/skills/$namespace/$($slugs[0])/confirm-publish" $ownerId '1.1.0'
    $python = Invoke-SkillConfirmPublishPostJson "$PythonUrl/api/v1/skills/$namespace/$($slugs[1])/confirm-publish" $ownerId '1.1.0'
    $proxy = Invoke-SkillConfirmPublishPostJson "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" $ownerId '1.1.0'
    $proxyWeb = Invoke-SkillConfirmPublishPostJson "$WebUrl/api/web/skills/$namespace/$($slugs[3])/confirm-publish" $ownerId '1.1.0'

    $rereleaseJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $rereleaseProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $submitReviewJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" -Method 'POST'
    $submitReviewProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" -Method 'POST'
    $unauthenticatedConfirmStatus = Invoke-SkillConfirmPublishUnauthenticatedStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" '1.1.0'

    $stable = [ordered]@{
        java = ConvertTo-StableSkillConfirmPublishContractJson -Response $java
        python = ConvertTo-StableSkillConfirmPublishContractJson -Response $python
        proxy = ConvertTo-StableSkillConfirmPublishContractJson -Response $proxy
        proxyWeb = ConvertTo-StableSkillConfirmPublishContractJson -Response $proxyWeb
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            dbState = ((Get-ConfirmDbState $slugs[1] $versionIds[$slugs[1]]) -eq "PUBLISHED|true|true|$ownerId" -and (Get-ConfirmDbState $slugs[2] $versionIds[$slugs[2]]) -eq "PUBLISHED|true|true|$ownerId" -and (Get-ConfirmDbState $slugs[3] $versionIds[$slugs[3]]) -eq "PUBLISHED|true|true|$ownerId")
            audit = ((Get-ConfirmAudit $versionIds[$slugs[1]]) -like "CONFIRM_PUBLISH|SKILL_VERSION|$($versionIds[$slugs[1]])|$ownerId|*" -and (Get-ConfirmAudit $versionIds[$slugs[2]]) -like "CONFIRM_PUBLISH|SKILL_VERSION|$($versionIds[$slugs[2]])|$ownerId|*" -and (Get-ConfirmAudit $versionIds[$slugs[3]]) -like "CONFIRM_PUBLISH|SKILL_VERSION|$($versionIds[$slugs[3]])|$ownerId|*")
            rereleaseBoundaryJavaOwned = ($rereleaseJava -eq $rereleaseProxy)
            submitReviewBoundaryJavaOwned = ($submitReviewJava -eq $submitReviewProxy)
            unauthenticatedConfirmRejected = ($unauthenticatedConfirmStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            rereleaseJava = $rereleaseJava
            rereleaseProxy = $rereleaseProxy
            submitReviewJava = $submitReviewJava
            submitReviewProxy = $submitReviewProxy
            unauthenticatedConfirmStatus = $unauthenticatedConfirmStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill confirm-publish contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillConfirmPublishSmokeVerification {
    try {
        Invoke-SkillConfirmPublishTests
        Start-Hybrid
        Invoke-SkillConfirmPublishContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillSubmitReviewTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_submit_review.py', 'tests/test_skill_lifecycle_confirm_publish.py', 'tests/test_skill_lifecycle_withdraw_review.py', 'tests/test_skill_lifecycle_delete_version.py', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillSubmitReviewPostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$Version,
        [string]$TargetVisibility
    )

    $body = @{ version = $Version; targetVisibility = $TargetVisibility } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function Invoke-SkillSubmitReviewUnauthenticatedStatus {
    param(
        [string]$Url,
        [string]$Version,
        [string]$TargetVisibility
    )

    $body = @{ version = $Version; targetVisibility = $TargetVisibility } | ConvertTo-Json -Compress
    try {
        Invoke-RestMethod -Uri $Url -Method Post -ContentType 'application/json' -Body $body | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillSubmitReviewContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillSubmitReviewContractComparison {
    param([string]$ResultFileName = 'skill-submit-review-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-submit-review-$suffix"
    $ownerId = "codex-submit-owner-$suffix"
    $slugs = @(
        "java-submit-$suffix",
        "python-submit-$suffix",
        "proxy-submit-$suffix",
        "proxy-web-submit-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Submit Review', 'Submit review contract', '$ownerId', 'NAMESPACE_ONLY', 'ACTIVE', '$ownerId', '$ownerId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$ownerId', 'Codex Submit Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Submit Review', 'TEAM', 'ACTIVE', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.1.0', 'UPLOADED',
            jsonb_build_object('name', 'Submit Review', 'description', 'Submit review contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 120, '$ownerId', '2026-06-09T09:00:00Z'::timestamptz,
            TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO version_id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-SubmitVersionId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '1.1.0' LIMIT 1;"
    }
    function Get-SubmitDbState([string]$Slug, [string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT sv.status || '|' || sv.requested_visibility || '|' || (SELECT COUNT(*) > 0 FROM review_task rt WHERE rt.skill_version_id = sv.id AND rt.status = 'PENDING' AND rt.submitted_by = '$ownerId') || '|' || COALESCE((SELECT rt.submitted_by FROM review_task rt WHERE rt.skill_version_id = sv.id AND rt.status = 'PENDING' ORDER BY rt.submitted_at DESC LIMIT 1), '') FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.id = $VersionId;"
    }
    function Get-SubmitAudit([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $VersionId AND action = 'SUBMIT_REVIEW' ORDER BY created_at DESC LIMIT 1;"
    }

    $versionIds = @{}
    foreach ($slug in $slugs) {
        $versionIds[$slug] = Get-SubmitVersionId $slug
    }

    $java = Invoke-SkillSubmitReviewPostJson "$JavaUrl/api/v1/skills/$namespace/$($slugs[0])/submit-review" $ownerId '1.1.0' 'PUBLIC'
    $python = Invoke-SkillSubmitReviewPostJson "$PythonUrl/api/v1/skills/$namespace/$($slugs[1])/submit-review" $ownerId '1.1.0' 'PUBLIC'
    $proxy = Invoke-SkillSubmitReviewPostJson "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" $ownerId '1.1.0' 'PUBLIC'
    $proxyWeb = Invoke-SkillSubmitReviewPostJson "$WebUrl/api/web/skills/$namespace/$($slugs[3])/submit-review" $ownerId '1.1.0' 'PUBLIC'

    $rereleaseJava = Invoke-HttpStatusNoRedirect "$JavaUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $rereleaseProxy = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.1.0/rerelease" -Method 'POST'
    $confirmPublishPython = Invoke-SkillConfirmPublishUnauthenticatedStatus "$PythonUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" '1.1.0'
    $confirmPublishProxy = Invoke-SkillConfirmPublishUnauthenticatedStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/confirm-publish" '1.1.0'
    $unauthenticatedSubmitStatus = Invoke-SkillSubmitReviewUnauthenticatedStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/submit-review" '1.1.0' 'PUBLIC'

    $stable = [ordered]@{
        java = ConvertTo-StableSkillSubmitReviewContractJson -Response $java
        python = ConvertTo-StableSkillSubmitReviewContractJson -Response $python
        proxy = ConvertTo-StableSkillSubmitReviewContractJson -Response $proxy
        proxyWeb = ConvertTo-StableSkillSubmitReviewContractJson -Response $proxyWeb
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            dbState = ((Get-SubmitDbState $slugs[0] $versionIds[$slugs[0]]) -eq "PENDING_REVIEW|PUBLIC|true|$ownerId" -and (Get-SubmitDbState $slugs[1] $versionIds[$slugs[1]]) -eq "PENDING_REVIEW|PUBLIC|true|$ownerId" -and (Get-SubmitDbState $slugs[2] $versionIds[$slugs[2]]) -eq "PENDING_REVIEW|PUBLIC|true|$ownerId" -and (Get-SubmitDbState $slugs[3] $versionIds[$slugs[3]]) -eq "PENDING_REVIEW|PUBLIC|true|$ownerId")
            audit = ((Get-SubmitAudit $versionIds[$slugs[0]]) -like "SUBMIT_REVIEW|SKILL_VERSION|$($versionIds[$slugs[0]])|$ownerId|*" -and (Get-SubmitAudit $versionIds[$slugs[1]]) -like "SUBMIT_REVIEW|SKILL_VERSION|$($versionIds[$slugs[1]])|$ownerId|*" -and (Get-SubmitAudit $versionIds[$slugs[2]]) -like "SUBMIT_REVIEW|SKILL_VERSION|$($versionIds[$slugs[2]])|$ownerId|*" -and (Get-SubmitAudit $versionIds[$slugs[3]]) -like "SUBMIT_REVIEW|SKILL_VERSION|$($versionIds[$slugs[3]])|$ownerId|*")
            rereleaseBoundaryJavaOwned = ($rereleaseJava -eq $rereleaseProxy)
            confirmPublishBoundaryStillPythonOwned = ($confirmPublishPython -eq 401 -and $confirmPublishProxy -eq 401)
            unauthenticatedSubmitRejected = ($unauthenticatedSubmitStatus -eq 401)
        }
        routeBoundaries = [ordered]@{
            rereleaseJava = $rereleaseJava
            rereleaseProxy = $rereleaseProxy
            confirmPublishPython = $confirmPublishPython
            confirmPublishProxy = $confirmPublishProxy
            unauthenticatedSubmitStatus = $unauthenticatedSubmitStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill submit-review contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillSubmitReviewSmokeVerification {
    try {
        Invoke-SkillSubmitReviewTests
        Start-Hybrid
        Invoke-SkillSubmitReviewContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillRereleaseTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_lifecycle_rerelease.py', 'tests/test_skill_lifecycle_submit_review.py', 'tests/test_skill_lifecycle_confirm_publish.py', 'tests/test_skill_lifecycle_withdraw_review.py', 'tests/test_skill_lifecycle_delete_version.py', 'tests/test_skill_lifecycle_archive.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillRereleasePostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [string]$TargetVersion,
        [bool]$ConfirmWarnings = $false
    )

    $body = @{ targetVersion = $TargetVersion; confirmWarnings = $ConfirmWarnings } | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $body
}

function Invoke-SkillRereleaseStatus {
    param(
        [string]$Url,
        [string]$TargetVersion,
        [string]$UserId = ''
    )

    $body = @{ targetVersion = $TargetVersion; confirmWarnings = $true } | ConvertTo-Json -Compress
    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    try {
        Invoke-RestMethod -Uri $Url -Method Post -Headers $headers -ContentType 'application/json' -Body $body | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillRereleaseContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Write-SkillRereleaseSourceStorage {
    param(
        [string]$SkillId,
        [string]$VersionId,
        [string]$SkillName
    )

    $skillFile = Join-Path $JavaStoragePath "skills\$SkillId\$VersionId\SKILL.md"
    $mainFile = Join-Path $JavaStoragePath "skills\$SkillId\$VersionId\src\main.py"
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $skillFile) | Out-Null
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $mainFile) | Out-Null
    $skillMd = "---`nname: $SkillName`ndescription: Rerelease contract`nversion: 1.0.0`n---`n# $SkillName`n"
    [System.IO.File]::WriteAllBytes($skillFile, [System.Text.UTF8Encoding]::new($false).GetBytes($skillMd))
    [System.IO.File]::WriteAllBytes($mainFile, [System.Text.UTF8Encoding]::new($false).GetBytes("print('rerelease')`n"))
}

function Test-SkillRereleaseStorageVersion {
    param(
        [string]$SkillId,
        [string]$VersionId,
        [string]$ExpectedVersion
    )

    $skillFile = Join-Path $JavaStoragePath "skills\$SkillId\$VersionId\SKILL.md"
    if (-not (Test-Path -LiteralPath $skillFile)) {
        return $false
    }
    return ((Get-Content -LiteralPath $skillFile -Raw) -like "*version: $ExpectedVersion*")
}

function Invoke-SkillRereleaseContractComparison {
    param([string]$ResultFileName = 'skill-rerelease-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-rerelease-$suffix"
    $ownerId = "codex-rerelease-owner-$suffix"
    $slugs = @(
        "java-rerelease-$suffix",
        "python-rerelease-$suffix",
        "proxy-rerelease-$suffix",
        "proxy-web-rerelease-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', '$($_)', 'Rerelease contract', '$ownerId', 'NAMESPACE_ONLY', 'ACTIVE', '$ownerId', '$ownerId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    source_version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, status)
    VALUES ('$ownerId', 'Codex Rerelease Owner', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Rerelease', 'TEAM', 'ACTIVE', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED',
            jsonb_build_object('name', skill_row.slug, 'description', 'Rerelease contract', 'version', '1.0.0'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md'), jsonb_build_object('path', 'src/main.py')),
            2, 180, '2026-06-09T08:00:00Z'::timestamptz, '$ownerId',
            '2026-06-09T07:00:00Z'::timestamptz, TRUE, TRUE, 'NAMESPACE_ONLY'
        )
        RETURNING id INTO source_version_id;

        INSERT INTO skill_file (version_id, file_path, file_size, content_type, sha256, storage_key, created_at)
        VALUES
            (source_version_id, 'SKILL.md', 140, 'text/markdown', 'sha-rerelease-skill-' || skill_row.slug, 'skills/' || skill_row.id || '/' || source_version_id || '/SKILL.md', CURRENT_TIMESTAMP),
            (source_version_id, 'src/main.py', 20, 'text/x-python', 'sha-rerelease-main-' || skill_row.slug, 'skills/' || skill_row.id || '/' || source_version_id || '/src/main.py', CURRENT_TIMESTAMP);

        UPDATE skill SET latest_version_id = source_version_id WHERE id = skill_row.id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-RereleaseSkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-RereleaseVersionId([string]$Slug, [string]$Version) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '$Version' LIMIT 1;"
    }
    function Get-RereleaseDbState([string]$Slug, [string]$VersionId, [string]$ExpectedStatus) {
        return Invoke-PostgresScalar -Sql "SELECT sv.version || '|' || sv.status || '|' || sv.requested_visibility || '|' || sv.file_count || '|' || sv.total_size || '|' || sv.bundle_ready || '|' || sv.download_ready || '|' || COALESCE(s.updated_by, '') || '|' || (SELECT COUNT(*) FROM skill_file sf WHERE sf.version_id = sv.id) FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.id = $VersionId;"
    }
    function Get-RereleaseAudit([string]$SourceVersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $SourceVersionId AND action = 'RERELEASE_SKILL_VERSION' ORDER BY created_at DESC LIMIT 1;"
    }

    $skillIds = @{}
    $sourceVersionIds = @{}
    foreach ($slug in $slugs) {
        $skillIds[$slug] = Get-RereleaseSkillId $slug
        $sourceVersionIds[$slug] = Get-RereleaseVersionId $slug '1.0.0'
        Write-SkillRereleaseSourceStorage -SkillId $skillIds[$slug] -VersionId $sourceVersionIds[$slug] -SkillName $slug
    }

    $java = Invoke-SkillRereleasePostJson "$JavaUrl/api/v1/skills/$namespace/$($slugs[0])/versions/1.0.0/rerelease" $ownerId '2.0.0' $true
    $python = Invoke-SkillRereleasePostJson "$PythonUrl/api/v1/skills/$namespace/$($slugs[1])/versions/1.0.0/rerelease" $ownerId '2.0.0' $true
    $proxy = Invoke-SkillRereleasePostJson "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.0.0/rerelease" $ownerId '2.0.0' $true
    $proxyWeb = Invoke-SkillRereleasePostJson "$WebUrl/api/web/skills/$namespace/$($slugs[3])/versions/1.0.0/rerelease" $ownerId '2.0.0' $true

    $targetVersionIds = @{}
    foreach ($slug in $slugs) {
        $targetVersionIds[$slug] = Get-RereleaseVersionId $slug '2.0.0'
    }

    $duplicateStatus = Invoke-SkillRereleaseStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.0.0/rerelease" '2.0.0' $ownerId
    $unauthenticatedStatus = Invoke-SkillRereleaseStatus "$WebUrl/api/v1/skills/$namespace/$($slugs[2])/versions/1.0.0/rerelease" '3.0.0'
    $adminYankStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[2]])/yank" -Method 'POST'
    $adminHideStatus = Invoke-HttpStatusNoRedirect "$WebUrl/api/v1/admin/skills/$($skillIds[$slugs[2]])/hide" -Method 'POST'

    $stable = [ordered]@{
        java = ConvertTo-StableSkillRereleaseContractJson -Response $java
        python = ConvertTo-StableSkillRereleaseContractJson -Response $python
        proxy = ConvertTo-StableSkillRereleaseContractJson -Response $proxy
        proxyWeb = ConvertTo-StableSkillRereleaseContractJson -Response $proxyWeb
    }
    $expectedStatus = $java.data.status
    $expectedDbStatePrefix = "2.0.0|$expectedStatus|NAMESPACE_ONLY|2|"

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy -and $stable.python -eq $stable.proxyWeb)
            dbState = ((Get-RereleaseDbState $slugs[0] $targetVersionIds[$slugs[0]] $expectedStatus) -like "$expectedDbStatePrefix*|true|true|$ownerId|2" -and (Get-RereleaseDbState $slugs[1] $targetVersionIds[$slugs[1]] $expectedStatus) -like "$expectedDbStatePrefix*|true|true|$ownerId|2" -and (Get-RereleaseDbState $slugs[2] $targetVersionIds[$slugs[2]] $expectedStatus) -like "$expectedDbStatePrefix*|true|true|$ownerId|2" -and (Get-RereleaseDbState $slugs[3] $targetVersionIds[$slugs[3]] $expectedStatus) -like "$expectedDbStatePrefix*|true|true|$ownerId|2")
            audit = ((Get-RereleaseAudit $sourceVersionIds[$slugs[0]]) -like "RERELEASE_SKILL_VERSION|SKILL_VERSION|$($sourceVersionIds[$slugs[0]])|$ownerId|*" -and (Get-RereleaseAudit $sourceVersionIds[$slugs[1]]) -like "RERELEASE_SKILL_VERSION|SKILL_VERSION|$($sourceVersionIds[$slugs[1]])|$ownerId|*" -and (Get-RereleaseAudit $sourceVersionIds[$slugs[2]]) -like "RERELEASE_SKILL_VERSION|SKILL_VERSION|$($sourceVersionIds[$slugs[2]])|$ownerId|*" -and (Get-RereleaseAudit $sourceVersionIds[$slugs[3]]) -like "RERELEASE_SKILL_VERSION|SKILL_VERSION|$($sourceVersionIds[$slugs[3]])|$ownerId|*")
            storageVersionRewritten = ((Test-SkillRereleaseStorageVersion -SkillId $skillIds[$slugs[1]] -VersionId $targetVersionIds[$slugs[1]] -ExpectedVersion '2.0.0') -and (Test-SkillRereleaseStorageVersion -SkillId $skillIds[$slugs[2]] -VersionId $targetVersionIds[$slugs[2]] -ExpectedVersion '2.0.0') -and (Test-SkillRereleaseStorageVersion -SkillId $skillIds[$slugs[3]] -VersionId $targetVersionIds[$slugs[3]] -ExpectedVersion '2.0.0'))
            duplicateTargetRejected = ($duplicateStatus -eq 400)
            unauthenticatedRereleaseRejected = ($unauthenticatedStatus -eq 401)
            adminYankStillJavaOwned = ($adminYankStatus -eq 401 -or $adminYankStatus -eq 403 -or $adminYankStatus -eq 404)
            adminHideStillJavaOwned = ($adminHideStatus -eq 401 -or $adminHideStatus -eq 403 -or $adminHideStatus -eq 404)
        }
        routeBoundaries = [ordered]@{
            duplicateStatus = $duplicateStatus
            unauthenticatedStatus = $unauthenticatedStatus
            adminYankStatus = $adminYankStatus
            adminHideStatus = $adminHideStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill rerelease contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillRereleaseSmokeVerification {
    try {
        Invoke-SkillRereleaseTests
        Start-Hybrid
        Invoke-SkillRereleaseContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-AdminSkillHideUnhideTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_admin_skill_governance.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-AdminSkillPostJson {
    param(
        [string]$Url,
        [string]$UserId,
        [hashtable]$Body = @{}
    )

    $json = $Body | ConvertTo-Json -Compress
    return Invoke-RestMethod -Uri $Url -Method Post -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -Body $json
}

function Invoke-AdminSkillStatus {
    param(
        [string]$Url,
        [string]$UserId = ''
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    try {
        Invoke-RestMethod -Uri $Url -Method Post -Headers $headers -ContentType 'application/json' -Body '{}' | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableAdminSkillMutationContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionId = $Response.data.versionId
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableAdminVersionMutationContractJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            skillIdPresent = ($null -ne $Response.data.skillId)
            versionIdPresent = ($null -ne $Response.data.versionId)
            action = $Response.data.action
            status = $Response.data.status
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-AdminSkillHideUnhideContractComparison {
    param([string]$ResultFileName = 'admin-skill-hide-unhide-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-admin-skill-$suffix"
    $superAdminId = "codex-super-admin-$suffix"
    $skillAdminId = "codex-skill-admin-$suffix"
    $hideSlugs = @(
        "java-hide-$suffix",
        "python-hide-$suffix",
        "proxy-hide-$suffix"
    )
    $unhideSlugs = @(
        "java-unhide-$suffix",
        "python-unhide-$suffix",
        "proxy-unhide-$suffix"
    )
    $hideValuesSql = ($hideSlugs | ForEach-Object { "(ns_id, '$($_)', 'Admin Hide', 'Admin hide contract', '$superAdminId', 'PUBLIC', 'ACTIVE', '$superAdminId', '$superAdminId', FALSE)" }) -join ",`n        "
    $unhideValuesSql = ($unhideSlugs | ForEach-Object { "(ns_id, '$($_)', 'Admin Unhide', 'Admin unhide contract', '$superAdminId', 'PUBLIC', 'ACTIVE', '$superAdminId', '$superAdminId', TRUE)" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    super_admin_role_id BIGINT;
    skill_admin_role_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$superAdminId', 'Codex Super Admin', 'super-$suffix@example.test', '', 'ACTIVE'),
        ('$skillAdminId', 'Codex Skill Admin', 'skill-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO role (code, name, description, is_system)
    VALUES
        ('SUPER_ADMIN', 'Super Admin', 'Super administrator', TRUE),
        ('SKILL_ADMIN', 'Skill Admin', 'Skill administrator', TRUE)
    ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        description = EXCLUDED.description,
        is_system = EXCLUDED.is_system;

    SELECT id INTO super_admin_role_id FROM role WHERE code = 'SUPER_ADMIN';
    SELECT id INTO skill_admin_role_id FROM role WHERE code = 'SKILL_ADMIN';

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES
        ('$superAdminId', super_admin_role_id),
        ('$skillAdminId', skill_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Admin Skill', 'TEAM', 'ACTIVE', '$superAdminId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by, hidden)
    VALUES
        $hideValuesSql,
        $unhideValuesSql;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-AdminSkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-AdminSkillHiddenState([string]$SkillId) {
        return Invoke-PostgresScalar -Sql "SELECT hidden || '|' || COALESCE(hidden_by, '') || '|' || (hidden_at IS NOT NULL) || '|' || COALESCE(updated_by, '') || '|' || status FROM skill WHERE id = $SkillId;"
    }
    function Get-AdminSkillAudit([string]$SkillId, [string]$Action) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL' AND target_id = $SkillId AND action = '$Action' ORDER BY created_at DESC LIMIT 1;"
    }

    $hideIds = @{}
    $unhideIds = @{}
    foreach ($slug in $hideSlugs) {
        $hideIds[$slug] = Get-AdminSkillId $slug
    }
    foreach ($slug in $unhideSlugs) {
        $unhideIds[$slug] = Get-AdminSkillId $slug
    }

    $javaHide = Invoke-AdminSkillPostJson "$JavaUrl/api/v1/admin/skills/$($hideIds[$hideSlugs[0]])/hide" $superAdminId @{ reason = 'policy' }
    $pythonHide = Invoke-AdminSkillPostJson "$PythonUrl/api/v1/admin/skills/$($hideIds[$hideSlugs[1]])/hide" $superAdminId @{ reason = 'policy' }
    $proxyHide = Invoke-AdminSkillPostJson "$WebUrl/api/v1/admin/skills/$($hideIds[$hideSlugs[2]])/hide" $superAdminId @{ reason = 'policy' }

    $javaUnhide = Invoke-AdminSkillPostJson "$JavaUrl/api/v1/admin/skills/$($unhideIds[$unhideSlugs[0]])/unhide" $superAdminId
    $pythonUnhide = Invoke-AdminSkillPostJson "$PythonUrl/api/v1/admin/skills/$($unhideIds[$unhideSlugs[1]])/unhide" $superAdminId
    $proxyUnhide = Invoke-AdminSkillPostJson "$WebUrl/api/v1/admin/skills/$($unhideIds[$unhideSlugs[2]])/unhide" $superAdminId

    $skillAdminHideStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/$($hideIds[$hideSlugs[2]])/hide" $skillAdminId
    $unauthenticatedHideStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/$($hideIds[$hideSlugs[2]])/hide"
    $yankJavaStatus = Invoke-AdminSkillStatus "$JavaUrl/api/v1/admin/skills/versions/999999/yank" $superAdminId
    $yankProxyStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/versions/999999/yank" $superAdminId

    $stableHide = [ordered]@{
        java = ConvertTo-StableAdminSkillMutationContractJson -Response $javaHide
        python = ConvertTo-StableAdminSkillMutationContractJson -Response $pythonHide
        proxy = ConvertTo-StableAdminSkillMutationContractJson -Response $proxyHide
    }
    $stableUnhide = [ordered]@{
        java = ConvertTo-StableAdminSkillMutationContractJson -Response $javaUnhide
        python = ConvertTo-StableAdminSkillMutationContractJson -Response $pythonUnhide
        proxy = ConvertTo-StableAdminSkillMutationContractJson -Response $proxyUnhide
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            hideResponsesMatch = ($stableHide.java -eq $stableHide.python -and $stableHide.python -eq $stableHide.proxy)
            unhideResponsesMatch = ($stableUnhide.java -eq $stableUnhide.python -and $stableUnhide.python -eq $stableUnhide.proxy)
            hideDbState = ((Get-AdminSkillHiddenState $hideIds[$hideSlugs[0]]) -eq "true|$superAdminId|true|$superAdminId|ACTIVE" -and (Get-AdminSkillHiddenState $hideIds[$hideSlugs[1]]) -eq "true|$superAdminId|true|$superAdminId|ACTIVE" -and (Get-AdminSkillHiddenState $hideIds[$hideSlugs[2]]) -eq "true|$superAdminId|true|$superAdminId|ACTIVE")
            unhideDbState = ((Get-AdminSkillHiddenState $unhideIds[$unhideSlugs[0]]) -eq "false||false|$superAdminId|ACTIVE" -and (Get-AdminSkillHiddenState $unhideIds[$unhideSlugs[1]]) -eq "false||false|$superAdminId|ACTIVE" -and (Get-AdminSkillHiddenState $unhideIds[$unhideSlugs[2]]) -eq "false||false|$superAdminId|ACTIVE")
            hideAudit = ((Get-AdminSkillAudit $hideIds[$hideSlugs[0]] 'HIDE_SKILL') -like "HIDE_SKILL|SKILL|$($hideIds[$hideSlugs[0]])|$superAdminId|*" -and (Get-AdminSkillAudit $hideIds[$hideSlugs[1]] 'HIDE_SKILL') -like "HIDE_SKILL|SKILL|$($hideIds[$hideSlugs[1]])|$superAdminId|*" -and (Get-AdminSkillAudit $hideIds[$hideSlugs[2]] 'HIDE_SKILL') -like "HIDE_SKILL|SKILL|$($hideIds[$hideSlugs[2]])|$superAdminId|*")
            unhideAudit = ((Get-AdminSkillAudit $unhideIds[$unhideSlugs[0]] 'UNHIDE_SKILL') -eq "UNHIDE_SKILL|SKILL|$($unhideIds[$unhideSlugs[0]])|$superAdminId|" -and (Get-AdminSkillAudit $unhideIds[$unhideSlugs[1]] 'UNHIDE_SKILL') -eq "UNHIDE_SKILL|SKILL|$($unhideIds[$unhideSlugs[1]])|$superAdminId|" -and (Get-AdminSkillAudit $unhideIds[$unhideSlugs[2]] 'UNHIDE_SKILL') -eq "UNHIDE_SKILL|SKILL|$($unhideIds[$unhideSlugs[2]])|$superAdminId|")
            skillAdminRejected = ($skillAdminHideStatus -eq 403)
            unauthenticatedRejected = ($unauthenticatedHideStatus -eq 401)
            yankStillJavaOwned = ($yankJavaStatus -eq $yankProxyStatus)
        }
        routeBoundaries = [ordered]@{
            skillAdminHideStatus = $skillAdminHideStatus
            unauthenticatedHideStatus = $unauthenticatedHideStatus
            yankJavaStatus = $yankJavaStatus
            yankProxyStatus = $yankProxyStatus
        }
        stableHide = $stableHide
        stableUnhide = $stableUnhide
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Admin skill hide/unhide contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridAdminSkillHideUnhideSmokeVerification {
    try {
        Invoke-AdminSkillHideUnhideTests
        Start-Hybrid
        Invoke-AdminSkillHideUnhideContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-AdminVersionYankTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_admin_skill_governance.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-AdminVersionYankContractComparison {
    param([string]$ResultFileName = 'admin-version-yank-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-admin-yank-$suffix"
    $skillAdminId = "codex-skill-admin-$suffix"
    $superAdminId = "codex-super-admin-$suffix"
    $userAdminId = "codex-user-admin-$suffix"
    $slugs = @(
        "java-yank-$suffix",
        "python-yank-$suffix",
        "proxy-yank-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Admin Yank', 'Admin yank contract', '$skillAdminId', 'PUBLIC', 'ACTIVE', '$skillAdminId', '$skillAdminId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_row RECORD;
    previous_version_id BIGINT;
    target_version_id BIGINT;
    skill_admin_role_id BIGINT;
    super_admin_role_id BIGINT;
    user_admin_role_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$skillAdminId', 'Codex Skill Admin', 'skill-$suffix@example.test', '', 'ACTIVE'),
        ('$superAdminId', 'Codex Super Admin', 'super-$suffix@example.test', '', 'ACTIVE'),
        ('$userAdminId', 'Codex User Admin', 'user-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO role (code, name, description, is_system)
    VALUES
        ('SKILL_ADMIN', 'Skill Admin', 'Skill administrator', TRUE),
        ('SUPER_ADMIN', 'Super Admin', 'Super administrator', TRUE),
        ('USER_ADMIN', 'User Admin', 'User administrator', TRUE)
    ON CONFLICT (code) DO UPDATE
    SET name = EXCLUDED.name,
        description = EXCLUDED.description,
        is_system = EXCLUDED.is_system;

    SELECT id INTO skill_admin_role_id FROM role WHERE code = 'SKILL_ADMIN';
    SELECT id INTO super_admin_role_id FROM role WHERE code = 'SUPER_ADMIN';
    SELECT id INTO user_admin_role_id FROM role WHERE code = 'USER_ADMIN';

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES
        ('$skillAdminId', skill_admin_role_id),
        ('$superAdminId', super_admin_role_id),
        ('$userAdminId', user_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Admin Yank', 'TEAM', 'ACTIVE', '$skillAdminId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    FOR skill_row IN
        INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
        VALUES
        $valuesSql
        RETURNING id, slug
    LOOP
        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.0.0', 'PUBLISHED',
            jsonb_build_object('name', 'Admin Yank', 'description', 'Admin yank contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 100, '2026-06-09T08:00:00Z'::timestamptz, '$skillAdminId',
            '2026-06-09T07:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
        )
        RETURNING id INTO previous_version_id;

        INSERT INTO skill_version (
            skill_id, version, status, parsed_metadata_json, manifest_json,
            file_count, total_size, published_at, created_by, created_at,
            bundle_ready, download_ready, requested_visibility
        )
        VALUES (
            skill_row.id, '1.1.0', 'PUBLISHED',
            jsonb_build_object('name', 'Admin Yank', 'description', 'Admin yank contract'),
            jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
            1, 110, '2026-06-09T09:00:00Z'::timestamptz, '$skillAdminId',
            '2026-06-09T08:30:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
        )
        RETURNING id INTO target_version_id;

        UPDATE skill SET latest_version_id = target_version_id WHERE id = skill_row.id;
    END LOOP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-YankVersionId([string]$Slug, [string]$Version) {
        return Invoke-PostgresScalar -Sql "SELECT sv.id FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.version = '$Version' LIMIT 1;"
    }
    function Get-YankDbState([string]$Slug, [string]$TargetVersionId, [string]$PreviousVersionId) {
        return Invoke-PostgresScalar -Sql "SELECT sv.status || '|' || sv.download_ready || '|' || (sv.yanked_at IS NOT NULL) || '|' || COALESCE(sv.yanked_by, '') || '|' || COALESCE(sv.yank_reason, '') || '|' || (s.latest_version_id = $PreviousVersionId) || '|' || COALESCE(s.updated_by, '') FROM skill_version sv JOIN skill s ON s.id = sv.skill_id JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' AND sv.id = $TargetVersionId;"
    }
    function Get-YankAudit([string]$VersionId) {
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || target_id || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'SKILL_VERSION' AND target_id = $VersionId AND action = 'YANK_SKILL_VERSION' ORDER BY created_at DESC LIMIT 1;"
    }

    $targetVersionIds = @{}
    $previousVersionIds = @{}
    foreach ($slug in $slugs) {
        $previousVersionIds[$slug] = Get-YankVersionId $slug '1.0.0'
        $targetVersionIds[$slug] = Get-YankVersionId $slug '1.1.0'
    }

    $java = Invoke-AdminSkillPostJson "$JavaUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[0]])/yank" $skillAdminId @{ reason = 'security' }
    $python = Invoke-AdminSkillPostJson "$PythonUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[1]])/yank" $skillAdminId @{ reason = 'security' }
    $proxy = Invoke-AdminSkillPostJson "$WebUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[2]])/yank" $skillAdminId @{ reason = 'security' }

    $userAdminStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[2]])/yank" $userAdminId
    $unauthenticatedStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/versions/$($targetVersionIds[$slugs[2]])/yank"
    $missingStatus = Invoke-AdminSkillStatus "$WebUrl/api/v1/admin/skills/versions/999999/yank" $skillAdminId

    $stable = [ordered]@{
        java = ConvertTo-StableAdminVersionMutationContractJson -Response $java
        python = ConvertTo-StableAdminVersionMutationContractJson -Response $python
        proxy = ConvertTo-StableAdminVersionMutationContractJson -Response $proxy
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            responsesMatch = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy)
            javaDbState = ((Get-YankDbState $slugs[0] $targetVersionIds[$slugs[0]] $previousVersionIds[$slugs[0]]) -eq "YANKED|false|true|$skillAdminId|security|true|$skillAdminId")
            pythonDbState = ((Get-YankDbState $slugs[1] $targetVersionIds[$slugs[1]] $previousVersionIds[$slugs[1]]) -eq "YANKED|false|true|$skillAdminId|security|true|$skillAdminId")
            proxyDbState = ((Get-YankDbState $slugs[2] $targetVersionIds[$slugs[2]] $previousVersionIds[$slugs[2]]) -eq "YANKED|false|true|$skillAdminId|security|true|$skillAdminId")
            javaAudit = ((Get-YankAudit $targetVersionIds[$slugs[0]]) -like "YANK_SKILL_VERSION|SKILL_VERSION|$($targetVersionIds[$slugs[0]])|$skillAdminId|*")
            pythonAudit = ((Get-YankAudit $targetVersionIds[$slugs[1]]) -like "YANK_SKILL_VERSION|SKILL_VERSION|$($targetVersionIds[$slugs[1]])|$skillAdminId|*")
            proxyAudit = ((Get-YankAudit $targetVersionIds[$slugs[2]]) -like "YANK_SKILL_VERSION|SKILL_VERSION|$($targetVersionIds[$slugs[2]])|$skillAdminId|*")
            userAdminRejected = ($userAdminStatus -eq 403)
            unauthenticatedRejected = ($unauthenticatedStatus -eq 401)
            missingVersionRejected = ($missingStatus -eq 404)
        }
        routeBoundaries = [ordered]@{
            userAdminStatus = $userAdminStatus
            unauthenticatedStatus = $unauthenticatedStatus
            missingStatus = $missingStatus
        }
        stable = $stable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Admin version yank contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridAdminVersionYankSmokeVerification {
    try {
        Invoke-AdminVersionYankTests
        Start-Hybrid
        Invoke-AdminVersionYankContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillStarTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_star.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillStarRequest {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = ''
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    return Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers
}

function Invoke-SkillStarStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = ''
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    try {
        Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillStarMutationJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        dataIsNull = ($null -eq $Response.data)
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableSkillStarReadJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [bool]$Response.data
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillStarContractComparison {
    param([string]$ResultFileName = 'skill-star-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-star-$suffix"
    $userId = "codex-star-user-$suffix"
    $slugs = @(
        "java-star-$suffix",
        "python-star-$suffix",
        "proxy-star-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Skill Star', 'Skill star contract', '$userId', 'PUBLIC', 'ACTIVE', '$userId', '$userId', 0)" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES ('$userId', 'Codex Star User', 'star-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Star', 'TEAM', 'ACTIVE', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by, star_count)
    VALUES
        $valuesSql;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-StarSkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-StarDbState([string]$SkillId) {
        return Invoke-PostgresScalar -Sql "SELECT (EXISTS (SELECT 1 FROM skill_star WHERE skill_id = $SkillId AND user_id = '$userId')) || '|' || star_count FROM skill WHERE id = $SkillId;"
    }

    $skillIds = @{}
    foreach ($slug in $slugs) {
        $skillIds[$slug] = Get-StarSkillId $slug
    }

    $javaAnonymousStatus = Invoke-SkillStarStatus 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/star"
    $pythonAnonymousStatus = Invoke-SkillStarStatus 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/star"
    $proxyAnonymousStatus = Invoke-SkillStarStatus 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/star"

    $javaStar = Invoke-SkillStarRequest 'Put' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/star" $userId
    $pythonStar = Invoke-SkillStarRequest 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/star" $userId
    $proxyStar = Invoke-SkillStarRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/star" $userId
    Invoke-SkillStarRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/star" $userId | Out-Null

    Start-Sleep -Milliseconds 500

    $javaCheckStarred = Invoke-SkillStarRequest 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/star" $userId
    $pythonCheckStarred = Invoke-SkillStarRequest 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/star" $userId
    $proxyCheckStarred = Invoke-SkillStarRequest 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/star" $userId

    $javaStarState = Get-StarDbState $skillIds[$slugs[0]]
    $pythonStarState = Get-StarDbState $skillIds[$slugs[1]]
    $proxyStarState = Get-StarDbState $skillIds[$slugs[2]]

    $javaV1UnstarStatus = Invoke-SkillStarStatus 'Delete' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/star" $userId
    $pythonV1UnstarStatus = Invoke-SkillStarStatus 'Delete' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/star" $userId
    $proxyWebUnstarStatus = Invoke-SkillStarStatus 'Delete' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/star" $userId

    Start-Sleep -Milliseconds 500

    $javaAfterRejectedUnstarState = Get-StarDbState $skillIds[$slugs[0]]
    $pythonAfterRejectedUnstarState = Get-StarDbState $skillIds[$slugs[1]]
    $proxyAfterJavaOwnedUnstarState = Get-StarDbState $skillIds[$slugs[2]]

    $pythonRatingPutStatus = Invoke-SkillStarStatus 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId
    $pythonSubscriptionPutStatus = Invoke-SkillStarStatus 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/subscription" $userId
    $proxyRatingPutStatus = Invoke-SkillStarStatus 'Put' "$WebUrl/api/v1/skills/$($skillIds[$slugs[2]])/rating" $userId
    $proxySubscriptionPutStatus = Invoke-SkillStarStatus 'Put' "$WebUrl/api/v1/skills/$($skillIds[$slugs[2]])/subscription" $userId

    $stableStar = [ordered]@{
        java = ConvertTo-StableSkillStarMutationJson -Response $javaStar
        python = ConvertTo-StableSkillStarMutationJson -Response $pythonStar
        proxy = ConvertTo-StableSkillStarMutationJson -Response $proxyStar
    }
    $stableCheck = [ordered]@{
        java = ConvertTo-StableSkillStarReadJson -Response $javaCheckStarred
        python = ConvertTo-StableSkillStarReadJson -Response $pythonCheckStarred
        proxy = ConvertTo-StableSkillStarReadJson -Response $proxyCheckStarred
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            unauthenticatedReadRejected = ($javaAnonymousStatus -eq 401 -and $pythonAnonymousStatus -eq 401 -and $proxyAnonymousStatus -eq 401)
            starResponsesMatch = ($stableStar.java -eq $stableStar.python -and $stableStar.python -eq $stableStar.proxy)
            authenticatedReadMatches = ($stableCheck.java -eq $stableCheck.python -and $stableCheck.python -eq $stableCheck.proxy)
            starDbState = ($javaStarState -eq 'true|1' -and $pythonStarState -eq 'true|1' -and $proxyStarState -eq 'true|1')
            javaV1UnstarKnownPolicyMismatch = ($javaV1UnstarStatus -eq 403 -and $javaAfterRejectedUnstarState -eq 'true|1')
            pythonV1UnstarOwned = ($pythonV1UnstarStatus -eq 200 -and $pythonAfterRejectedUnstarState -eq 'false|0')
            proxyWebUnstarPythonOwned = ($proxyWebUnstarStatus -eq 200 -and $proxyAfterJavaOwnedUnstarState -eq 'false|0')
        }
        routeBoundaries = [ordered]@{
            javaAnonymousStatus = $javaAnonymousStatus
            pythonAnonymousStatus = $pythonAnonymousStatus
            proxyAnonymousStatus = $proxyAnonymousStatus
            javaV1UnstarStatus = $javaV1UnstarStatus
            pythonV1UnstarStatus = $pythonV1UnstarStatus
            proxyWebUnstarStatus = $proxyWebUnstarStatus
            pythonRatingPutStatus = $pythonRatingPutStatus
            pythonSubscriptionPutStatus = $pythonSubscriptionPutStatus
            proxyRatingPutStatus = $proxyRatingPutStatus
            proxySubscriptionPutStatus = $proxySubscriptionPutStatus
        }
        stableStar = $stableStar
        stableCheck = $stableCheck
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill star contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillStarSmokeVerification {
    try {
        Invoke-SkillStarTests
        Start-Hybrid
        Invoke-SkillStarContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillSubscriptionTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_subscription.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillSubscriptionRequest {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = ''
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    return Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers
}

function Invoke-SkillSubscriptionStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = ''
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    try {
        Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillSubscriptionMutationJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        dataIsNull = ($null -eq $Response.data)
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableSkillSubscriptionReadJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [bool]$Response.data
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillSubscriptionContractComparison {
    param([string]$ResultFileName = 'skill-subscription-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-subscription-$suffix"
    $userId = "codex-subscription-user-$suffix"
    $slugs = @(
        "java-subscription-$suffix",
        "python-subscription-$suffix",
        "proxy-subscription-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Skill Subscription', 'Skill subscription contract', '$userId', 'PUBLIC', 'ACTIVE', '$userId', '$userId', 0)" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES ('$userId', 'Codex Subscription User', 'subscription-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Subscription', 'TEAM', 'ACTIVE', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by, subscription_count)
    VALUES
        $valuesSql;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-SubscriptionSkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-SubscriptionDbState([string]$SkillId) {
        return Invoke-PostgresScalar -Sql "SELECT (EXISTS (SELECT 1 FROM skill_subscription WHERE skill_id = $SkillId AND user_id = '$userId')) || '|' || subscription_count FROM skill WHERE id = $SkillId;"
    }

    $skillIds = @{}
    foreach ($slug in $slugs) {
        $skillIds[$slug] = Get-SubscriptionSkillId $slug
    }

    $javaAnonymousCheck = Invoke-SkillSubscriptionRequest 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/subscription"
    $pythonAnonymousCheck = Invoke-SkillSubscriptionRequest 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/subscription"
    $proxyAnonymousCheck = Invoke-SkillSubscriptionRequest 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/subscription"

    $javaSubscribe = Invoke-SkillSubscriptionRequest 'Put' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/subscription" $userId
    $pythonSubscribe = Invoke-SkillSubscriptionRequest 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/subscription" $userId
    $proxySubscribe = Invoke-SkillSubscriptionRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/subscription" $userId
    Invoke-SkillSubscriptionRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/subscription" $userId | Out-Null

    Start-Sleep -Milliseconds 500

    $javaCheckSubscribed = Invoke-SkillSubscriptionRequest 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/subscription" $userId
    $pythonCheckSubscribed = Invoke-SkillSubscriptionRequest 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/subscription" $userId
    $proxyCheckSubscribed = Invoke-SkillSubscriptionRequest 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/subscription" $userId

    $javaSubscriptionState = Get-SubscriptionDbState $skillIds[$slugs[0]]
    $pythonSubscriptionState = Get-SubscriptionDbState $skillIds[$slugs[1]]
    $proxySubscriptionState = Get-SubscriptionDbState $skillIds[$slugs[2]]

    $javaV1UnsubscribeStatus = Invoke-SkillSubscriptionStatus 'Delete' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/subscription" $userId
    $pythonV1UnsubscribeStatus = Invoke-SkillSubscriptionStatus 'Delete' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/subscription" $userId
    $proxyWebUnsubscribeStatus = Invoke-SkillSubscriptionStatus 'Delete' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/subscription" $userId

    Start-Sleep -Milliseconds 500

    $javaAfterRejectedUnsubscribeState = Get-SubscriptionDbState $skillIds[$slugs[0]]
    $pythonAfterRejectedUnsubscribeState = Get-SubscriptionDbState $skillIds[$slugs[1]]
    $proxyAfterJavaOwnedUnsubscribeState = Get-SubscriptionDbState $skillIds[$slugs[2]]

    $pythonRatingPutStatus = Invoke-SkillSubscriptionStatus 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId
    $proxyMeSubscriptionsStatus = Invoke-SkillSubscriptionStatus 'Get' "$WebUrl/api/v1/me/subscriptions" $userId

    $stableAnonymousCheck = [ordered]@{
        java = ConvertTo-StableSkillSubscriptionReadJson -Response $javaAnonymousCheck
        python = ConvertTo-StableSkillSubscriptionReadJson -Response $pythonAnonymousCheck
        proxy = ConvertTo-StableSkillSubscriptionReadJson -Response $proxyAnonymousCheck
    }
    $stableSubscribe = [ordered]@{
        java = ConvertTo-StableSkillSubscriptionMutationJson -Response $javaSubscribe
        python = ConvertTo-StableSkillSubscriptionMutationJson -Response $pythonSubscribe
        proxy = ConvertTo-StableSkillSubscriptionMutationJson -Response $proxySubscribe
    }
    $stableCheck = [ordered]@{
        java = ConvertTo-StableSkillSubscriptionReadJson -Response $javaCheckSubscribed
        python = ConvertTo-StableSkillSubscriptionReadJson -Response $pythonCheckSubscribed
        proxy = ConvertTo-StableSkillSubscriptionReadJson -Response $proxyCheckSubscribed
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            anonymousReadMatchesFalse = ($stableAnonymousCheck.java -eq $stableAnonymousCheck.python -and $stableAnonymousCheck.python -eq $stableAnonymousCheck.proxy -and $stableAnonymousCheck.java -like '*"data":false*')
            subscribeResponsesMatch = ($stableSubscribe.java -eq $stableSubscribe.python -and $stableSubscribe.python -eq $stableSubscribe.proxy)
            authenticatedReadMatches = ($stableCheck.java -eq $stableCheck.python -and $stableCheck.python -eq $stableCheck.proxy)
            subscriptionDbState = ($javaSubscriptionState -eq 'true|1' -and $pythonSubscriptionState -eq 'true|1' -and $proxySubscriptionState -eq 'true|1')
            javaV1UnsubscribeKnownPolicyMismatch = ($javaV1UnsubscribeStatus -eq 403 -and $javaAfterRejectedUnsubscribeState -eq 'true|1')
            pythonV1UnsubscribeOwned = ($pythonV1UnsubscribeStatus -eq 200 -and $pythonAfterRejectedUnsubscribeState -eq 'false|0')
            proxyWebUnsubscribePythonOwned = ($proxyWebUnsubscribeStatus -eq 200 -and $proxyAfterJavaOwnedUnsubscribeState -eq 'false|0')
            meSubscriptionsStillPythonOwned = ($proxyMeSubscriptionsStatus -ne 405)
        }
        routeBoundaries = [ordered]@{
            javaV1UnsubscribeStatus = $javaV1UnsubscribeStatus
            pythonV1UnsubscribeStatus = $pythonV1UnsubscribeStatus
            proxyWebUnsubscribeStatus = $proxyWebUnsubscribeStatus
            pythonRatingPutStatus = $pythonRatingPutStatus
            proxyMeSubscriptionsStatus = $proxyMeSubscriptionsStatus
        }
        stableAnonymousCheck = $stableAnonymousCheck
        stableSubscribe = $stableSubscribe
        stableCheck = $stableCheck
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill subscription contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillSubscriptionSmokeVerification {
    try {
        Invoke-SkillSubscriptionTests
        Start-Hybrid
        Invoke-SkillSubscriptionContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-SkillRatingTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_skill_rating.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-SkillRatingRequest {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = '',
        [object]$Body = $null
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    if ($null -eq $Body) {
        return Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers
    }
    return Invoke-RestMethod -Uri $Url -Method $Method -Headers $headers -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 10)
}

function Invoke-SkillRatingStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId = '',
        [object]$Body = $null
    )

    try {
        Invoke-SkillRatingRequest -Method $Method -Url $Url -UserId $UserId -Body $Body | Out-Null
        return 200
    } catch [System.Net.WebException] {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableSkillRatingMutationJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        dataIsNull = ($null -eq $Response.data)
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableSkillRatingReadJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        score = [int]$Response.data.score
        rated = [bool]$Response.data.rated
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-SkillRatingContractComparison {
    param([string]$ResultFileName = 'skill-rating-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-rating-$suffix"
    $userId = "codex-rating-user-$suffix"
    $slugs = @(
        "java-rating-$suffix",
        "python-rating-$suffix",
        "proxy-rating-$suffix"
    )
    $valuesSql = ($slugs | ForEach-Object { "(ns_id, '$($_)', 'Skill Rating', 'Skill rating contract', '$userId', 'PUBLIC', 'ACTIVE', '$userId', '$userId')" }) -join ",`n        "

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES ('$userId', 'Codex Rating User', 'rating-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Rating', 'TEAM', 'ACTIVE', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, created_by, updated_by)
    VALUES
        $valuesSql;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Get-RatingSkillId([string]$Slug) {
        return Invoke-PostgresScalar -Sql "SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug = '$namespace' AND s.slug = '$Slug' LIMIT 1;"
    }
    function Get-RatingDbState([string]$SkillId) {
        return Invoke-PostgresScalar -Sql "SELECT (EXISTS (SELECT 1 FROM skill_rating WHERE skill_id = $SkillId AND user_id = '$userId')) || '|' || COALESCE((SELECT score::text FROM skill_rating WHERE skill_id = $SkillId AND user_id = '$userId'), '') || '|' || to_char(rating_avg, 'FM999990.00') || '|' || rating_count FROM skill WHERE id = $SkillId;"
    }

    $skillIds = @{}
    foreach ($slug in $slugs) {
        $skillIds[$slug] = Get-RatingSkillId $slug
    }

    $javaAnonymousStatus = Invoke-SkillRatingStatus 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating"
    $pythonAnonymousStatus = Invoke-SkillRatingStatus 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating"
    $proxyAnonymousStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating"

    $javaInitialRead = Invoke-SkillRatingRequest 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating" $userId
    $pythonInitialRead = Invoke-SkillRatingRequest 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId
    $proxyInitialRead = Invoke-SkillRatingRequest 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating" $userId

    $javaRate = Invoke-SkillRatingRequest 'Put' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating" $userId @{ score = 4 }
    $pythonRate = Invoke-SkillRatingRequest 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId @{ score = 4 }
    $proxyRate = Invoke-SkillRatingRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating" $userId @{ score = 4 }

    Start-Sleep -Milliseconds 500

    $javaUpdate = Invoke-SkillRatingRequest 'Put' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating" $userId @{ score = 2 }
    $pythonUpdate = Invoke-SkillRatingRequest 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId @{ score = 2 }
    $proxyUpdate = Invoke-SkillRatingRequest 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating" $userId @{ score = 2 }

    Start-Sleep -Milliseconds 1000

    $javaFinalRead = Invoke-SkillRatingRequest 'Get' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating" $userId
    $pythonFinalRead = Invoke-SkillRatingRequest 'Get' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId
    $proxyFinalRead = Invoke-SkillRatingRequest 'Get' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating" $userId

    $javaDbState = Get-RatingDbState $skillIds[$slugs[0]]
    $pythonDbState = Get-RatingDbState $skillIds[$slugs[1]]
    $proxyDbState = Get-RatingDbState $skillIds[$slugs[2]]

    $javaInvalidStatus = Invoke-SkillRatingStatus 'Put' "$JavaUrl/api/v1/skills/$($skillIds[$slugs[0]])/rating" $userId @{ score = 0 }
    $pythonInvalidStatus = Invoke-SkillRatingStatus 'Put' "$PythonUrl/api/v1/skills/$($skillIds[$slugs[1]])/rating" $userId @{ score = 0 }
    $proxyInvalidStatus = Invoke-SkillRatingStatus 'Put' "$WebUrl/api/web/skills/$($skillIds[$slugs[2]])/rating" $userId @{ score = 0 }
    $proxyMeStarsStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl/api/v1/me/stars" $userId
    $proxyMeSubscriptionsStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl/api/v1/me/subscriptions" $userId

    $stableInitialRead = [ordered]@{
        java = ConvertTo-StableSkillRatingReadJson -Response $javaInitialRead
        python = ConvertTo-StableSkillRatingReadJson -Response $pythonInitialRead
        proxy = ConvertTo-StableSkillRatingReadJson -Response $proxyInitialRead
    }
    $stableRate = [ordered]@{
        java = ConvertTo-StableSkillRatingMutationJson -Response $javaRate
        python = ConvertTo-StableSkillRatingMutationJson -Response $pythonRate
        proxy = ConvertTo-StableSkillRatingMutationJson -Response $proxyRate
    }
    $stableUpdate = [ordered]@{
        java = ConvertTo-StableSkillRatingMutationJson -Response $javaUpdate
        python = ConvertTo-StableSkillRatingMutationJson -Response $pythonUpdate
        proxy = ConvertTo-StableSkillRatingMutationJson -Response $proxyUpdate
    }
    $stableFinalRead = [ordered]@{
        java = ConvertTo-StableSkillRatingReadJson -Response $javaFinalRead
        python = ConvertTo-StableSkillRatingReadJson -Response $pythonFinalRead
        proxy = ConvertTo-StableSkillRatingReadJson -Response $proxyFinalRead
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            unauthenticatedReadRejected = ($javaAnonymousStatus -eq 401 -and $pythonAnonymousStatus -eq 401 -and $proxyAnonymousStatus -eq 401)
            initialReadMatches = ($stableInitialRead.java -eq $stableInitialRead.python -and $stableInitialRead.python -eq $stableInitialRead.proxy -and $stableInitialRead.java -like '*"score":0*"rated":false*')
            rateResponsesMatch = ($stableRate.java -eq $stableRate.python -and $stableRate.python -eq $stableRate.proxy)
            updateResponsesMatch = ($stableUpdate.java -eq $stableUpdate.python -and $stableUpdate.python -eq $stableUpdate.proxy)
            finalReadMatches = ($stableFinalRead.java -eq $stableFinalRead.python -and $stableFinalRead.python -eq $stableFinalRead.proxy -and $stableFinalRead.java -like '*"score":2*"rated":true*')
            ratingDbState = ($javaDbState -eq 'true|2|2.00|1' -and $pythonDbState -eq 'true|2|2.00|1' -and $proxyDbState -eq 'true|2|2.00|1')
            invalidScoreRejected = ($javaInvalidStatus -eq 400 -and $pythonInvalidStatus -eq 400 -and $proxyInvalidStatus -eq 400)
            meStarsStillJavaOwned = ($proxyMeStarsStatus -ne 405)
            meSubscriptionsStillJavaOwned = ($proxyMeSubscriptionsStatus -ne 405)
        }
        routeBoundaries = [ordered]@{
            javaAnonymousStatus = $javaAnonymousStatus
            pythonAnonymousStatus = $pythonAnonymousStatus
            proxyAnonymousStatus = $proxyAnonymousStatus
            javaInvalidStatus = $javaInvalidStatus
            pythonInvalidStatus = $pythonInvalidStatus
            proxyInvalidStatus = $proxyInvalidStatus
            proxyMeStarsStatus = $proxyMeStarsStatus
            proxyMeSubscriptionsStatus = $proxyMeSubscriptionsStatus
        }
        dbState = [ordered]@{
            java = $javaDbState
            python = $pythonDbState
            proxy = $proxyDbState
        }
        stableInitialRead = $stableInitialRead
        stableRate = $stableRate
        stableUpdate = $stableUpdate
        stableFinalRead = $stableFinalRead
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Skill rating contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridSkillRatingSmokeVerification {
    try {
        Invoke-SkillRatingTests
        Start-Hybrid
        Invoke-SkillRatingContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-MySocialListsTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_my_social_lists.py', 'tests/test_skill_star.py', 'tests/test_skill_subscription.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath '.\node_modules\.bin\vitest.CMD' -Arguments @('run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableMySocialListJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.items)) {
        $items += [ordered]@{
            id = [int]$item.id
            slug = $item.slug
            displayName = $item.displayName
            summary = $item.summary
            visibility = $item.visibility
            status = $item.status
            downloadCount = [int]$item.downloadCount
            starCount = [int]$item.starCount
            ratingAvg = [double]$item.ratingAvg
            ratingCount = [int]$item.ratingCount
            namespace = $item.namespace
            updatedAt = $item.updatedAt
            canSubmitPromotion = [bool]$item.canSubmitPromotion
            headlineVersion = $item.headlineVersion
            publishedVersion = $item.publishedVersion
            ownerPreviewVersion = $item.ownerPreviewVersion
            resolutionMode = $item.resolutionMode
        }
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            items = $items
            total = [int]$Response.data.total
            page = [int]$Response.data.page
            size = [int]$Response.data.size
        }
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-MySocialListsContractComparison {
    param([string]$ResultFileName = 'my-social-lists-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $namespace = "codex-social-list-$suffix"
    $userId = "codex-social-list-user-$suffix"
    $slug = "social-list-skill-$suffix"

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    fixture_skill_id BIGINT;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES ('$userId', 'Codex Social List User', 'social-list-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex Social List', 'GLOBAL', 'ACTIVE', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    SELECT id INTO fixture_skill_id
    FROM skill
    WHERE namespace_id = ns_id AND slug = '$slug'
    LIMIT 1;

    IF fixture_skill_id IS NULL THEN
        INSERT INTO skill (
            namespace_id, slug, display_name, summary, owner_id, visibility, status,
            download_count, star_count, subscription_count, rating_avg, rating_count,
            created_by, updated_by, updated_at
        )
        VALUES (
            ns_id, '$slug', 'Social List Skill', 'Social list contract fixture', '$userId',
            'PUBLIC', 'ACTIVE', 7, 1, 1, 4.50, 2, '$userId', '$userId',
            '2026-06-10T08:00:00Z'::timestamptz
        )
        RETURNING id INTO fixture_skill_id;
    ELSE
        UPDATE skill
        SET display_name = 'Social List Skill',
            summary = 'Social list contract fixture',
            owner_id = '$userId',
            visibility = 'PUBLIC',
            status = 'ACTIVE',
            download_count = 7,
            star_count = 1,
            subscription_count = 1,
            rating_avg = 4.50,
            rating_count = 2,
            updated_by = '$userId',
            updated_at = '2026-06-10T08:00:00Z'::timestamptz
        WHERE id = fixture_skill_id;
    END IF;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        fixture_skill_id, '1.0.0', 'PUBLISHED', 'social list fixture',
        jsonb_build_object('name', 'Social List Skill', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 32, '2026-06-10T08:05:00Z'::timestamptz, '$userId',
        '2026-06-10T08:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
    SET status = 'PUBLISHED',
        changelog = EXCLUDED.changelog,
        parsed_metadata_json = EXCLUDED.parsed_metadata_json,
        manifest_json = EXCLUDED.manifest_json,
        file_count = EXCLUDED.file_count,
        total_size = EXCLUDED.total_size,
        published_at = EXCLUDED.published_at,
        created_at = EXCLUDED.created_at,
        bundle_ready = TRUE,
        download_ready = TRUE,
        requested_visibility = 'PUBLIC'
    RETURNING id INTO version_id;

    UPDATE skill
    SET latest_version_id = version_id
    WHERE id = fixture_skill_id;

    INSERT INTO skill_star (skill_id, user_id, created_at)
    VALUES (fixture_skill_id, '$userId', '2026-06-10T08:10:00Z'::timestamptz)
    ON CONFLICT (skill_id, user_id) DO UPDATE
    SET created_at = EXCLUDED.created_at;

    INSERT INTO skill_subscription (skill_id, user_id, created_at)
    VALUES (fixture_skill_id, '$userId', '2026-06-10T08:11:00Z'::timestamptz)
    ON CONFLICT (skill_id, user_id) DO UPDATE
    SET created_at = EXCLUDED.created_at;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $headers = @{ 'X-Mock-User-Id' = $userId }
    $starsPath = '/api/v1/me/stars?page=0&size=12'
    $starsWebPath = '/api/web/me/stars?page=0&size=12'
    $subscriptionsPath = '/api/v1/me/subscriptions?page=0&size=12'
    $subscriptionsWebPath = '/api/web/me/subscriptions?page=0&size=12'

    $javaStars = Invoke-RestMethod "$JavaUrl$starsPath" -Headers $headers
    $pythonStars = Invoke-RestMethod "$PythonUrl$starsPath" -Headers $headers
    $proxyStars = Invoke-RestMethod "$WebUrl$starsWebPath" -Headers $headers
    $javaSubscriptions = Invoke-RestMethod "$JavaUrl$subscriptionsPath" -Headers $headers
    $pythonSubscriptions = Invoke-RestMethod "$PythonUrl$subscriptionsPath" -Headers $headers
    $proxySubscriptions = Invoke-RestMethod "$WebUrl$subscriptionsWebPath" -Headers $headers

    $starsStable = [ordered]@{
        java = ConvertTo-StableMySocialListJson -Response $javaStars
        python = ConvertTo-StableMySocialListJson -Response $pythonStars
        proxy = ConvertTo-StableMySocialListJson -Response $proxyStars
    }
    $subscriptionsStable = [ordered]@{
        java = ConvertTo-StableMySocialListJson -Response $javaSubscriptions
        python = ConvertTo-StableMySocialListJson -Response $pythonSubscriptions
        proxy = ConvertTo-StableMySocialListJson -Response $proxySubscriptions
    }

    $javaAnonymousStarsStatus = Invoke-SkillRatingStatus 'Get' "$JavaUrl$starsPath"
    $pythonAnonymousStarsStatus = Invoke-SkillRatingStatus 'Get' "$PythonUrl$starsPath"
    $proxyAnonymousStarsStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl$starsWebPath"
    $javaAnonymousSubscriptionsStatus = Invoke-SkillRatingStatus 'Get' "$JavaUrl$subscriptionsPath"
    $pythonAnonymousSubscriptionsStatus = Invoke-SkillRatingStatus 'Get' "$PythonUrl$subscriptionsPath"
    $proxyAnonymousSubscriptionsStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl$subscriptionsWebPath"
    $proxyMySkillsStatus = Invoke-SkillRatingStatus 'Get' "$WebUrl/api/v1/me/skills" $userId

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            starsMatch = ($starsStable.java -eq $starsStable.python -and $starsStable.python -eq $starsStable.proxy)
            subscriptionsMatch = ($subscriptionsStable.java -eq $subscriptionsStable.python -and $subscriptionsStable.python -eq $subscriptionsStable.proxy)
            starsContainFixture = ($javaStars.data.total -eq 1 -and $javaStars.data.items[0].slug -eq $slug -and $javaStars.data.items[0].publishedVersion.version -eq '1.0.0')
            subscriptionsContainFixture = ($javaSubscriptions.data.total -eq 1 -and $javaSubscriptions.data.items[0].slug -eq $slug -and $javaSubscriptions.data.items[0].publishedVersion.version -eq '1.0.0')
            anonymousStarsRejected = ($javaAnonymousStarsStatus -eq 401 -and $pythonAnonymousStarsStatus -eq 401 -and $proxyAnonymousStarsStatus -eq 401)
            anonymousSubscriptionsRejected = ($javaAnonymousSubscriptionsStatus -eq 401 -and $pythonAnonymousSubscriptionsStatus -eq 401 -and $proxyAnonymousSubscriptionsStatus -eq 401)
            mySkillsStillJavaOwned = ($proxyMySkillsStatus -ne 405)
        }
        routeBoundaries = [ordered]@{
            javaAnonymousStarsStatus = $javaAnonymousStarsStatus
            pythonAnonymousStarsStatus = $pythonAnonymousStarsStatus
            proxyAnonymousStarsStatus = $proxyAnonymousStarsStatus
            javaAnonymousSubscriptionsStatus = $javaAnonymousSubscriptionsStatus
            pythonAnonymousSubscriptionsStatus = $pythonAnonymousSubscriptionsStatus
            proxyAnonymousSubscriptionsStatus = $proxyAnonymousSubscriptionsStatus
            proxyMySkillsStatus = $proxyMySkillsStatus
        }
        starsStable = $starsStable
        subscriptionsStable = $subscriptionsStable
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "My social lists contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridMySocialListsSmokeVerification {
    try {
        Invoke-MySocialListsTests
        Start-Hybrid
        Invoke-MySocialListsContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NotificationReadTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_notifications.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-NotificationRequest {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId
    )

    $headers = @{ 'X-Mock-User-Id' = $UserId }
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec 15
}

function Invoke-NotificationStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId
    )

    $headers = if ($UserId) { @{ 'X-Mock-User-Id' = $UserId } } else { @{} }
    try {
        Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers -UseBasicParsing -TimeoutSec 15 | Out-Null
        return 200
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableNotificationListJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.items)) {
        $items += [ordered]@{
            category = $item.category
            eventType = $item.eventType
            title = $item.title
            bodyJson = $item.bodyJson
            entityType = $item.entityType
            entityId = $item.entityId
            status = $item.status
            targetType = $item.targetType
            targetId = $item.targetId
            targetRoute = $item.targetRoute
            hasCreatedAt = [bool]$item.createdAt
            hasReadAt = [bool]$item.readAt
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        total = $Response.data.total
        page = $Response.data.page
        size = $Response.data.size
        items = $items
    } | ConvertTo-Json -Depth 20 -Compress)
}

function Get-NotificationIdByEventType {
    param([string]$EventType)

    return Invoke-PostgresScalar -Sql "SELECT id FROM notification WHERE event_type = '$EventType' LIMIT 1;"
}

function Get-NotificationStatusByEventType {
    param([string]$EventType)

    return Invoke-PostgresScalar -Sql "SELECT status FROM notification WHERE event_type = '$EventType' LIMIT 1;"
}

function Get-NotificationCountByEventType {
    param([string]$EventType)

    return [int](Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM notification WHERE event_type = '$EventType';")
}

function Invoke-NotificationReadContractComparison {
    param([string]$ResultFileName = 'notification-read-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $javaUser = "codex-notification-java-$suffix"
    $pythonUser = "codex-notification-python-$suffix"
    $proxyUser = "codex-notification-proxy-$suffix"
    $users = @($javaUser, $pythonUser, $proxyUser)
    $userValues = ($users | ForEach-Object {
        "('$_', 'Codex Notification User', '$_@example.test', '', 'ACTIVE')"
    }) -join ",`n        "
    $userList = ($users | ForEach-Object { "'$_'" }) -join ','

    $sql = @"
INSERT INTO user_account (id, display_name, email, avatar_url, status)
VALUES
        $userValues
ON CONFLICT (id) DO UPDATE
SET display_name = EXCLUDED.display_name,
    email = EXCLUDED.email,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

DELETE FROM notification WHERE recipient_id IN ($userList);

INSERT INTO notification (recipient_id, category, event_type, title, body_json, entity_type, entity_id, status, created_at, read_at)
SELECT recipient_id, category, event_type, title, body_json, entity_type, entity_id, status, created_at, read_at
FROM (VALUES
    ('$javaUser', 'REVIEW', 'CODEX_NOTIFICATION_LIST_REVIEW_$suffix', 'Review submitted', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7001, 'UNREAD', '2026-06-10T09:00:00Z'::timestamptz, NULL),
    ('$javaUser', 'PUBLISH', 'CODEX_NOTIFICATION_LIST_PUBLISH_$suffix', 'Published', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7002, 'READ', '2026-06-10T08:00:00Z'::timestamptz, '2026-06-10T08:30:00Z'::timestamptz),
    ('$pythonUser', 'REVIEW', 'CODEX_NOTIFICATION_LIST_REVIEW_$suffix', 'Review submitted', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7001, 'UNREAD', '2026-06-10T09:00:00Z'::timestamptz, NULL),
    ('$pythonUser', 'PUBLISH', 'CODEX_NOTIFICATION_LIST_PUBLISH_$suffix', 'Published', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7002, 'READ', '2026-06-10T08:00:00Z'::timestamptz, '2026-06-10T08:30:00Z'::timestamptz),
    ('$proxyUser', 'REVIEW', 'CODEX_NOTIFICATION_LIST_REVIEW_$suffix', 'Review submitted', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7001, 'UNREAD', '2026-06-10T09:00:00Z'::timestamptz, NULL),
    ('$proxyUser', 'PUBLISH', 'CODEX_NOTIFICATION_LIST_PUBLISH_$suffix', 'Published', jsonb_build_object('namespace', 'team-a', 'slug', 'demo')::text, 'SKILL', 7002, 'READ', '2026-06-10T08:00:00Z'::timestamptz, '2026-06-10T08:30:00Z'::timestamptz),
    ('$javaUser', 'REVIEW', 'CODEX_NOTIFICATION_MARK_READ_JAVA_$suffix', 'Mark java', jsonb_build_object()::text, 'REVIEW', 7101, 'UNREAD', '2026-06-10T07:00:00Z'::timestamptz, NULL),
    ('$pythonUser', 'REVIEW', 'CODEX_NOTIFICATION_MARK_READ_PYTHON_$suffix', 'Mark python', jsonb_build_object()::text, 'REVIEW', 7102, 'UNREAD', '2026-06-10T07:00:00Z'::timestamptz, NULL),
    ('$proxyUser', 'REVIEW', 'CODEX_NOTIFICATION_MARK_READ_PROXY_$suffix', 'Mark proxy', jsonb_build_object()::text, 'REVIEW', 7103, 'UNREAD', '2026-06-10T07:00:00Z'::timestamptz, NULL),
    ('$javaUser', 'REPORT', 'CODEX_NOTIFICATION_DELETE_JAVA_$suffix', 'Delete java', jsonb_build_object()::text, 'REPORT', 7201, 'READ', '2026-06-10T06:00:00Z'::timestamptz, '2026-06-10T06:30:00Z'::timestamptz),
    ('$pythonUser', 'REPORT', 'CODEX_NOTIFICATION_DELETE_PYTHON_$suffix', 'Delete python', jsonb_build_object()::text, 'REPORT', 7202, 'READ', '2026-06-10T06:00:00Z'::timestamptz, '2026-06-10T06:30:00Z'::timestamptz),
    ('$proxyUser', 'REPORT', 'CODEX_NOTIFICATION_DELETE_PROXY_$suffix', 'Delete proxy', jsonb_build_object()::text, 'REPORT', 7203, 'READ', '2026-06-10T06:00:00Z'::timestamptz, '2026-06-10T06:30:00Z'::timestamptz),
    ('$javaUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_JAVA_A_$suffix', 'All java a', jsonb_build_object()::text, 'SKILL', 7301, 'UNREAD', '2026-06-10T05:00:00Z'::timestamptz, NULL),
    ('$javaUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_JAVA_B_$suffix', 'All java b', jsonb_build_object()::text, 'SKILL', 7302, 'UNREAD', '2026-06-10T05:01:00Z'::timestamptz, NULL),
    ('$pythonUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_PYTHON_A_$suffix', 'All python a', jsonb_build_object()::text, 'SKILL', 7303, 'UNREAD', '2026-06-10T05:00:00Z'::timestamptz, NULL),
    ('$pythonUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_PYTHON_B_$suffix', 'All python b', jsonb_build_object()::text, 'SKILL', 7304, 'UNREAD', '2026-06-10T05:01:00Z'::timestamptz, NULL),
    ('$proxyUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_PROXY_A_$suffix', 'All proxy a', jsonb_build_object()::text, 'SKILL', 7305, 'UNREAD', '2026-06-10T05:00:00Z'::timestamptz, NULL),
    ('$proxyUser', 'PUBLISH', 'CODEX_NOTIFICATION_ALL_PROXY_B_$suffix', 'All proxy b', jsonb_build_object()::text, 'SKILL', 7306, 'UNREAD', '2026-06-10T05:01:00Z'::timestamptz, NULL)
) AS fixture(recipient_id, category, event_type, title, body_json, entity_type, entity_id, status, created_at, read_at);
"@
    Invoke-PostgresSql -Sql $sql

    $javaList = Invoke-NotificationRequest 'Get' "$JavaUrl/api/v1/notifications?page=0&size=2" $javaUser
    $pythonList = Invoke-NotificationRequest 'Get' "$PythonUrl/api/v1/notifications?page=0&size=2" $pythonUser
    $proxyList = Invoke-NotificationRequest 'Get' "$WebUrl/api/web/notifications?page=0&size=2" $proxyUser
    $javaReview = Invoke-NotificationRequest 'Get' "$JavaUrl/api/v1/notifications?page=0&size=1&category=REVIEW" $javaUser
    $pythonReview = Invoke-NotificationRequest 'Get' "$PythonUrl/api/v1/notifications?page=0&size=1&category=REVIEW" $pythonUser
    $proxyReview = Invoke-NotificationRequest 'Get' "$WebUrl/api/web/notifications?page=0&size=1&category=REVIEW" $proxyUser
    $javaUnread = Invoke-NotificationRequest 'Get' "$JavaUrl/api/v1/notifications/unread-count" $javaUser
    $pythonUnread = Invoke-NotificationRequest 'Get' "$PythonUrl/api/v1/notifications/unread-count" $pythonUser
    $proxyUnread = Invoke-NotificationRequest 'Get' "$WebUrl/api/web/notifications/unread-count" $proxyUser

    $javaMarkId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_MARK_READ_JAVA_$suffix"
    $pythonMarkId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_MARK_READ_PYTHON_$suffix"
    $proxyMarkId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_MARK_READ_PROXY_$suffix"
    $javaDeleteId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_DELETE_JAVA_$suffix"
    $pythonDeleteId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_DELETE_PYTHON_$suffix"
    $proxyDeleteId = Get-NotificationIdByEventType "CODEX_NOTIFICATION_DELETE_PROXY_$suffix"

    $javaMark = Invoke-NotificationRequest 'Put' "$JavaUrl/api/v1/notifications/$javaMarkId/read" $javaUser
    $pythonMark = Invoke-NotificationRequest 'Put' "$PythonUrl/api/v1/notifications/$pythonMarkId/read" $pythonUser
    $proxyMark = Invoke-NotificationRequest 'Put' "$WebUrl/api/web/notifications/$proxyMarkId/read" $proxyUser

    $javaAll = Invoke-NotificationRequest 'Put' "$JavaUrl/api/v1/notifications/read-all" $javaUser
    $pythonAll = Invoke-NotificationRequest 'Put' "$PythonUrl/api/v1/notifications/read-all" $pythonUser
    $proxyAll = Invoke-NotificationRequest 'Put' "$WebUrl/api/web/notifications/read-all" $proxyUser

    $javaDelete = Invoke-NotificationRequest 'Delete' "$JavaUrl/api/v1/notifications/$javaDeleteId" $javaUser
    $pythonDelete = Invoke-NotificationRequest 'Delete' "$PythonUrl/api/v1/notifications/$pythonDeleteId" $pythonUser
    $proxyDelete = Invoke-NotificationRequest 'Delete' "$WebUrl/api/web/notifications/$proxyDeleteId" $proxyUser

    $javaInvalid = Invoke-NotificationStatus 'Get' "$JavaUrl/api/v1/notifications?category=review" $javaUser
    $pythonInvalid = Invoke-NotificationStatus 'Get' "$PythonUrl/api/v1/notifications?category=review" $pythonUser
    $proxyInvalid = Invoke-NotificationStatus 'Get' "$WebUrl/api/web/notifications?category=review" $proxyUser
    $anonymousProxy = Invoke-NotificationStatus 'Get' "$WebUrl/api/web/notifications" $null
    $proxySseBoundary = Invoke-NotificationStatus 'Get' "$WebUrl/api/v1/notifications/sse" $javaUser
    $proxyPreferencesBoundary = Invoke-NotificationStatus 'Get' "$WebUrl/api/v1/notification-preferences" $javaUser

    $javaMarkStatus = Get-NotificationStatusByEventType "CODEX_NOTIFICATION_MARK_READ_JAVA_$suffix"
    $pythonMarkStatus = Get-NotificationStatusByEventType "CODEX_NOTIFICATION_MARK_READ_PYTHON_$suffix"
    $proxyMarkStatus = Get-NotificationStatusByEventType "CODEX_NOTIFICATION_MARK_READ_PROXY_$suffix"
    $javaDeleteCount = Get-NotificationCountByEventType "CODEX_NOTIFICATION_DELETE_JAVA_$suffix"
    $pythonDeleteCount = Get-NotificationCountByEventType "CODEX_NOTIFICATION_DELETE_PYTHON_$suffix"
    $proxyDeleteCount = Get-NotificationCountByEventType "CODEX_NOTIFICATION_DELETE_PROXY_$suffix"
    $listStable = [ordered]@{
        java = ConvertTo-StableNotificationListJson -Response $javaList
        python = ConvertTo-StableNotificationListJson -Response $pythonList
        proxy = ConvertTo-StableNotificationListJson -Response $proxyList
    }
    $reviewStable = [ordered]@{
        java = ConvertTo-StableNotificationListJson -Response $javaReview
        python = ConvertTo-StableNotificationListJson -Response $pythonReview
        proxy = ConvertTo-StableNotificationListJson -Response $proxyReview
    }

    $result = [ordered]@{
        suffix = $suffix
        checks = [ordered]@{
            listMatches = ($listStable.java -eq $listStable.python -and $listStable.python -eq $listStable.proxy)
            reviewFilterMatches = ($reviewStable.java -eq $reviewStable.python -and $reviewStable.python -eq $reviewStable.proxy)
            unreadCountMatches = ($javaUnread.data.count -eq $pythonUnread.data.count -and $pythonUnread.data.count -eq $proxyUnread.data.count)
            markReadEnvelopeMatches = ($javaMark.data -eq $null -and $pythonMark.data -eq $null -and $proxyMark.data -eq $null)
            markAllUpdatedMatches = ($javaAll.data.updated -eq 3 -and $pythonAll.data.updated -eq 3 -and $proxyAll.data.updated -eq 3)
            deleteReadEnvelopeMatches = ($javaDelete.data -eq $null -and $pythonDelete.data -eq $null -and $proxyDelete.data -eq $null)
            invalidCategoryRejected = ($javaInvalid -eq 400 -and $pythonInvalid -eq 400 -and $proxyInvalid -eq 400)
            anonymousRejected = ($anonymousProxy -eq 401)
            routeBoundariesRemainJava = ($proxySseBoundary -ne 404 -and $proxyPreferencesBoundary -ne 405)
            mutationsPersisted = ($javaMarkStatus -eq 'READ' -and $pythonMarkStatus -eq 'READ' -and $proxyMarkStatus -eq 'READ' -and $javaDeleteCount -eq 0 -and $pythonDeleteCount -eq 0 -and $proxyDeleteCount -eq 0)
        }
        listStable = $listStable
        reviewStable = $reviewStable
        counts = [ordered]@{
            javaUnread = $javaUnread.data.count
            pythonUnread = $pythonUnread.data.count
            proxyUnread = $proxyUnread.data.count
            javaAllUpdated = $javaAll.data.updated
            pythonAllUpdated = $pythonAll.data.updated
            proxyAllUpdated = $proxyAll.data.updated
        }
        routeBoundaries = [ordered]@{
            invalidCategory = @($javaInvalid, $pythonInvalid, $proxyInvalid)
            anonymousProxy = $anonymousProxy
            proxySseBoundary = $proxySseBoundary
            proxyPreferencesBoundary = $proxyPreferencesBoundary
        }
        dbStatuses = [ordered]@{
            javaMark = $javaMarkStatus
            pythonMark = $pythonMarkStatus
            proxyMark = $proxyMarkStatus
            javaDeleteCount = $javaDeleteCount
            pythonDeleteCount = $pythonDeleteCount
            proxyDeleteCount = $proxyDeleteCount
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Notification read contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNotificationReadSmokeVerification {
    try {
        Invoke-NotificationReadTests
        Start-Hybrid
        Invoke-NotificationReadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NotificationPreferencesTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_notification_preferences.py', 'tests/test_notifications.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-NotificationPreferencesRequest {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $headers = @{ 'X-Mock-User-Id' = $UserId }
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -TimeoutSec 15
    }
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 20) -TimeoutSec 15
}

function Invoke-NotificationPreferencesStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $headers = @{}
    if (-not [string]::IsNullOrWhiteSpace($UserId)) {
        $headers['X-Mock-User-Id'] = $UserId
    }
    try {
        if ($null -eq $Body) {
            Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers -UseBasicParsing -TimeoutSec 15 | Out-Null
        } else {
            Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 20) -UseBasicParsing -TimeoutSec 15 | Out-Null
        }
        return 200
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableNotificationPreferencesJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data)) {
        $items += [ordered]@{
            category = $item.category
            channel = $item.channel
            enabled = [bool]$item.enabled
        }
    }
    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $items
    } | ConvertTo-Json -Depth 20 -Compress)
}

function Get-NotificationPreferenceEnabled {
    param(
        [string]$UserId,
        [string]$Category
    )

    return Invoke-PostgresScalar -Sql "SELECT enabled FROM notification_preference WHERE user_id = '$UserId' AND category = '$Category' AND channel = 'IN_APP' LIMIT 1;"
}

function Invoke-NotificationPreferencesContractComparison {
    param([string]$ResultFileName = 'notification-preferences-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $javaUser = "codex-notification-pref-java-$suffix"
    $pythonUser = "codex-notification-pref-python-$suffix"
    $proxyUser = "codex-notification-pref-proxy-$suffix"
    $users = @($javaUser, $pythonUser, $proxyUser)
    $userValues = ($users | ForEach-Object {
        "('$_', 'Codex Notification Preference User', '$_@example.test', '', 'ACTIVE')"
    }) -join ",`n        "
    $userList = ($users | ForEach-Object { "'$_'" }) -join ','

    $sql = @"
INSERT INTO user_account (id, display_name, email, avatar_url, status)
VALUES
        $userValues
ON CONFLICT (id) DO UPDATE
SET display_name = EXCLUDED.display_name,
    email = EXCLUDED.email,
    status = EXCLUDED.status,
    updated_at = CURRENT_TIMESTAMP;

DELETE FROM notification_preference WHERE user_id IN ($userList);

INSERT INTO notification_preference (user_id, category, channel, enabled)
VALUES
    ('$javaUser', 'REVIEW', 'IN_APP', FALSE),
    ('$pythonUser', 'REVIEW', 'IN_APP', FALSE),
    ('$proxyUser', 'REVIEW', 'IN_APP', FALSE)
ON CONFLICT (user_id, category, channel)
DO UPDATE SET enabled = EXCLUDED.enabled;
"@
    Invoke-PostgresSql -Sql $sql

    $javaGet = Invoke-NotificationPreferencesRequest 'Get' "$JavaUrl/api/v1/notification-preferences" $javaUser
    $pythonGet = Invoke-NotificationPreferencesRequest 'Get' "$PythonUrl/api/v1/notification-preferences" $pythonUser
    $proxyGet = Invoke-NotificationPreferencesRequest 'Get' "$WebUrl/api/web/notification-preferences" $proxyUser

    $updateBody = @{
        preferences = @(
            @{ category = 'PUBLISH'; channel = 'IN_APP'; enabled = $false },
            @{ category = 'REPORT'; channel = 'IN_APP'; enabled = $false }
        )
    }
    $javaPut = Invoke-NotificationPreferencesRequest 'Put' "$JavaUrl/api/v1/notification-preferences" $javaUser $updateBody
    $pythonPut = Invoke-NotificationPreferencesRequest 'Put' "$PythonUrl/api/v1/notification-preferences" $pythonUser $updateBody
    $proxyPut = Invoke-NotificationPreferencesRequest 'Put' "$WebUrl/api/web/notification-preferences" $proxyUser $updateBody

    $invalidCategoryBody = @{ preferences = @( @{ category = 'review'; channel = 'IN_APP'; enabled = $true } ) }
    $duplicateBody = @{
        preferences = @(
            @{ category = 'REVIEW'; channel = 'IN_APP'; enabled = $true },
            @{ category = 'REVIEW'; channel = 'IN_APP'; enabled = $false }
        )
    }
    $invalidChannelBody = @{ preferences = @( @{ category = 'REVIEW'; channel = 'EMAIL'; enabled = $true } ) }

    $javaInvalidCategory = Invoke-NotificationPreferencesStatus 'Put' "$JavaUrl/api/v1/notification-preferences" $javaUser $invalidCategoryBody
    $pythonInvalidCategory = Invoke-NotificationPreferencesStatus 'Put' "$PythonUrl/api/v1/notification-preferences" $pythonUser $invalidCategoryBody
    $proxyInvalidCategory = Invoke-NotificationPreferencesStatus 'Put' "$WebUrl/api/web/notification-preferences" $proxyUser $invalidCategoryBody
    $javaDuplicate = Invoke-NotificationPreferencesStatus 'Put' "$JavaUrl/api/v1/notification-preferences" $javaUser $duplicateBody
    $pythonDuplicate = Invoke-NotificationPreferencesStatus 'Put' "$PythonUrl/api/v1/notification-preferences" $pythonUser $duplicateBody
    $proxyDuplicate = Invoke-NotificationPreferencesStatus 'Put' "$WebUrl/api/web/notification-preferences" $proxyUser $duplicateBody
    $javaInvalidChannel = Invoke-NotificationPreferencesStatus 'Put' "$JavaUrl/api/v1/notification-preferences" $javaUser $invalidChannelBody
    $pythonInvalidChannel = Invoke-NotificationPreferencesStatus 'Put' "$PythonUrl/api/v1/notification-preferences" $pythonUser $invalidChannelBody
    $proxyInvalidChannel = Invoke-NotificationPreferencesStatus 'Put' "$WebUrl/api/web/notification-preferences" $proxyUser $invalidChannelBody
    $anonymousProxy = Invoke-NotificationPreferencesStatus 'Get' "$WebUrl/api/web/notification-preferences" ''
    $proxySseBoundary = Invoke-NotificationStatus 'Get' "$WebUrl/api/v1/notifications/sse" $javaUser

    $getStable = [ordered]@{
        java = ConvertTo-StableNotificationPreferencesJson -Response $javaGet
        python = ConvertTo-StableNotificationPreferencesJson -Response $pythonGet
        proxy = ConvertTo-StableNotificationPreferencesJson -Response $proxyGet
    }
    $putStable = [ordered]@{
        java = ConvertTo-StableNotificationPreferencesJson -Response $javaPut
        python = ConvertTo-StableNotificationPreferencesJson -Response $pythonPut
        proxy = ConvertTo-StableNotificationPreferencesJson -Response $proxyPut
    }

    $result = [ordered]@{
        suffix = $suffix
        checks = [ordered]@{
            getMatches = ($getStable.java -eq $getStable.python -and $getStable.python -eq $getStable.proxy)
            putMatches = ($putStable.java -eq $putStable.python -and $putStable.python -eq $putStable.proxy)
            invalidCategoryRejected = ($javaInvalidCategory -eq 400 -and $pythonInvalidCategory -eq 400 -and $proxyInvalidCategory -eq 400)
            duplicateRejected = ($javaDuplicate -eq 400 -and $pythonDuplicate -eq 400 -and $proxyDuplicate -eq 400)
            invalidChannelRejected = ($javaInvalidChannel -eq 400 -and $pythonInvalidChannel -eq 400 -and $proxyInvalidChannel -eq 400)
            anonymousRejected = ($anonymousProxy -eq 401)
            sseStillJavaOwned = ($proxySseBoundary -eq 200)
            dbUpsertsPersisted = (
                (Get-NotificationPreferenceEnabled -UserId $javaUser -Category 'PUBLISH') -eq 'f' -and
                (Get-NotificationPreferenceEnabled -UserId $pythonUser -Category 'PUBLISH') -eq 'f' -and
                (Get-NotificationPreferenceEnabled -UserId $proxyUser -Category 'PUBLISH') -eq 'f' -and
                (Get-NotificationPreferenceEnabled -UserId $proxyUser -Category 'REPORT') -eq 'f'
            )
        }
        getStable = $getStable
        putStable = $putStable
        routeBoundaries = [ordered]@{
            invalidCategory = @($javaInvalidCategory, $pythonInvalidCategory, $proxyInvalidCategory)
            duplicate = @($javaDuplicate, $pythonDuplicate, $proxyDuplicate)
            invalidChannel = @($javaInvalidChannel, $pythonInvalidChannel, $proxyInvalidChannel)
            anonymousProxy = $anonymousProxy
            proxySseBoundary = $proxySseBoundary
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Notification preferences contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNotificationPreferencesSmokeVerification {
    try {
        Invoke-NotificationPreferencesTests
        Start-Hybrid
        Invoke-NotificationPreferencesContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-MySkillsTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_my_skills.py', 'tests/test_my_social_lists.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableMySkillsJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.items)) {
        $items += [ordered]@{
            slug = $item.slug
            displayName = $item.displayName
            visibility = $item.visibility
            status = $item.status
            namespace = $item.namespace
            canSubmitPromotion = [bool]$item.canSubmitPromotion
            headlineVersion = $item.headlineVersion
            publishedVersion = $item.publishedVersion
            ownerPreviewVersion = $item.ownerPreviewVersion
            resolutionMode = $item.resolutionMode
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        total = $Response.data.total
        page = $Response.data.page
        size = $Response.data.size
        items = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-MySkillsContractComparison {
    param([string]$ResultFileName = 'my-skills-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $userId = "codex-my-skills-user-$suffix"
    $namespace = "codex-my-skills-$suffix"
    $adminNamespace = "codex-my-skills-admin-$suffix"
    $adminUserId = 'local-admin'
    $visibleSlug = "visible-agent-$suffix"
    $pendingSlug = "pending-work-$suffix"
    $archivedSlug = "archived-agent-$suffix"
    $hiddenSlug = "hidden-agent-$suffix"
    $adminHiddenSlug = "admin-hidden-agent-$suffix"

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    admin_ns_id BIGINT;
    visible_id BIGINT;
    pending_id BIGINT;
    archived_id BIGINT;
    hidden_id BIGINT;
    admin_hidden_id BIGINT;
    version_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES ('$userId', 'Codex My Skills User', 'my-skills-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$namespace', 'Codex My Skills', 'TEAM', 'ACTIVE', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace (slug, display_name, type, status, created_by)
    VALUES ('$adminNamespace', 'Codex My Skills Admin', 'TEAM', 'ACTIVE', '$adminUserId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO admin_ns_id;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status, hidden,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by, updated_at
    )
    VALUES
        (ns_id, '$visibleSlug', 'Visible Agent Skill', 'visible agent summary', '$userId', 'PUBLIC', 'ACTIVE', FALSE, 11, 3, 0, 4.50, 2, '$userId', '$userId', '2026-06-10T12:00:00Z'::timestamptz),
        (ns_id, '$pendingSlug', 'Pending Work Skill', 'pending summary', '$userId', 'PUBLIC', 'ACTIVE', FALSE, 5, 1, 0, 0, 0, '$userId', '$userId', '2026-06-10T11:00:00Z'::timestamptz),
        (ns_id, '$archivedSlug', 'Archived Agent Skill', 'archived agent summary', '$userId', 'PUBLIC', 'ARCHIVED', FALSE, 2, 0, 0, 0, 0, '$userId', '$userId', '2026-06-10T10:00:00Z'::timestamptz),
        (ns_id, '$hiddenSlug', 'Hidden Agent Skill', 'hidden agent summary', '$userId', 'PUBLIC', 'ACTIVE', TRUE, 1, 0, 0, 0, 0, '$userId', '$userId', '2026-06-10T09:00:00Z'::timestamptz),
        (admin_ns_id, '$adminHiddenSlug', 'Admin Hidden Agent Skill', 'admin hidden summary', '$adminUserId', 'PUBLIC', 'ACTIVE', TRUE, 1, 0, 0, 0, 0, '$adminUserId', '$adminUserId', '2026-06-10T08:00:00Z'::timestamptz);

    SELECT id INTO visible_id FROM skill WHERE namespace_id = ns_id AND slug = '$visibleSlug';
    SELECT id INTO pending_id FROM skill WHERE namespace_id = ns_id AND slug = '$pendingSlug';
    SELECT id INTO archived_id FROM skill WHERE namespace_id = ns_id AND slug = '$archivedSlug';
    SELECT id INTO hidden_id FROM skill WHERE namespace_id = ns_id AND slug = '$hiddenSlug';
    SELECT id INTO admin_hidden_id FROM skill WHERE namespace_id = admin_ns_id AND slug = '$adminHiddenSlug';

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        visible_id, '1.0.0', 'PUBLISHED', 'published',
        jsonb_build_object('name', 'Visible Agent Skill', 'version', '1.0.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 32, '2026-06-10T12:05:00Z'::timestamptz, '$userId',
        '2026-06-10T12:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
    SET status = 'PUBLISHED', published_at = EXCLUDED.published_at, created_at = EXCLUDED.created_at
    RETURNING id INTO version_id;
    UPDATE skill SET latest_version_id = version_id WHERE id = visible_id;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        visible_id, '1.1.0', 'PENDING_REVIEW', 'pending',
        jsonb_build_object('name', 'Visible Agent Skill', 'version', '1.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 32, NULL, '$userId',
        '2026-06-10T12:10:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
    SET status = 'PENDING_REVIEW', created_at = EXCLUDED.created_at;

    INSERT INTO skill_version (
        skill_id, version, status, changelog, parsed_metadata_json, manifest_json,
        file_count, total_size, published_at, created_by, created_at, bundle_ready,
        download_ready, requested_visibility
    )
    VALUES (
        pending_id, '0.1.0', 'PENDING_REVIEW', 'pending only',
        jsonb_build_object('name', 'Pending Work Skill', 'version', '0.1.0'),
        jsonb_build_array(jsonb_build_object('path', 'SKILL.md')),
        1, 32, NULL, '$userId',
        '2026-06-10T11:00:00Z'::timestamptz, TRUE, TRUE, 'PUBLIC'
    )
    ON CONFLICT (skill_id, version) DO UPDATE
    SET status = 'PENDING_REVIEW', created_at = EXCLUDED.created_at;

    UPDATE skill SET latest_version_id = NULL WHERE id IN (pending_id, archived_id, hidden_id, admin_hidden_id);
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $headers = @{ 'X-Mock-User-Id' = $userId }
    $adminHeaders = @{ 'X-Mock-User-Id' = $adminUserId }
    $defaultPath = '/api/v1/me/skills?page=0&size=10'
    $filterPath = "/api/v1/me/skills?page=0&size=10&q=agent&namespace=$namespace"
    $hiddenPath = "/api/v1/me/skills?page=0&size=10&filter=HIDDEN&namespace=$adminNamespace"

    $javaDefault = Invoke-RestMethod "$JavaUrl$defaultPath" -Headers $headers
    $pythonDefault = Invoke-RestMethod "$PythonUrl$defaultPath" -Headers $headers
    $proxyDefault = Invoke-RestMethod "$WebUrl/api/web/me/skills?page=0&size=10" -Headers $headers
    $javaFilter = Invoke-RestMethod "$JavaUrl$filterPath" -Headers $headers
    $pythonFilter = Invoke-RestMethod "$PythonUrl$filterPath" -Headers $headers
    $proxyFilter = Invoke-RestMethod "$WebUrl/api/web/me/skills?page=0&size=10&q=agent&namespace=$namespace" -Headers $headers
    $javaHidden = Invoke-RestMethod "$JavaUrl$hiddenPath" -Headers $adminHeaders
    $pythonHidden = Invoke-RestMethod "$PythonUrl$hiddenPath" -Headers $adminHeaders
    $proxyHidden = Invoke-RestMethod "$WebUrl/api/web/me/skills?page=0&size=10&filter=HIDDEN&namespace=$adminNamespace" -Headers $adminHeaders

    $anonymousProxy = Invoke-NotificationStatus 'Get' "$WebUrl/api/web/me/skills" $null
    $postProxy = Invoke-NotificationStatus 'Post' "$WebUrl/api/v1/me/skills" $userId

    $defaultStable = [ordered]@{
        java = ConvertTo-StableMySkillsJson -Response $javaDefault
        python = ConvertTo-StableMySkillsJson -Response $pythonDefault
        proxy = ConvertTo-StableMySkillsJson -Response $proxyDefault
    }
    $filterStable = [ordered]@{
        java = ConvertTo-StableMySkillsJson -Response $javaFilter
        python = ConvertTo-StableMySkillsJson -Response $pythonFilter
        proxy = ConvertTo-StableMySkillsJson -Response $proxyFilter
    }
    $hiddenStable = [ordered]@{
        java = ConvertTo-StableMySkillsJson -Response $javaHidden
        python = ConvertTo-StableMySkillsJson -Response $pythonHidden
        proxy = ConvertTo-StableMySkillsJson -Response $proxyHidden
    }

    $result = [ordered]@{
        namespace = $namespace
        checks = [ordered]@{
            defaultMatches = ($defaultStable.java -eq $defaultStable.python -and $defaultStable.python -eq $defaultStable.proxy)
            filterMatches = ($filterStable.java -eq $filterStable.python -and $filterStable.python -eq $filterStable.proxy)
            hiddenMatches = ($hiddenStable.java -eq $hiddenStable.python -and $hiddenStable.python -eq $hiddenStable.proxy)
            defaultIncludesArchivedHidden = ($javaDefault.data.total -eq 4)
            filterExcludesArchivedHidden = ($javaFilter.data.total -eq 1 -and $javaFilter.data.items[0].slug -eq $visibleSlug)
            hiddenRequiresAdmin = ($javaHidden.data.total -eq 1 -and $javaHidden.data.items[0].slug -eq $adminHiddenSlug)
            anonymousRejected = ($anonymousProxy -eq 401)
            postStillJavaOwned = ($postProxy -ne 404)
        }
        defaultStable = $defaultStable
        filterStable = $filterStable
        hiddenStable = $hiddenStable
        routeBoundaries = [ordered]@{
            anonymousProxy = $anonymousProxy
            postProxy = $postProxy
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "My skills contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridMySkillsSmokeVerification {
    try {
        Invoke-MySkillsTests
        Start-Hybrid
        Invoke-MySkillsContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NamespaceReadTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_namespace_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableNamespacePageJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.items)) {
        $items += [ordered]@{
            slug = $item.slug
            displayName = $item.displayName
            status = $item.status
            type = $item.type
            description = $item.description
            avatarUrl = $item.avatarUrl
            createdBy = $item.createdBy
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        total = $Response.data.total
        page = $Response.data.page
        size = $Response.data.size
        items = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableMyNamespaceJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data)) {
        $items += [ordered]@{
            slug = $item.slug
            displayName = $item.displayName
            status = $item.status
            type = $item.type
            currentUserRole = $item.currentUserRole
            immutable = [bool]$item.immutable
            canFreeze = [bool]$item.canFreeze
            canUnfreeze = [bool]$item.canUnfreeze
            canArchive = [bool]$item.canArchive
            canRestore = [bool]$item.canRestore
            canDelete = [bool]$item.canDelete
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableNamespaceDetailJson {
    param([object]$Response)

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            slug = $Response.data.slug
            displayName = $Response.data.displayName
            status = $Response.data.status
            type = $Response.data.type
            description = $Response.data.description
            avatarUrl = $Response.data.avatarUrl
            createdBy = $Response.data.createdBy
        }
    } | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-NamespaceReadContractComparison {
    param([string]$ResultFileName = 'namespace-read-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $userId = "codex-namespace-user-$suffix"
    $otherUserId = "codex-namespace-other-$suffix"
    $alpha = "codex-ns-alpha-$suffix"
    $beta = "codex-ns-beta-$suffix"
    $frozen = "codex-ns-frozen-$suffix"
    $archived = "codex-ns-archived-$suffix"
    $skillSlug = "codex-ns-dependency-$suffix"

    $sql = @"
DO `$`$
DECLARE
    alpha_id BIGINT;
    beta_id BIGINT;
    frozen_id BIGINT;
    archived_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$userId', 'Codex Namespace User', 'namespace-$suffix@example.test', '', 'ACTIVE'),
        ('$otherUserId', 'Codex Namespace Other', 'namespace-other-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$alpha', 'Codex Alpha Namespace', 'TEAM', 'ACTIVE', 'alpha read fixture', 'https://example.test/alpha.png', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO alpha_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$beta', 'Codex Beta Namespace', 'TEAM', 'ACTIVE', 'beta read fixture', 'https://example.test/beta.png', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO beta_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$frozen', 'Codex Frozen Namespace', 'TEAM', 'FROZEN', 'frozen read fixture', '', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO frozen_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$archived', 'Codex Archived Namespace', 'TEAM', 'ARCHIVED', 'archived read fixture', '', '$userId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO archived_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (alpha_id, '$userId', 'OWNER'),
        (beta_id, '$userId', 'OWNER'),
        (frozen_id, '$userId', 'ADMIN'),
        (archived_id, '$userId', 'OWNER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;

    INSERT INTO skill (
        namespace_id, slug, display_name, summary, owner_id, visibility, status, hidden,
        download_count, star_count, subscription_count, rating_avg, rating_count,
        created_by, updated_by
    )
    VALUES (
        beta_id, '$skillSlug', 'Namespace Dependency Skill', 'dependency', '$userId',
        'PUBLIC', 'ACTIVE', FALSE, 0, 0, 0, 0, 0, '$userId', '$userId'
    )
    ON CONFLICT (namespace_id, slug, owner_id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        hidden = EXCLUDED.hidden,
        updated_at = CURRENT_TIMESTAMP;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $headers = @{ 'X-Mock-User-Id' = $userId }
    $otherHeaders = @{ 'X-Mock-User-Id' = $otherUserId }
    $listPath = '/api/v1/namespaces?page=0&size=10'
    $myPath = '/api/v1/me/namespaces'
    $detailPath = "/api/v1/namespaces/$alpha"
    $archivedDetailPath = "/api/v1/namespaces/$archived"

    $javaList = Invoke-RestMethod "$JavaUrl$listPath" -Headers $headers
    $pythonList = Invoke-RestMethod "$PythonUrl$listPath" -Headers $headers
    $proxyList = Invoke-RestMethod "$WebUrl/api/web/namespaces?page=0&size=10" -Headers $headers
    $javaMy = Invoke-RestMethod "$JavaUrl$myPath" -Headers $headers
    $pythonMy = Invoke-RestMethod "$PythonUrl$myPath" -Headers $headers
    $proxyMy = Invoke-RestMethod "$WebUrl/api/web/me/namespaces" -Headers $headers
    $javaDetail = Invoke-RestMethod "$JavaUrl$detailPath" -Headers $headers
    $pythonDetail = Invoke-RestMethod "$PythonUrl$detailPath" -Headers $headers
    $proxyDetail = Invoke-RestMethod "$WebUrl/api/web/namespaces/$alpha" -Headers $headers

    $anonymousProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces"
    $activeNonMemberJava = Invoke-HttpStatusWithHeaders "$JavaUrl$detailPath" -Headers $otherHeaders
    $activeNonMemberPython = Invoke-HttpStatusWithHeaders "$PythonUrl$detailPath" -Headers $otherHeaders
    $activeNonMemberProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces/$alpha" -Headers $otherHeaders
    $archivedNonMemberJava = Invoke-HttpStatusWithHeaders "$JavaUrl$archivedDetailPath" -Headers $otherHeaders
    $archivedNonMemberPython = Invoke-HttpStatusWithHeaders "$PythonUrl$archivedDetailPath" -Headers $otherHeaders
    $archivedNonMemberProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces/$archived" -Headers $otherHeaders
    $memberRouteProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/v1/namespaces/$alpha/members" -Headers $headers
    $postJava = Invoke-NotificationStatus 'Post' "$JavaUrl/api/v1/namespaces" $userId
    $postPython = Invoke-NotificationStatus 'Post' "$PythonUrl/api/v1/namespaces" $userId
    $postProxy = Invoke-NotificationStatus 'Post' "$WebUrl/api/v1/namespaces" $userId

    $listStable = [ordered]@{
        java = ConvertTo-StableNamespacePageJson -Response $javaList
        python = ConvertTo-StableNamespacePageJson -Response $pythonList
        proxy = ConvertTo-StableNamespacePageJson -Response $proxyList
    }
    $myStable = [ordered]@{
        java = ConvertTo-StableMyNamespaceJson -Response $javaMy
        python = ConvertTo-StableMyNamespaceJson -Response $pythonMy
        proxy = ConvertTo-StableMyNamespaceJson -Response $proxyMy
    }
    $detailStable = [ordered]@{
        java = ConvertTo-StableNamespaceDetailJson -Response $javaDetail
        python = ConvertTo-StableNamespaceDetailJson -Response $pythonDetail
        proxy = ConvertTo-StableNamespaceDetailJson -Response $proxyDetail
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @($listPath, $myPath, $detailPath)
        checks = [ordered]@{
            listMatches = ($listStable.java -eq $listStable.python -and $listStable.python -eq $listStable.proxy)
            myMatches = ($myStable.java -eq $myStable.python -and $myStable.python -eq $myStable.proxy)
            detailMatches = ($detailStable.java -eq $detailStable.python -and $detailStable.python -eq $detailStable.proxy)
            listOnlyActiveMemberships = ($javaList.data.total -eq 2 -and $javaList.data.items[0].slug -eq $alpha -and $javaList.data.items[1].slug -eq $beta)
            capabilityFlagsCovered = (
                ($javaMy.data | Where-Object { $_.slug -eq $alpha }).canFreeze -eq $true -and
                ($javaMy.data | Where-Object { $_.slug -eq $beta }).canDelete -eq $false -and
                ($javaMy.data | Where-Object { $_.slug -eq $frozen }).canUnfreeze -eq $true -and
                ($javaMy.data | Where-Object { $_.slug -eq $archived }).canRestore -eq $true
            )
            anonymousRejected = ($anonymousProxy -eq 401)
            activeNonMemberForbidden = ($activeNonMemberJava -eq 403 -and $activeNonMemberPython -eq 403 -and $activeNonMemberProxy -eq 403)
            archivedNonMemberNotFound = ($archivedNonMemberJava -eq 400 -and $archivedNonMemberPython -eq 400 -and $archivedNonMemberProxy -eq 400)
            memberRouteStillJavaOwned = ($memberRouteProxy -eq 200)
            postStillJavaOwned = ($postJava -eq $postProxy -and $postPython -eq 405)
        }
        listStable = $listStable
        myStable = $myStable
        detailStable = $detailStable
        routeBoundaries = [ordered]@{
            anonymousProxy = $anonymousProxy
            activeNonMember = @($activeNonMemberJava, $activeNonMemberPython, $activeNonMemberProxy)
            archivedNonMember = @($archivedNonMemberJava, $archivedNonMemberPython, $archivedNonMemberProxy)
            memberRouteProxy = $memberRouteProxy
            postJava = $postJava
            postPython = $postPython
            postProxy = $postProxy
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Namespace read contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-NamespaceMemberReadTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_namespace_member_read.py', 'tests/test_namespace_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableNamespaceMemberPageJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.items)) {
        $items += [ordered]@{
            userId = $item.userId
            displayName = $item.displayName
            email = $item.email
            role = $item.role
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        total = $Response.data.total
        page = $Response.data.page
        size = $Response.data.size
        items = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableNamespaceCandidateJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data)) {
        $items += [ordered]@{
            userId = $item.userId
            displayName = $item.displayName
            email = $item.email
            status = $item.status
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-NamespaceMemberReadContractComparison {
    param([string]$ResultFileName = 'namespace-member-read-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $ownerId = "codex-ns-member-owner-$suffix"
    $memberId = "codex-ns-member-basic-$suffix"
    $outsiderId = "codex-ns-member-outsider-$suffix"
    $candidateId = "codex-ns-candidate-$suffix"
    $existingCandidateId = "codex-ns-existing-candidate-$suffix"
    $inactiveCandidateId = "codex-ns-inactive-candidate-$suffix"
    $teamSlug = "codex-ns-members-$suffix"
    $frozenSlug = "codex-ns-members-frozen-$suffix"

    $sql = @"
DO `$`$
DECLARE
    team_id BIGINT;
    frozen_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$ownerId', 'Codex Namespace Owner', 'owner-$suffix@example.test', '', 'ACTIVE'),
        ('$memberId', 'Codex Namespace Member', 'member-$suffix@example.test', '', 'ACTIVE'),
        ('$outsiderId', 'Codex Namespace Outsider', 'outsider-$suffix@example.test', '', 'ACTIVE'),
        ('$candidateId', 'Codex Candidate Alpha', 'candidate-alpha-$suffix@example.test', '', 'ACTIVE'),
        ('$existingCandidateId', 'Codex Candidate Existing', 'candidate-existing-$suffix@example.test', '', 'ACTIVE'),
        ('$inactiveCandidateId', 'Codex Candidate Disabled', 'candidate-disabled-$suffix@example.test', '', 'DISABLED')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$teamSlug', 'Codex Namespace Members', 'TEAM', 'ACTIVE', 'member read fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$frozenSlug', 'Codex Namespace Members Frozen', 'TEAM', 'FROZEN', 'candidate readonly fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO frozen_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_id, '$ownerId', 'OWNER'),
        (team_id, '$memberId', 'MEMBER'),
        (team_id, '$existingCandidateId', 'MEMBER'),
        (frozen_id, '$ownerId', 'OWNER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    $ownerHeaders = @{ 'X-Mock-User-Id' = $ownerId }
    $memberHeaders = @{ 'X-Mock-User-Id' = $memberId }
    $outsiderHeaders = @{ 'X-Mock-User-Id' = $outsiderId }
    $membersPath = "/api/v1/namespaces/$teamSlug/members?page=0&size=10"
    $candidatesPath = "/api/v1/namespaces/$teamSlug/member-candidates?search=Candidate&size=20"
    $blankCandidatesPath = "/api/v1/namespaces/$teamSlug/member-candidates?search=%20%20%20&size=10"
    $shortCandidatesPath = "/api/v1/namespaces/$teamSlug/member-candidates?search=c&size=10"
    $globalCandidatesPath = '/api/v1/namespaces/global/member-candidates?search=Candidate&size=10'
    $frozenCandidatesPath = "/api/v1/namespaces/$frozenSlug/member-candidates?search=Candidate&size=10"

    $javaMembers = Invoke-RestMethod "$JavaUrl$membersPath" -Headers $ownerHeaders
    $pythonMembers = Invoke-RestMethod "$PythonUrl$membersPath" -Headers $ownerHeaders
    $proxyMembers = Invoke-RestMethod "$WebUrl/api/web/namespaces/$teamSlug/members?page=0&size=10" -Headers $ownerHeaders

    $javaCandidates = Invoke-RestMethod "$JavaUrl$candidatesPath" -Headers $ownerHeaders
    $pythonCandidates = Invoke-RestMethod "$PythonUrl$candidatesPath" -Headers $ownerHeaders
    $proxyCandidates = Invoke-RestMethod "$WebUrl/api/web/namespaces/$teamSlug/member-candidates?search=Candidate&size=20" -Headers $ownerHeaders

    $javaBlank = Invoke-RestMethod "$JavaUrl$blankCandidatesPath" -Headers $ownerHeaders
    $pythonBlank = Invoke-RestMethod "$PythonUrl$blankCandidatesPath" -Headers $ownerHeaders
    $proxyBlank = Invoke-RestMethod "$WebUrl$blankCandidatesPath" -Headers $ownerHeaders

    $anonymousMembers = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces/$teamSlug/members"
    $outsiderMembersJava = Invoke-HttpStatusWithHeaders "$JavaUrl$membersPath" -Headers $outsiderHeaders
    $outsiderMembersPython = Invoke-HttpStatusWithHeaders "$PythonUrl$membersPath" -Headers $outsiderHeaders
    $outsiderMembersProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces/$teamSlug/members?page=0&size=10" -Headers $outsiderHeaders
    $memberCandidatesJava = Invoke-HttpStatusWithHeaders "$JavaUrl$candidatesPath" -Headers $memberHeaders
    $memberCandidatesPython = Invoke-HttpStatusWithHeaders "$PythonUrl$candidatesPath" -Headers $memberHeaders
    $memberCandidatesProxy = Invoke-HttpStatusWithHeaders "$WebUrl/api/web/namespaces/$teamSlug/member-candidates?search=Candidate&size=20" -Headers $memberHeaders
    $shortJava = Invoke-HttpStatusWithHeaders "$JavaUrl$shortCandidatesPath" -Headers $ownerHeaders
    $shortPython = Invoke-HttpStatusWithHeaders "$PythonUrl$shortCandidatesPath" -Headers $ownerHeaders
    $shortProxy = Invoke-HttpStatusWithHeaders "$WebUrl$shortCandidatesPath" -Headers $ownerHeaders
    $globalJava = Invoke-HttpStatusWithHeaders "$JavaUrl$globalCandidatesPath" -Headers $ownerHeaders
    $globalPython = Invoke-HttpStatusWithHeaders "$PythonUrl$globalCandidatesPath" -Headers $ownerHeaders
    $globalProxy = Invoke-HttpStatusWithHeaders "$WebUrl$globalCandidatesPath" -Headers $ownerHeaders
    $frozenJava = Invoke-HttpStatusWithHeaders "$JavaUrl$frozenCandidatesPath" -Headers $ownerHeaders
    $frozenPython = Invoke-HttpStatusWithHeaders "$PythonUrl$frozenCandidatesPath" -Headers $ownerHeaders
    $frozenProxy = Invoke-HttpStatusWithHeaders "$WebUrl$frozenCandidatesPath" -Headers $ownerHeaders
    $postJava = Invoke-NotificationStatus 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/members" $ownerId
    $postPython = Invoke-NotificationStatus 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/members" $ownerId
    $postProxy = Invoke-NotificationStatus 'Post' "$WebUrl/api/v1/namespaces/$teamSlug/members" $ownerId

    $membersStable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberPageJson -Response $javaMembers
        python = ConvertTo-StableNamespaceMemberPageJson -Response $pythonMembers
        proxy = ConvertTo-StableNamespaceMemberPageJson -Response $proxyMembers
    }
    $candidatesStable = [ordered]@{
        java = ConvertTo-StableNamespaceCandidateJson -Response $javaCandidates
        python = ConvertTo-StableNamespaceCandidateJson -Response $pythonCandidates
        proxy = ConvertTo-StableNamespaceCandidateJson -Response $proxyCandidates
    }
    $blankStable = [ordered]@{
        java = ConvertTo-StableNamespaceCandidateJson -Response $javaBlank
        python = ConvertTo-StableNamespaceCandidateJson -Response $pythonBlank
        proxy = ConvertTo-StableNamespaceCandidateJson -Response $proxyBlank
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @($membersPath, $candidatesPath)
        checks = [ordered]@{
            membersMatch = ($membersStable.java -eq $membersStable.python -and $membersStable.python -eq $membersStable.proxy)
            candidatesMatch = ($candidatesStable.java -eq $candidatesStable.python -and $candidatesStable.python -eq $candidatesStable.proxy)
            blankSearchMatches = ($blankStable.java -eq $blankStable.python -and $blankStable.python -eq $blankStable.proxy)
            oneCandidateReturned = ($javaCandidates.data.Count -eq 1 -and $javaCandidates.data[0].userId -eq $candidateId)
            existingMemberExcluded = (($javaCandidates.data | Where-Object { $_.userId -eq $existingCandidateId }).Count -eq 0)
            inactiveUserExcluded = (($javaCandidates.data | Where-Object { $_.userId -eq $inactiveCandidateId }).Count -eq 0)
            anonymousRejected = ($anonymousMembers -eq 401)
            outsiderMemberForbidden = ($outsiderMembersJava -eq 403 -and $outsiderMembersPython -eq 403 -and $outsiderMembersProxy -eq 403)
            memberCandidateForbidden = ($memberCandidatesJava -eq 403 -and $memberCandidatesPython -eq 403 -and $memberCandidatesProxy -eq 403)
            shortSearchRejected = ($shortJava -eq 400 -and $shortPython -eq 400 -and $shortProxy -eq 400)
            globalImmutableRejected = ($globalJava -eq 400 -and $globalPython -eq 400 -and $globalProxy -eq 400)
            frozenReadonlyRejected = ($frozenJava -eq 400 -and $frozenPython -eq 400 -and $frozenProxy -eq 400)
            postMemberNowPythonOwned = ($postPython -eq $postProxy -and $postJava -ne $postProxy)
        }
        membersStable = $membersStable
        candidatesStable = $candidatesStable
        blankStable = $blankStable
        routeBoundaries = [ordered]@{
            anonymousMembers = $anonymousMembers
            outsiderMembers = @($outsiderMembersJava, $outsiderMembersPython, $outsiderMembersProxy)
            memberCandidates = @($memberCandidatesJava, $memberCandidatesPython, $memberCandidatesProxy)
            shortSearch = @($shortJava, $shortPython, $shortProxy)
            globalImmutable = @($globalJava, $globalPython, $globalProxy)
            frozenReadonly = @($frozenJava, $frozenPython, $frozenProxy)
            postMember = @($postJava, $postPython, $postProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Namespace member read contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNamespaceReadSmokeVerification {
    try {
        Invoke-NamespaceReadTests
        Start-Hybrid
        Invoke-NamespaceReadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridNamespaceMemberReadSmokeVerification {
    try {
        Invoke-NamespaceMemberReadTests
        Start-Hybrid
        Invoke-NamespaceMemberReadContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NamespaceMemberMutationTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_namespace_member_mutation.py', 'tests/test_namespace_member_read.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-NamespaceMemberJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $headers = @{ 'X-Mock-User-Id' = $UserId }
    if ($null -eq $Body) {
        return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers
    }
    return Invoke-RestMethod -Method $Method -Uri $Url -Headers $headers -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 20)
}

function Invoke-NamespaceMemberStatusJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $headers = if ($UserId) { @{ 'X-Mock-User-Id' = $UserId } } else { @{} }
    try {
        if ($null -eq $Body) {
            Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers -UseBasicParsing -TimeoutSec 15 | Out-Null
        } else {
            Invoke-WebRequest -Method $Method -Uri $Url -Headers $headers -ContentType 'application/json' -Body ($Body | ConvertTo-Json -Depth 20) -UseBasicParsing -TimeoutSec 15 | Out-Null
        }
        return 200
    } catch {
        if ($_.Exception.Response) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function ConvertTo-StableNamespaceMemberMutationJson {
    param([object]$Response)

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            userId = $Response.data.userId
            displayName = $Response.data.displayName
            email = $Response.data.email
            role = $Response.data.role
        }
    } | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableNamespaceMemberMessageJson {
    param([object]$Response)

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        message = $Response.data.message
    } | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableNamespaceMemberBatchJson {
    param([object]$Response)

    $items = @()
    foreach ($item in @($Response.data.results)) {
        $items += [ordered]@{
            userId = $item.userId
            role = $item.role
            success = [bool]$item.success
            error = $item.error
        }
    }

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        totalCount = $Response.data.totalCount
        successCount = $Response.data.successCount
        failureCount = $Response.data.failureCount
        results = $items
    } | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-NamespaceMemberMutationContractComparison {
    param([string]$ResultFileName = 'namespace-member-mutation-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $ownerId = "codex-ns-mut-owner-$suffix"
    $adminId = "codex-ns-mut-admin-$suffix"
    $memberId = "codex-ns-mut-member-$suffix"
    $targetId = "codex-ns-mut-target-$suffix"
    $batchNewId = "codex-ns-mut-batch-new-$suffix"
    $batchExistingId = "codex-ns-mut-batch-existing-$suffix"
    $teamSlug = "codex-ns-mut-$suffix"
    $frozenSlug = "codex-ns-mut-frozen-$suffix"

    $sql = @"
DO `$`$
DECLARE
    team_id BIGINT;
    frozen_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$ownerId', 'Codex Mutation Owner', 'mut-owner-$suffix@example.test', '', 'ACTIVE'),
        ('$adminId', 'Codex Mutation Admin', 'mut-admin-$suffix@example.test', '', 'ACTIVE'),
        ('$memberId', 'Codex Mutation Member', 'mut-member-$suffix@example.test', '', 'ACTIVE'),
        ('$targetId', 'Codex Mutation Target', 'mut-target-$suffix@example.test', '', 'ACTIVE'),
        ('$batchNewId', 'Codex Batch New', 'mut-batch-new-$suffix@example.test', '', 'ACTIVE'),
        ('$batchExistingId', 'Codex Batch Existing', 'mut-batch-existing-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$teamSlug', 'Codex Namespace Mutation', 'TEAM', 'ACTIVE', 'member mutation fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$frozenSlug', 'Codex Namespace Mutation Frozen', 'TEAM', 'FROZEN', 'member mutation readonly fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO frozen_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_id, '$ownerId', 'OWNER'),
        (team_id, '$adminId', 'ADMIN'),
        (team_id, '$memberId', 'MEMBER'),
        (team_id, '$batchExistingId', 'MEMBER'),
        (frozen_id, '$ownerId', 'OWNER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Reset-MemberFixture {
        param(
            [string]$UserId,
            [string]$Role = $null
        )
        $resetSql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    SELECT id INTO ns_id FROM namespace WHERE slug = '$teamSlug';
    DELETE FROM namespace_member WHERE namespace_id = ns_id AND user_id = '$UserId';
    IF '$Role' <> '' THEN
        INSERT INTO namespace_member (namespace_id, user_id, role)
        VALUES (ns_id, '$UserId', '$Role');
    END IF;
END `$`$;
"@
        Invoke-PostgresSql -Sql $resetSql
    }

    $addBody = @{ userId = $targetId; role = 'ADMIN' }
    Reset-MemberFixture -UserId $targetId
    $javaAdd = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/members" $ownerId $addBody
    Reset-MemberFixture -UserId $targetId
    $pythonAdd = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/members" $ownerId $addBody
    Reset-MemberFixture -UserId $targetId
    $proxyAdd = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/members" $ownerId $addBody

    $updateBody = @{ role = 'ADMIN' }
    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $javaUpdate = Invoke-NamespaceMemberJson 'Put' "$JavaUrl/api/v1/namespaces/$teamSlug/members/$targetId/role" $ownerId $updateBody
    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $pythonUpdate = Invoke-NamespaceMemberJson 'Put' "$PythonUrl/api/v1/namespaces/$teamSlug/members/$targetId/role" $ownerId $updateBody
    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $proxyUpdate = Invoke-NamespaceMemberJson 'Put' "$WebUrl/api/web/namespaces/$teamSlug/members/$targetId/role" $ownerId $updateBody

    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $javaRemove = Invoke-NamespaceMemberJson 'Delete' "$JavaUrl/api/v1/namespaces/$teamSlug/members/$targetId" $ownerId
    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $pythonRemove = Invoke-NamespaceMemberJson 'Delete' "$PythonUrl/api/v1/namespaces/$teamSlug/members/$targetId" $ownerId
    Reset-MemberFixture -UserId $targetId -Role 'MEMBER'
    $proxyRemove = Invoke-NamespaceMemberJson 'Delete' "$WebUrl/api/web/namespaces/$teamSlug/members/$targetId" $ownerId

    $batchBody = @{ members = @(@{ userId = $batchNewId; role = 'MEMBER' }, @{ userId = $batchExistingId; role = 'ADMIN' }, @{ userId = "codex-ns-mut-owner-direct-$suffix"; role = 'OWNER' }) }
    Reset-MemberFixture -UserId $batchNewId
    $javaBatch = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/members/batch" $ownerId $batchBody
    Reset-MemberFixture -UserId $batchNewId
    $pythonBatch = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/members/batch" $ownerId $batchBody
    Reset-MemberFixture -UserId $batchNewId
    $proxyBatch = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/members/batch" $ownerId $batchBody

    $ownerDirectBody = @{ userId = "codex-ns-mut-owner-direct-$suffix"; role = 'OWNER' }
    $ownerDirectJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/members" $ownerId $ownerDirectBody
    $ownerDirectPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/members" $ownerId $ownerDirectBody
    $ownerDirectProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/members" $ownerId $ownerDirectBody
    $removeOwnerJava = Invoke-NamespaceMemberStatusJson 'Delete' "$JavaUrl/api/v1/namespaces/$teamSlug/members/$ownerId" $ownerId
    $removeOwnerPython = Invoke-NamespaceMemberStatusJson 'Delete' "$PythonUrl/api/v1/namespaces/$teamSlug/members/$ownerId" $ownerId
    $removeOwnerProxy = Invoke-NamespaceMemberStatusJson 'Delete' "$WebUrl/api/web/namespaces/$teamSlug/members/$ownerId" $ownerId
    $memberOperatorJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/members" $memberId @{ userId = "codex-ns-mut-forbidden-$suffix"; role = 'MEMBER' }
    $memberOperatorPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/members" $memberId @{ userId = "codex-ns-mut-forbidden-$suffix"; role = 'MEMBER' }
    $memberOperatorProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/members" $memberId @{ userId = "codex-ns-mut-forbidden-$suffix"; role = 'MEMBER' }
    $frozenJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$frozenSlug/members" $ownerId @{ userId = $targetId; role = 'MEMBER' }
    $frozenPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$frozenSlug/members" $ownerId @{ userId = $targetId; role = 'MEMBER' }
    $frozenProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$frozenSlug/members" $ownerId @{ userId = $targetId; role = 'MEMBER' }
    $addStable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberMutationJson -Response $javaAdd
        python = ConvertTo-StableNamespaceMemberMutationJson -Response $pythonAdd
        proxy = ConvertTo-StableNamespaceMemberMutationJson -Response $proxyAdd
    }
    $updateStable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberMutationJson -Response $javaUpdate
        python = ConvertTo-StableNamespaceMemberMutationJson -Response $pythonUpdate
        proxy = ConvertTo-StableNamespaceMemberMutationJson -Response $proxyUpdate
    }
    $removeStable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberMessageJson -Response $javaRemove
        python = ConvertTo-StableNamespaceMemberMessageJson -Response $pythonRemove
        proxy = ConvertTo-StableNamespaceMemberMessageJson -Response $proxyRemove
    }
    $batchStable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberBatchJson -Response $javaBatch
        python = ConvertTo-StableNamespaceMemberBatchJson -Response $pythonBatch
        proxy = ConvertTo-StableNamespaceMemberBatchJson -Response $proxyBatch
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            "/api/v1/namespaces/$teamSlug/members",
            "/api/v1/namespaces/$teamSlug/members/$targetId/role",
            "/api/v1/namespaces/$teamSlug/members/$targetId",
            "/api/v1/namespaces/$teamSlug/members/batch"
        )
        checks = [ordered]@{
            addMatches = ($addStable.java -eq $addStable.python -and $addStable.python -eq $addStable.proxy)
            updateMatches = ($updateStable.java -eq $updateStable.python -and $updateStable.python -eq $updateStable.proxy)
            removeMatches = ($removeStable.java -eq $removeStable.python -and $removeStable.python -eq $removeStable.proxy)
            batchMatches = ($batchStable.java -eq $batchStable.python -and $batchStable.python -eq $batchStable.proxy)
            batchPartialSuccess = ($javaBatch.data.successCount -eq 1 -and $javaBatch.data.failureCount -eq 2)
            ownerDirectRejected = ($ownerDirectJava -eq 400 -and $ownerDirectPython -eq 400 -and $ownerDirectProxy -eq 400)
            removeOwnerRejected = ($removeOwnerJava -eq 400 -and $removeOwnerPython -eq 400 -and $removeOwnerProxy -eq 400)
            memberOperatorForbidden = ($memberOperatorJava -eq 403 -and $memberOperatorPython -eq 403 -and $memberOperatorProxy -eq 403)
            frozenReadonlyRejected = ($frozenJava -eq 400 -and $frozenPython -eq 400 -and $frozenProxy -eq 400)
        }
        addStable = $addStable
        updateStable = $updateStable
        removeStable = $removeStable
        batchStable = $batchStable
        routeBoundaries = [ordered]@{
            ownerDirect = @($ownerDirectJava, $ownerDirectPython, $ownerDirectProxy)
            removeOwner = @($removeOwnerJava, $removeOwnerPython, $removeOwnerProxy)
            memberOperator = @($memberOperatorJava, $memberOperatorPython, $memberOperatorProxy)
            frozenReadonly = @($frozenJava, $frozenPython, $frozenProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Namespace member mutation contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNamespaceMemberMutationSmokeVerification {
    try {
        Invoke-NamespaceMemberMutationTests
        Start-Hybrid
        Invoke-NamespaceMemberMutationContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NamespaceTransferOwnershipTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_namespace_member_mutation.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function Invoke-NamespaceTransferOwnershipContractComparison {
    param([string]$ResultFileName = 'namespace-transfer-ownership-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $ownerId = "codex-ns-xfer-owner-$suffix"
    $adminId = "codex-ns-xfer-admin-$suffix"
    $memberId = "codex-ns-xfer-member-$suffix"
    $missingMemberId = "codex-ns-xfer-current-missing-$suffix"
    $teamSlug = "codex-ns-xfer-$suffix"
    $frozenSlug = "codex-ns-xfer-frozen-$suffix"

    $sql = @"
DO `$`$
DECLARE
    team_id BIGINT;
    frozen_id BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$ownerId', 'Codex Transfer Owner', 'xfer-owner-$suffix@example.test', '', 'ACTIVE'),
        ('$adminId', 'Codex Transfer Admin', 'xfer-admin-$suffix@example.test', '', 'ACTIVE'),
        ('$memberId', 'Codex Transfer Member', 'xfer-member-$suffix@example.test', '', 'ACTIVE'),
        ('$missingMemberId', 'Codex Transfer Missing Member', 'xfer-current-missing-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$teamSlug', 'Codex Transfer Namespace', 'TEAM', 'ACTIVE', 'transfer ownership fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO team_id;

    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$frozenSlug', 'Codex Transfer Frozen', 'TEAM', 'FROZEN', 'transfer readonly fixture', '', '$ownerId')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO frozen_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (team_id, '$ownerId', 'OWNER'),
        (team_id, '$adminId', 'ADMIN'),
        (team_id, '$memberId', 'MEMBER'),
        (frozen_id, '$ownerId', 'OWNER'),
        (frozen_id, '$adminId', 'ADMIN')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Reset-TransferFixture {
        $resetSql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    SELECT id INTO ns_id FROM namespace WHERE slug = '$teamSlug';
    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES
        (ns_id, '$ownerId', 'OWNER'),
        (ns_id, '$adminId', 'ADMIN'),
        (ns_id, '$memberId', 'MEMBER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE
    SET role = EXCLUDED.role;
END `$`$;
"@
        Invoke-PostgresSql -Sql $resetSql
    }

    function Read-TransferRoleState {
        $roleSql = @"
SELECT string_agg(user_id || ':' || role, ',' ORDER BY user_id) AS roles
FROM namespace_member
WHERE namespace_id = (SELECT id FROM namespace WHERE slug = '$teamSlug')
  AND user_id IN ('$ownerId', '$adminId', '$memberId');
"@
        return Invoke-PostgresScalar -Sql $roleSql
    }

    $body = @{ newOwnerId = $adminId }
    Reset-TransferFixture
    $javaTransfer = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $ownerId $body
    $javaRoles = Read-TransferRoleState
    Reset-TransferFixture
    $pythonTransfer = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $ownerId $body
    $pythonRoles = Read-TransferRoleState
    Reset-TransferFixture
    $proxyTransfer = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/transfer-ownership" $ownerId $body
    $proxyRoles = Read-TransferRoleState

    Reset-TransferFixture
    $currentMissingJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $missingMemberId $body
    $currentMissingPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $missingMemberId $body
    $currentMissingProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/transfer-ownership" $missingMemberId $body
    $currentInvalidJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $memberId $body
    $currentInvalidPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $memberId $body
    $currentInvalidProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/transfer-ownership" $memberId $body
    $newMissingBody = @{ newOwnerId = "missing-new-owner-$suffix" }
    $newMissingJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $ownerId $newMissingBody
    $newMissingPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$teamSlug/transfer-ownership" $ownerId $newMissingBody
    $newMissingProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$teamSlug/transfer-ownership" $ownerId $newMissingBody
    $frozenJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$frozenSlug/transfer-ownership" $ownerId $body
    $frozenPython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$frozenSlug/transfer-ownership" $ownerId $body
    $frozenProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$frozenSlug/transfer-ownership" $ownerId $body

    $stable = [ordered]@{
        java = ConvertTo-StableNamespaceMemberMessageJson -Response $javaTransfer
        python = ConvertTo-StableNamespaceMemberMessageJson -Response $pythonTransfer
        proxy = ConvertTo-StableNamespaceMemberMessageJson -Response $proxyTransfer
    }
    $expectedRoles = "$adminId`:OWNER,$memberId`:MEMBER,$ownerId`:ADMIN"
    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            "/api/v1/namespaces/$teamSlug/transfer-ownership",
            "/api/web/namespaces/$teamSlug/transfer-ownership"
        )
        checks = [ordered]@{
            successEnvelopeMatches = ($stable.java -eq $stable.python -and $stable.python -eq $stable.proxy)
            roleStateMatches = ($javaRoles -eq $expectedRoles -and $pythonRoles -eq $expectedRoles -and $proxyRoles -eq $expectedRoles)
            currentMissingRejected = ($currentMissingJava -eq 400 -and $currentMissingPython -eq 400 -and $currentMissingProxy -eq 400)
            currentInvalidRejected = ($currentInvalidJava -eq 400 -and $currentInvalidPython -eq 400 -and $currentInvalidProxy -eq 400)
            newMissingRejected = ($newMissingJava -eq 400 -and $newMissingPython -eq 400 -and $newMissingProxy -eq 400)
            frozenReadonlyRejected = ($frozenJava -eq 400 -and $frozenPython -eq 400 -and $frozenProxy -eq 400)
        }
        stable = $stable
        roleStates = [ordered]@{
            expected = $expectedRoles
            java = $javaRoles
            python = $pythonRoles
            proxy = $proxyRoles
        }
        statusBoundaries = [ordered]@{
            currentMissing = @($currentMissingJava, $currentMissingPython, $currentMissingProxy)
            currentInvalid = @($currentInvalidJava, $currentInvalidPython, $currentInvalidProxy)
            newMissing = @($newMissingJava, $newMissingPython, $newMissingProxy)
            frozenReadonly = @($frozenJava, $frozenPython, $frozenProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Namespace transfer ownership contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNamespaceTransferOwnershipSmokeVerification {
    try {
        Invoke-NamespaceTransferOwnershipTests
        Start-Hybrid
        Invoke-NamespaceTransferOwnershipContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-NamespaceProfileLifecycleTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_namespace_profile_lifecycle.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableNamespaceProfileJson {
    param([object]$Response)

    return ([ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            slug = $Response.data.slug
            displayName = $Response.data.displayName
            status = $Response.data.status
            description = $Response.data.description
            type = $Response.data.type
        }
    } | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-NamespaceProfileLifecycleContractComparison {
    param([string]$ResultFileName = 'namespace-profile-lifecycle-contract-result.json')

    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $adminId = "codex-ns-life-admin-$suffix"
    $ownerId = "codex-ns-life-owner-$suffix"
    $memberId = "codex-ns-life-member-$suffix"

    $sql = @"
DO `$`$
DECLARE
    skill_admin_role BIGINT;
BEGIN
    INSERT INTO user_account (id, display_name, email, avatar_url, status)
    VALUES
        ('$adminId', 'Codex Namespace Admin', 'ns-life-admin-$suffix@example.test', '', 'ACTIVE'),
        ('$ownerId', 'Codex Namespace Owner', 'ns-life-owner-$suffix@example.test', '', 'ACTIVE'),
        ('$memberId', 'Codex Namespace Member', 'ns-life-member-$suffix@example.test', '', 'ACTIVE')
    ON CONFLICT (id) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    SELECT id INTO skill_admin_role FROM role WHERE code = 'SKILL_ADMIN';
    IF skill_admin_role IS NOT NULL THEN
        INSERT INTO user_role_binding (user_id, role_id)
        VALUES ('$adminId', skill_admin_role)
        ON CONFLICT DO NOTHING;
    END IF;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql

    function Ensure-LifeNamespace {
        param(
            [string]$Slug,
            [string]$Status = 'ACTIVE',
            [string]$Owner = $ownerId,
            [bool]$WithMember = $true
        )
        $setupSql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
BEGIN
    INSERT INTO namespace (slug, display_name, type, status, description, avatar_url, created_by)
    VALUES ('$Slug', 'Codex Namespace Lifecycle', 'TEAM', '$Status', 'lifecycle fixture', '', '$Owner')
    ON CONFLICT (slug) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        type = EXCLUDED.type,
        status = EXCLUDED.status,
        description = EXCLUDED.description,
        avatar_url = EXCLUDED.avatar_url,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role)
    VALUES (ns_id, '$Owner', 'OWNER')
    ON CONFLICT (namespace_id, user_id) DO UPDATE SET role = EXCLUDED.role;

    IF '$WithMember' = 'True' THEN
        INSERT INTO namespace_member (namespace_id, user_id, role)
        VALUES (ns_id, '$memberId', 'MEMBER')
        ON CONFLICT (namespace_id, user_id) DO UPDATE SET role = EXCLUDED.role;
    END IF;
END `$`$;
"@
        Invoke-PostgresSql -Sql $setupSql
    }

    function Read-LifeNamespaceStatus {
        param([string]$Slug)
        return Invoke-PostgresScalar -Sql "SELECT status FROM namespace WHERE slug = '$Slug';"
    }

    function Read-LifeNamespaceExists {
        param([string]$Slug)
        return Invoke-PostgresScalar -Sql "SELECT CASE WHEN EXISTS (SELECT 1 FROM namespace WHERE slug = '$Slug') THEN 'true' ELSE 'false' END;"
    }

    function Read-LifeAudit {
        param(
            [string]$Slug,
            [string]$Action
        )
        return Invoke-PostgresScalar -Sql "SELECT action || '|' || target_type || '|' || actor_user_id || '|' || COALESCE(detail_json::text, '') FROM audit_log WHERE target_type = 'NAMESPACE' AND target_id = (SELECT id FROM namespace WHERE slug = '$Slug') AND action = '$Action' ORDER BY created_at DESC LIMIT 1;"
    }

    $createJavaSlug = "codex-ns-life-create-java-$suffix"
    $createPythonSlug = "codex-ns-life-create-python-$suffix"
    $createProxySlug = "codex-ns-life-create-proxy-$suffix"
    $javaCreate = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces" $adminId @{ slug = $createJavaSlug; displayName = 'Codex Created'; description = 'created' }
    $pythonCreate = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces" $adminId @{ slug = $createPythonSlug; displayName = 'Codex Created'; description = 'created' }
    $proxyCreate = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces" $adminId @{ slug = $createProxySlug; displayName = 'Codex Created'; description = 'created' }
    $createMemberJava = Invoke-PostgresScalar -Sql "SELECT role FROM namespace_member WHERE namespace_id = (SELECT id FROM namespace WHERE slug = '$createJavaSlug') AND user_id = '$adminId';"
    $createMemberPython = Invoke-PostgresScalar -Sql "SELECT role FROM namespace_member WHERE namespace_id = (SELECT id FROM namespace WHERE slug = '$createPythonSlug') AND user_id = '$adminId';"
    $createMemberProxy = Invoke-PostgresScalar -Sql "SELECT role FROM namespace_member WHERE namespace_id = (SELECT id FROM namespace WHERE slug = '$createProxySlug') AND user_id = '$adminId';"

    $updateJavaSlug = "codex-ns-life-update-java-$suffix"
    $updatePythonSlug = "codex-ns-life-update-python-$suffix"
    $updateProxySlug = "codex-ns-life-update-proxy-$suffix"
    Ensure-LifeNamespace -Slug $updateJavaSlug
    Ensure-LifeNamespace -Slug $updatePythonSlug
    Ensure-LifeNamespace -Slug $updateProxySlug
    $javaUpdate = Invoke-NamespaceMemberJson 'Put' "$JavaUrl/api/v1/namespaces/$updateJavaSlug" $ownerId @{ displayName = 'Updated Name'; description = 'updated' }
    $pythonUpdate = Invoke-NamespaceMemberJson 'Put' "$PythonUrl/api/v1/namespaces/$updatePythonSlug" $ownerId @{ displayName = 'Updated Name'; description = 'updated' }
    $proxyUpdate = Invoke-NamespaceMemberJson 'Put' "$WebUrl/api/web/namespaces/$updateProxySlug" $ownerId @{ displayName = 'Updated Name'; description = 'updated' }

    $deleteJavaSlug = "codex-ns-life-delete-java-$suffix"
    $deletePythonSlug = "codex-ns-life-delete-python-$suffix"
    $deleteProxySlug = "codex-ns-life-delete-proxy-$suffix"
    Ensure-LifeNamespace -Slug $deleteJavaSlug
    Ensure-LifeNamespace -Slug $deletePythonSlug
    Ensure-LifeNamespace -Slug $deleteProxySlug
    $javaDelete = Invoke-NamespaceMemberJson 'Delete' "$JavaUrl/api/v1/namespaces/$deleteJavaSlug" $ownerId
    $pythonDelete = Invoke-NamespaceMemberJson 'Delete' "$PythonUrl/api/v1/namespaces/$deletePythonSlug" $ownerId
    $proxyDelete = Invoke-NamespaceMemberJson 'Delete' "$WebUrl/api/web/namespaces/$deleteProxySlug" $ownerId
    $deleteExistsJava = Read-LifeNamespaceExists -Slug $deleteJavaSlug
    $deleteExistsPython = Read-LifeNamespaceExists -Slug $deletePythonSlug
    $deleteExistsProxy = Read-LifeNamespaceExists -Slug $deleteProxySlug

    $freezeJavaSlug = "codex-ns-life-freeze-java-$suffix"
    $freezePythonSlug = "codex-ns-life-freeze-python-$suffix"
    $freezeProxySlug = "codex-ns-life-freeze-proxy-$suffix"
    Ensure-LifeNamespace -Slug $freezeJavaSlug
    Ensure-LifeNamespace -Slug $freezePythonSlug
    Ensure-LifeNamespace -Slug $freezeProxySlug
    $javaFreeze = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$freezeJavaSlug/freeze" $ownerId @{ reason = 'maintenance' }
    $pythonFreeze = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$freezePythonSlug/freeze" $ownerId @{ reason = 'maintenance' }
    $proxyFreeze = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$freezeProxySlug/freeze" $ownerId @{ reason = 'maintenance' }
    $freezeAuditJava = Read-LifeAudit -Slug $freezeJavaSlug -Action 'FREEZE_NAMESPACE'
    $freezeAuditPython = Read-LifeAudit -Slug $freezePythonSlug -Action 'FREEZE_NAMESPACE'
    $freezeAuditProxy = Read-LifeAudit -Slug $freezeProxySlug -Action 'FREEZE_NAMESPACE'

    $unfreezeJavaSlug = "codex-ns-life-unfreeze-java-$suffix"
    $unfreezePythonSlug = "codex-ns-life-unfreeze-python-$suffix"
    $unfreezeProxySlug = "codex-ns-life-unfreeze-proxy-$suffix"
    Ensure-LifeNamespace -Slug $unfreezeJavaSlug -Status 'FROZEN'
    Ensure-LifeNamespace -Slug $unfreezePythonSlug -Status 'FROZEN'
    Ensure-LifeNamespace -Slug $unfreezeProxySlug -Status 'FROZEN'
    $javaUnfreeze = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$unfreezeJavaSlug/unfreeze" $ownerId
    $pythonUnfreeze = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$unfreezePythonSlug/unfreeze" $ownerId
    $proxyUnfreeze = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$unfreezeProxySlug/unfreeze" $ownerId

    $archiveJavaSlug = "codex-ns-life-archive-java-$suffix"
    $archivePythonSlug = "codex-ns-life-archive-python-$suffix"
    $archiveProxySlug = "codex-ns-life-archive-proxy-$suffix"
    Ensure-LifeNamespace -Slug $archiveJavaSlug
    Ensure-LifeNamespace -Slug $archivePythonSlug
    Ensure-LifeNamespace -Slug $archiveProxySlug
    $javaArchive = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$archiveJavaSlug/archive" $ownerId @{ reason = 'retired' }
    $pythonArchive = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$archivePythonSlug/archive" $ownerId @{ reason = 'retired' }
    $proxyArchive = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$archiveProxySlug/archive" $ownerId @{ reason = 'retired' }

    $restoreJavaSlug = "codex-ns-life-restore-java-$suffix"
    $restorePythonSlug = "codex-ns-life-restore-python-$suffix"
    $restoreProxySlug = "codex-ns-life-restore-proxy-$suffix"
    Ensure-LifeNamespace -Slug $restoreJavaSlug -Status 'ARCHIVED'
    Ensure-LifeNamespace -Slug $restorePythonSlug -Status 'ARCHIVED'
    Ensure-LifeNamespace -Slug $restoreProxySlug -Status 'ARCHIVED'
    $javaRestore = Invoke-NamespaceMemberJson 'Post' "$JavaUrl/api/v1/namespaces/$restoreJavaSlug/restore" $ownerId
    $pythonRestore = Invoke-NamespaceMemberJson 'Post' "$PythonUrl/api/v1/namespaces/$restorePythonSlug/restore" $ownerId
    $proxyRestore = Invoke-NamespaceMemberJson 'Post' "$WebUrl/api/web/namespaces/$restoreProxySlug/restore" $ownerId

    $memberUpdateJava = Invoke-NamespaceMemberStatusJson 'Put' "$JavaUrl/api/v1/namespaces/$updateJavaSlug" $memberId @{ displayName = 'Forbidden'; description = 'forbidden' }
    $memberUpdatePython = Invoke-NamespaceMemberStatusJson 'Put' "$PythonUrl/api/v1/namespaces/$updatePythonSlug" $memberId @{ displayName = 'Forbidden'; description = 'forbidden' }
    $memberUpdateProxy = Invoke-NamespaceMemberStatusJson 'Put' "$WebUrl/api/web/namespaces/$updateProxySlug" $memberId @{ displayName = 'Forbidden'; description = 'forbidden' }
    $forbiddenArchiveJavaSlug = "codex-ns-life-archive-forbidden-java-$suffix"
    $forbiddenArchivePythonSlug = "codex-ns-life-archive-forbidden-python-$suffix"
    $forbiddenArchiveProxySlug = "codex-ns-life-archive-forbidden-proxy-$suffix"
    Ensure-LifeNamespace -Slug $forbiddenArchiveJavaSlug
    Ensure-LifeNamespace -Slug $forbiddenArchivePythonSlug
    Ensure-LifeNamespace -Slug $forbiddenArchiveProxySlug
    $memberArchiveJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces/$forbiddenArchiveJavaSlug/archive" $memberId @{ reason = 'forbidden' }
    $memberArchivePython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces/$forbiddenArchivePythonSlug/archive" $memberId @{ reason = 'forbidden' }
    $memberArchiveProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces/$forbiddenArchiveProxySlug/archive" $memberId @{ reason = 'forbidden' }
    $badCreateJava = Invoke-NamespaceMemberStatusJson 'Post' "$JavaUrl/api/v1/namespaces" $memberId @{ slug = "codex-ns-life-bad-$suffix"; displayName = 'Bad'; description = 'bad' }
    $badCreatePython = Invoke-NamespaceMemberStatusJson 'Post' "$PythonUrl/api/v1/namespaces" $memberId @{ slug = "codex-ns-life-bad-py-$suffix"; displayName = 'Bad'; description = 'bad' }
    $badCreateProxy = Invoke-NamespaceMemberStatusJson 'Post' "$WebUrl/api/web/namespaces" $memberId @{ slug = "codex-ns-life-bad-proxy-$suffix"; displayName = 'Bad'; description = 'bad' }

    $stable = [ordered]@{
        create = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaCreate
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonCreate
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyCreate
        }
        update = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaUpdate
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonUpdate
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyUpdate
        }
        delete = [ordered]@{
            java = ConvertTo-StableNamespaceMemberMessageJson -Response $javaDelete
            python = ConvertTo-StableNamespaceMemberMessageJson -Response $pythonDelete
            proxy = ConvertTo-StableNamespaceMemberMessageJson -Response $proxyDelete
        }
        freeze = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaFreeze
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonFreeze
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyFreeze
        }
        unfreeze = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaUnfreeze
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonUnfreeze
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyUnfreeze
        }
        archive = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaArchive
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonArchive
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyArchive
        }
        restore = [ordered]@{
            java = ConvertTo-StableNamespaceProfileJson -Response $javaRestore
            python = ConvertTo-StableNamespaceProfileJson -Response $pythonRestore
            proxy = ConvertTo-StableNamespaceProfileJson -Response $proxyRestore
        }
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            "/api/v1/namespaces",
            "/api/web/namespaces",
            "/api/v1/namespaces/{slug}",
            "/api/web/namespaces/{slug}",
            "/api/v1/namespaces/{slug}/freeze",
            "/api/web/namespaces/{slug}/unfreeze",
            "/api/v1/namespaces/{slug}/archive",
            "/api/web/namespaces/{slug}/restore"
        )
        checks = [ordered]@{
            createStatusShapeMatches = ($javaCreate.data.status -eq 'ACTIVE' -and $pythonCreate.data.status -eq 'ACTIVE' -and $proxyCreate.data.status -eq 'ACTIVE' -and $javaCreate.data.type -eq 'TEAM' -and $pythonCreate.data.type -eq 'TEAM' -and $proxyCreate.data.type -eq 'TEAM')
            createOwnerMemberCreated = ($createMemberJava -eq 'OWNER' -and $createMemberPython -eq 'OWNER' -and $createMemberProxy -eq 'OWNER')
            updateShapeMatches = ($javaUpdate.data.displayName -eq 'Updated Name' -and $pythonUpdate.data.displayName -eq 'Updated Name' -and $proxyUpdate.data.displayName -eq 'Updated Name')
            deleteEnvelopeMatches = ($stable.delete.java -eq $stable.delete.python -and $stable.delete.python -eq $stable.delete.proxy)
            deleteRemovesRows = ($deleteExistsJava -eq 'false' -and $deleteExistsPython -eq 'false' -and $deleteExistsProxy -eq 'false')
            freezeStatusMatches = ($javaFreeze.data.status -eq 'FROZEN' -and $pythonFreeze.data.status -eq 'FROZEN' -and $proxyFreeze.data.status -eq 'FROZEN')
            unfreezeStatusMatches = ($javaUnfreeze.data.status -eq 'ACTIVE' -and $pythonUnfreeze.data.status -eq 'ACTIVE' -and $proxyUnfreeze.data.status -eq 'ACTIVE')
            archiveStatusMatches = ($javaArchive.data.status -eq 'ARCHIVED' -and $pythonArchive.data.status -eq 'ARCHIVED' -and $proxyArchive.data.status -eq 'ARCHIVED')
            restoreStatusMatches = ($javaRestore.data.status -eq 'ACTIVE' -and $pythonRestore.data.status -eq 'ACTIVE' -and $proxyRestore.data.status -eq 'ACTIVE')
            freezeAuditWritten = ($freezeAuditJava -like 'FREEZE_NAMESPACE|NAMESPACE|*' -and $freezeAuditPython -like 'FREEZE_NAMESPACE|NAMESPACE|*' -and $freezeAuditProxy -like 'FREEZE_NAMESPACE|NAMESPACE|*')
            memberUpdateForbidden = ($memberUpdateJava -eq 403 -and $memberUpdatePython -eq 403 -and $memberUpdateProxy -eq 403)
            memberArchiveForbidden = ($memberArchiveJava -eq 403 -and $memberArchivePython -eq 403 -and $memberArchiveProxy -eq 403)
            createPlatformRoleRequired = ($badCreateJava -eq 403 -and $badCreatePython -eq 403 -and $badCreateProxy -eq 403)
        }
        stable = $stable
        audits = [ordered]@{
            freezeJava = $freezeAuditJava
            freezePython = $freezeAuditPython
            freezeProxy = $freezeAuditProxy
        }
        statusBoundaries = [ordered]@{
            memberUpdate = @($memberUpdateJava, $memberUpdatePython, $memberUpdateProxy)
            memberArchive = @($memberArchiveJava, $memberArchivePython, $memberArchiveProxy)
            badCreate = @($badCreateJava, $badCreatePython, $badCreateProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Namespace profile lifecycle contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridNamespaceProfileLifecycleSmokeVerification {
    try {
        Invoke-NamespaceProfileLifecycleTests
        Start-Hybrid
        Invoke-NamespaceProfileLifecycleContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-AdminLabelDefinitionTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = Join-Path $Root '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_admin_label_definitions.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableAdminLabelJson {
    param(
        [object]$Response,
        [string]$StableSlug = 'fixture'
    )

    $translations = @()
    if ($Response.data -and $Response.data.translations) {
        $translations = @($Response.data.translations | Sort-Object locale | ForEach-Object {
            [ordered]@{
                locale = $_.locale
                displayName = $_.displayName
            }
        })
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            slug = $StableSlug
            type = $Response.data.type
            visibleInFilter = [bool]$Response.data.visibleInFilter
            sortOrder = [int]$Response.data.sortOrder
            translations = $translations
        }
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableAdminLabelListJson {
    param([object]$Response)

    $items = @()
    if ($Response.data) {
        $items = @($Response.data | Sort-Object slug | ForEach-Object {
            [ordered]@{
                slug = $_.slug
                type = $_.type
                visibleInFilter = [bool]$_.visibleInFilter
                sortOrder = [int]$_.sortOrder
                translations = @($_.translations | Sort-Object locale | ForEach-Object {
                    [ordered]@{
                        locale = $_.locale
                        displayName = $_.displayName
                    }
                })
            }
        })
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $items
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableAdminLabelSortJson {
    param([object]$Response)

    $items = @()
    if ($Response.data) {
        $index = 0
        $items = @($Response.data | ForEach-Object {
            $index += 1
            [ordered]@{
                slug = "fixture-$index"
                type = $_.type
                visibleInFilter = [bool]$_.visibleInFilter
                sortOrder = [int]$_.sortOrder
            }
        })
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $items
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-AdminLabelDefinitionJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = @{ 'X-Mock-User-Id' = $UserId }
        ContentType = 'application/json'
        TimeoutSec = 20
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }
    return Invoke-RestMethod @params
}

function Invoke-AdminLabelDefinitionStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = @{ 'X-Mock-User-Id' = $UserId }
        ContentType = 'application/json'
        UseBasicParsing = $true
        TimeoutSec = 20
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }

    try {
        $response = Invoke-WebRequest @params
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Invoke-AdminLabelDefinitionContractComparison {
    param([string]$ResultFileName = 'admin-label-definition-contract-result.json')

    Ensure-AuthContractFixture
    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    $adminId = 'local-admin'
    $userId = 'local-user'

    Invoke-PostgresSql -Sql "DELETE FROM label_definition WHERE slug LIKE 'codex-admin-label-%';"

    $createBody = @{
        slug = "codex-admin-label-create-java-$suffix"
        type = 'RECOMMENDED'
        visibleInFilter = $true
        sortOrder = 11
        translations = @(@{ locale = 'en_US'; displayName = 'Created Label' })
    }
    $javaCreate = Invoke-AdminLabelDefinitionJson 'Post' "$JavaUrl/api/v1/admin/labels" $adminId $createBody
    $createBody.slug = "codex-admin-label-create-python-$suffix"
    $pythonCreate = Invoke-AdminLabelDefinitionJson 'Post' "$PythonUrl/api/v1/admin/labels" $adminId $createBody
    $createBody.slug = "codex-admin-label-create-proxy-$suffix"
    $proxyCreate = Invoke-AdminLabelDefinitionJson 'Post' "$WebUrl/api/v1/admin/labels" $adminId $createBody

    $updateSlugs = @{
        java = "codex-admin-label-update-java-$suffix"
        python = "codex-admin-label-update-python-$suffix"
        proxy = "codex-admin-label-update-proxy-$suffix"
    }
    $sortSlugs = @{
        javaA = "codex-admin-label-sort-java-a-$suffix"
        javaB = "codex-admin-label-sort-java-b-$suffix"
        pythonA = "codex-admin-label-sort-python-a-$suffix"
        pythonB = "codex-admin-label-sort-python-b-$suffix"
        proxyA = "codex-admin-label-sort-proxy-a-$suffix"
        proxyB = "codex-admin-label-sort-proxy-b-$suffix"
    }
    $deleteSlugs = @{
        java = "codex-admin-label-delete-java-$suffix"
        python = "codex-admin-label-delete-python-$suffix"
        proxy = "codex-admin-label-delete-proxy-$suffix"
    }

    $allFixtureSlugs = @($updateSlugs.java, $updateSlugs.python, $updateSlugs.proxy, $sortSlugs.javaA, $sortSlugs.javaB, $sortSlugs.pythonA, $sortSlugs.pythonB, $sortSlugs.proxyA, $sortSlugs.proxyB, $deleteSlugs.java, $deleteSlugs.python, $deleteSlugs.proxy)
    $values = ($allFixtureSlugs | ForEach-Object { "('$_', 'RECOMMENDED', TRUE, 50, '$adminId')" }) -join ",`n        "
    $seedSql = @"
WITH inserted AS (
    INSERT INTO label_definition (slug, type, visible_in_filter, sort_order, created_by)
    VALUES
        $values
    ON CONFLICT (slug) DO UPDATE
        SET type = EXCLUDED.type,
            visible_in_filter = EXCLUDED.visible_in_filter,
            sort_order = EXCLUDED.sort_order,
            updated_at = CURRENT_TIMESTAMP
    RETURNING id, slug
)
INSERT INTO label_translation (label_id, locale, display_name)
SELECT id, 'en', 'Seeded Label'
FROM inserted
ON CONFLICT (label_id, locale) DO UPDATE
    SET display_name = EXCLUDED.display_name,
        updated_at = CURRENT_TIMESTAMP;
"@
    Invoke-PostgresSql -Sql $seedSql

    $updateBody = @{
        type = 'PRIVILEGED'
        visibleInFilter = $false
        sortOrder = 7
        translations = @(@{ locale = 'zh_TW'; displayName = 'Updated Label' })
    }
    $javaUpdate = Invoke-AdminLabelDefinitionJson 'Put' "$JavaUrl/api/v1/admin/labels/$($updateSlugs.java)" $adminId $updateBody
    $pythonUpdate = Invoke-AdminLabelDefinitionJson 'Put' "$PythonUrl/api/v1/admin/labels/$($updateSlugs.python)" $adminId $updateBody
    $proxyUpdate = Invoke-AdminLabelDefinitionJson 'Put' "$WebUrl/api/v1/admin/labels/$($updateSlugs.proxy)" $adminId $updateBody

    $sortBodyJava = @{ items = @(@{ slug = $sortSlugs.javaB; sortOrder = 1 }, @{ slug = $sortSlugs.javaA; sortOrder = 2 }) }
    $sortBodyPython = @{ items = @(@{ slug = $sortSlugs.pythonB; sortOrder = 1 }, @{ slug = $sortSlugs.pythonA; sortOrder = 2 }) }
    $sortBodyProxy = @{ items = @(@{ slug = $sortSlugs.proxyB; sortOrder = 1 }, @{ slug = $sortSlugs.proxyA; sortOrder = 2 }) }
    $javaSort = Invoke-AdminLabelDefinitionJson 'Put' "$JavaUrl/api/v1/admin/labels/sort-order" $adminId $sortBodyJava
    $pythonSort = Invoke-AdminLabelDefinitionJson 'Put' "$PythonUrl/api/v1/admin/labels/sort-order" $adminId $sortBodyPython
    $proxySort = Invoke-AdminLabelDefinitionJson 'Put' "$WebUrl/api/v1/admin/labels/sort-order" $adminId $sortBodyProxy

    $javaDelete = Invoke-AdminLabelDefinitionJson 'Delete' "$JavaUrl/api/v1/admin/labels/$($deleteSlugs.java)" $adminId
    $pythonDelete = Invoke-AdminLabelDefinitionJson 'Delete' "$PythonUrl/api/v1/admin/labels/$($deleteSlugs.python)" $adminId
    $proxyDelete = Invoke-AdminLabelDefinitionJson 'Delete' "$WebUrl/api/v1/admin/labels/$($deleteSlugs.proxy)" $adminId

    $list = Invoke-AdminLabelDefinitionJson 'Get' "$PythonUrl/api/v1/admin/labels" $adminId
    $proxyList = Invoke-AdminLabelDefinitionJson 'Get' "$WebUrl/api/v1/admin/labels" $adminId
    $forbiddenGetJava = Invoke-AdminLabelDefinitionStatus 'Get' "$JavaUrl/api/v1/admin/labels" $userId
    $forbiddenGetPython = Invoke-AdminLabelDefinitionStatus 'Get' "$PythonUrl/api/v1/admin/labels" $userId
    $forbiddenGetProxy = Invoke-AdminLabelDefinitionStatus 'Get' "$WebUrl/api/v1/admin/labels" $userId

    $createdByJava = Invoke-PostgresScalar -Sql "SELECT created_by FROM label_definition WHERE slug = 'codex-admin-label-create-java-$suffix';"
    $createdByPython = Invoke-PostgresScalar -Sql "SELECT created_by FROM label_definition WHERE slug = 'codex-admin-label-create-python-$suffix';"
    $createdByProxy = Invoke-PostgresScalar -Sql "SELECT created_by FROM label_definition WHERE slug = 'codex-admin-label-create-proxy-$suffix';"
    $deleteExists = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM label_definition WHERE slug IN ('$($deleteSlugs.java)', '$($deleteSlugs.python)', '$($deleteSlugs.proxy)');"
    $auditCreate = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM audit_log WHERE action = 'LABEL_CREATE' AND actor_user_id = '$adminId' AND detail_json->>'slug' LIKE 'codex-admin-label-create-%-$suffix';"
    $auditUpdate = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM audit_log WHERE action = 'LABEL_UPDATE' AND actor_user_id = '$adminId' AND detail_json->>'slug' LIKE 'codex-admin-label-update-%-$suffix';"
    $auditDelete = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM audit_log WHERE action = 'LABEL_DELETE' AND actor_user_id = '$adminId' AND detail_json->>'slug' LIKE 'codex-admin-label-delete-%-$suffix';"
    $auditSort = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM audit_log WHERE action = 'LABEL_SORT_ORDER_UPDATE' AND actor_user_id = '$adminId' AND detail_json->>'count' = '2';"
    $sortPersisted = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM label_definition WHERE (slug IN ('$($sortSlugs.javaB)', '$($sortSlugs.pythonB)', '$($sortSlugs.proxyB)') AND sort_order = 1) OR (slug IN ('$($sortSlugs.javaA)', '$($sortSlugs.pythonA)', '$($sortSlugs.proxyA)') AND sort_order = 2);"

    $stable = [ordered]@{
        create = [ordered]@{
            java = ConvertTo-StableAdminLabelJson -Response $javaCreate
            python = ConvertTo-StableAdminLabelJson -Response $pythonCreate
            proxy = ConvertTo-StableAdminLabelJson -Response $proxyCreate
        }
        update = [ordered]@{
            java = ConvertTo-StableAdminLabelJson -Response $javaUpdate
            python = ConvertTo-StableAdminLabelJson -Response $pythonUpdate
            proxy = ConvertTo-StableAdminLabelJson -Response $proxyUpdate
        }
        sort = [ordered]@{
            java = ConvertTo-StableAdminLabelSortJson -Response $javaSort
            python = ConvertTo-StableAdminLabelSortJson -Response $pythonSort
            proxy = ConvertTo-StableAdminLabelSortJson -Response $proxySort
        }
        list = [ordered]@{
            python = ConvertTo-StableAdminLabelListJson -Response $list
            proxy = ConvertTo-StableAdminLabelListJson -Response $proxyList
        }
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            '/api/v1/admin/labels',
            '/api/v1/admin/labels/{slug}',
            '/api/v1/admin/labels/sort-order'
        )
        checks = [ordered]@{
            createEnvelopeMatches = ($stable.create.java -eq $stable.create.python -and $stable.create.python -eq $stable.create.proxy)
            updateEnvelopeMatches = ($stable.update.java -eq $stable.update.python -and $stable.update.python -eq $stable.update.proxy)
            sortEnvelopeMatches = ($stable.sort.java -eq $stable.sort.python -and $stable.sort.python -eq $stable.sort.proxy)
            sortOrderPersisted = ($sortPersisted -eq '6')
            deleteEnvelopeMatches = ($javaDelete.data.message -eq 'Label deleted' -and $pythonDelete.data.message -eq 'Label deleted' -and $proxyDelete.data.message -eq 'Label deleted')
            deleteRemovesRows = ($deleteExists -eq '0')
            listProxyMatchesPython = ($stable.list.python -eq $stable.list.proxy)
            createdByMatchesActor = ($createdByJava -eq $adminId -and $createdByPython -eq $adminId -and $createdByProxy -eq $adminId)
            auditCreateWritten = ([int]$auditCreate -ge 3)
            auditUpdateWritten = ([int]$auditUpdate -ge 3)
            auditDeleteWritten = ([int]$auditDelete -ge 3)
            auditSortWritten = ([int]$auditSort -ge 3)
            superAdminRequired = ($forbiddenGetJava -eq 403 -and $forbiddenGetPython -eq 403 -and $forbiddenGetProxy -eq 403)
        }
        stable = $stable
        statuses = [ordered]@{
            forbiddenGet = @($forbiddenGetJava, $forbiddenGetPython, $forbiddenGetProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Admin label definition contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridAdminLabelDefinitionSmokeVerification {
    try {
        Invoke-AdminLabelDefinitionTests
        Start-Hybrid
        Invoke-AdminLabelDefinitionContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-AdminUserManagementTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = Join-Path $Root '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_admin_user_management.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableAdminUserPageJson {
    param([object]$Response)

    $items = @()
    if ($Response.data -and $Response.data.items) {
        $items = @($Response.data.items | Sort-Object id | ForEach-Object {
            [ordered]@{
                id = 'fixture'
                username = $_.username
                email = 'fixture@example.test'
                status = $_.status
                platformRoles = @($_.platformRoles | Sort-Object)
            }
        })
    }

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            items = $items
            total = [int]$Response.data.total
            page = [int]$Response.data.page
            size = [int]$Response.data.size
        }
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function ConvertTo-StableAdminUserMutationJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = [ordered]@{
            userId = 'fixture'
            role = $Response.data.role
            status = $Response.data.status
        }
    }

    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-AdminUserJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = @{ 'X-Mock-User-Id' = $UserId }
        ContentType = 'application/json'
        TimeoutSec = 20
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }
    return Invoke-RestMethod @params
}

function Invoke-AdminUserStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId,
        [object]$Body = $null
    )

    $params = @{
        Uri = $Url
        Method = $Method
        Headers = @{ 'X-Mock-User-Id' = $UserId }
        ContentType = 'application/json'
        UseBasicParsing = $true
        TimeoutSec = 20
    }
    if ($null -ne $Body) {
        $params.Body = ($Body | ConvertTo-Json -Depth 20 -Compress)
    }

    try {
        $response = Invoke-WebRequest @params
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Ensure-AdminUserManagementFixture {
    param([string]$Suffix)

    $sql = @"
DO `$`$
DECLARE
    super_admin_role_id BIGINT;
    user_admin_role_id BIGINT;
    skill_admin_role_id BIGINT;
BEGIN
    INSERT INTO role (code, name, description, is_system)
    VALUES
        ('SUPER_ADMIN', 'Super Admin', 'Super administrator', TRUE),
        ('USER_ADMIN', 'User Admin', 'User administrator', TRUE),
        ('SKILL_ADMIN', 'Skill Admin', 'Skill administrator', TRUE)
    ON CONFLICT (code) DO UPDATE
        SET name = EXCLUDED.name,
            description = EXCLUDED.description,
            is_system = TRUE;

    SELECT id INTO super_admin_role_id FROM role WHERE code = 'SUPER_ADMIN';
    SELECT id INTO user_admin_role_id FROM role WHERE code = 'USER_ADMIN';
    SELECT id INTO skill_admin_role_id FROM role WHERE code = 'SKILL_ADMIN';

    DELETE FROM user_role_binding WHERE user_id LIKE 'codex-admin-user-%';
    DELETE FROM user_account WHERE id LIKE 'codex-admin-user-%';

    INSERT INTO user_account (id, display_name, email, avatar_url, status, created_at)
    VALUES
        ('codex-admin-user-actor-$Suffix', 'Codex User Admin', 'actor-$Suffix@example.test', '', 'ACTIVE', '2026-06-10T08:00:00Z'::timestamptz),
        ('codex-admin-user-list-a-$Suffix', 'Codex Listed A', 'list-a-$Suffix@example.test', '', 'ACTIVE', '2026-06-10T09:00:00Z'::timestamptz),
        ('codex-admin-user-list-b-$Suffix', 'Codex Listed B', 'list-b-$Suffix@example.test', '', 'ACTIVE', '2026-06-10T07:00:00Z'::timestamptz),
        ('codex-admin-user-list-disabled-$Suffix', 'Codex Listed Disabled', 'disabled-$Suffix@example.test', '', 'DISABLED', '2026-06-10T06:00:00Z'::timestamptz),
        ('codex-admin-user-role-java-$Suffix', 'Codex Role Java', 'role-java-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP),
        ('codex-admin-user-role-python-$Suffix', 'Codex Role Python', 'role-python-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP),
        ('codex-admin-user-role-proxy-$Suffix', 'Codex Role Proxy', 'role-proxy-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP),
        ('codex-admin-user-status-java-$Suffix', 'Codex Status Java', 'status-java-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP),
        ('codex-admin-user-status-python-$Suffix', 'Codex Status Python', 'status-python-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP),
        ('codex-admin-user-status-proxy-$Suffix', 'Codex Status Proxy', 'status-proxy-$Suffix@example.test', '', 'ACTIVE', CURRENT_TIMESTAMP)
    ON CONFLICT (id) DO UPDATE
        SET display_name = EXCLUDED.display_name,
            email = EXCLUDED.email,
            avatar_url = EXCLUDED.avatar_url,
            status = EXCLUDED.status,
            created_at = EXCLUDED.created_at,
            updated_at = CURRENT_TIMESTAMP;

    INSERT INTO user_role_binding (user_id, role_id)
    VALUES
        ('codex-admin-user-actor-$Suffix', user_admin_role_id),
        ('codex-admin-user-list-a-$Suffix', user_admin_role_id)
    ON CONFLICT (user_id, role_id) DO NOTHING;
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
}

function Invoke-AdminUserManagementContractComparison {
    param([string]$ResultFileName = 'admin-user-management-contract-result.json')

    Ensure-AuthContractFixture
    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    Ensure-AdminUserManagementFixture -Suffix $suffix

    $adminId = 'local-admin'
    $userAdminId = "codex-admin-user-actor-$suffix"
    $query = "?search=$suffix&status=ACTIVE&page=0&size=20"
    $javaList = Invoke-AdminUserJson 'Get' "$JavaUrl/api/v1/admin/users$query" $adminId
    $pythonList = Invoke-AdminUserJson 'Get' "$PythonUrl/api/v1/admin/users$query" $adminId
    $proxyList = Invoke-AdminUserJson 'Get' "$WebUrl/api/v1/admin/users$query" $adminId

    $roleBody = @{ role = 'SKILL_ADMIN' }
    $javaRoleTarget = "codex-admin-user-role-java-$suffix"
    $pythonRoleTarget = "codex-admin-user-role-python-$suffix"
    $proxyRoleTarget = "codex-admin-user-role-proxy-$suffix"
    $javaRole = Invoke-AdminUserJson 'Put' "$JavaUrl/api/v1/admin/users/$javaRoleTarget/role" $adminId $roleBody
    $pythonRole = Invoke-AdminUserJson 'Put' "$PythonUrl/api/v1/admin/users/$pythonRoleTarget/role" $adminId $roleBody
    $proxyRole = Invoke-AdminUserJson 'Put' "$WebUrl/api/v1/admin/users/$proxyRoleTarget/role" $adminId $roleBody

    $statusBody = @{ status = 'DISABLED' }
    $javaStatusTarget = "codex-admin-user-status-java-$suffix"
    $pythonStatusTarget = "codex-admin-user-status-python-$suffix"
    $proxyStatusTarget = "codex-admin-user-status-proxy-$suffix"
    $javaStatus = Invoke-AdminUserJson 'Put' "$JavaUrl/api/v1/admin/users/$javaStatusTarget/status" $adminId $statusBody
    $pythonStatus = Invoke-AdminUserJson 'Put' "$PythonUrl/api/v1/admin/users/$pythonStatusTarget/status" $adminId $statusBody
    $proxyStatus = Invoke-AdminUserJson 'Put' "$WebUrl/api/v1/admin/users/$proxyStatusTarget/status" $adminId $statusBody

    $javaEnable = Invoke-AdminUserJson 'Post' "$JavaUrl/api/v1/admin/users/$javaStatusTarget/enable" $adminId
    $pythonEnable = Invoke-AdminUserJson 'Post' "$PythonUrl/api/v1/admin/users/$pythonStatusTarget/enable" $adminId
    $proxyEnable = Invoke-AdminUserJson 'Post' "$WebUrl/api/v1/admin/users/$proxyStatusTarget/enable" $adminId

    $superAdminDeniedJava = Invoke-AdminUserStatus 'Put' "$JavaUrl/api/v1/admin/users/$javaRoleTarget/role" $userAdminId @{ role = 'SUPER_ADMIN' }
    $superAdminDeniedPython = Invoke-AdminUserStatus 'Put' "$PythonUrl/api/v1/admin/users/$pythonRoleTarget/role" $userAdminId @{ role = 'SUPER_ADMIN' }
    $superAdminDeniedProxy = Invoke-AdminUserStatus 'Put' "$WebUrl/api/v1/admin/users/$proxyRoleTarget/role" $userAdminId @{ role = 'SUPER_ADMIN' }
    $forbiddenListJava = Invoke-AdminUserStatus 'Get' "$JavaUrl/api/v1/admin/users$query" 'local-user'
    $forbiddenListPython = Invoke-AdminUserStatus 'Get' "$PythonUrl/api/v1/admin/users$query" 'local-user'
    $forbiddenListProxy = Invoke-AdminUserStatus 'Get' "$WebUrl/api/v1/admin/users$query" 'local-user'
    $passwordResetJava = Invoke-AdminUserStatus 'Post' "$JavaUrl/api/v1/admin/users/missing-password-reset-$suffix/password-reset" $adminId
    $passwordResetProxy = Invoke-AdminUserStatus 'Post' "$WebUrl/api/v1/admin/users/missing-password-reset-$suffix/password-reset" $adminId

    $roleRows = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM user_role_binding urb JOIN role r ON r.id = urb.role_id WHERE urb.user_id IN ('$javaRoleTarget', '$pythonRoleTarget', '$proxyRoleTarget') AND r.code = 'SKILL_ADMIN';"
    $enabledRows = Invoke-PostgresScalar -Sql "SELECT COUNT(*) FROM user_account WHERE id IN ('$javaStatusTarget', '$pythonStatusTarget', '$proxyStatusTarget') AND status = 'ACTIVE';"

    $stable = [ordered]@{
        list = [ordered]@{
            java = ConvertTo-StableAdminUserPageJson -Response $javaList
            python = ConvertTo-StableAdminUserPageJson -Response $pythonList
            proxy = ConvertTo-StableAdminUserPageJson -Response $proxyList
        }
        role = [ordered]@{
            java = ConvertTo-StableAdminUserMutationJson -Response $javaRole
            python = ConvertTo-StableAdminUserMutationJson -Response $pythonRole
            proxy = ConvertTo-StableAdminUserMutationJson -Response $proxyRole
        }
        status = [ordered]@{
            java = ConvertTo-StableAdminUserMutationJson -Response $javaStatus
            python = ConvertTo-StableAdminUserMutationJson -Response $pythonStatus
            proxy = ConvertTo-StableAdminUserMutationJson -Response $proxyStatus
        }
        enable = [ordered]@{
            java = ConvertTo-StableAdminUserMutationJson -Response $javaEnable
            python = ConvertTo-StableAdminUserMutationJson -Response $pythonEnable
            proxy = ConvertTo-StableAdminUserMutationJson -Response $proxyEnable
        }
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            '/api/v1/admin/users',
            '/api/v1/admin/users/{userId}/role',
            '/api/v1/admin/users/{userId}/status',
            '/api/v1/admin/users/{userId}/approve',
            '/api/v1/admin/users/{userId}/disable',
            '/api/v1/admin/users/{userId}/enable'
        )
        checks = [ordered]@{
            listEnvelopeMatches = ($stable.list.java -eq $stable.list.python -and $stable.list.python -eq $stable.list.proxy)
            roleEnvelopeMatches = ($stable.role.java -eq $stable.role.python -and $stable.role.python -eq $stable.role.proxy)
            statusEnvelopeMatches = ($stable.status.java -eq $stable.status.python -and $stable.status.python -eq $stable.status.proxy)
            enableEnvelopeMatches = ($stable.enable.java -eq $stable.enable.python -and $stable.enable.python -eq $stable.enable.proxy)
            rolePersisted = ($roleRows -eq '3')
            enablePersisted = ($enabledRows -eq '3')
            userAdminCannotAssignSuperAdmin = ($superAdminDeniedJava -eq 403 -and $superAdminDeniedPython -eq 403 -and $superAdminDeniedProxy -eq 403)
            nonAdminForbidden = ($forbiddenListJava -eq 403 -and $forbiddenListPython -eq 403 -and $forbiddenListProxy -eq 403)
            passwordResetStillJavaOwned = ($passwordResetJava -eq $passwordResetProxy)
        }
        stable = $stable
        statuses = [ordered]@{
            superAdminDenied = @($superAdminDeniedJava, $superAdminDeniedPython, $superAdminDeniedProxy)
            forbiddenList = @($forbiddenListJava, $forbiddenListPython, $forbiddenListProxy)
            passwordReset = @($passwordResetJava, $passwordResetProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Admin user management contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-GovernanceWorkbenchTests {
    Push-Location (Join-Path $Root 'server-python')
    try {
        $env:UV_CACHE_DIR = Join-Path $Root '.uv-cache'
        Invoke-NativeCommand -FilePath 'uv' -Arguments @('run', 'pytest', 'tests/test_governance_workbench.py', 'tests/test_hybrid_makefile.py', '-q')
    } finally {
        Pop-Location
    }

    Push-Location (Join-Path $Root 'web')
    try {
        Invoke-NativeCommand -FilePath 'npx.cmd' -Arguments @('vitest', 'run', 'vite.config.test.ts')
    } finally {
        Pop-Location
    }
}

function ConvertTo-StableGovernanceJson {
    param([object]$Response)

    $stable = [ordered]@{
        code = $Response.code
        msg = $Response.msg
        data = $Response.data
    }
    return ($stable | ConvertTo-Json -Depth 50 -Compress)
}

function Invoke-GovernanceJson {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId
    )

    return Invoke-RestMethod -Uri $Url -Method $Method -Headers @{ 'X-Mock-User-Id' = $UserId } -ContentType 'application/json' -TimeoutSec 20
}

function Invoke-GovernanceStatus {
    param(
        [string]$Method,
        [string]$Url,
        [string]$UserId
    )

    try {
        $response = Invoke-WebRequest -Uri $Url -Method $Method -Headers @{ 'X-Mock-User-Id' = $UserId } -UseBasicParsing -TimeoutSec 20
        return [int]$response.StatusCode
    } catch {
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            return [int]$_.Exception.Response.StatusCode
        }
        throw
    }
}

function Ensure-GovernanceWorkbenchFixture {
    param([string]$Suffix)

    $sql = @"
DO `$`$
DECLARE
    ns_id BIGINT;
    skill_id BIGINT;
    version_id BIGINT;
    review_id BIGINT;
    global_ns_id BIGINT;
BEGIN
    SELECT id INTO global_ns_id FROM namespace WHERE slug = 'global';

    DELETE FROM audit_log WHERE request_id LIKE 'codex-governance-%';
    DELETE FROM user_notification WHERE title LIKE 'Codex Governance Notification %';
    DELETE FROM skill_report sr
    WHERE sr.namespace_id IN (SELECT id FROM namespace WHERE slug LIKE 'codex-governance-%');
    DELETE FROM promotion_request pr
    WHERE pr.source_skill_id IN (
        SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug LIKE 'codex-governance-%'
    );
    DELETE FROM review_task rt
    WHERE rt.namespace_id IN (SELECT id FROM namespace WHERE slug LIKE 'codex-governance-%');
    UPDATE skill s SET latest_version_id = NULL
    WHERE s.namespace_id IN (SELECT id FROM namespace WHERE slug LIKE 'codex-governance-%');
    DELETE FROM skill_version sv
    WHERE sv.skill_id IN (
        SELECT s.id FROM skill s JOIN namespace n ON n.id = s.namespace_id WHERE n.slug LIKE 'codex-governance-%'
    );
    DELETE FROM skill s
    WHERE s.namespace_id IN (SELECT id FROM namespace WHERE slug LIKE 'codex-governance-%');
    DELETE FROM namespace_member nm
    WHERE nm.namespace_id IN (SELECT id FROM namespace WHERE slug LIKE 'codex-governance-%')
       OR nm.user_id LIKE 'codex-governance-%';
    DELETE FROM namespace WHERE slug LIKE 'codex-governance-%';
    DELETE FROM user_account WHERE id LIKE 'codex-governance-%';

    INSERT INTO user_account (id, display_name, email, status, created_at, updated_at)
    VALUES
        ('codex-governance-manager-$Suffix', 'Codex Governance Manager', 'governance-manager-$Suffix@example.test', 'ACTIVE', TIMESTAMP '2036-06-10 08:00:00', TIMESTAMP '2036-06-10 08:00:00'),
        ('codex-governance-submitter-$Suffix', 'Codex Governance Submitter', 'governance-submitter-$Suffix@example.test', 'ACTIVE', TIMESTAMP '2036-06-10 08:00:00', TIMESTAMP '2036-06-10 08:00:00'),
        ('codex-governance-reporter-$Suffix', 'Codex Governance Reporter', 'governance-reporter-$Suffix@example.test', 'ACTIVE', TIMESTAMP '2036-06-10 08:00:00', TIMESTAMP '2036-06-10 08:00:00')
    ON CONFLICT (id) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        email = EXCLUDED.email,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP;

    INSERT INTO namespace (slug, display_name, type, description, status, created_by, created_at, updated_at)
    VALUES ('codex-governance-$Suffix', 'Codex Governance $Suffix', 'TEAM', 'Governance workbench fixture', 'ACTIVE', 'local-admin', TIMESTAMP '2036-06-10 08:00:00', TIMESTAMP '2036-06-10 08:00:00')
    ON CONFLICT (slug) DO UPDATE SET
        display_name = EXCLUDED.display_name,
        status = EXCLUDED.status,
        updated_at = CURRENT_TIMESTAMP
    RETURNING id INTO ns_id;

    INSERT INTO namespace_member (namespace_id, user_id, role, created_at, updated_at)
    VALUES (ns_id, 'codex-governance-manager-$Suffix', 'ADMIN', TIMESTAMP '2036-06-10 08:00:00', TIMESTAMP '2036-06-10 08:00:00')
    ON CONFLICT (namespace_id, user_id) DO UPDATE SET role = EXCLUDED.role, updated_at = CURRENT_TIMESTAMP;

    INSERT INTO skill (namespace_id, slug, display_name, summary, owner_id, visibility, status, download_count, star_count, rating_avg, rating_count, created_by, created_at, updated_by, updated_at)
    VALUES (ns_id, 'codex-governance-skill-$Suffix', 'Codex Governance Skill', 'Governance fixture', 'codex-governance-submitter-$Suffix', 'PUBLIC', 'ACTIVE', 0, 0, 0.00, 0, 'codex-governance-submitter-$Suffix', TIMESTAMP '2036-06-10 08:01:00', 'codex-governance-submitter-$Suffix', TIMESTAMP '2036-06-10 08:01:00')
    RETURNING id INTO skill_id;

    INSERT INTO skill_version (skill_id, version, status, changelog, file_count, total_size, created_by, created_at)
    VALUES (skill_id, '9.9.$Suffix', 'UPLOADED', 'Governance fixture', 0, 0, 'codex-governance-submitter-$Suffix', TIMESTAMP '2036-06-10 08:02:00')
    RETURNING id INTO version_id;

    UPDATE skill SET latest_version_id = version_id WHERE id = skill_id;

    INSERT INTO review_task (skill_version_id, namespace_id, status, version, submitted_by, submitted_at)
    VALUES (version_id, ns_id, 'PENDING', 1, 'codex-governance-submitter-$Suffix', TIMESTAMP '2036-06-10 08:03:00')
    RETURNING id INTO review_id;

    INSERT INTO promotion_request (source_skill_id, source_version_id, target_namespace_id, status, version, submitted_by, submitted_at)
    VALUES (skill_id, version_id, global_ns_id, 'PENDING', 1, 'codex-governance-submitter-$Suffix', TIMESTAMP '2036-06-10 08:04:00');

    INSERT INTO skill_report (skill_id, namespace_id, reporter_id, reason, details, status, created_at)
    VALUES (skill_id, ns_id, 'codex-governance-reporter-$Suffix', 'governance fixture report', 'governance fixture details', 'PENDING', TIMESTAMP '2036-06-10 08:05:00');

    INSERT INTO user_notification (user_id, category, entity_type, entity_id, title, body_json, status, created_at)
    VALUES ('local-admin', 'REVIEW', 'REVIEW', review_id, 'Codex Governance Notification $Suffix', '{"suffix":"$Suffix"}', 'UNREAD', TIMESTAMPTZ '2036-06-10 08:06:00+00');

    INSERT INTO audit_log (actor_user_id, action, target_type, target_id, request_id, client_ip, user_agent, detail_json, created_at)
    VALUES ('local-admin', 'REVIEW_APPROVE', 'REVIEW', review_id, 'codex-governance-$Suffix', '127.0.0.1', 'codex-live-gate', NULL, TIMESTAMP '2036-06-10 08:07:00');
END `$`$;
"@
    Invoke-PostgresSql -Sql $sql
}

function Invoke-GovernanceWorkbenchContractComparison {
    param([string]$ResultFileName = 'governance-workbench-contract-result.json')

    Ensure-AuthContractFixture
    $suffix = Get-Date -Format 'yyyyMMddHHmmssfff'
    Ensure-GovernanceWorkbenchFixture -Suffix $suffix

    $adminId = 'local-admin'
    $managerId = "codex-governance-manager-$suffix"

    $javaSummary = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/summary" $adminId
    $pythonSummary = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/summary" $adminId
    $proxySummary = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/summary" $adminId
    $javaManagerSummary = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/summary" $managerId
    $pythonManagerSummary = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/summary" $managerId
    $proxyManagerSummary = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/summary" $managerId

    $javaInbox = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/inbox?page=0&size=20" $managerId
    $pythonInbox = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/inbox?page=0&size=20" $managerId
    $proxyInbox = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/inbox?page=0&size=20" $managerId
    $javaReportInbox = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/inbox?type=REPORT&page=0&size=1" $adminId
    $pythonReportInbox = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/inbox?type=REPORT&page=0&size=1" $adminId
    $proxyReportInbox = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/inbox?type=REPORT&page=0&size=1" $adminId

    $javaActivity = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/activity?page=0&size=1" $adminId
    $pythonActivity = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/activity?page=0&size=1" $adminId
    $proxyActivity = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/activity?page=0&size=1" $adminId
    $javaManagerActivity = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/activity?page=1&size=5" $managerId
    $pythonManagerActivity = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/activity?page=1&size=5" $managerId
    $proxyManagerActivity = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/activity?page=1&size=5" $managerId

    $javaNotifications = Invoke-GovernanceJson 'Get' "$JavaUrl/api/v1/governance/notifications?page=0&size=20" $adminId
    $pythonNotifications = Invoke-GovernanceJson 'Get' "$PythonUrl/api/v1/governance/notifications?page=0&size=20" $adminId
    $proxyNotifications = Invoke-GovernanceJson 'Get' "$WebUrl/api/v1/governance/notifications?page=0&size=20" $adminId
    $markReadJava = Invoke-GovernanceStatus 'Post' "$JavaUrl/api/v1/governance/notifications/999999999/read" $adminId
    $markReadProxy = Invoke-GovernanceStatus 'Post' "$WebUrl/api/v1/governance/notifications/999999999/read" $adminId

    $stable = [ordered]@{
        summary = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaSummary
            python = ConvertTo-StableGovernanceJson -Response $pythonSummary
            proxy = ConvertTo-StableGovernanceJson -Response $proxySummary
        }
        managerSummary = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaManagerSummary
            python = ConvertTo-StableGovernanceJson -Response $pythonManagerSummary
            proxy = ConvertTo-StableGovernanceJson -Response $proxyManagerSummary
        }
        inbox = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaInbox
            python = ConvertTo-StableGovernanceJson -Response $pythonInbox
            proxy = ConvertTo-StableGovernanceJson -Response $proxyInbox
        }
        reportInbox = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaReportInbox
            python = ConvertTo-StableGovernanceJson -Response $pythonReportInbox
            proxy = ConvertTo-StableGovernanceJson -Response $proxyReportInbox
        }
        activity = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaActivity
            python = ConvertTo-StableGovernanceJson -Response $pythonActivity
            proxy = ConvertTo-StableGovernanceJson -Response $proxyActivity
        }
        managerActivity = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaManagerActivity
            python = ConvertTo-StableGovernanceJson -Response $pythonManagerActivity
            proxy = ConvertTo-StableGovernanceJson -Response $proxyManagerActivity
        }
        notifications = [ordered]@{
            java = ConvertTo-StableGovernanceJson -Response $javaNotifications
            python = ConvertTo-StableGovernanceJson -Response $pythonNotifications
            proxy = ConvertTo-StableGovernanceJson -Response $proxyNotifications
        }
    }

    $result = [ordered]@{
        suffix = $suffix
        routes = @(
            '/api/v1/governance/summary',
            '/api/web/governance/summary',
            '/api/v1/governance/inbox',
            '/api/web/governance/inbox',
            '/api/v1/governance/activity',
            '/api/web/governance/activity',
            '/api/v1/governance/notifications',
            '/api/web/governance/notifications'
        )
        checks = [ordered]@{
            summaryEnvelopeMatches = ($stable.summary.java -eq $stable.summary.python -and $stable.summary.python -eq $stable.summary.proxy)
            managerSummaryEnvelopeMatches = ($stable.managerSummary.java -eq $stable.managerSummary.python -and $stable.managerSummary.python -eq $stable.managerSummary.proxy)
            inboxEnvelopeMatches = ($stable.inbox.java -eq $stable.inbox.python -and $stable.inbox.python -eq $stable.inbox.proxy)
            reportInboxEnvelopeMatches = ($stable.reportInbox.java -eq $stable.reportInbox.python -and $stable.reportInbox.python -eq $stable.reportInbox.proxy)
            activityEnvelopeMatches = ($stable.activity.java -eq $stable.activity.python -and $stable.activity.python -eq $stable.activity.proxy)
            managerActivityEnvelopeMatches = ($stable.managerActivity.java -eq $stable.managerActivity.python -and $stable.managerActivity.python -eq $stable.managerActivity.proxy)
            notificationEnvelopeMatches = ($stable.notifications.java -eq $stable.notifications.python -and $stable.notifications.python -eq $stable.notifications.proxy)
            markReadStillJavaOwned = ($markReadJava -eq $markReadProxy)
        }
        stable = $stable
        statuses = [ordered]@{
            markRead = @($markReadJava, $markReadProxy)
        }
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    foreach ($entry in $result.checks.GetEnumerator()) {
        if (-not $entry.Value) {
            throw "Governance workbench contract check failed at $($entry.Key). See .dev/$ResultFileName."
        }
    }
}

function Invoke-HybridGovernanceWorkbenchSmokeVerification {
    try {
        Invoke-GovernanceWorkbenchTests
        Start-Hybrid
        Invoke-GovernanceWorkbenchContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

function Invoke-HybridAdminUserManagementSmokeVerification {
    try {
        Invoke-AdminUserManagementTests
        Start-Hybrid
        Invoke-AdminUserManagementContractComparison
        Install-PlaywrightBrowsers
        Push-Location (Join-Path $Root 'web')
        try {
            $env:PLAYWRIGHT_BROWSERS_PATH = $PlaywrightBrowsersPath
            Invoke-NativeCommand -FilePath '.\node_modules\.bin\playwright.CMD' -Arguments @('test', '-c', 'playwright.smoke.config.ts')
        } finally {
            Pop-Location
        }
    } finally {
        Stop-Hybrid
    }
}

switch ($Action) {
    'up' { Start-Hybrid }
    'down' { Stop-Hybrid }
    'status' { Show-Status }
    'verify-labels-smoke' { Invoke-HybridLabelsSmokeVerification }
    'verify-files-smoke' { Invoke-HybridFilesSmokeVerification }
    'verify-detail-smoke' { Invoke-HybridDetailSmokeVerification }
    'verify-search-smoke' { Invoke-HybridSearchSmokeVerification }
    'verify-clawhub-search-smoke' { Invoke-HybridClawHubSearchSmokeVerification }
    'verify-clawhub-resolve-smoke' { Invoke-HybridClawHubResolveSmokeVerification }
    'verify-clawhub-skill-smoke' { Invoke-HybridClawHubSkillSmokeVerification }
    'verify-clawhub-list-smoke' { Invoke-HybridClawHubListSmokeVerification }
    'verify-auth-me-smoke' { Invoke-HybridAuthMeSmokeVerification }
    'verify-auth-detail-smoke' { Invoke-HybridAuthenticatedDetailSmokeVerification }
    'verify-owner-preview-detail-smoke' { Invoke-HybridOwnerPreviewDetailSmokeVerification }
    'verify-owner-preview-version-smoke' { Invoke-HybridOwnerPreviewVersionSmokeVerification }
    'verify-owner-preview-files-smoke' { Invoke-HybridOwnerPreviewFilesSmokeVerification }
    'verify-owner-preview-tag-files-smoke' { Invoke-HybridOwnerPreviewTagFilesSmokeVerification }
    'verify-file-content-smoke' { Invoke-HybridFileContentSmokeVerification }
    'verify-download-smoke' { Invoke-HybridDownloadSmokeVerification }
    'verify-owner-preview-resolve-smoke' { Invoke-HybridOwnerPreviewResolveSmokeVerification }
    'verify-owner-preview-compare-smoke' { Invoke-HybridOwnerPreviewCompareSmokeVerification }
    'verify-publish-foundation-smoke' { Invoke-HybridPublishFoundationSmokeVerification }
    'verify-publish-dry-run-smoke' { Invoke-HybridPublishDryRunSmokeVerification }
    'verify-publish-storage-foundation-smoke' { Invoke-HybridPublishStorageFoundationSmokeVerification }
    'verify-publish-db-foundation-smoke' { Invoke-HybridPublishDbFoundationSmokeVerification }
    'verify-publish-side-effects-foundation-smoke' { Invoke-HybridPublishSideEffectsFoundationSmokeVerification }
    'verify-publish-replacement-foundation-smoke' { Invoke-HybridPublishReplacementFoundationSmokeVerification }
    'verify-publish-transaction-split-smoke' { Invoke-HybridPublishTransactionSplitSmokeVerification }
    'verify-publish-orchestration-foundation-smoke' { Invoke-HybridPublishOrchestrationFoundationSmokeVerification }
    'verify-publish-http-validate-smoke' { Invoke-HybridPublishHttpValidateSmokeVerification }
    'verify-publish-cli-write-direct-smoke' { Invoke-HybridPublishCliWriteDirectSmokeVerification }
    'verify-publish-scanner-handoff-smoke' { Invoke-HybridPublishScannerHandoffSmokeVerification }
    'verify-publish-cli-replacement-lookup-smoke' { Invoke-HybridPublishCliReplacementLookupSmokeVerification }
    'verify-publish-pending-auto-withdraw-smoke' { Invoke-HybridPublishPendingAutoWithdrawSmokeVerification }
    'verify-publish-storage-failure-cleanup-smoke' { Invoke-HybridPublishStorageFailureCleanupSmokeVerification }
    'verify-cli-publish-write-ownership-smoke' { Invoke-HybridCliPublishWriteOwnershipSmokeVerification }
    'verify-portal-publish-write-ownership-smoke' { Invoke-HybridPortalPublishWriteOwnershipSmokeVerification }
    'verify-root-legacy-publish-write-ownership-smoke' { Invoke-HybridRootLegacyPublishWriteOwnershipSmokeVerification }
    'verify-publish-scanner-result-processing-smoke' { Invoke-HybridPublishScannerResultProcessingSmokeVerification }
    'verify-publish-scan-task-worker-boundary-smoke' { Invoke-HybridPublishScanTaskWorkerBoundarySmokeVerification }
    'verify-publish-scan-consumer-runtime-smoke' { Invoke-HybridPublishScanConsumerRuntimeSmokeVerification }
    'verify-publish-scanner-http-client-smoke' { Invoke-HybridPublishScannerHttpClientSmokeVerification }
    'verify-publish-scan-daemon-supervisor-smoke' { Invoke-HybridPublishScanDaemonSupervisorSmokeVerification }
    'verify-review-approve-smoke' { Invoke-HybridReviewApproveSmokeVerification }
    'verify-review-reject-withdraw-smoke' { Invoke-HybridReviewRejectWithdrawSmokeVerification }
    'verify-review-submit-smoke' { Invoke-HybridReviewSubmitSmokeVerification }
    'verify-review-list-smoke' { Invoke-HybridReviewListSmokeVerification }
    'verify-review-detail-smoke' { Invoke-HybridReviewDetailSmokeVerification }
    'verify-review-skill-detail-smoke' { Invoke-HybridReviewSkillDetailSmokeVerification }
    'verify-review-file-smoke' { Invoke-HybridReviewFileSmokeVerification }
    'verify-review-download-smoke' { Invoke-HybridReviewDownloadSmokeVerification }
    'verify-promotion-read-smoke' { Invoke-HybridPromotionReadSmokeVerification }
    'verify-promotion-submit-reject-smoke' { Invoke-HybridPromotionSubmitRejectSmokeVerification }
    'verify-promotion-approve-smoke' { Invoke-HybridPromotionApproveSmokeVerification }
    'verify-skill-lifecycle-archive-smoke' { Invoke-HybridSkillLifecycleArchiveSmokeVerification }
    'verify-skill-version-delete-smoke' { Invoke-HybridSkillVersionDeleteSmokeVerification }
    'verify-skill-version-withdraw-review-smoke' { Invoke-HybridSkillVersionWithdrawReviewSmokeVerification }
    'verify-skill-confirm-publish-smoke' { Invoke-HybridSkillConfirmPublishSmokeVerification }
    'verify-skill-submit-review-smoke' { Invoke-HybridSkillSubmitReviewSmokeVerification }
    'verify-skill-rerelease-smoke' { Invoke-HybridSkillRereleaseSmokeVerification }
    'verify-admin-skill-hide-unhide-smoke' { Invoke-HybridAdminSkillHideUnhideSmokeVerification }
    'verify-admin-version-yank-smoke' { Invoke-HybridAdminVersionYankSmokeVerification }
    'verify-skill-star-smoke' { Invoke-HybridSkillStarSmokeVerification }
    'verify-skill-subscription-smoke' { Invoke-HybridSkillSubscriptionSmokeVerification }
    'verify-skill-rating-smoke' { Invoke-HybridSkillRatingSmokeVerification }
    'verify-my-social-lists-smoke' { Invoke-HybridMySocialListsSmokeVerification }
    'verify-notification-read-smoke' { Invoke-HybridNotificationReadSmokeVerification }
    'verify-notification-preferences-smoke' { Invoke-HybridNotificationPreferencesSmokeVerification }
    'verify-my-skills-smoke' { Invoke-HybridMySkillsSmokeVerification }
    'verify-namespace-read-smoke' { Invoke-HybridNamespaceReadSmokeVerification }
    'verify-namespace-member-read-smoke' { Invoke-HybridNamespaceMemberReadSmokeVerification }
    'verify-namespace-member-mutation-smoke' { Invoke-HybridNamespaceMemberMutationSmokeVerification }
    'verify-namespace-transfer-ownership-smoke' { Invoke-HybridNamespaceTransferOwnershipSmokeVerification }
    'verify-namespace-profile-lifecycle-smoke' { Invoke-HybridNamespaceProfileLifecycleSmokeVerification }
    'verify-admin-label-definition-smoke' { Invoke-HybridAdminLabelDefinitionSmokeVerification }
    'verify-admin-user-management-smoke' { Invoke-HybridAdminUserManagementSmokeVerification }
    'verify-governance-workbench-smoke' { Invoke-HybridGovernanceWorkbenchSmokeVerification }
    'e2e-smoke' { Invoke-HybridE2E -Config 'playwright.smoke.config.ts' }
    'e2e' { Invoke-HybridE2E -Config 'playwright.config.ts' }
}
