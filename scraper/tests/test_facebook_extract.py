from datetime import datetime, timezone
from pathlib import Path

import pytest

from scraper.facebook.extract import (
    feed_url,
    group_key,
    parse_article,
    parse_groups,
    parse_permalink,
    parse_timestamp,
    split_articles,
)

FIXTURE = Path(__file__).parent / "fixtures" / "facebook" / "group_feed.html"
NOW = datetime(2026, 11, 7, 18, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def posts():
    articles = split_articles(FIXTURE.read_text(encoding="utf-8"))
    assert len(articles) == 5  # the comment is not a top-level article
    return [parse_article(html, group="242242325809377", now=NOW) for html in articles]


@pytest.mark.parametrize(
    ("value", "key"),
    [
        ("https://www.facebook.com/groups/242242325809377", "242242325809377"),
        ("https://www.facebook.com/groups/232947036803405/", "232947036803405"),
        ("https://www.facebook.com/groups/logementpmr.annonces/", "logementpmr.annonces"),
        ("https://m.facebook.com/groups/logementpmr.annonces/?ref=share", "logementpmr.annonces"),
        ("groups/242242325809377/", "242242325809377"),
        ("242242325809377", "242242325809377"),
        ("logementpmr.annonces/", "logementpmr.annonces"),
    ],
)
def test_group_key(value, key):
    assert group_key(value) == key


def test_parse_groups_dedupes_and_keeps_order():
    value = (
        "https://www.facebook.com/groups/242242325809377,\n"
        " https://www.facebook.com/groups/232947036803405/ , https://www.facebook.com/groups/logementpmr.annonces/,"
        "242242325809377/"
    )
    assert parse_groups(value) == ["242242325809377", "232947036803405", "logementpmr.annonces"]
    assert parse_groups("") == []
    assert feed_url("logementpmr.annonces") == (
        "https://www.facebook.com/groups/logementpmr.annonces/?sorting_setting=CHRONOLOGICAL"
    )


def test_group_key_rejects_garbage():
    with pytest.raises(ValueError):
        group_key("https://www.facebook.com/groups/")


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("https://www.facebook.com/groups/242242325809377/posts/1234567890123456/?__cft__[0]=AZ", ("242242325809377", "1234567890123456")),
        ("https://www.facebook.com/groups/logementpmr.annonces/permalink/2468013579246801/", ("logementpmr.annonces", "2468013579246801")),
        ("/groups/logementpmr.annonces/posts/pfbid02abcDEF/", ("logementpmr.annonces", "pfbid02abcDEF")),
        ("https://www.facebook.com/groups/232947036803405/?multi_permalinks=8642097531864209&x=1", ("232947036803405", "8642097531864209")),
        ("https://www.facebook.com/permalink.php?story_fbid=111&id=222", (None, "111")),
        ("https://www.facebook.com/groups/242242325809377/user/100004567891234/", (None, None)),
        (None, (None, None)),
    ],
)
def test_parse_permalink(href, expected):
    assert parse_permalink(href) == expected


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("3 h", "2026-11-07T15:00:00+00:00"),
        ("5 min", "2026-11-07T17:55:00+00:00"),
        ("2 j", "2026-11-05T18:00:00+00:00"),
        ("1 sem", "2026-10-31T18:00:00+00:00"),
        ("il y a 3 heures", "2026-11-07T15:00:00+00:00"),
        ("2d", "2026-11-05T18:00:00+00:00"),
        ("À l'instant", "2026-11-07T18:00:00+00:00"),
        ("Hier à 14:30", "2026-11-06T19:30:00+00:00"),
        ("Yesterday at 2:30 PM", "2026-11-06T19:30:00+00:00"),
        ("October 12 at 3:15 PM", "2026-10-12T20:15:00+00:00"),
        ("12 octobre à 15 h 15", "2026-10-12T20:15:00+00:00"),
        ("3 mars 2025", "2025-03-03T17:00:00+00:00"),
        ("15 décembre", "2025-12-15T17:00:00+00:00"),  # in the future this year -> last year
        ("Sponsorisé", None),
        (None, None),
    ],
)
def test_parse_timestamp(label, expected):
    assert parse_timestamp(label, NOW) == expected


