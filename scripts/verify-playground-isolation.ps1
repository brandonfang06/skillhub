$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot
$previousSecret = $env:SKILLHUB_PLAYGROUND_TOKEN_SECRET
$previousEnabled = $env:SKILLHUB_WEB_PLAYGROUND_ENABLED
$previousBaseUrl = $env:SKILLHUB_WEB_PLAYGROUND_BASE_URL

function Invoke-Checked {
    param(
        [Parameter(Mandatory = $true)]
        [scriptblock]$Command,
        [Parameter(Mandatory = $true)]
        [string]$Description
    )

    & $Command
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed with exit code $LASTEXITCODE"
    }
}

try {
    $env:SKILLHUB_PLAYGROUND_TOKEN_SECRET = ""
    $env:SKILLHUB_WEB_PLAYGROUND_ENABLED = "false"
    $env:SKILLHUB_WEB_PLAYGROUND_BASE_URL = ""

    Push-Location (Join-Path $repoRoot "server-python")
    try {
        Invoke-Checked -Description "Backend isolation tests" -Command {
            uv run pytest `
                tests/test_health.py `
                tests/test_playground_capability.py `
                tests/test_playground_context.py `
                tests/test_playground_api.py `
                tests/test_skill_detail.py `
                tests/test_skill_file_metadata.py `
                tests/test_skill_file_content.py `
                tests/test_skill_download.py `
                -q
        }
    }
    finally {
        Pop-Location
    }

    Push-Location (Join-Path $repoRoot "web")
    try {
        Invoke-Checked -Description "Frontend isolation tests" -Command {
            corepack pnpm exec vitest run `
                src/api/client.test.ts `
                src/app/content-security-policy.test.ts `
                src/features/playground/api.test.ts `
                src/features/playground/playground-chat.test.tsx `
                src/features/playground/use-playground-session.test.tsx `
                src/features/playground/use-playground.test.ts `
                src/pages/skill-playground.test.tsx `
                src/pages/skill-detail.test.tsx `
                src/app/router.test.ts
        }
        Invoke-Checked -Description "Frontend typecheck" -Command {
            corepack pnpm run typecheck
        }
    }
    finally {
        Pop-Location
    }
}
finally {
    $env:SKILLHUB_PLAYGROUND_TOKEN_SECRET = $previousSecret
    $env:SKILLHUB_WEB_PLAYGROUND_ENABLED = $previousEnabled
    $env:SKILLHUB_WEB_PLAYGROUND_BASE_URL = $previousBaseUrl
}
