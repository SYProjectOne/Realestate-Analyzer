# Starts API, worker and the frontend dev server, then opens the browser.
# Settings come from the repo-root .env (ENV_FILE). Values are never printed.
$ErrorActionPreference = 'Stop'
$Root = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Frontend = Join-Path $Root 'frontend'
$EnvFile = Join-Path $Root '.env'

$ApiPort = '8000'
if (Test-Path $EnvFile) {
    # Local GUI signs in automatically: the dev server (localhost only) inherits API_TOKEN as VITE_API_TOKEN.
    $tok = Get-Content $EnvFile | Where-Object { $_ -match '^\s*API_TOKEN\s*=' } | Select-Object -First 1
    if ($tok) { $env:VITE_API_TOKEN = ($tok -replace '^\s*API_TOKEN\s*=\s*', '').Trim().Trim('"').Trim("'") }
    $line = Get-Content $EnvFile | Where-Object { $_ -match '^\s*API_PORT\s*=\s*(\d+)\s*$' } | Select-Object -First 1
    if ($line -match '(\d+)\s*$') { $ApiPort = $Matches[1] }
}

$api = "`$env:ENV_FILE='$EnvFile'; Set-Location '$Backend'; uv run alembic upgrade head; uv run python -m app.serve"
$worker = "`$env:ENV_FILE='$EnvFile'; Set-Location '$Backend'; uv run python -m app.worker"
$Marker = Join-Path $Frontend 'node_modules\.package-lock.json'
$Lock = Join-Path $Frontend 'package-lock.json'
$Install = ''
if (-not (Test-Path $Marker) -or (Get-Item $Lock).LastWriteTime -gt (Get-Item $Marker).LastWriteTime) { $Install = 'npm ci; ' }
$web = "`$env:API_PROXY_TARGET='http://localhost:$ApiPort'; Set-Location '$Frontend'; ${Install}npm run dev"

Start-Process powershell -ArgumentList '-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='Subscription Analyzer - API'; $api"
Start-Sleep -Seconds 3
Start-Process powershell -ArgumentList '-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='Subscription Analyzer - worker'; $worker"
Start-Process powershell -ArgumentList '-NoExit', '-Command', "`$Host.UI.RawUI.WindowTitle='Subscription Analyzer - web'; $web"

Write-Host 'Waiting for API...'
$deadline = (Get-Date).AddSeconds(120)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest "http://127.0.0.1:$ApiPort/health" -UseBasicParsing -TimeoutSec 2 | Out-Null
        break
    } catch { Start-Sleep -Seconds 2 }
}
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    try {
        Invoke-WebRequest 'http://localhost:5173' -UseBasicParsing -TimeoutSec 2 | Out-Null
        break
    } catch { Start-Sleep -Seconds 2 }
}
Start-Process 'http://localhost:5173'
