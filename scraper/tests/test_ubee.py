"""ubee.com parsing and crawl against trimmed copies of real pages (tests/fixtures/ubee, Nov 2026)."""

import json
import sys
from pathlib import Path

import httpx
import pytest

from scraper import main, polite
from scraper.polite import IncompleteCrawl, SourceBlocked
from scraper.sources import ubee

FIXTURES = Path(__file__).parent / "fixtures" / "ubee"


def page(name: str) -> str:
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def search(kind: str) -> dict:
    return json.loads((FIXTURES / f"search_{kind}.json").read_text(encoding="utf-8"))


def parse(name: str):
    html = page(name)
    detail = ubee.detail_record(html)
    kind = name.split("_")[0]
    card = next(c for c in search(kind)["items"] if c["slugFr"] == detail["slugFr"])
    return ubee.to_listing(card, detail, sale=kind == "sale", title=ubee.page_title(html))


def test_rental_condo_published_by_its_owner():
    listing = parse("rent_condo_owner")
    assert (listing.source, listing.external_id) == ("ubee", "d3cb9fc5-0898-4942-b95e-7111708f1c08")
    assert listing.url == "https://ubee.com/a-louer/montreal/condo-104-7995-av-shelley-d3cb9f"
    assert (listing.listing_type, listing.price, listing.price_period) == ("rent", 1650.0, "monthly")
    assert listing.property_type == "apartment"  # ubee files every rental apartment as "Condo"
    assert (listing.address, listing.city, listing.postal_code) == ("104-7995 Av Shelley", "Montréal", "H1Z 3H5")
    assert (listing.latitude, listing.location_precision) == (pytest.approx(45.5639, abs=1e-3), "exact")
    assert (listing.bedrooms, listing.bathrooms, listing.area_sqft, listing.year_built) == (2.0, 1.0, 650.0, 2024)
    assert listing.rooms_qc == 4.0  # "Spacieux 4 ½ à louer"
    assert listing.description.startswith("Spacieux 4")
    assert len(listing.photos) == 3 and all(p.startswith("https://res.cloudinary.com/") for p in listing.photos)
    assert listing.extra["listed_by"] == "owner"
    assert "mls_number" not in listing.extra
    assert listing.available_date is None  # the site ships "TODO" as the move-in date
    assert listing.published_at.startswith("2026-06-19")


def test_rental_house():
    listing = parse("rent_house_owner")
    assert (listing.property_type, listing.price, listing.parking_spots) == ("house", 3950.0, 2)
    assert (listing.area_sqft, listing.lot_area_sqft) == (2000.0, None)  # no lot on a rental
    assert listing.extra["property_style"] == "plain-pied"
    assert listing.description.startswith("Emplacement de rêve\n")  # HTML paragraphs kept as lines


def test_centris_syndication_is_recognized_with_its_number():
    detail = ubee.detail_record(page("rent_condo_centris"))
    assert ubee.centris_number(detail) == "28657409"
    listing = parse("rent_condo_centris")
    assert listing.extra["mls_number"] == "28657409"
    assert (listing.city, listing.neighborhood) == ("Montréal", "Saint-Léonard")
    assert listing.agency_name == "Remax 2001 inc."
    assert listing.contact_name is None  # never the broker's own name, phone or email
    assert "Courtier" not in json.dumps(listing.model_dump(mode="json"), ensure_ascii=False)
    assert ubee.centris_number(ubee.detail_record(page("rent_condo_owner"))) is None


def test_centris_without_an_mls_number_is_still_recognized():
    detail = ubee.detail_record(page("rent_condo_centris"))
    detail["mlsNumber"] = None
    assert ubee.centris_number(detail) == "28657409"  # from the passerelle.centris.ca link
    detail["additionalLinks"] = None
    assert ubee.centris_number(detail) == ""  # descriptions sourced from Centris


def test_house_for_sale():
    listing = parse("sale_house_owner")
    assert (listing.listing_type, listing.price_period, listing.price) == ("sale", "total", 519500.0)
    assert listing.property_type == "house"
    assert (listing.bedrooms, listing.bathrooms, listing.parking_spots) == (3.0, 2.0, 4)
    assert (listing.area_sqft, listing.lot_area_sqft) == (1104.4, 6500.3)
    assert listing.municipal_assessment == 210800 + 224800  # land + building
    assert listing.furnished is True and listing.extra["furnishing"] == "semi-meublé"
    assert "Garage" in listing.amenities
    assert listing.available_date is None


def test_condo_for_sale():
    listing = parse("sale_condo_owner")
    assert (listing.property_type, listing.price, listing.rooms_qc) == ("condo", 635000.0, 4.0)
    assert listing.bedrooms is None  # not filled in (0 on ubee)
    assert listing.pets_allowed is True
    assert "Climatiseur central" in listing.amenities and "Ascenseur" in listing.amenities
    assert listing.description.startswith("Condo de luxe avec vue saisissante\n")


def test_plex_for_sale():
    owner = parse("sale_plex_owner")
    assert owner.property_type == "duplex-triplex"
    assert (owner.units, owner.gross_revenue_yearly, owner.municipal_assessment) == (7, 43000.0, 329500.0)
    assert owner.rooms_qc is None  # a "X 1/2" in a plex's text is one of its units

    centris = parse("sale_plex_centris")
    assert (centris.units, centris.extra["residential_units"]) == (2, "1 x 5 ½, 1 x 6 ½")
    assert (centris.municipal_taxes_yearly, centris.school_taxes_yearly) == (3931.0, 465.0)
    assert (centris.municipal_assessment, centris.municipal_assessment_year) == (576900.0, 2026)
    assert (centris.bathrooms, centris.gross_revenue_yearly) == (1.5, 39720.0)


