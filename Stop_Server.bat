@echo off
title Stop SmartCleaner-AI Server & Ngrok
cd /d "%~dp0"
echo ========================================================
echo   Stopping SmartCleaner-AI Server & Ngrok Tunnel...
echo ========================================================
echo.

taskkill /F /IM ngrok.exe >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000') do taskkill /F /PID %%a >nul 2>&1

echo [+] SmartCleaner Server and Ngrok have been stopped.
timeout /t 2 >nul
