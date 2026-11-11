"""Outreach Contacts.xlsx: the tool's database."""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from .config import CONTACTS_XLSX
from .models import (
    COLUMNS, Contact, STATUS_BOUNCED, STATUS_CHAT_DONE, STATUS_DRAFTED, STATUS_IN_GMAIL,
    STATUS_NEW, STATUS_NO_RESPONSE, STATUS_REPLIED, STATUS_SENT,
)

SHEET = "Contacts"
SUMMARY = "Summary"
CONVOS = "My Conversations"
# Anyone who has actually engaged - these get their own front tab so notes are easy to find.
TALKED = ("Replied", "Chat Scheduled", "Chat Done")
STATUSES = [STATUS_NEW, STATUS_DRAFTED, STATUS_IN_GMAIL, STATUS_SENT, STATUS_REPLIED,
            STATUS_CHAT_DONE, STATUS_BOUNCED, STATUS_NO_RESPONSE]

WIDTHS = {
    "ID": 8, "Priority": 8, "Firm": 24, "Firm Type": 9, "First": 12, "Last": 14, "Title": 30,
    "Level": 10, "Group": 20, "Location": 18, "School": 20, "Claremont Alum": 9, "LinkedIn": 30,
    "Email": 32, "Email Status": 11, "Email Alternates": 30, "Phone": 14, "Source": 9, "Notes": 30,
    "Subject": 40, "Draft": 80, "Status": 12, "Date Drafted": 12, "Date Pushed": 12,
    "Date Sent": 12, "Follow-up Due": 12, "Reply Notes": 30, "Draft Model": 11, "Confidence": 20, "Verify URL": 16, "Roster URL": 16, "Registered Firm": 34, "Referred By": 22,
}

HEADER_FILL = PatternFill("solid", fgColor="1F3864")
HEADER_FONT = Font(bold=True, color="FFFFFF")
PRIORITY_FILL = {1: "C6EFCE", 2: "DDEBF7", 3: "FFF2CC"}


class SheetError(RuntimeError):
    pass


