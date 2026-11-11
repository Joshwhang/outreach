"""Write the best contact per firm into the existing internship tracker (cols I and J only)."""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from openpyxl import load_workbook

from .config import BACKUP_DIR, TRACKER_XLSX
from .firms import FirmBook
from .models import (
    Contact, STATUS_CHAT_DONE, STATUS_DRAFTED, STATUS_IN_GMAIL, STATUS_NEW, STATUS_REPLIED, STATUS_SENT,
)

TRACKER_SHEET = "Tracker"
FIRM_COL, CONTACT_COL, STATUS_COL = 1, 9, 10  # A, I, J
EXAMPLE_MARKER = "e.g. "

# our Status -> tracker's Contact Status list
STATUS_MAP = {
    STATUS_NEW: "Not contacted",
    STATUS_DRAFTED: "Not contacted",
    STATUS_IN_GMAIL: "Not contacted",
    STATUS_SENT: "Emailed",
    STATUS_REPLIED: "Ongoing",
    STATUS_CHAT_DONE: "Coffee chat done",
}


def backup(path: Path = TRACKER_XLSX, backup_dir: Path | None = None) -> Path:
    backup_dir = backup_dir or BACKUP_DIR
    backup_dir.mkdir(parents=True, exist_ok=True)
    dest = backup_dir / f"{path.stem}.{datetime.now():%Y%m%d-%H%M%S}{path.suffix}"
    shutil.copy2(path, dest)
    return dest


def contact_label(c: Contact) -> str:
    bits = [c.name]
    if c.title:
        bits.append(c.title)
    if c.claremont_alum:
        bits.append("Claremont alum")
    return ", ".join(bits)


def sync(best_by_firm: dict[str, Contact], firms: FirmBook, path: Path = TRACKER_XLSX,
         force: bool = False, dry_run: bool = False) -> list[tuple[str, str, str]]:
    """Fill Networking Contact / Contact Status for each tracker row whose firm we have a contact for.

    Writes only into empty cells (or the template's 'e.g.' example) unless force=True.
    Returns [(tracker_firm, label, status)] for rows changed.
    """
    if not path.exists():
        raise FileNotFoundError(path)
    # resolve our canonical firm names -> contact
    canon: dict[str, Contact] = {}
    for firm_name, c in best_by_firm.items():
        f = firms.get(firm_name)
        canon[(f.name if f else firm_name).lower()] = c

    wb = load_workbook(path)
    ws = wb[TRACKER_SHEET]
    changes: list[tuple[str, str, str]] = []
    for row in ws.iter_rows(min_row=2):
        tracker_firm = row[FIRM_COL - 1].value
        if not tracker_firm or str(tracker_firm).startswith(("How to use", "•")):
            continue
        f = firms.get(str(tracker_firm))
        key = (f.name if f else str(tracker_firm)).lower()
        c = canon.get(key)
        if c is None:
            continue
        cell_c, cell_s = row[CONTACT_COL - 1], row[STATUS_COL - 1]
        current = str(cell_c.value or "")
        writable = force or not current or current.startswith(EXAMPLE_MARKER)
        if not writable:
            continue
        label, status = contact_label(c), STATUS_MAP.get(c.status, "Not contacted")
        if cell_c.value == label and cell_s.value == status:
            continue
        cell_c.value, cell_s.value = label, status
        changes.append((str(tracker_firm), label, status))
    if changes and not dry_run:
        backup(path)
        wb.save(path)
    return changes
