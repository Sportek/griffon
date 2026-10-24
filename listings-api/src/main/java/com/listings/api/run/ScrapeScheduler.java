package com.listings.api.run;

import java.time.Clock;
import java.time.DateTimeException;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZonedDateTime;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.scheduling.support.CronExpression;
import org.springframework.stereotype.Service;

/**
 * The backend side of periodic scraping: schedules live in MongoDB, and every minute the
 * due ones are turned into QUEUED runs that a worker claims. A source never gets a second
 * run while one is still queued or running (the slot is skipped, not stacked).
 */
@Service
public class ScrapeScheduler {

	private static final Logger log = LoggerFactory.getLogger(ScrapeScheduler.class);

	static final String DEFAULT_ZONE = "America/Toronto";

	private final MongoTemplate mongo;

	private final IngestionRunService runs;

	private final Clock clock;

	private final boolean enabled;

	ScrapeScheduler(MongoTemplate mongo, IngestionRunService runs, Clock clock,
			@Value("${listings.scheduler.enabled:true}") boolean enabled) {
		this.mongo = mongo;
		this.runs = runs;
		this.clock = clock;
		this.enabled = enabled;
	}

	@Scheduled(fixedDelayString = "${listings.scheduler.tick:60s}", initialDelayString = "${listings.scheduler.tick:60s}")
	void scheduledTick() {
		if (enabled) {
			tick();
		}
	}

	/** Expires stale runs, then queues every due schedule. Returns the number of runs queued. */
	public int tick() {
		runs.expireStale();
		Instant now = clock.instant();
		int queued = 0;
		Query due = Query.query(Criteria.where("enabled").is(true).and("nextRunAt").lte(now))
			.with(Sort.by("nextRunAt"));
		for (ScrapeSchedule schedule : mongo.find(due, ScrapeSchedule.class)) {
			Update update = Update.update("nextRunAt", nextRun(schedule.cron(), schedule.timeZone(), now));
			if (runs.hasActiveRun(schedule.source())) {
				log.info("Skipping scheduled {} run: the previous one is still queued or running", schedule.source());
			}
			else {
				runs.queue(schedule.source(), schedule.params(), IngestionRun.TRIGGER_SCHEDULE);
				update.set("lastQueuedAt", now);
				queued++;
			}
			mongo.updateFirst(Query.query(Criteria.where("_id").is(schedule.id())), update, ScrapeSchedule.class);
		}
		return queued;
	}

	/** Creates or replaces the schedule of a source. */
	public ScrapeSchedule save(ScrapeScheduleInput input) {
		if (input.source() == null || input.source().isBlank()) {
			throw new IllegalArgumentException("source must not be blank");
		}
		String zone = (input.timeZone() == null || input.timeZone().isBlank()) ? DEFAULT_ZONE : input.timeZone();
		ScrapeParams params = ScrapeParams.orDefaults(input.params());
		params.validate();
		Instant now = clock.instant();
		Instant next = nextRun(input.cron(), zone, now);
		ScrapeSchedule existing = find(input.source());
		return mongo.save(new ScrapeSchedule((existing != null) ? existing.id() : null, input.source(), input.cron(),
				zone, !Boolean.FALSE.equals(input.enabled()), params, next,
				(existing != null) ? existing.lastQueuedAt() : null, (existing != null) ? existing.createdAt() : now));
	}

	public boolean delete(String source) {
		return mongo.remove(Query.query(Criteria.where("source").is(source)), ScrapeSchedule.class)
			.getDeletedCount() > 0;
	}

	public ScrapeSchedule find(String source) {
		return mongo.findOne(Query.query(Criteria.where("source").is(source)), ScrapeSchedule.class);
	}

	public List<ScrapeSchedule> findAll() {
		return mongo.find(new Query().with(Sort.by("source")), ScrapeSchedule.class);
	}

	/** Next fire time strictly after {@code after}; validates the cron and the zone. */
	static Instant nextRun(String cron, String zone, Instant after) {
		CronExpression expression;
		ZoneId zoneId;
		try {
			expression = CronExpression.parse(cron);
		}
		catch (IllegalArgumentException | NullPointerException ex) {
			throw new IllegalArgumentException("Invalid cron \"" + cron
					+ "\": 6 fields expected (second minute hour day month weekday), e.g. \"0 0 3 * * *\"");
		}
		try {
			zoneId = ZoneId.of(zone);
		}
		catch (DateTimeException ex) {
			throw new IllegalArgumentException("Invalid timeZone: " + zone);
		}
		ZonedDateTime next = expression.next(after.atZone(zoneId));
		if (next == null) {
			throw new IllegalArgumentException("Cron \"" + cron + "\" never fires");
		}
		return next.toInstant();
	}

}
