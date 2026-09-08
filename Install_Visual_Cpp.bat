@echo off
title Install Microsoft Visual C++ Redistributable
color 0b
cd /d "%~dp0"

echo ================================================================
echo   Microsoft Visual C++ 2015-2022 Redistributable Installer
echo   Required for PyTorch and AI Models on Windows
echo ================================================================
echo.

if exist "%SystemRoot%\System32\vcruntime140_1.dll" (
    color 0a
    echo [+] Microsoft Visual C++ Redistributable is already installed on this PC!
    echo     (vcruntime140_1.dll found in System32)
    echo.
    pause
    exit /b 0
)

echo [*] Installing Microsoft Visual C++ Redistributable...
winget install Microsoft.VCRedist.2015+.x64 --accept-package-agreements --accept-source-agreements >nul 2>&1

if exist "%SystemRoot%\System32\vcruntime140_1.dll" (
    color 0a
    echo [+] Successfully installed via Windows winget!
    pause
    exit /b 0
)

echo [*] Downloading official VC++ installer from Microsoft...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; (New-Object System.Net.WebClient).DownloadFile('https://aka.ms/vs/17/release/vc_redist.x64.exe', 'vc_redist.exe')"

if exist vc_redist.exe (
    echo [*] Running installer...
    start /wait vc_redist.exe /passive /norestart
    del /f /q vc_redist.exe >nul 2>&1
)

if exist "%SystemRoot%\System32\vcruntime140_1.dll" (
    color 0a
    echo [+] Microsoft Visual C++ Redistributable installed successfully!
) else (
    color 0c
    echo [!] Could not verify installation automatically.
    echo Please download and run manually from:
    echo https://aka.ms/vs/17/release/vc_redist.x64.exe
    start https://aka.ms/vs/17/release/vc_redist.x64.exe
)

echo.
pause
