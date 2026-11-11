"""Derive Level, Claremont flag, and Priority for a contact."""
from __future__ import annotations

import re

from .config import CLAREMONT_SCHOOLS, SOCAL_MARKERS
from .models import Contact

LEVELS = ["Analyst", "Associate", "VP", "Director", "MD", "Other"]

_LEVEL_RULES = [
    ("MD", r"\b(managing director|md|partner|founder|ceo|chief|head of|co-head|principal)\b"),
    ("Director", r"\b(director|executive director|senior vice president|svp)\b"),
    ("VP", r"\b(vice president|vp)\b"),
    ("Associate", r"\bassociate\b"),
    ("Analyst", r"\banalyst\b"),
]


def detect_level(title: str) -> str:
    t = (title or "").lower()
    # "Associate Director" / "Analyst, Director" edge cases: highest matching rank wins.
    for level, pat in _LEVEL_RULES:
        if re.search(pat, t):
            return level
    return "Other"


def is_claremont(*texts: str) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(s in blob for s in CLAREMONT_SCHOOLS)


def is_socal(*texts: str) -> bool:
    blob = " " + " ".join(t for t in texts if t).lower() + " "
    return any(m in blob for m in SOCAL_MARKERS)


def priority_for(c: Contact) -> int:
    if c.claremont_alum or is_claremont(c.school, c.notes):
        return 1
    if c.level in ("Analyst", "Associate"):
        return 2
    if is_socal(c.location, c.notes):
        return 3
    return 4


def enrich(c: Contact) -> Contact:
    """Fill level / claremont_alum / priority in place and return the contact."""
    c.level = detect_level(c.title)
    c.claremont_alum = c.claremont_alum or is_claremont(c.school, c.notes)
    c.priority = priority_for(c)
    return c
