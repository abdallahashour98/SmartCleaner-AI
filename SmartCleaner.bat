@echo off
title SmartCleaner-AI
cd /d "%~dp0"

:: 1. Check if embedded/local portable runtime exists
if exist "%~dp0runtime\python.exe" (
    start "" "%~dp0runtime\pythonw.exe" "%~dp0gui_cleaner.py"
    exit
)

:: 2. Check for py -3.10
py -3.10 --version >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw -3.10 "%~dp0gui_cleaner.py"
    exit
)

:: 3. Check for standard python in PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    start "" pythonw "%~dp0gui_cleaner.py"
    exit
)

:: 4. Fallback to py launcher
py --version >nul 2>&1
if %errorlevel% equ 0 (
    start "" pyw "%~dp0gui_cleaner.py"
    exit
)

echo ========================================================
echo   [!] SmartCleaner-AI Launcher Error
echo ========================================================
echo Python 3.10 environment was not found on your system.
echo Please install Python 3.10+ or place embedded Python in runtime/
echo.
echo For troubleshooting, please run: SmartCleaner_Debug.bat
echo ========================================================
pause
