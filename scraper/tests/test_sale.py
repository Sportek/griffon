"""Sale parsing against trimmed copies of real pages (tests/fixtures, fetched in Nov 2026)."""

from pathlib import Path

import httpx
import pytest

from scraper import polite
from scraper.api_sink import to_input
from scraper.sources import centris, duproprio

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def test_centris_condo_for_sale():
    listing = centris._parse_sale_detail(fixture("centris_sale_condo.html"), "https://www.centris.ca/x", "20555078")
    assert listing.external_id == "sale-20555078"  # never collides with a rental offer of the same inscription
    assert (listing.listing_type, listing.price_period, listing.price) == ("sale", "total", 420000.0)
    assert listing.property_type == "condo"
    assert (listing.city, listing.neighborhood) == ("Montréal", "Le Plateau-Mont-Royal")
    assert (listing.bedrooms, listing.bathrooms, listing.area_sqft, listing.year_built) == (1.0, 1.0, 763.0, 2009)
    assert (listing.municipal_assessment, listing.municipal_assessment_year) == (390300.0, 2024)
    # Yearly amounts, not the monthly table next to them.
    assert (listing.municipal_taxes_yearly, listing.school_taxes_yearly) == (2445.0, 276.0)
    assert listing.condo_fees_monthly == 399.0
    assert listing.extra["mls_number"] == "20555078"
    assert listing.extra["Type de copropriété"] == "Divise"


def test_centris_plex_for_sale():
    listing = centris._parse_sale_detail(fixture("centris_sale_triplex.html"), "https://www.centris.ca/x", "18847279")
    assert listing.property_type == "duplex-triplex"
    assert (listing.units, listing.gross_revenue_yearly, listing.lot_area_sqft) == (3, 62400.0, 2305.0)
    # No teaser on a plex: bedrooms and bathrooms are the main dwelling's.
    assert (listing.bedrooms, listing.bathrooms) == (4.0, 2.0)
    assert listing.rooms_qc is None
    assert listing.parking_spots == 2
    assert listing.condo_fees_monthly is None
    assert listing.extra["residential_units"] == "2 x 3 ½, 1 x 7 ½"
    assert listing.extra["expenses_yearly"] == {"Assurances": 3361.0}


def test_sale_fields_reach_the_api():
    listing = centris._parse_sale_detail(fixture("centris_sale_condo.html"), "https://www.centris.ca/x", "20555078")
    sent = to_input(listing.model_dump(mode="json"))
    assert (sent["listingType"], sent["pricePeriod"]) == ("SALE", "TOTAL")
    assert sent["municipalAssessment"] == 390300.0
    assert sent["condoFeesMonthly"] == 399.0


def test_duproprio_condo_for_sale():
    listing = duproprio._parse_sale_page(fixture("duproprio_sale_condo.html"), "https://duproprio.com/x", "1146008", "condo")
    assert (listing.listing_type, listing.price_period, listing.price) == ("sale", "total", 309000.0)
    assert (listing.address, listing.city, listing.postal_code) == ("201-35 rue St-Michel", "Granby", "J2G 4L7")
    assert (listing.latitude, listing.longitude, listing.location_precision) == (45.40244, -72.71219, "exact")
    assert (listing.bedrooms, listing.bathrooms, listing.area_sqft, listing.year_built) == (2.0, 1.0, 1056.0, 1977)
    assert (listing.municipal_taxes_yearly, listing.school_taxes_yearly, listing.condo_fees_monthly) == (
        2200.0,
        180.0,
        376.36,
    )
    assert listing.parking_spots == 1
    assert listing.extra["ownership"] == "Divided"
    assert listing.photos[0].endswith("/1146008/condo-granby-1600-16017773.jpg")  # the cover first
    assert all("/for_sale/" in p and "/1146008/" in p for p in listing.photos)
    assert listing.description.startswith("Condo de plus de 1 000 pieds carrés")  # the owner's own words


def test_duproprio_house_for_sale():
    listing = duproprio._parse_sale_page(
        fixture("duproprio_sale_house.html"), "https://duproprio.com/x", "1145823", "bungalow"
    )
    assert listing.property_type == "house"
    assert (listing.lot_area_sqft, listing.municipal_assessment) == (7000.0, 470000.0)
    assert listing.parking_spots == 5  # 1 interior + 4 exterior
    assert listing.condo_fees_monthly is None


@pytest.mark.parametrize(("slug", "expected"), [("home", "house"), ("cottage", "house"), ("triplex", "duplex-triplex")])
def test_duproprio_type_slugs(slug, expected):
    from scraper.models import Listing

    assert Listing(source="d", external_id="1", url="u", property_type=duproprio._SALE_TYPES.get(slug, slug)).property_type == expected


def _search_page(numbers_by_area: dict[str, list[str]], area: str, total: int, capped: bool) -> str:
    links = "".join(f'<a href="/fr/condo~a-vendre~{loc}/{n}">x</a>' for loc, ns in numbers_by_area.items() for n in ns)
    more = "&#x2B;" if capped else ""
    return f'<span id="numberOfResults">{total}</span>\n<span id="pagingMoreSign">{more}</span>{links}'


def test_centris_sale_splits_a_capped_search_and_flags_what_stays_capped(monkeypatch):
    """montreal is capped: it is split into the boroughs its listings link to; one borough is
    still capped, so the crawl ends with IncompleteCrawl (the run fails, nothing is deactivated)."""
    pages = {
        "/fr/condo~a-vendre~montreal": _search_page(
            {"montreal-ville-marie": ["10000001"], "montreal-anjou": ["10000002"]}, "montreal", 5000, True
        ),
        "/fr/condo~a-vendre~montreal-ville-marie": _search_page(
            {"montreal-ville-marie": ["10000001", "10000003"]}, "", 2, False
        ),
        "/fr/condo~a-vendre~montreal-anjou": _search_page({"montreal-anjou": ["10000002"]}, "", 5000, True),
    }
    details: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path in pages:
            # Past the last page Centris serves the first one again.
            return httpx.Response(200, text=pages[path])
        details.append(path.rsplit("/", 1)[-1])
        return httpx.Response(200, text=fixture("centris_sale_condo.html"))

    real_client = polite.PoliteClient

    def client(*args, **kwargs):
        kwargs.update(transport=httpx.MockTransport(handler), min_delay=0, max_delay=0)
        return real_client(*args, **kwargs)

    monkeypatch.setattr(centris, "PoliteClient", client)
    monkeypatch.setattr(centris.time, "sleep", lambda _s: None)

    listings = []
    with pytest.raises(centris.IncompleteCrawl, match="condo~montreal-anjou"):
        for listing in centris.scrape_sale(areas=["montreal"], categories=["condo"], max_pages_per_area=3):
            listings.append(listing)
    # Every listing once, the one only the borough search showed included.
    assert sorted(details) == ["10000001", "10000002", "10000003"]
    assert {l.external_id for l in listings} == {"sale-10000001", "sale-10000002", "sale-10000003"}
