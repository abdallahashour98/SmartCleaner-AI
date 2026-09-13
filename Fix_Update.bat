@echo off
chcp 65001 >nul
title SmartCleaner-AI - Quick Update and Repair Tool
color 0b
cd /d "%~dp0"

echo ===============================================================================
echo            SmartCleaner-AI - اداة التحديث السريع والاصلاح
echo            SmartCleaner-AI - Quick Update and Repair Tool
echo ===============================================================================
echo.

if not exist "%~dp0SmartCleaner.bat" (
    color 0c
    echo [!] خطأ: يجب وضع هذا الملف داخل مجلد SmartCleaner-AI الرئيسي!
    echo [!] Error: Please place Fix_Update.bat inside your main SmartCleaner-AI folder!
    echo.
    echo المسار الحالي / Current path: "%~dp0"
    echo ===============================================================================
    pause
    exit /b 1
)

echo [*] جاري الاتصال بسيرفر التحديثات وتحميل أحدث إصدار...
echo [*] Connecting to update server and downloading latest release...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command "$ProgressPreference = 'SilentlyContinue'; [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; try { $m = Invoke-RestMethod -Uri 'https://raw.githubusercontent.com/abdallahashour98/SmartCleaner-AI-Updata/main/version_manifest.json'; Write-Host ('  [+] اصدار التحديث المتوفر: v' + $m.latest_version); Write-Host '  [*] جاري تنزيل ملفات الباتش...'; Invoke-WebRequest -Uri $m.patch_url -OutFile 'patch_temp.zip'; Write-Host '  [*] جاري تثبيت وتحديث ملفات البرنامج...'; Expand-Archive -Path 'patch_temp.zip' -DestinationPath '.' -Force; Remove-Item 'patch_temp.zip' -Force; Write-Host '  [+] اكتمل التثبيت بنجاح!'; exit 0 } catch { Write-Host ('  [-] حدث خطأ اثناء التحديث: ' + $_.Exception.Message); exit 1 }"

if errorlevel 1 goto :fail

echo.
color 0a
echo ===============================================================================
echo   [OK] تم تحديث البرنامج واصلاح مثبت التحديثات التلقائية بنجاح!
echo   [OK] SmartCleaner-AI updated and auto-updater repaired successfully!
echo ===============================================================================
echo.
echo هل ترغب في فتح البرنامج الان؟ (اضغط Enter للتشغيل)
set "REPLY="
set /p "REPLY=Do you want to launch SmartCleaner-AI now? [Y/n]: "
if /i "%REPLY%"=="n" goto :done

echo [*] جاري تشغيل SmartCleaner-AI...
start "" "%~dp0SmartCleaner.bat"
goto :done

:fail
echo.
color 0c
echo ===============================================================================
echo  [-] فشل التحديث. يرجى التاكد من اتصال الانترنت ومحاولة التشغيل مرة اخرى.
echo  [-] Update failed. Please check your internet connection and try again.
echo ===============================================================================
echo.
pause
exit /b 1

:done
exit /b 0
