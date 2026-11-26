@echo off
cd /d "%~dp0"
title Visa tracking - office helper
if not exist ".venv\Scripts\python.exe" (
    echo Not installed yet: double-click "Install office helper.bat" first.
    pause
    exit /b 1
)
if not exist "office_helper.env" (
    echo office_helper.env is missing: copy it here from the old office PC.
    pause
    exit /b 1
)
echo Office helper for the online visa tracking website.
echo Keep this window open ^(minimised is fine^): it opens the CAPTCHA windows when someone presses Check.
echo To stop it, close this window.
echo.
:run
".venv\Scripts\python.exe" office_helper.py
if errorlevel 3 if not errorlevel 4 exit /b 0
echo.
echo The helper stopped. Restarting in 15 seconds - close this window to stop it for good.
timeout /t 15 /nobreak >nul
goto run
