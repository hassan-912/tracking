"""Check every client's visa / WES status from the works sheet in one go.

    python run_tracker.py "Works Sheet.xlsx"                 # check everything
    python run_tracker.py "Works Sheet.xlsx" --only WES      # one column
    python run_tracker.py "Works Sheet.xlsx" --rows 4-20     # some rows
    python run_tracker.py "Works Sheet.xlsx" --dry-run       # just list what it would check

A browser window opens. When a portal asks for an OTP, a CAPTCHA or a
security question, do it in that window; the program notices and carries on.
Results go to the "results" folder (no passwords are written there).
"""
from __future__ import annotations

import argparse
import os
import queue
import random
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from tracker import results, tls_helper
from tracker.pdf_report import make_pdf
from tracker.sheet import Account, mask, read_accounts
from tracker.status_rules import classify_status

HERE = Path(__file__).resolve().parent
DOWNLOADS = Path.home() / "Downloads"
PAUSE_BETWEEN_S = (1, 2)   # small gap between clients so portals don't block us


def parse_rows(spec: str | None) -> range | None:
    if not spec:
        return None
    a, _, b = spec.partition("-")
    return range(int(a), int(b or a) + 1)


def _key(column: str) -> str:
    """'BLS ( TOURISM)' and 'bls tourism' are the same column."""
    return "".join(ch for ch in column.lower() if ch.isalnum())


def pick(accounts: list[Account], only: str | None, rows: range | None) -> list[Account]:
    out = accounts
    if only:
        wanted = {_key(c) for c in only.split(",") if c.strip()}
        out = [a for a in out if _key(a.column) in wanted]
    if rows:
        out = [a for a in out if a.row in rows]
    return out


_print_lock = threading.Lock()
# Where progress lines go: the terminal by default; the website swaps in its own.
LOG_SINK = None


def say(*lines: str) -> None:
    """Print a few lines together, so parallel windows don't mix their output."""
    with _print_lock:
        if LOG_SINK:
            LOG_SINK(list(lines))
        else:
            print("\n".join(lines), flush=True)


def check_one(browser, acc: Account, previous: dict, blocked: set[str], tag: str) -> dict:
    """Log in for one client in its own private window and return its report row."""
    from tracker.portals import bls, brazil, gckey, romania, vfs, wes

    # VFS gets (reference, surname), Romania (file number, password) and
    # BLS / Brazil (reference, birth date) in the username/password slots.
    checkers = {"gckey": gckey.check, "wes": wes.check, "vfs": vfs.check,
                "romania": romania.check, "bls": bls.check, "brazil": brazil.check}
    entry = {"row": acc.row, "column": acc.column, "client": acc.name,
             "login": mask(acc.username),
             "checked_at": datetime.now().strftime("%Y-%m-%d %H:%M")}
    if acc.portal in blocked:
        acc.problem = ("Not tried: GCKey blocked this run — retrying now could lock "
                       "the client's account. Check by hand or try again tomorrow.")
    if acc.problem:
        entry["problem"] = acc.problem
        say(f"{tag} {acc.label()}", f"    ✖ skipped: {acc.problem}")
        return entry

    started = time.monotonic()
    context = browser.new_context()       # private window: own cookies, like incognito
    page = context.new_page()
    res = None
    try:
        extra = (acc.name,) if acc.portal == "brazil" else ()   # Brazil also needs the surname
        res = checkers[acc.portal](page, acc.username, acc.password, acc.label(), *extra)
    except Exception as exc:               # one broken account must not stop the run
        entry["problem"] = f"Unexpected error: {type(exc).__name__}: {str(exc)[:150]}"
    finally:
        # Picture of whatever the portal is showing now, for the PDF
        # (or of the result window, if the portal opened a new one).
        try:
            entry["_screenshot"] = (res.screenshot if res and res.screenshot
                                    else page.screenshot(full_page=True, timeout=20_000))
        except Exception:
            entry["_screenshot"] = None
        context.close()

    extra = []
    if res:
        entry.update(status=res.status, details=res.details, problem=res.problem)
        if res.problem.startswith("No VFS tracking page found"):
            entry["_screenshot"] = None    # a VFS "404" page isn't worth a PDF page
        if res.problem.startswith(gckey.BLOCKED):
            blocked.add("gckey")
            extra.append("    🛑 GCKey security check failed — stopping all GCKey checks "
                         "for this run to protect clients' accounts.")
        if not res.problem:
            entry["category"] = classify_status(acc.portal, res.status)
    before = previous.get((acc.row, acc.column))
    if before is not None and entry.get("status") and before != entry["status"]:
        entry["changed"] = "YES"
    took = f"  ({time.monotonic() - started:.1f}s)"
    result = ("    ✖ " + entry["problem"] if entry.get("problem")
              else f"    ✔ {entry.get('category', '')}: {entry.get('status', '')}") + took
    say(f"{tag} {acc.label()}", *extra, result)
    return entry


def ask_in_terminal(windows: int) -> None:
    """Default way to confirm the CAPTCHAs: type yes in the terminal."""
    while True:
        answer = input("   Have you finished all the CAPTCHAs? Type yes and press Enter: ")
        if answer.strip().lower() in ("yes", "y", "نعم", "ايوه", "اه"):
            return
        say("   OK, take your time. Type yes when every window shows its result.")


