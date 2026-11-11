"""Work-email generation from firm patterns, with optional Hunter.io verification."""
from __future__ import annotations

import requests

from .config import HUNTER_API_KEY
from .firms import Firm, FirmBook, candidate_emails
from .models import Contact

HUNTER = "https://api.hunter.io/v2"

# Hunter verifier -> our Email Status
_HUNTER_MAP = {
    "valid": "verified",
    "accept_all": "risky",
    "webmail": "risky",
    "unknown": "guessed",
    "disposable": "invalid",
    "invalid": "invalid",
}


# Rosters print what teammates call you; email directories use the legal name. When every pattern
# for the short form fails verification, retry with the long form before giving up.
FORMAL_NAMES = {
    "zach": "zachary", "zack": "zachary", "nick": "nicholas", "jake": "jacob", "alex": "alexander",
    "ben": "benjamin", "mike": "michael", "chris": "christopher", "matt": "matthew", "dan": "daniel",
    "danny": "daniel", "will": "william", "billy": "william", "bill": "william", "tom": "thomas",
    "tommy": "thomas", "jim": "james", "jimmy": "james", "joe": "joseph", "joey": "joseph",
    "sam": "samuel", "andy": "andrew", "drew": "andrew", "tony": "anthony", "rob": "robert",
    "bobby": "robert", "bob": "robert", "steve": "steven", "dave": "david", "jon": "jonathan",
    "josh": "joshua", "nate": "nathan", "nathaniel": "nathaniel", "ed": "edward", "eddie": "edward",
    "pat": "patrick", "tim": "timothy", "greg": "gregory", "jeff": "jeffrey", "ken": "kenneth",
    "kate": "katherine", "katie": "katherine", "kathy": "katherine", "liz": "elizabeth",
    "beth": "elizabeth", "maggie": "margaret", "meg": "margaret", "jen": "jennifer", "jenny": "jennifer",
    "abby": "abigail", "allie": "allison", "ally": "allison", "becca": "rebecca", "becky": "rebecca",
    "steph": "stephanie", "vicky": "victoria", "tori": "victoria", "mandy": "amanda", "sammy": "samantha",
    "charlie": "charles", "chuck": "charles", "ted": "theodore", "teddy": "theodore", "max": "maxwell",
    "gabe": "gabriel", "cam": "cameron", "ty": "tyler", "trey": "trey",
}


def formal_first(first: str) -> str | None:
    f = FORMAL_NAMES.get((first or "").lower())
    return f.title() if f and f != (first or "").lower() else None


class HunterClient:
    def __init__(self, api_key: str = HUNTER_API_KEY, session: requests.Session | None = None):
        if not api_key:
            raise RuntimeError("HUNTER_API_KEY not set - add it to outreach/.env or run without --verify")
        self.key = api_key
        self.s = session or requests.Session()

    def verify(self, email: str) -> str:
        r = self.s.get(f"{HUNTER}/email-verifier", params={"email": email, "api_key": self.key}, timeout=30)
        if r.status_code == 429:
            raise RuntimeError("Hunter rate limit hit - wait and re-run")
        if r.status_code == 402:
            raise RuntimeError("Hunter verification credits exhausted for this month")
        if r.status_code == 400:
            return "guessed"     # domain hidden or unverifiable - keep the pattern guess, don't crash
        r.raise_for_status()
        status = (r.json().get("data") or {}).get("status", "unknown")
        return _HUNTER_MAP.get(status, "guessed")

    def find(self, first: str, last: str, domain: str) -> tuple[str, int, str] | None:
        """Hunter's Email Finder: (email, score 0-100, verification status) or None.

        This is the database-lookup leg of the SalesQL-style approach - Hunter has seen real
        addresses at the domain and infers this person's from them, rather than guessing a pattern.
        Costs one 'search' credit (free tier: 25/month)."""
        r = self.s.get(f"{HUNTER}/email-finder",
                       params={"domain": domain, "first_name": first, "last_name": last, "api_key": self.key},
                       timeout=30)
        if r.status_code in (402, 429):
            # Hunter signals an exhausted search quota with either code; verification has its own quota.
            raise RuntimeError("Hunter search credits exhausted for this month")
        if r.status_code == 400:
            return None          # e.g. "domain hidden for privacy reasons" - fall back to pattern verification
        r.raise_for_status()
        d = r.json().get("data") or {}
        if not d.get("email"):
            return None
        status = ((d.get("verification") or {}).get("status")) or "unknown"
        return d["email"], int(d.get("score") or 0), _HUNTER_MAP.get(status, "guessed")

    def domain_pattern(self, domain: str) -> str | None:
        """Hunter's inferred pattern like '{first}.{last}' -> our token form 'first.last'."""
        r = self.s.get(f"{HUNTER}/domain-search", params={"domain": domain, "api_key": self.key, "limit": 1}, timeout=30)
        r.raise_for_status()
        pat = (r.json().get("data") or {}).get("pattern")
        if not pat:
            return None
        return pat.replace("{", "").replace("}", "")


