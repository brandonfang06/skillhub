param(
    [ValidateSet('up', 'down', 'status', 'verify-labels-smoke', 'verify-files-smoke', 'verify-detail-smoke', 'verify-search-smoke', 'verify-clawhub-search-smoke', 'verify-clawhub-resolve-smoke', 'verify-clawhub-skill-smoke', 'e2e-smoke', 'e2e')]
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
    'e2e-smoke' { Invoke-HybridE2E -Config 'playwright.smoke.config.ts' }
    'e2e' { Invoke-HybridE2E -Config 'playwright.config.ts' }
}
