"""Shared hand-off for portals where the employee types a CAPTCHA (VFS, Romania e-Visa, BLS, Brazil).

Each window calls `ready()` once its form is filled (or it gave up), then
`wait_for_yes(page)`. The runner waits for every window to be ready, asks in
the terminal, and calls `user_said_yes()`.
"""
from __future__ import annotations

import threading

from playwright.sync_api import Page

PORTALS = ("vfs", "romania", "bls", "brazil")

_windows_ready = threading.Semaphore(0)
_user_done = threading.Event()


def ready() -> None:
    _windows_ready.release()


def said_yes() -> bool:
    return _user_done.is_set()


def wait_for_yes(page: Page) -> None:
    # Keep the browser responsive meanwhile (the employee is typing, retrying…).
    while not _user_done.is_set():
        page.wait_for_timeout(500)


def wait_until_all_ready(windows: int) -> None:
    for _ in range(windows):
        _windows_ready.acquire()


def user_said_yes() -> None:
    _user_done.set()


def reset() -> None:
    _user_done.clear()


def highlight(page: Page, selector: str = "#CaptchaInputText",
              hint: str = "Type the code, then press Enter") -> None:
    """Yellow outline + hint on the CAPTCHA box. Visual only: nothing extra is sent."""
    try:
        page.eval_on_selector(selector, """(box, hint) => {
            box.style.outline = '4px solid #F1C232';
            box.placeholder = hint;
            box.focus();
        }""", hint)
    except Exception:
        pass
