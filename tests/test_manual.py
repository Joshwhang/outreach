from pathlib import Path

from outreach.models import split_name
from outreach.sources.manual import parse_csv, parse_pipe_lines


def test_split_name():
    assert split_name("Jane Doe") == ("Jane", "Doe")
    assert split_name("Jane Q. Doe, CFA") == ("Jane", "Doe")
    assert split_name("Prince") == ("Prince", "")
    assert split_name("") == ("", "")


def test_pipe_lines_with_defaults_and_comments():
    text = """# header
Jane Doe | Analyst | Baird | https://linkedin.com/in/janedoe | Pitzer '24
John Smith | Vice President
"""
    cs = parse_pipe_lines(text, default_firm="PIMCO")
    assert len(cs) == 2
    assert cs[0].firm == "Baird" and cs[0].notes == "Pitzer '24" and cs[0].linkedin.endswith("janedoe")
    assert cs[1].firm == "PIMCO" and cs[1].title == "Vice President" and cs[1].source == "manual"


def test_csv_import(tmp_path: Path):
    p = tmp_path / "c.csv"
    p.write_text("Full Name,Position,Company,Email,City\nJane Doe,Analyst,Baird,jdoe@rwbaird.com,Milwaukee\n,,,,\n")
    cs = parse_csv(p)
    assert len(cs) == 1
    c = cs[0]
    assert (c.first, c.last, c.title, c.firm, c.location) == ("Jane", "Doe", "Analyst", "Baird", "Milwaukee")
    assert c.email == "jdoe@rwbaird.com" and c.email_status == "from_api"
