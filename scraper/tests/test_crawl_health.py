"""Retries, Cloudflare detection and the "incomplete crawl must not deactivate" path."""

import json

import httpx
import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout

from scraper import browser, polite
from scraper.api_sink import ApiSink
from scraper.polite import CrawlHealth, IncompleteCrawl, PoliteClient, SourceBlocked, request_budget
from scraper.sources import centris


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    # polite.time, browser.time and centris.time are all the `time` module: one patch.
    slept = []
    monkeypatch.setattr(polite.time, "sleep", lambda s: slept.append(s) if s >= 1 else None)
    return slept


def _client(handler, **kwargs):
    return PoliteClient(source="test", transport=httpx.MockTransport(handler), min_delay=0, max_delay=0, **kwargs)


# --- PoliteClient -------------------------------------------------------------------------


def test_timeouts_are_retried_with_backoff(no_sleep):
    outcomes = iter([httpx.ReadTimeout("slow"), httpx.ConnectError("reset"), httpx.Response(200)])

    def handler(request):
        item = next(outcomes)
        if isinstance(item, Exception):
            raise item
        return item

    with _client(handler) as c:
        assert c.get("https://example.test/").status_code == 200
    assert no_sleep == [15, 30]


def test_timeouts_give_up_after_the_retries():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with _client(handler, max_retries=2) as c, pytest.raises(httpx.ReadTimeout):
        c.get("https://example.test/")
    assert c.requests_sent == 3


def test_cloudflare_challenge_stops_at_the_first_response():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(403, headers={"cf-mitigated": "challenge"})

    with _client(handler) as c, pytest.raises(SourceBlocked, match="Cloudflare challenge"):
        try:  # not swallowed by the sources' `except Exception`
            c.get("https://example.test/")
        except Exception:
            pass
    assert len(calls) == 1


def test_request_budget_resolution(monkeypatch):
    monkeypatch.setenv("SCRAPER_MAX_REQUESTS", "6000")
    monkeypatch.delenv("SCRAPER_MAX_REQUESTS_LOGIS_QUEBEC", raising=False)
    assert request_budget("centris") == 6000
    assert request_budget("logis_quebec", 12000) == 12000  # the source's need beats the global cap
    monkeypatch.setenv("SCRAPER_MAX_REQUESTS_LOGIS_QUEBEC", "800")
    assert request_budget("logis_quebec", 12000) == 800  # an explicit per-source setting wins


# --- CrawlHealth --------------------------------------------------------------------------


def test_a_few_lost_details_are_tolerated(capsys):
    health = CrawlHealth("test", max_failure_ratio=0.02)
    for _ in range(99):
        health.ok("detail")
    health.failed("detail", "https://x/1", httpx.ReadTimeout("slow"))
    health.finish()  # 1% lost: complete enough
    err = capsys.readouterr().err
    assert "[test] detail failed (1/100 so far): https://x/1: ReadTimeout: slow" in err
    assert "[test] crawl: details 99/100 ok" in err


def test_too_many_lost_pages_make_the_crawl_incomplete():
    health = CrawlHealth("test", max_failure_ratio=0.02)
    for _ in range(9):
        health.ok("search page")
    health.failed("search page", "page 10", "HTTP 503")
    with pytest.raises(IncompleteCrawl, match="1/10 search pages lost"):
        health.finish()


def test_a_skipped_area_always_makes_the_crawl_incomplete():
    health = CrawlHealth("test", max_failure_ratio=0.5)
    health.ok("search page")
    health.gap("laval: given up")
    with pytest.raises(IncompleteCrawl, match="laval: given up"):
        health.finish()


# --- ApiSink: an incomplete run succeeds without deactivating ----------------------------


def _recording_sink():
    finishes = []

    def handler(request):
        body = json.loads(request.content)
        if "finishIngestionRun" in body["query"]:
            finishes.append(body["variables"])
            return httpx.Response(200, json={"data": {"finishIngestionRun": {"status": body["variables"]["status"]}}})
        return httpx.Response(200, json={"data": {}})

    sink = ApiSink("http://api.test/graphql", retry_delays=())
    sink._client = httpx.Client(transport=httpx.MockTransport(handler))
    return sink, finishes


def test_incomplete_crawl_finishes_succeeded_without_deactivation():
    sink, finishes = _recording_sink()
    with pytest.raises(IncompleteCrawl), sink.attach("run1", source="centris", mark_unseen_inactive=True):
        raise IncompleteCrawl("centris: 30/400 details lost")
    assert finishes[0]["status"] == "SUCCEEDED"
    assert finishes[0]["markUnseenInactive"] is False
    assert "incomplete crawl" in finishes[0]["error"]