def run(accounts: list[Account], previous: dict, parallel: int,
        confirm=ask_in_terminal, tls_step=None) -> list[dict]:
    """WES clients run `parallel` at a time; CAPTCHA portals (VFS, Romania
    e-Visa, BLS) all at once, waiting for one "yes" in the terminal; GCKey always
    one at a time (it needs a person for OTPs and blocks bursts of logins).
    TLS clients go one by one through tls_helper (terminal, or the website via tls_step)."""
    from playwright.sync_api import sync_playwright

    from tracker.portals import captcha_gate

    total = len(accounts)
    report: list[dict | None] = [None] * total
    blocked: set[str] = set()

    def worker(jobs: queue.Queue) -> None:
        with sync_playwright() as p:
            # Each worker has its own Microsoft Edge (installed on every Windows PC).
            browser = p.chromium.launch(channel="msedge", headless=False)
            try:
                while True:
                    try:
                        i, acc = jobs.get_nowait()
                    except queue.Empty:
                        return
                    report[i] = check_one(browser, acc, previous, blocked, f"[{i + 1}/{total}]")
                    if not jobs.empty():
                        time.sleep(random.uniform(*PAUSE_BETWEEN_S))
            finally:
                browser.close()

    def run_pool(items: list[tuple[int, Account]], workers: int, while_running=None) -> None:
        if not items:
            return
        jobs: queue.Queue = queue.Queue()
        for item in items:
            jobs.put(item)
        threads = [threading.Thread(target=worker, args=(jobs,), daemon=True)
                   for _ in range(min(workers, len(items)))]
        for t in threads:
            t.start()
            time.sleep(0.7)     # stagger start-up so logins don't all hit in the same instant
        if while_running:
            while_running()
        for t in threads:
            t.join()

    def ask_when_captchas_done(windows: int) -> None:
        """Wait until every CAPTCHA form is filled, then ask the employee in the terminal."""
        captcha_gate.wait_until_all_ready(windows)
        say("",
            f"⏸  {windows} window(s) are ready (VFS / Romania e-Visa / BLS / Brazil).",
            "   In EACH window: type the CAPTCHA code and press Enter "
            "(or click Submit / Continuă).",
            "   BLS windows: click Verify, pick the pictures, then click Submit.",
            "   Brazil windows: tick the hCaptcha box (and pictures), then click SEARCH.",
            "   Wait until each window shows its result.")
        confirm(windows)
        say("   ✔ Reading results and taking screenshots…", "")
        captcha_gate.user_said_yes()

    indexed = list(enumerate(accounts))
    captcha_items = [x for x in indexed if x[1].portal in captcha_gate.PORTALS]
    tls_items = [x for x in indexed if x[1].portal == "tls"]
    others = [x for x in indexed
              if x[1].portal not in ("gckey", "tls") and x not in captcha_items]
    windows = sum(1 for _, a in captcha_items if not a.problem)

    run_pool(others, parallel)
    # Every CAPTCHA client gets its own window at the same time, so one "yes" covers them all.
    captcha_gate.reset()
    run_pool(captcha_items, len(captcha_items),
             while_running=(lambda: ask_when_captchas_done(windows)) if windows else None)
    # TLS (Cloudflare) refuses controlled browsers: a person logs in, the helper assists.
    tls_helper.run(tls_items, report, previous, step=tls_step, say=say)
    run_pool([x for x in indexed if x[1].portal == "gckey"], 1)
    return [r for r in report if r is not None]


def save_outputs(report: list[dict], out_dir: Path, label: str = "") -> tuple[Path, Path | None]:
    """Results workbook (in out_dir) + screenshots PDF (in Downloads)."""
    path = results.write(out_dir, report)
    name = f"Tracking screenshots{' ' + label if label else ''} {datetime.now():%Y-%m-%d %H-%M}.pdf"
    pdf = make_pdf([(r.get("client", ""), r.get("_screenshot")) for r in report], DOWNLOADS / name)
    return path, pdf


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("workbook")
    ap.add_argument("--only", help='column(s), comma-separated, e.g. "WES" or '
                                   '"VFS,Romania,ROMANIA STUDY"')
    ap.add_argument("--rows", help="row range, e.g. 4-20")
    ap.add_argument("--dry-run", action="store_true", help="list what would be checked, log in to nothing")
    ap.add_argument("--parallel", type=int, default=0,
                    help="how many WES clients to check at the same time "
                         "(default: all of them; GCKey is always 1)")
    args = ap.parse_args()

    accounts = pick(read_accounts(args.workbook), args.only, parse_rows(args.rows))
    ready = [a for a in accounts if not a.problem]
    print(f"{len(accounts)} clients found, {len(ready)} ready to check, "
          f"{len(accounts) - len(ready)} with a problem in the sheet.\n")

    if args.dry_run:
        for a in accounts:
            flag = f"  ✖ {a.problem}" if a.problem else ""
            print(f"  {a.label():55}  {a.portal:6} login {mask(a.username)}{flag}")
        return

    out_dir = HERE / "results"
    started = time.monotonic()
    parallel = args.parallel if args.parallel > 0 else max(1, len(accounts))
    report = run(accounts, results.previous_statuses(out_dir), parallel)
    print(f"\nAll checks took {time.monotonic() - started:.0f}s.")
    path, pdf = save_outputs(report, out_dir)
    bad = sum(1 for r in report if r.get("problem"))
    changed = sum(1 for r in report if r.get("changed") == "YES")
    print(f"\nDone: {len(report) - bad} checked, {changed} changed since last run, "
          f"{bad} need a manual look.\nResults: {path}")
    if pdf:
        print(f"Screenshots PDF: {pdf}")
        os.startfile(pdf)   # opens it so staff see it straight away


if __name__ == "__main__":
    main()
