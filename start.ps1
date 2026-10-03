# Starts the OrchardVision ground station: database, backend, front end.
# Run from the project folder:   .\start.ps1
# Add -Sitl to also start the ArduPilot software autopilot.
param([switch]$Sitl)

$root = $PSScriptRoot
Set-Location $root

docker info *> $null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Docker Desktop is not running. Start it, wait for it to be ready, then run this again." -ForegroundColor Yellow
    Write-Host "The ground station can fly without the database, but nothing is saved or recorded." -ForegroundColor Yellow
} else {
    docker compose up -d db
    if ($Sitl) { docker compose --profile sitl up -d sitl }
}

Push-Location "$root\backend"
uv sync --quiet
uv run alembic upgrade head
Pop-Location

if (-not (Test-Path "$root\frontend\node_modules")) {
    Push-Location "$root\frontend"; npm install; Pop-Location
}

Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\backend'; uv run uvicorn app.main:app --port 8000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", "Set-Location '$root\frontend'; npm run dev"

Start-Sleep 4
Start-Process "http://localhost:5173"
Write-Host "Ground station: http://localhost:5173   (close the two new windows to stop it)" -ForegroundColor Green
