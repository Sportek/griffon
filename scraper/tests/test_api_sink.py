import httpx
import pytest

from scraper.api_sink import _FIELDS, ApiSink, to_input
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


def _sink_with(responses):
    calls = iter(responses)

    def handler(request):
        item = next(calls)
        if isinstance(item, Exception):
            raise item
        return item

    sink = ApiSink("http://api.test/graphql", retry_delays=(0, 0, 0))
    sink._client = httpx.Client(transport=httpx.MockTransport(handler))
    return sink


def test_transient_errors_are_retried_until_the_api_is_back():
    ok = httpx.Response(200, json={"data": {"listings": {"totalElements": 7}}})
    sink = _sink_with([httpx.Response(404), httpx.ConnectError("refused"), httpx.Response(502), ok])
    assert len(sink) == 7


def test_retries_give_up_and_client_errors_fail_at_once():
    sink = _sink_with([httpx.Response(503)] * 4)
    with pytest.raises(httpx.HTTPStatusError):
        len(sink)
    sink = _sink_with([httpx.Response(401)])
    with pytest.raises(httpx.HTTPStatusError):
        len(sink)
