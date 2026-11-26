"""Write one results workbook per run. Passwords are never written."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

HEADERS = ["Row", "Column", "Client", "Login", "Category", "Status", "Changed?",
           "Problem", "Details", "Checked at"]
FILLS = {
    "Approved": "FFC6EFCE",
    "Refused": "FFFFC7CE",
    "Action needed": "FFFFEB9C",
    "Problem": "FFF4CCCC",
}


def previous_statuses(folder: Path) -> dict[tuple[int, str], str]:
    """Statuses from the most recent earlier results file, keyed by (row, column)."""
    files = sorted(folder.glob("Tracking *.xlsx"))
    if not files:
        return {}
    ws = load_workbook(files[-1], read_only=True).active
    out = {}
    for r in ws.iter_rows(min_row=2, values_only=True):
        if r and r[0] is not None:
            out[(int(r[0]), str(r[1]))] = str(r[5] or "")
    return out


def write(folder: Path, rows: list[dict]) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "Tracking"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFFFF")
        cell.fill = PatternFill("solid", fgColor="FF3D85C6")
    for r in rows:
        ws.append([r.get(h.lower().rstrip("?").replace(" ", "_"), "") for h in HEADERS])
        fill = FILLS.get("Problem" if r.get("problem") else r.get("category", ""))
        if fill:
            for cell in ws[ws.max_row]:
                cell.fill = PatternFill("solid", fgColor=fill)
        if r.get("changed") == "YES":
            ws.cell(ws.max_row, 7).font = Font(bold=True, color="FFC00000")
    widths = [6, 15, 28, 22, 15, 40, 10, 40, 80, 17]
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[ws.cell(1, i).column_letter].width = w
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column == 9)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions
    path = folder / f"Tracking {datetime.now():%Y-%m-%d %H-%M}.xlsx"
    wb.save(path)
    return path
