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

# The Cairo visa centre page: it has the LOGIN button (the home page doesn't).
SITES = {"de": "https://visas-de.tlscontact.com/en-us/country/eg/vac/egCAI2de",
         "fr": "https://visas-fr.tlscontact.com/en-us/country/eg/vac/egCAI2fr"}
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

# Website mode: step(info, copy) shows this client on the website (again whenever info
# changes) and returns at once: "next" (read the window now), "skip", "stop", or ""
# (nothing pressed). copy("email") / copy("password") puts that value on the clipboard.
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


# ---------- filling the login form in the person's Edge window ----------
# Like a password manager's auto-type: the program looks at the window (screenshot +
# Windows text recognition), clicks, and types. It never touches the CAPTCHA and never
# presses Login: staff tick "I'm not a robot" and click Login themselves.

class NotInFront(Exception):
    """The client's window is no longer the active one: stop typing at once."""


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t))


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (("dx", wintypes.LONG), ("dy", wintypes.LONG), ("mouseData", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t))


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT))
    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


KEYEVENTF_KEYUP, KEYEVENTF_UNICODE = 0x0002, 0x0004
MOUSEEVENTF_LEFTDOWN, MOUSEEVENTF_LEFTUP = 0x0002, 0x0004
VK_CONTROL, VK_A, VK_DELETE = 0x11, 0x41, 0x2E


def _send(*inputs: _INPUT) -> None:
    arr = (_INPUT * len(inputs))(*inputs)
    user32.SendInput(len(inputs), arr, ctypes.sizeof(_INPUT))


def _key(vk: int = 0, char: str = "", up: bool = False) -> _INPUT:
    flags = (KEYEVENTF_UNICODE if char else 0) | (KEYEVENTF_KEYUP if up else 0)
    return _INPUT(type=1, ki=_KEYBDINPUT(wVk=vk, wScan=ord(char) if char else 0, dwFlags=flags))


def _must_be_in_front(hwnd: int) -> None:
    if user32.GetForegroundWindow() != hwnd:
        raise NotInFront


def _click(hwnd: int, x: int, y: int) -> None:
    _must_be_in_front(hwnd)
    user32.SetCursorPos(x, y)
    time.sleep(0.15)
    _send(_INPUT(type=0, mi=_MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTDOWN)),
          _INPUT(type=0, mi=_MOUSEINPUT(dwFlags=MOUSEEVENTF_LEFTUP)))
    time.sleep(0.4)


def _type_into_focused(hwnd: int, text: str) -> None:
    """Clear the focused box (Ctrl+A, Delete) and type text, checking before every key
    that the client's window is still the active one."""
    _must_be_in_front(hwnd)
    _send(_key(VK_CONTROL), _key(VK_A), _key(VK_A, up=True), _key(VK_CONTROL, up=True),
          _key(VK_DELETE), _key(VK_DELETE, up=True))
    for char in text:
        _must_be_in_front(hwnd)
        _send(_key(char=char), _key(char=char, up=True))
        time.sleep(0.02)


class Window:
    """The client's Edge window, as seen on screen."""

    def __init__(self, pid: int):
        self.pid = pid
        self.box = (0, 0, 0, 0)

    @property
    def hwnd(self) -> int:
        found = _windows_of(self.pid)
        return found[0] if found else 0

    def look(self, bring: bool = True) -> tuple[bytes | None, list[ocr.Line]]:
        """Screenshot + the text in it. With bring=False it only looks when the window
        is already in front (so it never pulls focus away from staff)."""
        hwnd = self.hwnd
        if not hwnd:
            return None, []
        if bring:
            if user32.GetForegroundWindow() != hwnd:
                _bring_to_front(hwnd)
                time.sleep(0.8)
        elif user32.GetForegroundWindow() != hwnd:
            return None, []
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        self.box = (max(rect.left, 0), max(rect.top, 0), rect.right, rect.bottom)
        buf = io.BytesIO()
        ImageGrab.grab(bbox=self.box, all_screens=True).save(buf, "PNG")
        shot = buf.getvalue()
        return shot, ocr.read_lines(shot)

    def click(self, line: ocr.Line) -> None:
        x, y = line.centre
        _click(self.hwnd, self.box[0] + x, self.box[1] + y)


PAGE_TOP = 90          # below Edge's own tabs and address bar (pixels from the window top)
CLOUDFLARE = re.compile(r"security verification|verify you are human|just a moment", re.I)
LOGIN_FORM = re.compile(r"login to your tlscontact account|email address and password", re.I)
LOGIN_ERROR = re.compile(r"invalid (username|email)|invalid .*password|incorrect|"
                         r"account (is )?(locked|disabled)|too many", re.I)


def _find(lines: list[ocr.Line], pattern: str, below: int = PAGE_TOP) -> ocr.Line | None:
    return next((l for l in lines if l.top > below and re.fullmatch(pattern, l.text, re.I)),
                None)


def _wait_for(window: Window, test, seconds: int, poll: Callable[[], str]) -> tuple[list, str]:
    """Look at the window until test(lines) is true. Returns (lines, button pressed)."""
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        answer = poll()
        if answer:
            return [], answer
        _, lines = window.look()
        if lines and test(lines):
            return lines, ""
        time.sleep(1.5)
    return [], ""


