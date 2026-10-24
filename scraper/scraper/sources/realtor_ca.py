"""REALTOR.ca rental scraper.

realtor.ca sits behind bot protection (plain HTTP -- including its JSON API
at api2.realtor.ca -- gets a 403). A Playwright-driven Chromium loading the
map page passes, and the page itself POSTs to
`api2.realtor.ca/Listing.svc/AsyncPropertySearch_Post` for the bounding box
in the URL hash. We don't call that API ourselves: we just load the map for a
bounding box and read the JSON response the page receives.

Limits, by design of that approach:
- One map load returns the first page only (~11 listings) plus the total
  count for the box, so we split boxes into quadrants (quadtree) until each
  one fits in a single page, down to `min_tile_deg`.
- In practice (Oct 2026) the site stops answering repeat map loads from the
  same browser session after the first one, so a headless run yields only the
  first ~11 listings. We stop at the first silent tile rather than fight the
  bot protection.
- In headless mode the listing-card template request is refused, so the
  in-page "next page" control doesn't work; with `headless=False` we also
  click through it while it keeps producing new pages.
- Changing only the hash doesn't trigger a new search, so each tile is a
  fresh navigation (via about:blank).

Most Quebec rentals on realtor.ca are Centris listings syndicated through
the boards (their `AlternateURL` points back to centris.ca, and
`extra.mls_number` equals the Centris `external_id`), so the `centris`
source already covers them with richer data.
"""

import re
import sys
from collections.abc import Iterator
from datetime import datetime, timedelta, timezone

from ..browser import new_context, polite_delay
from ..models import Listing
from ..normalize import clean_text, format_postal_code, parse_number, split_city_neighborhood

BASE = "https://www.realtor.ca"

# (lat_min, lng_min, lat_max, lng_max)
AREAS = {
    "montreal": (45.40, -73.98, 45.71, -73.47),
    "laval": (45.51, -73.89, 45.70, -73.52),
    "longueuil": (45.42, -73.56, 45.62, -73.36),
    "quebec-city": (46.72, -71.48, 46.94, -71.13),
    "gatineau": (45.40, -75.95, 45.56, -75.50),
    "sherbrooke": (45.33, -72.03, 45.48, -71.80),
}

_RENT_RE = re.compile(r"/\s*(Monthly|Yearly|mois|an)", re.I)


def _map_url(box: tuple[float, float, float, float]) -> str:
    lat_min, lng_min, lat_max, lng_max = box
    center_lat, center_lng = (lat_min + lat_max) / 2, (lng_min + lng_max) / 2
    return (
        f"{BASE}/map#ZoomLevel=13&Center={center_lat:.6f}%2C{center_lng:.6f}"
        f"&LatitudeMax={lat_max:.6f}&LongitudeMax={lng_max:.6f}"
        f"&LatitudeMin={lat_min:.6f}&LongitudeMin={lng_min:.6f}"
        "&view=list&Sort=6-D&PropertyTypeGroupID=1&TransactionTypeId=3&PropertySearchTypeId=0&Currency=CAD"
    )


def _split(box: tuple[float, float, float, float]) -> list[tuple[float, float, float, float]]:
    lat_min, lng_min, lat_max, lng_max = box
    lat_mid, lng_mid = (lat_min + lat_max) / 2, (lng_min + lng_max) / 2
    return [
        (lat_min, lng_min, lat_mid, lng_mid),
        (lat_min, lng_mid, lat_mid, lng_max),
        (lat_mid, lng_min, lat_max, lng_mid),
        (lat_mid, lng_mid, lat_max, lng_max),
    ]


