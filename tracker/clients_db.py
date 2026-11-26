"""The website's own client list (SQLite file data/clients.db).

One table, one row per client. What `ref` and `secret` mean depends on the
category (see CATEGORIES). Passwords live only in this local file.
"""
from __future__ import annotations

import re
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from .sheet import (BLS_REF_RE, BRAZIL_CODE_RE, EMAIL_RE, EVISA_NUMBER_RE, VFS_REF_RE,
                    Account)

DB_FILE = Path(__file__).resolve().parents[1] / "data" / "clients.db"


@dataclass(frozen=True)
class Category:
    key: str
    title: str          # shown in the website
    portal: str         # which checker runs it
    ref_label: str      # first login field
    ref_hint: str
    secret_label: str   # second login field
    secret_is_date: bool = False
    secret_is_password: bool = False


CATEGORIES: dict[str, Category] = {c.key: c for c in (
    Category("wes", "WES", "wes", "Email", "client@email.com",
             "Password", secret_is_password=True),
    Category("bls_tourism", "BLS Tourism", "bls", "BLS reference", "CAI12345678901",
             "Date of birth", secret_is_date=True),
    Category("bls_study", "BLS Study", "bls", "BLS reference", "CAI12345678901",
             "Date of birth", secret_is_date=True),
    Category("vfs", "VFS", "vfs", "VFS reference", "NLD/CAI/123456/1234/01",
             "Surname"),
    Category("romania_study", "Romania Study", "romania", "e-Visa file number",
             "E12345678901234", "Password", secret_is_password=True),
    Category("brazil", "Brazil", "brazil", "Recovery code", "AB12CD34EF",
             "Date of birth", secret_is_date=True),
)}

_REF_PATTERNS = {"wes": EMAIL_RE, "bls": BLS_REF_RE, "vfs": VFS_REF_RE,
                 "romania": EVISA_NUMBER_RE, "brazil": BRAZIL_CODE_RE}


@contextmanager
def _connect() -> Iterator[sqlite3.Connection]:
    """Open the database, commit on success, and always close it again
    (several office PCs may save at the same moment)."""
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_FILE, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        con.execute("""CREATE TABLE IF NOT EXISTS clients (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            name TEXT NOT NULL DEFAULT '',
            ref TEXT NOT NULL DEFAULT '',
            secret TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '')""")
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


def load(category: str) -> list[dict]:
    with _connect() as con:
        rows = con.execute("SELECT id, name, ref, secret, notes FROM clients "
                           "WHERE category = ? ORDER BY id", (category,)).fetchall()
    return [dict(r) for r in rows]


def count(category: str) -> int:
    with _connect() as con:
        return con.execute("SELECT COUNT(*) FROM clients WHERE category = ?",
                           (category,)).fetchone()[0]


def save(category: str, rows: list[dict]) -> None:
    """Make the category's clients exactly `rows`: rows with an id are updated,
    rows without one are added, missing ids are removed."""
    now = datetime.now().isoformat(timespec="seconds")
    keep = [r for r in rows if any(str(r.get(k) or "").strip() for k in ("name", "ref", "secret"))]
    with _connect() as con:
        existing = {r["id"] for r in con.execute(
            "SELECT id FROM clients WHERE category = ?", (category,))}
        kept_ids = set()
        for r in keep:
            values = tuple(str(r.get(k) or "").strip() for k in ("name", "ref", "secret", "notes"))
            rid = r.get("id")
            if rid in existing:
                con.execute("UPDATE clients SET name=?, ref=?, secret=?, notes=?, updated_at=? "
                            "WHERE id=?", (*values, now, rid))
                kept_ids.add(rid)
            else:
                con.execute("INSERT INTO clients (category, name, ref, secret, notes, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?)", (category, *values, now))
        for rid in existing - kept_ids:
            con.execute("DELETE FROM clients WHERE id = ?", (rid,))


FIELDS = ("name", "ref", "secret", "notes")


def update(client_id: int, changes: dict) -> None:
    sets = {k: str(v or "").strip() for k, v in changes.items() if k in FIELDS}
    if not sets:
        return
    with _connect() as con:
        con.execute(f"UPDATE clients SET {', '.join(f'{k}=?' for k in sets)}, updated_at=? "
                    "WHERE id=?",
                    (*sets.values(), datetime.now().isoformat(timespec="seconds"), client_id))


def add(category: str, fields: dict) -> None:
    add_many(category, [{k: str(fields.get(k) or "").strip() for k in FIELDS}])


def delete(client_ids: list[int]) -> None:
    with _connect() as con:
        con.executemany("DELETE FROM clients WHERE id = ?", [(i,) for i in client_ids])


def _as_text(value) -> str:
    """Editor cell value -> stored text (dates as YYYY-MM-DD)."""
    if value is None or (isinstance(value, float) and value != value):    # NaN
        return ""
    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T", text) else text


def apply_changes(category: str, ids: list[int], changes: dict) -> None:
    """Save a table editor's changes: {"edited_rows": {row: {col: value}},
    "added_rows": [{col: value}], "deleted_rows": [row]} (rows are positions in `ids`)."""
    portal = CATEGORIES[category].portal

    def clean(fields: dict) -> dict:
        out = {k: _as_text(v).strip() for k, v in fields.items() if k in FIELDS}
        if "ref" in out and portal != "wes":
            out["ref"] = out["ref"].replace(" ", "").upper()
        return out

    for index, fields in changes.get("edited_rows", {}).items():
        update(ids[int(index)], clean(fields))
    for fields in changes.get("added_rows", []):
        fields = clean(fields)
        if any(fields.values()):
            add(category, fields)
    delete([ids[int(i)] for i in changes.get("deleted_rows", [])])


def add_many(category: str, rows: list[dict]) -> int:
    """Append rows (used by the one-time Excel import)."""
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as con:
        con.executemany(
            "INSERT INTO clients (category, name, ref, secret, notes, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [(category, r.get("name", ""), r.get("ref", ""), r.get("secret", ""),
              r.get("notes", ""), now) for r in rows])
    return len(rows)


def problem_of(category: str, ref: str, secret: str) -> str:
    """Why this client can't be checked yet ('' when it can)."""
    cat = CATEGORIES[category]
    ref = ref.strip()
    if not ref:
        return f"{cat.ref_label} is empty"
    pattern = _REF_PATTERNS[cat.portal]
    probe = ref if cat.portal == "wes" else ref.replace(" ", "")
    if not pattern.match(probe):
        return f"{cat.ref_label} doesn't look right (like {cat.ref_hint})"
    if not secret.strip():
        return f"{cat.secret_label} is empty"
    return ""


def to_accounts(category: str, ids: list[int] | None = None) -> list[Account]:
    """The category's clients (or only `ids`) ready for the tracker."""
    cat = CATEGORIES[category]
    out = []
    for r in load(category):
        if ids is not None and r["id"] not in ids:
            continue
        ref = r["ref"].strip()
        if cat.portal != "wes":
            ref = ref.replace(" ", "").upper()
        out.append(Account(row=r["id"], column=cat.title, portal=cat.portal, name=r["name"],
                           username=ref, password=r["secret"].strip(),
                           problem=problem_of(category, r["ref"], r["secret"])))
    return out
