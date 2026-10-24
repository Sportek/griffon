import json
import sys
from pathlib import Path

from .models import Listing


class JsonlSink:
    """Writes listings to a JSONL file, deduping by (source, external_id) across runs."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._seen: set[str] = set()
        if self.path.exists():
            with self.path.open(encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    row = json.loads(line)
                    self._seen.add(f"{row['source']}:{row['external_id']}")

    def write(self, listing: Listing) -> bool:
        """Appends the listing if new. Returns True if it was written."""
        if listing.dedupe_key in self._seen:
            return False
        self._seen.add(listing.dedupe_key)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(listing.model_dump_json() + "\n")
        return True

    def __len__(self) -> int:
        return len(self._seen)


class StdoutSink:
    """Streams one JSON document per line to stdout, for piping into another app."""

    def __init__(self):
        self._seen: set[str] = set()

    def write(self, listing: Listing) -> bool:
        if listing.dedupe_key in self._seen:
            return False
        self._seen.add(listing.dedupe_key)
        sys.stdout.write(listing.model_dump_json() + "\n")
        sys.stdout.flush()
        return True

    def __len__(self) -> int:
        return len(self._seen)
