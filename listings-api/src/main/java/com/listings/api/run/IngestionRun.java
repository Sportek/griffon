package com.listings.api.run;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * One scraper execution for one source. Scheduled or manually triggered runs start
 * QUEUED until a worker claims them; runs started from the CLI start RUNNING.
 *
 * @param cancelRequested set by cancelIngestionRun on a RUNNING run: the worker learns it from
 * its next heartbeat, stops and finishes the run CANCELLED
 * @param resumeOf the FAILED or CANCELLED run this one picks up from (resumeIngestionRun)
 * @param coverageSince start of the scrape this run belongs to: its own startedAt, or for a
 * resumed run the one of the run it resumes. Listings seen since then count as seen by the run.
 */
@Document(IngestionRun.COLLECTION)
public record IngestionRun(
		@Id String id,
		String source,
		IngestionRunStatus status,
		String trigger,
		ScrapeParams params,
		Instant queuedAt,
		Instant startedAt,
		Instant finishedAt,
		Instant lastBatchAt,
		String worker,
		int batches,
		int received,
		int created,
		int updated,
		int unchanged,
		int rejected,
		int deactivated,
		String error,
		Boolean cancelRequested,
		String resumeOf,
		Instant coverageSince) {

	/** Runs saved before cancelRequested existed have no such field. */
	public IngestionRun {
		cancelRequested = Boolean.TRUE.equals(cancelRequested);
	}

	public static final String COLLECTION = "ingestionRuns";

	public static final String TRIGGER_CLI = "cli";

	public static final String TRIGGER_SCHEDULE = "schedule";

	public static final String TRIGGER_MANUAL = "manual";

	public static final String TRIGGER_RESUME = "resume";

	/** Since when the listings this run saw were seen: its own start, unless it resumes an earlier run. */
	Instant seenSince() {
		return (coverageSince != null) ? coverageSince : startedAt;
	}

	/** Last sign of life: batches and heartbeats both refresh lastBatchAt. */
	Instant lastActivity() {
		return (lastBatchAt != null) ? lastBatchAt : startedAt;
	}

}
