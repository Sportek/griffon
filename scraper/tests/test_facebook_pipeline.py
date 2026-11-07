import base64
import json
from datetime import date

import httpx
import pytest

from scraper.api_sink import to_input
from scraper.facebook import session
from scraper.facebook.extract import Post
from scraper.facebook.llm import FIELDS, Classifier
from scraper.facebook.mapping import to_listing
from scraper.facebook.prefilter import text_hash
from scraper.facebook.store import Store
from scraper.sources.facebook import process

RENT = "4½ à louer sur le Plateau, 1450$/mois, chauffé, rue Saint-Denis coin Rachel. 514-555-0199"
SUBLET = "Sous-location de mon 3½ du 1er décembre au 30 avril, 1100$ par mois, meublé"
COLOC = "Chambre à louer dans un grand 6½ à Rosemont, 700$ tout inclus"
SEEKING_LOOKALIKE = "Bonjour à tous, petit 3½ disponible à Verdun pour janvier, 1200$/mois"  # LLM says seeking


def post(pid, text, photos=()):
    return Post(post_id=pid, group="g1", url=f"https://www.facebook.com/groups/g1/posts/{pid}/", text=text,
                published_at="2026-11-07T15:00:00+00:00", photos=list(photos))


SUBLET_CLASS = {
    "keep": True, "kind": "sublet", "price": 1100.0, "price_period": "monthly", "bedrooms": 1.0, "rooms_qc": 3.0,
    "bathrooms": 1.0, "furnished": True, "pets_allowed": False, "available_date": "2026-12-01",
    "sublet_end_date": "2027-04-30", "address": None, "neighborhood": "Plateau-Mont-Royal", "city": "Montréal",
    "heating_included": True, "electricity_included": True, "parking": False, "laundry": "building",
    "_model": "test/model",
}


def test_sublet_mapping():
    listing = to_listing(post("1", SUBLET, ["https://scontent.x/p.jpg"]), SUBLET_CLASS, group="g1")
    assert listing.source == "facebook" and listing.external_id == "1"
    assert listing.url == "https://www.facebook.com/groups/g1/posts/1/"
    assert listing.listing_type == "rent"
    assert listing.extra["is_sublet"] is True
    assert listing.extra["sublet_end_date"] == "2027-04-30"
    assert listing.extra["classifier"] == "test/model"
    assert listing.lease_term == "Sous-location"
    assert (listing.price, listing.rooms_qc, listing.bedrooms) == (1100.0, 3.0, 1.0)
    assert listing.available_date == "2026-12-01"
    assert listing.utilities_included == ["Heat", "Electricity"]
    assert listing.amenities == ["Laundry (in building)"]
    assert listing.photos == ["https://scontent.x/p.jpg"]
    assert listing.description == SUBLET
    assert listing.contact_name is None
    assert listing.property_type == "apartment"
    assert listing.region == "QC"
    # And it goes through the API mapping as is.
    sent = to_input(listing.model_dump(mode="json"))
    assert sent["listingType"] == "RENT" and sent["extra"]["is_sublet"] is True


def test_rules_only_mapping():
    listing = to_listing(post("2", RENT), None, group="g1")
    assert listing.price == 1450.0
    assert listing.rooms_qc == 4.0
    assert listing.city == "Montréal"
    assert listing.extra == {"group": "g1", "classifier": "rules"}
    assert "514-555-0199" in listing.description  # contact kept in the text only
    assert listing.title.startswith("4½ à louer sur le Plateau")
    sublet = to_listing(post("3", SUBLET), None, group="g1")
    assert sublet.extra["is_sublet"] is True


def test_weekly_price_is_not_called_monthly():
    listing = to_listing(post("4", SUBLET), {**SUBLET_CLASS, "price": 350.0, "price_period": "weekly"}, group="g1")
    assert listing.price_period == "unknown"
    assert listing.extra["price_period_raw"] == "weekly"


def _router(kinds):
    """Mock OpenRouter answering with the kind registered for each post text."""
    requests = []

    def handler(request):
        body = json.loads(request.content)
        requests.append(body)
        lines = [l for l in body["messages"][1]["content"].split("\n") if l.startswith("#")]
        items = []
        for i, line in enumerate(lines):
            kind = next(k for snippet, k in kinds.items() if snippet in line)
            items.append({"i": i, **{k: None for k in FIELDS}, "k": kind in ("rent", "sublet"), "t": kind, "p": 999})
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"r": items})}}],
                                         "usage": {"prompt_tokens": 10, "completion_tokens": 5}})

    return handler, requests


def _classifier(handler):
    return Classifier("k", model="test/model", client=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=lambda _s: None, today=date(2026, 11, 7))


def test_process_dedupes_filters_classifies_and_caches(tmp_path):
    store = Store(tmp_path / "cache.json")
    handler, requests = _router({"Plateau": "rent", "Sous-location": "sublet", "Verdun": "seeking"})
    collected = [
        ("g1", post("1", RENT)),
        ("g2", post("2", RENT.upper() + "!!")),  # same post in another group
        ("g1", post("3", COLOC)),
        ("g1", post("4", SUBLET)),
        ("g1", post("5", SEEKING_LOOKALIKE)),
    ]
    listings = list(process(collected, store, _classifier(handler)))
    assert [l.external_id for l in listings] == ["1", "4"]
    assert listings[1].extra["is_sublet"] is True
    assert len(requests) == 1  # one batch, the coloc and the repost never reached the LLM
    assert len([l for l in requests[0]["messages"][1]["content"].split("\n")]) == 3
    for pid in ("1", "3", "4", "5"):
        assert store.seen("g1", pid)
    assert store.seen("g2", "2")
    store.save()

    # Next run: the classification survived, and the same post shared into another group
    # (same id) or reposted (same text) is not sent again.
    store2 = Store(tmp_path / "cache.json")
    assert store2.classification(text_hash(SUBLET))["kind"] == "sublet"
    again = list(process([("g3", post("4", SUBLET)), ("g3", post("40", SUBLET))], store2, _classifier(handler)))
    assert again == []
    assert len(requests) == 1


