"""DuProprio scraper: rentals (`scrape`) and properties for sale (`scrape_sale`, at the end).

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
import os
import re
import time
from collections.abc import Iterator

import httpx
from selectolax.parser import HTMLParser

from ..models import Listing
from ..normalize import parse_number
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


def _gallery(page: str, external_id: str, kind: str = "for_rent") -> list[str]:
    """Every photo of the listing, at 1600 px, in upload order.

    The JSON-LD names a single image; the page's own photo data has the whole gallery.
    Photos of the other listings the page recommends are left out: a listing's photos
    sit under its own id in the path. `kind` is "for_rent" or "for_sale".
    """
    page = page.replace("\\/", "/")
    pattern = re.compile(rf"photos/public/{kind}/\d+/" + re.escape(external_id) + r"/[^\"'\s]*?-1600-(\d+)\.jpg")
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


# --- Properties for sale ------------------------------------------------------------------
#
# /en/search/list?is_for_sale=1 lists every property for sale in Quebec, 12 per page, newest
# first. A sale page differs from a rental one: its JSON-LD is a `Product` (price) plus a
# `SingleFamilyResidence` (address and coordinates, whatever the type -- condos included),
# with whitespace-padded values and raw newlines (hence strict=False). Everything else is
# HTML: main characteristics (bedrooms, bathrooms, living area, lot), the "Property
# features" rows (year built, municipal assessment, parking) and the yearly / monthly costs
# table (taxes, condo fees). Sale and rental ids share one sequence, so they never collide.

SALE_SEARCH_URL = f"{BASE_URL}/en/search/list"
SALE_URL_RE = re.compile(r'href="(https://duproprio\.com/en/[^"]*?/([a-z0-9-]+)-for-sale/hab-[a-z0-9\-]+-(\d{6,}))"')
# The URL's type slug, where it says more than the generic vocabulary would guess. In
# Quebec English a "cottage" is a two-storey house, not a chalet.
_SALE_TYPES = {"home": "house", "cottage": "house", "intergenerational": "house", "split-level": "house",
               "semi-detached": "house", "detached": "house", "mobile-home": "house"}
_NOT_HOMES = {"land", "lot", "farm", "hobby-farm", "commercial", "industrial", "business", "woodlot"}
_SQFT_PER_M2 = 10.7639


def _strip(value):
    return value.strip() if isinstance(value, str) else value


def _ld_blocks(page: str) -> dict[str, dict]:
    blocks: dict[str, dict] = {}
    for raw in LD_JSON_RE.findall(page):
        try:
            data = json.loads(raw, strict=False)
        except ValueError:
            continue  # e.g. a breadcrumb with an unrendered "{{$key+1}}" template
        if isinstance(data, dict) and data.get("@type"):
            blocks.setdefault(data["@type"], data)
    return blocks


def _clean(node) -> str | None:
    if node is None:
        return None
    return re.sub(r"\s+", " ", node.text(separator=" ")).strip() or None


def _surface_sqft(text: str | None) -> float | None:
    """'1 056 ft² (98.11 m²)' -> 1056.0; '650 m²' -> 6996.5."""
    if not text:
        return None
    if m := re.search(r"([\d\s  ,.]+)\s*ft", text):
        return parse_number(m.group(1))
    if m := re.search(r"([\d\s  ,.]+)\s*m", text):
        n = parse_number(m.group(1))
        return round(n * _SQFT_PER_M2, 1) if n is not None else None
    return None


def _money(text: str | None) -> float | None:
    """'$2,200.00' -> 2200.0, '$470,000' -> 470000.0 (English formatting)."""
    if not text or not (m := re.search(r"\d[\d,]*(?:\.\d+)?", text)):
        return None
    return float(m.group(0).replace(",", ""))


def _parse_sale_page(page: str, url: str, external_id: str, type_slug: str | None) -> Listing | None:
    ld = _ld_blocks(page)
    home, product = ld.get("SingleFamilyResidence"), ld.get("Product")
    if not home and not product:
        return None
    home, product = home or {}, product or {}
    addr = {k: _strip(v) for k, v in (home.get("address") or {}).items()}
    geo = home.get("geo") or {}
    tree = HTMLParser(page)

    # Main characteristics: "2 | bedrooms", "1 | bathroom", "Lot dimensions | 7 000 ft² (650.32 m²)".
    bedrooms = bathrooms = area = lot = None
    levels = None
    for item in tree.css(".listing-main-characteristics__item"):
        title = (_clean(item.css_first(".listing-main-characteristics__title")) or "").lower()
        number = _clean(item.css_first(".listing-main-characteristics__number"))
        classes = item.attributes.get("class") or ""
        if "living-space-area" in classes:
            area = _surface_sqft(number)
        elif "lot-dimensions" in classes:
            lot = _surface_sqft(number)
        elif number and number.replace(".", "").isdigit():
            n = float(number)
            if "half" in title or "powder" in title:
                bathrooms = (bathrooms or 0) + 0.5 * n
            elif "bathroom" in title:
                bathrooms = (bathrooms or 0) + n
            elif "bedroom" in title:
                bedrooms = n
            elif "level" in title:
                levels = n

    rows: dict[str, str] = {}
    for row in tree.css(".listing-box__dotted-row"):
        cells = [c for c in (_clean(div) for div in row.iter() if div.tag == "div") if c]
        if len(cells) >= 2:
            rows.setdefault(cells[0], cells[-1])
    parking = None
    for key in ("Number of interior parking", "Number of exterior parking"):
        if (n := _money(rows.get(key))) is not None:
            parking = int((parking or 0) + n)

    # "Summary of Expenditures | Monthly | Annual" rows.
    taxes, school, condo_fees, expenses = None, None, None, {}
    for row in tree.css(".mortgage-data__table--costs .mortgage-data__table__row"):
        name = _clean(row.css_first(".mortgage-data__table__row__item--name"))
        monthly = _money(_clean(row.css_first(".mortgage-data__table__row__item--monthly-costs")))
        yearly = _money(_clean(row.css_first(".mortgage-data__table__row__item--yearly-costs")))
        if not name:
            continue
        low = name.lower()
        if low.startswith(("property tax", "municipal tax")):
            taxes = yearly
        elif low.startswith("school tax"):
            school = yearly
        elif "condo fee" in low or "co-ownership" in low:
            condo_fees = monthly if monthly is not None else (round(yearly / 12, 2) if yearly else None)
        elif yearly is not None:
            expenses[name] = yearly

    description_node = tree.css_first(".js-listing-owners-comments-description-original") or tree.css_first(
        ".listing-owners-comments__description"
    )
    description = description_node.text(separator="\n").strip() if description_node is not None else None
    description = re.sub(r"\n\s*\n+", "\n\n", description) if description else None

    year = _money(rows.get("Year of construction"))
    units = _money(rows.get("Number of units") or rows.get("Number of dwellings"))
    lat, lng = _strip(geo.get("latitude")), _strip(geo.get("longitude"))
    try:
        lat, lng = (float(lat), float(lng)) if lat and lng else (None, None)
    except ValueError:
        lat, lng = None, None
    price = _money(_strip((product.get("offers") or {}).get("price")))
    raw_type = _SALE_TYPES.get(type_slug or "", type_slug)

    extra = {
        "ownership": rows.get("Ownership"),
        "property_style": rows.get("Property Style"),
        "floor": rows.get("Located on which floor?"),
        "levels": levels,
        "building_dimensions": rows.get("Building dimensions"),
        "expenses_yearly": expenses or None,
        "type_slug": type_slug,
    }
    image = _strip(home.get("image") or product.get("image"))
    return Listing(
        source="duproprio",
        external_id=external_id,
        url=url,
        title=html.unescape(_strip(home.get("name") or product.get("name")) or "") or None,
        listing_type="sale",
        property_type=raw_type,
        price=price or None,
        price_period="total",
        address=(html.unescape(addr.get("streetAddress") or "")).lstrip(". ") or None,
        city=html.unescape(addr["addressLocality"]) if addr.get("addressLocality") else None,
        region=addr.get("addressRegion"),
        postal_code=addr.get("postalCode"),
        latitude=lat,
        longitude=lng,
        location_precision="exact" if lat is not None else None,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        area_sqft=area,
        lot_area_sqft=lot,
        year_built=int(year) if year else None,
        parking_spots=parking,
        municipal_assessment=_money(rows.get("Municipal Assessment")),
        municipal_taxes_yearly=taxes,
        school_taxes_yearly=school,
        condo_fees_monthly=condo_fees,
        units=int(units) if units else None,
        photos=_primary_first(_gallery(page, external_id, "for_sale"), image),
        description=description,
        extra={k: v for k, v in extra.items() if v is not None},
    )


def _discover_sale_urls(client: httpx.Client, page_number: int) -> list[tuple[str, str, str]]:
    """[(external_id, url, type slug), ...] for one page of properties for sale."""
    resp = client.get(
        SALE_SEARCH_URL,
        params={"search": "true", "is_for_sale": 1, "parent": 1, "pageNumber": page_number, "sort": "-published_at"},
    )
    resp.raise_for_status()
    found: dict[str, tuple[str, str]] = {}
    for url, type_slug, ext_id in SALE_URL_RE.findall(resp.text):
        found.setdefault(ext_id, (url, type_slug))
    return [(eid, url, slug) for eid, (url, slug) in found.items()]


def scrape_sale(
    *, max_pages: int = 1000, stale_page_limit: int = 5, delay_s: float = 0.5, max_requests: int | None = None
) -> Iterator[Listing]:
    """Yields DuProprio properties for sale (houses, condos, plexes), newest first."""
    if max_requests is None:
        max_requests = int(os.getenv("SCRAPER_SALE_MAX_REQUESTS", 20000))
    seen_ids: set[str] = set()
    stale_pages = 0
    with PoliteClient(
        headers=HEADERS, timeout=20, follow_redirects=True, source="duproprio_sale", max_requests=max_requests
    ) as client:
        for page_number in range(1, max_pages + 1):
            rows = _discover_sale_urls(client, page_number)
            if not rows:
                break
            fresh = [r for r in rows if r[0] not in seen_ids]
            stale_pages = stale_pages + 1 if not fresh else 0
            if stale_pages >= stale_page_limit:
                break
            for external_id, url, type_slug in fresh:
                seen_ids.add(external_id)
                if type_slug in _NOT_HOMES:
                    continue
                try:
                    resp = client.get(url)
                    resp.raise_for_status()
                    listing = _parse_sale_page(resp.text, url, external_id, type_slug)
                    if listing:
                        yield listing
                except Exception:  # noqa: BLE001 -- one odd page must not stop the crawl
                    continue
                time.sleep(delay_s)
