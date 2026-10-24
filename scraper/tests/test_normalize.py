import pytest

from scraper.models import Listing
from scraper.normalize import IMMEDIATELY, iso_date, parse_number, parse_qc_rooms, property_type
from scraper.sources.kijiji import _city_from_address
from scraper.sources.rentals_ca import _parse_unit_row


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Condo / Appartement", "apartment"),  # Centris
        ("appartement-condo-court-terme", "apartment"),  # Logis Québec
        ("Apartment", "apartment"),  # realtor.ca
        ("condo", "condo"),
        ("Maison de ville", "townhouse"),
        ("chambre-et-colocation", "room"),
        ("Bateau", "bateau"),  # unknown labels stay visible
        (None, None),
    ],
)
def test_property_type_uses_one_vocabulary(raw, expected):
    assert property_type(raw) == expected


def test_listing_keeps_the_raw_property_type():
    listing = Listing(source="centris", external_id="1", url="u", property_type="Condo / Appartement")
    assert listing.property_type == "apartment"
    assert listing.extra["property_type_raw"] == "Condo / Appartement"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1er juillet 2026", "2026-07-01"),
        ("July 1, 2026", "2026-07-01"),
        ("Immédiatement", IMMEDIATELY),
        ("Available", IMMEDIATELY),
        ("N/A", None),
        ("Novembre 2026", "Novembre 2026"),
    ],
)
def test_iso_date(raw, expected):
    assert iso_date(raw) == expected


def test_numbers_and_quebec_rooms():
    assert parse_number("1 350 $") == 1350.0
    assert parse_number("2,250") == 2250.0
    assert parse_qc_rooms("Appartement 4 1/2") == 4.0


@pytest.mark.parametrize(
    ("address", "city"),
    [
        ("Montréal, QC H4K 1J8", "Montréal"),
        ("36 rue de l'Aqueduc, Varennes, QC, J3X 1P4", "Varennes"),
        ("QC", None),
    ],
)
def test_kijiji_city_from_address(address, city):
    assert _city_from_address(address) == city


def test_rentals_ca_furnishing_is_not_an_availability():
    unit = _parse_unit_row("1 Bedroom", ["$1,450", "1 Bath", "567 ft²", "Semi-furnished", "Available"])
    assert unit["price"] == 1450.0
    assert (unit["furnished"], unit["furnishing"], unit["availability"]) == (True, "Semi-furnished", "Available")
