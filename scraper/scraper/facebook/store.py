"""Small JSON state kept on the worker volume (FACEBOOK_CACHE, next to the session file).

    {"version": 2,                                              # see VERSION
     "seen":   {"<group>": {"<post id>": "<first seen ISO>"}},   # where to stop scrolling
     "hashes": {"<text hash>": "<post id>"},                     # reposts across groups
     "llm":    {"<text hash>": {...classification...}}}          # never classify twice

Entries older than `keep_days` are pruned on save so the file stays small (a few hundred KB).
Writes are atomic (temp file + rename): a container killed mid-write keeps the old state.
"""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path


def atomic_write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


# Bumped when the extraction changes what a post id or a post text is: "seen" and "hashes" of
# an older version are dropped (they could stop the scroll at posts never really read), the LLM
# answers, keyed by text, are kept. 2: posts read from the [aria-posinset] feed units; version 1
# read the comments' articles instead.
VERSION = 2


class Store:
    def __init__(self, path: str | Path | None, *, keep_days: int = 90):
        self.path = Path(path) if path else None
        self.keep_days = keep_days
        self.data: dict = {"version": VERSION, "seen": {}, "hashes": {}, "llm": {}}
        if self.path and self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                current = loaded.get("version", 1) == VERSION
                for key in ("seen", "hashes", "llm") if current else ("llm",):
                    if isinstance(loaded.get(key), dict):
                        self.data[key] = loaded[key]
            except (OSError, ValueError):
                pass  # a corrupt cache only costs a few re-classifications

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    # seen posts -------------------------------------------------------------------

    def seen(self, group: str, post_id: str) -> bool:
        return post_id in self.data["seen"].get(group, {})

    def seen_anywhere(self, post_id: str) -> bool:
        """A post shared into several groups keeps its id: one listing, not one per group."""
        return any(post_id in posts for posts in self.data["seen"].values())

    def mark_seen(self, group: str, post_id: str) -> None:
        self.data["seen"].setdefault(group, {}).setdefault(post_id, self._now())

    # reposts ----------------------------------------------------------------------

    def hash_owner(self, text_hash: str) -> str | None:
        owner = self.data["hashes"].get(text_hash)
        return owner[0] if isinstance(owner, list) else owner

    def remember_hash(self, text_hash: str, post_id: str) -> None:
        self.data["hashes"].setdefault(text_hash, [post_id, self._now()])

    # LLM cache --------------------------------------------------------------------

    def classification(self, text_hash: str) -> dict | None:
        hit = self.data["llm"].get(text_hash)
        return hit.get("r") if isinstance(hit, dict) else None

    def remember_classification(self, text_hash: str, result: dict) -> None:
        self.data["llm"][text_hash] = {"r": result, "at": self._now()}

    # persistence ------------------------------------------------------------------

    def prune(self) -> None:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=self.keep_days)).isoformat()
        for group, posts in self.data["seen"].items():
            self.data["seen"][group] = {k: v for k, v in posts.items() if v >= cutoff}
        self.data["hashes"] = {
            k: v for k, v in self.data["hashes"].items() if not isinstance(v, list) or v[1] >= cutoff
        }
        self.data["llm"] = {k: v for k, v in self.data["llm"].items() if v.get("at", "") >= cutoff}

    def save(self) -> None:
        if self.path:
            self.prune()
            atomic_write_json(self.path, self.data)
