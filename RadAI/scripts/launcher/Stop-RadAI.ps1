# Stop-RadAI.ps1 - shut down the RadAI stack from a single click.
$ErrorActionPreference = 'Continue'

$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $RepoRoot

Write-Host ""
Write-Host "Stopping RadAI services..." -ForegroundColor Yellow
& docker compose down
if ($LASTEXITCODE -eq 0) {
    Write-Host "Stopped. Data volumes preserved." -ForegroundColor Green
} else {
    Write-Host "docker compose down returned non-zero exit code." -ForegroundColor Red
}
Start-Sleep -Seconds 2
