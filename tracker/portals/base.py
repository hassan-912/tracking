"""Shared pieces for every portal: the result type and the wait-for-a-person loop."""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from playwright.sync_api import Page

# How long to wait for the employee to type an OTP / solve a CAPTCHA.
HUMAN_TIMEOUT_S = 5 * 60


@dataclass
class Result:
    status: str = ""      # what the portal says, trimmed
    details: str = ""     # extra lines (application numbers, dates)
    problem: str = ""     # why the check failed, if it did
    screenshot: bytes | None = None   # set when the result opened in a new window


def wait_until(page: Page, done: Callable[[Page], bool], failed: Callable[[Page], str],
               who: str, timeout_s: int = HUMAN_TIMEOUT_S) -> str:
    """Wait until `done(page)` is true.

    While the page is neither done nor showing a login error, a person is
    probably needed (OTP, CAPTCHA, security question): say so once and keep
    waiting. Returns "" on success or the reason it gave up.
    """
    announced = False
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            if done(page):
                if announced:
                    print("    ✔ thanks, carrying on")
                return ""
            error = failed(page)
            if error:
                return error
        except Exception:
            pass  # page is mid-navigation; look again
        if not announced and time.monotonic() > deadline - timeout_s + 8:
            print(f"    ⏸  {who}: needs you in the browser "
                  "(OTP, CAPTCHA or security question). I'll continue when it's done.")
            announced = True
        page.wait_for_timeout(300)
    return f"Gave up after {timeout_s // 60} min waiting for login (OTP/CAPTCHA not completed)"


def goto_with_retry(page: Page, url: str, attempts: int = 2, timeout_ms: int = 60_000) -> None:
    """Government sites are often slow: wait up to 60 s, and try once more."""
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
            return
        except Exception:
            if attempt == attempts:
                raise RuntimeError(f"Site did not load after {attempts} tries "
                                   f"({timeout_ms // 1000}s each) — try again later") from None
            page.wait_for_timeout(5000)


def settle(page: Page, max_ms: int = 5000) -> None:
    """Give the page up to `max_ms` to finish loading, then carry on anyway.

    Sites like WES keep background requests open forever, so waiting for
    "no network activity" could otherwise cost the full 30 s every time.
    """
    try:
        page.wait_for_load_state("networkidle", timeout=max_ms)
    except Exception:
        pass


def clean_text(text: str, limit: int = 600) -> str:
    lines = [" ".join(l.split()) for l in text.splitlines()]
    text = "\n".join(l for l in lines if l)
    return text if len(text) <= limit else text[:limit] + " …"
