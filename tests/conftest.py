import pytest

from outreach.firms import Firm, FirmBook


@pytest.fixture
def firms():
    return FirmBook([
        Firm(name="Baird", type="IB", tier="MM", domain="rwbaird.com", pattern="flast",
             alt_patterns=["first.last"], aliases=["Robert W. Baird"], hq="Milwaukee"),
        Firm(name="PIMCO", type="AM", tier="AM", domain="pimco.com", pattern="first.last", hq="Newport Beach"),
        Firm(name="Morgan Stanley Wealth Management", type="WM", tier="WM", domain="morganstanley.com",
             pattern="first.last", aliases=["MSWM"]),
    ])
