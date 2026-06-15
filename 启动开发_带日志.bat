@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\dev-with-logs.ps1"
echo.
echo Logs: logs\dev\session.log
echo.
pause