def fill_login(window: Window, acc: Account, poll: Callable[[], str], say) -> str:
    """Open TLS's login form and type the email and password.
    Returns "" when filled, a button pressed on the website ("skip"/"stop"/"next"),
    or "manual: <why>" when staff must fill it themselves."""
    # 1. the centre page (after Cloudflare's automatic check): click LOGIN
    lines, answer = _wait_for(window, lambda ls: bool(_find(ls, r"log ?in")) or
                              any(LOGIN_FORM.search(l.text) for l in ls), 90, poll)
    if answer:
        return answer
    if not lines:
        return "manual: the TLS page didn't load (or Cloudflare wants a tick)"
    if not any(LOGIN_FORM.search(l.text) for l in lines):
        window.click(_find(lines, r"log ?in"))
        lines, answer = _wait_for(window, lambda ls: any(LOGIN_FORM.search(l.text) for l in ls),
                                  60, poll)
        if answer:
            return answer
        if not lines:
            return "manual: the login page didn't open"

    # 2. the form: clicking a field's label puts the cursor in that field
    email_label, password_label = _find(lines, r"email"), _find(lines, r"password")
    if not email_label or not password_label:
        return "manual: couldn't find the Email and Password boxes"
    window.click(email_label)
    _type_into_focused(window.hwnd, acc.username)
    window.click(password_label)
    _type_into_focused(window.hwnd, acc.password)
    say("    email and password filled in: waiting for the CAPTCHA and Login")
    return ""


def wait_for_login(window: Window, poll: Callable[[], str], minutes: int = 6) -> tuple[str, str]:
    """After the form is filled: wait for staff to tick the CAPTCHA and click Login.
    Returns ("in", "") when the account page shows, ("", button) if one was pressed,
    ("error", what TLS said) on a wrong password, or ("timeout", "")."""
    end = time.monotonic() + minutes * 60
    left_form = 0
    while time.monotonic() < end:
        answer = poll()
        if answer:
            return "", answer
        _, lines = window.look(bring=False)          # never pull focus while staff work
        if lines:
            text = [l.text for l in lines if l.top > PAGE_TOP]
            address = " ".join(l.text for l in lines if l.top <= PAGE_TOP).lower()
            error = next((l for l in text if LOGIN_ERROR.search(l)), "")
            if error:
                return "error", error
            # Logged in = the address bar shows TLS but no longer its sign-in address
            # (auth.visas-…), and no login form or Cloudflare check is on screen. A
            # picture CAPTCHA covering the form doesn't change the address, so it can't
            # be mistaken for a login.
            on_form = ("tlscontact" not in address or "auth." in address
                       or any(LOGIN_FORM.search(l) or CLOUDFLARE.search(l) for l in text))
            # ... for two looks in a row (the page has settled).
            left_form = 0 if on_form else left_form + 1
            if left_form >= 2:
                return "in", ""
        time.sleep(2)
    return "timeout", ""


def _one_web(acc: Account, n: int, total: int, profiles: Path, step: Step, say) -> dict:
    entry = {"row": acc.row, "column": acc.column, "client": acc.name,
             "login": mask(acc.username),
             "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    info = {"n": n, "total": total, "client": acc.name or mask(acc.username),
            "email": acc.username, "site": SITE_NAMES.get(acc.site, acc.site), "stage": "filling"}
    values = {"email": acc.username, "password": acc.password}
    copy = lambda what: copy_to_clipboard(values.get(what, ""))   # noqa: E731
    poll = lambda: step(info, copy)                                # noqa: E731

    edge, profile = _open_edge(acc, profiles)
    window = Window(edge.pid)
    try:
        try:
            answer = fill_login(window, acc, poll, say)
        except NotInFront:
            answer = "manual: another window was clicked while the program was typing"
        if answer.startswith("manual:"):
            say(f"    couldn't fill the form by itself ({answer[8:]}): staff fill it")
            info = {**info, "stage": "manual", "why": answer[8:]}
            copy_to_clipboard(acc.username)
            answer = ""
        else:
            info = {**info, "stage": "captcha"}

        result = ""
        if not answer:
            result, answer = wait_for_login(window, poll)
        if answer == "stop":
            entry["problem"], entry["_stop"] = "Not checked: run stopped", True
        elif answer == "skip":
            entry["problem"] = "Skipped"
        elif result == "error":
            entry["problem"] = f"TLS refused the login: {answer or 'wrong email or password'}"
            entry["_screenshot"] = window.look()[0]
        elif result == "timeout":
            entry["problem"] = "Not logged in within 6 minutes (see screenshot)"
            entry["_screenshot"] = window.look()[0]
        else:                                   # logged in, or "Read it now" pressed
            info = {**info, "stage": "reading"}
            poll()
            time.sleep(3)                       # let the account page finish loading
            _read_window(entry, edge.pid)
        return entry
    finally:
        clear_clipboard()
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
            entry = (_one_web(acc, n, len(ready), profiles, step, say) if step
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
