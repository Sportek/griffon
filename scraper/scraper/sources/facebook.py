"""Facebook groups: rental posts from groups the scraping account is a member of.

Needs a logged-in session (python -m scraper.facebook_login, see the README). One run:

1. Collect: for each group in FACEBOOK_GROUPS, one at a time, open the feed sorted by new
   posts and scroll it slowly like a person would (randomized wheel steps and pauses,
   "See more" expanded), until reaching posts already seen in an earlier run, posts older
   than FACEBOOK_MAX_AGE_DAYS, FACEBOOK_MAX_POSTS_PER_GROUP posts or FACEBOOK_MAX_SCROLLS.
   A login / checkpoint page fails the run at once (SessionExpired) instead of insisting.
   The refreshed cookies are saved back to the session file.
2. Filter: dedupe by post id and by normalized text (reposts across groups), then the
   keyword rules of facebook/prefilter.py.
3. Classify the rest in batches with OpenRouter (facebook/llm.py), cached by text hash.
   Without OPENROUTER_API_KEY, the keyword rules decide alone and the price comes from a regex.
4. Yield kept posts as Listings (facebook/mapping.py). Geocoding is the usual --enrich step.

Group posts don't disappear in a way a crawl can see, so never use markUnseenInactive for
this source: the API's inactivity sweep retires them N days after they were first seen
(listings.inactivity.stale-after-by-source.facebook).

Keep activity low: a few runs a day, small caps, no parallelism. Volume per run is
roughly (new posts per group) x (groups) page scrolls, not page loads.
"""

import os
import random
import sys
import time
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from ..browser import USER_AGENTS, _proxy_config
from ..facebook import session
from ..facebook.extract import (
    FEED_ARTICLES_JS,
    SEE_MORE_JS,
    SEE_MORE_LABELS,
    SEE_MORE_SELECTOR,
    TIME_ATTR,
    TIMESTAMP_MARK_JS,
    TIMESTAMP_SELECTOR,
    Post,
    feed_url,
    parse_article,
    parse_groups,
)
from ..facebook.llm import Classifier, LlmStopped
from ..facebook.mapping import to_listing
from ..facebook.prefilter import prefilter, text_hash
from ..facebook.store import Store
from ..models import Listing
from ..polite import BlockBreaker, browser_status

log = sys.stderr


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


@dataclass
class Caps:
    """Per-group limits of one run (env defaults; maxPages of a run overrides max_scrolls and
    raises max_posts to match)."""

    max_posts: int = field(default_factory=lambda: _env_int("FACEBOOK_MAX_POSTS_PER_GROUP", 60))
    max_scrolls: int = field(default_factory=lambda: _env_int("FACEBOOK_MAX_SCROLLS", 25))
    # Pinned / "featured" posts come before the new ones, hence more than one.
    stop_after_seen: int = field(default_factory=lambda: _env_int("FACEBOOK_STOP_AFTER_SEEN", 3))
    max_age_days: int = field(default_factory=lambda: _env_int("FACEBOOK_MAX_AGE_DAYS", 14))


def _cache_path() -> Path:
    if path := os.getenv("FACEBOOK_CACHE"):
        return Path(path)
    return session.state_path().with_name("cache.json")


@contextmanager
def _browser(state: dict, user_agent: str | None, *, headless: bool):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            proxy=_proxy_config(),
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            storage_state=state,
            user_agent=user_agent or USER_AGENTS[0],
            locale="fr-CA",
            timezone_id="America/Toronto",
            viewport={"width": 1366, "height": 900},
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Videos autoplay in feeds: no need to download them.
        context.route("**/*", lambda route: route.abort() if route.request.resource_type == "media" else route.continue_())
        try:
            yield context
        finally:
            context.close()
            browser.close()


# --- collection -------------------------------------------------------------------


def _human_scroll(page) -> None:
    if random.random() < 0.3:
        page.mouse.move(random.randint(300, 1000), random.randint(200, 700), steps=random.randint(5, 15))
    for _ in range(random.randint(2, 4)):
        page.mouse.wheel(0, random.randint(220, 480))
        page.wait_for_timeout(random.randint(150, 600))
    # Mostly a few seconds of "reading", sometimes a longer stop.
    page.wait_for_timeout(int(1000 * (random.uniform(8, 16) if random.random() < 0.15 else random.uniform(2.5, 6))))


