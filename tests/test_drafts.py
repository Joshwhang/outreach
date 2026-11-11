from outreach.drafts import assemble, practice_for, subject_for, word_count
from outreach.models import Contact
from outreach.resume import ResumeFacts


def facts():
    return ResumeFacts(name="Joshua Whang", school="Pitzer College (Claremont Colleges)", class_year="2029",
                       year_label="sophomore", major="Economics", experiences=[], activities=[], skills=[],
                       interests=[], hooks=["4.0 GPA", "D3 football"])


def test_subject_and_practice(firms):
    c = Contact(firm="Baird", first="Jane", last="Doe", title="Analyst")
    assert subject_for(firms.get("Baird"), c, facts()) == "Pitzer Sophomore Interested in Baird Investment Banking"
    c.claremont_alum = True
    assert subject_for(firms.get("Baird"), c, facts()).startswith("Pitzer Student")
    c2 = Contact(firm="Baird", first="J", last="D", group="Private Wealth Management")
    assert practice_for(firms.get("Baird"), c2) == "wealth management"
    assert practice_for(firms.get("PIMCO"), Contact(firm="PIMCO", first="J", last="D")) == "asset management"


def test_assemble_skeleton(firms):
    c = Contact(firm="PIMCO", first="Jane", last="Doe", title="Associate")
    d = assemble(c, firms.get("PIMCO"), facts(), "I am a sophomore at Pitzer. I grew up in Irvine.")
    assert d.body.startswith("Hi Jane,\n\nI am a sophomore at Pitzer.")
    assert "path to PIMCO" in d.body and "asset management internships" in d.body
    assert d.body.rstrip().endswith("jowhang@pitzer.edu")
    assert word_count(d.body) < 160
    assert "—" not in d.body


def test_model_tiering():
    from outreach.drafts import model_for
    p1 = Contact(firm="X", first="A", last="B", priority=1)
    p3 = Contact(firm="X", first="A", last="B", priority=3)
    assert model_for(p1) == "opus"
    assert model_for(p3) == "sonnet"
    assert model_for(p1, "sonnet") == "sonnet"   # explicit override wins
    assert model_for(p1, "auto") == "opus"
    assert model_for(p3, "haiku") == "haiku"


def test_rules_cover_known_failure_modes():
    """Each rule here was added after a live draft got it wrong - keep them pinned."""
    from outreach.drafts import SYSTEM_RULES
    for phrase in ["first person", "Attribute every fact", "never call the recipient a student".lower()]:
        assert phrase.lower() in SYSTEM_RULES.lower(), phrase


def test_template_tie_sentences(firms):
    from outreach.drafts import tie_sentence, template_middle, athletic_tie
    f = facts(); f.gpa = "4.0/4.0"; f.major = "Economics (Bachelor of Arts)"
    pp_fb = Contact(firm="Baird", first="A", last="B", claremont_alum=True,
                    notes="Pomona-Pitzer football, 2018-2021, class of 2022, from Irvine, CA")
    pp_bb = Contact(firm="Baird", first="A", last="B", claremont_alum=True,
                    notes="Pomona-Pitzer mens basketball, 2019, class of 2021")
    cms = Contact(firm="Baird", first="A", last="B", claremont_alum=True,
                  notes="Claremont-Mudd-Scripps womens soccer, 2013-2015, class of 2017")
    alum = Contact(firm="Baird", first="A", last="B", claremont_alum=True, school="Pomona", notes="Pomona '19")
    other = Contact(firm="Baird", first="A", last="B", notes="met at info session")

    assert athletic_tie(pp_fb) == ("Pomona-Pitzer", "football")
    assert athletic_tie(cms) == ("Claremont-Mudd-Scripps", "womens soccer")
    assert tie_sentence(pp_fb, "investment banking").startswith("I noticed that you played for the same program")
    assert "played men's basketball for Pomona-Pitzer" in tie_sentence(pp_bb, "investment banking")
    assert "played women's soccer at Claremont-Mudd-Scripps" in tie_sentence(cms, "investment banking")
    assert "you went to Pomona" in tie_sentence(alum, "investment banking")
    assert "working in wealth management" in tie_sentence(other, "wealth management")

    mid = template_middle(pp_fb, firms.get("Baird"), f)
    assert mid.startswith("I am Joshua Whang, a sophomore economics major at Pitzer College, "
                          "and I am interested in a career in investment banking.")
    assert "have a 4.0 GPA" in mid


def test_template_practice_varies_by_firm(firms):
    from outreach.drafts import draft_for
    f = facts(); f.gpa = "4.0/4.0"
    c = Contact(firm="PIMCO", first="Jane", last="Doe")
    d = draft_for(c, firms.get("PIMCO"), f, style="template")
    assert "career in asset management" in d.body and "asset management internships" in d.body
    assert "path to PIMCO" in d.body and d.model == "template"


def test_non_claremont_athlete_tie():
    from outreach.drafts import athletic_tie, tie_sentence
    c = Contact(firm="Roth Capital Partners", first="T", last="N",
                notes="played football at Notre Dame; NFL tight end 2014-2019; energy sector")
    assert athletic_tie(c) == ("Notre Dame", "football")
    assert "you played football at Notre Dame and wanted to reach out" in tie_sentence(c, "investment banking")


def test_hometown_clause_only_when_office_matches():
    from outreach.drafts import tie_sentence
    f = facts(); f.hometown = "Irvine, CA"
    irvine = Contact(firm="X", first="A", last="B", location="Irvine, CA",
                     notes="Pomona-Pitzer football, 2020-2023, class of 2024, from San Juan Capistrano, CA")
    ny = Contact(firm="X", first="A", last="B", location="New York, NY",
                 notes="Pomona-Pitzer football, 2020-2023, class of 2024, from Irvine, CA")
    assert ("played for the same program and are now based in Irvine, where I grew up, and wanted"
            in tie_sentence(irvine, "wealth management", f))
    assert "Irvine" not in tie_sentence(ny, "wealth management", f)   # from Irvine but works in NY - not claimed


def test_referral_opens_with_the_referrer(firms):
    from outreach.drafts import template_middle
    f = facts(); f.gpa = "4.0/4.0"; f.major = "Economics"
    c = Contact(firm="Baird", first="E", last="D", referred_by="Jane Smith", claremont_alum=True,
                notes="Pomona-Pitzer football, 2016-2019, class of 2020")
    mid = template_middle(c, firms.get("Baird"), f)
    assert mid.startswith("I recently spoke with Jane Smith, who suggested I reach out to you. I am Joshua Whang")
    assert "You played for the same program" in mid
    assert "I noticed that you played" not in mid          # cold phrasing must not appear


def test_cold_contact_unchanged_by_referral_feature(firms):
    from outreach.drafts import template_middle
    f = facts(); f.gpa = "4.0/4.0"; f.major = "Economics"
    c = Contact(firm="Baird", first="A", last="B", claremont_alum=True,
                notes="Pomona-Pitzer football, 2018-2021, class of 2022")
    mid = template_middle(c, firms.get("Baird"), f)
    assert mid.startswith("I am Joshua Whang")
    assert "I noticed that you played for the same program" in mid