def test_cached_classification_is_not_requested_again(tmp_path):
    store = Store(tmp_path / "cache.json")
    store.remember_classification(text_hash(SUBLET), {**SUBLET_CLASS, "price": 1234.0})
    handler, requests = _router({})
    out = list(process([("g1", post("9", SUBLET))], store, _classifier(handler)))
    assert [l.price for l in out] == [1234.0]
    assert requests == []


def test_same_post_from_two_groups_in_one_run(tmp_path):
    out = list(process([("g1", post("1", RENT)), ("g2", post("1", RENT))], Store(tmp_path / "c.json"), None))
    assert len(out) == 1


def test_process_defers_posts_when_the_llm_stops(tmp_path):
    store = Store(tmp_path / "cache.json")
    refused = httpx.MockTransport(lambda r: httpx.Response(402, json={"error": "no credits"}))
    classifier = Classifier("k", client=httpx.Client(transport=refused), sleep=lambda _s: None)
    assert list(process([("g1", post("1", RENT))], store, classifier)) == []
    assert not store.seen("g1", "1")  # picked up again next run


def test_process_without_key_uses_the_rules(tmp_path):
    store = Store(tmp_path / "cache.json")
    out = list(process([("g1", post("1", RENT)), ("g1", post("3", COLOC))], store, None))
    assert [(l.external_id, l.price, l.extra["classifier"]) for l in out] == [("1", 1450.0, "rules")]


def _state(c_user=True):
    cookies = [{"name": "xs", "value": "1", "domain": ".facebook.com", "path": "/"}]
    if c_user:
        cookies.append({"name": "c_user", "value": "1000", "domain": ".facebook.com", "path": "/"})
    return {"cookies": cookies, "origins": [], "griffon": {"user_agent": "UA/1"}}


def test_session_load_and_expired(tmp_path, monkeypatch):
    monkeypatch.delenv("FACEBOOK_STORAGE_STATE_B64", raising=False)
    path = tmp_path / "state.json"
    with pytest.raises(session.SessionExpired, match="facebook_login"):
        session.load(path)
    path.write_text(json.dumps(_state()))
    state, ua = session.load(path)
    assert ua == "UA/1" and "griffon" not in state and len(state["cookies"]) == 2
    path.write_text(json.dumps(_state(c_user=False)))
    with pytest.raises(session.SessionExpired, match="session expired, re-run facebook_login"):
        session.load(path)


def test_session_bootstrap_from_env_only_when_it_changes(tmp_path, monkeypatch):
    path = tmp_path / "facebook" / "state.json"
    monkeypatch.setenv("FACEBOOK_STORAGE_STATE_B64", base64.b64encode(json.dumps(_state()).encode()).decode())
    session.load(path)
    assert path.exists()
    # The worker refreshed the cookies since: the same env value must not overwrite them.
    refreshed = _state()
    refreshed["cookies"][0]["value"] = "fresh"
    path.write_text(json.dumps(refreshed))
    session.load(path)
    assert json.loads(path.read_text())["cookies"][0]["value"] == "fresh"
    # A new login pasted in the env replaces the file.
    new_login = _state()
    new_login["cookies"][0]["value"] = "new"
    monkeypatch.setenv("FACEBOOK_STORAGE_STATE_B64", base64.b64encode(json.dumps(new_login).encode()).decode())
    session.load(path)
    assert json.loads(path.read_text())["cookies"][0]["value"] == "new"


@pytest.mark.parametrize(
    ("url", "head", "c_user", "expired"),
    [
        ("https://www.facebook.com/groups/1/?sorting_setting=CHRONOLOGICAL", "<html>", True, False),
        ("https://www.facebook.com/login/?next=%2Fgroups%2F1", "<html>", True, True),
        ("https://www.facebook.com/checkpoint/1501092823525282/", "<html>", True, True),
        ("https://www.facebook.com/two_step_verification/authentication/", "<html>", True, True),
        ("https://www.facebook.com/groups/1/", "<html>", False, True),
        ("https://www.facebook.com/groups/1/", '<form id="login_form">', True, True),
    ],
)
def test_check_page(url, head, c_user, expired):
    cookies = [{"name": "c_user"}] if c_user else []
    if expired:
        with pytest.raises(session.SessionExpired):
            session.check_page(url, head, cookies)
    else:
        session.check_page(url, head, cookies)


def test_session_expired_is_a_source_block():
    from scraper.polite import SourceBlocked

    assert issubclass(session.SessionExpired, SourceBlocked)


def test_store_prunes_old_entries(tmp_path):
    store = Store(tmp_path / "c.json", keep_days=30)
    store.mark_seen("g", "new")
    store.data["seen"]["g"]["old"] = "2020-01-01T00:00:00+00:00"
    store.data["llm"]["h"] = {"r": {}, "at": "2020-01-01T00:00:00+00:00"}
    store.save()
    reloaded = Store(tmp_path / "c.json")
    assert reloaded.seen("g", "new") and not reloaded.seen("g", "old")
    assert reloaded.classification("h") is None
