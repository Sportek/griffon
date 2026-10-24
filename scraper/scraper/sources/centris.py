"""Centris rental scraper.

No browser needed -- plain HTTP works throughout:

1. Search results (`/fr/propriete~a-louer~<city>?page=N`) are server-rendered
   with 20 listings per page. The `page` query param is honoured on a plain
   GET (the site's own pager POSTs to /Property/GetInscriptions, which needs
   the session-bound query and isn't worth replicating). Centris caps a
   search at ~5000 results, so big areas are better split by city.
2. Each listing page carries price / lat-lng / photos in microdata and hidden
   spans, the rooms/bedrooms/bathrooms "teaser", a list of `carac-container`
   title/value pairs (area, year built, parking, move-in date, additional
   features) and the public remarks.
"""

import html
import re
import time
from collections.abc import Iterator

import httpx
from selectolax.parser import HTMLParser, Node

from ..models import Listing
from ..polite import PoliteClient
from ..normalize import clean_text, iso_date, parse_int, parse_number, parse_qc_rooms, split_city_neighborhood

BASE_URL = "https://www.centris.ca"

# "" = the whole province (still capped at ~5000 results by Centris).
DEFAULT_AREAS = ["montreal", "laval", "longueuil", "quebec", "gatineau", "sherbrooke", "trois-rivieres"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-CA,fr;q=0.9",
}

_LISTING_HREF_RE = re.compile(r'href="(/fr/[^"]*~a-louer~[^"]*/(\d{6,}))"')
_PARENS_COUNT_RE = re.compile(r"\((\d+)\)")
_SQFT_PER_M2 = 10.7639


def _text(node: Node | None) -> str | None:
    return clean_text(node.text(separator=" ")) if node else None


def _attr(tree: HTMLParser, selector: str, name: str) -> str | None:
    node = tree.css_first(selector)
    return node.attributes.get(name) if node else None


def _area_sqft(value: str) -> float | None:
    n = parse_number(value)
    if n is None:
        return None
    return round(n * _SQFT_PER_M2, 1) if "m²" in value or "m2" in value else n


def _parse_features(raw: str) -> dict:
    """Interprets the 'Caractéristiques additionnelles' comma list."""
    items = [clean_text(x) for x in raw.split(",")]
    items = [x for x in items if x]
    lowered = [x.lower() for x in items]
    out: dict = {"amenities": []}
    for item, low in zip(items, lowered):
        if low.startswith("animaux"):
            out["pets_allowed"] = "non accept" not in low
            out["pets_policy"] = item
        elif low.startswith("fumeurs"):
            out["smoking_allowed"] = "non accept" not in low
        elif low in ("meublé", "semi-meublé"):
            out["furnished"] = True
            out["furnishing"] = item
        elif low == "non meublé":
            out["furnished"] = False
        else:
            out["amenities"].append(item)
    return out


