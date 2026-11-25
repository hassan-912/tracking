@echo off
cd /d "%~dp0"
title Visa tracking - office helper
echo Office helper for the online visa tracking website.
echo Keep this window open: it opens the CAPTCHA windows when someone presses Check.
".venv\Scripts\python.exe" office_helper.py
pause
