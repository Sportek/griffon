"""LogisQuébec rental scraper.

No browser needed. Search results are server-rendered, 10 per page, at
`/a-louer/<region>/<N>`; listing URLs look like
`/<type>-a-louer-<neighbourhood>-l<id>` (sale listings end in `-v<id>`, which
the regex skips). Each listing page has a schema.org `RealEstateListing`
JSON-LD block with price, address, geo, beds, baths, floor size, amenities
and every photo. The HTML adds the "X½" room count, the availability date
and a "Charges" list (utilities either "Inclus" or a monthly cost).
"""

import json
import re
import time
from collections.abc import Iterator

import httpx
from selectolax.parser import HTMLParser

from ..models import Listing
from ..polite import PoliteClient
from ..normalize import (
    clean_text,
    format_postal_code,
    iso_date,
    parse_number,
    parse_qc_rooms,
    split_city_neighborhood,
)

BASE_URL = "https://www.logisquebec.com"

REGIONS = [
    "ile-de-montreal",
    "laval",
    "monteregie",
    "laurentides",
    "lanaudiere",
    "capitale-nationale",
    "outaouais",
    "estrie",
    "mauricie",
    "chaudiere-appalaches",
    "centre-du-quebec",
    "saguenay_lac-saint-jean",
    "bas-saint-laurent",
    "abitibi-temiscamingue",
    "cote-nord",
    "gaspesie_iles-de-la-madeleine",
    "nord-du-quebec",
]

# Non-residential listing types published under /a-louer.
_EXCLUDED_TYPES = ("bureau", "local-commercial", "batisse-commerciale", "autre-garage", "entrepot", "terrain", "stationnement")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-CA,fr;q=0.9",
}

_LISTING_HREF_RE = re.compile(r'href="(?:https://www\.logisquebec\.com)?/(([a-z\-]+?)-a-louer-[a-z0-9\-_]+-l(\d+))"')
_LD_JSON_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)

_PROPERTY_TYPES = {
    "appartement": "apartment",
    "studio": "studio",
    "condo": "condo",
    "maison": "house",
    "loft": "loft",
    "chambre-et-colocation": "room",
    "chalet": "chalet",
    "duplex": "duplex-triplex",
    "triplex": "duplex-triplex",
}