def _expand_see_more(page, feed: str, max_clicks: int = 6) -> None:
    try:
        if not page.evaluate(SEE_MORE_JS, sorted(SEE_MORE_LABELS)):
            return
        for handle in page.locator(SEE_MORE_SELECTOR).element_handles()[:max_clicks]:
            try:
                handle.scroll_into_view_if_needed(timeout=3000)
                handle.click(timeout=3000)
                handle.evaluate("e => e.removeAttribute('data-griffon-more')")
            except Exception:  # noqa: BLE001 -- detached or covered: the text stays truncated
                pass
            page.wait_for_timeout(random.randint(400, 1300))
            if "/groups/" not in page.url or "/posts/" in page.url or "/permalink/" in page.url:
                page.goto(feed, wait_until="domcontentloaded", timeout=45000)  # opened the post instead
                page.wait_for_timeout(random.randint(2000, 4000))
                return
    except Exception as e:  # noqa: BLE001
        print(f"[facebook] 'See more' expansion failed: {e!r}", file=log)


def _read_timestamps(page, max_hovers: int = 15) -> None:
    """Hovers the timestamp link of the undated posts on screen: the tooltip holds the full date
    ("Dimanche 8 novembre 2026 à 18:25") and is copied onto the post unit (TIME_ATTR)."""
    try:
        if not page.evaluate(TIMESTAMP_MARK_JS):
            return
        for handle in page.locator(TIMESTAMP_SELECTOR).element_handles()[:max_hovers]:
            try:
                handle.evaluate("e => e.removeAttribute('data-griffon-ts')")
                handle.scroll_into_view_if_needed(timeout=3000)
                handle.hover(timeout=3000)
                tip = page.wait_for_selector('[role="tooltip"]', timeout=2500)
                text = (tip.inner_text() or "").strip() if tip else ""
                if text:
                    handle.evaluate("(e, t) => e.closest('[aria-posinset]').setAttribute(%r, t)" % TIME_ATTR, text)
            except Exception:  # noqa: BLE001 -- no tooltip or detached: the post stays undated
                pass
            page.mouse.move(random.randint(5, 40), random.randint(300, 600))
            page.wait_for_timeout(random.randint(200, 600))
    except Exception as e:  # noqa: BLE001
        print(f"[facebook] reading post dates failed: {e!r}", file=log)


def collect_group(page, context, group: str, store: Store, breaker: BlockBreaker, *, now: datetime, caps: Caps) -> list[Post]:
    oldest = (now - timedelta(days=caps.max_age_days)).isoformat()

    url = feed_url(group)
    breaker.record(browser_status(page.goto(url, wait_until="domcontentloaded", timeout=45000)))
    page.wait_for_timeout(random.randint(3500, 7000))
    session.check_page(page.url, page.content()[:300_000], context.cookies())

    posts: dict[str, Post] = {}
    already_seen: set[str] = set()
    too_old: set[str] = set()
    reached: str | None = None  # oldest post date read so far
    for scroll in range(caps.max_scrolls):
        _expand_see_more(page, url)
        _read_timestamps(page)
        articles = page.evaluate(FEED_ARTICLES_JS)
        if scroll == 0 and not articles:
            body = (page.inner_text("body") or "")[:5000].lower()
            if any(k in body for k in ("rejoindre le groupe", "join group", "contenu n'est pas disponible",
                                       "content isn't available")):
                print(f"[facebook] {group}: not a member or group unavailable, skipped", file=log)
                return []
        for html in articles:
            post = parse_article(html, group=group, now=now)
            if post is None:
                continue
            if post.post_id in posts:
                if len(post.text) > len(posts[post.post_id].text):  # "See more" expanded since
                    posts[post.post_id] = post
                continue
            if post.published_at and post.published_at < oldest:
                too_old.add(post.post_id)
                continue
            if post.published_at:
                reached = min(reached or post.published_at, post.published_at)
            if store.seen(group, post.post_id):
                already_seen.add(post.post_id)
                continue
            posts[post.post_id] = post
        if len(already_seen) >= caps.stop_after_seen or len(too_old) >= 3 or len(posts) >= caps.max_posts:
            break
        _human_scroll(page)
        session.check_page(page.url, "", context.cookies())
    print(f"[facebook] {group}: {len(posts)} new posts ({scroll + 1} scrolls, "
          f"{len(already_seen)} already seen, {len(too_old)} too old, back to {reached or '?'})", file=log)
    return list(posts.values())[: caps.max_posts]