def test_only_homes_are_kept():
    kinds = {c["slugFr"]: ubee.is_home(c) for c in search("sale")["items"] + search("rent")["items"]}
    assert kinds["commercial-880-rue-craig-380b38"] is True  # a plex
    assert kinds["terrain-rue-du-domaine-corona-36a8a0"] is False
    assert kinds["commercial-755-rue-berri-a27f9e"] is False
    assert kinds["commercial-saint-jean-6a78bd"] is False  # industrial premises


# --- Crawl ---------------------------------------------------------------------------------

PAGES = {
    "condo-104-7995-av-shelley-d3cb9f": "rent_condo_owner",
    "unifamiliale-47-av-fifth-caef42": "rent_house_owner",
    "condo-6969-a-rue-rainier-2568c1": "rent_condo_centris",
    "unifamiliale-44-rue-elgin-a66ece": "sale_house_owner",
    "condo-322-rue-des-veterans-ca3582": "sale_condo_owner",
    "commercial-880-rue-craig-380b38": "sale_plex_owner",
    "commercial-10531-10533-av-armand-lavergne-33c55f": "sale_plex_centris",
}


@pytest.fixture
def site(monkeypatch):
    """Serves the fixtures; returns the list of requested URLs (and a dict of overrides)."""
    calls: list[str] = []
    overrides: dict[str, httpx.Response] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        calls.append(url)
        for needle, response in overrides.items():
            if needle in url:
                return response
        if "offered-properties" in url:
            return httpx.Response(200, json=search("sale" if "forSale=true" in url else "rent"))
        slug = request.url.path.rsplit("/", 1)[-1]
        if slug in PAGES:
            return httpx.Response(200, text=page(PAGES[slug]))
        return httpx.Response(404)

    real = polite.PoliteClient

    def client(*args, **kwargs):
        kwargs.update(transport=httpx.MockTransport(handler), min_delay=0, max_delay=0)
        return real(*args, **kwargs)

    monkeypatch.setattr(ubee, "PoliteClient", client)
    return calls, overrides


def test_rent_crawl_skips_centris_and_non_homes(site, capsys):
    calls, _ = site
    listings = list(ubee.scrape(cache_path=""))
    assert sorted(l.external_id[:6] for l in listings) == ["caef42", "d3cb9f"]
    assert all(l.listing_type == "rent" for l in listings)
    # One search request, then one detail page per home: none for the terrain or the industrial unit.
    assert len(calls) == 1 + 3
    assert "skipped 1 Centris syndications, 2 non-homes" in capsys.readouterr().err


def test_sale_crawl(site):
    listings = list(ubee.scrape_sale(cache_path=""))
    assert sorted(l.external_id[:6] for l in listings) == ["380b38", "a66ece", "ca3582"]
    assert all((l.listing_type, l.price_period) == ("sale", "total") for l in listings)


def test_syndications_can_be_kept(site):
    listings = list(ubee.scrape(skip_centris=False, cache_path=""))
    centris = next(l for l in listings if l.external_id.startswith("2568c1"))
    assert centris.extra["mls_number"] == "28657409"


def test_the_cache_saves_detail_requests(site, tmp_path):
    calls, _ = site
    cache = str(tmp_path / "ubee.json")
    first = list(ubee.scrape(cache_path=cache))
    calls.clear()
    second = list(ubee.scrape(cache_path=cache))
    assert len(calls) == 1  # only the search: Centris ids are known, owner details are fresh
    assert [l.model_dump(exclude={"scraped_at"}) for l in second] == [l.model_dump(exclude={"scraped_at"}) for l in first]
    saved = json.loads(Path(cache).read_text(encoding="utf-8"))
    assert saved["2568c104-3f5b-5b74-ba90-00b0660cc5c0"] == {"mls": "28657409"}


def test_a_changed_card_fetches_the_detail_again(site, tmp_path, monkeypatch):
    calls, _ = site
    cache = str(tmp_path / "ubee.json")
    list(ubee.scrape(cache_path=cache))
    changed = search("rent")
    next(c for c in changed["items"] if c["slugFr"].endswith("d3cb9f"))["askPrice"] = 1600
    monkeypatch.setattr(sys.modules[__name__], "search", lambda kind: changed)
    calls.clear()
    listings = list(ubee.scrape(cache_path=cache))
    assert len(calls) == 2 and calls[1].endswith("d3cb9f")
    assert next(l for l in listings if l.external_id.startswith("d3cb9f")).price == 1600.0


def test_a_block_stops_at_once(site):
    calls, overrides = site
    overrides["caef42"] = httpx.Response(429, headers={"Retry-After": "1"})
    with pytest.raises(SourceBlocked):
        list(ubee.scrape(cache_path=""))
    assert sum("caef42" in c for c in calls) == 1  # no retry


def test_lost_details_make_the_crawl_incomplete(site):
    _, overrides = site
    overrides["d3cb9f"] = httpx.Response(200, text="<html>maintenance</html>")
    with pytest.raises(IncompleteCrawl):
        list(ubee.scrape(cache_path=""))


def test_a_listing_gone_since_the_search_is_not_a_failure(site):
    _, overrides = site
    overrides["d3cb9f"] = httpx.Response(410)
    listings = list(ubee.scrape(cache_path=""))  # no IncompleteCrawl
    assert [l.external_id[:6] for l in listings] == ["caef42"]


def test_registered_outside_all():
    assert {"ubee", "ubee_sale"} <= set(main.SOURCES)
    assert {"ubee", "ubee_sale"} <= main.DISABLED_FROM_ALL
