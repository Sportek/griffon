package com.listings.api.run;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.List;

import com.listings.api.listing.InactivityService;
import com.listings.api.listing.IngestReport;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.FindAndModifyOptions;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

/**
 * Lifecycle of ingestion runs: QUEUED (scheduled or triggered, waiting for a worker) →
 * RUNNING (claimed, or started straight from the CLI) → SUCCEEDED / FAILED / CANCELLED. Runs whose
 * worker went silent, or that no worker ever picked up, are failed by {@link #expireStale()}.
 * A FAILED or CANCELLED worker run can be resumed: a new run with the same params skips what
 * the interrupted one already sent (see {@link #resume(String)}).
 */
@Service
public class IngestionRunService {

	private static final Logger log = LoggerFactory.getLogger(IngestionRunService.class);

	static final int MAX_LIMIT = 100;

	private final MongoTemplate mongo;

	private final InactivityService inactivity;

	private final OpsNotifier ops;

	private final Clock clock;

	private final Duration runningTimeout;

	private final Duration queuedTimeout;

	IngestionRunService(MongoTemplate mongo, InactivityService inactivity, OpsNotifier ops, Clock clock,
			@Value("${listings.runs.running-timeout:30m}") Duration runningTimeout,
			@Value("${listings.runs.queued-timeout:6h}") Duration queuedTimeout) {
		this.mongo = mongo;
		this.inactivity = inactivity;
		this.ops = ops;
		this.clock = clock;
		this.runningTimeout = runningTimeout;
		this.queuedTimeout = queuedTimeout;
	}

	/** A run started directly by the CLI (no queue, no worker). */
	public IngestionRun start(String source) {
		requireSource(source);
		Instant now = clock.instant();
		return mongo.insert(new IngestionRun(null, source, IngestionRunStatus.RUNNING, IngestionRun.TRIGGER_CLI,
				null, now, now, null, now, null, 0, 0, 0, 0, 0, 0, 0, null, false, null, null));
	}

	/** Queues a run for a worker. Refused while the source already has a queued or running run. */
	public IngestionRun queue(String source, ScrapeParams params, String trigger) {
		requireSource(source);
		ScrapeParams effective = ScrapeParams.orDefaults(params);
		effective.validate();
		if (hasActiveRun(source)) {
			throw new IllegalArgumentException("A run of " + source + " is already queued or running");
		}
		return mongo.insert(new IngestionRun(null, source, IngestionRunStatus.QUEUED, trigger, effective,
				clock.instant(), null, null, null, null, 0, 0, 0, 0, 0, 0, 0, null, false, null, null));
	}

	/**
	 * Stops a run. A queued run is CANCELLED at once; a running one is flagged, and its worker,
	 * told by its next heartbeat, stops and finishes it CANCELLED.
	 */
	public IngestionRun cancel(String id) {
		IngestionRun run = find(id);
		if (run == null) {
			throw new IllegalArgumentException("Unknown ingestion run: " + id);
		}
		Query query = Query.query(Criteria.where("_id").is(id).and("status").is(run.status()));
		Update update = switch (run.status()) {
			case QUEUED -> new Update().set("status", IngestionRunStatus.CANCELLED)
				.set("finishedAt", clock.instant())
				.set("error", "cancelled before a worker picked it up");
			case RUNNING -> new Update().set("cancelRequested", true);
			default -> throw new IllegalArgumentException("Ingestion run " + id + " is already " + run.status());
		};
		IngestionRun updated = mongo.findAndModify(query, update, FindAndModifyOptions.options().returnNew(true),
				IngestionRun.class);
		if (updated == null) {
			throw new IllegalArgumentException("Ingestion run " + id + " changed meanwhile, try again");
		}
		return updated;
	}

