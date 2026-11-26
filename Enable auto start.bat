@echo off
cd /d "%~dp0"
title Visa tracking - enable auto start
REM Puts a shortcut to "Start office helper.bat" in this Windows user's Startup folder,
REM so the helper starts (minimised) every time this user signs in to Windows.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$lnk = Join-Path ([Environment]::GetFolderPath('Startup')) 'Visa tracking office helper.lnk';" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($lnk);" ^
  "$s.TargetPath = (Join-Path (Get-Location) 'Start office helper.bat');" ^
  "$s.WorkingDirectory = (Get-Location).Path;" ^
  "$s.WindowStyle = 7;" ^
  "$s.Description = 'Visa tracking office helper';" ^
  "$s.Save();" ^
  "Write-Host ('Auto start is ON. Shortcut: ' + $lnk)"
echo.
echo The helper will now start by itself (minimised) when you sign in to Windows.
echo To turn this off, double-click "Disable auto start.bat".
pause
