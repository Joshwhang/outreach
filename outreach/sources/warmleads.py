"""Import a warm-leads workbook (rosters x FINRA BrokerCheck) into the contact pipeline.

The workbook pairs Claremont athletes with FINRA-registered individuals of the same name and
scores how likely the pairing is to be the same human. Those scores are priors, not proof, so:

  - only the `strong` tier imports by default
  - the per-row BrokerCheck and roster links are carried into the sheet for one-click verification
  - rows whose name is shared with another row are marked, not silently merged
  - the CRD, links and confidence live in their own columns and are NEVER put in `notes`,
    because `notes` is fed to the model when drafting and would leak into the email

What lands in `notes` is only the affinity itself - team, seasons, class year - which is exactly
the hook the draft should open with.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from openpyxl import load_workbook

from ..firms import FirmBook
from ..models import Contact, split_name

TIERS = ("strong", "review", "weak")

# Broker-dealers whose registrants are retail / advisory rather than banking or asset management.
# A bulge-bracket name alone is ambiguous (J.P. MORGAN SECURITIES covers IB and the Private Bank);
# these entity names are not.
WEALTH_BD_PREFIXES = (
    "MORGAN STANLEY SMITH BARNEY", "WELLS FARGO CLEARING", "WELLS FARGO ADVISORS", "UBS FINANCIAL SERVICES",
    "MERRILL LYNCH", "EDWARD JONES", "CHARLES SCHWAB", "NORTHWESTERN MUTUAL", "AMERIPRISE", "LPL FINANCIAL",
    "OSAIC", "CETERA", "EQUITABLE ADVISORS", "RAYMOND JAMES & ASSOCIATES", "RAYMOND JAMES FINANCIAL SERVICES",
    "FIDELITY BROKERAGE SERVICES", "VANGUARD MARKETING", "PARK AVENUE SECURITIES", "MML INVESTORS",
    "PFS INVESTMENTS", "TRANSAMERICA FINANCIAL", "STATE FARM", "NYLIFE", "LINCOLN FINANCIAL ADVISORS",
    "PRUDENTIAL", "ROCKEFELLER FINANCIAL", "BAIRD PRIVATE WEALTH",
)
WEALTH_BD_EXACT = ("MORGAN STANLEY",)      # plain 'MORGAN STANLEY' is the wealth BD; '& CO. LLC' is the bank


def is_wealth_bd(bd: str) -> bool:
    b = (bd or "").upper().strip().rstrip(".")
    return b in WEALTH_BD_EXACT or b.startswith(WEALTH_BD_PREFIXES)
DEFAULT_SHEET = "Warm Leads"
NO_FIRM = "(no current firm)"


@dataclass
class LeadStats:
    read: int = 0
    skipped_tier: int = 0
    skipped_no_firm: int = 0
    skipped_low_conf: int = 0
    unmapped_firm: int = 0
    flagged_duplicate: int = 0


def _first(value: str | None) -> str:
    """Firms and offices arrive pipe-separated; the first is the current/primary one."""
    return (value or "").split("|")[0].strip()


def _cell_link(ws, row: int, col: int) -> str:
    c = ws.cell(row=row, column=col)
    return c.hyperlink.target if c.hyperlink else ""


def build_notes(row: dict) -> str:
    """The affinity line the draft will open with. No identifiers, no URLs."""
    team = (row.get("Team") or row.get("College") or "").strip()
    consortium = (row.get("College") or "").strip()
    school = team or consortium or "Claremont"
    sport = (row.get("Sport") or "").replace("-", " ").strip()
    bits = [f"{school} {sport}".strip()]
    seasons = str(row.get("Seasons") or "").strip()
    if seasons:
        parts = seasons.split("-")
        if len(parts) == 2 and parts[0] == parts[1]:
            seasons = parts[0]          # "2015-2015" -> "2015"
        bits.append(seasons)
    if row.get("Est. grad"):
        bits.append(f"class of {row['Est. grad']}")
    if row.get("Hometown"):
        bits.append(f"from {row['Hometown']}")
    return ", ".join(b for b in bits if b)


def load_leads(path: Path, firms: FirmBook, sheet: str = DEFAULT_SHEET,
               tiers: tuple[str, ...] = ("strong",), min_confidence: float = 0.75,
               keep_unmapped: bool = False) -> tuple[list[Contact], LeadStats]:
    wb = load_workbook(path)
    if sheet not in wb.sheetnames:
        raise RuntimeError(f"{path.name} has no '{sheet}' sheet - found {wb.sheetnames}")
    ws = wb[sheet]
    header = [c.value for c in ws[1]]
    idx = {name: i + 1 for i, name in enumerate(header) if name}
    stats = LeadStats()
    out: list[Contact] = []

    for r in range(2, ws.max_row + 1):
        row = {name: ws.cell(row=r, column=col).value for name, col in idx.items()}
        if not (row.get("Name") or "").strip():
            continue
        stats.read += 1

        tier = (row.get("Tier") or "").strip().lower()
        if tier and tiers and tier not in tiers:
            stats.skipped_tier += 1
            continue
        try:
            conf = float(row.get("Confidence") or 0)
        except (TypeError, ValueError):
            conf = 0.0
        if conf < min_confidence:
            stats.skipped_low_conf += 1
            continue

        raw_firm = _first(row.get("Current firm(s)"))
        if not raw_firm or raw_firm == NO_FIRM:
            stats.skipped_no_firm += 1
            continue
        firm = firms.get(raw_firm)
        if firm is None:
            stats.unmapped_firm += 1
            if not keep_unmapped:
                continue

        first, last = split_name(str(row["Name"]))
        if not first or not last:
            continue

        dup = str(row.get("Duplicate name?") or "").strip().upper() == "CHECK"
        if dup:
            stats.flagged_duplicate += 1

        confidence = f"{tier or 'n/a'} {conf:.2f}"
        if dup:
            confidence += " | SHARES NAME - CHECK BOTH"

        c = Contact(
            firm=firm.name if firm else raw_firm,
            firm_type=firm.type if firm else "",
            first=first, last=last,
            title="",                       # BrokerCheck gives registration, not job title
            location=_first(row.get("Office")),
            school=(row.get("College") or row.get("Team") or "Claremont Colleges"),
            claremont_alum=True,
            source="warm-leads",
            notes=build_notes(row),
            confidence=confidence,
            verify_url=_cell_link(ws, r, idx.get("BrokerCheck", 0)) if "BrokerCheck" in idx else "",
            roster_url=_cell_link(ws, r, idx.get("Roster", 0)) if "Roster" in idx else "",
            registered_firm=raw_firm,
            group="Wealth Management" if is_wealth_bd(raw_firm) else "",
        )
        out.append(c)
    return out, stats
