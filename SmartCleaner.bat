@echo off
setlocal enabledelayedexpansion
title SmartCleaner-AI Studio
cd /d "%~dp0"

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
echo   Option 1: Install Python 3.10 automatically via Windows winget.
echo   Option 2: Open the official Python 3.10 download webpage.
echo.
echo ================================================================
set /p choice="Enter option (1 or 2): "

if "!choice!"=="1" (
    echo.
    echo [*] Installing Python 3.10 via winget...
    winget install Python.Python.3.10 --accept-package-agreements --accept-source-agreements
    echo.
    echo [+] Installation finished. Please close this window and run SmartCleaner.bat again!
    pause
    exit /b 0
)

if "!choice!"=="2" (
    start https://www.python.org/downloads/release/python-31011/
    echo [*] Download page opened. Please check 'Add Python to PATH' during installation!
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
