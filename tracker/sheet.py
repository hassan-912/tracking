"""Read client logins from the works workbook.

"Status" sheet (headers on row 3). Each cell holds several lines for one client:

    Canada Tourism / Canada Study : username, password
    WES / WES ICAP                : full name, email, password
    FEE (GCKey)                   : full name, username (in RED), password (last line)

"status 2" sheet (headers on row 1):

    BLS (Tourism) / BLS (Study)   : BLS reference, date of birth (day/month/year), full name
    VFS / Romania                 : VFS reference, surname, full name
    TLS                           : email, password (blank = the shared password in
                                    tls_password.txt), notes such as "Germany Tourism"
    Brazil                        : recovery code (10 letters/numbers), date of birth, full name
    Romania Study                 : e-Visa file number (E + 14 digits) and password, any order

Australia and other columns are ignored.
"""
from __future__ import annotations

import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl
from openpyxl.cell.rich_text import CellRichText, TextBlock

# Sheet name -> (header row, first data row, {column header -> (portal, cell layout)})
SHEETS = {
    "Status": (3, 4, {
        "canada tourism": ("gckey", "user_pass"),
        "canada study": ("gckey", "user_pass"),
        "fee": ("gckey", "fee"),
        "wes": ("wes", "name_email_pass"),
        "wes icap": ("wes", "name_email_pass"),
    }),
    # VFS cells: reference · surname · full name. The "Romania" column
    # also holds VFS references (NLD/…, FRA/…).
    "status 2": (1, 2, {
        # BLS Spain (Egypt): reference · date of birth · full name.
        "bls ( tourism)": ("bls", "ref_dob_name"),
        "bls (tourism)": ("bls", "ref_dob_name"),
        "bls (study)": ("bls", "ref_dob_name"),
        "vfs": ("vfs", "ref_surname_name"),
        "romania": ("vfs", "ref_surname_name"),
        # Romania e-Visa: file number (E + 14 digits) and password, in either order.
        "romania study": ("romania", "evisa_number_pass"),
        # Brazil (SCI visa form): recovery code · date of birth · full name.
        "brazil": ("brazil", "code_dob_name"),
        # TLScontact: email, maybe a password, maybe a note naming the country.
        "tls": ("tls", "tls"),
    }),
}
BLS_REF_RE = re.compile(r"^[A-Z]{3}\d{6,}$", re.I)
BRAZIL_CODE_RE = re.compile(r"^[A-Z0-9]{10}$", re.I)
# First line of a "reference · date of birth · name" cell, per layout.
FIRST_LINE = {
    "ref_dob_name": (BLS_REF_RE, "a BLS reference (like CAI12345678901)"),
    "code_dob_name": (BRAZIL_CODE_RE, "a Brazil recovery code (10 letters/numbers)"),
}
DATE_RE = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{4})$")
EVISA_NUMBER_RE = re.compile(r"^E\d{14}$", re.I)
VFS_REF_RE = re.compile(r"^[A-Z]{3,4}/[A-Z0-9/]+$", re.I)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

# Shared TLS password: typed by staff into this file, never into the code or the sheet.
TLS_PASSWORD_FILE = Path(__file__).resolve().parents[1] / "tls_password.txt"
# A word in a TLS note -> which TLScontact site the account belongs to.
TLS_COUNTRIES = {"germany": "de", "german": "de", "france": "fr", "french": "fr"}
TLS_DEFAULT_COUNTRY = "de"     # most TLS clients are Germany


@dataclass
class Account:
    row: int                 # Excel row number, so staff can find it
    column: str              # header, e.g. "FEE"
    portal: str              # "gckey", "wes", "vfs" or "romania"
    name: str = ""
    username: str = ""       # GCKey username, WES email, VFS reference or e-Visa file number
    password: str = field(default="", repr=False)   # never printed; VFS: surname, BLS: birth date
    problem: str = ""        # filled when the cell can't be used
    site: str = ""           # TLS: "de" or "fr"

    def label(self) -> str:
        who = self.name or mask(self.username)
        return f"row {self.row} · {self.column} · {who}"


def mask(text: str) -> str:
    """Show just enough to recognise an account: 'ab****@gmail.com'."""
    if not text:
        return "?"
    if "@" in text:
        local, domain = text.split("@", 1)
        return f"{local[:2]}****@{domain}"
    return f"{text[:2]}****"


def _is_red(font) -> bool:
    c = getattr(font, "color", None)
    if c is None or c.type != "rgb" or not c.rgb or len(c.rgb) < 6:
        return False
    r, g, b = (int(c.rgb[-6:][i:i + 2], 16) for i in (0, 2, 4))
    return r >= 0xC0 and g < 0x60 and b < 0x60


def _lines(value) -> list[tuple[str, bool]]:
    """Split a cell into non-empty lines as (text, is_red)."""
    out: list[tuple[str, bool]] = []
    if isinstance(value, CellRichText):
        current, red = "", False
        for run in value:
            text = run.text if isinstance(run, TextBlock) else str(run)
            run_red = isinstance(run, TextBlock) and _is_red(run.font)
            parts = text.split("\n")
            for i, part in enumerate(parts):
                if i:
                    out.append((current, red))
                    current, red = "", False
                if part.strip():
                    current += part
                    red = red or run_red
        out.append((current, red))
    else:
        out = [(line, False) for line in str(value).split("\n")]
    return [(t.strip(), r) for t, r in out if t.strip()]


