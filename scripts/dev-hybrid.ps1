param(
    [ValidateSet('up', 'down', 'status', 'e2e-smoke', 'e2e')]
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

$WebUrl = 'http://localhost:3000'
$JavaUrl = 'http://localhost:8080'
$PythonUrl = 'http://localhost:8081'
$ScannerUrl = 'http://localhost:8000'

function Ensure-DevDir {
    New-Item -ItemType Directory -Force -Path $DevDir | Out-Null
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
    Stop-Process -Id $processId -Force -ErrorAction SilentlyContinue
    Remove-Item -Force -LiteralPath $PidFile -ErrorAction SilentlyContinue
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
    $process = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $WorkingDirectory `
        -RedirectStandardOutput $LogFile `
        -RedirectStandardError $errorLogFile `
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

function Invoke-DockerComposeRequired {
    param([string[]]$Arguments)

    if (-not (Test-CommandAvailable -Name 'docker')) {
        throw 'Docker CLI is required for hybrid local dependencies, but docker was not found in PATH.'
    }

    docker @Arguments
}

function Invoke-WebDeps {
    $webDir = Join-Path $Root 'web'
    $corepackHome = 'C:\tmp\corepack'
    New-Item -ItemType Directory -Force -Path $corepackHome | Out-Null
    $env:COREPACK_HOME = $corepackHome
    Push-Location $webDir
    try {
        corepack pnpm install --frozen-lockfile
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
    $env:Path = (Join-Path $javaHome 'bin') + ';' + $env:Path
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
    Push-Location (Join-Path $Root 'web')
    try {
        .\node_modules\.bin\playwright.CMD test -c $Config
    } finally {
        Pop-Location
    }
}

switch ($Action) {
    'up' { Start-Hybrid }
    'down' { Stop-Hybrid }
    'status' { Show-Status }
    'e2e-smoke' { Invoke-HybridE2E -Config 'playwright.smoke.config.ts' }
    'e2e' { Invoke-HybridE2E -Config 'playwright.config.ts' }
}
