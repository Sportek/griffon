"""Long-running worker: executes the scrapes the API schedules.

The API owns the schedule (scrapeSchedules / triggerScrape) and queues runs; this worker
polls `claimIngestionRun`, runs the source with the run's params, streams listings into
the run, keeps it alive with heartbeats and finishes it (FAILED with the reason if the
source is blocked or crashes; SUCCEEDED without deactivating anything if the source lost
too many pages, see polite.CrawlHealth). It only ever calls out to the API, so it can sit behind a
home NAT (e.g. on a residential IP, which sites block far less than datacenter IPs).

    LISTINGS_API_URL=https://api.example/graphql LISTINGS_API_KEY=... python -m scraper.worker

Environment:
    WORKER_NAME            shown in ingestionRuns.worker (default: hostname)
    WORKER_SOURCES         comma-separated sources this worker accepts (default: all)
    WORKER_POLL_SECONDS    wait between two claims when idle (default 60)
    WORKER_HEARTBEAT_SECONDS                              (default 60)
    WORKER_PROGRESS_SECONDS  a [progress] line in the logs every so often (default 300)
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
from .main import NEVER_MARK_UNSEEN, SOURCES
from .polite import PROGRESS, IncompleteCrawl, SourceBlocked

log = sys.stderr


class Stop(SystemExit):
    """Raised in the main thread on SIGTERM/SIGINT so the current run is finished as FAILED."""


def _on_signal(signum, _frame):
    raise Stop(f"worker stopped by signal {signal.Signals(signum).name}")


def _minutes(seconds: float) -> str:
    m = round(seconds / 60)
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} min"


def progress_line(source: str, elapsed_s: float, sent: int, progress: dict[str, int]) -> str:
    """One line on where a run is: time, listings sent, requests, and position/ETA when known."""
    parts = [f"[progress] {source}: {_minutes(elapsed_s)}", f"{sent} listings sent"]
    if "requests" in progress:
        parts.append(f"{progress['requests']} requests")
    done, total = progress.get("done"), progress.get("total")
    if done and total:
        parts.append(f"{done}/{total} checked ({100 * done // total} %)")
        if done < total and elapsed_s > 60:
            parts.append(f"~{_minutes(elapsed_s / done * (total - done))} left")
    return ", ".join(parts)


def _heartbeat(run_id: str, stop: threading.Event, every_s: float, report=None, report_every_s: float = 300) -> None:
    # Own client: the main thread's one is busy streaming listings.
    next_report = time.monotonic() + report_every_s
    with ApiSink() as beat:
        while not stop.wait(every_s):
            try:
                beat.heartbeat(run_id)
            except Exception as e:  # noqa: BLE001 -- a missed beat is retried next time
                print(f"[worker] heartbeat failed: {e!r}", file=log)
            if report and time.monotonic() >= next_report:
                next_report += report_every_s
                print(report(), file=log, flush=True)


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

    PROGRESS.pop(source, None)
    started = time.monotonic()
    seen = 0

    def report() -> str:
        return progress_line(source, time.monotonic() - started, seen, dict(PROGRESS.get(source, {})))

    stop = threading.Event()
    beat = threading.Thread(
        target=_heartbeat,
        args=(run["id"], stop, heartbeat_s),
        kwargs={"report": report, "report_every_s": float(os.getenv("WORKER_PROGRESS_SECONDS", 300))},
        daemon=True,
    )
    beat.start()
    try:
        mark_unseen = bool(params.get("markUnseenInactive")) and source not in NEVER_MARK_UNSEEN
        with sink.attach(run["id"], source=source, mark_unseen_inactive=mark_unseen):
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
    except IncompleteCrawl as e:
        # The run is SUCCEEDED, but nothing was marked inactive (see ApiSink.attach).
        print(f"[worker] {source} incomplete, no listing deactivated: {e}", file=log)
    except SourceBlocked as e:
        print(f"[worker] {source} stopped: {e}", file=log)
    except Stop:
        raise
    except Exception as e:  # noqa: BLE001 -- the run is already FAILED; keep the worker alive
        print(f"[worker] {source} failed: {e!r}", file=log)
    finally:
        stop.set()
    print(f"[worker] {source} done: {seen} listings", file=log)
    print(report(), file=log)


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
