@echo off
setlocal enabledelayedexpansion
title SmartCleaner-AI - Install Dependencies
color 0b
cd /d "%~dp0"

echo ================================================================
echo   SmartCleaner-AI - Install AI Dependencies
echo ================================================================
echo.

set "PYTHON="

if exist "%~dp0runtime\python.exe" set "PYTHON=%~dp0runtime\python.exe"
if not defined PYTHON py -3.10 --version >nul 2>&1 && set "PYTHON=py -3.10"
if not defined PYTHON py -3 --version >nul 2>&1 && set "PYTHON=py -3"
if not defined PYTHON python -c "import sys; assert 'WindowsApps' not in sys.executable" >nul 2>&1 && set "PYTHON=python"

if not defined PYTHON (
    color 0c
    echo [ERROR] Python 3.10 was not found on this system.
    echo Please install Python 3.10 from https://www.python.org/
    echo (Make sure to check 'Add Python to PATH' during installation!)
    echo.
    pause
    exit /b 1
)

echo [*] Using Python: !PYTHON!
echo [*] Upgrading pip...
!PYTHON! -m pip install --upgrade pip

echo.
echo [*] Installing requirements from requirements.txt...
!PYTHON! -m pip install -r requirements.txt

echo.
!PYTHON! -c "import PySide6, cv2, torch" >nul 2>&1
if !errorlevel! equ 0 (
    color 0a
    echo ================================================================
    echo   [SUCCESS] All dependencies installed successfully!
    echo   You can now run SmartCleaner.bat to start the app.
    echo ================================================================
) else (
    color 0c
    echo ================================================================
    echo   [FAILED] Some dependencies could not be installed.
    echo   Please check your internet connection and try again.
    echo ================================================================
)
echo.
pause
