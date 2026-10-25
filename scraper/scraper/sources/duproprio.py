"""DuProprio rental scraper.

No browser needed -- plain HTTP works throughout:

1. The search results HTML (/en/rental/search/list?...&pageNumber=N) is
   server-rendered and deterministic; listing URLs are pulled out with a
   regex over the raw HTML (confirmed stable across repeated fetches).
   NOTE: an `/api-proxy/featured-homes` XHR looked tempting at first (clean
   JSON) but it turned out to be a "featured/recommended" widget that
   returns a rotating, non-deterministic sample -- not real pagination.
   Don't reuse it for enumeration.
2. Each listing detail page embeds full structured data as schema.org
   `Apartment` + `RealEstateListing` JSON-LD blocks (address, beds, baths,
   price, photo, amenities) -- no HTML-scraping needed for the fields.
"""

import html
import json
import re
import time
from collections.abc import Iterator

import httpx

from ..models import Listing
from ..polite import PoliteClient

BASE_URL = "https://duproprio.com"
SEARCH_URL = f"{BASE_URL}/en/rental/search/list"
LISTING_URL_RE = re.compile(r'href="(https://duproprio\.com/en/rental/[^"]*?hab-[a-z0-9\-]+-(\d{6,}))"')
LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
}

# DuProprio doesn't expose square footage as structured data on rentals (it's an
# optional field landlords often skip) -- best-effort pull it out of the free-text
# description when they did mention it, e.g. "...of approximately 1500 sqft built...".
_AREA_RE = re.compile(r"(\d{2,5}(?:[.,]\d+)?)\s*(?:sq\.?\s?ft\.?|sqft|square feet|pi\s?2|pi²)", re.I)


def _parse_area_sqft(description: str | None) -> float | None:
    if not description:
        return None
    if m := _AREA_RE.search(description):
        return float(m.group(1).replace(",", ""))
    return None


_UTILITY_KEYWORDS = ("heat", "water", "electric", "hydro")


def _split_amenities(amenity_feature: list[dict]) -> tuple[list[str], list[str]]:
    """Splits the flat amenityFeature list into (amenities, utilities_included)."""
    amenities, utilities = [], []
    for feat in amenity_feature:
        name = feat.get("name")
        if not name:
            continue
        (utilities if any(k in name.lower() for k in _UTILITY_KEYWORDS) else amenities).append(name)
    return amenities, utilities


def _discover_urls(client: httpx.Client, page_number: int) -> list[tuple[str, str]]:
    """Returns [(external_id, absolute_url), ...] for one search results page."""
    resp = client.get(
        SEARCH_URL,
        params={"search": "true", "parent": 1, "pageNumber": page_number, "sort": "-published_at"},
    )
    resp.raise_for_status()
    seen_on_page: dict[str, str] = {}
    for url, ext_id in LISTING_URL_RE.findall(resp.text):
        seen_on_page[ext_id] = url
    return list(seen_on_page.items())


PHOTO_HOST = "https://photos.duproprio.com/"


def _gallery(page: str, external_id: str) -> list[str]:
    """Every photo of the listing, at 1600 px, in upload order.

    The JSON-LD names a single image; the page's own photo data has the whole gallery.
    Photos of the other listings the page recommends are left out: a listing's photos
    sit under its own id in the path.
    """
    page = page.replace("\\/", "/")
    pattern = re.compile(r"photos/public/for_rent/\d+/" + re.escape(external_id) + r"/[^\"'\s]*?-1600-(\d+)\.jpg")
    found = {m.group(1): m.group(0) for m in pattern.finditer(page)}
    return [PHOTO_HOST + found[k] for k in sorted(found, key=int)]


def _primary_first(gallery: list[str], primary: str | None) -> list[str]:
    """The cover photo the listing chose (the JSON-LD image) leads the gallery."""
    if not primary:
        return gallery
    if primary in gallery:
        return [primary, *(p for p in gallery if p != primary)]
    return [primary, *gallery] if not gallery else gallery


def _fetch_detail(client: httpx.Client, url: str, external_id: str) -> dict | None:
    resp = client.get(url)
    resp.raise_for_status()
    apartment, real_estate = None, None
    for block in LD_JSON_RE.findall(resp.text):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if data.get("@type") == "Apartment":
            apartment = data
        elif data.get("@type") == "RealEstateListing":
            real_estate = data
    if not apartment:
        return None
    return {"apartment": apartment, "real_estate": real_estate, "photos": _gallery(resp.text, external_id)}


def _to_listing(external_id: str, url: str, detail: dict) -> Listing:
    a = detail["apartment"]
    offer = (detail.get("real_estate") or {}).get("offers", {})
    addr = a.get("address", {})

    def _num(key: str) -> float | None:
        val = a.get(key)
        try:
            return float(val) if val is not None else None
        except ValueError:
            return None

    def _unescape(s: str | None) -> str | None:
        return html.unescape(s) if s else s

    price = offer.get("price")
    description = _unescape(a.get("description"))
    amenities, utilities = _split_amenities(a.get("amenityFeature", []))
    return Listing(
        source="duproprio",
        external_id=external_id,
        url=url,
        title=_unescape(a.get("name")),
        listing_type="rent",
        price=float(price) if price else None,
        price_period="monthly",
        # Owners can hide the civic number, which DuProprio renders as ". 36e avenue Ouest".
        address=(_unescape(addr.get("streetAddress")) or "").lstrip(". ") or None,
        city=_unescape(addr.get("addressLocality")),
        region=addr.get("addressRegion"),
        postal_code=addr.get("postalCode"),
        bedrooms=_num("numberOfBedrooms"),
        bathrooms=_num("numberOfFullBathrooms"),
        rooms_qc=_num("numberOfRooms"),
        area_sqft=_parse_area_sqft(description),
        amenities=amenities,
        utilities_included=utilities,
        photos=_primary_first(detail.get("photos") or [], a.get("image")),
        description=description,
    )


def scrape(*, max_pages: int = 350, stale_page_limit: int = 5, delay_s: float = 0.5) -> Iterator[Listing]:
    seen_ids: set[str] = set()
    stale_pages = 0

    with PoliteClient(headers=HEADERS, timeout=20, follow_redirects=True, source="duproprio") as client:
        for page_number in range(1, max_pages + 1):
            pairs = _discover_urls(client, page_number)
            new_pairs = [(eid, url) for eid, url in pairs if eid not in seen_ids]

            if not pairs:
                break
            stale_pages = stale_pages + 1 if not new_pairs else 0
            if stale_pages >= stale_page_limit:
                break

            for external_id, url in new_pairs:
                seen_ids.add(external_id)
                try:
                    detail = _fetch_detail(client, url, external_id)
                    if detail:
                        yield _to_listing(external_id, url, detail)
                except Exception:
                    continue
                time.sleep(delay_s)
