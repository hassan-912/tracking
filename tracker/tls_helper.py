"""TLS helper mode: TLScontact (behind Cloudflare) refuses browsers a program
controls, so for TLS the program only *assists* a person:

  1. opens the client's TLS site in a normal Edge window (its own fresh profile,
     so clients never share cookies, and nothing controls the page),
  2. puts the email, then the password, on the clipboard for Ctrl+V,
  3. after the employee logs in and says so, screenshots that Edge window for the
     PDF and reads the status from the picture (Windows text recognition),
  4. closes the window, wipes its profile and clears the clipboard.

Two ways to drive it: in the terminal (press Enter), or from the website (the office
helper passes `step`, and staff press "Copy password" / "Next client" / "Skip").
"""
from __future__ import annotations

import ctypes
import io
import shutil
import subprocess
import tempfile
import re
import time
from collections.abc import Callable
from ctypes import wintypes
from datetime import datetime
from pathlib import Path

from PIL import ImageGrab

from . import ocr
from .portals.base import clean_text
from .sheet import Account, mask

SITES = {"de": "https://visas-de.tlscontact.com/", "fr": "https://visas-fr.tlscontact.com/"}
SITE_NAMES = {"de": "Germany", "fr": "France"}
EDGE_PATHS = (
    Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
    Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"),
)
SKIP_WORDS = ("skip", "s")
STOP_WORDS = ("stop", "q", "quit")

user32 = ctypes.windll.user32


# ---------- small Windows helpers ----------

def _edge() -> str:
    for p in EDGE_PATHS:
        if p.exists():
            return str(p)
    found = shutil.which("msedge")
    if not found:
        raise SystemExit("Microsoft Edge was not found on this PC.")
    return found


kernel32 = ctypes.windll.kernel32
kernel32.GlobalAlloc.restype = wintypes.HGLOBAL
kernel32.GlobalAlloc.argtypes = (wintypes.UINT, ctypes.c_size_t)
kernel32.GlobalLock.restype = wintypes.LPVOID
kernel32.GlobalLock.argtypes = (wintypes.HGLOBAL,)
kernel32.GlobalUnlock.argtypes = (wintypes.HGLOBAL,)
user32.SetClipboardData.argtypes = (wintypes.UINT, wintypes.HANDLE)
user32.SetClipboardData.restype = wintypes.HANDLE
CF_UNICODETEXT, GMEM_MOVEABLE = 13, 0x0002


def copy_to_clipboard(text: str) -> None:
    """Put text on the clipboard exactly as it is (Ctrl+V pastes it)."""
    data = ctypes.create_unicode_buffer(text)
    size = ctypes.sizeof(data)
    for _ in range(10):                  # another app may hold the clipboard for a moment
        if user32.OpenClipboard(None):
            break
        time.sleep(0.1)
    else:
        raise RuntimeError("Could not open the clipboard")
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, size)
        ctypes.memmove(kernel32.GlobalLock(handle), data, size)
        kernel32.GlobalUnlock(handle)
        user32.SetClipboardData(CF_UNICODETEXT, handle)   # Windows owns it now
    finally:
        user32.CloseClipboard()


def clear_clipboard() -> None:
    if user32.OpenClipboard(None):
        user32.EmptyClipboard()
        user32.CloseClipboard()


