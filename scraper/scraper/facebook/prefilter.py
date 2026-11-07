"""Cheap keyword rules applied before the LLM (FR/EN, accent- and case-insensitive).

Kept: whole-unit rentals and sublets. Dropped: colocations / rooms, "looking for" posts,
for-sale posts and posts with no rental signal at all. The rules lean towards keeping:
a post that slips through is still classified by the LLM, a post dropped here is lost.

Known traps handled:
- negated colocs: "pas de coloc", "no roommates", "sans colocataire";
- offering wording that looks like seeking: "cherche locataire", "looking for a tenant",
  "on cherche quelqu'un pour reprendre notre bail" (that's a sublet offer);
- bedroom counts: "4½ 2 chambres à louer" is an apartment, "chambre à louer" a room;
- "à vendre" inside a rental post ("meubles à vendre", "électros à vendre si intéressé").
"""

import hashlib
import re
from dataclasses import dataclass

from ..normalize import _fold


def normalize_text(text: str) -> str:
    """Folded, punctuation-free, single-spaced: what reposts across groups have in common."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9$]+", " ", _fold(text))).strip()


def text_hash(text: str) -> str:
    return hashlib.sha1(normalize_text(text).encode()).hexdigest()[:16]


@dataclass(frozen=True)
class Verdict:
    keep: bool
    reason: str | None = None  # why it was dropped: coloc, seeking, sale, off_topic, empty

    def __bool__(self) -> bool:
        return self.keep


# --- vocabulary (matched against _fold()ed text) ------------------------------------

_NEGATION = r"(?:pas de|pas une?|aucune?|sans|non|no|not a|not|never|jamais de|zero)\s+(?:\w+\s+)?"

_COLOC = re.compile(
    r"\b(?:colocs?|colocations?|colocataires?|co-locataires?|roommates?|room-mates?|roomies?"
    r"|housemates?|flatmates?|colloc\w*"
    r"|room (?:for rent|available|disponible|a louer)|private room|shared (?:apartment|appartement|flat)"
    r"|chambre (?:a louer|disponible|libre|meublee a louer|privee)"
    r"|chambre dans (?:un|une|mon|notre|le|la|grand|beau)"
    r"|room in (?:a|an|my|our|the|shared|big|large|beautiful)"
    r"|partager (?:mon|notre|un|l)\s*(?:appart|logement|4|5|6)"
    r"|cherche (?:un |une )?(?:coloc|colocataire|roommate))\b"
)
# "chambre à louer" preceded by a count is a bedroom count of a whole unit.
_ROOM_COUNT_BEFORE = re.compile(r"(?:\d|deux|trois|quatre|two|three|four)\s*$")

_SEEKING = re.compile(
    r"(?:\b(?:je|j|on|nous)\s*(?:suis|sommes)?\s*(?:a la )?(?:cherche|recherche|cherchons|recherchons)\b"
    r"|\bcherche (?:un|une|des|mon|notre|appartement|appart|logement|studio|loft|\d)"
    r"|^\s*(?:recherche|cherche|looking for|searching for|seeking|wanted|iso)\b"
    r"|\brecherche (?:un|une|de|d|des|appartement|appart|logement|studio|\d)"
    r"|\ba la recherche (?:d|de)\b"
    r"|\b(?:i am|i m|im|we are|we re|were|i|we)\s*(?:currently\s+)?(?:looking|searching)\b"
    r"|\blooking for (?:a|an|my|our|\d|apartment|appartment|place|studio|room)"
    r"|\biso\b|\bin search of\b|\bwanted\s*:)"
)
# Object of the "looking for" that means the poster is the one offering the place.
_OFFERING_OBJECT = re.compile(
    r"^\W*(?:(?:a|an|un|une|des|de|d|du|le|la|les|mon|ma|nos|notre|someone|quelqu un|quelqu|une personne|"
    r"personnes?|un\.e)\s+)*(?:nouveaux?\s+|nouvelles?\s+|new\s+|bons?\s+|good\s+)?"
    r"(?:locataires?|preneurs?|repreneurs?|sous[- ]?locataires?|tenants?|subtenants?|remplacants?|"
    r"someone|somebody|quelqu|personnes? pour|person to|people to|candidats?|occupants?)"
)

_SALE = re.compile(
    r"\b(?:a vendre|for sale|vente (?:de|d|rapide|privee)|condo a vendre|maison a vendre|selling (?:my|our|a)"
    r"|asking price|prix demande|plex a vendre|duplex a vendre|triplex a vendre)\b"
)
# Things sold inside a rental post ("meubles à vendre") don't make it a sale post.
_SALE_OBJECT_BEFORE = re.compile(
    r"(?:meubles?|furniture|electros?|electromenagers?|appliances?|lit|bed|sofa|divan|items?|objets?|"
    r"laveuse|secheuse|frigo|cuisiniere|table|chaises?|bureau|tv|velo|bike)\s+(?:\w+\s+)?$"
)

_RENT_SIGNAL = re.compile(
    r"\b(?:a louer|louer|location|loyer|bail|baux|sous[- ]?locations?|sous[- ]?louer|sublets?|sublease|"
    r"subletting|for rent|rent|rental|lease|leasing|disponible|available|libre|"
    r"par mois|mois|month|monthly|mo|appartement|appart|apartment|apt|logement|studio|loft|condo|"
    r"chauffe|eclaire|heated|hydro|reprise|transfert|cession|demenage|moving)\b"
    r"|\d\s*(?:1/2|½|et demi)|\d+\s*\$|\$\s*\d+"
)
_PRICE_RE = re.compile(r"(?<![\d.])(\d{1,2}[ ,.]?\d{3}|\d{3,4})\s*\$|\$\s*(\d{1,2}[ ,]?\d{3}|\d{3,4})(?![\d])")

_SUBLET = re.compile(
    r"\b(?:sous[- ]?locations?|sous[- ]?louer|sous[- ]?loue|sous[- ]?locataires?|sublets?|sublease|subletting|"
    r"(?:transfert|cession|reprise|reprendre|transfer|take over|takeover)\s+(?:de |du |d |mon |my |our |notre |the |a )?"
    r"(?:bail|lease)|lease (?:transfer|takeover)|lease swap|echange de bail)\b"
)


def _match_not_negated(regex: re.Pattern, text: str) -> bool:
    for m in regex.finditer(text):
        before = text[max(0, m.start() - 25):m.start()]
        if re.search(_NEGATION + r"$", before):
            continue
        if m.group(0).startswith("chambre") and _ROOM_COUNT_BEFORE.search(before):
            continue
        return True
    return False


def _is_seeking(text: str) -> bool:
    for m in _SEEKING.finditer(text):
        after = text[m.end():m.end() + 60]
        if _OFFERING_OBJECT.search(after):
            continue
        return True
    return False


def _is_sale(text: str) -> bool:
    for m in _SALE.finditer(text):
        before = text[max(0, m.start() - 30):m.start()]
        if _SALE_OBJECT_BEFORE.search(before):
            continue
        # "à vendre ou à louer" style posts mention renting too: let the LLM decide.
        if _RENT_SIGNAL.search(text) and re.search(r"\b(?:a louer|for rent|loyer|par mois|/mois|/month)\b", text):
            continue
        return True
    return False


def prefilter(text: str | None) -> Verdict:
    if not text or len(text.strip()) < 15:
        return Verdict(False, "empty")
    folded = re.sub(r"\s+", " ", _fold(text))
    if _match_not_negated(_COLOC, folded):
        return Verdict(False, "coloc")
    if _is_seeking(folded):
        return Verdict(False, "seeking")
    if _is_sale(folded):
        return Verdict(False, "sale")
    if not _RENT_SIGNAL.search(folded):
        return Verdict(False, "off_topic")
    return Verdict(True)


def is_sublet(text: str | None) -> bool:
    return bool(text) and bool(_SUBLET.search(_fold(text)))


def regex_price(text: str | None) -> float | None:
    """The first plausible monthly rent in the text ('1 450$', '$1,450', '1450 $/mois')."""
    if not text:
        return None
    for m in _PRICE_RE.finditer(text):
        raw = re.sub(r"[ ,.]", "", m.group(1) or m.group(2))
        value = float(raw)
        if 300 <= value <= 10000:
            return value
    return None