def _dotnet_ticks_to_iso(ticks: str | None) -> str | None:
    try:
        return (datetime(1, 1, 1, tzinfo=timezone.utc) + timedelta(microseconds=int(ticks) // 10)).isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _sum_parts(text: str | None) -> float | None:
    """'2 + 1' (above + below grade) -> 3.0."""
    if not text:
        return None
    parts = [parse_number(p) for p in str(text).split("+")]
    parts = [p for p in parts if p is not None]
    return sum(parts) if parts else None


def _to_listing(r: dict) -> Listing:
    building = r.get("Building") or {}
    prop = r.get("Property") or {}
    addr = prop.get("Address") or {}

    # "5401 Crois. Plamondon|Saint-Lambert, Quebec J4S1W4" or, with a unit,
    # "2357A Boul. Rosemont|#A|Montréal (Rosemont/La Petite-Patrie), Quebec H2G1T9"
    parts = (addr.get("AddressText") or "").split("|")
    street, locality = parts[0], parts[-1] if len(parts) > 1 else ""
    unit = parts[1].strip() if len(parts) > 2 else None
    city, neighborhood = split_city_neighborhood(locality.rsplit(",", 1)[0], city_first=True) if locality else (None, None)

    rent_text = prop.get("LeaseRent") or ""
    period = "monthly"
    if m := _RENT_RE.search(rent_text):
        period = "yearly" if m.group(1).lower() in ("yearly", "an") else "monthly"
    price = parse_number(prop.get("LeaseRentUnformattedValue")) or parse_number(rent_text)

    baths = parse_number(building.get("BathroomTotal"))
    half = parse_number(building.get("HalfBathTotal")) or 0
    area = parse_number(building.get("SizeInterior"))
    if area and "m2" in (building.get("SizeInterior") or "").lower():
        area = round(area * 10.7639, 1)

    photos = [p.get("HighResPath") or p.get("MedResPath") for p in prop.get("Photo") or []]
    individuals = r.get("Individual") or []
    agent = individuals[0] if individuals else {}

    lat, lng = parse_number(addr.get("Latitude")), parse_number(addr.get("Longitude"))
    extra = {
        "mls_number": r.get("MlsNumber"),  # == centris external_id for Quebec board listings
        "ownership_type": prop.get("OwnershipType"),
        "building_type": building.get("Type"),
        "stories_total": building.get("StoriesTotal"),
        "parking": [p.get("Name") for p in prop.get("Parking") or [] if p.get("Name")] or None,
        "amenities_nearby": prop.get("AmmenitiesNearBy"),
        "alternate_url": (r.get("AlternateURL") or {}).get("DetailsLink"),
        "time_on_realtor": r.get("TimeOnRealtor"),
    }
    return Listing(
        source="realtor_ca",
        external_id=str(r["Id"]),
        url=BASE + (r.get("RelativeURLFr") or r.get("RelativeDetailsURL") or f"/real-estate/{r['Id']}"),
        title=clean_text(street) or None,
        listing_type="rent",
        property_type=(building.get("Type") or prop.get("Type") or None),
        price=price,
        price_period=period,
        address=clean_text(f"{street} {unit}" if unit else street) or None,
        neighborhood=neighborhood,
        city=city,
        region="QC" if r.get("ProvinceName") in ("Quebec", "Québec") else r.get("ProvinceName"),
        postal_code=format_postal_code(r.get("PostalCode")),
        latitude=lat,
        longitude=lng,
        location_precision=(
            ("exact" if addr.get("PermitShowAddress", True) else "approximate") if lat is not None else None
        ),
        bedrooms=_sum_parts(building.get("Bedrooms")),
        bathrooms=(baths + 0.5 * half) if baths is not None else None,
        area_sqft=area,
        parking_spots=int(n) if (n := parse_number(prop.get("ParkingSpaceTotal"))) is not None else None,
        photos=[p for p in photos if p],
        description=clean_text(r.get("PublicRemarks")),
        contact_name=agent.get("Name"),
        agency_name=(agent.get("Organization") or {}).get("Name"),
        published_at=_dotnet_ticks_to_iso(r.get("InsertedDateUTC")),
        extra={k: v for k, v in extra.items() if v},
    )


def _load_tile(page, box, *, headless: bool, timeout_ms: int = 20000) -> tuple[list[dict], int]:
    """Loads the map for `box`; returns (results seen, total records reported for the box)."""
    responses: list[dict] = []

    def on_response(resp):
        if "PropertySearch_Post" in resp.url and resp.status == 200:
            try:
                responses.append(resp.json())
            except Exception:
                pass

    page.on("response", on_response)
    try:
        page.goto("about:blank")
        page.goto(_map_url(box), wait_until="domcontentloaded", timeout=60000)
        waited = 0
        while not responses and waited < timeout_ms:
            page.wait_for_timeout(500)
            waited += 500
        if not responses:
            return [], 0

        total = int((responses[0].get("Paging") or {}).get("TotalRecords") or 0)
        results = list(responses[0].get("Results") or [])
        if not headless:
            # Headed browsers render the list, so the pager works: click through it.
            while len(results) < min(total, 600):
                before = len(responses)
                nxt = page.locator(".lnkNextResultsPage:visible")
                if nxt.count() == 0:
                    break
                nxt.first.click()
                page.wait_for_timeout(4000)
                if len(responses) == before:
                    break
                results.extend(responses[-1].get("Results") or [])
        return results, total
    finally:
        page.remove_listener("response", on_response)


def scrape(
    *,
    areas: list[str] | None = None,
    headless: bool = True,
    min_tile_deg: float = 0.01,
    max_tiles: int = 400,
) -> Iterator[Listing]:
    areas = areas or ["montreal"]
    seen: set[str] = set()
    tiles_loaded = 0
    with new_context(headless=headless, locale="fr-CA") as ctx:
        page = ctx.new_page()
        for area in areas:
            stack = [AREAS[area]]
            while stack and tiles_loaded < max_tiles:
                box = stack.pop()
                results, total = _load_tile(page, box, headless=headless)
                tiles_loaded += 1
                if not results and total == 0 and tiles_loaded > 1:
                    # The site stops answering repeat map loads from the same session; don't
                    # burn the timeout on every remaining tile.
                    print(f"[realtor_ca] no search response for tile {tiles_loaded}; stopping", file=sys.stderr)
                    return
                for r in results:
                    if str(r.get("Id")) in seen:
                        continue
                    seen.add(str(r.get("Id")))
                    try:
                        yield _to_listing(r)
                    except Exception:
                        continue
                too_big = total > len(results)
                if too_big and (box[2] - box[0]) / 2 >= min_tile_deg:
                    stack.extend(_split(box))
                polite_delay()
