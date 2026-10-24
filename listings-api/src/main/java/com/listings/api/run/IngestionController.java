package com.listings.api.run;

import java.util.List;

import com.listings.api.listing.InactivityService;
import com.listings.api.listing.IngestReport;
import com.listings.api.listing.ListingIngestionService;
import com.listings.api.listing.ListingInput;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

/** Everything the scraper calls: listing upserts and the ingestion run lifecycle. */
@Controller
class IngestionController {

	private final ListingIngestionService ingestion;

	private final IngestionRunService runs;

	private final InactivityService inactivity;

	private final ScrapeScheduler scheduler;

	IngestionController(ListingIngestionService ingestion, IngestionRunService runs, InactivityService inactivity,
			ScrapeScheduler scheduler) {
		this.ingestion = ingestion;
		this.runs = runs;
		this.inactivity = inactivity;
		this.scheduler = scheduler;
	}

	@QueryMapping
	List<ScrapeSchedule> scrapeSchedules() {
		return scheduler.findAll();
	}

	@MutationMapping
	ScrapeSchedule saveScrapeSchedule(@Argument ScrapeScheduleInput input) {
		return scheduler.save(input);
	}

	@MutationMapping
	boolean deleteScrapeSchedule(@Argument String source) {
		return scheduler.delete(source);
	}

	@MutationMapping
	IngestionRun triggerScrape(@Argument String source, @Argument ScrapeParams params) {
		return runs.queue(source, params, IngestionRun.TRIGGER_MANUAL);
	}

	@MutationMapping
	int runSchedulerTick() {
		return scheduler.tick();
	}

	@MutationMapping
	IngestionRun claimIngestionRun(@Argument String worker, @Argument List<String> sources) {
		return runs.claim(worker, sources);
	}

	@MutationMapping
	boolean heartbeatIngestionRun(@Argument String id) {
		return runs.heartbeat(id);
	}

	@MutationMapping
	IngestReport upsertListings(@Argument List<ListingInput> listings, @Argument String runId) {
		if (runId == null) {
			return ingestion.upsert(listings);
		}
		IngestionRun run = runs.requireRunning(runId);
		IngestReport report = ingestion.upsert(listings, run.source());
		runs.record(runId, report);
		return report;
	}

	@MutationMapping
	IngestionRun startIngestionRun(@Argument String source) {
		return runs.start(source);
	}

	@MutationMapping
	IngestionRun finishIngestionRun(@Argument String id, @Argument IngestionRunStatus status, @Argument String error,
			@Argument Boolean markUnseenInactive) {
		return runs.finish(id, status, error, Boolean.TRUE.equals(markUnseenInactive));
	}

	@MutationMapping
	int sweepInactiveListings() {
		return inactivity.sweep();
	}

	@QueryMapping
	IngestionRun ingestionRun(@Argument String id) {
		return runs.find(id);
	}

	@QueryMapping
	List<IngestionRun> ingestionRuns(@Argument String source, @Argument IngestionRunStatus status,
			@Argument Integer limit) {
		return runs.list(source, status, (limit != null) ? limit : 20);
	}

}
