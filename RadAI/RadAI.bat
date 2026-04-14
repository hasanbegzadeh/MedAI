@echo off
REM RadAI launcher — double-click this file (or the desktop shortcut it
REM creates) to start the full stack. Opens a console so you can see
REM progress; closes when you press Enter at the end.
setlocal
cd /d "%~dp0"
echo Launching RadAI from %CD%
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\launcher\Start-RadAI.ps1"
set RC=%ERRORLEVEL%
echo.
echo Launcher exited with code %RC%.
pause
endlocal
