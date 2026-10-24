package com.listings.api;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.listings.api.alert.Alert;
import com.listings.api.alert.SavedSearch;
import com.listings.api.listing.Listing;
import com.listings.api.run.IngestionRun;
import com.listings.api.run.ScrapeSchedule;
import org.junit.jupiter.api.BeforeEach;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.graphql.test.autoconfigure.tester.AutoConfigureGraphQlTester;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.Primary;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.graphql.test.tester.GraphQlTester;

/**
 * Base for GraphQL integration tests: a real MongoDB (Testcontainers), a controllable
 * clock and empty collections before each test. Subclasses share one Spring context.
 */
@SpringBootTest(properties = { "listings.inactivity.enabled=false", "listings.scheduler.enabled=false" })
@AutoConfigureGraphQlTester
@Import({ TestcontainersConfiguration.class, IntegrationTest.ClockConfig.class })
public abstract class IntegrationTest {

	protected static final String UPSERT = """
			mutation($listings: [ListingInput!]!, $runId: ID) {
			  upsertListings(listings: $listings, runId: $runId) {
			    received created updated unchanged rejected
			    results { externalId status error }
			  }
			}""";

	@Autowired
	protected GraphQlTester graphQl;

	@Autowired
	protected MongoTemplate mongo;

	@Autowired
	protected MutableClock clock;

	@BeforeEach
	void cleanDatabase() {
		clock.reset();
		for (String collection : List.of(Listing.COLLECTION, IngestionRun.COLLECTION, ScrapeSchedule.COLLECTION,
				SavedSearch.COLLECTION, Alert.COLLECTION)) {
			mongo.remove(new Query(), collection);
		}
	}

	protected GraphQlTester.Response upsert(List<Map<String, Object>> listings) {
		return graphQl.document(UPSERT).variable("listings", listings).execute();
	}

	@SafeVarargs
	protected final GraphQlTester.Response upsert(Map<String, Object>... listings) {
		return upsert(List.of(listings));
	}

	protected static Map<String, Object> duproprio(String id, String city, double price) {
		return listing("duproprio", id, city, price);
	}

	protected static Map<String, Object> listing(String source, String id, String city, double price) {
		Map<String, Object> listing = new HashMap<>();
		listing.put("source", source);
		listing.put("externalId", id);
		listing.put("url", "https://example.com/" + source + "/" + id);
		listing.put("title", "Logement " + id);
		listing.put("city", city);
		listing.put("price", price);
		listing.put("roomsQc", 4.0);
		listing.put("amenities", List.of("Air Conditioning", "Parking"));
		listing.put("scrapedAt", "2026-08-05T02:34:43.741371+00:00");
		return listing;
	}

	protected static Map<String, Object> with(Map<String, Object> listing, Object... keyValues) {
		Map<String, Object> copy = new HashMap<>(listing);
		for (int i = 0; i < keyValues.length; i += 2) {
			copy.put((String) keyValues[i], keyValues[i + 1]);
		}
		return copy;
	}

	public static final class MutableClock extends Clock {

		static final Instant START = Instant.parse("2026-10-01T12:00:00Z");

		private Instant now = START;

		void reset() {
			now = START;
		}

		public Instant advance(Duration duration) {
			now = now.plus(duration);
			return now;
		}

		@Override
		public ZoneId getZone() {
			return ZoneOffset.UTC;
		}

		@Override
		public Clock withZone(ZoneId zone) {
			return this;
		}

		@Override
		public Instant instant() {
			return now;
		}

	}

	@TestConfiguration(proxyBeanMethods = false)
	static class ClockConfig {

		@Bean
		@Primary
		MutableClock testClock() {
			return new MutableClock();
		}

	}

}
