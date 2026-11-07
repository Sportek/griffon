import json
from datetime import date

import httpx
import pytest

from scraper.facebook.llm import FIELDS, SCHEMA, Classifier, LlmStopped, ParseError, expand, parse_response


def answer(i, **over):
    item = {"i": i, **{k: None for k in FIELDS}, "k": True, "t": "rent", "p": 1450, "pp": "m", "r": 4}
    item.update(over)
    return item


def completion(items, *, usage=(100, 50), content=None):
    body = {
        "choices": [{"message": {"content": content if content is not None else json.dumps({"r": items})}}],
        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "cost": 0.0001},
    }
    return httpx.Response(200, json=body)


class FakeRouter:
    """Mock OpenRouter: `reply(posts)` builds the answer from the posts of each request."""

    def __init__(self, reply):
        self.reply = reply
        self.requests = []

    def __call__(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        posts = [line for line in body["messages"][1]["content"].split("\n") if line.startswith("#")]
        return self.reply(posts, body)


def classifier(router, **kw):
    client = httpx.Client(transport=httpx.MockTransport(router))
    return Classifier("sk-test", model="test/model", client=client, sleep=lambda _s: None, today=date(2026, 11, 7), **kw)


def test_schema_uses_short_keys_and_is_strict():
    item = SCHEMA["properties"]["r"]["items"]
    assert item["additionalProperties"] is False
    assert set(item["required"]) == {"i", *FIELDS}
    assert all(len(k) <= 2 for k in item["properties"])


def test_expand_maps_short_keys_and_types():
    out = expand({"i": 0, "k": True, "t": "sublet", "p": "1 100 $", "pp": "m", "b": 1, "r": "3", "f": "oui",
                  "a": "2026-12-01", "e": "2027-04-30", "ad": "Saint-Denis / Rachel", "h": True, "l": "unit"})
    assert out["keep"] is True and out["kind"] == "sublet"
    assert out["price"] == 1100.0 and out["price_period"] == "monthly"
    assert out["rooms_qc"] == 3.0 and out["bedrooms"] == 1.0
    assert out["furnished"] is True
    assert out["sublet_end_date"] == "2027-04-30"
    assert out["address"] == "Saint-Denis / Rachel"
    assert out["laundry"] == "in_unit"
    assert out["pets_allowed"] is None


def test_expand_never_keeps_a_coloc_even_if_the_model_says_keep():
    assert expand({"k": True, "t": "coloc"})["keep"] is False
    assert expand({"k": True, "t": "nonsense"})["kind"] == "other"


@pytest.mark.parametrize(
    "content",
    ["", "not json", '{"x": []}', json.dumps({"r": [answer(0)]})],  # last one misses post #1
)
def test_parse_errors(content):
    with pytest.raises(ParseError):
        parse_response(content, 2)


def test_parse_accepts_fenced_json_and_bare_lists():
    fenced = "```json\n" + json.dumps({"r": [answer(1), answer(0)]}) + "\n```"
    assert set(parse_response(fenced, 2)) == {0, 1}
    assert parse_response(json.dumps([answer(0)]), 1)[0]["price"] == 1450


def test_batches_truncation_and_usage():
    router = FakeRouter(lambda posts, _b: completion([answer(i) for i in range(len(posts))]))
    c = classifier(router, batch_size=3, max_chars=50)
    texts = [f"post {n} " + "x" * 200 for n in range(7)]
    results = c.classify(texts)
    assert len(router.requests) == 3  # 3 + 3 + 1
    assert all(results[i]["keep"] for i in range(7))
    first = router.requests[0]
    assert first["model"] == "test/model"
    assert first["temperature"] == 0
    assert first["response_format"]["type"] == "json_schema"
    assert "Today: 2026-11-07" in first["messages"][0]["content"]
    sent = first["messages"][1]["content"].split("\n")[0]
    assert sent.startswith("#0 post 0 ") and len(sent) <= len("#0 ") + 50 + 1
    assert (c.calls, c.prompt_tokens, c.completion_tokens) == (3, 300, 150)
    assert "3 calls" in c.usage_line()


def test_bad_batch_is_retried_then_split_in_half():
    # Any request with more than 2 posts gets garbage; smaller ones succeed.
    def reply(posts, _b):
        if len(posts) > 2:
            return completion(None, content="Sorry, I can't")
        return completion([answer(i, p=1000 + int(p.split()[2])) for i, p in enumerate(posts)])

    router = FakeRouter(reply)
    c = classifier(router, batch_size=8)
    results = c.classify([f"post {n}" for n in range(8)])
    sizes = [len([l for l in r["messages"][1]["content"].split("\n")]) for r in router.requests]
    # 8 (x2) -> 4 (x2) -> 4 (x2) -> 2,2,2,2
    assert sizes == [8, 8, 4, 4, 2, 2, 4, 4, 2, 2]
    assert [results[i]["price"] for i in range(8)] == [1000.0 + n for n in range(8)]


def test_single_post_that_never_parses_is_none():
    def reply(posts, _b):
        if any("cursed" in p for p in posts):
            return completion(None, content="{")
        return completion([answer(i) for i in range(len(posts))])

    c = classifier(FakeRouter(reply), batch_size=4)
    results = c.classify(["a", "b", "cursed", "d"])
    assert results[2] is None
    assert all(results[i] for i in (0, 1, 3))


def test_token_budget_stops_and_keeps_partial_results():
    router = FakeRouter(lambda posts, _b: completion([answer(i) for i in range(len(posts))], usage=(900, 300)))
    c = classifier(router, batch_size=2, token_budget=1500)
    with pytest.raises(LlmStopped):
        c.classify(["a", "b", "c", "d", "e", "f"])
    assert set(c.results) == {0, 1}
    assert len(router.requests) == 1


def test_model_without_json_schema_falls_back_to_json_mode():
    def reply(posts, body):
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": {"message": "response_format json_schema not supported"}})
        return completion([answer(i) for i in range(len(posts))])

    router = FakeRouter(reply)
    c = classifier(router)
    assert c.classify(["a", "b"])[1]["keep"]
    assert [r["response_format"]["type"] for r in router.requests] == ["json_schema", "json_object"]
    c.classify(["c"])
    assert router.requests[-1]["response_format"]["type"] == "json_object"


def test_rate_limits_are_retried_and_bad_keys_stop():
    calls = iter([httpx.Response(429), httpx.Response(503), None])

    def reply(posts, _b):
        r = next(calls)
        return r or completion([answer(i) for i in range(len(posts))])

    assert classifier(FakeRouter(reply)).classify(["a"])[0]["keep"]

    unauthorized = FakeRouter(lambda _p, _b: httpx.Response(401, json={"error": "no"}))
    with pytest.raises(LlmStopped):
        classifier(unauthorized).classify(["a", "b"])
    assert len(unauthorized.requests) == 1  # no retry, no split