	/**
	 * Queues the continuation of a FAILED or CANCELLED worker run: same params, and the
	 * listings it already sent are skipped (see {@link #alreadySeen(String)}). Counted from
	 * the interrupted run's start, a complete continuation can still deactivate unseen listings.
	 */
	public IngestionRun resume(String id) {
		IngestionRun previous = find(id);
		if (previous == null) {
			throw new IllegalArgumentException("Unknown ingestion run: " + id);
		}
		if (previous.status() != IngestionRunStatus.FAILED && previous.status() != IngestionRunStatus.CANCELLED) {
			throw new IllegalArgumentException(
					"Only a FAILED or CANCELLED run can be resumed; " + id + " is " + previous.status());
		}
		if (previous.params() == null) {
			throw new IllegalArgumentException("Run " + id + " was started from the CLI, not by a worker: re-run it");
		}
		if (hasActiveRun(previous.source())) {
			throw new IllegalArgumentException("A run of " + previous.source() + " is already queued or running");
		}
		return mongo.insert(new IngestionRun(null, previous.source(), IngestionRunStatus.QUEUED,
				IngestionRun.TRIGGER_RESUME, previous.params(), clock.instant(), null, null, null, null, 0, 0, 0, 0,
				0, 0, 0, null, false, previous.id(), previous.seenSince()));
	}

	/**
	 * External ids a resumed run can skip: its source's listings seen since the interrupted
	 * scrape started. Empty for a run that resumes nothing.
	 */
	public List<String> alreadySeen(String id) {
		IngestionRun run = find(id);
		if (run == null) {
			throw new IllegalArgumentException("Unknown ingestion run: " + id);
		}
		if (run.resumeOf() == null || run.coverageSince() == null) {
			return List.of();
		}
		return inactivity.externalIdsSeenSince(run.source(), run.coverageSince());
	}

	boolean hasActiveRun(String source) {
		return mongo.exists(Query.query(Criteria.where("source")
			.is(source)
			.and("status")
			.in(IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING)), IngestionRun.class);
	}

	/**
	 * Atomically hands the oldest queued run (optionally restricted to {@code sources}) to
	 * {@code worker}. Null when there is nothing to do.
	 */
	public IngestionRun claim(String worker, List<String> sources) {
		if (worker == null || worker.isBlank()) {
			throw new IllegalArgumentException("worker must not be blank");
		}
		Criteria criteria = Criteria.where("status").is(IngestionRunStatus.QUEUED);
		if (sources != null && !sources.isEmpty()) {
			criteria = criteria.and("source").in(sources);
		}
		Instant now = clock.instant();
		Update update = new Update().set("status", IngestionRunStatus.RUNNING)
			.set("worker", worker)
			.set("startedAt", now)
			.set("lastBatchAt", now);
		return mongo.findAndModify(Query.query(criteria).with(Sort.by("queuedAt")), update,
				FindAndModifyOptions.options().returnNew(true), IngestionRun.class);
	}

	/**
	 * Keeps a long run alive between batches (e.g. while a source walks its search pages).
	 * False tells the worker to stop: the run was cancelled, or is no longer RUNNING.
	 */
	public boolean heartbeat(String id) {
		return mongo
			.updateFirst(
					Query.query(Criteria.where("_id")
						.is(id)
						.and("status")
						.is(IngestionRunStatus.RUNNING)
						.and("cancelRequested")
						.ne(true)),
					Update.update("lastBatchAt", clock.instant()), IngestionRun.class)
			.getMatchedCount() > 0;
	}

	public IngestionRun find(String id) {
		return mongo.findById(id, IngestionRun.class);
	}

	/** The run, which must exist and still be RUNNING to accept batches. */
	public IngestionRun requireRunning(String id) {
		IngestionRun run = find(id);
		if (run == null) {
			throw new IllegalArgumentException("Unknown ingestion run: " + id);
		}
		if (run.status() != IngestionRunStatus.RUNNING) {
			throw new IllegalArgumentException("Ingestion run " + id + " is " + run.status() + ", not RUNNING");
		}
		return run;
	}

