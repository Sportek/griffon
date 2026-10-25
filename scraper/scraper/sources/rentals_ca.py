"""rentals.ca scraper.

rentals.ca sits behind a Cloudflare JS challenge (plain HTTP requests get a
403 'challenge' response), but a real Playwright-driven Chromium passes it
and the listing content is server-rendered underneath. Each search result is
a *building*; the detail page lists individual units (floor plans) with
their own price/beds/baths/size in a "Floor Plans" table.
"""

import re
from collections.abc import Iterator

from ..browser import new_context, polite_delay
from ..models import Listing
from ..normalize import iso_date
from ..polite import BlockBreaker, browser_status

BASE = "https://rentals.ca"
DEFAULT_CITIES = [
    "montreal",
    "quebec-city",
    "gatineau",
    "laval",
    "longueuil",
    "sherbrooke",
    "trois-rivieres",
]

# e.g. "1 Bedroom 1 1 560.0 ft² $1,582" -> (label=1, beds=1, baths=1, size=560.0, price=1582)
_UNIT_ROW_RE = re.compile(r"(\d+)\s*Bedroom\s+(\d+)\s+(\d+)\s+([\d.]+)\s*ft\S*\s*\$([\d,]+)")
_LATLNG_RE = re.compile(r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?.*?"longitude"\s*:\s*"?(-?\d+\.\d+)"?', re.S)


def _collect_building_links(page) -> list[tuple[str, str, str]]:
    """Returns (property_id, absolute_url, title) for every card on the current search page."""
    out = []
    cards = page.locator(".listing-card-container")
    for i in range(cards.count()):
        card = cards.nth(i)
        prop_id = card.get_attribute("data-property-id")
        link = card.locator(f"a[href^='{BASE}/']").first
        if link.count() == 0 or not prop_id:
            continue
        href = (link.get_attribute("href") or "").split("#")[0]
        title_el = card.locator("[class*='title']").first
        title = title_el.inner_text().strip() if title_el.count() else ""
        out.append((prop_id, href, title))
    return out


def _parse_unit_row(label: str, cells: list[str]) -> dict | None:
    """One floor-plan <li>: label 'Studio' / '1.5 Bedroom', then cells like '$1,450', '1 Bath', '567 ft²', 'Available'."""
    unit: dict = {
        "bedrooms": None,
        "bathrooms": None,
        "area_sqft": None,
        "price": None,
        "availability": None,
        "furnished": None,
        "furnishing": None,
    }
    if label.lower().startswith(("studio", "bachelor")):
        unit["bedrooms"] = 0.0
    elif m := re.search(r"(\d+(?:\.\d+)?)\s*Bed", label, re.I):
        unit["bedrooms"] = float(m.group(1))
    for cell in cells:
        if m := re.search(r"\$([\d,]+)", cell):
            unit["price"] = float(m.group(1).replace(",", ""))
        elif m := re.search(r"(\d+(?:\.\d+)?)\s*Bath", cell, re.I):
            unit["bathrooms"] = float(m.group(1))
        elif m := re.search(r"([\d,.]+)\s*ft", cell):
            unit["area_sqft"] = float(m.group(1).replace(",", ""))
        elif re.search(r"furnished", cell, re.I):
            # "Furnished" / "Semi-furnished" / "Unfurnished": same convention as Centris
            # (semi counts as furnished, the exact wording goes to extra["furnishing"]).
            unit["furnished"] = not re.search(r"\bun-?furnished", cell, re.I)
            unit["furnishing"] = cell.strip()
        elif cell.strip():
            unit["availability"] = cell.strip()
    return unit if unit["price"] is not None else None


def _extract_units(page) -> list[dict]:
    units_el = page.locator(".listing-details-ssr__units").first
    if units_el.count() == 0:
        return []
    rows = units_el.evaluate(
        """el => [...el.querySelectorAll('li')].map(li => ({
            label: (li.querySelector('strong') || {}).innerText || '',
            cells: [...li.querySelectorAll('span')].map(s => s.innerText),
        }))"""
    )
    units = [u for r in rows if (u := _parse_unit_row(r["label"], r["cells"]))]
    if units:
        return units
    # Older layout: "1 Bedroom 1 1 560.0 ft² $1,582" rows in a table.
    for m in _UNIT_ROW_RE.finditer(units_el.inner_text()):
        _label, beds, baths, size, price = m.groups()
        units.append(
            {
                "bedrooms": float(beds),
                "bathrooms": float(baths),
                "area_sqft": float(size),
                "price": float(price.replace(",", "")),
                "availability": None,
                "furnished": None,
                "furnishing": None,
            }
        )
    return units


def _extract_latlng(html: str) -> tuple[float | None, float | None]:
    m = _LATLNG_RE.search(html)
    return (float(m.group(1)), float(m.group(2))) if m else (None, None)


_CATEGORY_HEADER_RE = re.compile(r"\(\d+\)$")


def _extract_amenities(page) -> list[str]:
    items = page.locator("[class*='amenit'] li").all_inner_texts()
    out, seen = [], set()
    for raw in items:
        text = raw.strip().replace("\n", " ").strip()
        if not text or _CATEGORY_HEADER_RE.search(text):
            continue
        if text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def _extract_utilities(page) -> list[str]:
    items = page.locator("[class*='utilities'] li").all_inner_texts()
    out, seen = [], set()
    for raw in items:
        text = raw.strip()
        if text and text.lower() not in seen:
            seen.add(text.lower())
            out.append(text)
    return out


def scrape(
    *,
    cities: list[str] | None = None,
    max_pages_per_city: int = 3,
    headless: bool = True,
) -> Iterator[Listing]:
    cities = cities or DEFAULT_CITIES
    breaker = BlockBreaker("rentals_ca")
    with new_context(headless=headless) as ctx:
        list_page = ctx.new_page()

        for city in cities:
            buildings: list[tuple[str, str, str]] = []
            for p in range(1, max_pages_per_city + 1):
                url = f"{BASE}/{city}" + (f"?p={p}" if p > 1 else "")
                resp = list_page.goto(url, wait_until="domcontentloaded", timeout=30000)
                breaker.record(browser_status(resp))
                if not resp or resp.status == 404:
                    break
                list_page.wait_for_timeout(2000)
                found = _collect_building_links(list_page)
                if not found:
                    break
                buildings.extend(found)
                polite_delay()

            seen_ids: set[str] = set()
            for prop_id, href, title in buildings:
                if prop_id in seen_ids:
                    continue
                seen_ids.add(prop_id)

                detail_page = ctx.new_page()
                try:
                    breaker.record(browser_status(detail_page.goto(href, wait_until="domcontentloaded", timeout=30000)))
                    detail_page.wait_for_timeout(2000)
                    html = detail_page.content()
                    lat, lng = _extract_latlng(html)
                    photos = sorted(
                        {
                            src
                            for src in detail_page.eval_on_selector_all(
                                "img", "els => els.map(e => e.src)"
                            )
                            if src and "images.rentals.ca/property-pictures" in src
                        }
                    )
                    units = _extract_units(detail_page)
                    amenities = _extract_amenities(detail_page)
                    utilities = _extract_utilities(detail_page)
                except Exception:
                    units, amenities, utilities = [], [], []
                finally:
                    detail_page.close()
                polite_delay()

                for unit in units:
                    # Floor-plan-derived id (not row position) so re-scrapes dedupe consistently.
                    external_id = (
                        f"{prop_id}-{unit['bedrooms']}-{unit['bathrooms']}"
                        f"-{unit['area_sqft']}-{unit['price']}"
                    )
                    yield Listing(
                        source="rentals_ca",
                        external_id=external_id,
                        url=href,
                        title=title or None,
                        listing_type="rent",
                        price=unit["price"],
                        price_period="monthly",
                        # Card titles read "3555 Cote-des-Neiges Road, Montréal, QC".
                        address=(title.split(",")[0].strip() or None) if title else None,
                        city=(
                            title.split(",")[1].strip()
                            if title and title.count(",") >= 2
                            else city.replace("-", " ").title()
                        ),
                        region="QC",
                        latitude=lat,
                        longitude=lng,
                        location_precision="exact" if lat is not None else None,
                        bedrooms=unit["bedrooms"],
                        bathrooms=unit["bathrooms"],
                        area_sqft=unit["area_sqft"],
                        available_date=iso_date(unit.get("availability")),
                        furnished=unit.get("furnished"),
                        extra={"furnishing": unit["furnishing"]} if unit.get("furnishing") else {},
                        amenities=amenities,
                        utilities_included=utilities,
                        photos=photos,
                    )
