"""Long-running worker: executes the scrapes the API schedules.

The API owns the schedule (scrapeSchedules / triggerScrape) and queues runs; this worker
polls `claimIngestionRun`, runs the source with the run's params, streams listings into
the run, keeps it alive with heartbeats and finishes it (FAILED with the reason if the
source is blocked or crashes). It only ever calls out to the API, so it can sit behind a
home NAT (e.g. on a residential IP, which sites block far less than datacenter IPs).

    LISTINGS_API_URL=https://api.example/graphql LISTINGS_API_KEY=... python -m scraper.worker

Environment:
    WORKER_NAME            shown in ingestionRuns.worker (default: hostname)
    WORKER_SOURCES         comma-separated sources this worker accepts (default: all)
    WORKER_POLL_SECONDS    wait between two claims when idle (default 60)
    WORKER_HEARTBEAT_SECONDS                              (default 60)
"""

import argparse
import os
import signal
import socket
import sys
import threading
import time

import httpx
from dotenv import load_dotenv

from .api_sink import ApiError, ApiSink
from .geo.config import ProximityConfig
from .geo.enrich import Enricher
from .main import SOURCES
from .polite import SourceBlocked

log = sys.stderr


class Stop(SystemExit):
    """Raised in the main thread on SIGTERM/SIGINT so the current run is finished as FAILED."""


def _on_signal(signum, _frame):
    raise Stop(f"worker stopped by signal {signal.Signals(signum).name}")


def _heartbeat(run_id: str, stop: threading.Event, every_s: float) -> None:
    # Own client: the main thread's one is busy streaming listings.
    with ApiSink() as beat:
        while not stop.wait(every_s):
            try:
                beat.heartbeat(run_id)
            except Exception as e:  # noqa: BLE001 -- a missed beat is retried next time
                print(f"[worker] heartbeat failed: {e!r}", file=log)


def execute(sink: ApiSink, run: dict, *, heartbeat_s: float) -> None:
    source, params = run["source"], run.get("params") or {}
    print(f"[worker] run {run['id']}: {source} {params}", file=log)
    args = argparse.Namespace(
        max_pages=params.get("maxPages"),
        areas=",".join(params["areas"]) if params.get("areas") else None,
        headed=False,
        no_details=False,
    )
    limit = params.get("limit")
    enricher = Enricher(ProximityConfig()) if params.get("enrich") else None

    stop = threading.Event()
    beat = threading.Thread(target=_heartbeat, args=(run["id"], stop, heartbeat_s), daemon=True)
    beat.start()
    seen = 0
    try:
        with sink.attach(run["id"], source=source, mark_unseen_inactive=bool(params.get("markUnseenInactive"))):
            if source not in SOURCES:
                raise ValueError(f"unknown source {source!r}; this worker knows {', '.join(SOURCES)}")
            for listing in SOURCES[source](args):
                seen += 1
                if enricher:
                    enricher.enrich(listing)
                sink.write(listing)
                if seen % 25 == 0:
                    print(f"[worker] {source}: {seen} sent", file=log)
                if limit and seen >= limit:
                    break
    except SourceBlocked as e:
        print(f"[worker] {source} stopped: {e}", file=log)
    except Stop:
        raise
    except Exception as e:  # noqa: BLE001 -- the run is already FAILED; keep the worker alive
        print(f"[worker] {source} failed: {e!r}", file=log)
    finally:
        stop.set()
    print(f"[worker] {source} done: {seen} listings", file=log)


def main() -> None:
    load_dotenv()
    name = os.getenv("WORKER_NAME") or socket.gethostname()
    sources = [s.strip() for s in os.getenv("WORKER_SOURCES", "").split(",") if s.strip()] or None
    poll_s = float(os.getenv("WORKER_POLL_SECONDS", 60))
    heartbeat_s = float(os.getenv("WORKER_HEARTBEAT_SECONDS", 60))
    signal.signal(signal.SIGTERM, _on_signal)
    signal.signal(signal.SIGINT, _on_signal)

    print(f"[worker] {name} polling {os.getenv('LISTINGS_API_URL', 'default URL')} for {sources or 'all sources'}", file=log)
    with ApiSink() as sink:
        try:
            while True:
                try:
                    run = sink.claim(name, sources)
                except (ApiError, httpx.HTTPError, ValueError) as e:
                    # API down or misconfigured: keep trying, quietly.
                    print(f"[worker] cannot reach the API: {e!r}", file=log)
                    run = None
                if run:
                    execute(sink, run, heartbeat_s=heartbeat_s)
                else:
                    time.sleep(poll_s)
        except Stop as e:
            print(f"[worker] {e}", file=log)


if __name__ == "__main__":
    main()
