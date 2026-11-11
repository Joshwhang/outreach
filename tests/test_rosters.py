from outreach.sources.rosters import RosterEntry, parse_people, roster_url, RosterError
import pytest

SAMPLE = '''
<html><script type="application/ld+json">
{"@type":"ListItem","item":[
 {"@type":"Person","name":"Jane Doe","url":"/x"},
 {"@type":"Person","name":"Bo Smith Jr."},
 {"@type":"Organization","name":"Not A Person"},
 {"@type":"Person","name":"Jane Doe"}
]}</script>
<script type="application/ld+json">{"broken json</script></html>
'''


def test_parse_people_dedups_and_filters():
    assert parse_people(SAMPLE) == ["Jane Doe", "Bo Smith Jr."]


def test_parse_people_tolerates_no_json():
    assert parse_people("<html>nothing here</html>") == []


def test_roster_url():
    assert roster_url("pp", "football", 2019) == "https://sagehens.com/sports/football/roster/2019"
    assert roster_url("cms", "mens-golf", 2021) == "https://cmsathletics.org/sports/mens-golf/roster/2021"
    with pytest.raises(RosterError):
        roster_url("ucla", "football", 2019)


def test_tie_phrasing():
    e = RosterEntry("Jane", "Doe", "Pomona-Pitzer", "mens-basketball", 2019)
    assert e.tie == "Pomona-Pitzer mens basketball, 2019 roster"


def test_sport_presets_are_valid_slugs():
    from outreach.sources.rosters import ALL_SPORTS, FINANCE_HEAVY
    assert set(FINANCE_HEAVY) <= set(ALL_SPORTS)
    assert len(ALL_SPORTS) == len(set(ALL_SPORTS))
    for slug in ALL_SPORTS:
        assert slug == slug.lower() and " " not in slug


def test_html_entities_decoded():
    h = '<script type="application/ld+json">{"@type":"ListItem","item":[{"@type":"Person","name":"Gavin B&uuml;tz"},{"@type":"Person","name":"Jos&eacute; O&#39;Neil"}]}</script>'
    assert parse_people(h) == ["Gavin Bütz", "José O'Neil"]