def test_complete_crawl_still_deactivates_and_blocked_one_fails():
    sink, finishes = _recording_sink()
    with sink.attach("run1", source="centris", mark_unseen_inactive=True):
        pass
    with pytest.raises(SourceBlocked), sink.attach("run2", source="centris", mark_unseen_inactive=True):
        raise SourceBlocked("centris: 3 consecutive HTTP 403")
    assert (finishes[0]["status"], finishes[0]["markUnseenInactive"]) == ("SUCCEEDED", True)
    assert finishes[1]["status"] == "FAILED"


# --- centris scrape loop ------------------------------------------------------------------


def _search_html(ids, total):
    links = "".join(f'<a href="/fr/condo~a-louer~laval/{i}">x</a>' for i in ids)
    return f'<span class="js-resultCount font-weight-bold">{total}</span>{links}'


def _run_centris(monkeypatch, handler, **kwargs):
    def client_factory(*args, **kw):
        kw.update(transport=httpx.MockTransport(handler), min_delay=0, max_delay=0)
        return PoliteClient(*args, **kw)

    monkeypatch.setattr(centris, "PoliteClient", client_factory)
    out = []
    try:
        for listing in centris.scrape(areas=["laval"], delay_s=0, **kwargs):
            out.append(listing.external_id)
    except IncompleteCrawl as e:
        return out, e
    return out, None


def test_centris_pins_one_sort_seed_and_counts_detail_failures(monkeypatch):
    pages = {1: ["1000001", "1000002"], 2: ["1000003", "1000004"], 3: []}
    seeds = set()

    def handler(request):
        if "propriete~a-louer" in request.url.path:
            seeds.add(request.url.params["sortSeed"])
            return httpx.Response(200, text=_search_html(pages[int(request.url.params.get("page", 1))], 4))
        if request.url.path.endswith("1000003"):
            return httpx.Response(404)
        return httpx.Response(200, text="<html></html>")

    listings, incomplete = _run_centris(monkeypatch, handler)
    assert listings == ["1000001", "1000002", "1000004"]
    assert len(seeds) == 1  # same shuffle on every page, or pages overlap and listings are missed
    assert incomplete is not None and "1/4 details lost" in str(incomplete)


def test_centris_keeps_going_past_a_failed_search_page(monkeypatch):
    calls = {"page2": 0}

    def handler(request):
        if "propriete~a-louer" in request.url.path:
            page = int(request.url.params.get("page", 1))
            if page == 2:
                calls["page2"] += 1
                return httpx.Response(503)
            ids = {1: ["1000001"], 3: ["1000003"], 4: []}[page]
            return httpx.Response(200, text=_search_html(ids, 3))
        return httpx.Response(200, text="<html></html>")

    listings, incomplete = _run_centris(monkeypatch, handler)
    assert listings == ["1000001", "1000003"]  # page 3 is still crawled
    assert calls["page2"] == 4  # 1 try + 3 retries with backoff
    assert incomplete is not None and "search pages lost" in str(incomplete)


def test_centris_flags_an_area_listed_far_below_its_result_count(monkeypatch):
    def handler(request):
        if "propriete~a-louer" in request.url.path:
            page = int(request.url.params.get("page", 1))
            return httpx.Response(200, text=_search_html(["1000001"] if page == 1 else [], 700))
        return httpx.Response(200, text="<html></html>")

    listings, incomplete = _run_centris(monkeypatch, handler)
    assert listings == ["1000001"]
    assert incomplete is not None and "only 1 of 700" in str(incomplete)


def test_centris_full_crawl_is_complete(monkeypatch):
    def handler(request):
        if "propriete~a-louer" in request.url.path:
            page = int(request.url.params.get("page", 1))
            return httpx.Response(200, text=_search_html(["1000001", "1000002"] if page == 1 else [], 2))
        return httpx.Response(200, text="<html></html>")

    listings, incomplete = _run_centris(monkeypatch, handler)
    assert listings == ["1000001", "1000002"] and incomplete is None


def test_result_count_with_thousands_separator():
    assert centris._result_count('<span class="js-resultCount font-weight-bold">1 234</span>') == 1234
    assert centris._result_count("<p>nothing</p>") is None


# --- browser navigation -------------------------------------------------------------------


class _FakePage:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes)
        self.calls = 0

    def goto(self, url, **kwargs):
        self.calls += 1
        item = self.outcomes.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def test_goto_retries_a_timeout_then_succeeds(no_sleep):
    page = _FakePage([PlaywrightTimeout("Page.goto: Timeout 30000ms exceeded."), "response"])
    assert browser.goto_with_retry(page, "https://rentals.ca/laval?p=2", source="rentals_ca") == "response"
    assert page.calls == 2 and no_sleep == [15]


def test_goto_gives_up_after_the_retries(no_sleep):
    page = _FakePage([PlaywrightTimeout("Timeout")] * 3)
    with pytest.raises(PlaywrightTimeout):
        browser.goto_with_retry(page, "https://rentals.ca/laval?p=2", source="rentals_ca", retries=2)
    assert page.calls == 3 and no_sleep == [15, 45]
