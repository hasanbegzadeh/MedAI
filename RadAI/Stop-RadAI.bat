@echo off
REM Stop the RadAI stack. Double-click to run.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Stop-RadAI.ps1"