def _parse_detail(page_html: str, url: str, external_id: str) -> Listing:
    tree = HTMLParser(page_html)

    page_title = _text(tree.css_first("[data-id=PageTitle]"))  # "Condo / Appartement à louer"
    property_type = re.sub(r"\s+à louer$", "", page_title or "") or None

    address_line = _text(tree.css_first("h2[itemprop=address]"))
    address, city, neighborhood = address_line, None, None
    if address_line and "," in address_line:
        street, _, locality = address_line.rpartition(",")
        address = street.strip()
        city, neighborhood = split_city_neighborhood(locality, city_first=True)

    price = parse_number(_attr(tree, "[itemprop=offers] meta[itemprop=price]", "content"))
    period_text = (_text(tree.css_first(".property-summary-header__price-description")) or "").lower()
    price_period = "yearly" if "an" in period_text.split() else "monthly"

    lat = parse_number(_text(tree.css_first("#PropertyLat")))
    lng = parse_number(_text(tree.css_first("#PropertyLng")))

    rooms = parse_number(_text(tree.css_first(".teaser .piece")))
    bedrooms = parse_number(_text(tree.css_first(".teaser .cac")))
    bathrooms_text = _text(tree.css_first(".teaser .sdb")) or ""
    # "1 salle de bain et 1 salle d'eau" -> 1.5
    bathrooms = None
    if m := re.search(r"(\d+)\s+salles?\s+de\s+bain", bathrooms_text):
        bathrooms = float(m.group(1))
    if m := re.search(r"(\d+)\s+salles?\s+d.eau", bathrooms_text):
        bathrooms = (bathrooms or 0) + 0.5 * int(m.group(1))

    caracs: dict[str, str] = {}
    for c in tree.css(".carac-container"):
        title = _text(c.css_first(".carac-title"))
        value = _text(c.css_first(".carac-value"))
        if title and value:
            caracs[title] = value

    area = None
    for key in ("Superficie nette", "Superficie habitable", "Superficie brute", "Superficie du bâtiment"):
        if key in caracs:
            area = _area_sqft(caracs[key])
            break

    parking = None
    if parking_text := caracs.get("Stationnement total"):
        counts = [int(n) for n in _PARENS_COUNT_RE.findall(parking_text)]
        parking = sum(counts) if counts else parse_int(parking_text)

    features = _parse_features(caracs.get("Caractéristiques additionnelles", ""))

    photos_attr = _attr(tree, "[data-photo-urls]", "data-photo-urls") or ""
    photos = [
        re.sub(r"&w=\d+&h=\d+", "&w=1260&h=1024", html.unescape(u.strip()))
        for u in photos_attr.split(",")
        if u.strip()
    ]
    if not photos and (og := _attr(tree, "meta[property='og:image']", "content")):
        photos = [html.unescape(og)]

    remarks = tree.css_first("#property-public-remarks-container .remarks-text")
    description = clean_text(remarks.text(separator="\n")) if remarks else None
    if not description:
        description = clean_text(_attr(tree, "meta[name=description]", "content"))

    broker = _text(tree.css_first("[itemprop=employee] [itemprop=name]"))
    agency = clean_text(_attr(tree, "[itemprop=employee] [itemprop=legalName]", "content"))

    known = {
        "Superficie nette", "Superficie habitable", "Superficie brute", "Superficie du bâtiment",
        "Année de construction", "Stationnement total", "Caractéristiques additionnelles",
        "Date d’emménagement", "Date d'emménagement",
    }
    extra = {k: v for k, v in caracs.items() if k not in known}
    if rooms is not None:
        extra["rooms_total"] = rooms
    if features.get("pets_policy"):
        extra["pets_policy"] = features["pets_policy"]
    if features.get("furnishing"):
        extra["furnishing"] = features["furnishing"]
    if muni := _text(tree.css_first("#municipalityId")):
        extra["centris_municipality_id"] = muni

    return Listing(
        source="centris",
        external_id=external_id,
        url=url,
        title=clean_text(f"{page_title} - {address_line}") if page_title and address_line else page_title,
        listing_type="rent",
        property_type=property_type,
        price=price or None,
        price_period=price_period,
        address=address,
        neighborhood=neighborhood,
        city=city,
        region="QC",
        latitude=lat,
        longitude=lng,
        location_precision="exact" if lat is not None else None,
        bedrooms=bedrooms,
        bathrooms=bathrooms,
        area_sqft=area,
        # Centris "pièces" is a full room count (a 2-bedroom condo can be 8), not the "X 1/2"
        # convention, so it goes to extra["rooms_total"] instead.
        rooms_qc=parse_qc_rooms(description),
        year_built=parse_int(caracs.get("Année de construction")),
        parking_spots=parking,
        furnished=features.get("furnished"),
        pets_allowed=features.get("pets_allowed"),
        smoking_allowed=features.get("smoking_allowed"),
        available_date=iso_date(caracs.get("Date d’emménagement") or caracs.get("Date d'emménagement")),
        amenities=features["amenities"],
        photos=photos,
        description=description,
        contact_name=broker,
        agency_name=agency,
        extra=extra,
    )


def _search_page(client: httpx.Client, area: str, page: int) -> list[tuple[str, str]]:
    path = f"/fr/propriete~a-louer~{area}" if area else "/fr/propriete~a-louer"
    resp = client.get(BASE_URL + path, params={"page": page} if page > 1 else None)
    resp.raise_for_status()
    found: dict[str, str] = {}
    for href, ext_id in _LISTING_HREF_RE.findall(resp.text):
        found.setdefault(ext_id, BASE_URL + href)
    return list(found.items())


def scrape(
    *,
    areas: list[str] | None = None,
    max_pages_per_area: int = 250,
    delay_s: float = 0.75,
) -> Iterator[Listing]:
    areas = DEFAULT_AREAS if areas is None else areas
    seen: set[str] = set()
    with PoliteClient(headers=HEADERS, timeout=30, follow_redirects=True, source="centris") as client:
        for area in areas:
            for page in range(1, max_pages_per_area + 1):
                try:
                    pairs = _search_page(client, area, page)
                except httpx.HTTPError:
                    break
                new_pairs = [(eid, url) for eid, url in pairs if eid not in seen]
                if not new_pairs:
                    break
                for external_id, url in new_pairs:
                    seen.add(external_id)
                    try:
                        resp = client.get(url)
                        resp.raise_for_status()
                        yield _parse_detail(resp.text, url, external_id)
                    except Exception:
                        pass
                    time.sleep(delay_s)
                time.sleep(delay_s)
