"""Builds docs/Office helper setup guide.pdf from the HTML below (uses Edge via Playwright).

    .venv\\Scripts\\python docs\\make_guide.py
"""
from pathlib import Path

from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SITE = "https://visa-tracking-eight.vercel.app"
REPO_ZIP = "https://github.com/hassan-912/tracking/archive/refs/heads/main.zip"


def cmd(*lines: str) -> str:
    return "<pre>" + "\n".join(lines) + "</pre>"


STEPS = [
    ("Before you start", f"""
<p>The <b>office helper</b> is a small program that runs on one office PC. When someone presses
<b>Check</b> on the website (<b>{SITE}</b>), the helper opens the visa-site windows on that PC,
fills in the logins, waits for staff to solve the CAPTCHAs, then sends the statuses and the
screenshots PDF back to the website.</p>
<h3>You need</h3>
<ul class="check">
  <li>A <b>Windows 10 or 11</b> PC with internet, that can stay on during work hours</li>
  <li><b>Microsoft Edge</b> (already on every Windows PC)</li>
  <li>The file <b>office_helper.env</b> from the current office PC, on a <b>USB stick</b>
      or in a shared office folder (it is the helper's secret key: never email or WhatsApp it)</li>
  <li>About <b>15 minutes</b></li>
</ul>
<h3>The steps</h3>
<p><b>Quickest:</b> the next page has <b>one command</b> that does all of this.</p>
<ol>
  <li>Install Python</li><li>Download the program</li><li>Install the helper</li>
  <li>Copy the key file</li><li>Stop the helper on the old PC</li><li>Start the helper</li>
  <li>Start automatically with the PC</li><li>Keep the PC awake</li>
</ol>
<h3>How to open the terminal (PowerShell)</h3>
<p>Press the <b>Windows key</b>, type <b>PowerShell</b>, press <b>Enter</b>. Copy each grey box
below into it and press <b>Enter</b>. Wait until each command finishes before the next one.</p>
"""),
    ("Fast way — one command does everything", """
<p>Instead of Steps 1–8 one by one, this single command does all of them. First put
<b>office_helper.env</b> on a <b>USB stick</b> and plug it in (the setup finds it there).</p>
<p>Open <b>PowerShell</b> (Windows key → type PowerShell → Enter) and paste this as <b>one line</b>:</p>
""" + cmd('irm https://raw.githubusercontent.com/hassan-912/tracking/main/setup-helper.ps1 '
          '-OutFile "$env:TEMP\\setup-helper.ps1"; powershell -ExecutionPolicy Bypass '
          '-File "$env:TEMP\\setup-helper.ps1"') + """
<p>It will:</p>
<ol>
  <li>install <b>Python 3.12</b> if it is missing</li>
  <li>download the program into <b>C:\\visa-tracking</b> (or update it, keeping the key file)</li>
  <li>install the libraries</li>
  <li>copy <b>office_helper.env</b> from the USB stick — or ask you where it is</li>
  <li>turn on <b>auto start</b> and put <b>Visa tracking helper</b> on the Desktop</li>
  <li>ask: <i>stop this PC sleeping while plugged in?</i> — answer <b>y</b></li>
  <li>ask: <i>start the helper now?</i> — answer <b>y</b></li>
</ol>
<p class="ok">It ends with <i>Setup finished</i>. The website's Tracking page should then say
<b>Office PC helper is online (&lt;this PC's name&gt;)</b>.</p>
<div class="warn">Then on the <b>old PC</b>: close the helper window and double-click
<b>Disable auto start.bat</b> — only one PC should run the helper.</div>
<div class="note"><b>Updating later:</b> run the same command again. It keeps the key file and settings.
<br><b>If anything fails:</b> run it again, or follow Steps 1–8 on the next pages.</div>
"""),
    ("Step 1 — Install Python", """
<p>Python runs the helper. Install version <b>3.12</b> with one command:</p>
""" + cmd("winget install -e --id Python.Python.3.12 --scope user") + """
<p>If it asks to accept the source agreement, type <b>Y</b> and press Enter.
When it says <i>Successfully installed</i>, <b>close PowerShell and open it again</b>
(so Windows notices Python).</p>
<p>Check it worked:</p>
""" + cmd("py -3.12 --version") + """
<p class="ok">You should see: <code>Python 3.12.x</code></p>
<div class="note"><b>No winget?</b> Download Python 3.12 from <b>python.org/downloads</b>,
run it, and on the first screen <b>tick “Add python.exe to PATH”</b>, then Install Now.</div>
"""),
    ("Step 2 — Download the program", """
<p>These commands download the program from GitHub and put it in <b>C:\\visa-tracking</b>:</p>
""" + cmd(f'Invoke-WebRequest "{REPO_ZIP}" -OutFile "$env:TEMP\\visa-tracking.zip"',
          'Expand-Archive "$env:TEMP\\visa-tracking.zip" -DestinationPath "C:\\" -Force',
          'Rename-Item "C:\\tracking-main" "visa-tracking"',
          'cd C:\\visa-tracking') + """
<p class="ok">Check: <code>dir</code> should list <b>Install office helper.bat</b>,
<b>Start office helper.bat</b> and <b>office_helper.py</b>.</p>
<div class="note"><b>Updating later?</b> Close the helper, delete <b>C:\\visa-tracking</b>
(keep a copy of <b>office_helper.env</b>!), run these commands again, put
<b>office_helper.env</b> back, then do Step 3 again.</div>
<div class="note"><b>Without the terminal:</b> open github.com/hassan-912/tracking →
green <b>Code</b> button → <b>Download ZIP</b> → unzip to <b>C:\\visa-tracking</b>.</div>
"""),
    ("Step 3 — Install the helper", """
<p>In the same PowerShell window (inside <b>C:\\visa-tracking</b>):</p>
""" + cmd('& ".\\Install office helper.bat"') + """
<p>Or double-click <b>Install office helper.bat</b> in the folder. It:</p>
<ol>
  <li>finds Python 3.12 (and installs it with winget if it is missing)</li>
  <li>creates the program's own Python folder <b>.venv</b></li>
  <li>downloads the libraries it needs (a few minutes the first time)</li>
  <li>checks that Edge and the key file are there</li>
</ol>
<p class="ok">It ends with <i>Setup finished</i>. Press any key to close it.</p>
<div class="note"><b>“An Application Control policy has blocked this file”</b> — Windows checks
new files the first time they run. Just run <b>Install office helper.bat</b> again.</div>
"""),
    ("Step 4 — Copy the key file", """
<p>The key file lets this PC run checks for your website. It is <b>not</b> on GitHub on purpose.</p>
<ol>
  <li>On the <b>old office PC</b>, find <b>office_helper.env</b> in the program folder
      (for example <b>C:\\Users\\Menna\\Documents\\test tracking</b>).</li>
  <li>Copy it to a <b>USB stick</b> or a shared office folder.</li>
  <li>On the <b>new PC</b>, paste it into <b>C:\\visa-tracking</b>.</li>
</ol>
<p>Check it is in the right place:</p>
""" + cmd('Test-Path "C:\\visa-tracking\\office_helper.env"') + """
<p class="ok">You should see: <code>True</code></p>
<div class="warn"><b>Keep it private.</b> Anyone with this file can run checks for your
website. Don't email it, don't send it on WhatsApp, and delete it from the USB stick afterwards.</div>
"""),
    ("Step 5 — Stop the helper on the old PC", """
<p>Only <b>one PC</b> should run the helper at a time. If two PCs run it, the CAPTCHA windows
could open on the wrong computer.</p>
<p>On the <b>old PC</b>:</p>
<ol>
  <li>Close the black window <b>“Visa tracking - office helper”</b>.</li>
  <li>If auto start was on there, double-click <b>Disable auto start.bat</b> in its program folder.</li>
</ol>
"""),
    ("Step 6 — Start the helper", """
<p>On the <b>new PC</b>:</p>
""" + cmd('& ".\\Start office helper.bat"') + """
<p>Or double-click <b>Start office helper.bat</b>. A black window opens and shows:</p>
<pre class="screen">Office helper running on &lt;PC name&gt; for """ + SITE + """
Keep this window open. Ctrl+C to stop.</pre>
<p>Now open the website, sign in, and go to <b>Tracking</b>. Within a few seconds you should see:</p>
<p class="pill">● Office PC helper is online (&lt;PC name&gt;)</p>
<ul>
  <li><b>Keep the black window open</b> (minimised is fine). Closing it stops the helper.</li>
  <li>If the helper stops by itself, the window restarts it after 15 seconds.</li>
  <li>CAPTCHA windows open <b>on this PC</b> — someone has to be here to solve them.</li>
</ul>
"""),
    ("Step 7 — Start automatically with the PC", """
<p>So nobody has to remember to start it:</p>
""" + cmd('& ".\\Enable auto start.bat"') + """
<p>Or double-click <b>Enable auto start.bat</b>. From now on the helper starts by itself
(minimised) every time this Windows user signs in.</p>
<p class="ok">Check: press <b>Windows + R</b>, type <b>shell:startup</b>, Enter. You should see
<b>Visa tracking office helper</b> in that folder.</p>
<h3>To turn it off</h3>
""" + cmd('& ".\\Disable auto start.bat"') + """
<div class="note"><b>Doing it by hand instead:</b> press <b>Windows + R</b>, type
<b>shell:startup</b>, Enter. Right-click <b>Start office helper.bat</b> in C:\\visa-tracking →
<b>Show more options</b> → <b>Create shortcut</b>, and move that shortcut into the Startup folder.</div>
<div class="note">Auto start works when someone <b>signs in</b> to Windows. Set the PC to sign in
to this user (or sign in each morning).</div>
"""),
    ("Step 8 — Keep the PC awake", """
<p>If the PC goes to sleep, the website shows the helper as offline. To stop it sleeping while
plugged in:</p>
""" + cmd("powercfg /change standby-timeout-ac 0") + """
<p>The screen can still turn off — that's fine. To let it sleep again after 30 minutes:</p>
""" + cmd("powercfg /change standby-timeout-ac 30") + """
<div class="note"><b>Without the terminal:</b> Settings → System → Power →
<b>Screen and sleep</b> → “When plugged in, put my device to sleep after” → <b>Never</b>.</div>
"""),
    ("If something goes wrong", f"""
<table>
  <tr><th>You see</th><th>Do this</th></tr>
  <tr><td>Website says <b>helper is offline</b></td>
      <td>Is the black window open on the office PC? Is the PC awake and online? Start
      <b>Start office helper.bat</b>.</td></tr>
  <tr><td><i>office_helper.env is missing</i></td><td>Do Step 4.</td></tr>
  <tr><td><i>Not installed yet</i></td><td>Do Step 3.</td></tr>
  <tr><td><i>Application Control policy has blocked this file</i></td>
      <td>Windows is checking new files — run the same thing again.</td></tr>
  <tr><td><i>website not reachable … retrying</i></td>
      <td>Internet problem. It keeps retrying by itself.</td></tr>
  <tr><td><i>Website answered 401</i></td>
      <td>The key file is wrong or old — copy <b>office_helper.env</b> again from the PC that
      worked.</td></tr>
  <tr><td>CAPTCHA windows don't appear</td>
      <td>They open on the PC running the helper — check that PC (and that only one PC runs it).</td></tr>
</table>
<p class="small">Website: {SITE} · Program: github.com/hassan-912/tracking</p>
"""),
]

