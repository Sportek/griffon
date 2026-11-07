"""Queues scrapes by hand and optionally follows them until they finish.

The API keeps one FIFO queue (oldest queuedAt first) and the worker runs one scrape at a
time, so the sources given here run one after the other, in this order:

    python -m scraper.trigger ubee ubee_sale facebook --watch
    python -m scraper.trigger centris --max-pages 1          # quick test, never deactivates
    python -m scraper.trigger --status                       # queue + last runs

By default each run reuses the params of the source's schedule (areas, enrich,
markUnseenInactive...); the flags below override them. A source that already has a
QUEUED or RUNNING run is skipped unless --force.

Needs LISTINGS_API_URL and LISTINGS_API_KEY (read from .env).
"""

import argparse
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from .api_sink import ApiSink
from .main import SOURCES

RUN_FIELDS = "id source status trigger queuedAt startedAt finishedAt worker received created updated unchanged rejected deactivated error"

SCHEDULES_QUERY = "{ scrapeSchedules { source params { maxPages areas limit enrich markUnseenInactive } } }"
TRIGGER_MUTATION = f"mutation($s: String!, $p: ScrapeParamsInput) {{ triggerScrape(source: $s, params: $p) {{ {RUN_FIELDS} }} }}"
RUN_QUERY = f"query($id: ID!) {{ ingestionRun(id: $id) {{ {RUN_FIELDS} }} }}"
RUNS_QUERY = f"query($st: IngestionRunStatus, $n: Int) {{ ingestionRuns(status: $st, limit: $n) {{ {RUN_FIELDS} }} }}"

DONE = {"SUCCEEDED", "FAILED"}


def _hms(iso: str | None) -> str:
    if not iso:
        return "-"
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone().strftime("%m-%d %H:%M")


def describe(run: dict) -> str:
    counts = f"recv {run['received']} new {run['created']} upd {run['updated']} same {run['unchanged']} rej {run['rejected']}"
    if run["status"] in DONE:
        counts += f" deact {run['deactivated']}"
    line = f"{run['source']:<15} {run['status']:<9} queued {_hms(run['queuedAt'])} started {_hms(run['startedAt'])} " \
           f"ended {_hms(run['finishedAt'])}  {counts}"
    if run.get("error"):
        line += f"\n{'':15} error: {run['error']}"
    return line


def show_status(sink: ApiSink) -> None:
    for status in ("RUNNING", "QUEUED"):
        runs = sink._execute(RUNS_QUERY, {"st": status, "n": 50})["ingestionRuns"]
        print(f"-- {status} ({len(runs)})")
        for run in sorted(runs, key=lambda r: r["queuedAt"] or ""):
            print(describe(run))
    print("-- last 10")
    for run in sink._execute(RUNS_QUERY, {"st": None, "n": 10})["ingestionRuns"]:
        print(describe(run))


def build_params(schedule_params: dict | None, args: argparse.Namespace) -> dict:
    params = {k: v for k, v in (schedule_params or {}).items() if v is not None}
    if args.max_pages is not None:
        params["maxPages"] = args.max_pages
    if args.limit is not None:
        params["limit"] = args.limit
    if args.areas:
        params["areas"] = [a.strip() for a in args.areas.split(",") if a.strip()]
    if args.enrich is not None:
        params["enrich"] = args.enrich
    if args.mark_unseen is not None:
        params["markUnseenInactive"] = args.mark_unseen
    # A partial crawl must never deactivate the listings it did not reach.
    if params.get("maxPages") is not None or params.get("limit") is not None:
        params["markUnseenInactive"] = False
    return params


def watch(sink: ApiSink, runs: list[dict], every: float) -> int:
    pending = {r["id"]: r for r in runs}
    last_line: dict[str, str] = {}
    while pending:
        for run_id in list(pending):
            run = sink._execute(RUN_QUERY, {"id": run_id})["ingestionRun"]
            line = describe(run)
            if last_line.get(run_id) != line:
                print(f"[{datetime.now():%H:%M:%S}] {line}", flush=True)
                last_line[run_id] = line
            if run["status"] in DONE:
                pending.pop(run_id).update(run)
        if pending:
            time.sleep(every)
    failed = [r for r in runs if r["status"] == "FAILED"]
    print(f"done: {len(runs) - len(failed)} succeeded, {len(failed)} failed")
    return 1 if failed else 0


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Queue scrapes on the worker (they run one after another)")
    parser.add_argument("sources", nargs="*", help=f"in run order; one of: {', '.join(SOURCES)}")
    parser.add_argument("--status", action="store_true", help="show running/queued and recent runs, then exit")
    parser.add_argument("--watch", action="store_true", help="follow the queued runs until they all finish")
    parser.add_argument("--every", type=float, default=30, help="seconds between two checks with --watch")
    parser.add_argument("--force", action="store_true", help="queue even if the source already has a pending run")
    parser.add_argument("--max-pages", type=int)
    parser.add_argument("--limit", type=int)
    parser.add_argument("--areas", help="comma-separated, same meaning as in scraper.main")
    parser.add_argument("--enrich", action=argparse.BooleanOptionalAction, default=None)
    parser.add_argument("--mark-unseen", action=argparse.BooleanOptionalAction, default=None,
                        help="deactivate listings not seen during the run (default: the schedule's)")
    args = parser.parse_args()

    unknown = [s for s in args.sources if s not in SOURCES]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")

    with ApiSink() as sink:
        if args.status or not args.sources:
            show_status(sink)
            return

        schedules = {s["source"]: s["params"] for s in sink._execute(SCHEDULES_QUERY)["scrapeSchedules"]}
        busy = set()
        for status in ("RUNNING", "QUEUED"):
            busy |= {r["source"] for r in sink._execute(RUNS_QUERY, {"st": status, "n": 100})["ingestionRuns"]}

        queued = []
        for source in args.sources:
            if source in busy and not args.force:
                print(f"{source}: already queued or running, skipped (--force to queue anyway)")
                continue
            params = build_params(schedules.get(source), args)
            run = sink._execute(TRIGGER_MUTATION, {"s": source, "p": params})["triggerScrape"]
            print(f"queued {source} ({run['id']}) params {params}")
            queued.append(run)

        if args.watch and queued:
            sys.exit(watch(sink, queued, args.every))


if __name__ == "__main__":
    main()
