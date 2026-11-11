from outreach.firms import FirmBook, candidate_emails, expand_pattern, load_firms
from outreach.config import FIRMS_CSV


def test_expand_patterns():
    assert expand_pattern("first.last", "Jane", "Doe", "x.com") == "jane.doe@x.com"
    assert expand_pattern("flast", "Jane", "Doe", "x.com") == "jdoe@x.com"
    assert expand_pattern("first_last", "Jane", "Doe", "x.com") == "jane_doe@x.com"
    assert expand_pattern("firstl", "Jane", "Doe", "x.com") == "janed@x.com"
    assert expand_pattern("lastf", "Jane", "Doe", "x.com") == "doej@x.com"
    assert expand_pattern("first", "Jane", "Doe", "x.com") == "jane@x.com"


def test_expand_strips_punctuation_and_accents():
    assert expand_pattern("first.last", "José", "O'Brien-Smith", "x.com") == "jose.obriensmith@x.com"


def test_expand_missing_pieces():
    assert expand_pattern("first.last", "", "Doe", "x.com") == ""
    assert expand_pattern("first.last", "Jane", "", "x.com") == ""
    assert expand_pattern("first.last", "Jane", "Doe", "") == ""
    assert expand_pattern("bogus", "Jane", "Doe", "x.com") == ""


def test_candidates_primary_then_alternates_dedup(firms):
    baird = firms.get("Baird")
    cands = candidate_emails(baird, "Jane", "Doe")
    assert cands[0] == "jdoe@rwbaird.com"
    assert cands[1] == "jane.doe@rwbaird.com"
    assert len(cands) == len(set(cands))


def test_lookup_exact_alias_and_substring(firms):
    assert firms.get("robert w baird").name == "Baird"
    assert firms.get("MSWM").name == "Morgan Stanley Wealth Management"
    assert firms.get("pimco").name == "PIMCO"
    assert firms.get("Nonexistent Bank") is None
    assert firms.get("") is None


def test_shipped_csv_loads_and_is_sane():
    fs = load_firms(FIRMS_CSV)
    assert len(fs) > 100
    names = [f.name for f in fs]
    assert len(names) == len(set(names)), "duplicate firm names"
    for f in fs:
        assert f.type in ("IB", "AM", "WM", "RE", "PE"), f.name
        assert "." in f.domain, f.name
        assert expand_pattern(f.pattern, "Jane", "Doe", f.domain), f"{f.name} bad pattern {f.pattern}"
        for p in f.alt_patterns:
            assert expand_pattern(p, "Jane", "Doe", f.domain) or p == "first.m.last", f"{f.name} bad alt {p}"


def test_shipped_csv_covers_tracker_firms():
    fb = FirmBook.load()
    for name in ["Baird", "Piper Sandler", "Raymond James", "William Blair", "Houlihan Lokey", "Stifel",
                 "Lincoln International", "Harris Williams", "Fidelity", "Neuberger Berman", "AllianceBernstein",
                 "Lord Abbett", "Northern Trust", "T. Rowe Price", "Baird PWM", "William Blair IM", "Hines",
                 "Eastdil Secured", "CBRE", "JLL", "Cushman & Wakefield", "Tishman Speyer", "Related Companies",
                 "Brookfield", "Goldman Sachs", "JPMorgan", "Morgan Stanley", "Bank of America", "Citi", "Blackstone"]:
        assert fb.get(name) is not None, name


def test_short_aliases_do_not_substring_match():
    fb = FirmBook.load()
    for bogus in ["KINGSROCK SECURITIES LLC", "TPEG SECURITIES, LLC", "EQUITABLE ADVISORS, LLC",
                  "NATIONAL FINANCIAL SERVICES LLC"]:
        assert fb.get(bogus) is None, f"{bogus} matched {fb.get(bogus).name}"
    # and a name containing another firm's name as a substring must NOT match that other firm
    assert fb.get("CRAIG-HALLUM CAPITAL GROUP LLC").name == "Craig-Hallum"


def test_legal_names_still_match():
    fb = FirmBook.load()
    assert fb.get("GOLDMAN SACHS & CO. LLC").name == "Goldman Sachs"
    assert fb.get("J.P. MORGAN SECURITIES LLC").name == "JPMorgan"
    assert fb.get("MORGAN STANLEY & CO. LLC").name == "Morgan Stanley"
    assert fb.get("WELLS FARGO CLEARING SERVICES, LLC").name == "Wells Fargo"
    assert fb.get("HOULIHAN LOKEY CAPITAL, INC.").name == "Houlihan Lokey"
    assert fb.get("TIAA-CREF INDIVIDUAL & INSTITUTIONAL SERVICES, LLC").name == "Nuveen"
    assert fb.get("GS").name == "Goldman Sachs"          # exact alias still works
