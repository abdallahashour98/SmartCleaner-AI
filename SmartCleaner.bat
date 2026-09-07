@echo off
chcp 65001 >nul
title SmartCleaner-AI Studio
cd /d "%~dp0"

set "PY_CMD="

:: 1. Check local portable runtime
if exist "%~dp0runtime\python.exe" (
    set "PY_CMD="%~dp0runtime\python.exe""
    goto :found_python
)

:: 2. Check py -3.10 launcher
py -3.10 -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py -3.10"
    goto :found_python
)

:: 3. Check py -3 launcher
py -3 -c "import sys" >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=py -3"
    goto :found_python
)

:: 4. Check system python (ensuring it's not the WindowsApps dummy stub)
python -c "import sys; assert 'WindowsApps' not in sys.executable" >nul 2>&1
if %errorlevel% equ 0 (
    set "PY_CMD=python"
    goto :found_python
)

:: If no Python was found at all:
:python_missing
cls
color 0c
echo ================================================================
echo   [!] SmartCleaner-AI - لم يتم العثور على بايثون (Python 3.10)
echo ================================================================
echo.
echo   لتشغيل استوديو SmartCleaner-AI، يجب توفر Python 3.10+ على جهازك.
echo.
echo   [1] اضغط 1 لتثبيت Python 3.10 تلقائياً عبر ويندوز (winget).
echo   [2] اضغط 2 لفتح صفحة تحميل Python 3.10 الرسمية في المتصفح.
echo   [3] اضغط 3 للخروج.
echo.
echo ================================================================
set /p user_choice="اختر رقم (1 أو 2 أو 3): "

if "%user_choice%"=="1" (
    echo.
    echo [*] جاري محاولة تثبيت Python 3.10 عبر winget...
    winget install Python.Python.3.10 --accept-package-agreements --accept-source-agreements
    echo.
    echo [+] تم التثبيت. يرجى إغلاق هذه النافذة وإعادة تشغيل البرنامج!
    pause
    exit
)
if "%user_choice%"=="2" (
    start https://www.python.org/downloads/release/python-31011/
    echo [*] تم فتح صفحة التحميل. تأكد من تفعيل خيار (Add Python to PATH) أثناء التثبيت!
    pause
    exit
)
exit

:found_python
:: Check if PySide6 and core libs are installed
%PY_CMD% -c "import PySide6, cv2, torch" >nul 2>&1
if %errorlevel% equ 0 (
    :: Everything is installed! Launch GUI
    start "" %PY_CMD% gui_cleaner.py
    exit
)

:: If PySide6 or dependencies are missing:
cls
color 0e
echo ================================================================
echo   ⚡ SmartCleaner-AI - تهيئة مكتبات الذكاء الاصطناعي لأول مرة
echo ================================================================
echo.
echo   تم العثور على Python، ولكن مكتبات التطبيق الأساسية غير مثبتة بعد.
echo   جاري تثبيت المكتبات المطلوبة تلقائياً من requirements.txt...
echo   (هذه العملية تتم مرة واحدة فقط وتستغرق دقيقة إلى دقيقتين)
echo.
echo ================================================================
echo.

%PY_CMD% -m pip install --upgrade pip
%PY_CMD% -m pip install -r requirements.txt

echo.
%PY_CMD% -c "import PySide6" >nul 2>&1
if %errorlevel% equ 0 (
    echo ================================================================
    echo   ✅ تم تثبيت كافة المكتبات بنجاح! جاري إطلاق البرنامج...
    echo ================================================================
    timeout /t 2 >nul
    start "" %PY_CMD% gui_cleaner.py
    exit
) else (
    color 0c
    echo ================================================================
    echo   ❌ حدث خطأ أثناء تثبيت المكتبات.
    echo   يرجى التحقق من اتصالك بالإنترنت وتشغيل SmartCleaner_Debug.bat
    echo ================================================================
    pause
    exit
)
