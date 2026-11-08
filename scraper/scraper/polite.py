"""Rate limiting and block detection shared by every source, so a scrape never hammers a site.

- PoliteClient (drop-in httpx.Client): a randomized minimum gap between requests,
  Retry-After / exponential backoff on 429, 5xx and network errors (timeouts, resets),
  a per-run request budget, and a circuit breaker that aborts the source after a few
  consecutive 403/429 -- or at once on a Cloudflare challenge, which plain HTTP never passes.
- SourceBlocked derives from BaseException on purpose: sources wrap detail fetches in
  `except Exception`, and a block must not be swallowed there -- it has to stop
  the source (and mark its ingestion run FAILED) instead of retrying at full speed.
- CrawlHealth counts the pages a source failed to fetch or parse and logs each failure.
  At the end of the crawl it raises IncompleteCrawl if too much was lost: the run still
  succeeds, but its unseen listings are not marked inactive (they were likely just missed).

Tunable with environment variables (defaults are deliberately gentle):
    SCRAPER_MIN_DELAY=2.0   SCRAPER_MAX_DELAY=5.0   seconds between two requests
    SCRAPER_MAX_REQUESTS=6000                         per source run, 0 = unlimited
    SCRAPER_MAX_REQUESTS_<SOURCE>=...                 per-source override (e.g. ..._LOGIS_QUEBEC)
    SCRAPER_BLOCK_THRESHOLD=3                         consecutive 403/429 before giving up
    SCRAPER_MAX_FAILURE_RATIO=0.02                    share of lost pages (per kind) that makes
                                                      a crawl incomplete: no deactivation
"""

import os
import random
import sys
import time

import httpx

# Live progress of the sources running in this process, read by the worker's progress log.
# Per source: "requests" (counted by PoliteClient) and, when the source knows them,
# "done"/"total" items (set with report_progress). Plain ints: safe to read from another thread.
PROGRESS: dict[str, dict[str, int]] = {}


def report_progress(source: str, done: int, total: int) -> None:
    entry = PROGRESS.setdefault(source, {})
    entry["done"], entry["total"] = done, total


RETRYABLE = {429, 500, 502, 503, 504}
BLOCKING = {403, 429}


class SourceBlocked(BaseException):
    """The site is refusing us (or the request budget is spent): stop this source now."""


class IncompleteCrawl(Exception):
    """Raised by a source after it yielded everything it could, when it lost too many pages
    for "not seen in this run" to mean "gone": the run ends without markUnseenInactive."""


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, default))
    except ValueError:
        return default


def jitter_sleep(min_s: float | None = None, max_s: float | None = None) -> None:
    """A human-ish pause; defaults to SCRAPER_MIN_DELAY..SCRAPER_MAX_DELAY."""
    lo = _env_float("SCRAPER_MIN_DELAY", 2.0) if min_s is None else min_s
    hi = _env_float("SCRAPER_MAX_DELAY", 5.0) if max_s is None else max_s
    time.sleep(random.uniform(lo, max(lo, hi)))


class BlockBreaker:
    """Counts consecutive blocking responses; trips after `threshold` in a row."""

    def __init__(self, source: str, threshold: int | None = None):
        self.source = source
        self.threshold = threshold or int(_env_float("SCRAPER_BLOCK_THRESHOLD", 3))
        self.consecutive = 0

    def record(self, status: int | None) -> None:
        if status in BLOCKING:
            self.consecutive += 1
            print(f"[{self.source}] HTTP {status} ({self.consecutive}/{self.threshold})", file=sys.stderr)
            if self.consecutive >= self.threshold:
                raise SourceBlocked(f"{self.source}: {self.consecutive} consecutive HTTP {status}, stopping to avoid a ban")
        elif status is not None and status < 400:
            self.consecutive = 0


def browser_status(response) -> int | None:
    """Status to feed a BlockBreaker from a Playwright navigation. Only 429 counts as a
    block: behind Cloudflare the first response is a 403 challenge that the real browser
    then solves, so a 403 there is not a refusal."""
    if response is None:
        return None
    return response.status if response.status == 429 or response.status < 400 else None


def is_cloudflare_challenge(response: httpx.Response) -> bool:
    """Cloudflare's "Just a moment..." / Turnstile page: only a real (often human) browser passes it."""
    return response.headers.get("cf-mitigated") == "challenge"


def request_budget(source: str, default: int | None = None) -> int:
    """SCRAPER_MAX_REQUESTS_<SOURCE>, else the source's own default, else SCRAPER_MAX_REQUESTS."""
    name = f"SCRAPER_MAX_REQUESTS_{source.upper()}"
    if os.getenv(name):
        return int(_env_float(name, 0))
    if default is not None:
        return default
    return int(_env_float("SCRAPER_MAX_REQUESTS", 6000))


