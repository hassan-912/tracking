"""One-time copy of clients from the Excel workbooks into the website.

    python import_clients.py "Works Sheet.xlsx" "BLS,TLS,VFS.xlsx"

A category that already has clients in the website is left alone (so running
this twice doesn't double everyone); add --replace to wipe and re-import.
The Excel files are only read, never changed.
"""
from __future__ import annotations

import argparse
import re
import sys

from tracker import clients_db
from tracker.sheet import read_accounts

# Excel column (letters only, lower case) -> website category
COLUMN_TO_CATEGORY = {
    "wes": "wes", "wesicap": "wes",
    "blstourism": "bls_tourism", "blsstudy": "bls_study",
    "vfs": "vfs", "romania": "vfs",
    "romaniastudy": "romania_study",
    "brazil": "brazil",
}


def _key(column: str) -> str:
    return re.sub(r"[^a-z]", "", column.lower())


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser()
    ap.add_argument("workbooks", nargs="+")
    ap.add_argument("--replace", action="store_true", help="wipe each category first")
    args = ap.parse_args()

    found: dict[str, list[dict]] = {}
    for path in args.workbooks:
        for acc in read_accounts(path):
            category = COLUMN_TO_CATEGORY.get(_key(acc.column))
            if acc.portal == "tls":     # Germany or France, from the note in the cell
                category = "tls_france" if acc.site == "fr" else "tls_germany"
            if not category:
                continue            # GCKey, Almaviva… are not in the website
            note = ("" if acc.portal == "tls" or _key(acc.column) == category.replace("_", "")
                    else acc.column)
            if acc.problem:
                note = (note + " · " if note else "") + f"Check: {acc.problem} (Excel row {acc.row})"
            rows = found.setdefault(category, [])
            if any(r["ref"] == acc.username and r["secret"] == acc.password for r in rows):
                continue            # same client in both workbooks (they share sheets)
            rows.append({"name": acc.name, "ref": acc.username, "secret": acc.password,
                         "notes": note})

    for category, rows in found.items():
        title = clients_db.CATEGORIES[category].title
        if args.replace:
            clients_db.save(category, [])
        elif clients_db.count(category):
            print(f"{title:14} already has clients in the website: skipped (use --replace)")
            continue
        clients_db.add_many(category, rows)
        problems = sum(1 for r in rows if "Check:" in r["notes"])
        print(f"{title:14} {len(rows)} imported" + (f", {problems} need checking" if problems else ""))


if __name__ == "__main__":
    main()
