# Builds the frontend plus separate CPU and GPU backend images.
# Neither backend image overwrites the other.
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "Building frontend and CPU backend..." -ForegroundColor Cyan
docker compose build frontend backend
if ($LASTEXITCODE -ne 0) { throw "CPU build failed." }

Write-Host "Building GPU backend..." -ForegroundColor Cyan
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build backend
if ($LASTEXITCODE -ne 0) { throw "GPU build failed." }

Write-Host "Build complete: intern_project-backend-cpu and intern_project-backend-gpu" -ForegroundColor Green
