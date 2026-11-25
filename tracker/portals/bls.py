"""BLS Spain Egypt (Cairo + Alexandria): reference number + date of birth + CAPTCHA.

The program fills the reference and date of birth in every window. The employee
clicks "Verify", solves the picture CAPTCHA, then clicks "Submit"; then answers
"yes" in the terminal. Only then is each result read and screenshotted.
The program never clicks Verify or Submit itself. No password is involved.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page

from . import captcha_gate
from .base import Result, clean_text, goto_with_retry, settle

STATUS_URL = "https://egypt.blsspainglobal.com/Global/bls/VisaApplicationStatus"

# Wording that means the reference / date of birth pair is wrong.
NOT_FOUND = (
    "no record",
    "not found",
    "invalid reference",
    "incorrect",
    "does not match",
)
# Wording on the result page that carries the status.
STATUS_WORDS = re.compile(
    r"(received|under process|processing|in process|forwarded|dispatched|"
    r"returned|ready for|collect|handed over|delivered|decision|approved|refused|"
    r"rejected|submitted|embassy|consulate|in transit|awaiting|pending|courier)", re.I)


def _on_form(page: Page) -> bool:
    return page.locator("#refNo").count() > 0 and page.locator("#btnVerify").count() > 0


def _set_birth_date(page: Page, iso_date: str) -> None:
    """The date box is a read-only calendar picker: set it the way picking a day would."""
    page.wait_for_function("() => window.jQuery && jQuery('#dob').data('kendoDatePicker')",
                           timeout=20_000)
    page.evaluate("""(iso) => {
        const [y, m, d] = iso.split('-').map(Number);
        const picker = jQuery('#dob').data('kendoDatePicker');
        picker.value(new Date(y, m - 1, d));
        picker.trigger('change');
    }""", iso_date)


def check(page: Page, reference: str, birth_date: str, who: str) -> Result:
    try:
        goto_with_retry(page, STATUS_URL)
        page.fill("#refNo", reference)
        _set_birth_date(page, birth_date)
        captcha_gate.highlight(page, "#btnVerify")
    finally:
        captcha_gate.ready()          # tell the runner this window is set up (or gave up)

    captcha_gate.wait_for_yes(page)   # the employee answers "yes" in the terminal

    settle(page, 4000)
    text = page.inner_text("body")
    lower = text.lower()
    for phrase in NOT_FOUND:
        if phrase in lower:
            return Result(problem=f"BLS: {phrase} — check the reference / date of birth")
    if _on_form(page):
        return Result(problem="No result: Verify / Submit wasn't finished in this window "
                              "(or BLS asked for the CAPTCHA again)")

    lines = [" ".join(l.split()) for l in text.splitlines()]
    status_lines = [l for l in lines if l and len(l) < 200 and STATUS_WORDS.search(l)]
    return Result(status=status_lines[0] if status_lines else "(see screenshot)",
                  details=clean_text("\n".join(status_lines) or text))
