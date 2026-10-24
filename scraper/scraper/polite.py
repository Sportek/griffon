"""Rate limiting and block detection shared by every source, so a scrape never hammers a site.

- PoliteClient (drop-in httpx.Client): a randomized minimum gap between requests,
  Retry-After / exponential backoff on 429 and 5xx, a per-run request budget, and a
  circuit breaker that aborts the source after a few consecutive 403/429.
- SourceBlocked derives from BaseException on purpose: sources wrap detail fetches in
  `except Exception: pass`, and a block must not be swallowed there -- it has to stop
  the source (and mark its ingestion run FAILED) instead of retrying at full speed.

Tunable with environment variables (defaults are deliberately gentle):
    SCRAPER_MIN_DELAY=2.0   SCRAPER_MAX_DELAY=5.0   seconds between two requests
    SCRAPER_MAX_REQUESTS=6000                         per source run, 0 = unlimited
    SCRAPER_BLOCK_THRESHOLD=3                         consecutive 403/429 before giving up
"""

import os
import random
import sys
import time

import httpx

RETRYABLE = {429, 500, 502, 503, 504}
BLOCKING = {403, 429}


class SourceBlocked(BaseException):
    """The site is refusing us (or the request budget is spent): stop this source now."""


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


class PoliteClient(httpx.Client):
    def __init__(
        self,
        *args,
        source: str,
        min_delay: float | None = None,
        max_delay: float | None = None,
        max_requests: int | None = None,
        max_retries: int = 3,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.source = source
        self.min_delay = _env_float("SCRAPER_MIN_DELAY", 2.0) if min_delay is None else min_delay
        self.max_delay = _env_float("SCRAPER_MAX_DELAY", 5.0) if max_delay is None else max_delay
        self.max_requests = int(_env_float("SCRAPER_MAX_REQUESTS", 6000)) if max_requests is None else max_requests
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
            response = super().send(request, **kwargs)
            if response.status_code not in RETRYABLE or attempt == self.max_retries:
                break
            pause = _retry_after(response) or min(30 * 2**attempt, 600)
            print(f"[{self.source}] HTTP {response.status_code}, pausing {pause:.0f}s", file=sys.stderr)
            response.close()
            time.sleep(pause)
        self.breaker.record(response.status_code)
        return response


def _retry_after(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After")
    try:
        return min(float(value), 900) if value else None
    except ValueError:
        return None
