from outreach.addresses import assign_email, fill_emails
from outreach.models import Contact


class FakeHunter:
    def __init__(self, answers):
        self.answers, self.calls = answers, []

    def verify(self, email):
        self.calls.append(email)
        return self.answers.get(email, "guessed")


def test_guess_without_hunter(firms):
    c = assign_email(Contact(firm="Baird", first="Jane", last="Doe"), firms.get("Baird"))
    assert c.email == "jdoe@rwbaird.com" and c.email_status == "guessed"
    assert "jane.doe@rwbaird.com" in c.email_alternates


def test_hunter_picks_first_verified(firms):
    h = FakeHunter({"jdoe@rwbaird.com": "invalid", "jane.doe@rwbaird.com": "verified"})
    c = assign_email(Contact(firm="Baird", first="Jane", last="Doe"), firms.get("Baird"), h)
    assert c.email == "jane.doe@rwbaird.com" and c.email_status == "verified"
    assert h.calls == ["jdoe@rwbaird.com", "jane.doe@rwbaird.com"]
    assert "jdoe@rwbaird.com" not in c.email_alternates


def test_api_email_untouched(firms):
    c = Contact(firm="Baird", first="Jane", last="Doe", email="real@rwbaird.com", email_status="from_api")
    assign_email(c, firms.get("Baird"))
    assert c.email == "real@rwbaird.com"


def test_fill_emails_reports_unknown_firm(firms):
    cs = [Contact(firm="Baird", first="A", last="B"), Contact(firm="Unknown Co", first="C", last="D")]
    n, warnings = fill_emails(cs, firms)
    assert n == 1 and cs[0].email and not cs[1].email
    assert "Unknown Co" in warnings[0]


class FakeHunterWithFinder(FakeHunter):
    def __init__(self, answers, found=None):
        super().__init__(answers)
        self.found = found

    def find(self, first, last, domain):
        self.calls.append(f"find:{first}.{last}@{domain}")
        return self.found


def test_finder_result_wins_over_pattern(firms):
    h = FakeHunterWithFinder({}, found=("jane.doe@rwbaird.com", 95, "verified"))
    c = assign_email(Contact(firm="Baird", first="Jane", last="Doe"), firms.get("Baird"), h)
    assert c.email == "jane.doe@rwbaird.com" and c.email_status == "verified"
    assert h.calls == ["find:Jane.Doe@rwbaird.com"]      # no verifier calls needed
    assert "jdoe@rwbaird.com" in c.email_alternates


def test_low_score_finder_falls_back_to_verification(firms):
    h = FakeHunterWithFinder({"jdoe@rwbaird.com": "verified"}, found=("x@rwbaird.com", 40, "unknown"))
    c = assign_email(Contact(firm="Baird", first="Jane", last="Doe"), firms.get("Baird"), h)
    assert c.email == "jdoe@rwbaird.com" and c.email_status == "verified"


def test_formal_name_fallback_when_all_patterns_invalid(firms):
    from outreach.addresses import formal_first
    assert formal_first("Zach") == "Zachary" and formal_first("Jane") is None
    h = FakeHunter({"zdoe@rwbaird.com": "invalid", "zach.doe@rwbaird.com": "invalid",
                    "zach_doe@rwbaird.com": "invalid", "zachd@rwbaird.com": "invalid",
                    "zdoe@rwbaird.com": "invalid", "zachary.doe@rwbaird.com": "verified"})
    c = assign_email(Contact(firm="Baird", first="Zach", last="Doe"), firms.get("Baird"), h)
    assert c.email == "zachary.doe@rwbaird.com" and c.email_status == "verified"
