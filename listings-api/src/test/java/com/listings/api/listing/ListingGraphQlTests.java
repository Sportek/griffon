package com.listings.api.listing;

import java.time.Duration;
import java.time.Instant;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class ListingGraphQlTests extends IntegrationTest {

	@Test
	void storesScraperEnrichmentAndFiltersOnProximity() {
		Map<String, Object> proximity = Map.of("method", "estimate", "computed_at", "2026-10-01T00:00:00Z",
				"nearest_metro", Map.of("name", "Jarry", "walk_minutes", 6.5), "nearest_rem",
				Map.of("name", "Canora", "walk_minutes", 25.0), "essentials",
				Map.of("grocery", Map.of("count", 3), "pharmacy", Map.of("count", 0)));
		Map<String, Object> villeray = with(duproprio("1", "Montréal", 1500.0), "neighborhood",
				"Villeray/Saint-Michel/Parc-Extension", "propertyType", "apartment", "yearBuilt", 1960, "extra",
				Map.of("floor", 3, "heated", true), "proximity", proximity);
		Map<String, Object> laval = with(duproprio("2", "Laval", 1200.0), "proximity",
				Map.of("nearest_metro", Map.of("walk_minutes", 30.0)));
		upsert(villeray, laval);

		graphQl.document("""
				{ listings(filter: { maxTransitWalkMinutes: 10, nearbyCategories: ["grocery"],
				                     neighborhoods: ["villeray saint-michel parc-extension"], propertyTypes: ["apartment"] }) {
				    content { externalId } } }""")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("1");
		graphQl.document("{ listings(filter: { nearbyCategories: [\"pharmacy\"] }) { totalElements } }")
			.execute()
			.path("listings.totalElements")
			.entity(Integer.class)
			.isEqualTo(0);

		GraphQlTester.Response stored = graphQl
			.document("{ listingByKey(source: \"duproprio\", externalId: \"1\") { metroWalkMinutes remWalkMinutes yearBuilt extra proximity } }")
			.execute();
		stored.path("listingByKey.metroWalkMinutes").entity(Double.class).isEqualTo(6.5);
		stored.path("listingByKey.yearBuilt").entity(Integer.class).isEqualTo(1960);
		stored.path("listingByKey.extra.floor").entity(Integer.class).isEqualTo(3);
		stored.path("listingByKey.proximity.nearest_metro.name").entity(String.class).isEqualTo("Jarry");

		// Re-enriching only bumps proximity.computed_at: not a content change.
		Map<String, Object> reEnriched = new HashMap<>(proximity);
		reEnriched.put("computed_at", "2026-10-02T00:00:00Z");
		upsert(with(villeray, "proximity", reEnriched)).path("upsertListings.unchanged")
			.entity(Integer.class)
			.isEqualTo(1);
	}

	@Test
	void upsertIsIdempotentAndTracksPriceChanges() {
		Map<String, Object> listing = duproprio("1", "Montréal", 1500.0);

		upsert(List.of(listing)).path("upsertListings.created").entity(Integer.class).isEqualTo(1);
		clock.advance(Duration.ofHours(1));
		upsert(List.of(listing)).path("upsertListings.unchanged").entity(Integer.class).isEqualTo(1);
		clock.advance(Duration.ofHours(1));
		upsert(List.of(duproprio("1", "Montréal", 1400.0))).path("upsertListings.updated")
			.entity(Integer.class)
			.isEqualTo(1);

		GraphQlTester.Response response = graphQl.document("""
				{ listingByKey(source: "duproprio", externalId: "1") {
				    price seenCount firstSeenAt lastSeenAt priceHistory { price } } }""").execute();
		response.path("listingByKey.price").entity(Double.class).isEqualTo(1400.0);
		response.path("listingByKey.seenCount").entity(Integer.class).isEqualTo(3);
		response.path("listingByKey.priceHistory[*].price").entityList(Double.class).containsExactly(1500.0, 1400.0);
		String firstSeen = response.path("listingByKey.firstSeenAt").entity(String.class).get();
		String lastSeen = response.path("listingByKey.lastSeenAt").entity(String.class).get();
		assertThat(Instant.parse(lastSeen)).isEqualTo(Instant.parse(firstSeen).plus(Duration.ofHours(2)));
	}

	@Test
	void invalidListingsAreRejectedWithoutFailingTheBatch() {
		Map<String, Object> bad = new HashMap<>(duproprio("2", "Laval", 900.0));
		bad.put("latitude", 123.0);

		GraphQlTester.Response response = upsert(List.of(duproprio("1", "Laval", 900.0), bad));
		response.path("upsertListings.created").entity(Integer.class).isEqualTo(1);
		response.path("upsertListings.rejected").entity(Integer.class).isEqualTo(1);
		assertThat(response.path("upsertListings.results[1].error").entity(String.class).get()).contains("latitude");
	}

	@Test
	void filtersAreAccentAndCaseInsensitive() {
		upsert(List.of(duproprio("1", "Montréal", 1500.0), duproprio("2", "Laval", 900.0),
				duproprio("3", "MONTREAL", 2500.0)));

		graphQl.document("""
				{ listings(filter: { cities: ["montreal"], maxPrice: 2000, amenities: ["air conditioning"] }) {
				    totalElements content { externalId } } }""")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("1");
	}

	@Test
	void textAndGeoFilters() {
		Map<String, Object> plateau = new HashMap<>(duproprio("1", "Montréal", 1500.0));
		plateau.put("latitude", 45.5225);
		plateau.put("longitude", -73.5800);
		plateau.put("description", "Superbe logement près du parc La Fontaine");
		Map<String, Object> quebec = new HashMap<>(duproprio("2", "Québec", 1200.0));
		quebec.put("latitude", 46.8139);
		quebec.put("longitude", -71.2080);
		upsert(List.of(plateau, quebec));

		graphQl.document("""
				{ listings(filter: { near: { latitude: 45.50, longitude: -73.57, radiusKm: 10 } }) {
				    content { externalId } } }""")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("1");

		graphQl.document("{ listings(filter: { text: \"fontaine\" }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("1");
	}

	@Test
	void latestReturnsMostRecentlyDiscoveredFirst() {
		upsert(List.of(duproprio("old", "Laval", 900.0)));
		Instant cutoff = clock.advance(Duration.ofDays(1));
		upsert(List.of(duproprio("new1", "Laval", 900.0)));
		clock.advance(Duration.ofMinutes(1));
		upsert(List.of(duproprio("new2", "Laval", 900.0)));
		// Re-seeing an old listing must not make it "latest".
		upsert(List.of(duproprio("old", "Laval", 900.0)));

		graphQl.document("query($since: DateTime) { latestListings(limit: 10, since: $since) { externalId } }")
			.variable("since", cutoff.toString())
			.execute()
			.path("latestListings[*].externalId")
			.entityList(String.class)
			.containsExactly("new2", "new1");
	}

	@Test
	void paginationAndStats() {
		upsert(List.of(duproprio("1", "Laval", 1000.0), duproprio("2", "Laval", 2000.0),
				duproprio("3", "Montréal", 3000.0)));

		GraphQlTester.Response page = graphQl
			.document("{ listings(sort: PRICE_DESC, page: 1, size: 2) { totalElements totalPages hasNext content { price } } }")
			.execute();
		page.path("listings.totalElements").entity(Integer.class).isEqualTo(3);
		page.path("listings.totalPages").entity(Integer.class).isEqualTo(2);
		page.path("listings.hasNext").entity(Boolean.class).isEqualTo(false);
		page.path("listings.content[*].price").entityList(Double.class).containsExactly(1000.0);

		GraphQlTester.Response stats = graphQl
			.document("{ listingStats { count avgPrice byCity { key count avgPrice } byRoomsQc { key count } } }")
			.execute();
		stats.path("listingStats.count").entity(Integer.class).isEqualTo(3);
		stats.path("listingStats.avgPrice").entity(Double.class).isEqualTo(2000.0);
		stats.path("listingStats.byCity[0].key").entity(String.class).isEqualTo("Laval");
		stats.path("listingStats.byCity[0].avgPrice").entity(Double.class).isEqualTo(1500.0);
		stats.path("listingStats.byRoomsQc[0].key").entity(String.class).isEqualTo("4");
	}

	@Test
	void invalidPageSizeIsABadRequest() {
		graphQl.document("{ listings(size: 1000) { totalElements } }")
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));
	}


	@Test
	void mapListingsAndBoundingBoxReturnOnlyLocatedListingsInside() {
		Map<String, Object> plateau = with(duproprio("1", "Montréal", 1500.0), "latitude", 45.5225, "longitude", -73.58,
				"locationPrecision", "exact");
		Map<String, Object> quebec = with(duproprio("2", "Québec", 1200.0), "latitude", 46.8139, "longitude", -71.208);
		Map<String, Object> unlocated = duproprio("3", "Montréal", 1300.0);
		upsert(plateau, quebec, unlocated);

		graphQl.document("{ mapListings { price } }")
			.execute()
			.path("mapListings[*].price")
			.entityList(Double.class)
			.contains(1500.0, 1200.0)
			.hasSize(2);
		GraphQlTester.Response island = graphQl.document("""
				{ mapListings(filter: { within: { south: 45.4, west: -73.98, north: 45.71, east: -73.47 } }) {
				    latitude longitude price roomsQc locationPrecision } }""").execute();
		island.path("mapListings[0]")
			.entity(Map.class)
			.isEqualTo(Map.of("latitude", 45.5225, "longitude", -73.58, "price", 1500.0, "roomsQc", 4.0,
					"locationPrecision", "exact"));
		island.path("mapListings").entityList(Object.class).hasSize(1);

		graphQl.document("""
				{ listings(filter: { within: { south: 46.7, west: -71.4, north: 46.9, east: -71.1 } }) {
				    content { externalId } } }""")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("2");
	}

	@Test
	void invalidBoundingBoxIsABadRequest() {
		graphQl.document("{ mapListings(filter: { within: { south: 46, west: -73, north: 45, east: -72 } }) { id } }")
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));
	}

	@Test
	void priceBenchmarkComparesWithTheNeighbourhoodThenTheCity() {
		for (int i = 0; i < 5; i++) {
			upsert(with(duproprio("r" + i, "Montréal", 1400.0 + i * 50), "neighborhood", "Rosemont"));
		}
		upsert(with(duproprio("target", "Montréal", 1380.0), "neighborhood", "Rosemont"),
				with(duproprio("plateau", "Montréal", 2000.0), "neighborhood", "Le Plateau"),
				with(duproprio("big", "Montréal", 3000.0), "neighborhood", "Rosemont", "roomsQc", 6.0));

		Map<?, ?> rosemont = benchmark("target");
		assertThat(rosemont.get("scope")).isEqualTo("NEIGHBORHOOD");
		assertThat(rosemont.get("area")).isEqualTo("Rosemont");
		assertThat(rosemont.get("sampleSize")).isEqualTo(5);
		assertThat(rosemont.get("median")).isEqualTo(1500.0);
		assertThat(rosemont.get("deltaPercent")).isEqualTo(-8.0);

		// One comparable in Le Plateau: not enough, so it compares with the whole city.
		Map<?, ?> plateau = benchmark("plateau");
		assertThat(plateau.get("scope")).isEqualTo("CITY");
		assertThat(plateau.get("sampleSize")).isEqualTo(6);

		graphQl.document("{ listingByKey(source: \"duproprio\", externalId: \"big\") { priceBenchmark { median } } }")
			.execute()
			.path("listingByKey.priceBenchmark")
			.valueIsNull();
	}


	@Test
	void canonicalServiceKeysMatchEverySourceSpelling() {
		upsert(with(listing("kijiji", "k1", "Montréal", 1500.0), "utilitiesIncluded", List.of("Heat", "Water")),
				with(duproprio("d1", "Montréal", 1400.0), "utilitiesIncluded", List.of("Heated", "Hot Water"),
						"amenities", List.of("Balcony/Terrace")),
				with(listing("logis_quebec", "l1", "Montréal", 1300.0), "utilitiesIncluded", List.of("Chauffage")),
				with(listing("centris", "c1", "Montréal", 1200.0), "utilitiesIncluded", List.of("Électricité")));

		graphQl.document("{ listings(filter: { utilitiesIncluded: [\"chauffé\"] }) { totalElements } }")
			.execute()
			.path("listings.totalElements")
			.entity(Integer.class)
			.isEqualTo(0);
		graphQl.document("{ listings(filter: { utilitiesIncluded: [\"chauffage\"] }, sort: PRICE_ASC) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("l1", "d1", "k1");
		graphQl.document("{ listings(filter: { utilitiesIncluded: [\"eau chaude\"], amenities: [\"balcon\"] }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("d1");
		graphQl.document("{ listings(filter: { utilitiesIncluded: [\"électricité\"] }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("c1");
	}


	@Test
	void aScrapeWithoutEnrichmentKeepsWhatAnEnrichedOneComputed() {
		Map<String, Object> plain = with(duproprio("1", "Montréal", 1500.0), "address", "4202 rue Radisson");
		Map<String, Object> enriched = with(plain, "latitude", 45.59, "longitude", -73.53, "locationPrecision",
				"geocoded_address", "proximity", Map.of("nearest_metro", Map.of("name", "Radisson", "walk_minutes", 3.0)));
		upsert(enriched);
		clock.advance(Duration.ofHours(1));

		upsert(plain).path("upsertListings.unchanged").entity(Integer.class).isEqualTo(1);
		GraphQlTester.Response kept = graphQl
			.document("{ listingByKey(source: \"duproprio\", externalId: \"1\") { latitude locationPrecision metroWalkMinutes proximity } }")
			.execute();
		kept.path("listingByKey.latitude").entity(Double.class).isEqualTo(45.59);
		kept.path("listingByKey.locationPrecision").entity(String.class).isEqualTo("geocoded_address");
		kept.path("listingByKey.metroWalkMinutes").entity(Double.class).isEqualTo(3.0);
		graphQl.document("{ mapListings { id } }").execute().path("mapListings").entityList(Object.class).hasSize(1);

		// A real change still goes through, and keeps the enrichment too.
		upsert(with(plain, "price", 1400.0)).path("upsertListings.updated").entity(Integer.class).isEqualTo(1);
		graphQl.document("{ listingByKey(source: \"duproprio\", externalId: \"1\") { metroWalkMinutes } }")
			.execute()
			.path("listingByKey.metroWalkMinutes")
			.entity(Double.class)
			.isEqualTo(3.0);
	}

	private Map<?, ?> benchmark(String externalId) {
		return graphQl.document("query($e: String!) { listingByKey(source: \"duproprio\", externalId: $e) { priceBenchmark { scope area median sampleSize deltaPercent } } }")
			.variable("e", externalId)
			.execute()
			.path("listingByKey.priceBenchmark")
			.entity(Map.class)
			.get();
	}

}
