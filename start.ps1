# Starts Postgres and Redis (background) + API + UI in this one terminal.
# Stop everything with Ctrl+C.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Starting Postgres and Redis..." -ForegroundColor Cyan
docker compose up -d postgres redis | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "Postgres could not be started."
}

$python = Join-Path $PSScriptRoot "backend\.venv\Scripts\python.exe"
$uvicorn = Join-Path $PSScriptRoot "backend\.venv\Scripts\uvicorn.exe"
if (-not (Test-Path $python) -or -not (Test-Path $uvicorn)) {
    Write-Host "Backend venv missing. Run the first-time setup from README.md." -ForegroundColor Red
    exit 1
}

$envFile = Join-Path $PSScriptRoot "backend\.env"
if (-not (Test-Path $envFile)) {
    Write-Host "backend\.env is missing. Copy backend\.env.example and set SECRET_KEY." -ForegroundColor Red
    exit 1
}

Write-Host "Waiting for Postgres..." -ForegroundColor Cyan
$postgresReady = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    docker compose exec -T postgres pg_isready -U agent -d agent_platform *> $null
    if ($LASTEXITCODE -eq 0) {
        $postgresReady = $true
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $postgresReady) {
    throw "Postgres did not become ready within 30 seconds."
}

Write-Host "Applying database migrations..." -ForegroundColor Cyan
Push-Location (Join-Path $PSScriptRoot "backend")
try {
    & $python -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Database migrations failed."
    }
}
finally {
    Pop-Location
}

Write-Host "Starting API on http://127.0.0.1:8000 ..." -ForegroundColor Cyan
$backendOutLog = Join-Path $PSScriptRoot "backend\uvicorn.stdout.log"
$backendErrorLog = Join-Path $PSScriptRoot "backend\uvicorn.stderr.log"
$backend = Start-Process -PassThru -WindowStyle Hidden `
    -WorkingDirectory (Join-Path $PSScriptRoot "backend") `
    -FilePath $python `
    -ArgumentList @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000") `
    -RedirectStandardOutput $backendOutLog `
    -RedirectStandardError $backendErrorLog

Write-Host "Waiting for API..." -ForegroundColor Cyan
$apiReady = $false
for ($attempt = 1; $attempt -le 30; $attempt++) {
    if ($backend.HasExited) {
        Write-Host "API process exited during startup." -ForegroundColor Red
        if (Test-Path $backendErrorLog) {
            Get-Content $backendErrorLog
        }
        throw "API could not be started."
    }
    try {
        $health = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -TimeoutSec 1
        if ($health.status -eq "ok") {
            $apiReady = $true
            break
        }
    }
    catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $apiReady) {
    if (Test-Path $backendErrorLog) {
        Get-Content $backendErrorLog
    }
    throw "API did not become ready within 30 attempts."
}

Write-Host "Starting UI on http://localhost:5173 ..." -ForegroundColor Cyan
Write-Host "Press Ctrl+C to stop." -ForegroundColor Yellow

try {
    Set-Location (Join-Path $PSScriptRoot "frontend")
    npm run dev
}
finally {
    Write-Host "`nStopping API..." -ForegroundColor Cyan
    if ($backend -and -not $backend.HasExited) {
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
        Get-CimInstance Win32_Process |
            Where-Object { $_.ParentProcessId -eq $backend.Id } |
            ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    }
}
