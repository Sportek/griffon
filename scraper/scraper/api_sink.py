"""Sends listings to the listings-api GraphQL service (../listings-api).

Drop-in alternative to JsonlSink: same write()/len() interface, but every listing
seen is sent -- not only new ones -- so the API can track lastSeenAt / price changes.

    sink = ApiSink()                       # LISTINGS_API_URL or http://localhost:8080/graphql
    with sink.run("duproprio"):            # optional: journals the run in the API
        sink.write(listing)                # True if the API had never seen it

Set LISTINGS_API_KEY when the API is started with API_KEY.

Backfill an existing JSONL file:

    python -m scraper.api_sink data/listings.jsonl
"""

import argparse
import json
import os
import time
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path

import httpx

from .models import Listing

DEFAULT_URL = "http://localhost:8080/graphql"

UPSERT_MUTATION = """
mutation($listings: [ListingInput!]!, $runId: ID) {
  upsertListings(listings: $listings, runId: $runId) {
    received created updated unchanged rejected
    results { source externalId status error }
  }
}
"""

START_RUN_MUTATION = """
mutation($source: String!) { startIngestionRun(source: $source) { id } }
"""

FINISH_RUN_MUTATION = """
mutation($id: ID!, $status: IngestionRunStatus!, $error: String, $markUnseenInactive: Boolean) {
  finishIngestionRun(id: $id, status: $status, error: $error, markUnseenInactive: $markUnseenInactive) {
    status received created updated unchanged rejected deactivated
  }
}
"""

CLAIM_RUN_MUTATION = """
mutation($worker: String!, $sources: [String!]) {
  claimIngestionRun(worker: $worker, sources: $sources) {
    id source params { maxPages areas limit enrich markUnseenInactive }
  }
}
"""

HEARTBEAT_MUTATION = "mutation($id: ID!) { heartbeatIngestionRun(id: $id) }"

COUNT_QUERY = "{ listings(size: 1) { totalElements } }"

# Python field -> GraphQL ListingInput field. Explicit so that a new field on the
# Listing model does not break ingestion before the API schema knows about it.
_FIELDS = {
    "source": "source",
    "external_id": "externalId",
    "url": "url",
    "title": "title",
    "listing_type": "listingType",
    "property_type": "propertyType",
    "price": "price",
    "price_currency": "priceCurrency",
    "price_period": "pricePeriod",
    "address": "address",
    "neighborhood": "neighborhood",
    "city": "city",
    "region": "region",
    "postal_code": "postalCode",
    "country": "country",
    "latitude": "latitude",
    "longitude": "longitude",
    "location_precision": "locationPrecision",
    "bedrooms": "bedrooms",
    "bathrooms": "bathrooms",
    "area_sqft": "areaSqft",
    "rooms_qc": "roomsQc",
    "year_built": "yearBuilt",
    "parking_spots": "parkingSpots",
    "furnished": "furnished",
    "pets_allowed": "petsAllowed",
    "smoking_allowed": "smokingAllowed",
    "available_date": "availableDate",
    "lease_term": "leaseTerm",
    "amenities": "amenities",
    "utilities_included": "utilitiesIncluded",
    "photos": "photos",
    "description": "description",
    "contact_name": "contactName",
    "agency_name": "agencyName",
    "published_at": "publishedAt",
    "extra": "extra",
    "proximity": "proximity",
    "scraped_at": "scrapedAt",
}
_ENUM_FIELDS = {"listing_type", "price_period"}


def to_input(row: dict) -> dict:
    """Maps a Listing.model_dump(mode="json") (or a JSONL row) to a GraphQL ListingInput."""
    out = {}
    for py_name, gql_name in _FIELDS.items():
        value = row.get(py_name)
        if value is None:
            continue
        out[gql_name] = value.upper() if py_name in _ENUM_FIELDS else value
    return out


class ApiError(RuntimeError):
    pass


# While the API is redeployed, the proxy in front of it answers 404/502/503 for a minute
# or so. A scrape takes hours: it waits the restart out instead of failing the whole run.
# Retrying is safe, since upserts are idempotent.
TRANSIENT_STATUSES = {404, 502, 503, 504}
RETRY_DELAYS_S = (2, 5, 10, 20, 30, 60, 60)


