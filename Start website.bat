@echo off
cd /d "%~dp0"
echo Visa tracking website: open http://localhost:8501 on this PC,
echo or http://%COMPUTERNAME%:8501 from other office PCs.
echo Keep this window open while the website is in use.
".venv\Scripts\streamlit.exe" run website.py
pause
