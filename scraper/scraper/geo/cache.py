import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class DiskCache:
    """Tiny SQLite-backed JSON key/value cache with optional TTL.

    Used for geocoding and Overpass/OSRM responses so re-running a scrape (or
    enriching many units of the same building) doesn't hit public APIs again.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS kv (ns TEXT, k TEXT, v TEXT, ts REAL, PRIMARY KEY (ns, k))"
        )
        self._conn.commit()

    def get(self, ns: str, key: str, *, ttl_s: float | None = None) -> Any | None:
        with self._lock:
            row = self._conn.execute("SELECT v, ts FROM kv WHERE ns = ? AND k = ?", (ns, key)).fetchone()
        if not row:
            return None
        value, ts = row
        if ttl_s is not None and time.time() - ts > ttl_s:
            return None
        return json.loads(value)

    def set(self, ns: str, key: str, value: Any) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO kv (ns, k, v, ts) VALUES (?, ?, ?, ?)",
                (ns, key, json.dumps(value, ensure_ascii=False), time.time()),
            )
            self._conn.commit()
