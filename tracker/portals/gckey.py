"""IRCC secure account through GCKey (Canada Tourism, Canada Study, FEE)."""
from __future__ import annotations

from playwright.sync_api import Page

from .base import Result, clean_text, goto_with_retry, settle, wait_until

LOGIN_URL = ("https://onlineservices-servicesenligne-cic.fjgc-gccf.gc.ca"
             "/mycic/gccf?lang=eng&idp=gckey&svc=/mycic/start")

# Text that only appears once the IRCC account home page has loaded.
HOME_MARKERS = (
    "view the applications you submitted",
    "view submitted applications",
    "applications you have submitted",
    "continue an application you have not submitted",
)
BLOCKED = "GCKey BLOCKED"   # runner stops all GCKey checks when it sees this

LOGIN_ERRORS = (
    "security check failed",
    "username or password you entered is incorrect",
    "your gckey has been revoked",
    "your gckey is locked",
    "account is locked",
    "password has expired",
)


def _body(page: Page) -> str:
    return page.inner_text("body", timeout=2000).lower()


def _on_home(page: Page) -> bool:
    return "cic.gc.ca" in page.url and any(m in _body(page) for m in HOME_MARKERS)


def _login_error(page: Page) -> str:
    if "gckey" not in page.url:
        return ""
    body = _body(page)
    for err in LOGIN_ERRORS:
        if err in body:
            if err == "security check failed":
                return f"{BLOCKED}: GCKey security check failed (too many logins / automated browser)"
            return f"GCKey: {err}"
    return ""


def _status_rows(page: Page) -> list[str]:
    """Every table row on the home page, with the status column first."""
    rows: list[str] = []
    for table in page.locator("table").all():
        headers = [h.inner_text().strip().lower() for h in table.locator("th").all()]
        status_idx = next((i for i, h in enumerate(headers) if "status" in h), None)
        for tr in table.locator("tbody tr").all():
            cells = [" ".join(c.inner_text().split()) for c in tr.locator("td").all()]
            if not any(cells):
                continue
            if status_idx is not None and status_idx < len(cells):
                rows.append(f"{cells[status_idx]}  ←  " + " | ".join(
                    c for i, c in enumerate(cells) if i != status_idx and c))
            else:
                rows.append(" | ".join(c for c in cells if c))
    return rows


def check(page: Page, username: str, password: str, who: str) -> Result:
    goto_with_retry(page, LOGIN_URL)
    if page.locator("#token1").count() == 0:
        blocked = _login_error(page)
        if blocked:
            return Result(problem=blocked)
    page.fill("#token1", username)
    page.fill("#token2", password)
    page.click("#button")

    problem = wait_until(page, _on_home, _login_error, who)
    if problem:
        return Result(problem=problem)

    settle(page)
    rows = _status_rows(page)
    if not rows:
        return Result(status="(no submitted applications found)",
                      details=clean_text(page.inner_text("main") if page.locator("main").count() else ""))

    _sign_out(page)
    return Result(status=rows[0].split("  ←  ")[0], details=clean_text("\n".join(rows)))


def _sign_out(page: Page) -> None:
    try:
        link = page.get_by_role("link", name="Sign out")
        if link.count():
            link.first.click(timeout=5000)
    except Exception:
        pass  # closing the browser context ends the session anyway