def _windows_of(pid: int) -> list[int]:
    found: list[int] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd) and user32.GetWindowTextLengthW(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(each, 0)
    return found


def _bring_to_front(hwnd: int) -> None:
    user32.ShowWindow(hwnd, 3)                 # SW_MAXIMIZE
    user32.keybd_event(0x12, 0, 0, 0)          # tap Alt: Windows then lets us switch windows
    user32.keybd_event(0x12, 0, 2, 0)
    user32.SetForegroundWindow(hwnd)


def screenshot_window(pid: int) -> bytes | None:
    """PNG of the client's Edge window (brought to the front first)."""
    windows = _windows_of(pid)
    if not windows:
        return None
    hwnd = windows[0]
    _bring_to_front(hwnd)
    time.sleep(1.2)                            # let it repaint
    rect = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    box = (max(rect.left, 0), max(rect.top, 0), rect.right, rect.bottom)
    image = ImageGrab.grab(bbox=box, all_screens=True)
    buf = io.BytesIO()
    image.save(buf, "PNG")
    return buf.getvalue()


# ---------- reading the status from the screenshot ----------

# Wording on a TLScontact account page that carries the application's status.
STATUS_WORDS = re.compile(
    r"(ready for collection|ready to collect|collected|passport (is|has)|returned|"
    r"dispatched|delivered|in transit|sent to|forwarded|being processed|processing|"
    r"in process|under process|submitted|received|decision|completed|"
    r"appointment (confirmed|booked|on)|application status|status:)", re.I)
STILL_AT_CLOUDFLARE = re.compile(r"verify you are human|checking (if|your) (the site|browser)", re.I)
STILL_AT_LOGIN = re.compile(r"\b(log ?in|sign ?in|forgot.*password)\b", re.I)


def read_status(lines: list[str]) -> tuple[str, str]:
    """(status, problem) from the text Windows read in the screenshot."""
    found = [l for l in lines if len(l) < 200 and STATUS_WORDS.search(l)]
    if found:
        # "Application status" on its own is a heading: prefer a real status line.
        best = next((l for l in found
                     if not re.fullmatch(r"(application )?status:?", l, re.I)), found[0])
        return best, ""
    text = " ".join(lines)
    if STILL_AT_CLOUDFLARE.search(text):
        return "", "Still at the Cloudflare check: not logged in (see screenshot)"
    if STILL_AT_LOGIN.search(text) and re.search(r"password", text, re.I):
        return "", "Still on the login page: not logged in (see screenshot)"
    if not lines:
        return "(see screenshot)", ""
    return "(see screenshot: status wording not recognised)", ""


def _read_window(entry: dict, pid: int) -> None:
    """Screenshot the client's window into entry, plus the status read from it."""
    shot = screenshot_window(pid)
    entry["_screenshot"] = shot
    if not shot:
        entry["problem"] = "The Edge window was closed before the screenshot"
        return
    lines = ocr.read_text(shot)
    status, problem = read_status(lines)
    if problem:
        entry["problem"] = problem
    else:
        entry["status"] = status
    entry["details"] = clean_text("\n".join(lines))


# ---------- the helper itself ----------

# Website mode: step(info, copy) shows this client on the website and waits for staff.
# copy("email") / copy("password") puts that value on this PC's clipboard.
# It returns "next" (logged in: read the window), "skip", or "stop".
Step = Callable[[dict, Callable[[str], None]], str]


def _open_edge(acc: Account, profiles: Path) -> tuple[subprocess.Popen, Path]:
    profile = Path(tempfile.mkdtemp(prefix="tls-", dir=profiles))
    edge = subprocess.Popen([_edge(), f"--user-data-dir={profile}", "--no-first-run",
                             "--no-default-browser-check", "--start-maximized", "--new-window",
                             SITES.get(acc.site, SITES["de"])])
    return edge, profile


def _close_edge(edge: subprocess.Popen, profile: Path) -> None:
    clear_clipboard()
    edge.terminate()
    try:
        edge.wait(timeout=10)
    except subprocess.TimeoutExpired:
        edge.kill()
    shutil.rmtree(profile, ignore_errors=True)


def _one_web(acc: Account, n: int, total: int, profiles: Path, step: Step) -> dict:
    entry = {"row": acc.row, "column": acc.column, "client": acc.name,
             "login": mask(acc.username),
             "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    edge, profile = _open_edge(acc, profiles)
    try:
        copy_to_clipboard(acc.username)
        values = {"email": acc.username, "password": acc.password}
        answer = step({"n": n, "total": total, "client": acc.name or mask(acc.username),
                       "email": acc.username, "site": SITE_NAMES.get(acc.site, acc.site)},
                      lambda what: copy_to_clipboard(values.get(what, "")))
        clear_clipboard()
        if answer == "stop":
            entry["problem"] = "Not checked: run stopped"
            entry["_stop"] = True
        elif answer == "skip":
            entry["problem"] = "Skipped"
        else:
            _read_window(entry, edge.pid)
        return entry
    finally:
        _close_edge(edge, profile)

def _ask(prompt: str) -> str:
    return input(prompt).strip()


def _one(acc: Account, n: int, total: int, profiles: Path) -> dict:
    entry = {"row": acc.row, "column": acc.column, "client": acc.name,
             "login": mask(acc.username),
             "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    site = SITE_NAMES.get(acc.site, acc.site)
    print(f"\n[TLS {n}/{total}] row {acc.row} · {acc.name or mask(acc.username)} · TLS {site}")
    print(f"   Email: {acc.username}")

    edge, profile = _open_edge(acc, profiles)
    try:
        copy_to_clipboard(acc.username)
        print("   1) Email copied. In the Edge window: tick 'Verify you are human' if shown,")
        print("      open Login, click the email box and press Ctrl+V.")
        answer = _ask("   Press Enter for the password (or type skip / stop): ").lower()
        if answer in STOP_WORDS:
            entry["problem"] = "Not checked: helper stopped"
            entry["_stop"] = True
            return entry
        if answer in SKIP_WORDS:
            entry["problem"] = "Skipped in the TLS helper"
            return entry

        copy_to_clipboard(acc.password)
        print("   2) Password copied. Click the password box, press Ctrl+V, solve any CAPTCHA,")
        print("      click Log in and wait until the page shows the application.")
        answer = _ask("   Press Enter to take the screenshot (or type skip): ").lower()
        clear_clipboard()
        if answer in SKIP_WORDS:
            entry["problem"] = "Skipped in the TLS helper"
            return entry

        _read_window(entry, edge.pid)
        print(f"   Read from the window: {entry.get('status') or entry.get('problem')}")
        typed = _ask("   3) Press Enter if that is right, or type the status you see: ")
        if typed:
            entry["status"], entry["problem"] = typed, ""
        print("   ✔ saved")
        return entry
    finally:
        _close_edge(edge, profile)


def run(accounts: list[tuple[int, Account]], report: list, previous: dict | None = None,
        step: Step | None = None, say: Callable[..., None] = print) -> None:
    """Go through the TLS clients one by one; fills report[i] for each.
    With `step` the website drives it, otherwise the terminal."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # true pixel sizes for screenshots
    except Exception:
        pass
    ready = [(i, a) for i, a in accounts if not a.problem]
    for i, a in accounts:
        if a.problem:
            report[i] = {"row": a.row, "column": a.column, "client": a.name,
                         "login": mask(a.username), "problem": a.problem}
    if not ready:
        return
    say(f"\n━━ TLS: {len(ready)} client(s), one at a time ━━")
    if not step:
        print("   TLS blocks programs, so you log in yourself; the program copies the email and")
        print("   password for you and takes the screenshot. Type stop at any time to end.")
    profiles = Path(tempfile.mkdtemp(prefix="tls-helper-"))
    try:
        stopped = False
        for n, (i, acc) in enumerate(ready, 1):
            if stopped:
                report[i] = {"row": acc.row, "column": acc.column, "client": acc.name,
                             "login": mask(acc.username), "problem": "Not checked: helper stopped"}
                continue
            entry = (_one_web(acc, n, len(ready), profiles, step) if step
                     else _one(acc, n, len(ready), profiles))
            stopped = bool(entry.pop("_stop", False))
            before = (previous or {}).get((acc.row, acc.column))
            if before is not None and entry.get("status") and before != entry["status"]:
                entry["changed"] = "YES"
            say(f"[TLS {n}/{len(ready)}] {acc.label()}",
                "    ✖ " + entry["problem"] if entry.get("problem")
                else f"    ✔ {entry.get('status', '')}")
            report[i] = entry
    finally:
        clear_clipboard()
        shutil.rmtree(profiles, ignore_errors=True)
