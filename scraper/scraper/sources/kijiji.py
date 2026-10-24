"""Kijiji long-term rentals scraper.

No browser needed. Both the search results page and the listing page are
Next.js pages that embed their Apollo GraphQL cache in `__NEXT_DATA__`:

- Search pages (`/b-appartement-condo/<slug>/page-N/c37l<locationId>`) hold
  ~45 `RealEstateListing:<id>` entries each, already including coordinates,
  price (in cents), photos and every structured attribute (beds, baths,
  utilities, amenities, ...). The description there is truncated.
- The listing page holds the same record with the full HTML description and
  a `CommercialProfileV2` entry for the poster (agency / building name).

Attribute values are strings: booleans are "0"/"1", `numberbathrooms` is
x10 ("15" = 1.5 baths), `petsallowed` can be "limited", and
`smokingpermitted` is 0=no / 1=yes / 2=outdoors only.
"""

import json
import re
import time
from collections.abc import Iterator

import httpx

from ..models import Listing
from ..polite import PoliteClient
from ..normalize import find_postal_code, html_to_text, iso_date, parse_qc_rooms

BASE_URL = "https://www.kijiji.ca"
CATEGORY_ID = 37  # "Appartements, condos" (long-term rentals)
CATEGORY_SLUG = "b-appartement-condo"

# (url slug, Kijiji location id). Province-wide search covers everything; the
# cities are handy for narrower runs.
LOCATIONS = {
    "quebec": ("quebec", 9001),
    "montreal": ("ville-de-montreal", 1700281),
    "grand-montreal": ("grand-montreal", 80002),
    "quebec-city": ("ville-de-quebec", 1700124),
    "gatineau": ("gatineau", 1700186),
    "sherbrooke": ("sherbrooke-qc", 1700156),
}

# The province segment, alone ("QC") or followed by the postal code ("QC H4K 1J8").
_PROVINCE_RE = re.compile(r"^(?:QC|Québec|Quebec)(?:\s+[A-Za-z]\d[A-Za-z]\s?\d[A-Za-z]\d)?$", re.I)


def _city_from_address(address: str | None) -> str | None:
    """The part right before the province: "4050 Rosemont, Montréal, QC, H1X 1M3" and
    "Montréal, QC H4K 1J8" both give "Montréal"."""
    if not address:
        return None
    parts = [p.strip() for p in address.split(",")]
    for i, part in enumerate(parts):
        if i > 0 and _PROVINCE_RE.match(part):
            return parts[i - 1] or None
    return None


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-CA,fr;q=0.9,en;q=0.8",
}

_NEXT_DATA_RE = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_IMAGE_RULE_RE = re.compile(r"rule=kijijica-\d+-\w+")
_CIVIC_NUMBER_RE = re.compile(r"^\s*\d+")

_UTILITIES = {
    "heat": "Heat",
    "water": "Water",
    "hydro": "Electricity",
    "internet": "Internet",
    "cabletv": "Cable TV",
}
_AMENITIES = {
    "airconditioning": "Air conditioning",
    "balcony": "Balcony",
    "yard": "Yard",
    "dishwasher": "Dishwasher",
    "fridgefreezer": "Fridge / Freezer",
    "laundryinunit": "Laundry (in unit)",
    "laundryinbuilding": "Laundry (in building)",
    "storagelocker": "Storage locker",
    "elevator": "Elevator",
    "gym": "Gym",
    "pool": "Pool",
    "concierge": "Concierge",
    "twentyfourhoursecurity": "24h security",
    "bicycleparking": "Bicycle parking",
    "wheelchairaccessible": "Wheelchair accessible",
    "barrierfreeentrancesandramps": "Barrier-free entrances and ramps",
    "accessiblewashroomsinsuite": "Accessible washrooms in suite",
    "visualaids": "Visual aids",
    "audioprompts": "Audio prompts",
    "braillelabels": "Braille labels",
}


def _apollo_state(page_html: str) -> dict:
    m = _NEXT_DATA_RE.search(page_html)
    if not m:
        return {}
    data = json.loads(m.group(1))
    return data.get("props", {}).get("pageProps", {}).get("__APOLLO_STATE__", {}) or {}


def _attrs(listing: dict) -> dict[str, list[str]]:
    return {
        a["canonicalName"]: a.get("canonicalValues") or []
        for a in (listing.get("attributes") or {}).get("all", [])
        if a.get("canonicalName")
    }


def _first(attrs: dict[str, list[str]], key: str) -> str | None:
    vals = attrs.get(key)
    return vals[0] if vals else None


def _flag(attrs: dict[str, list[str]], key: str) -> bool | None:
    val = _first(attrs, key)
    if val is None:
        return None
    return val not in ("0", "false", "")


def _float(val: str | None) -> float | None:
    try:
        return float(val) if val not in (None, "") else None
    except ValueError:
        return None


def _full_size(url: str) -> str:
    return _IMAGE_RULE_RE.sub("rule=kijijica-1600-jpg", url)


