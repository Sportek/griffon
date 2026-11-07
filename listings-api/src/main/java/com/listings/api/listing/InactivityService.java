package com.listings.api.listing;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.bson.Document;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;

/**
 * Flags listings the scraper stopped returning (rented, withdrawn) as inactive.
 * <p>
 * Two triggers: a periodic sweep on {@code lastSeenAt} age (per-source thresholds, since
 * scrape frequencies differ), and the end of a complete ingestion run, where anything of
 * that source not seen since the run started is gone. Seeing a listing again reactivates it.
 */
@Service
@EnableConfigurationProperties(InactivityService.Properties.class)
public class InactivityService {

	private static final Logger log = LoggerFactory.getLogger(InactivityService.class);

	private final MongoTemplate mongo;

	private final DuplicateDetector duplicates;

	private final Clock clock;

	private final Properties properties;

	InactivityService(MongoTemplate mongo, DuplicateDetector duplicates, Clock clock, Properties properties) {
		this.mongo = mongo;
		this.duplicates = duplicates;
		this.clock = clock;
		this.properties = properties;
	}

	@Scheduled(cron = "${listings.inactivity.sweep-cron:0 0 * * * *}")
	void scheduledSweep() {
		if (properties.enabled()) {
			int count = sweep();
			if (count > 0) {
				log.info("Marked {} listings inactive", count);
			}
		}
	}

	/**
	 * Deactivates listings not seen for longer than their threshold. Rentals and properties
	 * for sale of one source are scraped by different runs, at different paces: each has its
	 * own threshold, looked up by run source ({@code centris_sale}), then by listing source.
	 */
	public int sweep() {
		Instant now = clock.instant();
		int total = 0;
		for (String source : mongo.getCollection(Listing.COLLECTION).distinct("source", String.class)) {
			for (boolean sale : new boolean[] { false, true }) {
				RunScope scope = new RunScope(source, sale);
				Duration staleAfter = properties.staleAfterBySource()
					.getOrDefault(scope.runSource(),
							properties.staleAfterBySource().getOrDefault(source, properties.staleAfter()));
				total += deactivate(scope.criteria().append("lastSeenAt", new Document("$lt", now.minus(staleAfter))));
			}
		}
		return total;
	}

	/**
	 * Deactivates the listings of a run source not seen since {@code since} (end of a complete
	 * run). {@code centris} only touches Centris rentals, {@code centris_sale} only Centris
	 * properties for sale.
	 */
	public int markUnseenSince(String runSource, Instant since) {
		return deactivate(RunScope.of(runSource).criteria().append("lastSeenAt", new Document("$lt", since)));
	}

	private int deactivate(Document criteria) {
		criteria.append("active", new Document("$ne", false));
		List<Document> stale = mongo.getCollection(Listing.COLLECTION)
			.find(criteria)
			.projection(new Document(DuplicateDetector.KEY, 1))
			.into(new ArrayList<>());
		if (stale.isEmpty()) {
			return 0;
		}
		List<Object> ids = stale.stream().map(d -> d.get("_id")).toList();
		mongo.getCollection(Listing.COLLECTION)
			.updateMany(new Document("_id", new Document("$in", ids)),
					new Document("$set", new Document("active", false).append("inactiveSince", clock.instant())));
		// An inactive canonical hands its role over to an active duplicate.
		duplicates.regroup(stale.stream().map(d -> d.getString(DuplicateDetector.KEY)).toList());
		return stale.size();
	}

	/**
	 * @param enabled run the scheduled sweep
	 * @param staleAfter default age of lastSeenAt after which a listing is inactive
	 * @param staleAfterBySource per-source overrides, e.g. {@code kijiji: P2D}
	 */
	@ConfigurationProperties("listings.inactivity")
	public record Properties(@DefaultValue("true") boolean enabled, @DefaultValue("3d") Duration staleAfter,
			Map<String, Duration> staleAfterBySource) {

		public Properties {
			staleAfterBySource = (staleAfterBySource == null) ? Map.of() : staleAfterBySource;
		}

	}

}
