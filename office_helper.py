"""Office PC helper for the online tracking website.

Keep it running on the office PC (double-click "Start office helper.bat"). Every few
seconds it asks the website whether someone pressed "Check"; if so it opens the
browser windows here, waits for "I've finished all the CAPTCHAs" on the website,
then sends the statuses, the screenshots PDF and the results Excel back.

Settings come from office_helper.env (never uploaded to GitHub):
    SITE_URL=https://your-site.vercel.app
    AGENT_TOKEN=<the helper's secret key>

    python office_helper.py            # run
    python office_helper.py --upload   # one-time: copy clients from data/clients.db to the website
"""
from __future__ import annotations

import base64
import json
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENV_FILE = HERE / "office_helper.env"
RESULTS_DIR = HERE / "results" / "online"
FILE_PART = 2_500_000          # bytes per upload (Vercel caps a request at 4.5 MB)
POLL_S = 5


def settings() -> tuple[str, str]:
    if not ENV_FILE.exists():
        raise SystemExit(f"Missing {ENV_FILE.name} (SITE_URL and AGENT_TOKEN).")
    values = dict(line.split("=", 1) for line in ENV_FILE.read_text(encoding="utf-8").splitlines()
                  if "=" in line and not line.lstrip().startswith("#"))
    url, token = values.get("SITE_URL", "").strip().rstrip("/"), values.get("AGENT_TOKEN", "").strip()
    if not url or not token:
        raise SystemExit(f"{ENV_FILE.name} needs SITE_URL and AGENT_TOKEN.")
    return url, token


SITE, TOKEN = "", ""


def call(path: str, body: dict, attempts: int = 4) -> dict:
    """POST JSON to the website as the office helper; retries short network hiccups."""
    data = json.dumps(body).encode()
    for attempt in range(attempts):
        req = urllib.request.Request(f"{SITE}{path}", data, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=90) as res:
                return json.load(res)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == attempts - 1:
                raise RuntimeError(f"Website answered {e.code}: {e.read()[:200]!r}") from e
        except (urllib.error.URLError, TimeoutError, ConnectionError):
            if attempt == attempts - 1:
                raise
        time.sleep(2 * (attempt + 1))
    return {}


# ---------- one tracking run ----------

class Run:
    def __init__(self, job: dict, clients: list[dict]):
        from tracker.clients_db import CATEGORIES
        self.job_id = job["id"]
        self.category = CATEGORIES[job["category"]]
        self.clients = clients
        self._lines: list[str] = []
        self._lock = threading.Lock()
        self._stop = threading.Event()

    def report(self, **body) -> dict:
        return call(f"/api/agent/jobs/{self.job_id}", body)

    # progress lines -> website, sent in small batches
    def log(self, lines: list[str]) -> None:
        with self._lock:
            self._lines.extend(l for l in lines if l.strip())

    def _flush(self) -> None:
        with self._lock:
            text, self._lines = "".join(l + "\n" for l in self._lines), []
        if text:
            try:
                self.report(log=text)
            except Exception:
                pass

    def _flusher(self) -> None:
        while not self._stop.wait(2):
            self._flush()

    def confirm(self, windows: int) -> None:
        """Instead of typing yes: wait for the website button."""
        self._flush()
        self.report(state="waiting", windows=windows)
        while True:
            answer = self.report()
            if answer.get("done_clicked") or answer.get("state") in ("cancelled", "missing"):
                break
            time.sleep(2)
        self.report(state="running")

    def accounts(self):
        from tracker import clients_db
        from tracker.sheet import Account
        out = []
        for c in self.clients:
            ref = c["ref"].strip()
            if self.category.portal != "wes":
                ref = ref.replace(" ", "").upper()
            out.append(Account(row=c["id"], column=self.category.title, portal=self.category.portal,
                               name=c["name"], username=ref, password=c["secret"].strip(),
                               problem=clients_db.problem_of(self.category.key, c["ref"], c["secret"])))
        return out

    def upload(self, kind: str, path: Path | None) -> None:
        if not path or not path.exists():
            return
        data = path.read_bytes()
        for part, start in enumerate(range(0, len(data), FILE_PART)):
            chunk = base64.b64encode(data[start:start + FILE_PART]).decode()
            self.report(file={"kind": kind, "part": part, "data": chunk})

    def go(self) -> None:
        import run_tracker
        from tracker import results

        print(f"\n▶ {self.category.title}: {len(self.clients)} client(s) (run {self.job_id})")
        run_tracker.LOG_SINK = self.log
        flusher = threading.Thread(target=self._flusher, daemon=True)
        flusher.start()
        try:
            accounts = self.accounts()
            report = run_tracker.run(accounts, results.previous_statuses(RESULTS_DIR),
                                     max(1, len(accounts)), confirm=self.confirm)
            xlsx, pdf = run_tracker.save_outputs(report, RESULTS_DIR, self.category.title)
            self._flush()
            self.upload("pdf", pdf)
            self.upload("xlsx", xlsx)
            rows = [{"client": r.get("client", ""), "status": r.get("status", ""),
                     "problem": r.get("problem", ""), "changed": r.get("changed", "")} for r in report]
            self.report(state="finished", results=rows, log="Finished.\n")
            print(f"✔ run {self.job_id} finished")
        except Exception as exc:              # report it on the website, keep the helper alive
            self._flush()
            self.report(state="failed", error=f"{type(exc).__name__}: {exc}"[:500])
            print(f"✖ run {self.job_id} failed: {exc}")
        finally:
            self._stop.set()
            run_tracker.LOG_SINK = None


# ---------- one-time upload of the clients ----------

def upload_clients() -> None:
    from tracker import clients_db
    for key, cat in clients_db.CATEGORIES.items():
        rows = clients_db.load(key)
        answer = call("/api/agent/import", {"category": key, "clients": [
            {"name": r["name"], "ref": r["ref"], "secret": r["secret"], "notes": r["notes"]}
            for r in rows]})
        if answer.get("skipped"):
            print(f"{cat.title:14} already has {answer['existing']} client(s) online: left as is")
        else:
            print(f"{cat.title:14} {answer.get('imported', 0)} uploaded")


def main() -> None:
    global SITE, TOKEN
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    SITE, TOKEN = settings()
    if "--upload" in sys.argv:
        upload_clients()
        return
    host = socket.gethostname()
    print(f"Office helper running on {host} for {SITE}\nKeep this window open. Ctrl+C to stop.")
    while True:
        try:
            answer = call("/api/agent/claim", {"host": host})
            if answer.get("job"):
                Run(answer["job"], answer.get("clients", [])).go()
                continue
        except Exception as exc:
            print(f"(website not reachable: {str(exc)[:120]} — retrying)")
        time.sleep(POLL_S)


if __name__ == "__main__":
    main()
