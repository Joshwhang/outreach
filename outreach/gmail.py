"""Create Gmail drafts (never sends). Google OAuth desktop flow, token cached locally."""
from __future__ import annotations

import base64
from email.message import EmailMessage
from pathlib import Path

from .config import GOOGLE_CREDENTIALS, GOOGLE_TOKEN, RESUME_PDF, SENDER_EMAIL, SENDER_FROM, SENDER_NAME
from .models import Contact

SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]


class GmailError(RuntimeError):
    pass


def _service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError as e:  # pragma: no cover
        raise GmailError("Google libraries missing - run: pip install google-api-python-client google-auth-oauthlib") from e

    creds = None
    if GOOGLE_TOKEN.exists():
        creds = Credentials.from_authorized_user_file(str(GOOGLE_TOKEN), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not GOOGLE_CREDENTIALS.exists():
                raise GmailError(
                    f"{GOOGLE_CREDENTIALS.name} not found. Create a Google Cloud OAuth 'Desktop app' client with the "
                    "Gmail API enabled, download the JSON, and save it as outreach/credentials.json (see README)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(GOOGLE_CREDENTIALS), SCOPES)
            creds = flow.run_local_server(port=0)
        GOOGLE_TOKEN.write_text(creds.to_json())
    return build("gmail", "v1", credentials=creds, cache_discovery=False)


def build_mime(c: Contact, attach_resume: bool = True, resume: Path | None = None) -> EmailMessage:
    resume = resume or RESUME_PDF
    msg = EmailMessage()
    msg["To"] = c.email
    if SENDER_FROM:
        msg["From"] = f"{SENDER_NAME} <{SENDER_FROM}>"
    if SENDER_FROM != SENDER_EMAIL:
        msg["Reply-To"] = SENDER_EMAIL
    msg["Subject"] = c.subject
    msg.set_content(c.draft)
    if attach_resume and resume.exists():
        msg.add_attachment(resume.read_bytes(), maintype="application", subtype="pdf",
                           filename=f"{SENDER_NAME.replace(' ', '_')}_Resume.pdf")
    return msg


def create_draft(c: Contact, attach_resume: bool = True, service=None) -> str:
    """Returns the Gmail draft id."""
    if not c.email:
        raise GmailError(f"{c.name}: no email address")
    if not c.draft or not c.subject:
        raise GmailError(f"{c.name}: no draft - run `outreach draft` first")
    svc = service or _service()
    raw = base64.urlsafe_b64encode(build_mime(c, attach_resume).as_bytes()).decode()
    result = svc.users().drafts().create(userId="me", body={"message": {"raw": raw}}).execute()
    return result.get("id", "")