def _to_listing(raw: dict, *, profile: dict | None = None, full_description: bool = False) -> Listing:
    attrs = _attrs(raw)
    loc = raw.get("location") or {}
    coords = loc.get("coordinates") or {}
    address = loc.get("address")

    price = (raw.get("price") or {}).get("amount")
    baths = _float(_first(attrs, "numberbathrooms"))
    area = _float(_first(attrs, "areainfeet"))
    pets = _first(attrs, "petsallowed")
    smoking = _first(attrs, "smokingpermitted")
    posted_by = _first(attrs, "forrentbyhousing")

    description = raw.get("description")
    description = html_to_text(description) if full_description else (description or None)

    # Kijiji lets posters hide the civic number, in which case the pin is only near the street.
    has_civic = bool(address and _CIVIC_NUMBER_RE.match(address))
    lat, lng = coords.get("latitude"), coords.get("longitude")

    city = _city_from_address(address)

    extra = {
        "posted_by": {"ownr": "owner", "reprofessional": "professional"}.get(posted_by, posted_by),
        "nearest_intersection": loc.get("nearestIntersection") or None,
        "kijiji_location": loc.get("name"),
        "virtual_options": attrs.get("rentalsvirtualoptions") or None,
        "pets_policy": pets if pets not in ("0", "1") else None,  # e.g. "limited"
        "smoking_policy": {"0": "no", "1": "yes", "2": "outdoors_only"}.get(smoking, smoking),
        "laundry_in_unit": _flag(attrs, "laundryinunit"),
        "top_ad": (raw.get("flags") or {}).get("topAd"),
    }

    return Listing(
        source="kijiji",
        external_id=str(raw["id"]),
        url=raw.get("url") or f"{BASE_URL}/v-appartement-condo/{raw['id']}",
        title=raw.get("title"),
        listing_type="rent",
        property_type=_first(attrs, "unittype"),
        price=price / 100 if price else None,
        price_period="monthly",
        address=address,
        city=city,
        region="QC",
        postal_code=find_postal_code(address),
        latitude=lat,
        longitude=lng,
        location_precision=("exact" if has_civic else "approximate") if lat is not None else None,
        bedrooms=_float(_first(attrs, "numberbedrooms")),
        bathrooms=baths / 10 if baths is not None else None,
        area_sqft=area if area and area > 50 else None,
        rooms_qc=parse_qc_rooms(raw.get("title")) or parse_qc_rooms(description),
        parking_spots=int(n) if (n := _float(_first(attrs, "numberparkingspots"))) is not None else None,
        furnished=_flag(attrs, "furnished"),
        pets_allowed=None if pets is None else pets != "0",
        smoking_allowed=None if smoking is None else smoking == "1",
        available_date=iso_date(_first(attrs, "dateavailable")),
        lease_term=_first(attrs, "agreementtype"),
        amenities=[label for key, label in _AMENITIES.items() if _flag(attrs, key)],
        utilities_included=[label for key, label in _UTILITIES.items() if _flag(attrs, key)],
        photos=[_full_size(u) for u in raw.get("imageUrls") or []],
        description=description,
        contact_name=None,
        agency_name=(profile or {}).get("name"),
        published_at=raw.get("activationDate"),
        extra={k: v for k, v in extra.items() if v is not None},
    )


def _search_url(slug: str, location_id: int, page: int) -> str:
    page_part = f"/page-{page}" if page > 1 else ""
    return f"{BASE_URL}/{CATEGORY_SLUG}/{slug}{page_part}/c{CATEGORY_ID}l{location_id}"


def _fetch_detail(client: httpx.Client, url: str) -> tuple[dict | None, dict | None]:
    resp = client.get(url)
    resp.raise_for_status()
    state = _apollo_state(resp.text)
    listing = next((v for k, v in state.items() if k.startswith("RealEstateListing:")), None)
    profile = next((v for k, v in state.items() if k.startswith("CommercialProfile")), None)
    return listing, profile


def scrape(
    *,
    location: str = "quebec",
    max_pages: int = 100,
    fetch_details: bool = True,
    delay_s: float = 0.75,
) -> Iterator[Listing]:
    """Yields Kijiji rentals for `location` (a key of LOCATIONS, or 'slug:locationId')."""
    if location in LOCATIONS:
        slug, location_id = LOCATIONS[location]
    else:
        slug, _, loc_id = location.partition(":")
        location_id = int(loc_id)

    seen: set[str] = set()
    with PoliteClient(headers=HEADERS, timeout=30, follow_redirects=True, source="kijiji") as client:
        for page in range(1, max_pages + 1):
            resp = client.get(_search_url(slug, location_id, page))
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            state = _apollo_state(resp.text)
            rows = [v for k, v in state.items() if k.startswith("RealEstateListing:")]
            new_rows = [r for r in rows if str(r.get("id")) not in seen]
            if not new_rows:
                # Past the last page Kijiji serves the last page again instead of a 404.
                break

            for row in new_rows:
                seen.add(str(row["id"]))
                listing_raw, profile = row, None
                full = False
                if fetch_details and row.get("url"):
                    try:
                        detail, profile = _fetch_detail(client, row["url"])
                        if detail:
                            # Detail records lack the SRP-only fields (e.g. nearestIntersection); merge.
                            listing_raw = {**row, **{k: v for k, v in detail.items() if v is not None}}
                            listing_raw["location"] = row.get("location") or detail.get("location")
                            # Detail pages blank out some attributes (e.g. dateavailable): keep non-empty ones.
                            merged = {**_attrs(row), **{k: v for k, v in _attrs(detail).items() if v}}
                            listing_raw["attributes"] = {
                                "all": [{"canonicalName": k, "canonicalValues": v} for k, v in merged.items()]
                            }
                            full = True
                    except httpx.HTTPError:
                        pass
                    time.sleep(delay_s)
                try:
                    yield _to_listing(listing_raw, profile=profile, full_description=full)
                except Exception:
                    continue
            time.sleep(delay_s)
