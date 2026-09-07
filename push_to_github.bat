@echo off
chcp 65001 >nul
title SmartCleaner-AI - GitHub Upload
color 0b
echo ========================================================
echo   🚀 جاري رفع مشروع SmartCleaner-AI إلى GitHub...
echo   المستودع: https://github.com/abdallahashour98/SmartCleaner-AI.git
echo ========================================================
echo.

git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ========================================================
    echo   ✅ تم رفع المشروع بالكامل إلى GitHub بنجاح!
    echo ========================================================
) else (
    echo ========================================================
    echo   ❌ حدث خطأ أو لم يتم إتمام تسجيل الدخول.
    echo ========================================================
)
echo.
pause
