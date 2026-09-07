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

:: Start Python Server with dynamic Ngrok integration
echo [*] Starting SmartCleaner-AI Server & Ngrok Tunnel...
echo.
py -3.10 server_api.py --with-ngrok
pause
