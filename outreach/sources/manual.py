"""Manual contact entry: pipe-delimited lines or a CSV file."""
from __future__ import annotations

import csv
from pathlib import Path

from ..models import Contact, split_name

PIPE_FIELDS = ["name", "title", "firm", "linkedin", "notes"]
CSV_ALIASES = {
    "name": ("name", "full name", "full_name"),
    "first": ("first", "first name", "first_name"),
    "last": ("last", "last name", "last_name"),
    "title": ("title", "position", "role"),
    "firm": ("firm", "company", "organization", "employer"),
    "linkedin": ("linkedin", "linkedin url", "linkedin_url", "profile"),
    "notes": ("notes", "note", "comment"),
    "group": ("group", "division", "team"),
    "location": ("location", "city", "office"),
    "school": ("school", "university", "college", "education"),
    "email": ("email", "e-mail", "work email"),
    "phone": ("phone", "phone number", "mobile"),
}


def parse_pipe_lines(text: str, default_firm: str = "") -> list[Contact]:
    """Each line: Name | Title | Firm | LinkedIn URL | Notes  (trailing fields optional)."""
    out: list[Contact] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        parts += [""] * (len(PIPE_FIELDS) - len(parts))
        name, title, firm, linkedin, notes = parts[:5]
        first, last = split_name(name)
        if not first:
            continue
        out.append(Contact(firm=firm or default_firm, first=first, last=last, title=title,
                           linkedin=linkedin, notes=notes, source="manual"))
    return out


def _pick(row: dict, key: str) -> str:
    lower = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
    for alias in CSV_ALIASES[key]:
        if alias in lower and lower[alias]:
            return lower[alias]
    return ""


def parse_csv(path: Path, default_firm: str = "") -> list[Contact]:
    out: list[Contact] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            first, last = _pick(row, "first"), _pick(row, "last")
            if not first:
                first, last = split_name(_pick(row, "name"))
            if not first:
                continue
            c = Contact(
                firm=_pick(row, "firm") or default_firm, first=first, last=last,
                title=_pick(row, "title"), linkedin=_pick(row, "linkedin"), notes=_pick(row, "notes"),
                group=_pick(row, "group"), location=_pick(row, "location"), school=_pick(row, "school"),
                phone=_pick(row, "phone"), source="csv",
            )
            email = _pick(row, "email")
            if email:
                c.email, c.email_status = email, "from_api"
            out.append(c)
    return out
