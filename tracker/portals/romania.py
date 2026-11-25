"""Romania e-Visa (evisa.mae.ro): "Accesare dosar existent" = file number + password + CAPTCHA.

Works like VFS: the program fills the file number and password in every window,
the employee types each CAPTCHA and presses Enter / "Continuă", then answers
"yes" in the terminal. Only then is each file's page read and screenshotted.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page

from . import captcha_gate
from .base import Result, clean_text, goto_with_retry, settle

LOGIN_URL = "https://evisa.mae.ro/Dosar/Cautare"

# Romanian wording that means the number/password pair was rejected.
REJECTED = (
    "incorect",            # număr dosar / parolă incorectă
    "nu a fost găsit",
    "nu există",
    "invalid",
)
# Wording on the file page that carries the status (Romanian + English).
STATUS_WORDS = re.compile(
    r"(stadiu|stare|status|aprobat|respins|refuz|acordat|eliberat|în lucru|in lucru|"
    r"în analiză|in analiza|depus|transmis|programare|approved|rejected|refused|"
    r"issued|granted|under review|submitted)", re.I)


def _on_form(page: Page) -> bool:
    return page.locator("#CaptchaInputText").count() > 0 and page.locator("#CodDosar").count() > 0


def _rejected(page: Page) -> str:
    if not _on_form(page):
        return ""
    body = page.inner_text("body", timeout=2000).lower()
    for phrase in REJECTED:
        if phrase in body:
            return f"Romania e-Visa: login rejected ({phrase}) — check the file number / password"
    return ""


def check(page: Page, file_number: str, password: str, who: str) -> Result:
    try:
        goto_with_retry(page, LOGIN_URL)
        page.fill("#CodDosar", file_number)
        page.fill("#Parola", password)
        captcha_gate.highlight(page, hint="Type the code, then press Enter")
    finally:
        captcha_gate.ready()

    captcha_gate.wait_for_yes(page)

    settle(page, 4000)
    rejected = _rejected(page)
    if rejected:
        return Result(problem=rejected)
    if _on_form(page):
        return Result(problem="No result: the CAPTCHA wasn't submitted in this window "
                              "(or the site asked for it again)")

    text = page.inner_text("body")
    lines = [" ".join(l.split()) for l in text.splitlines()]
    status_lines = [l for l in lines if l and len(l) < 200 and STATUS_WORDS.search(l)]
    return Result(status=status_lines[0] if status_lines else "(see screenshot)",
                  details=clean_text("\n".join(status_lines) or text))
