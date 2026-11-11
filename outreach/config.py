"""Paths, environment, and constants shared by every module."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_DIR = Path(__file__).resolve().parent
TOOL_DIR = PACKAGE_DIR.parent                 # .../Claude projects/outreach
DATA_DIR = Path(os.environ.get("OUTREACH_DATA_DIR", TOOL_DIR.parent))  # .../Claude projects

load_dotenv(TOOL_DIR / ".env")

RESUME_PDF = Path(os.environ.get("RESUME_PDF", DATA_DIR / "resume.pdf"))
TRACKER_XLSX = Path(os.environ.get("TRACKER_XLSX", DATA_DIR / "Internship Tracker Summer 2027.xlsx"))
CONTACTS_XLSX = Path(os.environ.get("CONTACTS_XLSX", DATA_DIR / "Outreach Contacts.xlsx"))
FIRMS_CSV = TOOL_DIR / "firms.csv"
RESUME_FACTS_JSON = TOOL_DIR / "resume_facts.json"
BACKUP_DIR = TOOL_DIR / "backups"
GOOGLE_CREDENTIALS = TOOL_DIR / "credentials.json"
GOOGLE_TOKEN = TOOL_DIR / "token.json"

# Model tiers. Values are CLI aliases (opus / sonnet / haiku) - mapped to API ids when the api backend is used.
# Drafts default to sonnet to conserve your Opus quota; priority-1 (alumni) drafts get opus because they matter most.
MODEL_RESUME = os.environ.get("MODEL_RESUME", "sonnet")
MODEL_DRAFT = os.environ.get("MODEL_DRAFT", "sonnet")
MODEL_DRAFT_P1 = os.environ.get("MODEL_DRAFT_P1", "opus")

API_MODEL_IDS = {
    "opus": "claude-opus-5",
    "sonnet": "claude-sonnet-5",
    "haiku": "claude-haiku-4-5",
}
MODEL_ALIASES = tuple(API_MODEL_IDS)
APOLLO_API_KEY = os.environ.get("APOLLO_API_KEY", "")
HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")

SENDER_NAME = "Joshua Whang"
# Shown in the email signature - keep this the .edu, it reads better to recruiters.
SENDER_EMAIL = os.environ.get("SENDER_EMAIL", "jowhang@pitzer.edu")
# From header. Leave blank to let Gmail use whichever account you authorized. Gmail silently
# rewrites this unless the address is a verified "Send mail as" alias on that account.
SENDER_FROM = os.environ.get("SENDER_FROM", "")
SENDER_PHONE = os.environ.get("SENDER_PHONE", "")
SENDER_SCHOOL_LINE = "Pitzer College '29 | Economics"

CLAREMONT_SCHOOLS = (
    "pitzer", "pomona", "claremont mckenna", "cmc", "harvey mudd", "scripps",
    "claremont colleges", "claremont graduate", "keck graduate",
)
SOCAL_MARKERS = (
    "los angeles", "la,", " la ", "irvine", "newport beach", "orange county",
    "costa mesa", "san diego", "century city", "santa monica", "pasadena",
    "el segundo", "long beach", "anaheim", "southern california", "socal",
)

FIRM_TYPES = ("IB", "AM", "WM", "RE", "PE")
