package com.listings.api.run;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/** When a source should be scraped: a cron in a time zone, plus the options for the worker. */
@Document(ScrapeSchedule.COLLECTION)
public record ScrapeSchedule(
		@Id String id,
		String source,
		String cron,
		String timeZone,
		boolean enabled,
		ScrapeParams params,
		Instant nextRunAt,
		Instant lastQueuedAt,
		Instant createdAt) {

	public static final String COLLECTION = "scrapeSchedules";

}
