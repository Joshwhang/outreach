from outreach.models import Contact
from outreach.ranking import detect_level, enrich, is_claremont, is_socal


def test_levels():
    assert detect_level("Investment Banking Analyst") == "Analyst"
    assert detect_level("Associate, M&A") == "Associate"
    assert detect_level("Vice President") == "VP"
    assert detect_level("VP - Healthcare") == "VP"
    assert detect_level("Executive Director") == "Director"
    assert detect_level("Managing Director, Head of West Coast") == "MD"
    assert detect_level("Financial Advisor") == "Other"
    assert detect_level("") == "Other"


def test_claremont_and_socal():
    assert is_claremont("Pitzer College")
    assert is_claremont("", "met at CMC info session")
    assert not is_claremont("UCLA")
    assert is_socal("Los Angeles, California")
    assert is_socal("Newport Beach")
    assert not is_socal("New York, NY")


def test_priority_order():
    alum = enrich(Contact(firm="X", first="A", last="B", title="Managing Director", school="Pomona College"))
    analyst = enrich(Contact(firm="X", first="A", last="C", title="Analyst", location="New York"))
    socal_vp = enrich(Contact(firm="X", first="A", last="D", title="Vice President", location="Irvine, CA"))
    other = enrich(Contact(firm="X", first="A", last="E", title="Director", location="Chicago"))
    assert (alum.priority, analyst.priority, socal_vp.priority, other.priority) == (1, 2, 3, 4)
    assert alum.claremont_alum is True
