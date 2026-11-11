"""Firm master list: load firms.csv, resolve aliases, expand email patterns."""
from __future__ import annotations

import csv
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .config import FIRMS_CSV

# Pattern tokens: first, last, f (first initial), l (last initial)
PATTERNS = ["first.last", "flast", "first_last", "firstl", "first", "lastf", "last.first", "f.last", "firstlast"]


@dataclass
class Firm:
    name: str
    type: str                 # IB / AM / WM / RE / PE
    tier: str                 # BB / EB / MM / Regional / AM / WM / RE
    domain: str
    pattern: str              # primary pattern
    alt_patterns: list[str] = field(default_factory=list)
    pattern_confidence: str = "medium"   # high / medium / low
    hq: str = ""
    offices: str = ""
    careers_url: str = ""
    aliases: list[str] = field(default_factory=list)
    active: bool = True
    notes: str = ""

    @property
    def all_names(self) -> list[str]:
        return [self.name, *self.aliases]


LEGAL_SUFFIXES = re.compile(
    r"\b(llc|l\.l\.c|inc|incorporated|corp|corporation|co|company|lp|l\.p|llp|plc|ltd|"
    r"securities|capital|markets|global|holdings|group|usa|america|americas|advisors|advisers|"
    r"services|financial|partners|and|&)\b", re.I)


def normalize_legal_name(name: str) -> str:
    """'GOLDMAN SACHS & CO. LLC' -> 'goldmansachs'. For matching FINRA/SEC registered names."""
    return _norm(LEGAL_SUFFIXES.sub(" ", name or ""))


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", s.lower())


def _ascii_token(s: str) -> str:
    """Lowercase ASCII letters only: 'O'Brien-Smith' -> 'obriensmith'."""
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z]", "", s.lower())


def expand_pattern(pattern: str, first: str, last: str, domain: str) -> str:
    f, l = _ascii_token(first), _ascii_token(last)
    if not f or not domain:
        return ""
    local = {
        "first.last": f"{f}.{l}",
        "flast": f"{f[0]}{l}",
        "first_last": f"{f}_{l}",
        "firstl": f"{f}{l[:1]}",
        "first": f,
        "lastf": f"{l}{f[0]}",
        "last.first": f"{l}.{f}",
        "f.last": f"{f[0]}.{l}",
        "firstlast": f"{f}{l}",
    }.get(pattern)
    if local is None or (not l and pattern != "first"):
        return ""
    return f"{local}@{domain}"


def candidate_emails(firm: Firm, first: str, last: str) -> list[str]:
    """Primary pattern first, then alternates, then the remaining common patterns. De-duplicated."""
    order = [firm.pattern, *firm.alt_patterns, *PATTERNS]
    seen: list[str] = []
    for p in order:
        e = expand_pattern(p, first, last, firm.domain)
        if e and e not in seen:
            seen.append(e)
    return seen


def load_firms(path: Path = FIRMS_CSV) -> list[Firm]:
    firms: list[Firm] = []
    with open(path, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if not (row.get("firm") or "").strip():
                continue
            firms.append(Firm(
                name=row["firm"].strip(),
                type=(row.get("type") or "").strip().upper(),
                tier=(row.get("tier") or "").strip(),
                domain=(row.get("domain") or "").strip().lower(),
                pattern=(row.get("pattern") or "first.last").strip(),
                alt_patterns=[p.strip() for p in (row.get("alt_patterns") or "").split(";") if p.strip()],
                pattern_confidence=(row.get("pattern_confidence") or "medium").strip(),
                hq=(row.get("hq") or "").strip(),
                offices=(row.get("offices") or "").strip(),
                careers_url=(row.get("careers_url") or "").strip(),
                aliases=[a.strip() for a in (row.get("aliases") or "").split(";") if a.strip()],
                active=(row.get("active") or "yes").strip().lower() in ("yes", "y", "true", "1"),
                notes=(row.get("notes") or "").strip(),
            ))
    return firms


class FirmBook:
    def __init__(self, firms: list[Firm]):
        self.firms = firms
        self._index: dict[str, Firm] = {}
        for f in firms:
            for n in f.all_names:
                self._index[_norm(n)] = f

    @classmethod
    def load(cls, path: Path = FIRMS_CSV) -> "FirmBook":
        return cls(load_firms(path))

    def get(self, name: str) -> Firm | None:
        """Exact (normalized) match on name or alias, else a prefix match.

        Registered legal names lead with the brand ("GOLDMAN SACHS & CO. LLC", "WELLS FARGO
        CLEARING SERVICES"), so a known name that is a *prefix* of the query is a safe match, while
        a plain substring is not ("CRAIG-HALLUM CAPITAL GROUP" is not Capital Group)."""
        if not name:
            return None
        n = _norm(name)
        if n in self._index:
            return self._index[n]
        hits = self._prefix_hits(n)
        if len(hits) == 1:
            return hits[0]
        ln = normalize_legal_name(name)          # strip LLC / Securities / & Co and retry
        if ln and ln != n:
            if ln in self._index:
                return self._index[ln]
            hits = self._prefix_hits(ln)
            if len(hits) == 1:
                return hits[0]
        return None

    def _prefix_hits(self, q: str) -> list[Firm]:
        out: dict[str, Firm] = {}
        for k, f in self._index.items():
            if len(k) >= 4 and q.startswith(k):
                out[f.name] = f                      # known name leads the query
            elif len(q) >= 5 and len(q) <= 14 and k.startswith(q):
                out[f.name] = f                      # short human-typed query leads a known name
        # Prefer the longest matching key: "morganstanley" beats "ms" style collisions.
        if len(out) > 1:
            best = max(out.values(), key=lambda f: max(len(_norm(x)) for x in f.all_names if q.startswith(_norm(x)) or _norm(x).startswith(q)))
            longest = max(len(_norm(x)) for x in best.all_names if q.startswith(_norm(x)) or _norm(x).startswith(q))
            out = {nm: f for nm, f in out.items()
                   if max(len(_norm(x)) for x in f.all_names if q.startswith(_norm(x)) or _norm(x).startswith(q)) == longest}
        return list(out.values())

    def active(self, types: list[str] | None = None) -> list[Firm]:
        out = [f for f in self.firms if f.active]
        if types:
            t = {x.upper() for x in types}
            out = [f for f in out if f.type in t]
        return out