def assign_email(c: Contact, firm: Firm, hunter: HunterClient | None = None) -> Contact:
    """Set c.email / c.email_status / c.email_alternates. Leaves API-sourced emails alone."""
    if c.email and c.email_status == "from_api":
        return c
    cands = candidate_emails(firm, c.first, c.last)
    if not cands:
        return c
    if hunter is None:
        c.email = cands[0]
        c.email_status = "guessed"
        c.email_alternates = "; ".join(cands[1:4])
        return c
    # Lookup first: if Hunter has this person, trust it over our pattern guess.
    found = None
    if hasattr(hunter, "find") and not getattr(hunter, "finder_exhausted", False):
        try:
            found = hunter.find(c.first, c.last, firm.domain)
        except RuntimeError as e:
            if "exhausted" in str(e):
                hunter.finder_exhausted = True      # fall back to verification for the rest of the run
            else:
                raise
    if found:
        email, score, st = found
        if score >= 70:
            c.email = email
            c.email_status = st if st == "verified" else ("risky" if score < 90 else "guessed")
            c.email_alternates = "; ".join(e for e in cands[:3] if e != email)
            return c
    # Otherwise verify our candidates in order; first 'verified' wins, else best non-invalid.
    results: list[tuple[str, str]] = []
    for e in cands[:4]:
        st = hunter.verify(e)
        results.append((e, st))
        if st == "verified":
            break
    if not results:
        return c
    # Every short-form pattern rejected? Try the legal first name once before declaring it dead.
    if all(st == "invalid" for _, st in results):
        formal = formal_first(c.first)
        if formal:
            for e in candidate_emails(firm, formal, c.last)[:2]:
                st = hunter.verify(e)
                results.append((e, st))
                if st == "verified":
                    break
    rank = {"verified": 0, "risky": 1, "guessed": 2, "invalid": 3}
    results.sort(key=lambda x: rank[x[1]])
    best, st = results[0]
    c.email, c.email_status = best, st
    c.email_alternates = "; ".join(e for e, s in results[1:] if s != "invalid")
    return c


def fill_emails(contacts: list[Contact], firms: FirmBook, verify: bool = False,
                on_each=None) -> tuple[int, list[str]]:
    """Assign emails for contacts missing one. Returns (count_filled, warnings).

    on_each(contact) is called after every contact is processed - use it to save progress so a
    quota error or network drop late in a long run does not lose the earlier results."""
    hunter = HunterClient() if verify else None
    filled, warnings = 0, []
    for c in contacts:
        if c.email and c.email_status != "guessed":
            continue
        if c.email and not verify:
            continue
        firm = firms.get(c.firm)
        if firm is None:
            warnings.append(f"{c.name}: firm '{c.firm}' not in firms.csv")
            continue
        if not firm.domain:
            warnings.append(f"{c.name}: no domain for {firm.name}")
            continue
        before = c.email
        try:
            assign_email(c, firm, hunter)
        except RuntimeError as e:
            warnings.append(f"stopped at {c.name}: {e}")
            break
        except requests.HTTPError as e:
            warnings.append(f"{c.name}: Hunter error {e.response.status_code if e.response is not None else ''} - left as guessed")
            if on_each:
                on_each(c)
            continue
        if c.email and (c.email != before or verify):
            filled += 1
        if on_each:
            on_each(c)
    return filled, warnings
