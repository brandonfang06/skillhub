param(
    [ValidateSet('up', 'down', 'status', 'verify-labels-smoke', 'verify-files-smoke', 'e2e-smoke', 'e2e')]
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

switch ($Action) {
    'up' { Start-Hybrid }
    'down' { Stop-Hybrid }
    'status' { Show-Status }
    'verify-labels-smoke' { Invoke-HybridLabelsSmokeVerification }
    'verify-files-smoke' { Invoke-HybridFilesSmokeVerification }
    'e2e-smoke' { Invoke-HybridE2E -Config 'playwright.smoke.config.ts' }
    'e2e' { Invoke-HybridE2E -Config 'playwright.config.ts' }
}
