"""Centris scraper: rentals (`scrape`) and properties for sale (`scrape_sale`, at the end).

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
import os
import re
import sys
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
    property_type = re.sub(r"\s+à (?:louer|vendre)$", "", page_title or "") or None

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


# --- Properties for sale ------------------------------------------------------------------
#
# The same pages with `~a-vendre~` instead of `~a-louer~`, one search per category
# (condo, maison, plex). What differs from rentals:
# - Centris caps a search at 5000 results (`#numberOfResults` 5000 and a "+" in
#   `#pagingMoreSign`), and Montreal condos alone exceed it. A capped search is split into
#   the sub-areas its listings link to ("condo~a-vendre~montreal-ville-marie"), which Centris
#   accepts as search areas too. A sub-area that is still capped leaves the crawl incomplete:
#   scrape_sale then raises IncompleteCrawl once it is done, so the ingestion run fails and
#   nothing is flagged inactive on the strength of a partial view.
# - One inscription number can be offered both for rent and for sale: sale listings get the
#   external id "sale-<number>", so the two offers stay two listings (number in extra.mls_number).
# - "Détails financiers" give the municipal assessment, the taxes and the condo fees, each
#   in a monthly and a yearly table.

SALE_CATEGORIES = ["condo", "maison", "plex"]
DEFAULT_SALE_AREAS = ["montreal", "laval", "longueuil"]
# A sale run walks thousands of detail pages: a larger request budget than rentals, still
# rate limited by PoliteClient. SCRAPER_SALE_MAX_REQUESTS overrides it (0 = unlimited).
SALE_MAX_REQUESTS = 20000

_SALE_HREF_RE = re.compile(r'href="(/fr/([a-z0-9-]+)~a-vendre~([a-z0-9-]+)/(\d{6,}))"')
_MORE_RE = re.compile(r'id="pagingMoreSign">\s*(\S*?)\s*<')
# Not homes: skipped before their detail page is fetched.
_NOT_HOMES = {
    "terrain", "terre", "ferme", "fermette", "commercial", "commerce", "industriel", "bureau",
    "entreprise", "local-commercial", "batiment-commercial",
}
_SALE_KNOWN = {
    "Superficie du terrain", "Nombre d’unités", "Nombre d'unités", "Revenus bruts potentiels",
    "Unité principale", "Unités résidentielles",
}


class IncompleteCrawl(RuntimeError):
    """Some search stayed capped by the site: what the run did not see may still be online."""


def _caracs(tree: HTMLParser) -> dict[str, str]:
    caracs: dict[str, str] = {}
    for c in tree.css(".carac-container"):
        title = _text(c.css_first(".carac-title"))
        value = _text(c.css_first(".carac-value"))
        if title and value:
            caracs[title] = value
    return caracs


def _financials(tree: HTMLParser) -> dict:
    """Assessment, taxes (yearly), condo fees (monthly) and the other expenses (yearly)."""
    out: dict = {}
    section = tree.css_first("section[data-financial-details]")
    if section is None:
        return out
    if m := re.search(r"valuation municipale\s*\((\d{4})\)", section.text(separator=" ")):
        out["municipal_assessment_year"] = int(m.group(1))
    other: dict[str, float] = {}
    for table in section.css("table.financial-details-table__table"):
        wrapper_class = (table.parent.attributes.get("class") or "") if table.parent else ""
        period = "monthly" if "--monthly" in wrapper_class else "yearly" if "--yearly" in wrapper_class else None
        rows = {}
        for tr in table.css("tbody tr"):
            label = _text(tr.css_first(".financial-details-table__label"))
            value = parse_number(_text(tr.css_first(".financial-details-table__value")))
            if label and value is not None:
                rows[label] = value
        total = parse_number(_text(table.css_first("tfoot .financial-details-table__value")))
        if period is None:
            # The assessment table: land, building, total.
            if total is not None and any(k.lower().startswith(("terrain", "bâtiment")) for k in rows):
                out["municipal_assessment"] = total
            continue
        for label, value in rows.items():
            low = label.lower()
            if low.startswith("municipal"):
                if period == "yearly":
                    out["municipal_taxes_yearly"] = value
            elif low.startswith("scolaire"):
                if period == "yearly":
                    out["school_taxes_yearly"] = value
            elif "copropriété" in low:
                if period == "monthly":
                    out["condo_fees_monthly"] = value
                else:
                    out.setdefault("condo_fees_monthly", round(value / 12, 2))
            elif period == "yearly":
                other[label] = value
    if other:
        out["expenses_yearly"] = other
    return out


def _residential_units(text: str | None) -> int | None:
    """'Résidentiel (3)' or 'Résidentiel (2), Commercial (1)' -> the dwellings."""
    if text and (m := re.search(r"sidentiel\w*\s*\((\d+)\)", text, re.I)):
        return int(m.group(1))
    return None


def _parse_sale_detail(page_html: str, url: str, number: str) -> Listing:
    base = _parse_detail(page_html, url, number)
    tree = HTMLParser(page_html)
    caracs = _caracs(tree)
    fin = _financials(tree)
    units = _residential_units(caracs.get("Nombre d’unités") or caracs.get("Nombre d'unités"))

    data = base.model_dump()
    extra = {k: v for k, v in data["extra"].items() if k not in _SALE_KNOWN}
    # A plex has no teaser: its main dwelling reads "7 pièces, 4 chambres, 2 salles de bain".
    if main := caracs.get("Unité principale"):
        if data["bedrooms"] is None and (m := re.search(r"(\d+)\s+chambres?", main)):
            data["bedrooms"] = float(m.group(1))
        if data["bathrooms"] is None and (m := re.search(r"(\d+)\s+salles?\s+de\s+bain", main)):
            data["bathrooms"] = float(m.group(1))
        if m := re.search(r"(\d+)\s+pièces?", main):
            extra.setdefault("rooms_total", float(m.group(1)))
    extra["mls_number"] = number
    if units_text := caracs.get("Unités résidentielles"):
        extra["residential_units"] = units_text  # "2 x 3 ½, 1 x 7 ½"
    if fin.get("expenses_yearly"):
        extra["expenses_yearly"] = fin["expenses_yearly"]

    lot = caracs.get("Superficie du terrain")
    data.update(
        external_id=f"sale-{number}",
        listing_type="sale",
        price_period="total",
        # The "X 1/2" pulled from a plex's description is one of its units, not the property.
        rooms_qc=None if units and units > 1 else data["rooms_qc"],
        lot_area_sqft=_area_sqft(lot) if lot else None,
        municipal_assessment=fin.get("municipal_assessment"),
        municipal_assessment_year=fin.get("municipal_assessment_year"),
        municipal_taxes_yearly=fin.get("municipal_taxes_yearly"),
        school_taxes_yearly=fin.get("school_taxes_yearly"),
        condo_fees_monthly=fin.get("condo_fees_monthly"),
        units=units,
        gross_revenue_yearly=parse_number(caracs.get("Revenus bruts potentiels")),
        extra=extra,
    )
    return Listing(**data)


def _sale_search_page(
    client: httpx.Client, category: str, area: str, page: int
) -> tuple[dict[str, tuple[str, str, str]], bool]:
    """({number: (url, category slug, area slug)}, capped) for one page of results."""
    path = f"/fr/{category}~a-vendre~{area}" if area else f"/fr/{category}~a-vendre"
    resp = client.get(BASE_URL + path, params={"page": page} if page > 1 else None)
    resp.raise_for_status()
    found: dict[str, tuple[str, str, str]] = {}
    for href, cat, loc, number in _SALE_HREF_RE.findall(resp.text):
        found.setdefault(number, (BASE_URL + href, cat, loc))
    more = _MORE_RE.search(resp.text)
    return found, bool(more and more.group(1) in ("+", "&#x2B;"))


def scrape_sale(
    *,
    areas: list[str] | None = None,
    categories: list[str] | None = None,
    max_pages_per_area: int = 250,
    delay_s: float = 0.75,
    max_requests: int | None = None,
) -> Iterator[Listing]:
    """Yields Centris properties for sale (condos, houses, plexes) in `areas`."""
    areas = DEFAULT_SALE_AREAS if areas is None else areas
    categories = SALE_CATEGORIES if categories is None else categories
    if max_requests is None:
        max_requests = int(os.getenv("SCRAPER_SALE_MAX_REQUESTS", SALE_MAX_REQUESTS))
    seen: set[str] = set()
    capped: list[str] = []
    with PoliteClient(
        headers=HEADERS, timeout=30, follow_redirects=True, source="centris_sale", max_requests=max_requests
    ) as client:
        for category in categories:
            queue, searched = list(areas), set()
            while queue:
                area = queue.pop(0)
                if area in searched:
                    continue
                searched.add(area)
                in_search: dict[str, tuple[str, str, str]] = {}
                search_capped = False
                for page in range(1, max_pages_per_area + 1):
                    try:
                        found, page_capped = _sale_search_page(client, category, area, page)
                    except httpx.HTTPError as e:
                        print(f"[centris_sale] {category}~{area} page {page}: {e!r}", file=sys.stderr)
                        break
                    search_capped = search_capped or page_capped
                    # Past the last page Centris serves the last one again.
                    fresh = {n: v for n, v in found.items() if n not in in_search}
                    if not fresh:
                        break
                    in_search.update(fresh)
                    for number, (url, cat, _loc) in fresh.items():
                        if number in seen or cat in _NOT_HOMES:
                            continue
                        seen.add(number)
                        try:
                            resp = client.get(url)
                            resp.raise_for_status()
                            yield _parse_sale_detail(resp.text, url, number)
                        except Exception as e:  # noqa: BLE001 -- one odd page must not stop the crawl
                            print(f"[centris_sale] {url}: {e!r}", file=sys.stderr)
                        time.sleep(delay_s)
                    time.sleep(delay_s)
                if not search_capped:
                    continue
                subareas = sorted({loc for _, _, loc in in_search.values() if area and loc.startswith(area + "-")})
                if area in areas and subareas:
                    print(
                        f"[centris_sale] {category}~{area} is capped, splitting into {len(subareas)} areas",
                        file=sys.stderr,
                    )
                    queue.extend(subareas)
                else:
                    capped.append(f"{category}~{area}")
    if capped:
        raise IncompleteCrawl(f"centris_sale: searches capped at 5000 results: {', '.join(capped)}")
