@echo off
chcp 65001 >nul
title SmartCleaner-AI - Install Dependencies
color 0b
cd /d "%~dp0"

echo ================================================================
echo   🚀 SmartCleaner-AI - تثبيت مكتبات الذكاء الاصطناعي
echo ================================================================
echo.

set "PY_CMD="

if exist "%~dp0runtime\python.exe" set "PY_CMD="%~dp0runtime\python.exe""
if not defined PY_CMD py -3.10 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3.10"
if not defined PY_CMD py -3 -c "import sys" >nul 2>&1 && set "PY_CMD=py -3"
if not defined PY_CMD python -c "import sys; assert 'WindowsApps' not in sys.executable" >nul 2>&1 && set "PY_CMD=python"

if not defined PY_CMD (
    color 0c
    echo [!] لم يتم العثور على بايثون. يرجى تثبيت Python 3.10 أولاً.
    pause
    exit /b 1
)

echo [*] جاري تحديث pip وتثبيت متطلبات requirements.txt...
echo.
%PY_CMD% -m pip install --upgrade pip
%PY_CMD% -m pip install -r requirements.txt

echo.
%PY_CMD% -c "import PySide6, cv2, torch" >nul 2>&1
if %errorlevel% equ 0 (
    color 0a
    echo ================================================================
    echo   ✅ تم تثبيت كافة المكتبات بنجاح! يمكنك الآن تشغيل SmartCleaner.bat
    echo ================================================================
) else (
    color 0c
    echo ================================================================
    echo   ❌ حدث خطأ أثناء التثبيت. يرجى مراجعة الرسائل أعلاه.
    echo ================================================================
)
echo.
pause
