@echo off
cd /d "%~dp0"

if not exist ".env" (
    echo [ERROR] Missing .env - copy .env.example and add API keys
    pause
    exit /b 1
)

pip show fastapi >nul 2>&1
if errorlevel 1 pip install fastapi uvicorn -i https://pypi.org/simple -q

echo.
echo [开发模式] API 端口 8766 — 与 8765 可同时运行
echo http://127.0.0.1:8766/docs
echo Press Ctrl+C to stop
echo.

set NOVEL_WEB_PORT=8766
python web_app.py
pause