class PoliteClient(httpx.Client):
    def __init__(
        self,
        *args,
        source: str,
        min_delay: float | None = None,
        max_delay: float | None = None,
        max_requests: int | None = None,
        default_max_requests: int | None = None,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.source = source
        self.min_delay = _env_float("SCRAPER_MIN_DELAY", 2.0) if min_delay is None else min_delay
        self.max_delay = _env_float("SCRAPER_MAX_DELAY", 5.0) if max_delay is None else max_delay
        # default_max_requests: what a full crawl of this source needs, when that is more
        # than the global SCRAPER_MAX_REQUESTS (a per-source env variable still wins).
        self.max_requests = request_budget(source, default_max_requests) if max_requests is None else max_requests
        self.max_retries = max_retries
        self.requests_sent = 0
        self.breaker = BlockBreaker(source)
        self._next_allowed = 0.0

    def _wait_turn(self) -> None:
        now = time.monotonic()
        if now < self._next_allowed:
            time.sleep(self._next_allowed - now)
        self._next_allowed = time.monotonic() + random.uniform(self.min_delay, max(self.min_delay, self.max_delay))

    def send(self, request: httpx.Request, **kwargs) -> httpx.Response:
        for attempt in range(self.max_retries + 1):
            if self.max_requests and self.requests_sent >= self.max_requests:
                raise SourceBlocked(f"{self.source}: request budget of {self.max_requests} spent")
            self._wait_turn()
            self.requests_sent += 1
            entry = PROGRESS.setdefault(self.source, {})
            entry["requests"] = entry.get("requests", 0) + 1
            try:
                response = super().send(request, **kwargs)
            except httpx.TransportError as e:  # timeout, reset, DNS: usually gone a minute later
                if attempt == self.max_retries:
                    print(f"[{self.source}] {e!r} on {request.url}, giving up after {attempt + 1} tries", file=sys.stderr)
                    raise
                pause = min(15 * 2**attempt, 300)
                print(f"[{self.source}] {e!r} on {request.url}, retrying in {pause:.0f}s", file=sys.stderr)
                time.sleep(pause)
                continue
            if is_cloudflare_challenge(response):
                response.close()
                raise SourceBlocked(
                    f"{self.source}: Cloudflare challenge (HTTP {response.status_code}, cf-mitigated: challenge) "
                    f"on {request.url}: the site now requires a browser check, stopping"
                )
            if response.status_code not in RETRYABLE or attempt == self.max_retries:
                break
            pause = _retry_after(response) or min(30 * 2**attempt, 600)
            print(f"[{self.source}] HTTP {response.status_code}, pausing {pause:.0f}s", file=sys.stderr)
            response.close()
            time.sleep(pause)
        self.breaker.record(response.status_code)
        return response


class CrawlHealth:
    """Counts what a crawl fetched and lost, so a partial crawl cannot pass for a full one.

        health = CrawlHealth("centris")
        health.ok("search page")                  # one per page fetched and parsed
        health.failed("detail", url, exc)         # logged with running counts
        health.gap("laval: given up at page 7")   # a whole part of the site skipped
        health.finish()                           # last line of scrape(): may raise IncompleteCrawl
    """

    def __init__(self, source: str, max_failure_ratio: float | None = None):
        self.source = source
        self.max_failure_ratio = (
            _env_float("SCRAPER_MAX_FAILURE_RATIO", 0.02) if max_failure_ratio is None else max_failure_ratio
        )
        self.attempted: dict[str, int] = {}
        self.lost: dict[str, int] = {}
        self.gaps: list[str] = []

    def ok(self, kind: str) -> None:
        self.attempted[kind] = self.attempted.get(kind, 0) + 1

    def failed(self, kind: str, what: str, error: BaseException | str) -> None:
        self.ok(kind)
        self.lost[kind] = self.lost.get(kind, 0) + 1
        if isinstance(error, str):
            reason = error
        else:  # first line only: Playwright errors carry a long call log
            reason = f"{type(error).__name__}: {(str(error).splitlines() or [''])[0]}"
        print(
            f"[{self.source}] {kind} failed ({self.lost[kind]}/{self.attempted[kind]} so far): {what}: {reason}",
            file=sys.stderr,
        )

    def gap(self, reason: str) -> None:
        """Part of the site was not crawled at all: the crawl is incomplete whatever the ratios."""
        self.gaps.append(reason)
        print(f"[{self.source}] {reason}", file=sys.stderr)

    def summary(self) -> str:
        parts = [f"{kind}s {n - self.lost.get(kind, 0)}/{n} ok" for kind, n in self.attempted.items()]
        return ", ".join(parts + self.gaps) or "nothing crawled"

    def problems(self) -> list[str]:
        out = list(self.gaps)
        for kind, lost in self.lost.items():
            if lost / self.attempted[kind] > self.max_failure_ratio:
                out.append(f"{lost}/{self.attempted[kind]} {kind}s lost")
        return out

    def finish(self) -> None:
        print(f"[{self.source}] crawl: {self.summary()}", file=sys.stderr)
        if problems := self.problems():
            detail = "; ".join(problems)
            raise IncompleteCrawl(f"{self.source}: {detail} (tolerated: {self.max_failure_ratio:.0%} per kind)")


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return min(float(value), 900) if value else None
    except ValueError:
        return None
