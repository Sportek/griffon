package com.listings.api.run;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * One scraper execution for one source. Scheduled or manually triggered runs start
 * QUEUED until a worker claims them; runs started from the CLI start RUNNING.
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
		String error) {

	public static final String COLLECTION = "ingestionRuns";

	public static final String TRIGGER_CLI = "cli";

	public static final String TRIGGER_SCHEDULE = "schedule";

	public static final String TRIGGER_MANUAL = "manual";

	/** Last sign of life: batches and heartbeats both refresh lastBatchAt. */
	Instant lastActivity() {
		return (lastBatchAt != null) ? lastBatchAt : startedAt;
	}

}
