@echo off
setlocal enabledelayedexpansion
title SmartCleaner-AI Studio
cd /d "%~dp0"

:: 0. Check if running inside temporary unextracted ZIP
echo "%~dp0" | findstr /i "AppData\\Local\\Temp" >nul
if !errorlevel! equ 0 (
    cls
    color 0c
    echo ================================================================
    echo   [!] ZIP EXTRACTION REQUIRED
    echo ================================================================
    echo.
    echo   You are running SmartCleaner-AI from inside a compressed ZIP!
    echo   Windows cannot run the application properly from inside a ZIP.
    echo.
    echo   Please EXTRACT the ZIP folder first:
    echo   1. Close this window.
    echo   2. Right-click the downloaded ZIP file.
    echo   3. Click "Extract All..." (استخراج الكل).
    echo   4. Open the extracted folder and run SmartCleaner.bat.
    echo.
    echo ================================================================
    pause
    exit /b 1
)

:: 1. Detect Python
set "PYTHON="

if exist "%~dp0runtime\python.exe" (
    set "PYTHON=%~dp0runtime\python.exe"
    goto :check_python
)

py -3.10 --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON=py -3.10"
    goto :check_python
)

py -3 --version >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON=py -3"
    goto :check_python
)

python -c "import sys; assert 'WindowsApps' not in sys.executable" >nul 2>&1
if !errorlevel! equ 0 (
    set "PYTHON=python"
    goto :check_python
)

:: No Python found
cls
color 0c
echo ================================================================
echo   [!] SmartCleaner-AI Launcher Error
echo   Python 3.10+ was not found on this computer.
echo ================================================================
echo.
echo   To run this application, Python 3.10 or newer is required.
echo.
echo   Option 1: Download & Install Python 3.10 automatically.
echo   Option 2: Open the official Python 3.10 download webpage.
echo.
echo ================================================================
set /p choice="Enter option (1 or 2): "

if "!choice!"=="1" (
    echo.
    winget --version >nul 2>&1
    if !errorlevel! equ 0 (
        echo [*] Installing Python 3.10 via Windows winget...
        winget install Python.Python.3.10 --accept-package-agreements --accept-source-agreements
    ) else (
        echo [*] Downloading official Python 3.10.11 installer...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe', 'python_installer.exe')"
        if exist python_installer.exe (
            echo.
            echo [*] Launching Python 3.10 Installer...
            echo ================================================================
            echo   CRITICAL: At the bottom of the installer window,
            echo   make sure to CHECK the box: [x] Add Python to PATH!
            echo ================================================================
            start /wait python_installer.exe
            del /f /q python_installer.exe >nul 2>&1
        ) else (
            echo [!] Automatic download failed. Opening download page in browser...
            start https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
        )
    )
    echo.
    echo [+] Installation step completed.
    echo [*] Please close this window and run SmartCleaner.bat again!
    pause
    exit /b 0
)

if "!choice!"=="2" (
    start https://www.python.org/ftp/python/3.10.11/python-3.10.11-amd64.exe
    echo [*] Download started in browser.
    echo ================================================================
    echo   CRITICAL: During installation, make sure to check:
    echo   [x] Add Python to PATH (at the bottom of the installer)
    echo ================================================================
    pause
    exit /b 0
)

pause
exit /b 1

:check_python
echo [*] Python environment detected: !PYTHON!
echo [*] Starting SmartCleaner-AI launcher...
echo.

!PYTHON! tools\launcher.py

if !errorlevel! neq 0 (
    echo.
    echo ================================================================
    echo   [!] Application stopped with exit code !errorlevel!.
    echo ================================================================
    pause
)
