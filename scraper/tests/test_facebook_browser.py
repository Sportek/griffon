"""The in-page JS (FEED_ARTICLES_JS, SEE_MORE_JS) against the fixture, in a real Chromium.
Skipped when Playwright's browser isn't installed."""

from pathlib import Path

import pytest

from scraper.facebook.extract import (
    FEED_ARTICLES_JS,
    SEE_MORE_JS,
    SEE_MORE_LABELS,
    SEE_MORE_SELECTOR,
    parse_article,
    split_articles,
)

FIXTURE = Path(__file__).parent / "fixtures" / "facebook" / "group_feed.html"


UNITS_FIXTURE = Path(__file__).parent / "fixtures" / "facebook" / "group_feed_units.html"


@pytest.fixture(scope="module")
def browser():
    sync_api = pytest.importorskip("playwright.sync_api")
    with sync_api.sync_playwright() as pw:
        try:
            browser = pw.chromium.launch()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"no Chromium: {e}")
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(browser):
    page = browser.new_page()
    page.set_content(FIXTURE.read_text(encoding="utf-8"))
    return page


@pytest.fixture(scope="module")
def units_page(browser):
    page = browser.new_page()
    page.set_content(UNITS_FIXTURE.read_text(encoding="utf-8"))
    return page


def test_feed_articles_js_matches_the_python_twin(page):
    from_browser = page.evaluate(FEED_ARTICLES_JS)
    assert len(from_browser) == len(split_articles(FIXTURE.read_text(encoding="utf-8"))) == 5
    ids = [p.post_id for html in from_browser if (p := parse_article(html, group="242242325809377"))]
    assert ids == ["1234567890123456", "2468013579246801", "1357913579135791", "8642097531864209"]


def test_see_more_buttons_of_posts_only(page):
    assert page.evaluate(SEE_MORE_JS, sorted(SEE_MORE_LABELS)) == 1
    assert page.locator(SEE_MORE_SELECTOR).count() == 1
    assert page.evaluate(SEE_MORE_JS, sorted(SEE_MORE_LABELS)) == 0  # not marked twice


def test_feed_units_js_matches_the_python_twin(units_page):
    from_browser = units_page.evaluate(FEED_ARTICLES_JS)
    assert len(from_browser) == len(split_articles(UNITS_FIXTURE.read_text(encoding="utf-8"))) == 3
    ids = [p.post_id for html in from_browser if (p := parse_article(html, group="242242325809377"))]
    assert ids == ["29825807217026163", "29824949407111944"]


def test_see_more_of_unit_posts_not_of_their_comments(units_page):
    assert units_page.evaluate(SEE_MORE_JS, sorted(SEE_MORE_LABELS)) == 1
