"""Contact record and its mapping to spreadsheet columns."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, fields, asdict
from typing import Any

COLUMNS = [
    "ID", "Priority", "Firm", "Firm Type", "First", "Last", "Title", "Level",
    "Group", "Location", "School", "Claremont Alum", "LinkedIn", "Email",
    "Email Status", "Email Alternates", "Phone", "Source", "Notes", "Subject",
    "Draft", "Status", "Date Drafted", "Date Pushed", "Date Sent",
    "Follow-up Due", "Reply Notes", "Draft Model", "Confidence", "Verify URL", "Roster URL", "Registered Firm", "Referred By",
]

STATUS_NEW = "New"
STATUS_DRAFTED = "Drafted"
STATUS_IN_GMAIL = "In Gmail"
STATUS_SENT = "Sent"
STATUS_REPLIED = "Replied"
STATUS_CHAT_DONE = "Chat Done"
STATUS_BOUNCED = "Bounced"
STATUS_NO_RESPONSE = "No Response"


@dataclass
class Contact:
    firm: str
    first: str
    last: str
    title: str = ""
    id: str = ""
    priority: int = 4
    firm_type: str = ""
    level: str = ""
    group: str = ""
    location: str = ""
    school: str = ""
    claremont_alum: bool = False
    linkedin: str = ""
    email: str = ""
    email_status: str = ""
    email_alternates: str = ""
    phone: str = ""
    source: str = ""
    notes: str = ""
    subject: str = ""
    draft: str = ""
    status: str = STATUS_NEW
    date_drafted: str = ""
    date_pushed: str = ""
    date_sent: str = ""
    follow_up_due: str = ""
    reply_notes: str = ""
    draft_model: str = ""
    confidence: str = ""
    verify_url: str = ""
    roster_url: str = ""
    registered_firm: str = ""
    referred_by: str = ""

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()

    @property
    def key(self) -> str:
        return dedup_key(self.first, self.last, self.firm)

    def to_row(self) -> list[Any]:
        d = asdict(self)
        return [
            d["id"], d["priority"], d["firm"], d["firm_type"], d["first"], d["last"],
            d["title"], d["level"], d["group"], d["location"], d["school"],
            "Yes" if d["claremont_alum"] else "", d["linkedin"], d["email"],
            d["email_status"], d["email_alternates"], d["phone"], d["source"],
            d["notes"], d["subject"], d["draft"], d["status"], d["date_drafted"],
            d["date_pushed"], d["date_sent"], d["follow_up_due"], d["reply_notes"],
            d["draft_model"], d["confidence"], d["verify_url"], d["roster_url"], d["registered_firm"],
            d["referred_by"],
        ]

    @classmethod
    def from_row(cls, row: list[Any]) -> "Contact":
        vals = list(row) + [None] * (len(COLUMNS) - len(row))
        s = lambda v: "" if v is None else str(v).strip()  # noqa: E731
        try:
            priority = int(vals[1]) if vals[1] not in (None, "") else 4
        except (TypeError, ValueError):
            priority = 4
        return cls(
            id=s(vals[0]), priority=priority, firm=s(vals[2]), firm_type=s(vals[3]),
            first=s(vals[4]), last=s(vals[5]), title=s(vals[6]), level=s(vals[7]),
            group=s(vals[8]), location=s(vals[9]), school=s(vals[10]),
            claremont_alum=s(vals[11]).lower() in ("yes", "y", "true", "1"),
            linkedin=s(vals[12]), email=s(vals[13]), email_status=s(vals[14]),
            email_alternates=s(vals[15]), phone=s(vals[16]), source=s(vals[17]),
            notes=s(vals[18]), subject=s(vals[19]), draft=s(vals[20]),
            status=s(vals[21]) or STATUS_NEW, date_drafted=s(vals[22]),
            date_pushed=s(vals[23]), date_sent=s(vals[24]),
            follow_up_due=s(vals[25]), reply_notes=s(vals[26]), draft_model=s(vals[27]),
            confidence=s(vals[28]), verify_url=s(vals[29]), roster_url=s(vals[30]),
            registered_firm=s(vals[31]), referred_by=s(vals[32]),
        )


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def dedup_key(first: str, last: str, firm: str) -> str:
    return f"{_norm(first)}|{_norm(last)}|{_norm(firm)}"


def split_name(full: str) -> tuple[str, str]:
    """'Jane Q. Doe, CFA' -> ('Jane', 'Doe'). Drops credentials and middle initials."""
    full = re.split(r",", full.strip())[0]
    parts = [p for p in full.split() if p.strip(".")]
    parts = [p for p in parts if not (len(p.strip(".")) == 1 and len(parts) > 2)]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], parts[-1]


assert len(fields(Contact)) == len(COLUMNS), "Contact fields and COLUMNS must stay in sync"
