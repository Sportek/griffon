import os
import random
import time
from contextlib import contextmanager

from playwright.sync_api import sync_playwright

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
]


def _proxy_config() -> dict | None:
    """Reads PROXY_SERVER (e.g. socks5://127.0.0.1:9050 for ProtonVPN's SOCKS proxy).

    Leave unset if the machine is already tunneled system-wide through the
    ProtonVPN app -- Playwright will use the OS network stack transparently.
    """
    server = os.getenv("PROXY_SERVER")
    if not server:
        return None
    proxy = {"server": server}
    if user := os.getenv("PROXY_USERNAME"):
        proxy["username"] = user
    if pwd := os.getenv("PROXY_PASSWORD"):
        proxy["password"] = pwd
    return proxy


@contextmanager
def new_context(*, headless: bool = True, locale: str = "fr-CA"):
    """Launches a Chromium context with light stealth tweaks and optional proxy."""
    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=headless,
            proxy=_proxy_config(),
            args=["--disable-blink-features=AutomationControlled"],
        )
        context = browser.new_context(
            user_agent=random.choice(USER_AGENTS),
            locale=locale,
            timezone_id="America/Toronto",
            viewport={"width": 1440, "height": 900},
        )
        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        try:
            yield context
        finally:
            context.close()
            browser.close()


def polite_delay(min_s: float | None = None, max_s: float | None = None) -> None:
    """Pause between page loads: SCRAPER_BROWSER_MIN_DELAY..SCRAPER_BROWSER_MAX_DELAY (3-7 s)."""
    lo = float(os.getenv("SCRAPER_BROWSER_MIN_DELAY", 3.0)) if min_s is None else min_s
    hi = float(os.getenv("SCRAPER_BROWSER_MAX_DELAY", 7.0)) if max_s is None else max_s
    time.sleep(random.uniform(lo, max(lo, hi)))
