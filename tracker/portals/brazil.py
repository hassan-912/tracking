"""Brazil visa (SCI form, Ministry of Foreign Affairs): "Check application status".

Needs the application recovery code, family name(s) and date of birth, plus an
hCaptcha. The program fills the three boxes in every window; the employee solves
the hCaptcha and clicks SEARCH, then answers "yes" in the terminal. Only then is
each result read and screenshotted. The program never clicks SEARCH itself.
"""
from __future__ import annotations

import re

from playwright.sync_api import Page

from . import captcha_gate
from .base import Result, clean_text, goto_with_retry, settle

# The status page for visa applicants (foreign citizens).
STATUS_URL = "https://formulario-mre.serpro.gov.br/sci/pages/web/ui/#/visto-status"

# Wording that means the code / surname / birth date don't match an application.
NOT_FOUND = (
    "not found",
    "no application",
    "no record",
    "não encontrad",       # nenhum requerimento encontrado
    "nenhum",
    "invalid",
    "inválid",
)
# Wording in the result that carries the status (English + Portuguese).
STATUS_WORDS = re.compile(
    r"(situa[cç][aã]o|status|received|recebid|under analysis|em an[aá]lise|pending|pendente|"
    r"approved|aprovad|deferid|denied|indeferid|refused|recusad|issued|emitid|concedid|"
    r"ready|pronto|dispon[ií]vel|submitted|enviad|cancel)", re.I)


def surname_of(full_name: str) -> str:
    """Family name as the form expects it: the last word of the full name."""
    words = full_name.split()
    return words[-1] if words else ""


def _date_for_form(page: Page, iso_date: str) -> str:
    """The form shows the date the way its language does: mm/dd/yyyy in English,
    dd/mm/yyyy in Portuguese and the others."""
    year, month, day = iso_date.split("-")
    body = page.inner_text("body", timeout=5000).lower()
    if "mm/dd/" in body:
        return f"{month}/{day}/{year}"
    return f"{day}/{month}/{year}"


def _on_form(page: Page) -> bool:
    return page.locator("#codigo").count() > 0 and page.locator("#pesquisar").count() > 0


def _result_text(page: Page) -> str:
    for selector in ("#collapseResultados", "#outputResultado", "#outputSingle"):
        box = page.locator(selector)
        if box.count() and box.first.is_visible():
            text = box.first.inner_text().strip()
            if text:
                return text
    return ""


def check(page: Page, code: str, birth_date: str, who: str, full_name: str = "") -> Result:
    surname = surname_of(full_name)
    try:
        goto_with_retry(page, STATUS_URL)
        page.locator("#codigo").wait_for(timeout=30_000)
        page.fill("#codigo", code)
        if surname:
            page.fill("#sobrenome", surname)
        # The date box formats as you type, so type it like a person would.
        page.click("#inputDtNasc")
        page.keyboard.type(_date_for_form(page, birth_date), delay=40)
        page.keyboard.press("Tab")
        captcha_gate.highlight(page, "#pesquisar")
    finally:
        captcha_gate.ready()          # tell the runner this window is set up (or gave up)

    captcha_gate.wait_for_yes(page)   # the employee answers "yes" in the terminal

    settle(page, 4000)
    result = _result_text(page)
    body = page.inner_text("body")
    lower = (result or body).lower()
    for phrase in NOT_FOUND:
        if phrase in lower:
            hint = f" (surname used: {surname})" if surname else " (no name in the sheet)"
            return Result(problem=f"Brazil: {phrase} — check the code / surname / birth date{hint}")
    if not result:
        return Result(problem="No result: the hCaptcha / SEARCH wasn't finished in this window")

    lines = [" ".join(l.split()) for l in result.splitlines()]
    status_lines = [l for l in lines if l and len(l) < 200 and STATUS_WORDS.search(l)]
    return Result(status=status_lines[0] if status_lines else "(see screenshot)",
                  details=clean_text("\n".join(status_lines) or result))
