"""Batched post classification and field extraction through OpenRouter, with few tokens.

- ~25 posts per call, each cut to ~600 characters, one compact system prompt;
- a strict JSON schema (`response_format: json_schema`) with one-or-two-letter keys, mapped
  back to readable names here (output tokens are the expensive ones); models that reject
  the schema get JSON mode plus the same validation;
- results cached by normalized-text hash (Store), so a post is never classified twice;
- a bad answer is retried once, then the batch is split in half (down to single posts);
- token usage is logged per run, and a hard per-run budget stops classification (the
  remaining posts are left for the next run, not guessed).

    OPENROUTER_API_KEY            required to classify (without it: keyword rules only)
    OPENROUTER_MODEL              default google/gemini-2.5-flash-lite
    FACEBOOK_LLM_BATCH_SIZE       posts per call (default 25)
    FACEBOOK_LLM_MAX_CHARS        characters of each post sent (default 600)
    FACEBOOK_LLM_TOKEN_BUDGET     max prompt+completion tokens per run (default 150000)
"""

import json
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import date

import httpx

from ..normalize import parse_number

API_URL = "https://openrouter.ai/api/v1/chat/completions"
# $0.10 / M input, $0.40 / M output tokens, structured outputs, good French (Nov. 2026).
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"

KINDS = ["rent", "sublet", "coloc", "seeking", "sale", "other"]
PERIODS = {"m": "monthly", "w": "weekly", "d": "daily", "t": "total"}
LAUNDRY = {"unit": "in_unit", "hookup": "hookups", "building": "building", "none": "none"}