def _ld_listing(page_html: str) -> dict | None:
    for block in _LD_JSON_RE.findall(page_html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "RealEstateListing":
            return data
    return None


def _gallery(page_html: str, external_id: str, first: list[str]) -> list[str]:
    """Every full-size photo of the listing, the JSON-LD ones (10 at most) first.

    The page shows the whole gallery, under the listing's own id in the path; thumbnails
    and the photos of the other listings it recommends are left out.
    """
    pattern = re.compile(r"https://i\.logisquebec\.com/[^\"'\s)]*/" + re.escape(external_id) + r"/[^\"'\s)/]+\.(?:jpe?g|png|webp)", re.I)
    photos = [u.replace(" ", "%20") for u in first]
    for url in pattern.findall(page_html):
        if "/thumbnail/" not in url and url not in photos:
            photos.append(url)
    return photos


def _parse_detail(page_html: str, url: str, external_id: str, type_slug: str) -> Listing | None:
    ld = _ld_listing(page_html)
    if not ld:
        return None
    apt = ld.get("mainEntity") or {}
    addr = apt.get("address") or {}
    geo = apt.get("geo") or {}
    offer = ld.get("offers") or {}
    price_spec = offer.get("priceSpecification") or {}
    floor = apt.get("floorSize") or {}

    tree = HTMLParser(page_html)
    type_line = clean_text(tree.css_first(".content-annonce-propriete").text()) if tree.css_first(
        ".content-annonce-propriete"
    ) else None
    available = None
    if node := tree.css_first(".content-annonce-disponibilite"):
        available = clean_text(node.text().split(":", 1)[-1])

    utilities, utility_costs = [], {}
    for li in tree.css("ul.charges li"):
        label = clean_text(li.css_first(".label").text()) if li.css_first(".label") else None
        value = clean_text(li.css_first(".content").text()) if li.css_first(".content") else None
        if not label:
            continue
        if value and value.lower().startswith("inclus"):
            utilities.append(label)
        elif value and (cost := parse_number(value)) is not None:
            utility_costs[label] = cost

    amenities = [f["name"] for f in apt.get("amenityFeature") or [] if f.get("name") and f.get("value", True)]
    low = [a.lower() for a in amenities]
    furnished = True if any("meublé" in a and "non" not in a for a in low) else None
    pets = True if any("animaux accept" in a for a in low) else None
    parking = 1 if any("stationnement" in a or "garage" in a for a in low) else None

    city, neighborhood = split_city_neighborhood(addr.get("addressLocality"), city_first=False)
    area = floor.get("value") if floor.get("unitCode") in ("FTK", None) else None
    if floor.get("unitCode") == "MTK" and floor.get("value"):
        area = round(float(floor["value"]) * 10.7639, 1)

    tags = [clean_text(t.text()) for t in tree.css(".mots_cles .tag")]
    extra = {
        "type_line": type_line,
        "utility_costs": utility_costs or None,
        "tags": [t for t in tags if t] or None,
        "ai_summary": clean_text(tree.css_first(".resume-ia").text()) if tree.css_first(".resume-ia") else None,
    }

    contact = tree.css_first("p.content-contact-nom, p.box-contact-right-nom")
    return Listing(
        source="logis_quebec",
        external_id=external_id,
        url=url,
        title=clean_text(ld.get("name")),
        listing_type="rent",
        property_type=_PROPERTY_TYPES.get(type_slug, type_slug),
        price=float(price_spec["price"]) if price_spec.get("price") else None,
        price_period="monthly" if price_spec.get("unitCode", "MON") == "MON" else "unknown",
        address=clean_text(addr.get("streetAddress")),
        neighborhood=neighborhood,
        city=city,
        region=addr.get("addressRegion") or "QC",
        postal_code=format_postal_code(addr.get("postalCode")),
        latitude=geo.get("latitude"),
        longitude=geo.get("longitude"),
        location_precision="exact" if geo.get("latitude") is not None else None,
        bedrooms=apt.get("numberOfBedrooms"),
        bathrooms=apt.get("numberOfBathroomsTotal"),
        area_sqft=area,
        rooms_qc=parse_qc_rooms(type_line) or parse_qc_rooms(ld.get("name")),
        parking_spots=parking,
        furnished=furnished,
        pets_allowed=pets,
        available_date=iso_date(available),
        amenities=amenities,
        utilities_included=utilities,
        photos=_gallery(page_html, external_id, ld.get("image") or []),
        description=ld.get("description"),
        contact_name=clean_text(contact.text()) if contact else None,
        extra={k: v for k, v in extra.items() if v},
    )


def _search_page(client: httpx.Client, region: str, page: int) -> list[tuple[str, str, str]]:
    url = f"{BASE_URL}/a-louer/{region}" + (f"/{page}" if page > 1 else "")
    resp = client.get(url)
    if resp.status_code == 404:
        return []
    resp.raise_for_status()
    # Only the results list: the page footer also links "similar" listings.
    body = resp.text.split('id="content-result-footer"', 1)[0]
    out: dict[str, tuple[str, str]] = {}
    for path, type_slug, ext_id in _LISTING_HREF_RE.findall(body):
        if type_slug.startswith(_EXCLUDED_TYPES):
            continue
        out.setdefault(ext_id, (f"{BASE_URL}/{path}", type_slug))
    return [(eid, url, t) for eid, (url, t) in out.items()]


def scrape(
    *,
    regions: list[str] | None = None,
    max_pages_per_region: int = 500,
    delay_s: float = 0.75,
) -> Iterator[Listing]:
    regions = regions or REGIONS
    seen: set[str] = set()
    with PoliteClient(headers=HEADERS, timeout=30, follow_redirects=True, source="logis_quebec") as client:
        for region in regions:
            for page in range(1, max_pages_per_region + 1):
                try:
                    rows = _search_page(client, region, page)
                except httpx.HTTPError:
                    break
                new_rows = [r for r in rows if r[0] not in seen]
                if not new_rows:
                    break
                for external_id, url, type_slug in new_rows:
                    seen.add(external_id)
                    try:
                        resp = client.get(url)
                        resp.raise_for_status()
                        if listing := _parse_detail(resp.text, url, external_id, type_slug):
                            yield listing
                    except Exception:
                        pass
                    time.sleep(delay_s)
                time.sleep(delay_s)
