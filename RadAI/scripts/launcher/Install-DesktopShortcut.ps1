# Install-DesktopShortcut.ps1 — create a "RadAI" icon on the Windows desktop.
#
# Run once after cloning the repo:
#     powershell -ExecutionPolicy Bypass -File scripts\launcher\Install-DesktopShortcut.ps1
#
# Produces two desktop shortcuts that point at the launcher scripts via the
# double-clickable .bat wrappers, so no console/ExecutionPolicy friction.

$ErrorActionPreference = 'Stop'

$RepoRoot    = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Desktop     = [Environment]::GetFolderPath('Desktop')
$StartBat    = Join-Path $RepoRoot 'RadAI.bat'
$StopBat     = Join-Path $RepoRoot 'Stop-RadAI.bat'

if (-not (Test-Path $StartBat)) {
    Write-Host "ERROR: $StartBat not found." -ForegroundColor Red
    exit 1
}

$shell = New-Object -ComObject WScript.Shell

function New-Shortcut($lnkPath, $target, $description) {
    $lnk = $shell.CreateShortcut($lnkPath)
    $lnk.TargetPath       = $target
    $lnk.WorkingDirectory = $RepoRoot
    $lnk.Description      = $description
    $lnk.IconLocation     = "$env:SystemRoot\System32\imageres.dll,109"
    $lnk.Save()
}

New-Shortcut (Join-Path $Desktop 'RadAI.lnk')      $StartBat 'Start the RadAI medical imaging stack'
if (Test-Path $StopBat) {
    New-Shortcut (Join-Path $Desktop 'Stop RadAI.lnk') $StopBat  'Stop the RadAI medical imaging stack'
}

Write-Host "Created desktop shortcut: RadAI" -ForegroundColor Green
Write-Host "Double-click it to launch the stack." -ForegroundColor Green
