import os
import time

import httpx

# Public instances, tried in order. Override with OVERPASS_URL (comma-separated) to
# point at your own instance for heavy use -- the public ones are rate limited.
DEFAULT_ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

def user_agent() -> str:
    """OSM services ask for an identifying User-Agent, ideally with a contact."""
    contact = os.getenv("GEOCODER_EMAIL")
    return f"qc-rental-scraper/0.1 ({contact})" if contact else "qc-rental-scraper/0.1"


def endpoints() -> list[str]:
    if env := os.getenv("OVERPASS_URL"):
        return [u.strip() for u in env.split(",") if u.strip()]
    return DEFAULT_ENDPOINTS


def query(ql: str, *, timeout_s: float = 90, retries: int = 1) -> dict:
    """Runs an Overpass QL query, falling back across endpoints on 429/5xx/timeouts."""
    last_error: Exception | None = None
    for attempt in range(retries + 1):
        for url in endpoints():
            try:
                resp = httpx.post(url, data={"data": ql}, timeout=timeout_s, headers={"User-Agent": user_agent()})
                if resp.status_code == 200:
                    return resp.json()
                last_error = httpx.HTTPStatusError(f"{resp.status_code} from {url}", request=resp.request, response=resp)
            except (httpx.HTTPError, ValueError) as e:
                last_error = e
        time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"Overpass query failed on every endpoint: {last_error}")