	public void record(String id, IngestReport report) {
		Update update = new Update().inc("batches", 1)
			.inc("received", report.received())
			.inc("created", report.created())
			.inc("updated", report.updated())
			.inc("unchanged", report.unchanged())
			.inc("rejected", report.rejected())
			.set("lastBatchAt", clock.instant());
		mongo.updateFirst(Query.query(Criteria.where("_id").is(id)), update, IngestionRun.class);
	}

	public IngestionRun finish(String id, IngestionRunStatus status, String error, boolean markUnseenInactive) {
		if (status == IngestionRunStatus.QUEUED || status == IngestionRunStatus.RUNNING) {
			throw new IllegalArgumentException("A run can only finish as SUCCEEDED, FAILED or CANCELLED");
		}
		IngestionRun run = requireRunning(id);
		int deactivated = 0;
		// Only a successful run proves that what it did not see is gone.
		if (markUnseenInactive && status == IngestionRunStatus.SUCCEEDED) {
			deactivated = inactivity.markUnseenSince(run.source(), run.seenSince());
		}
		Update update = new Update().set("status", status)
			.set("finishedAt", clock.instant())
			.set("error", error)
			.set("deactivated", deactivated);
		IngestionRun finished = mongo.findAndModify(
				Query.query(Criteria.where("_id").is(id).and("status").is(IngestionRunStatus.RUNNING)), update,
				FindAndModifyOptions.options().returnNew(true), IngestionRun.class);
		if (finished != null && status == IngestionRunStatus.FAILED) {
			ops.runFailed(finished);
		}
		return finished;
	}

	/** Fails runs whose worker went silent and queued runs no worker picked up. */
	public int expireStale() {
		Instant now = clock.instant();
		int expired = 0;
		for (IngestionRun run : mongo.find(Query.query(Criteria.where("status")
			.in(IngestionRunStatus.QUEUED, IngestionRunStatus.RUNNING)), IngestionRun.class)) {
			String reason = null;
			if (run.status() == IngestionRunStatus.RUNNING
					&& run.lastActivity().isBefore(now.minus(runningTimeout))) {
				reason = "No activity for " + runningTimeout.toMinutes() + " min: worker " + run.worker()
						+ " crashed or lost its connection";
			}
			else if (run.status() == IngestionRunStatus.QUEUED && run.queuedAt().isBefore(now.minus(queuedTimeout))) {
				reason = "Not picked up within " + queuedTimeout.toHours() + " h: is a worker running for "
						+ run.source() + "?";
			}
			if (reason == null) {
				continue;
			}
			IngestionRun failed = mongo.findAndModify(
					Query.query(Criteria.where("_id").is(run.id()).and("status").is(run.status())),
					new Update().set("status", IngestionRunStatus.FAILED).set("finishedAt", now).set("error", reason),
					FindAndModifyOptions.options().returnNew(true), IngestionRun.class);
			if (failed != null) {
				log.warn("Ingestion run {} ({}) failed: {}", run.id(), run.source(), reason);
				ops.runFailed(failed);
				expired++;
			}
		}
		return expired;
	}

	public List<IngestionRun> list(String source, IngestionRunStatus status, int limit) {
		if (limit < 1 || limit > MAX_LIMIT) {
			throw new IllegalArgumentException("limit must be between 1 and " + MAX_LIMIT);
		}
		Criteria criteria = new Criteria();
		if (source != null) {
			criteria = criteria.and("source").is(source);
		}
		if (status != null) {
			criteria = criteria.and("status").is(status);
		}
		Query query = Query.query(criteria).with(Sort.by(Sort.Direction.DESC, "queuedAt", "_id")).limit(limit);
		return mongo.find(query, IngestionRun.class);
	}

	private static void requireSource(String source) {
		if (source == null || source.isBlank()) {
			throw new IllegalArgumentException("source must not be blank");
		}
	}

}
