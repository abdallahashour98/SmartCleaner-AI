@echo off
title SmartCleaner-AI - Quick Update and Repair Tool
color 0b
cd /d "%~dp0"

echo ===============================================================================
echo            SmartCleaner-AI - Quick Update and Repair Tool
echo ===============================================================================
echo.

if not exist "%~dp0SmartCleaner.bat" (
    color 0c
    echo [!] Error: Please place Fix_Update.bat inside your main SmartCleaner-AI folder!
    echo [!] Current path: "%~dp0"
    echo ===============================================================================
    pause
    exit /b 1
)

echo [*] Connecting to update server and downloading latest patch...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $m = Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/abdallahashour98/SmartCleaner-AI-Updata/main/version_manifest.json'; Write-Host ('[+] Found latest version: v' + $m.latest_version); Write-Host '[*] Downloading patch package...'; Invoke-WebRequest -Uri $m.patch_url -OutFile 'patch_temp.zip'; Write-Host '[*] Extracting and updating files...'; Add-Type -AssemblyName System.IO.Compression.FileSystem; $zip = [System.IO.Compression.ZipFile]::OpenRead('patch_temp.zip'); foreach ($entry in $zip.Entries) { if ($entry.Name -ne 'Fix_Update.bat' -and -not [string]::IsNullOrEmpty($entry.Name)) { $dest = [System.IO.Path]::Combine((Get-Location).Path, $entry.FullName); $dir = [System.IO.Path]::GetDirectoryName($dest); if (-not [System.IO.Directory]::Exists($dir)) { [System.IO.Directory]::CreateDirectory($dir) | Out-Null }; [System.IO.Compression.ZipFileExtensions]::ExtractToFile($entry, $dest, $true); } }; $zip.Dispose(); Remove-Item 'patch_temp.zip' -Force; Write-Host '[+] Successfully updated to latest version!'; exit 0; } catch { Write-Host ('[-] Update failed: ' + $_.Exception.Message); exit 1; }"

if errorlevel 1 goto :fail

echo.
color 0a
echo ===============================================================================
echo   [OK] SmartCleaner-AI updated and auto-updater repaired successfully!
echo ===============================================================================
echo.
set "REPLY="
set /p "REPLY=Do you want to launch SmartCleaner-AI now? [Y/n]: "
if /i "%REPLY%"=="n" goto :done

echo [*] Launching SmartCleaner-AI...
start "" "%~dp0SmartCleaner.bat"
goto :done

:fail
echo.
color 0c
echo ===============================================================================
echo  [-] Update failed. Please check your internet connection and try again.
echo ===============================================================================
echo.
pause
exit /b 1

:done
exit /b 0
