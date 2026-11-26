@echo off
setlocal
cd /d "%~dp0"
title Visa tracking - install office helper
echo ============================================================
echo   Visa tracking - office helper setup
echo ============================================================
echo.

REM ---- 1. Python 3.12 (installs it with winget if missing) ----
set "PYEXE="
for /f "delims=" %%P in ('py -3.12 -c "import sys; print(sys.executable)" 2^>nul') do set "PYEXE=%%P"
if not defined PYEXE if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if not defined PYEXE (
    echo [1/4] Python 3.12 not found - installing it with winget ...
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    if exist "%LocalAppData%\Programs\Python\Python312\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\Python312\python.exe"
)
if not defined PYEXE (
    echo.
    echo  Could not find or install Python 3.12.
    echo  Install it from python.org ^(tick "Add python.exe to PATH"^), then run this file again.
    pause
    exit /b 1
)
echo [1/4] Python found: %PYEXE%

REM ---- 2. Private Python folder for this program (.venv) ----
if not exist ".venv\Scripts\python.exe" (
    echo [2/4] Creating .venv ...
    "%PYEXE%" -m venv .venv || (echo Could not create .venv & pause & exit /b 1)
) else (
    echo [2/4] .venv already exists
)

REM ---- 3. Libraries the helper needs ----
echo [3/4] Installing libraries ^(a few minutes the first time^) ...
".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
".venv\Scripts\python.exe" -m pip install --quiet -r requirements-helper.txt || (echo Library install failed - check the internet connection & pause & exit /b 1)
REM Windows Smart App Control checks new files on first use; trying twice gets past that check.
".venv\Scripts\python.exe" -c "import playwright.sync_api, PIL, openpyxl" 2>nul || ".venv\Scripts\python.exe" -c "import playwright.sync_api, PIL, openpyxl" || (echo Libraries are installed but Windows blocked them - run this file again & pause & exit /b 1)

REM ---- 4. Checks ----
echo [4/4] Checking Microsoft Edge and the key file ...
set "EDGE_OK="
if exist "%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe" set "EDGE_OK=1"
if exist "%ProgramFiles%\Microsoft\Edge\Application\msedge.exe" set "EDGE_OK=1"
if not defined EDGE_OK echo  WARNING: Microsoft Edge was not found. Install Edge before running checks.

echo.
if exist "office_helper.env" (
    echo  Setup finished. Double-click "Start office helper.bat" to start.
) else (
    echo  Setup finished, but office_helper.env is missing.
    echo  Copy office_helper.env from the old office PC into:
    echo     %CD%
    echo  ^(by USB stick or a shared office folder - not by email or WhatsApp^)
    echo  Then double-click "Start office helper.bat".
)
echo.
pause