def _shared_tls_password() -> str:
    if not TLS_PASSWORD_FILE.exists():
        return ""
    return TLS_PASSWORD_FILE.read_text(encoding="utf-8").strip()


def _iso_date(text: str) -> str:
    """'7/3/1990' (day/month/year, as the staff write it) -> '1990-03-07'."""
    from datetime import date
    m = DATE_RE.match(text.strip())
    if not m:
        return ""
    day, month, year = (int(x) for x in m.groups())
    try:
        return date(year, month, day).isoformat()
    except ValueError:      # e.g. 31/2/1990, or written month-first by mistake
        return ""


def _parse(row: int, column: str, portal: str, layout: str, value) -> Account:
    acc = Account(row=row, column=column, portal=portal)
    lines = _lines(value)
    texts = [t for t, _ in lines]

    if layout == "user_pass":
        if len(texts) < 2:
            acc.problem = "Cell needs a username line and a password line"
            return acc
        # First two lines; anything after them is staff notes.
        acc.username, acc.password = texts[0], texts[1]

    elif layout == "name_email_pass":
        emails = [t for t in texts if EMAIL_RE.match(t)]
        if not emails:
            acc.problem = "No email found in cell"
            return acc
        acc.username = emails[0]
        acc.name = texts[0] if texts[0] != emails[0] else ""
        if texts[-1] == emails[0]:
            acc.problem = "No password after the email"
            return acc
        acc.password = texts[-1]

    elif layout == "fee":
        red = [t for t, is_red in lines if is_red]
        if red:
            acc.username = red[0]
        elif len(texts) >= 3:
            acc.username = texts[1]
        else:
            acc.problem = "No red username found in cell"
            return acc
        acc.password = texts[-1]
        if lines[0][1] is False and texts[0] != acc.username:
            acc.name = texts[0]
        if acc.password == acc.username:
            acc.problem = "No password after the username"

    elif layout == "ref_surname_name":
        if not texts or not VFS_REF_RE.match(texts[0].replace(" ", "")):
            acc.problem = "First line is not a VFS reference (like NLD/CAI/123456/1234/01)"
            return acc
        acc.username = texts[0].replace(" ", "").upper()
        if len(texts) < 2:
            acc.problem = "No surname under the reference"
            return acc
        acc.password = texts[1]
        acc.name = texts[2] if len(texts) > 2 else ""

    elif layout in FIRST_LINE:
        pattern, what = FIRST_LINE[layout]
        if not texts or not pattern.match(texts[0].replace(" ", "")):
            acc.problem = f"First line is not {what}"
            return acc
        acc.username = texts[0].replace(" ", "").upper()
        dob = _iso_date(texts[1]) if len(texts) > 1 else ""
        if not dob:
            acc.problem = "Second line is not a date of birth (day/month/year)"
            return acc
        acc.password = dob
        acc.name = texts[2] if len(texts) > 2 else ""

    elif layout == "tls":
        emails = [t for t in texts if EMAIL_RE.match(t)]
        if not emails:
            acc.problem = "No email found in cell"
            return acc
        acc.username = emails[0]
        rest = [t for t in texts if t != emails[0]]
        # Words only (e.g. "Germany Business") = a note; anything else = the password.
        notes = [t for t in rest if re.fullmatch(r"[^\W\d_]+(\s+[^\W\d_]+)*", t)]
        passwords = [t for t in rest if t not in notes]
        words = {w for note in notes for w in note.lower().split()}
        acc.site = next((TLS_COUNTRIES[w] for w in words if w in TLS_COUNTRIES),
                        TLS_DEFAULT_COUNTRY)
        if passwords:
            acc.password = passwords[0]
        else:
            acc.password = _shared_tls_password()
            if not acc.password:
                acc.problem = ("No password in the cell and no shared password yet: "
                               "type it into tls_password.txt")

    elif layout == "evisa_number_pass":
        numbers = [t for t in texts if EVISA_NUMBER_RE.match(t.replace(" ", ""))]
        if not numbers:
            acc.problem = "No e-Visa file number (E + 14 digits) in cell"
            return acc
        acc.username = numbers[0].replace(" ", "").upper()
        others = [t for t in texts if t != numbers[0]]
        if not others:
            acc.problem = "No password next to the file number"
            return acc
        acc.password = others[0]

    return acc


def read_accounts(path: str | Path) -> list[Account]:
    with warnings.catch_warnings():
        # The workbook has cells Excel mis-flags as dates and pivot caches
        # openpyxl can't follow; both are harmless for reading.
        warnings.simplefilter("ignore")
        wb = openpyxl.load_workbook(path, rich_text=True, data_only=True)
    accounts: list[Account] = []
    found = [name for name in SHEETS if name in wb.sheetnames]
    if not found:
        raise SystemExit(f"None of the sheets {list(SHEETS)} were found in {path}")
    for sheet_name in found:
        header_row, first_row, columns = SHEETS[sheet_name]
        ws = wb[sheet_name]
        wanted: dict[int, tuple[str, str, str]] = {}
        for cell in ws[header_row]:
            key = re.sub(r"\s+", " ", str(cell.value or "").strip().lower())
            if key in columns:
                portal, layout = columns[key]
                wanted[cell.column] = (str(cell.value).strip(), portal, layout)

        for row in ws.iter_rows(min_row=first_row):
            for cell in row:
                if cell.column not in wanted or not str(cell.value or "").strip():
                    continue
                column, portal, layout = wanted[cell.column]
                accounts.append(_parse(cell.row, column, portal, layout, cell.value))
    return accounts
