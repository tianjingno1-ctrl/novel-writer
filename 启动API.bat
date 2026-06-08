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
echo Starting API server... browser will open /docs
echo http://127.0.0.1:8765/docs
echo Press Ctrl+C to stop
echo.

python web_app.py
pause
