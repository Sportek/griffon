"""Stopping a run from the API (cancelIngestionRun) and resuming one (resumeIngestionRun)."""

import json
import time

import httpx
import pytest

from scraper import polite, worker
from scraper.api_sink import ApiSink
from scraper.models import Listing
from scraper.polite import PoliteClient, RunCancelled, already_sent


class FakeApi:
    """Answers the worker's GraphQL calls and records what it was told."""

    def __init__(self, *, heartbeat=True, already_seen=()):
        self.heartbeat = heartbeat
        self.already_seen = list(already_seen)
        self.sent: list[str] = []
        self.finished: dict | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        query, variables = body["query"], body["variables"]
        if "heartbeatIngestionRun" in query:
            data = {"heartbeatIngestionRun": self.heartbeat}
        elif "ingestionRunAlreadySeen" in query:
            data = {"ingestionRunAlreadySeen": self.already_seen}
        elif "upsertListings" in query:
            self.sent += [row["externalId"] for row in variables["listings"]]
            n = len(variables["listings"])
            data = {"upsertListings": {"received": n, "created": n, "updated": 0, "unchanged": 0, "rejected": 0,
                                       "results": []}}
        elif "finishIngestionRun" in query:
            self.finished = variables
            data = {"finishIngestionRun": {"status": variables["status"]}}
        else:
            raise AssertionError(query)
        return httpx.Response(200, json={"data": data})

    def sink(self) -> ApiSink:
        sink = ApiSink("http://api.test/graphql", retry_delays=(0,))
        sink._client = httpx.Client(transport=httpx.MockTransport(self.handler))
        return sink


@pytest.fixture
def api(monkeypatch):
    def make(**kwargs):
        fake = FakeApi(**kwargs)
        monkeypatch.setattr(worker, "ApiSink", fake.sink)  # the heartbeat thread's own client
        return fake
    return make


def _listing(external_id: str) -> Listing:
    return Listing(source="kijiji", external_id=external_id, url=f"https://x/{external_id}", listing_type="rent")


def test_heartbeat_answered_false_cancels_the_run(api, monkeypatch):
    fake = api(heartbeat=False)

    def endless(_args):
        for i in range(10_000):
            time.sleep(0.01)
            yield _listing(str(i))

    monkeypatch.setitem(worker.SOURCES, "kijiji", endless)
    run = {"id": "r1", "source": "kijiji", "params": {"markUnseenInactive": True}}
    worker.execute(fake.sink(), run, heartbeat_s=0.05)

    assert fake.finished["status"] == "CANCELLED"
    assert fake.finished["markUnseenInactive"] is False  # a stopped run never deactivates
    assert 0 < len(fake.sent) < 10_000
    assert not polite.CANCEL.is_set()  # ready for the next run


def test_resumed_run_hands_the_already_sent_ids_to_the_source(api, monkeypatch):
    fake = api(already_seen=["1", "2"])

    def source(_args):
        for external_id in ("1", "2", "3"):
            if not already_sent(external_id):
                yield _listing(external_id)

    monkeypatch.setitem(worker.SOURCES, "kijiji", source)
    run = {"id": "r2", "source": "kijiji", "resumeOf": "r1", "params": {}}
    worker.execute(fake.sink(), run, heartbeat_s=60)

    assert fake.sent == ["3"]
    assert fake.finished["status"] == "SUCCEEDED"
    assert not polite.ALREADY_SENT  # cleared for the next run


def test_a_run_that_resumes_nothing_skips_nothing(api, monkeypatch):
    fake = api(already_seen=["1"])
    monkeypatch.setitem(worker.SOURCES, "kijiji", lambda _args: (_listing(i) for i in ("1", "2") if not already_sent(i)))
    worker.execute(fake.sink(), {"id": "r3", "source": "kijiji", "params": {}}, heartbeat_s=60)
    assert fake.sent == ["1", "2"]


def test_polite_client_refuses_to_send_once_cancelled():
    client = PoliteClient(source="t", min_delay=0, max_delay=0,
                          transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    try:
        polite.CANCEL.set()
        with pytest.raises(RunCancelled):
            client.get("https://example.test/")
    finally:
        polite.CANCEL.clear()
        client.close()
