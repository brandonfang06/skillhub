param(
    [ValidateSet('up', 'down', 'status', 'verify-labels-smoke', 'verify-files-smoke', 'verify-detail-smoke', 'verify-search-smoke', 'verify-clawhub-search-smoke', 'verify-clawhub-resolve-smoke', 'verify-clawhub-skill-smoke', 'verify-clawhub-list-smoke', 'verify-auth-me-smoke', 'verify-auth-detail-smoke', 'verify-owner-preview-detail-smoke', 'verify-owner-preview-version-smoke', 'verify-owner-preview-files-smoke', 'verify-file-content-smoke', 'verify-download-smoke', 'verify-owner-preview-resolve-smoke', 'verify-owner-preview-compare-smoke', 'verify-publish-foundation-smoke', 'verify-publish-dry-run-smoke', 'verify-publish-storage-foundation-smoke', 'verify-publish-db-foundation-smoke', 'verify-publish-side-effects-foundation-smoke', 'verify-publish-replacement-foundation-smoke', 'verify-publish-transaction-split-smoke', 'verify-publish-orchestration-foundation-smoke', 'verify-publish-http-validate-smoke', 'e2e-smoke', 'e2e')]
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
        [string]$Method = 'GET'
    )

    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Method = $Method
        $request.AllowAutoRedirect = $false
        $request.Timeout = 10000
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
        $response = Invoke-WebRequest -Uri $Url -Method $Method -UseBasicParsing -TimeoutSec 10
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
    $zipPath = Join-Path $DevDir 'publish-validate-fixture.zip'
    $fixtureDir = Join-Path $DevDir 'publish-validate-fixture'
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
name: Codex Validate Skill
description: Validate-only fixture
version: 1.0.0
---
# Codex Validate Skill
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
        return [ordered]@{
            status = [int]$response.StatusCode
            body = if ($body) { $body | ConvertFrom-Json } else { $null }
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
        [ordered]@{ name = 'clawHubRootPublish'; path = '/api/v1/skills'; method = 'POST' },
        [ordered]@{ name = 'legacyPublish'; path = '/api/v1/publish'; method = 'POST' },
        [ordered]@{ name = 'portalV1NamespacePublish'; path = '/api/v1/skills/global/publish'; method = 'POST' },
        [ordered]@{ name = 'portalWebNamespacePublish'; path = '/api/web/skills/global/publish'; method = 'POST' },
        [ordered]@{ name = 'cliPublishWrite'; path = '/api/cli/v1/skills/global/publish'; method = 'POST' }
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
        allWriteRoutesRemainJavaOwned = -not [bool]($writeResults | Where-Object { -not $_.proxyMatchesJava })
        comparedFields = @('status', 'code', 'data.valid', 'data.errors', 'data.warnings', 'data.resolvedSlug', 'data.resolvedVersion')
    }

    $resultPath = Join-Path $DevDir $ResultFileName
    $result | ConvertTo-Json -Depth 50 | Set-Content -LiteralPath $resultPath
    $result | ConvertTo-Json -Depth 50

    if (-not $result.validate.javaMatchesPython -or -not $result.validate.pythonMatchesProxy -or -not $result.allWriteRoutesRemainJavaOwned) {
        throw "Publish validate contract check failed. See .dev/$ResultFileName."
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
    'e2e-smoke' { Invoke-HybridE2E -Config 'playwright.smoke.config.ts' }
    'e2e' { Invoke-HybridE2E -Config 'playwright.config.ts' }
}
