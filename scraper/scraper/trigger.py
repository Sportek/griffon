"""Queues scrapes by hand and optionally follows them until they finish.

The API keeps one FIFO queue (oldest queuedAt first) and the worker runs one scrape at a
time, so the sources given here run one after the other, in this order:

    python -m scraper.trigger ubee ubee_sale facebook --watch
    python -m scraper.trigger centris --max-pages 1          # quick test, never deactivates
    python -m scraper.trigger --status                       # queue + last runs
    python -m scraper.trigger --cancel centris_sale          # stop its queued/running run
    python -m scraper.trigger --resume centris_sale --watch  # pick its last stopped run up

--cancel and --resume also take run ids. A running run stops at the worker's next heartbeat
(about a minute) and ends CANCELLED. --resume queues the continuation of the source's last
run, which must be FAILED or CANCELLED (e.g. cut by a redeploy): same params, and the
listings it already sent are skipped, so only the rest is fetched.

By default each run reuses the params of the source's schedule (areas, enrich,
markUnseenInactive...); the flags below override them. A source that already has a
QUEUED or RUNNING run is skipped unless --force.

Needs LISTINGS_API_URL and LISTINGS_API_KEY (read from .env).
"""

import argparse
import re
import sys
import time
from datetime import datetime

from dotenv import load_dotenv

from .api_sink import ApiSink
from .main import SOURCES

RUN_FIELDS = (
    "id source status trigger queuedAt startedAt finishedAt worker received created updated unchanged rejected "
    "deactivated error cancelRequested resumeOf"
)

SCHEDULES_QUERY = "{ scrapeSchedules { source params { maxPages areas limit enrich markUnseenInactive } } }"
TRIGGER_MUTATION = f"mutation($s: String!, $p: ScrapeParamsInput) {{ triggerScrape(source: $s, params: $p) {{ {RUN_FIELDS} }} }}"
RUN_QUERY = f"query($id: ID!) {{ ingestionRun(id: $id) {{ {RUN_FIELDS} }} }}"
RUNS_QUERY = f"query($st: IngestionRunStatus, $n: Int) {{ ingestionRuns(status: $st, limit: $n) {{ {RUN_FIELDS} }} }}"
SOURCE_RUNS_QUERY = f"query($s: String!) {{ ingestionRuns(source: $s, limit: 1) {{ {RUN_FIELDS} }} }}"
CANCEL_MUTATION = f"mutation($id: ID!) {{ cancelIngestionRun(id: $id) {{ {RUN_FIELDS} }} }}"
RESUME_MUTATION = f"mutation($id: ID!) {{ resumeIngestionRun(id: $id) {{ {RUN_FIELDS} }} }}"

DONE = {"SUCCEEDED", "FAILED", "CANCELLED"}
RUN_ID_RE = re.compile(r"^[0-9a-f]{24}$")


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
    if run.get("cancelRequested") and run["status"] == "RUNNING":
        line += "  (stop requested)"
    if run.get("resumeOf"):
        line += f"  (resumes {run['resumeOf']})"
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
    cancelled = [r for r in runs if r["status"] == "CANCELLED"]
    print(f"done: {len(runs) - len(failed) - len(cancelled)} succeeded, {len(failed)} failed, {len(cancelled)} cancelled")
    return 1 if failed else 0


def target_run(sink: ApiSink, target: str) -> dict | None:
    """A run id as is, or a source's most recent run."""
    if RUN_ID_RE.match(target):
        return sink._execute(RUN_QUERY, {"id": target})["ingestionRun"]
    runs = sink._execute(SOURCE_RUNS_QUERY, {"s": target})["ingestionRuns"]
    return runs[0] if runs else None


def cancel(sink: ApiSink, targets: list[str]) -> None:
    for target in targets:
        run = target_run(sink, target)
        if not run or run["status"] not in ("QUEUED", "RUNNING"):
            print(f"{target}: no queued or running run to cancel")
            continue
        run = sink._execute(CANCEL_MUTATION, {"id": run["id"]})["cancelIngestionRun"]
        what = "cancelled" if run["status"] == "CANCELLED" else "stop requested, the worker stops within a minute"
        print(f"{run['source']} ({run['id']}): {what}")


def resume(sink: ApiSink, targets: list[str]) -> list[dict]:
    queued = []
    for target in targets:
        run = target_run(sink, target)
        if not run or run["status"] not in ("FAILED", "CANCELLED"):
            status = run["status"] if run else "no run"
            print(f"{target}: last run is {status}, nothing to resume")
            continue
        new = sink._execute(RESUME_MUTATION, {"id": run["id"]})["resumeIngestionRun"]
        print(f"queued {new['source']} ({new['id']}), resuming {run['id']} ({run['received']} listings already sent)")
        queued.append(new)
    return queued


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description="Queue scrapes on the worker (they run one after another)")
    parser.add_argument("sources", nargs="*",
                        help=f"in run order; one of: {', '.join(SOURCES)} (run ids too with --cancel/--resume)")
    parser.add_argument("--status", action="store_true", help="show running/queued and recent runs, then exit")
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--cancel", action="store_true", help="stop the queued/running run of these sources (or run ids)")
    action.add_argument("--resume", action="store_true",
                        help="continue the last FAILED/CANCELLED run of these sources (or run ids), skipping what it sent")
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

    by_id = args.cancel or args.resume
    unknown = [s for s in args.sources if s not in SOURCES and not (by_id and RUN_ID_RE.match(s))]
    if unknown:
        parser.error(f"unknown source(s): {', '.join(unknown)}")

    with ApiSink() as sink:
        if args.status or not args.sources:
            show_status(sink)
            return
        if args.cancel:
            cancel(sink, args.sources)
            return
        if args.resume:
            queued = resume(sink, args.sources)
            if args.watch and queued:
                sys.exit(watch(sink, queued, args.every))
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