def test_rental_post(posts):
    post = posts[0]
    assert post.post_id == "1234567890123456"
    assert post.group == "242242325809377"
    assert post.url == "https://www.facebook.com/groups/242242325809377/posts/1234567890123456/"
    assert post.time_label == "3 h"
    assert post.published_at == "2026-11-07T15:00:00+00:00"
    assert post.text.startswith("🏠 4½ À LOUER — PLATEAU MONT-ROYAL 🏠")
    assert "1 450 $/mois, chauffé, éclairé." in post.text
    assert "514-555-0199" in post.text  # contact stays in the description
    assert "Voir plus" not in post.text
    assert post.photos == [
        "https://scontent.fyhu1-1.fna.fbcdn.net/v/t39.30808-6/450001111_1022_n.jpg?stp=dst-jpg_p526x296&_nc_cat=105&oh=00_AYA&oe=66A1",
        "https://scontent.fyhu1-1.fna.fbcdn.net/v/t39.30808-6/450001112_1023_n.jpg?stp=dst-jpg_s206x206&_nc_cat=105",
    ]


def test_nothing_from_the_poster_or_the_comments(posts):
    dumped = repr(posts)
    for private in ("Marie Tremblay", "100004567891234", "t39.30808-1", "Jean Untel", "438-555-0000", "comment_photo"):
        assert private not in dumped


def test_vanity_group_and_text_without_message_marker(posts):
    post = posts[1]
    assert (post.post_id, post.group) == ("2468013579246801", "logementpmr.annonces")
    assert post.url == "https://www.facebook.com/groups/logementpmr.annonces/posts/2468013579246801/"
    assert post.published_at == "2026-11-06T19:30:00+00:00"
    assert post.text.startswith("Sous-location de mon 3½")
    assert "Alex Gagnon" not in post.text
    assert post.photos == ["https://scontent.fyhu1-2.fna.fbcdn.net/v/t39.30808-6/sublet_photo_1_n.jpg?_nc_cat=1"]


def test_id_from_photo_set_and_time_from_abbr(posts):
    post = posts[2]
    assert post.post_id == "1357913579135791"
    assert post.group == "242242325809377"  # the feed being scrolled
    assert post.published_at == datetime.fromtimestamp(1793836800, timezone.utc).isoformat()
    assert post.text.startswith("Grand 5 1/2 à louer")


def test_multi_permalinks(posts):
    post = posts[3]
    assert (post.post_id, post.group) == ("8642097531864209", "232947036803405")
    assert post.published_at == "2026-10-12T20:15:00+00:00"
    assert post.text.startswith("Looking for someone to take over my lease 🔥: 1 bedroom in Mile End")
    assert post.photos == []  # emoji are not photos


def test_non_post_units_are_skipped(posts):
    assert posts[4] is None


# --- current markup: [aria-posinset] units, comments are the only role="article" -----------

UNITS_FIXTURE = Path(__file__).parent / "fixtures" / "facebook" / "group_feed_units.html"


@pytest.fixture(scope="module")
def unit_posts():
    units = split_articles(UNITS_FIXTURE.read_text(encoding="utf-8"))
    assert len(units) == 3  # the loading placeholder is skipped
    return [parse_article(html, group="242242325809377", now=NOW) for html in units]


def test_unit_post_takes_its_id_from_the_photo_set_and_ignores_the_comments(unit_posts):
    post = unit_posts[0]
    assert post.post_id == "29825807217026163"
    assert post.url == "https://www.facebook.com/groups/242242325809377/posts/29825807217026163/"
    assert post.text.startswith("*2093 Rue De Bordeaux*\n$1899\nSuperbe 4 1/2 meublé")
    assert "Voir plus" not in post.text
    assert len(post.photos) == 2
    for private in ("Jean Untel", "438-555-0000", "Encore disponible", "Marie Tremblay"):
        assert private not in repr(post)


def test_unit_post_without_photo_takes_its_id_from_a_comment_link(unit_posts):
    post = unit_posts[1]
    assert (post.post_id, post.group) == ("29824949407111944", "242242325809377")
    assert post.text.startswith("Sous-location de mon 3½ à Rosemont")
    assert "Intéressé" not in post.text


def test_unit_post_without_any_id_is_skipped(unit_posts):
    assert unit_posts[2] is None


def test_unit_post_dated_from_the_hovered_tooltip():
    html = split_articles(UNITS_FIXTURE.read_text(encoding="utf-8"))[0]
    html = html.replace("<div aria-posinset=\"1\"", '<div data-griffon-time="Dimanche 8 novembre 2026 à 18:25" aria-posinset="1"', 1)
    post = parse_article(html, group="242242325809377", now=NOW)
    assert post.time_label == "Dimanche 8 novembre 2026 à 18:25"
    assert post.published_at == "2026-11-08T23:25:00+00:00"


def test_unit_post_without_tooltip_stays_undated(unit_posts):
    assert unit_posts[0].published_at is None
