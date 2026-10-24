from scraper.api_sink import _FIELDS, to_input
from scraper.models import Listing


def test_every_model_field_is_sent_to_the_api():
    # A new Listing field must be added to the API schema and to _FIELDS, or it is dropped.
    assert set(Listing.model_fields) == set(_FIELDS)


def test_to_input_maps_names_and_enums():
    row = Listing(source="kijiji", external_id="1", url="u", listing_type="rent", rooms_qc=4.0).model_dump(mode="json")
    sent = to_input(row)
    assert sent["externalId"] == "1"
    assert sent["listingType"] == "RENT"
    assert sent["pricePeriod"] == "MONTHLY"
    assert sent["roomsQc"] == 4.0
    assert "price" not in sent  # None values are omitted
