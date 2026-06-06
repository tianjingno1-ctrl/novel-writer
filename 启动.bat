@echo off
cd /d "%~dp0"

if exist ".env" goto run
if exist ".evn" goto fix_evn

echo.
echo [ERROR] Missing .env file
echo   1. Copy .env.example to .env
echo   2. Edit .env and paste your API keys
echo   Note: filename must be .env not .evn
echo.
pause
exit /b 1

:fix_evn
echo.
echo [WARN] Found .evn - renaming to .env ...
ren ".evn" ".env"
echo Done.
echo.

:run
python main.py
pause
