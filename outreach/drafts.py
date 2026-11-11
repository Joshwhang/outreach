"""Hybrid drafting: fixed skeleton + Claude-written middle paragraph."""
from __future__ import annotations

import re
from dataclasses import dataclass

from pydantic import BaseModel, Field

from .config import MODEL_DRAFT, MODEL_DRAFT_P1, SENDER_EMAIL, SENDER_NAME, SENDER_PHONE, SENDER_SCHOOL_LINE
from .firms import Firm
from .llm import complete_structured
from .models import Contact
from .resume import ResumeFacts

PRACTICE = {
    "IB": "investment banking",
    "AM": "asset management",
    "WM": "wealth management",
    "RE": "real estate",
    "PE": "private equity",
}

MAX_MIDDLE_WORDS = 70


class Middle(BaseModel):
    middle: str = Field(description="The personalized middle paragraph, 2-3 sentences, plain text, no greeting, no ask, no sign-off")


@dataclass
class Draft:
    subject: str
    body: str
    model: str = ""


def practice_for(firm: Firm, contact: Contact) -> str:
    g = (contact.group or "").lower()
    if "wealth" in g or "private bank" in g or "advis" in g:
        return "wealth management"
    if "asset" in g or "portfolio" in g or "investment management" in g:
        return "asset management"
    return PRACTICE.get(firm.type, "finance")


def subject_for(firm: Firm, contact: Contact, facts: ResumeFacts) -> str:
    practice = practice_for(firm, contact).title()
    school_short = facts.school.split("(")[0].strip().replace(" College", "")
    if contact.claremont_alum:
        return f"{school_short} Student Interested in {firm.name} {practice}"
    return f"{school_short} {facts.year_label.title()} Interested in {firm.name} {practice}"


def assemble(contact: Contact, firm: Firm, facts: ResumeFacts, middle: str) -> Draft:
    practice = practice_for(firm, contact)
    body = (
        f"Hi {contact.first},\n\n"
        f"{middle.strip()}\n\n"
        f"Would you have 15 minutes in the next couple of weeks for a quick call? I would love to hear about "
        f"your path to {firm.name} and any advice you have as I prepare to recruit for {practice} internships. "
        f"I've attached my resume for reference and am happy to work around your schedule.\n\n"
        f"Thank you for your time,\n"
        f"{SENDER_NAME}\n"
        f"{SENDER_SCHOOL_LINE}\n"
        f"{' | '.join(x for x in (SENDER_PHONE, SENDER_EMAIL) if x)}"
    )
    return Draft(subject=subject_for(firm, contact, facts), body=body)


def word_count(s: str) -> int:
    return len(re.findall(r"\S+", s))


SYSTEM_RULES = """You write the middle paragraph of a short cold networking email from a college student to a finance professional. You are given the student's resume facts and the recipient's details. Return only that paragraph.

Rules:
- Write in the first person as the student ("I am...", "I worked..."). Never refer to the student by name in the third person.
- 2 to 3 sentences, at most 70 words.
- Sentence 1 introduces the student: name, school, year, major, and how they found the recipient if a note says so (alumni directory, LinkedIn, event).
- Include exactly ONE specific hook that ties the student to this recipient: a shared school (Claremont Colleges) if applicable, else a shared region (Southern California), else the recipient's group or firm and one resume fact that maps to it. Pick the strongest.
- Cite one concrete resume fact (an experience, activity, or number). No lists of accomplishments.
- Attribute every fact to the right organization. Never merge two experiences into one clause or imply work done at one employer happened at another.
- The student is a current undergraduate; the recipient is a working professional. Never call the recipient a student or the student an alum. For a shared school, name the school itself ("we both went to Pitzer", "a fellow Pitzer alum" only if they graduated) rather than assigning either person the wrong status.
- Plain, direct, warm. No flattery about the recipient or firm. No "I hope this finds you well", "I am reaching out", "I came across your profile", "impressive", "esteemed", or "passion".
- No em dashes, no exclamation points, no bullet points, no greeting, no ask for a call, no sign-off. Those are added separately.
- Never invent facts about the recipient beyond what is provided. If their school is unknown, do not guess it.
"""


def generate_middle(contact: Contact, firm: Firm, facts: ResumeFacts, model_name: str | None = None) -> str:
    recipient = "\n".join(f"{k}: {v}" for k, v in {
        "Name": contact.name, "Title": contact.title, "Level": contact.level, "Firm": firm.name,
        "Firm type": PRACTICE.get(firm.type, firm.type), "Group": contact.group,
        "Office location": contact.location, "School": contact.school,
        "Claremont alum": "yes" if contact.claremont_alum else "unknown/no",
        "Notes from student": contact.notes,
    }.items() if v)
    system = [
        {"type": "text", "text": SYSTEM_RULES},
        {"type": "text", "text": f"<resume_facts>\n{facts.model_dump_json(indent=1)}\n</resume_facts>",
         "cache_control": {"type": "ephemeral"}},
    ]
    user = f"<recipient>\n{recipient}\n</recipient>\n\nWrite the middle paragraph."
    for attempt in range(2):
        middle = complete_structured(system, user, Middle, model_name).middle.strip()
        middle = middle.replace("—", ", ").replace("–", "-")
        if middle and word_count(middle) <= MAX_MIDDLE_WORDS + 10:
            return middle
        user += f"\n\nThat was {word_count(middle)} words. Rewrite in at most {MAX_MIDDLE_WORDS} words."
    return middle


