@echo off
title Visa tracking - disable auto start
set "LNK=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\Visa tracking office helper.lnk"
if exist "%LNK%" (
    del "%LNK%"
    echo Auto start is OFF. The helper will no longer start with Windows.
) else (
    echo Auto start was already off.
)
pause
