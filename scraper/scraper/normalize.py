"""Small parsing helpers shared by the sources."""

import html
import re
import unicodedata
from datetime import date

from selectolax.parser import HTMLParser

_NUM_RE = re.compile(r"-?\d[\d\s  ,]*(?:[.,]\d+)?")


def parse_number(text: str | None) -> float | None:
    """'1 350 $' -> 1350.0, '2,250' -> 2250.0, '594 pc' -> 594.0, '1.5' -> 1.5."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    m = _NUM_RE.search(text)
    if not m:
        return None
    raw = re.sub(r"[\s  ]", "", m.group(0))
    # "2,250" is a thousands separator; "1,5" is a French decimal.
    if re.fullmatch(r"-?\d{1,3}(,\d{3})+", raw):
        raw = raw.replace(",", "")
    else:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_int(text: str | None) -> int | None:
    n = parse_number(text)
    return int(n) if n is not None else None


_QC_ROOMS_RE = re.compile(r"(\d{1,2})\s*(?:½|1/2|\.5|,5|\s+et\s+demi|\s+and\s+a\s+half|\s+&\s+demi)", re.I)


def parse_qc_rooms(text: str | None) -> float | None:
    """Pulls the Quebec 'X 1/2' room count out of free text ('Appartement 3½', '4 1/2', '5 et demi')."""
    if not text:
        return None
    if m := _QC_ROOMS_RE.search(text):
        return float(m.group(1))
    return None


_PAREN_RE = re.compile(r"^\s*(.*?)\s*\(([^)]*)\)\s*$")


def split_city_neighborhood(text: str | None, *, city_first: bool) -> tuple[str | None, str | None]:
    """Splits 'Montréal (Ville-Marie)' (city_first=True) or 'Ville-Marie (Montréal)' (city_first=False).

    Returns (city, neighborhood). Text without parentheses is returned as the city.
    """
    if not text:
        return None, None
    text = html.unescape(text).strip()
    m = _PAREN_RE.match(text)
    if not m:
        return text, None
    outer, inner = m.group(1).strip() or None, m.group(2).strip() or None
    return (outer, inner) if city_first else (inner, outer)


def html_to_text(fragment: str | None) -> str | None:
    """Converts a description HTML fragment to plain text, keeping line breaks."""
    if not fragment:
        return None
    fragment = re.sub(r"<br\s*/?>|</p>|</li>", "\n", fragment, flags=re.I)
    tree = HTMLParser(fragment)
    text = tree.text(separator="") if tree.body is None else tree.body.text(separator="")
    text = html.unescape(text)
    text = re.sub(r"[ \t ]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text)
    return text.strip() or None


def clean_text(text: str | None) -> str | None:
    if text is None:
        return None
    text = re.sub(r"\s+", " ", html.unescape(text)).strip()
    return text or None


_ISO_DATE_RE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_MONTHS = {
    "janvier": 1, "février": 2, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
    "juillet": 7, "août": 8, "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11,
    "décembre": 12, "decembre": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_TEXT_DATE_RE = re.compile(r"(\d{1,2})(?:er|st|nd|rd|th)?\s+([a-zéû]+)\s+(\d{4})", re.I)
_TEXT_DATE_EN_RE = re.compile(r"([a-z]+)\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(\d{4})", re.I)


IMMEDIATELY = "immediately"
_IMMEDIATE = {
    "immediatement", "immediately", "available", "available now", "now", "maintenant",
    "disponible", "disponible maintenant", "disponible immediatement", "tout de suite",
}
_NOT_AVAILABLE = {"n/a", "na", "-", "?"}


def _fold(text: str) -> str:
    """Lower-case, accent-free: 'Immédiatement' -> 'immediatement'."""
    decomposed = unicodedata.normalize("NFD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower().strip()


def iso_date(text: str | None) -> str | None:
    """Returns 'YYYY-MM-DD' when the text holds a date ('2026-07-01', '1er juillet 2026',
    'July 1, 2026'), IMMEDIATELY for 'Immédiatement' / 'Available now', None for 'N/A',
    else the cleaned raw text (e.g. 'Novembre 2026')."""
    text = clean_text(text)
    if not text:
        return None
    folded = _fold(text).rstrip(".!")
    if folded in _IMMEDIATE:
        return IMMEDIATELY
    if folded in _NOT_AVAILABLE:
        return None
    candidates = []
    if m := _ISO_DATE_RE.search(text):
        candidates.append((m.group(1), m.group(2), m.group(3)))
    if (m := _TEXT_DATE_RE.search(text)) and m.group(2).lower() in _MONTHS:
        candidates.append((m.group(3), _MONTHS[m.group(2).lower()], m.group(1)))
    if (m := _TEXT_DATE_EN_RE.search(text)) and m.group(1).lower() in _MONTHS:
        candidates.append((m.group(3), _MONTHS[m.group(1).lower()], m.group(2)))
    for y, mo, d in candidates:
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            continue
    return text


# Canonical property types, checked in order (first match wins): the sources use their own
# labels ("Condo / Appartement", "appartement-condo-court-terme", "Apartment", "maison"...).
_PROPERTY_TYPE_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("room", ("chambre", "room", "colocation", "coloc")),
    ("studio", ("studio", "bachelor")),
    ("loft", ("loft",)),
    ("townhouse", ("townhouse", "town house", "maison de ville", "row house")),
    ("duplex-triplex", ("duplex", "triplex", "quadruplex", "plex")),
    ("chalet", ("chalet", "cottage", "cabin")),
    # "Condo / Appartement" is one Centris category: it is an apartment, not specifically a condo.
    ("apartment", ("appartement", "apartment", "apt", "logement", "basement", "sous-sol", "flat")),
    ("condo", ("condo",)),
    ("house", ("maison", "house", "bungalow", "cottage", "single family")),
]
PROPERTY_TYPES = [name for name, _ in _PROPERTY_TYPE_RULES]


def property_type(raw: str | None) -> str | None:
    """Maps a source's property type label to one of PROPERTY_TYPES; unknown labels are
    returned lower-cased so they stay visible instead of being guessed."""
    if not raw or not raw.strip():
        return None
    folded = _fold(raw)
    words = re.sub(r"[^a-z0-9]+", " ", folded)
    for name, keywords in _PROPERTY_TYPE_RULES:
        if any(re.search(rf"\b{re.escape(k)}", words) for k in keywords):
            return name
    return folded


def format_postal_code(text: str | None) -> str | None:
    """'h2a3c5' -> 'H2A 3C5'. Returns the input unchanged if it isn't a Canadian postal code."""
    if not text:
        return None
    compact = re.sub(r"\s", "", text).upper()
    if re.fullmatch(r"[A-Z]\d[A-Z]\d[A-Z]\d", compact):
        return f"{compact[:3]} {compact[3:]}"
    return text.strip() or None


_POSTAL_RE = re.compile(r"\b([A-Za-z]\d[A-Za-z])\s?(\d[A-Za-z]\d)\b")


def find_postal_code(text: str | None) -> str | None:
    if text and (m := _POSTAL_RE.search(text)):
        return f"{m.group(1).upper()} {m.group(2).upper()}"
    return None
