"""VFS Global online tracking: reference number + surname + image CAPTCHA.

The program fills the reference and surname in every window, then asks in the
terminal. The employee types each CAPTCHA and presses Enter (or clicks Submit)
themselves, then answers "yes"; only then are results read and screenshots
taken. The program never submits on its own. No password is involved.
"""
from __future__ import annotations

import json
import re
import threading
from pathlib import Path

from playwright.sync_api import Page

from . import captcha_gate
from .base import Result, clean_text, goto_with_retry, settle

LINKS_FILE = Path(__file__).resolve().parents[2] / "vfs_links.json"


def _on_form(page: Page) -> bool:
    return page.locator("#CaptchaInputText").count() > 0

# Wording that means the reference/surname pair is wrong (stop waiting).
NOT_FOUND = (
    "no record found",
    "no records found",
    "invalid reference",
    "reference number is invalid",
    "details entered are incorrect",
    "does not match",
)
# Wording on the result page that carries the status.
STATUS_WORDS = re.compile(
    r"(received|under process|processing|forwarded|dispatched|returned|ready for|"
    r"collect|delivered|decision|approved|refused|rejected|submitted|in transit|"
    r"awaiting|pending|courier)", re.I)


# Reference prefixes that are not simply the 3-letter country code.
MISSION_ALIASES = {"SEAC": "swe"}

# Second part of the reference = city of the visa centre -> country applied from.
CITY_TO_ORIGIN = {
    "CAI": "egy", "ALX": "egy", "HBE": "egy",
    "DXB": "are", "AUH": "are", "SHJ": "are", "AAN": "are", "RAK": "are", "FUJ": "are",
    "JED": "sau", "RUH": "sau", "DMM": "sau", "KHO": "sau",
    "KWI": "kwt", "DOH": "qat", "MCT": "omn", "BAH": "bhr", "AMM": "jor", "BEY": "lbn",
}
# Tried in this order when the reference has no (known) city.
DEFAULT_ORIGINS = ("egy", "are")
ORIGIN_NAMES = {"egy": "Egypt", "are": "UAE", "sau": "Saudi Arabia", "kwt": "Kuwait",
                "qat": "Qatar", "omn": "Oman", "bhr": "Bahrain", "jor": "Jordan",
                "lbn": "Lebanon"}

TRACKER_LINK_RE = re.compile(r"/Global-Passporttracking/Track/Index\?q=", re.I)
_links_lock = threading.Lock()


def country_of(reference: str) -> str:
    return reference.split("/", 1)[0].upper()


def mission_of(reference: str) -> str:
    """Destination country as VFS writes it in its web addresses: 'nld', 'cze', 'swe'…"""
    prefix = country_of(reference)
    return MISSION_ALIASES.get(prefix, prefix[:3]).lower()


def origins_of(reference: str) -> tuple[str, ...]:
    """Countries the client may have applied from, most likely first."""
    parts = reference.upper().split("/")
    city = parts[1] if len(parts) > 2 else ""
    if city in CITY_TO_ORIGIN:
        return (CITY_TO_ORIGIN[city],)
    return DEFAULT_ORIGINS


def _load_links() -> dict:
    if not LINKS_FILE.exists():
        return {}
    return json.loads(LINKS_FILE.read_text(encoding="utf-8"))


def _save_link(key: str, link: str) -> None:
    with _links_lock:
        links = _load_links()
        links[key] = link
        LINKS_FILE.write_text(json.dumps(links, indent=2, ensure_ascii=False), encoding="utf-8")


def tracking_link(reference: str) -> str:
    """Saved link for this reference's country + where it was applied, if any."""
    links = _load_links()
    for origin in origins_of(reference):
        link = (links.get(f"{mission_of(reference)}/{origin}") or "").strip()
        if link:
            return link
    return ""


def find_link(page: Page, reference: str) -> str:
    """Open VFS's 'Track your application' page for this country, pick up the
    online-tracking link, and save it for next time."""
    mission = mission_of(reference)
    for origin in origins_of(reference):
        url = f"https://visa.vfsglobal.com/{origin}/en/{mission}/track-application"
        try:
            goto_with_retry(page, url)
            anchor = page.locator("a[href*='Global-Passporttracking/Track/Index']").first
            anchor.wait_for(state="attached", timeout=20_000)
            link = anchor.get_attribute("href") or ""
        except Exception:
            continue          # no VFS page for this pair (404) or it didn't load
        if TRACKER_LINK_RE.search(link):
            _save_link(f"{mission}/{origin}", link)
            return link
    return ""


def where_tried(reference: str) -> str:
    return " or ".join(ORIGIN_NAMES.get(o, o.upper()) for o in origins_of(reference))


def _not_found(page: Page) -> str:
    body = page.inner_text("body", timeout=2000).lower()
    for phrase in NOT_FOUND:
        if phrase in body:
            return f"VFS: {phrase}"
    return ""   # a wrong CAPTCHA just shows the form again: keep waiting


def check(page: Page, reference: str, surname: str, who: str) -> Result:
    popups: list[Page] = []
    page.context.on("page", lambda new_page: popups.append(new_page))
    try:
        link = tracking_link(reference) or find_link(page, reference)
        if not link:
            return Result(problem=f"No VFS tracking page found for {country_of(reference)} "
                                  f"from {where_tried(reference)} — add the link to vfs_links.json")
        goto_with_retry(page, link)
        page.fill("#AppRefNo", reference)
        page.fill("[name='LastName']", surname)
        captcha_gate.highlight(page)
    finally:
        captcha_gate.ready()          # tell the runner this window is set up (or gave up)

    captcha_gate.wait_for_yes(page)   # the employee answers "yes" in the terminal

    target = popups[-1] if popups else page
    settle(target, 4000)
    text = target.inner_text("body")
    shot = target.screenshot(full_page=True) if target is not page else None
    not_found = _not_found(target)
    if not_found:
        return Result(problem=not_found, screenshot=shot)

    lines = [" ".join(l.split()) for l in text.splitlines()]
    status_lines = [l for l in lines if l and len(l) < 200 and STATUS_WORDS.search(l)]
    if not status_lines and _on_form(target):
        return Result(problem="No result: the CAPTCHA wasn't submitted in this window "
                              "(or VFS asked for it again)", screenshot=shot)
    return Result(status=status_lines[0] if status_lines else "(see screenshot)",
                  details=clean_text("\n".join(status_lines) or text), screenshot=shot)
