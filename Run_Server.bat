@echo off
title SmartCleaner-AI Mobile Bridge Server
cd /d "%~dp0"
echo ========================================================
echo   SmartCleaner-AI - Mobile Bridge Server
echo   Connect via Ngrok Tunnel or Local Wi-Fi (LAN)
echo ========================================================
echo.

:: Kill lingering old ngrok & port 8000 processes to avoid port conflicts
taskkill /F /IM ngrok.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1

:: Determine Python command
set "PY_CMD="
if exist "%~dp0runtime\python.exe" (
    set "PY_CMD=%~dp0runtime\python.exe"
) else (
    py -3.10 --version >nul 2>&1
    if %errorlevel% equ 0 (
        set "PY_CMD=py -3.10"
    ) else (
        set "PY_CMD=python"
    )
)

:: Start Python Server with dynamic Ngrok integration
echo [*] Starting SmartCleaner-AI Server & Ngrok Tunnel...
echo.
%PY_CMD% server_api.py --with-ngrok
pause
