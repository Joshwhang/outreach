from pathlib import Path

from outreach.gmail import GmailError, build_mime, create_draft
from outreach.models import Contact


def contact(**kw):
    base = dict(firm="Baird", first="Jane", last="Doe", email="jane@rwbaird.com",
                subject="Subj", draft="Hi Jane,\n\nbody")
    base.update(kw)
    return Contact(**base)


def test_mime_has_body_and_resume(tmp_path: Path):
    pdf = tmp_path / "r.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")
    msg = build_mime(contact(), resume=pdf)
    assert msg["To"] == "jane@rwbaird.com" and msg["Subject"] == "Subj"
    parts = list(msg.walk())
    assert any(p.get_content_type() == "application/pdf" for p in parts)
    assert any(p.get_filename() == "Joshua_Whang_Resume.pdf" for p in parts)
    assert "Hi Jane," in msg.get_body(("plain",)).get_content()


def test_mime_without_attachment(tmp_path: Path):
    msg = build_mime(contact(), attach_resume=False, resume=tmp_path / "missing.pdf")
    assert msg.get_content_type() == "text/plain"


class FakeService:
    def __init__(self):
        self.body = None

    def users(self):
        return self

    def drafts(self):
        return self

    def create(self, userId, body):
        self.body = body
        return self

    def execute(self):
        return {"id": "draft123"}


def test_create_draft_uses_service(tmp_path: Path):
    svc = FakeService()
    assert create_draft(contact(), attach_resume=False, service=svc) == "draft123"
    assert "raw" in svc.body["message"]


def test_refuses_incomplete_contacts():
    for bad in (contact(email=""), contact(draft=""), contact(subject="")):
        try:
            create_draft(bad, service=FakeService())
        except GmailError:
            continue
        raise AssertionError("expected GmailError")


def test_reply_to_is_edu_when_from_differs(monkeypatch, tmp_path: Path):
    import outreach.gmail as g
    monkeypatch.setattr(g, "SENDER_FROM", "")
    monkeypatch.setattr(g, "SENDER_EMAIL", "jowhang@pitzer.edu")
    msg = build_mime(contact(), attach_resume=False)
    assert msg["From"] is None          # Gmail fills in the authorized account
    assert msg["Reply-To"] == "jowhang@pitzer.edu"

    monkeypatch.setattr(g, "SENDER_FROM", "jowhang@pitzer.edu")
    msg = build_mime(contact(), attach_resume=False)
    assert msg["From"] == "Joshua Whang <jowhang@pitzer.edu>"
    assert msg["Reply-To"] is None      # no point when they match
