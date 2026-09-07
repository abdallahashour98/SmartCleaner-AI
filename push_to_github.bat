@echo off
title SmartCleaner-AI - GitHub Upload
color 0b
echo ========================================================
echo   Uploading SmartCleaner-AI to GitHub...
echo   Target: https://github.com/abdallahashour98/SmartCleaner-AI.git
echo ========================================================
echo.

git push -u origin main

echo.
if %errorlevel% equ 0 (
    echo ========================================================
    echo   [SUCCESS] Code pushed to GitHub successfully!
    echo ========================================================
) else (
    echo ========================================================
    echo   [FAILED] Push failed. Check your login credentials above.
    echo ========================================================
)
echo.
pause
