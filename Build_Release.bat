@echo off
setlocal enabledelayedexpansion
title SmartCleaner-AI - Build Release Packages
color 0b
cd /d "%~dp0"

echo ================================================================
echo   SmartCleaner-AI - Master Release Packaging System
echo ================================================================
echo.

set "PYTHON="

if exist "%~dp0runtime\python.exe" set "PYTHON=%~dp0runtime\python.exe"
if not defined PYTHON py -3.10 --version >nul 2>&1 && set "PYTHON=py -3.10"
if not defined PYTHON py -3 --version >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON python -c "import sys; assert 'WindowsApps' not in sys.executable" >nul 2>&1 && set "PYTHON=python"

if not defined PYTHON (
    color 0c
    echo [ERROR] Python 3.10+ was not found on this system.
    echo Please install Python 3.10 from https://www.python.org/
    echo.
    pause
    exit /b 1
)

echo [*] Using Python: !PYTHON!
echo [*] Starting build process...
echo.

!PYTHON! tools\package_enduser_release.py %*

if !errorlevel! equ 0 (
    echo.
    echo [+] Build finished successfully! Check the dist\ folder.
) else (
    color 0c
    echo.
    echo [!] Build finished with errors (Exit Code: !errorlevel!).
)

echo.
pause
