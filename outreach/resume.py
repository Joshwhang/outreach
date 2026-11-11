"""Parse resume.pdf once into structured facts used by every draft."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field
from pypdf import PdfReader

from .config import MODEL_RESUME, RESUME_FACTS_JSON, RESUME_PDF
from .llm import complete_structured


class Experience(BaseModel):
    organization: str
    role: str
    dates: str = ""
    highlights: list[str] = Field(default_factory=list, description="1-3 concrete, quantified bullets")


class ResumeFacts(BaseModel):
    name: str
    school: str
    class_year: str = Field(description="e.g. '2029'")
    year_label: str = Field(description="e.g. 'sophomore'")
    major: str
    gpa: str = ""
    hometown: str = ""
    email: str = ""
    phone: str = ""
    experiences: list[Experience]
    activities: list[Experience]
    skills: list[str]
    interests: list[str]
    hooks: list[str] = Field(description="6-10 short, specific talking points a cold email could use (e.g. 'D3 football + 4.0 GPA', 'real estate internship in Koreatown', 'Irvine native')")


def extract_text(pdf: Path = RESUME_PDF) -> str:
    reader = PdfReader(str(pdf))
    return "\n".join((p.extract_text() or "") for p in reader.pages)


def parse_resume(pdf: Path = RESUME_PDF) -> ResumeFacts:
    text = extract_text(pdf)
    if len(text.strip()) < 100:
        raise RuntimeError(f"Could not extract text from {pdf} - is it a scanned image?")
    return complete_structured(
        system="You extract structured facts from a student resume for use in networking emails. "
               "Be faithful to the text; do not invent or embellish. Keep highlights concise.",
        user=f"<resume>\n{text}\n</resume>",
        model=ResumeFacts,
        model_name=MODEL_RESUME,
    )


def load_facts(pdf: Path = RESUME_PDF, cache: Path = RESUME_FACTS_JSON, refresh: bool = False) -> ResumeFacts:
    if cache.exists() and not refresh and cache.stat().st_mtime >= pdf.stat().st_mtime:
        return ResumeFacts.model_validate_json(cache.read_text())
    facts = parse_resume(pdf)
    cache.write_text(facts.model_dump_json(indent=2))
    return facts
