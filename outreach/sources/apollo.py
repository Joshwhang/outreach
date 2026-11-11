"""Apollo.io people search + optional enrichment.

Docs: https://docs.apollo.io/reference/people-search and /reference/people-enrichment
Search is by firm domain (from firms.csv), optionally filtered by titles/locations.
Search results usually hide the email; `enrich` spends a credit per person to reveal it.
"""
from __future__ import annotations

import requests

from ..config import APOLLO_API_KEY
from ..firms import Firm
from ..models import Contact

BASE = "https://api.apollo.io/api/v1"

DEFAULT_TITLES = [
    "Analyst", "Investment Banking Analyst", "Summer Analyst", "Associate",
    "Investment Banking Associate", "Vice President", "Director", "Managing Director",
    "Financial Advisor", "Wealth Advisor", "Private Wealth Advisor", "Portfolio Manager",
    "Research Analyst", "Investment Analyst",
]


class ApolloError(RuntimeError):
    pass


class ApolloClient:
    def __init__(self, api_key: str = APOLLO_API_KEY, session: requests.Session | None = None):
        if not api_key:
            raise ApolloError("APOLLO_API_KEY not set - add it to outreach/.env, or use `outreach add` to paste contacts")
        self.s = session or requests.Session()
        self.s.headers.update({
            "x-api-key": api_key,
            "Content-Type": "application/json",
            "Cache-Control": "no-cache",
        })

    def _post(self, path: str, body: dict) -> dict:
        r = self.s.post(f"{BASE}/{path}", json=body, timeout=60)
        if r.status_code in (401, 403):
            raise ApolloError(
                f"Apollo returned {r.status_code}. People Search needs a paid Apollo plan with API access; "
                "check the key and plan at app.apollo.io/#/settings/integrations/api"
            )
        if r.status_code == 429:
            raise ApolloError("Apollo rate limit hit - wait a minute and retry")
        if r.status_code >= 400:
            raise ApolloError(f"Apollo error {r.status_code}: {r.text[:300]}")
        return r.json()

    def search(self, firm: Firm, titles: list[str] | None = None, locations: list[str] | None = None,
               max_results: int = 50) -> list[Contact]:
        body: dict = {
            "q_organization_domains_list": [firm.domain],
            "person_titles": titles or DEFAULT_TITLES,
            "page": 1,
            "per_page": min(max_results, 100),
        }
        if locations:
            body["person_locations"] = locations
        out: list[Contact] = []
        while len(out) < max_results:
            data = self._post("mixed_people/search", body)
            people = data.get("people") or []
            if not people:
                break
            for p in people:
                c = person_to_contact(p, firm)
                if c:
                    out.append(c)
            pagination = data.get("pagination") or {}
            if body["page"] >= int(pagination.get("total_pages") or 1):
                break
            body["page"] += 1
        return out[:max_results]

    def enrich(self, c: Contact, firm: Firm, reveal_phone: bool = False) -> Contact:
        body = {
            "first_name": c.first, "last_name": c.last,
            "organization_name": firm.name, "domain": firm.domain,
            "reveal_personal_emails": False,
            "reveal_phone_number": reveal_phone,
        }
        if c.linkedin:
            body["linkedin_url"] = c.linkedin
        p = (self._post("people/match", body) or {}).get("person") or {}
        email = p.get("email") or ""
        if email and "not_unlocked" not in email:
            c.email, c.email_status = email, "from_api"
        phones = p.get("phone_numbers") or []
        if phones and not c.phone:
            c.phone = phones[0].get("sanitized_number") or phones[0].get("raw_number") or ""
        if not c.linkedin:
            c.linkedin = p.get("linkedin_url") or ""
        return c


def person_to_contact(p: dict, firm: Firm) -> Contact | None:
    first = (p.get("first_name") or "").strip()
    last = (p.get("last_name") or "").strip()
    if not first:
        return None
    loc = ", ".join(x for x in (p.get("city"), p.get("state")) if x)
    email = p.get("email") or ""
    c = Contact(
        firm=firm.name, first=first, last=last, title=(p.get("title") or "").strip(),
        linkedin=p.get("linkedin_url") or "", location=loc, source="apollo",
    )
    if email and "not_unlocked" not in email and "@" in email:
        c.email, c.email_status = email, "from_api"
    return c