class ContactSheet:
    def __init__(self, path: Path = CONTACTS_XLSX):
        self.path = Path(path)
        self.contacts: list[Contact] = []
        self.migrated_from: int | None = None
        if self.path.exists():
            self._load()

    # -- io -----------------------------------------------------------------
    def _load(self) -> None:
        wb = load_workbook(self.path)
        if SHEET not in wb.sheetnames:
            raise SheetError(f"{self.path.name} has no '{SHEET}' sheet")
        ws = wb[SHEET]
        header = [c.value for c in ws[1]][: len(COLUMNS)]
        if header != COLUMNS:
            # A file written by an older version is fine as long as its header is a leading
            # slice of the current one - the missing columns just come back empty.
            if header == COLUMNS[: len(header)]:
                self.migrated_from = len(header)
            else:
                raise SheetError(
                    f"Header mismatch in {self.path.name}. Expected {COLUMNS}, got {header}. "
                    "Restore the header row or start a new file."
                )
        for row in ws.iter_rows(min_row=2, values_only=True):
            if not any(v not in (None, "") for v in row[: len(COLUMNS)]):
                continue
            self.contacts.append(Contact.from_row(list(row)))

    def save(self) -> None:
        self._assign_ids()
        self.contacts.sort(key=lambda c: (c.priority, c.firm.lower(), c.last.lower(), c.first.lower()))
        wb = Workbook()
        ws = wb.active
        ws.title = SHEET
        ws.append(COLUMNS)
        for i, name in enumerate(COLUMNS, start=1):
            cell = ws.cell(row=1, column=i)
            cell.fill, cell.font = HEADER_FILL, HEADER_FONT
            cell.alignment = Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(i)].width = WIDTHS.get(name, 14)
        draft_col = COLUMNS.index("Draft") + 1
        prio_col = COLUMNS.index("Priority") + 1
        for c in self.contacts:
            ws.append(c.to_row())
            r = ws.max_row
            ws.cell(row=r, column=draft_col).alignment = Alignment(wrap_text=True, vertical="top")
            fill = PRIORITY_FILL.get(c.priority)
            if fill:
                ws.cell(row=r, column=prio_col).fill = PatternFill("solid", fgColor=fill)
        ws.freeze_panes = "G2"
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{max(ws.max_row, 2)}"
        dv = DataValidation(type="list", formula1='"' + ",".join(STATUSES) + '"', allow_blank=True)
        ws.add_data_validation(dv)
        status_letter = get_column_letter(COLUMNS.index("Status") + 1)
        dv.add(f"{status_letter}2:{status_letter}{max(ws.max_row, 2) + 500}")
        self._write_summary(wb)
        self._write_conversations(wb)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        wb.save(self.path)

    def _write_summary(self, wb: Workbook) -> None:
        ws = wb.create_sheet(SUMMARY)
        L = {name: get_column_letter(COLUMNS.index(name) + 1) for name in COLUMNS}
        n = max(len(self.contacts) + 1, 2)
        rng = lambda col: f"{SHEET}!${L[col]}$2:${L[col]}${n + 500}"  # noqa: E731
        ws.append(["Firm", "Type", "Contacts", "P1 Alumni", "Emails Found", "Drafted+", "Sent+", "Replied+"])
        for i in range(1, 9):
            ws.cell(row=1, column=i).font = HEADER_FONT
            ws.cell(row=1, column=i).fill = HEADER_FILL
        firms = sorted({(c.firm, c.firm_type) for c in self.contacts}, key=lambda x: (x[1], x[0]))
        for r, (firm, ftype) in enumerate(firms, start=2):
            f = f"$A{r}"
            ws.append([
                firm, ftype,
                f'=COUNTIF({rng("Firm")},{f})',
                f'=COUNTIFS({rng("Firm")},{f},{rng("Priority")},1)',
                f'=COUNTIFS({rng("Firm")},{f},{rng("Email")},"?*")',
                f'=COUNTIFS({rng("Firm")},{f},{rng("Draft")},"?*")',
                f'=COUNTIFS({rng("Firm")},{f},{rng("Date Sent")},"?*")',
                f'=COUNTIFS({rng("Firm")},{f},{rng("Status")},"{STATUS_REPLIED}")+COUNTIFS({rng("Firm")},{f},{rng("Status")},"{STATUS_CHAT_DONE}")',
            ])
        last = max(len(firms) + 1, 2)
        ws.append([])
        ws.append(["TOTAL", "", f"=SUM(C2:C{last})", f"=SUM(D2:D{last})", f"=SUM(E2:E{last})",
                   f"=SUM(F2:F{last})", f"=SUM(G2:G{last})", f"=SUM(H2:H{last})"])
        ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
        for col, w in zip("ABCDEFGH", (30, 8, 10, 10, 13, 10, 8, 10)):
            ws.column_dimensions[col].width = w
        ws.freeze_panes = "A2"

    def _write_conversations(self, wb: Workbook) -> None:
        """A front tab holding only people Josh has actually spoken to, with the full notes."""
        # Bounced contacts carry an explanatory note but were never a conversation.
        rows = [c for c in self.contacts if c.status in TALKED]
        rows.sort(key=lambda c: (c.status != "Chat Done", c.firm.lower(), c.last.lower()))
        ws = wb.create_sheet(CONVOS, 0)
        cols = ["Name", "Firm", "Title", "Status", "Email", "Phone", "Connection", "Notes"]
        ws.append(cols)
        for i in range(1, len(cols) + 1):
            ws.cell(row=1, column=i).fill = HEADER_FILL
            ws.cell(row=1, column=i).font = HEADER_FONT
        for c in rows:
            ws.append([c.name, c.firm, c.title, c.status, c.email, c.phone, c.notes, c.reply_notes])
            for col in (7, 8):
                ws.cell(row=ws.max_row, column=col).alignment = Alignment(wrap_text=True, vertical="top")
        for letter, width in zip("ABCDEFGH", (20, 22, 34, 16, 30, 30, 34, 120)):
            ws.column_dimensions[letter].width = width
        ws.freeze_panes = "B2"
        if rows:
            ws.auto_filter.ref = f"A1:H{ws.max_row}"

    # -- mutations -----------------------------------------------------------
    def _assign_ids(self) -> None:
        used = {c.id for c in self.contacts if c.id}
        nxt = 1
        for c in self.contacts:
            if c.id:
                continue
            while f"C{nxt:04d}" in used:
                nxt += 1
            c.id = f"C{nxt:04d}"
            used.add(c.id)

    def add(self, new: list[Contact]) -> tuple[list[Contact], list[Contact]]:
        """Append contacts not already present (by first+last+firm). Returns (added, skipped)."""
        keys = {c.key for c in self.contacts}
        added, skipped = [], []
        for c in new:
            if c.key in keys:
                skipped.append(c)
                continue
            keys.add(c.key)
            self.contacts.append(c)
            added.append(c)
        return added, skipped

    def select(self, firm: str | None = None, priority: int | None = None, status: str | None = None,
               limit: int | None = None, group: str | None = None) -> list[Contact]:
        out = self.contacts
        if firm:
            fl = firm.lower()
            out = [c for c in out if fl in c.firm.lower()]
        if group:
            gl = group.lower()
            out = [c for c in out if gl in (c.group or "").lower()]
        if priority is not None:
            out = [c for c in out if c.priority <= priority]
        if status:
            out = [c for c in out if c.status == status]
        out = sorted(out, key=lambda c: (c.priority, c.firm.lower(), c.last.lower()))
        return out[:limit] if limit else out

    def best_by_firm(self) -> dict[str, Contact]:
        """Top-ranked contact per firm, preferring ones with an email and further along in status."""
        order = {s: i for i, s in enumerate(STATUSES)}
        best: dict[str, Contact] = {}
        for c in sorted(self.contacts, key=lambda c: (c.priority, -order.get(c.status, 0), not c.email)):
            best.setdefault(c.firm, c)
        return best
