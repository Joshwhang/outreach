"""Claremont athletics rosters (public team pages).

Pomona-Pitzer (Sagehens) and Claremont-Mudd-Scripps (CMS/Athenas) both run on the Sidearm
platform, which embeds a JSON-LD Person list on every roster page. We read that rather than
scraping markup, so this keeps working across template changes.

Only names are taken. Roster pages are public; robots.txt on both sites permits /sports/.
"""
from __future__ import annotations

import html as html_mod
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

from ..config import TOOL_DIR

SCHOOLS = {
    "pp": ("Pomona-Pitzer", "https://sagehens.com"),
    "cms": ("Claremont-Mudd-Scripps", "https://cmsathletics.org"),
}
CACHE_DIR = TOOL_DIR / "cache" / "rosters"
USER_AGENT = "outreach-tool/0.1 (personal networking research; contact jowhang@pitzer.edu)"
POLITE_DELAY = 1.5


@dataclass
class RosterEntry:
    first: str
    last: str
    school: str          # "Pomona-Pitzer"
    sport: str
    year: int

    @property
    def tie(self) -> str:
        """The phrase that ends up in the email, e.g. 'Pomona-Pitzer football, 2019 roster'."""
        return f"{self.school} {self.sport.replace('-', ' ')}, {self.year} roster"


class RosterError(RuntimeError):
    pass


def roster_url(school: str, sport: str, year: int) -> str:
    if school not in SCHOOLS:
        raise RosterError(f"unknown school '{school}' - use one of {list(SCHOOLS)}")
    return f"{SCHOOLS[school][1]}/sports/{sport}/roster/{year}"


def _fetch(url: str, cache: Path | None) -> str:
    if cache and cache.exists():
        return cache.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "text/html"})
    try:
        with urllib.request.urlopen(req, timeout=45) as r:
            html = r.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        raise RosterError(f"{url} returned {e.code}") from e
    except urllib.error.URLError as e:
        raise RosterError(f"could not reach {url}: {e.reason}") from e
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(html, encoding="utf-8")
    time.sleep(POLITE_DELAY)
    return html


def parse_people(html: str) -> list[str]:
    """Names from the roster page's JSON-LD ListItem/Person blocks."""
    names: list[str] = []
    for block in re.findall(r'<script[^>]*type="application/ld\+json"[^>]*>(.*?)</script>', html, re.S):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        items = data.get("item") if isinstance(data, dict) else None
        for person in items or []:
            if isinstance(person, dict) and person.get("@type") == "Person":
                name = html_mod.unescape(person.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
    return names


def fetch_roster(school: str, sport: str, year: int, use_cache: bool = True) -> list[RosterEntry]:
    from ..models import split_name
    url = roster_url(school, sport, year)
    cache = CACHE_DIR / f"{school}-{sport}-{year}.html" if use_cache else None
    names = parse_people(_fetch(url, cache))
    out = []
    for n in names:
        first, last = split_name(n)
        if first and last:
            out.append(RosterEntry(first, last, SCHOOLS[school][0], sport, year))
    return out


# Sports whose alumni turn up in finance most often. Not a rule, just where to start.
FINANCE_HEAVY = ["football", "mens-basketball", "mens-golf", "baseball", "mens-soccer",
                 "womens-golf", "womens-soccer", "womens-basketball", "mens-tennis",
                 "womens-lacrosse", "mens-water-polo"]

ALL_SPORTS = ["football", "mens-basketball", "mens-golf", "baseball", "mens-soccer", "mens-tennis",
              "mens-water-polo", "mens-swimming-and-diving", "mens-cross-country",
              "mens-track-and-field", "womens-basketball", "womens-golf", "womens-lacrosse",
              "womens-soccer", "womens-tennis", "womens-volleyball", "womens-water-polo",
              "womens-swimming-and-diving", "womens-cross-country", "womens-track-and-field",
              "softball"]


def fetch_many(school: str, sports: list[str], years: range, use_cache: bool = True) -> list[RosterEntry]:
    """Deduplicated across years - someone on four rosters is one person; keep their latest year."""
    seen: dict[tuple[str, str], RosterEntry] = {}
    for sport in sports:
        for year in years:
            try:
                entries = fetch_roster(school, sport, year, use_cache)
            except RosterError as e:
                print(f"  ! {school}/{sport}/{year}: {e}")
                continue
            for e in entries:
                key = (e.first.lower(), e.last.lower())
                if key not in seen or e.year > seen[key].year:
                    seen[key] = e
            print(f"  {school}/{sport}/{year}: {len(entries)} players")
    return list(seen.values())
