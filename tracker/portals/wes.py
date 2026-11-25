"""World Education Services (WES, WES ICAP)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import Page

from .base import Result, clean_text, goto_with_retry, settle, wait_until

LOGIN_URL = "https://applications.wes.org/createaccount/login/"

LOGIN_ERRORS = (
    "please check your username and password",
    "your login attempt has failed",
    "incorrect",
    "locked",
)
REF_RE = re.compile(r"Reference Number:\s*([A-Z0-9-]{6,})", re.I)
STEPS = ("Application", "Documents", "Evaluation")

# Written once per run so the step reader can be tuned. Holds only CSS class
# names and labels of the progress tracker, no client data.
DEBUG_FILE = Path(__file__).resolve().parents[2] / "results" / "wes-tracker-debug.json"

# Given one step label element, describe it and its parents (crossing the
# site's shadow-DOM boundaries): tag, class, aria-*/data-* attributes and any
# icon nearby. That's where WES marks a step as done / current.
_ANCESTORS_JS = """
(el) => {
  const out = [];
  let n = el;
  for (let i = 0; i < 7 && n; i++) {
    const attrs = [];
    if (n.attributes) for (const a of n.attributes)
      if (/^(class|aria-|data-|title|role|alt|state|status)/.test(a.name)) attrs.push(a.name + '=' + a.value);
    out.push((n.tagName || '').toLowerCase() + ' ' + attrs.join(' '));
    if (i < 3 && n.querySelector) {
      const icon = n.querySelector('img[alt], lightning-icon, svg, [class*=icon]');
      if (icon) out.push('  icon: ' + (icon.getAttribute('alt') || icon.getAttribute('icon-name')
          || icon.getAttribute('class') || icon.tagName));
    }
    n = n.parentElement || (n.getRootNode && n.getRootNode().host) || null;
  }
  return out.join('\\n').toLowerCase();
}
"""
TRACKER_HINT = re.compile(r"step|path|progress|stage|tracker|milestone|indicator", re.I)


def _read_steps(page: Page) -> list[dict]:
    """For each step label, the attribute dump of the match that sits in the tracker."""
    steps = []
    for label in STEPS:
        dumps = []
        for handle in page.get_by_text(label, exact=True).element_handles()[:6]:
            try:
                dumps.append(handle.evaluate(_ANCESTORS_JS))
            except Exception:
                continue
        best = next((d for d in dumps if TRACKER_HINT.search(d)), dumps[0] if dumps else None)
        steps.append({"label": label, "attrs": best, "all_matches": len(dumps)})
    return steps


def _logged_in(page: Page) -> bool:
    return "/login" not in page.url and "applications.wes.org" in page.url \
        and page.get_by_text(re.compile(r"log ?out|sign ?out", re.I)).count() > 0


def _login_error(page: Page) -> str:
    if "/login" not in page.url:
        return ""
    body = page.inner_text("body", timeout=2000).lower()
    for err in LOGIN_ERRORS:
        if err in body:
            return f"WES: {err}"
    return ""


def _stage(steps: list[dict]) -> str:
    """Name the stage from which tracker step is marked done / current."""
    done, current = [], None
    for s in steps:
        # Only the label, its closest parents and their icons: higher parents
        # wrap all three steps and would mark every step the same.
        a = "\n".join((s.get("attrs") or "").splitlines()[:5])
        if re.search(r"incomplete|unchecked|not[-_ ]?started|pending|disabled|inactive", a):
            continue
        if re.search(r"current|active|in[-_ ]?progress", a) and current is None:
            current = s["label"]
        elif re.search(r"complete|done|success|finished|check", a):
            done.append(s["label"])
    if current:
        return f"{current} stage"
    if done and len(done) == len(STEPS):
        return "Evaluation complete"
    if done:
        return f"{done[-1]} done"
    return ""


def check(page: Page, email: str, password: str, who: str) -> Result:
    goto_with_retry(page, LOGIN_URL)
    page.get_by_placeholder("Enter").first.wait_for(timeout=30000)
    page.get_by_label("Email Address").fill(email)
    page.get_by_label("Password").fill(password)
    page.get_by_role("button", name="Log In").click()

    problem = wait_until(page, _logged_in, _login_error, who)
    if problem:
        return Result(problem=problem)

    settle(page)
    text = page.inner_text("body")
    try:
        steps = _read_steps(page)
    except Exception:
        steps = []
    status = _stage(steps)
    if steps and not status:
        # Keep the layout of an unrecognised tracker so the reader can be tuned.
        DEBUG_FILE.parent.mkdir(exist_ok=True)
        DEBUG_FILE.write_text(json.dumps(steps, indent=2), encoding="utf-8")

    ref = REF_RE.search(text)
    apps = re.search(r"My Applications \((\d+)\)", text)
    status = status or "(stage not recognised — see screenshot)"
    details = "\n".join(filter(None, [
        f"Ref {ref.group(1)}" if ref else "",
        f"{apps.group(1)} application(s) on this account" if apps and apps.group(1) != "1" else "",
        clean_text(text),
    ]))
    return Result(status=status, details=details)