CSS = """
@page { size: A4; margin: 18mm 16mm; }
body { font-family: 'Segoe UI', Tahoma, sans-serif; color: #1d2433; font-size: 12.5pt; line-height: 1.45; }
section { page-break-after: always; }
section:last-child { page-break-after: auto; }
.cover { border-bottom: 3px solid #1f5fad; margin-bottom: 18px; padding-bottom: 8px; }
.cover h1 { margin: 0; color: #1f5fad; font-size: 24pt; }
.cover p { margin: 4px 0 0; color: #667085; }
h2 { color: #1f5fad; font-size: 19pt; margin: 0 0 12px; border-bottom: 2px solid #e4e7ec; padding-bottom: 6px; }
h3 { font-size: 13pt; margin: 18px 0 6px; }
pre { background: #1d2433; color: #e8f0fa; padding: 10px 12px; border-radius: 6px; font-family: Consolas, monospace;
      font-size: 10.5pt; white-space: pre-wrap; word-break: break-all; }
pre.screen { background: #0c0c0c; color: #cccccc; }
code { font-family: Consolas, monospace; background: #f2f4f7; padding: 1px 4px; border-radius: 3px; }
.ok { color: #137a3d; }
.note { background: #e8f0fa; border-left: 4px solid #1f5fad; padding: 8px 12px; margin: 12px 0; border-radius: 4px; }
.warn { background: #fff8e6; border-left: 4px solid #e0a400; padding: 8px 12px; margin: 12px 0; border-radius: 4px; }
.pill { display: inline-block; background: #e7f6ec; color: #137a3d; padding: 4px 12px; border-radius: 999px; }
ul.check { list-style: none; padding-left: 0; } ul.check li::before { content: '☐  '; }
table { border-collapse: collapse; width: 100%; font-size: 11pt; }
th, td { border: 1px solid #e4e7ec; padding: 7px 9px; text-align: left; vertical-align: top; }
th { background: #f6f7f9; }
.small { color: #667085; font-size: 10pt; margin-top: 18px; }
.stepno { color: #667085; font-size: 10pt; float: right; }
"""


def build() -> Path:
    parts = []
    for i, (title, body) in enumerate(STEPS):
        cover = ('<div class="cover"><h1>Office helper — setup guide</h1>'
                 '<p>Visa tracking · set up the helper on a new office PC</p></div>') if i == 0 else ""
        num = f'<span class="stepno">Page {i + 1} of {len(STEPS)}</span>'
        parts.append(f"<section>{cover}{num}<h2>{title}</h2>{body}</section>")
    html = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{CSS}</style></head><body>{''.join(parts)}</body></html>"
    out = HERE / "Office helper setup guide.pdf"
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge")
        page = browser.new_page()
        page.set_content(html)
        page.pdf(path=str(out), format="A4", print_background=True)
        browser.close()
    return out


if __name__ == "__main__":
    print(build())
