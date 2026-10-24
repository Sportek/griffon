"""PoliteClient against an in-memory transport: no network, no real waiting."""

import httpx
import pytest

from scraper import polite
from scraper.polite import PoliteClient, SourceBlocked


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(polite.time, "sleep", slept.append)
    return slept


def client(statuses, **kwargs):
    responses = iter(statuses)

    def handler(request):
        status, headers = next(responses)
        return httpx.Response(status, headers=headers)

    return PoliteClient(source="test", transport=httpx.MockTransport(handler), min_delay=0, max_delay=0, **kwargs)


def test_retry_after_is_honoured(no_sleep):
    with client([(429, {"Retry-After": "12"}), (200, {})]) as c:
        assert c.get("https://example.test/").status_code == 200
    assert 12.0 in no_sleep


def test_consecutive_blocks_stop_the_source_even_inside_except_exception():
    with client([(403, {})] * 5) as c, pytest.raises(SourceBlocked):
        for _ in range(5):
            try:  # what the sources do around detail fetches
                c.get("https://example.test/")
            except Exception:
                pass


def test_request_budget():
    with client([(200, {})] * 5, max_requests=2) as c:
        c.get("https://example.test/")
        c.get("https://example.test/")
        with pytest.raises(SourceBlocked, match="budget"):
            c.get("https://example.test/")