class ApiSink:
    def __init__(
        self,
        url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 30,
        batch_size: int = 200,
        retry_delays: tuple[float, ...] = RETRY_DELAYS_S,
    ):
        self.url = url or os.getenv("LISTINGS_API_URL", DEFAULT_URL)
        self.batch_size = batch_size
        api_key = api_key or os.getenv("LISTINGS_API_KEY")
        headers = {"X-API-Key": api_key} if api_key else {}
        self._client = httpx.Client(timeout=timeout, headers=headers)
        self._run_id: str | None = None
        self._retry_delays = retry_delays

    def _post(self, payload: dict) -> httpx.Response:
        for delay in (*self._retry_delays, None):
            try:
                resp = self._client.post(self.url, json=payload)
                if resp.status_code not in TRANSIENT_STATUSES or delay is None:
                    return resp
                reason = f"HTTP {resp.status_code}"
            except httpx.TransportError as e:
                if delay is None:
                    raise
                reason = repr(e)
            print(f"[api] {reason}, retrying in {delay:g} s")
            time.sleep(delay)
        raise AssertionError("unreachable")

    def _execute(self, query: str, variables: dict | None = None) -> dict:
        resp = self._post({"query": query, "variables": variables or {}})
        resp.raise_for_status()
        body = resp.json()
        if body.get("errors"):
            raise ApiError(body["errors"])
        return body["data"]

    def upsert(self, rows: list[dict]) -> dict:
        """Sends one batch of raw rows; returns the IngestReport."""
        variables = {"listings": [to_input(r) for r in rows], "runId": self._run_id}
        report = self._execute(UPSERT_MUTATION, variables)["upsertListings"]
        for result in report["results"]:
            if result["status"] == "REJECTED":
                print(f"[api] rejected {result['source']}:{result['externalId']}: {result['error']}")
        return report

    def write(self, listing: Listing) -> bool:
        """Sends the listing. Returns True if it was new to the API."""
        return self.upsert([listing.model_dump(mode="json")])["created"] == 1

    def write_many(self, rows: Iterable[dict]) -> dict:
        """Sends rows in batches; returns summed counters."""
        totals = {"received": 0, "created": 0, "updated": 0, "unchanged": 0, "rejected": 0}
        batch: list[dict] = []

        def flush() -> None:
            report = self.upsert(batch)
            for k in totals:
                totals[k] += report[k]
            batch.clear()

        for row in rows:
            batch.append(row)
            if len(batch) >= self.batch_size:
                flush()
        if batch:
            flush()
        return totals

    @contextmanager
    def run(self, source: str, *, mark_unseen_inactive: bool = False) -> Iterator[str]:
        """Journals the writes inside the block as one ingestion run of `source`.

        mark_unseen_inactive: on success, the API flags this source's listings that were
        not sent during the run as inactive. Only for complete scrapes (no --max-pages/--limit).
        """
        run_id = self._execute(START_RUN_MUTATION, {"source": source})["startIngestionRun"]["id"]
        with self.attach(run_id, source=source, mark_unseen_inactive=mark_unseen_inactive):
            yield run_id

    @contextmanager
    def attach(self, run_id: str, *, source: str, mark_unseen_inactive: bool = False) -> Iterator[str]:
        """Sends the writes inside the block to an existing RUNNING run (e.g. one a worker
        claimed), then finishes it: SUCCEEDED, or FAILED with the exception if the block raises."""
        self._run_id = run_id
        status, error = "SUCCEEDED", None
        try:
            yield run_id
        except BaseException as e:
            status, error = "FAILED", str(e) or repr(e)
            raise
        finally:
            self._run_id = None
            summary = self._execute(
                FINISH_RUN_MUTATION,
                {"id": run_id, "status": status, "error": error, "markUnseenInactive": mark_unseen_inactive},
            )["finishIngestionRun"]
            print(f"[api] run {source}: {summary}")

    def claim(self, worker: str, sources: list[str] | None = None) -> dict | None:
        """Takes the oldest queued run for these sources, or None when there is nothing to do."""
        return self._execute(CLAIM_RUN_MUTATION, {"worker": worker, "sources": sources})["claimIngestionRun"]

    def heartbeat(self, run_id: str) -> bool:
        return self._execute(HEARTBEAT_MUTATION, {"id": run_id})["heartbeatIngestionRun"]

    def __len__(self) -> int:
        return self._execute(COUNT_QUERY)["listings"]["totalElements"]

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "ApiSink":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _read_jsonl(path: Path) -> Iterable[dict]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            if line.strip():
                yield json.loads(line)


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill a listings JSONL file into listings-api")
    parser.add_argument("jsonl", type=Path)
    parser.add_argument("--url", default=None, help=f"GraphQL endpoint (default: $LISTINGS_API_URL or {DEFAULT_URL})")
    parser.add_argument("--batch-size", type=int, default=200)
    args = parser.parse_args()

    with ApiSink(args.url, batch_size=args.batch_size) as sink:
        totals = sink.write_many(_read_jsonl(args.jsonl))
        print(f"[api] {totals}. Total in API: {len(sink)}")


if __name__ == "__main__":
    main()
