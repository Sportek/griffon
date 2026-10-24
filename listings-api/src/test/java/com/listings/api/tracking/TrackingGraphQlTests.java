package com.listings.api.tracking;

import java.time.Duration;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.data.mongodb.core.query.Query;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class TrackingGraphQlTests extends IntegrationTest {

	private static final String UPDATE = """
			mutation($id: ID!, $input: TrackingInput!) {
			  updateTracking(listingId: $id, input: $input) { favorite status notes hidden priceWhenTracked }
			}""";

	@Test
	void partialUpdatesKeepWhatTheyDoNotMention() {
		upsert(duproprio("1", "Montréal", 1500.0));
		String id = idOf("duproprio", "1");

		update(id, Map.of("favorite", true));
		update(id, Map.of("status", "VISIT_PLANNED", "notes", "  proprio sympa  "));

		graphQl.document("query($id: ID!) { listing(id: $id) { tracking { favorite status notes priceWhenTracked } } }")
			.variable("id", id)
			.execute()
			.path("listing.tracking")
			.entity(Map.class)
			.isEqualTo(Map.of("favorite", true, "status", "VISIT_PLANNED", "notes", "proprio sympa", "priceWhenTracked",
					1500.0));

		update(id, Map.of("clearStatus", true, "notes", ""));
		GraphQlTester.Response cleared = graphQl
			.document("query($id: ID!) { listing(id: $id) { tracking { favorite status notes } } }")
			.variable("id", id)
			.execute();
		cleared.path("listing.tracking.favorite").entity(Boolean.class).isEqualTo(true);
		cleared.path("listing.tracking.status").valueIsNull();
		cleared.path("listing.tracking.notes").valueIsNull();
	}

	@Test
	void anEmptiedTrackingIsDeleted() {
		upsert(duproprio("1", "Montréal", 1500.0));
		String id = idOf("duproprio", "1");
		update(id, Map.of("favorite", true));
		update(id, Map.of("favorite", false));

		assertThat(mongo.count(new Query(), Tracking.COLLECTION)).isZero();
		graphQl.document("query($id: ID!) { listing(id: $id) { tracking { favorite } } }")
			.variable("id", id)
			.execute()
			.path("listing.tracking")
			.valueIsNull();
	}

	@Test
	void trackedListingsFilterOnFavoriteAndStatusAndLeaveHiddenOut() {
		upsert(duproprio("1", "Montréal", 1500.0), duproprio("2", "Montréal", 1600.0), duproprio("3", "Laval", 1200.0));
		update(idOf("duproprio", "1"), Map.of("favorite", true));
		clock.advance(Duration.ofMinutes(1));
		update(idOf("duproprio", "2"), Map.of("status", "CONTACTED"));
		update(idOf("duproprio", "3"), Map.of("hidden", true));

		graphQl.document("{ trackedListings { listing { externalId } } }")
			.execute()
			.path("trackedListings[*].listing.externalId")
			.entityList(String.class)
			.containsExactly("2", "1");
		graphQl.document("{ trackedListings(favorite: true) { listing { externalId } } }")
			.execute()
			.path("trackedListings[*].listing.externalId")
			.entityList(String.class)
			.containsExactly("1");
		graphQl.document("{ trackedListings(statuses: [CONTACTED, VISITED]) { listing { externalId } } }")
			.execute()
			.path("trackedListings[*].listing.externalId")
			.entityList(String.class)
			.containsExactly("2");
		graphQl.document("{ trackedListings(hidden: true) { listing { externalId } } }")
			.execute()
			.path("trackedListings[*].listing.externalId")
			.entityList(String.class)
			.containsExactly("3");
	}

	@Test
	void hidingAListingHidesItsDuplicatesFromSearchAndMap() {
		upsert(located(unit("duproprio", "d1", 1000.0)));
		clock.advance(Duration.ofMinutes(1));
		upsert(located(unit("kijiji", "k1", 1020.0)), located(listing("centris", "c1", "Québec", 1400.0)));
		// Hiding the duplicate, not the canonical: the whole group must still disappear.
		update(idOf("kijiji", "k1"), Map.of("hidden", true));

		graphQl.document("{ listings(filter: { excludeHidden: true }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.containsExactly("c1");
		graphQl.document("{ mapListings(filter: { excludeHidden: true }) { id } }")
			.execute()
			.path("mapListings")
			.entityList(Object.class)
			.hasSize(1);
		graphQl.document("{ listings { totalElements } }")
			.execute()
			.path("listings.totalElements")
			.entity(Integer.class)
			.isEqualTo(3);
	}

	@Test
	void trackingAnUnknownListingIsABadRequest() {
		graphQl.document(UPDATE)
			.variable("id", "000000000000000000000000")
			.variable("input", Map.of("favorite", true))
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getMessage()).contains("unknown listing")));
	}

	private void update(String id, Map<String, Object> input) {
		graphQl.document(UPDATE).variable("id", id).variable("input", input).execute().path("updateTracking").hasValue();
	}

	private String idOf(String source, String externalId) {
		return graphQl.document("query($s: String!, $e: String!) { listingByKey(source: $s, externalId: $e) { id } }")
			.variable("s", source)
			.variable("e", externalId)
			.execute()
			.path("listingByKey.id")
			.entity(String.class)
			.get();
	}

	private static Map<String, Object> unit(String source, String id, double price) {
		return with(listing(source, id, "Québec", price), "address", "401-962 rue Antoine-du-Verdier", "bedrooms", 2.0);
	}

	private static Map<String, Object> located(Map<String, Object> listing) {
		return with(listing, "latitude", 46.81, "longitude", -71.21);
	}

}