# short key -> (readable name, JSON schema of the value)
_NUM = {"type": ["number", "null"]}
_BOOL = {"type": ["boolean", "null"]}
_STR = {"type": ["string", "null"]}
FIELDS: dict[str, tuple[str, dict]] = {
    "k": ("keep", {"type": "boolean"}),
    "t": ("kind", {"type": "string", "enum": KINDS}),
    "p": ("price", _NUM),
    "pp": ("price_period", {"type": ["string", "null"], "enum": [*PERIODS, None]}),
    "b": ("bedrooms", _NUM),
    "r": ("rooms_qc", _NUM),
    "ba": ("bathrooms", _NUM),
    "f": ("furnished", _BOOL),
    "pe": ("pets_allowed", _BOOL),
    "a": ("available_date", _STR),
    "e": ("sublet_end_date", _STR),
    "ad": ("address", _STR),
    "n": ("neighborhood", _STR),
    "c": ("city", _STR),
    "h": ("heating_included", _BOOL),
    "el": ("electricity_included", _BOOL),
    "pk": ("parking", _BOOL),
    "l": ("laundry", {"type": ["string", "null"], "enum": [*LAUNDRY, None]}),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "r": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"i": {"type": "integer"}, **{k: s for k, (_, s) in FIELDS.items()}},
                "required": ["i", *FIELDS],
                "additionalProperties": False,
            },
        }
    },
    "required": ["r"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Posts from Montreal/Quebec housing Facebook groups (FR/EN). Return {"r":[one object per post]}, i = post number.
k: true only if the poster OFFERS a whole unit for rent, or a sublet / lease transfer. False for rooms/colocation, people looking for a place, sales, anything else.
t: rent|sublet (sous-location, lease transfer, cession de bail)|coloc (room, roommate)|seeking|sale|other.
Only what the post states, else null: p rent CAD; pp m|w|d|t(total for the stay); b bedrooms; r Quebec room count (4½->4, studio 1½->1); ba bathrooms; f furnished; pe pets allowed; a available date YYYY-MM-DD; e sublet end YYYY-MM-DD; ad civic address or intersection ("Saint-Denis / Rachel"); n neighbourhood; c city; h heating included; el electricity included; pk parking; l laundry unit|hookup|building|none. Today: {today}."""


class ParseError(ValueError):
    pass


class LlmStopped(RuntimeError):
    """Stop classifying for this run: token budget spent, key refused, model unknown..."""


def _strip_fences(content: str) -> str:
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content)
    return content


def _coerce(name: str, value):
    if value is None or value == "":
        return None
    spec = next(s for _, (n, s) in FIELDS.items() if n == name)
    types = spec["type"] if isinstance(spec["type"], list) else [spec["type"]]
    if "number" in types:
        if isinstance(value, bool):
            return None
        return float(value) if isinstance(value, (int, float)) else parse_number(str(value))
    if "boolean" in types:
        if isinstance(value, bool):
            return value
        folded = str(value).strip().lower()
        return True if folded in ("true", "yes", "oui", "1") else False if folded in ("false", "no", "non", "0") else None
    if "enum" in spec and value not in spec["enum"]:
        return None
    return str(value).strip() or None


def expand(item: dict) -> dict:
    """Short-key model answer -> readable, type-checked classification."""
    out = {name: _coerce(name, item.get(short)) for short, (name, _) in FIELDS.items()}
    if out["kind"] not in KINDS:
        out["kind"] = "other"
    out["keep"] = bool(out["keep"]) and out["kind"] in ("rent", "sublet")
    out["price_period"] = PERIODS.get(out["price_period"])
    out["laundry"] = LAUNDRY.get(out["laundry"])
    return out


def parse_response(content: str | None, size: int) -> dict[int, dict]:
    """Model message content -> {post number: classification}. Raises ParseError when the
    answer isn't the expected JSON or misses posts."""
    if not content:
        raise ParseError("empty answer")
    try:
        body = json.loads(_strip_fences(content))
    except ValueError as e:
        raise ParseError(f"not JSON: {e}") from e
    items = body.get("r") if isinstance(body, dict) else body if isinstance(body, list) else None
    if not isinstance(items, list):
        raise ParseError("no 'r' array")
    out: dict[int, dict] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        try:
            i = int(item.get("i"))
        except (TypeError, ValueError):
            continue
        if 0 <= i < size and "k" in item and "t" in item:
            out[i] = expand(item)
    if len(out) < size:
        raise ParseError(f"answers for {len(out)}/{size} posts")
    return out


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except ValueError:
        return default


class Classifier:
    def __init__(
        self,
        api_key: str,
        *,
        model: str | None = None,
        client: httpx.Client | None = None,
        batch_size: int | None = None,
        max_chars: int | None = None,
        token_budget: int | None = None,
        sleep: Callable[[float], None] = time.sleep,
        today: date | None = None,
    ):
        self.model = model or os.getenv("OPENROUTER_MODEL") or DEFAULT_MODEL
        self.batch_size = batch_size or _env_int("FACEBOOK_LLM_BATCH_SIZE", 25)
        self.max_chars = max_chars or _env_int("FACEBOOK_LLM_MAX_CHARS", 600)
        self.token_budget = token_budget or _env_int("FACEBOOK_LLM_TOKEN_BUDGET", 150_000)
        self._client = client or httpx.Client(timeout=90)
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/griffon",
            "X-Title": "Griffon",
        }
        self._sleep = sleep
        self._system = SYSTEM_PROMPT.replace("{today}", (today or date.today()).isoformat())
        self._json_schema = True
        self.calls = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.cost = 0.0

    @property
    def tokens_used(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def usage_line(self) -> str:
        cost = f", ${self.cost:.4f}" if self.cost else ""
        return (f"{self.calls} calls, {self.prompt_tokens} prompt + {self.completion_tokens} completion tokens"
                f"{cost} ({self.model})")

    # --- HTTP ---------------------------------------------------------------------

    def _user_message(self, texts: list[str]) -> str:
        lines = []
        for i, text in enumerate(texts):
            text = re.sub(r"\s+", " ", text).strip()
            if len(text) > self.max_chars:
                text = text[: self.max_chars] + "…"
            lines.append(f"#{i} {text}")
        return "\n".join(lines)

    def _request(self, texts: list[str]) -> str | None:
        user = self._user_message(texts)
        max_tokens = 60 + 110 * len(texts)
        estimate = (len(self._system) + len(user)) // 3 + max_tokens
        if self.tokens_used + estimate > self.token_budget:
            raise LlmStopped(f"token budget {self.token_budget} reached ({self.tokens_used} used)")
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": self._system}, {"role": "user", "content": user}],
            "temperature": 0,
            "max_tokens": max_tokens,
            "usage": {"include": True},
            "response_format": (
                {"type": "json_schema", "json_schema": {"name": "posts", "strict": True, "schema": SCHEMA}}
                if self._json_schema
                else {"type": "json_object"}
            ),
        }
        for attempt in range(4):
            resp = self._client.post(API_URL, json=body, headers=self._headers)
            if resp.status_code == 400 and self._json_schema and "response_format" in resp.text.lower():
                print(f"[facebook] {self.model} rejects json_schema, using JSON mode", file=sys.stderr)
                self._json_schema = False
                body["response_format"] = {"type": "json_object"}
                continue
            if resp.status_code in (408, 429, 500, 502, 503, 504) and attempt < 3:
                self._sleep(5 * 3**attempt)
                continue
            break
        if 400 <= resp.status_code < 500:
            # Bad key, no credits, unknown model...: retrying or splitting won't help.
            raise LlmStopped(f"OpenRouter HTTP {resp.status_code}: {resp.text[:200]}")
        resp.raise_for_status()
        data = resp.json()
        self.calls += 1
        usage = data.get("usage") or {}
        self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
        self.completion_tokens += int(usage.get("completion_tokens") or 0)
        self.cost += float(usage.get("cost") or 0)
        choices = data.get("choices") or [{}]
        return (choices[0].get("message") or {}).get("content")

    # --- batching -----------------------------------------------------------------

    def _classify_batch(self, texts: list[str], offset: int) -> None:
        for _attempt in range(2):
            try:
                answers = parse_response(self._request(texts), len(texts))
            except (ParseError, httpx.HTTPError, ValueError) as e:
                print(f"[facebook] LLM answer unusable for {len(texts)} posts: {e}", file=sys.stderr)
                continue
            for i in range(len(texts)):
                self.results[offset + i] = answers[i]
            return
        if len(texts) == 1:
            self.results[offset] = None
            return
        half = len(texts) // 2
        self._classify_batch(texts[:half], offset)
        self._classify_batch(texts[half:], offset + half)

    def classify(self, texts: list[str]) -> dict[int, dict | None]:
        """{index: classification} (None when the model never gave a usable answer).
        Raises LlmStopped mid-way; what was classified before is in `results`."""
        self.results: dict[int, dict | None] = {}
        for start in range(0, len(texts), self.batch_size):
            self._classify_batch(texts[start:start + self.batch_size], start)
        return self.results

    def close(self) -> None:
        self._client.close()
