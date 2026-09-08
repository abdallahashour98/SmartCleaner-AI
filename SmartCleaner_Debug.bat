@echo off
title SmartCleaner-AI (Debug & Diagnostic Console)
cd /d "%~dp0"

echo ========================================================
echo   SmartCleaner-AI - Debug Mode Console
echo ========================================================
echo.
set "PYTHONPATH=%~dp0;%PYTHONPATH%"

:: 1. Check if embedded/local runtime exists
if exist "%~dp0runtime\python.exe" (
    echo [*] Using local portable Python: %~dp0runtime\python.exe
    "%~dp0runtime\python.exe" tools\check_environment.py
    echo.
    echo [*] Starting GUI...
    "%~dp0runtime\python.exe" gui_cleaner.py
    goto :end
)

:: 2. Check for py -3.10
py -3.10 --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Using Python 3.10 Launcher (py -3.10)...
    py -3.10 tools\check_environment.py
    echo.
    echo [*] Starting GUI...
    py -3.10 gui_cleaner.py
    goto :end
)

:: 3. Check for standard python in PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    echo [*] Using System Python...
    python tools\check_environment.py
    echo.
    echo [*] Starting GUI...
    python gui_cleaner.py
    goto :end
)

echo [!] Error: No compatible Python environment found.
echo Please install Python 3.10 (with Add to PATH checked).

:end
echo.
echo ========================================================
echo   Process finished.
echo ========================================================
pause
