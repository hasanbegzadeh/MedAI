# Start-RadAI.ps1 - one-click launcher for the RadAI stack on Windows.
#
# Does everything a user would otherwise type into a terminal:
#   1. Make sure Docker Desktop is running (start it if not).
#   2. Create .env from .env.development on first run.
#   3. docker compose up -d.
#   4. Wait for the backend healthcheck to pass.
#   5. Open https://localhost in the default browser.
#
# Migrations and admin seeding happen automatically inside the backend
# container (see backend/entrypoint.sh), so no 'make migrate' / 'make
# seed-admin' follow-up is needed.
#
# IMPORTANT: this file is pure ASCII. Do not introduce em-dashes or other
# non-ASCII punctuation - Windows PowerShell 5.1 reads BOM-less files as
# ANSI and will corrupt multi-byte UTF-8, which breaks string quoting.

$ErrorActionPreference = 'Continue'

trap {
    Write-Host ""
    Write-Host "FATAL: launcher crashed." -ForegroundColor Red
    Write-Host $_ -ForegroundColor Red
    Write-Host $_.ScriptStackTrace -ForegroundColor DarkRed
    Read-Host "Press Enter to close this window"
    exit 1
}

# Repo root = two levels up from this script (scripts/launcher/ -> RadAI/)
if (-not $PSScriptRoot) {
    Write-Host "ERROR: PSScriptRoot is empty. Run via RadAI.bat or 'powershell -File ...'." -ForegroundColor Red
    Read-Host "Press Enter to close this window"
    exit 1
}
$RepoRoot = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Write-Host "Repo root: $RepoRoot" -ForegroundColor DarkGray
Set-Location $RepoRoot

if (-not (Test-Path (Join-Path $RepoRoot 'docker-compose.yml'))) {
    Write-Host "ERROR: docker-compose.yml not found at $RepoRoot." -ForegroundColor Red
    Write-Host "       The launcher expected to live at REPO\scripts\launcher\Start-RadAI.ps1." -ForegroundColor Red
    Read-Host "Press Enter to close this window"
    exit 1
}

function Write-Step($n, $msg) {
    Write-Host ""
    Write-Host "[$n/5] $msg" -ForegroundColor Cyan
}

function Write-Ok($msg)    { Write-Host "      $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "      $msg" -ForegroundColor Yellow }
function Write-Err2($msg)  { Write-Host "      $msg" -ForegroundColor Red }

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "           RadAI Launcher" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# --- 1. Docker Desktop -------------------------------------------------------
Write-Step 1 "Checking Docker Desktop"

function Test-DockerReady {
    try {
        $null = & docker info --format '{{.ServerVersion}}' 2>$null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

if (Test-DockerReady) {
    Write-Ok "Docker is running."
} else {
    Write-Warn2 "Docker is not running. Attempting to start Docker Desktop..."
    $dockerExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
    if (Test-Path $dockerExe) {
        Start-Process -FilePath $dockerExe | Out-Null
    } else {
        Write-Err2 "Docker Desktop not found at $dockerExe."
        Write-Err2 "Install it from https://www.docker.com/products/docker-desktop/ and re-run."
        Read-Host "Press Enter to exit"
        exit 1
    }

    $deadline = (Get-Date).AddMinutes(3)
    while (-not (Test-DockerReady)) {
        if ((Get-Date) -gt $deadline) {
            Write-Err2 "Docker Desktop did not become ready within 3 minutes."
            Read-Host "Press Enter to exit"
            exit 1
        }
        Start-Sleep -Seconds 2
        Write-Host "." -NoNewline
    }
    Write-Host ""
    Write-Ok "Docker is ready."
}

# --- 2. Configuration --------------------------------------------------------
Write-Step 2 "Checking configuration"

if (-not (Test-Path ".env")) {
    if (Test-Path ".env.development") {
        Copy-Item ".env.development" ".env"
        Write-Ok "Created .env from .env.development."
    } else {
        Write-Err2 "No .env.development template found; cannot bootstrap config."
        Read-Host "Press Enter to exit"
        exit 1
    }
} else {
    Write-Ok ".env already present."
}

# --- 3. Start stack ----------------------------------------------------------
Write-Step 3 "Starting services (first run can take 15+ minutes to build)"

& docker compose up -d
if ($LASTEXITCODE -ne 0) {
    Write-Err2 "docker compose up failed. Run 'docker compose logs' to investigate."
    Read-Host "Press Enter to exit"
    exit 1
}
Write-Ok "Containers started."

# --- 4. Wait for backend healthy --------------------------------------------
Write-Step 4 "Waiting for backend to become healthy"

$deadline = (Get-Date).AddMinutes(5)
$healthy = $false
while ((Get-Date) -lt $deadline) {
    $status = & docker inspect --format '{{.State.Health.Status}}' radai-backend 2>$null
    if ($LASTEXITCODE -eq 0 -and $status -eq 'healthy') {
        $healthy = $true
        break
    }
    Start-Sleep -Seconds 3
    Write-Host "." -NoNewline
}
Write-Host ""

if ($healthy) {
    Write-Ok "Backend is healthy (migrations applied, admin user seeded)."
} else {
    Write-Warn2 "Backend did not report healthy in 5 minutes. Opening anyway;"
    Write-Warn2 "check 'docker compose logs backend' if login fails."
}

# --- 5. Open browser ---------------------------------------------------------
Write-Step 5 "Opening RadAI in your browser"
Start-Process "https://localhost" | Out-Null
Write-Ok "Launched https://localhost"

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  RadAI is running" -ForegroundColor Green
Write-Host "  URL:    https://localhost" -ForegroundColor Green
Write-Host "  Login:  admin / changeme" -ForegroundColor Green
Write-Host "  Stop:   double-click Stop-RadAI.bat" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to close this window"
