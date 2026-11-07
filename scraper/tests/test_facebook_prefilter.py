import pytest

from scraper.facebook.prefilter import is_sublet, normalize_text, prefilter, regex_price, text_hash

KEEP = [
    "4½ à louer sur le Plateau, 1450$/mois, chauffé éclairé, libre le 1er juillet",
    "Grand 5 1/2 à louer à Rosemont, 2 chambres fermées, 1 850 $ par mois. Pas de coloc svp.",
    "Sous-location de mon 3½ du 1er décembre au 30 avril, 1100$, meublé, près du métro Mont-Royal",
    "Sous location 4 1/2 Villeray, 1300$ tout inclus. Je cherche quelqu'un pour reprendre mon bail!",
    "Cession de bail : beau 3 et demi à Verdun, 1 200 $/mois, disponible immédiatement",
    "Je cherche un locataire pour mon 4½ à Hochelaga, 1350$ non chauffé",
    "On cherche des locataires sérieux pour un 6½ rénové à Ahuntsic, 2400$",
    "Nous recherchons un preneur pour notre bail (5½, Petite-Patrie, 1950$)",
    "Looking for a tenant to take over my lease: 1 bedroom in the Plateau, $1,600/month",
    "Looking for someone to sublet my studio downtown from January to May, $1200 all included",
    "Spacious 2 bedroom apartment for rent in Griffintown, $2,100/month, no roommates please",
    "Appartement 3 chambres à louer à Saint-Laurent, 2 200 $ par mois",
    "Studio meublé à louer, Côte-des-Neiges, 950$ chauffé, électros inclus. Meubles à vendre si intéressé.",
    "Lease transfer! 3 1/2 in Mile End, $1,425, available Feb 1st. Not a coloc.",
    "Logement 4½ disponible le 1er janvier, rue Saint-Denis coin Rachel. Contact : 514-555-1234",
    "Sublet available for the summer, cozy studio near Concordia, $1100",
]

DROP = [
    ("Chambre à louer dans un grand 6½ à Rosemont, 700$ tout inclus", "coloc"),
    ("Cherche colocataire pour partager mon 5½ à Villeray, 750$/mois", "coloc"),
    ("Colocation disponible : chambre dans un 4½ près de l'UdeM, 650 $", "coloc"),
    ("Room for rent in a shared apartment downtown, $800 all included", "coloc"),
    ("Looking for a roommate to share my 2 bedroom in NDG, $900/month", "coloc"),
    ("Private room available in Plateau, female only, $750", "coloc"),
    ("Je cherche un 4½ à louer dans le Plateau pour juillet, budget 1500$", "seeking"),
    ("Bonjour! Je suis à la recherche d'un 3½ à Villeray ou Rosemont, max 1200$", "seeking"),
    ("Recherche logement 5½ pour famille de 4, Ahuntsic, budget 2000$/mois", "seeking"),
    ("ISO 1 bedroom apartment in Mile End for May, up to $1500", "seeking"),
    ("Hi everyone, I'm looking for a studio or 1 bedroom near McGill, $1200 max", "seeking"),
    ("We are looking for a 2 bedroom apartment in Verdun starting July 1st", "seeking"),
    ("Cherche sous-location pour l'été, 3½ meublé, centre-ville", "seeking"),
    ("Condo à vendre à Griffintown, 2 chambres, 549 000 $", "sale"),
    ("Triplex à vendre à Rosemont, revenus 54 000$/an, prix demandé 1 150 000$", "sale"),
    ("Condo for sale in Old Montreal, 1 bedroom, $425,000", "sale"),
    ("Quelqu'un connaît un bon déménageur pas trop cher? Merci!", "off_topic"),
    ("Attention aux arnaques dans ce groupe, ne payez jamais de dépôt par virement", "off_topic"),
    ("", "empty"),
]


@pytest.mark.parametrize("text", KEEP)
def test_kept(text):
    verdict = prefilter(text)
    assert verdict.keep, f"dropped as {verdict.reason}: {text}"


@pytest.mark.parametrize(("text", "reason"), DROP)
def test_dropped(text, reason):
    verdict = prefilter(text)
    assert not verdict.keep, f"kept: {text}"
    assert verdict.reason == reason


@pytest.mark.parametrize(
    ("text", "sublet"),
    [
        ("Sous-location de mon 3½ du 1er décembre au 30 avril", True),
        ("Sous location 4 1/2 Villeray", True),
        ("Transfert de bail 4½ Plateau", True),
        ("Cession de bail : beau 3 et demi", True),
        ("Looking for someone to take over my lease", True),
        ("Summer sublet, studio near Concordia", True),
        ("4½ à louer, bail de 12 mois", False),
        ("Spacious 2 bedroom apartment for rent", False),
    ],
)
def test_is_sublet(text, sublet):
    assert is_sublet(text) is sublet


@pytest.mark.parametrize(
    ("text", "price"),
    [
        ("4½ à louer 1450$/mois", 1450),
        ("Loyer : 1 850 $ par mois", 1850),
        ("$1,600/month", 1600),
        ("2 200 $ chauffé", 2200),
        ("Disponible le 1er juillet, 3 chambres", None),
        ("Dépôt de 50$ puis 1200$ par mois", 1200),
    ],
)
def test_regex_price(text, price):
    assert regex_price(text) == price


def test_reposts_share_a_hash():
    a = "4½ à louer, Plateau!! 1450$ / mois\n\nLibre 1er juillet"
    b = "4 ½ A LOUER plateau 1450$/mois libre 1er juillet"
    assert normalize_text(a) != ""
    assert text_hash("4½ à louer, Plateau!! 1450$ / mois") == text_hash("4½ a louer plateau 1450$ / MOIS")
    assert text_hash(a) != text_hash("3½ à louer, Verdun, 1100$")
    assert isinstance(text_hash(b), str)
