# Sets up the visa tracking office helper on this PC, from nothing.
#
# Run in PowerShell (as yourself, not as administrator):
#     irm https://raw.githubusercontent.com/hassan-912/tracking/main/setup-helper.ps1 | iex
#
# It: installs Python 3.12 if missing, downloads the program to C:\visa-tracking
# (or updates it, keeping your key file), installs its libraries, asks where the
# key file office_helper.env is, turns on auto start, puts a Desktop shortcut,
# and can start the helper. Safe to run again to update.

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'          # much faster downloads
$Dir     = if ($env:VT_DIR) { $env:VT_DIR } else { 'C:\visa-tracking' }
$Zip     = 'https://github.com/hassan-912/tracking/archive/refs/heads/main.zip'
$Ask     = -not $env:VT_NO_PROMPT                 # (testing switches)
$Links   = -not $env:VT_NO_SHORTCUTS

function Step($n, $text) { Write-Host "`n[$n/7] $text" -ForegroundColor Cyan }
function Ok($text)       { Write-Host "      $text" -ForegroundColor Green }
function Warn($text)     { Write-Host "      $text" -ForegroundColor Yellow }

Write-Host '============================================================'
Write-Host '  Visa tracking - office helper setup'
Write-Host "  Folder: $Dir"
Write-Host '============================================================'

# ---------- 1. Python 3.12 ----------
Step 1 'Python 3.12'
function Find-Python {
    $p = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    if (Test-Path $p) { return $p }
    try { $p = (& py -3.12 -c 'import sys; print(sys.executable)' 2>$null) } catch { $p = $null }
    if ($p -and (Test-Path $p)) { return $p }
    return $null
}
$Python = Find-Python
if (-not $Python) {
    Warn 'Not found - installing with winget (a few minutes)...'
    winget install -e --id Python.Python.3.12 --scope user --accept-package-agreements --accept-source-agreements
    $Python = Find-Python
}
if (-not $Python) { throw 'Python 3.12 could not be installed. Install it from python.org, then run this again.' }
Ok "Found: $Python"

# ---------- 2. The program (download or update) ----------
Step 2 'Downloading the program from GitHub'
$tmp = Join-Path $env:TEMP ('visa-tracking-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory $tmp | Out-Null
Invoke-WebRequest $Zip -OutFile "$tmp\program.zip"
Expand-Archive "$tmp\program.zip" -DestinationPath $tmp -Force
$src = Join-Path $tmp 'tracking-main'
New-Item -ItemType Directory -Force $Dir | Out-Null
# Copy everything over; office_helper.env, .venv and results are not in the download, so they survive updates.
Copy-Item "$src\*" $Dir -Recurse -Force
Remove-Item $tmp -Recurse -Force
Ok "Program is in $Dir"

# ---------- 3. Libraries ----------
Step 3 'Installing libraries (a few minutes the first time)'
$venvPy = Join-Path $Dir '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPy)) { & $Python -m venv (Join-Path $Dir '.venv') }
& $venvPy -m pip install --quiet --disable-pip-version-check --upgrade pip
& $venvPy -m pip install --quiet --disable-pip-version-check -r (Join-Path $Dir 'requirements-helper.txt')
if ($LASTEXITCODE -ne 0) { throw 'Library install failed - check the internet connection and run this again.' }
# Windows Smart App Control checks new files on first use; a second try gets past that check.
$check = 'import playwright.sync_api, PIL, openpyxl'
& $venvPy -c $check 2>$null
if ($LASTEXITCODE -ne 0) { Start-Sleep 3; & $venvPy -c $check }
if ($LASTEXITCODE -ne 0) { throw 'Windows blocked the new libraries on first use - just run this setup again.' }
Ok 'Libraries ready'
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
          "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ }
if ($edge) { Ok 'Microsoft Edge found' } else { Warn 'Microsoft Edge NOT found - install Edge before running checks.' }

# ---------- 4. The key file ----------
Step 4 'Key file (office_helper.env)'
$envFile = Join-Path $Dir 'office_helper.env'
if ($env:VT_ENV_FILE) { Copy-Item $env:VT_ENV_FILE $envFile -Force }
if (-not (Test-Path $envFile)) {
    # Look on USB sticks and other removable drives first.
    $found = Get-CimInstance Win32_LogicalDisk -Filter 'DriveType=2' -ErrorAction SilentlyContinue |
        ForEach-Object { Get-ChildItem "$($_.DeviceID)\" -Filter 'office_helper.env' -Recurse -Depth 2 -ErrorAction SilentlyContinue } |
        Select-Object -First 1
    if ($found) {
        Copy-Item $found.FullName $envFile
        Ok "Copied from $($found.FullName) - you can delete it from the USB stick now."
    } elseif ($Ask) {
        Warn 'Not found on a USB stick. Copy office_helper.env from the old office PC'
        Warn '(USB stick or shared office folder - never email or WhatsApp).'
        while (-not (Test-Path $envFile)) {
            $path = (Read-Host '      Full path of office_helper.env (or press Enter to skip for now)').Trim('"', ' ')
            if (-not $path) { break }
            if (Test-Path $path -PathType Leaf) { Copy-Item $path $envFile } else { Warn "Not found: $path" }
        }
    }
}
if (Test-Path $envFile) { Ok 'Key file in place' } else { Warn "Skipped: put office_helper.env in $Dir before starting." }

# ---------- 5. Auto start + Desktop shortcut ----------
Step 5 'Auto start and Desktop shortcut'
if ($Links) {
    $shell = New-Object -ComObject WScript.Shell
    $bat = Join-Path $Dir 'Start office helper.bat'
    $s = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Startup')) 'Visa tracking office helper.lnk'))
    $s.TargetPath = $bat; $s.WorkingDirectory = $Dir; $s.WindowStyle = 7; $s.Save()
    $s = $shell.CreateShortcut((Join-Path ([Environment]::GetFolderPath('Desktop')) 'Visa tracking helper.lnk'))
    $s.TargetPath = $bat; $s.WorkingDirectory = $Dir
    $s.IconLocation = "$env:SystemRoot\System32\shell32.dll,13"; $s.Save()
    Ok 'Starts by itself when you sign in to Windows; "Visa tracking helper" is on the Desktop'
} else { Warn 'Skipped (test mode)' }

# ---------- 6. Sleep ----------
Step 6 'Keep the PC awake when plugged in'
if ($Ask -and (Read-Host '      Stop this PC sleeping while plugged in? (y/n)') -match '^[yY]') {
    powercfg /change standby-timeout-ac 0
    Ok 'Sleep is off while plugged in (the screen can still turn off)'
} else { Warn 'Left as it is' }

# ---------- 7. Start ----------
Step 7 'Start'
Write-Host '      IMPORTANT: only ONE PC should run the helper. On the old PC, close the helper'
Write-Host '      window and double-click "Disable auto start.bat".'
if ((Test-Path $envFile) -and $Ask -and (Read-Host '      Start the helper now? (y/n)') -match '^[yY]') {
    Start-Process -FilePath (Join-Path $Dir 'Start office helper.bat') -WorkingDirectory $Dir
    Ok 'Started - check the website: Tracking should say the helper is online.'
}
Write-Host "`nSetup finished." -ForegroundColor Green
