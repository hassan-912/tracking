"""One tracking run at a time, started from the website and shared by every
office PC looking at it (the browser windows open on the PC running the site).
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import clients_db

RESULTS_DIR = Path(__file__).resolve().parents[1] / "results" / "website"


@dataclass
class Job:
    category: str = ""
    title: str = ""
    started_by: str = ""
    state: str = "idle"          # idle · running · waiting · finished · failed
    windows: int = 0
    log: list[str] = field(default_factory=list)
    report: list[dict] = field(default_factory=list)
    results_file: Path | None = None
    pdf: Path | None = None
    error: str = ""
    started_at: float = 0.0
    finished_at: float = 0.0


class Tracker:
    """Holds the current (or last) job; safe to call from any page/user."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._done = threading.Event()
        self.job = Job()

    @property
    def busy(self) -> bool:
        return self.job.state in ("running", "waiting")

    def start(self, category: str, ids: list[int] | None, started_by: str = "") -> str:
        """Start checking a category (or the chosen client ids). Returns '' or why not."""
        with self._lock:
            if self.busy:
                return f"{self.job.title} tracking is already running — wait for it to finish."
            accounts = clients_db.to_accounts(category, ids)
            if not accounts:
                return "No clients to check."
            self._done.clear()
            self.job = Job(category=category, title=clients_db.CATEGORIES[category].title,
                           started_by=started_by, state="running", started_at=time.time())
        threading.Thread(target=self._run, args=(accounts,), daemon=True).start()
        return ""

    def captchas_done(self) -> None:
        """The 'I've finished the CAPTCHAs' button (replaces typing yes)."""
        self._done.set()

    # ---- runs in the background thread ----

    def _log(self, lines: list[str]) -> None:
        self.job.log.extend(l for l in lines if l.strip())

    def _confirm(self, windows: int) -> None:
        self.job.windows = windows
        self.job.state = "waiting"
        self._done.wait()
        self.job.state = "running"

    def _run(self, accounts) -> None:
        import run_tracker
        from . import results

        job = self.job
        run_tracker.LOG_SINK = self._log
        try:
            ready = [a for a in accounts if not a.problem]
            self._log([f"Checking {len(ready)} {job.title} client(s)…"])
            report = run_tracker.run(accounts, results.previous_statuses(RESULTS_DIR),
                                     max(1, len(accounts)), confirm=self._confirm)
            job.report = [{k: v for k, v in r.items() if k != "_screenshot"} for r in report]
            job.results_file, job.pdf = run_tracker.save_outputs(report, RESULTS_DIR, job.title)
            job.state = "finished"
            self._log(["Finished."])
        except Exception as exc:            # shown on the page instead of crashing the site
            job.error = f"{type(exc).__name__}: {exc}"
            job.state = "failed"
        finally:
            run_tracker.LOG_SINK = None
            job.finished_at = time.time()


def stamp(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M") if ts else ""