def model_for(contact: Contact, override: str | None = None) -> str:
    """Tiered by priority so Opus quota goes to the contacts most worth it."""
    if override and override != "auto":
        return override
    return MODEL_DRAFT_P1 if contact.priority == 1 else MODEL_DRAFT


# --- template mode: Josh's own foundation, with only the necessary slots varying -----------------

TEAM_RE = re.compile(r"(Pomona-Pitzer|Claremont-Mudd-Scripps)\s+([a-z][a-z ]*?)(?:,|$)", re.I)
# Notes convention for non-Claremont athletes: "played football at Notre Dame" -> (Notre Dame, football)
PLAYED_RE = re.compile(r"played\s+([a-z][a-z' ]*?)\s+(?:at|for)\s+([A-Z][\w.&' -]*?)(?:[;,.]|$)")

# Deliberately not a shared constant with the ask paragraph: this is the sentence that changes.
TIE_SAME_PROGRAM = ("I noticed that you played for the same program and wanted to reach out because I very "
                    "much desire to be in an environment full of people who share the same interests and "
                    "passion for sports.")
TIE_REFERRED_SAME_PROGRAM = ("You played for the same program, which is part of why I wanted to connect - I very "
                             "much want to be in an environment full of people who share the same interests and "
                             "passion for sports.")
TIE_OTHER_SPORT = ("I noticed that you played {sport} {prep} {team} and wanted to reach out because I very "
                   "much desire to be in an environment full of people who share the same interests and "
                   "passion for sports.")
TIE_CLAREMONT = ("I noticed that you went to {school} and wanted to reach out because I very much desire to "
                 "learn from people who came through the Claremont Colleges.")
TIE_GENERIC = "I wanted to reach out because I very much desire to learn from people working in {practice}."


def athletic_tie(contact: Contact) -> tuple[str, str] | None:
    """(team, sport) parsed from the affinity notes, e.g. ('Pomona-Pitzer', 'football')."""
    m = TEAM_RE.search(contact.notes or "")
    if m:
        return m.group(1), m.group(2).strip().lower()
    m = PLAYED_RE.search(contact.notes or "")
    if m:
        return m.group(2).strip(), m.group(1).strip().lower()
    return None


def hometown_clause(contact: Contact, facts: ResumeFacts | None) -> str:
    """' and are now based in Irvine, where I grew up,' when the contact's office is Josh's hometown.

    Deliberately about their office, not their origin: the data says where they work, and claiming
    a shared hometown that isn't true is the kind of small error that costs a reply."""
    if not facts or not facts.hometown:
        return ""
    city = facts.hometown.split(",")[0].strip()
    if city and city.lower() in (contact.location or "").lower():
        return f" and are now based in {city}, where I grew up,"
    return ""


def tie_sentence(contact: Contact, practice: str, facts: ResumeFacts | None = None) -> str:
    tie = athletic_tie(contact)
    local = hometown_clause(contact, facts)
    if tie:
        team, sport = tie
        if team == "Pomona-Pitzer" and sport == "football":
            if contact.referred_by:
                return TIE_REFERRED_SAME_PROGRAM.replace(
                    " which is part of why", f"{local + ' and' if local else ''} which is part of why", 1)
            return TIE_SAME_PROGRAM.replace(" and wanted to reach out", f"{local} and wanted to reach out", 1)
        prep = "for" if team == "Pomona-Pitzer" else "at"
        return TIE_OTHER_SPORT.format(sport=_sport_label(sport), prep=prep, team=team) \
            .replace(" and wanted to reach out", f"{local} and wanted to reach out", 1)
    if contact.claremont_alum:
        school = contact.school if contact.school and "claremont colleges" not in contact.school.lower() \
            else "the Claremont Colleges"
        return TIE_CLAREMONT.format(school=school)
    return TIE_GENERIC.format(practice=practice)


def _sport_label(sport: str) -> str:
    """'womens soccer' -> "women's soccer"; 'mens golf' -> "men's golf"."""
    return re.sub(r"\b(wo)?mens\b", lambda m: f"{m.group(1) or ''}men's", sport)


def _major(facts: ResumeFacts) -> str:
    return re.sub(r"\s*\(.*?\)", "", facts.major).strip().lower()   # drop '(Bachelor of Arts)'


def template_middle(contact: Contact, firm: Firm, facts: ResumeFacts) -> str:
    """A referred email leads with the referrer; a cold one leads with the introduction."""
    practice = practice_for(firm, contact)
    intro = (f"I am {facts.name}, a {facts.year_label} {_major(facts)} major at "
             f"{facts.school.split('(')[0].strip()}, and I am interested in a career in {practice}. "
             f"I currently play football for the Pomona-Pitzer program and have a "
             f"{facts.gpa.split('/')[0]} GPA. ")
    if contact.referred_by:
        return (f"I recently spoke with {contact.referred_by}, who suggested I reach out to you. "
                f"{intro}{tie_sentence(contact, practice, facts)}")
    return f"{intro}{tie_sentence(contact, practice, facts)}"


def draft_for(contact: Contact, firm: Firm, facts: ResumeFacts, model_name: str | None = None,
              style: str = "template") -> Draft:
    if style == "template":
        d = assemble(contact, firm, facts, template_middle(contact, firm, facts))
        d.model = "template"
        return d
    model_name = model_for(contact, model_name)
    d = assemble(contact, firm, facts, generate_middle(contact, firm, facts, model_name))
    d.model = model_name
    return d