def collect(groups: list[str], store: Store, *, caps: Caps, headless: bool = True) -> list[tuple[str, Post]]:
    state, user_agent = session.load()
    user_agent = user_agent or USER_AGENTS[0]  # saved with the cookies: one fingerprint per session
    breaker = BlockBreaker("facebook", threshold=2)
    now = datetime.now(timezone.utc)
    out: list[tuple[str, Post]] = []
    with _browser(state, user_agent, headless=headless) as context:
        page = context.new_page()
        try:
            for i, group in enumerate(groups):
                if i:
                    time.sleep(random.uniform(20, 60))  # between groups, like switching tabs
                posts = collect_group(page, context, group, store, breaker, now=now, caps=caps)
                out.extend((group, post) for post in posts)
        finally:
            session.save(context, user_agent=user_agent)
    return out


# --- filtering, classification, mapping --------------------------------------------


def process(collected: list[tuple[str, Post]], store: Store, classifier: Classifier | None) -> Iterator[Listing]:
    stats: Counter = Counter(collected=len(collected))
    candidates: list[tuple[str, Post, str]] = []
    this_run: set[str] = set()
    for group, post in collected:
        if post.post_id in this_run or store.seen_anywhere(post.post_id):
            stats["shared"] += 1  # the same post shared into another group
            store.mark_seen(group, post.post_id)
            continue
        this_run.add(post.post_id)
        h = text_hash(post.text)
        owner = store.hash_owner(h)
        if owner and owner != post.post_id:
            stats["repost"] += 1
            store.mark_seen(group, post.post_id)
            continue
        store.remember_hash(h, post.post_id)
        verdict = prefilter(post.text)
        if not verdict:
            stats[f"rules:{verdict.reason}"] += 1
            store.mark_seen(group, post.post_id)
            continue
        candidates.append((group, post, h))

    failed: set[str] = set()
    if classifier:
        todo = list({h: post.text for _, post, h in candidates if store.classification(h) is None}.items())
        if todo:
            try:
                classifier.classify([text for _, text in todo])
            except LlmStopped as e:
                print(f"[facebook] LLM stopped: {e}; unclassified posts are left for the next run", file=log)
            for i, (h, _) in enumerate(todo):
                if i in classifier.results:
                    if (result := classifier.results[i]) is None:
                        failed.add(h)
                    else:
                        store.remember_classification(h, {**result, "_model": classifier.model})
        print(f"[facebook] LLM: {classifier.usage_line()}", file=log)

    for group, post, h in candidates:
        classification = store.classification(h) if classifier else None
        if classifier and classification is None and h not in failed:
            stats["deferred"] += 1  # budget spent or API down: retried next run (not marked seen)
            continue
        store.mark_seen(group, post.post_id)
        if classification is not None and not classification.get("keep"):
            stats[f"llm:{classification.get('kind')}"] += 1
            continue
        stats["kept"] += 1
        yield to_listing(post, classification, group=group)
    print(f"[facebook] {dict(stats)}", file=log)


def scrape(
    *,
    groups: list[str] | None = None,
    headless: bool = True,
    max_scrolls: int | None = None,
) -> Iterator[Listing]:
    keys = parse_groups(",".join(groups)) if groups else parse_groups(os.getenv("FACEBOOK_GROUPS"))
    if not keys:
        raise ValueError("facebook: no group configured (FACEBOOK_GROUPS)")
    caps = Caps()
    if max_scrolls:
        # A run asking for more scrolls (maxPages, e.g. a catch-up) is not cut by the posts cap.
        # It also digs past the posts seen by earlier runs, down to max_age_days.
        caps.max_scrolls = max_scrolls
        caps.max_posts = max(caps.max_posts, 3 * max_scrolls)
        caps.stop_after_seen = 10**9
    store = Store(_cache_path())
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("[facebook] warning: OPENROUTER_API_KEY not set, keeping posts on keyword rules alone", file=log)
    try:
        collected = collect(keys, store, caps=caps, headless=headless)
        store.save()
        # A catch-up classifies many more posts: ~1000 tokens per scroll (about $0.15 for 600).
        budget = max(150_000, 1000 * max_scrolls) if max_scrolls else None
        classifier = Classifier(api_key, token_budget=budget) if api_key else None
        try:
            yield from process(collected, store, classifier)
        finally:
            if classifier:
                classifier.close()
    finally:
        store.save()
