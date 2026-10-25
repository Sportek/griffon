package com.listings.api.listing;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class ListingGroupTests extends IntegrationTest {

	private static final String GROUPS = """
			query($filter: ListingFilter, $sort: ListingSort) {
			  listingGroups(filter: $filter, sort: $sort) {
			    totalGroups totalListings
			    content { address count totalInBuilding minPrice maxPrice listings { externalId unit } }
			  }
			}""";

	@Test
	void unitsOfOneBuildingAreGroupedAndStillFilteredOneByOne() {
		upsert(unit("c1", "1188, Avenue Union, app. 1804", 1790.0, 4.0), unit("c2", "1188 Av. Union #3201", 2400.0, 5.0),
				unit("c3", "1188 avenue Union, app. 902", 1650.0, 4.0),
				with(listing("centris", "other", "Montréal", 1500.0), "address", "50 rue Sherbrooke"));

		GraphQlTester.Response all = groups(Map.of(), "PRICE_ASC");
		all.path("listingGroups.totalGroups").entity(Integer.class).isEqualTo(2);
		all.path("listingGroups.totalListings").entity(Integer.class).isEqualTo(4);
		all.path("listingGroups.content[*].count").entityList(Integer.class).containsExactly(1, 3);
		all.path("listingGroups.content[1].address").entity(String.class).isEqualTo("1188 avenue Union");
		all.path("listingGroups.content[1].listings[*].externalId").entityList(String.class).containsExactly("c3", "c1", "c2");
		all.path("listingGroups.content[1].listings[*].unit").entityList(String.class).containsExactly("902", "1804", "3201");

		groups(Map.of("buildingKeys", List.of("1188 union|montreal")), "PRICE_ASC")
			.path("listingGroups.totalListings")
			.entity(Integer.class)
			.isEqualTo(3);

		// Each unit is matched on its own: the 5 1/2 drops out, the building keeps its size.
		GraphQlTester.Response small = groups(Map.of("maxRoomsQc", 4.0, "minPrice", 1600.0), "PRICE_ASC");
		small.path("listingGroups.content[*].count").entityList(Integer.class).containsExactly(2);
		small.path("listingGroups.content[0].totalInBuilding").entity(Integer.class).isEqualTo(3);
		small.path("listingGroups.content[0].maxPrice").entity(Double.class).isEqualTo(1790.0);
	}

	@Test
	void groupsAreOrderedByTheirBestMember() {
		upsert(unit("old", "10 rue King", 1000.0, 4.0));
		clock.advance(Duration.ofHours(1));
		upsert(with(listing("centris", "alone", "Montréal", 900.0), "address", "20 rue Queen"));
		clock.advance(Duration.ofHours(1));
		upsert(unit("new", "10 rue King, app. 2", 3000.0, 4.0));

		groups(Map.of(), "NEWEST").path("listingGroups.content[*].count").entityList(Integer.class).containsExactly(2, 1);
		groups(Map.of(), "PRICE_ASC").path("listingGroups.content[*].count").entityList(Integer.class).containsExactly(1, 2);
		groups(Map.of(), "PRICE_DESC").path("listingGroups.content[*].count").entityList(Integer.class).containsExactly(2, 1);
	}

	@Test
	void exactCoordinatesGroupListingsWithoutAddressButApproximateOnesDoNot() {
		upsert(located("e1", "exact"), located("e2", "exact"), located("a1", "approximate"), located("a2", "approximate"));

		assertThat(groups(Map.of(), "PRICE_ASC").path("listingGroups.content[*].count").entityList(Integer.class).get())
			.containsExactlyInAnyOrder(2, 1, 1);
	}

	@Test
	void aListingKnowsTheOtherUnitsOfItsBuilding() {
		upsert(unit("c1", "1188 Avenue Union, app. 1", 1790.0, 4.0), unit("c2", "1188 Avenue Union, app. 2", 1600.0, 4.0),
				unit("c3", "1188 Avenue Union, app. 3", 2000.0, 4.0));

		List<String> others = graphQl
			.document("{ listingByKey(source: \"centris\", externalId: \"c1\") { sameBuilding { externalId } } }")
			.execute()
			.path("listingByKey.sameBuilding[*].externalId")
			.entityList(String.class)
			.get();
		assertThat(others).containsExactly("c2", "c3");
	}

	@Test
	void streetAddressDropsTheUnitButKeepsTheWriting() {
		assertThat(DuplicateDetector.streetAddress("401-962 rue Antoine-du-Verdier")).isEqualTo("962 rue Antoine-du-Verdier");
		assertThat(DuplicateDetector.streetAddress("1245, Rue De Bleury, app. 5516")).isEqualTo("1245 Rue De Bleury");
		assertThat(DuplicateDetector.streetAddress("1188 Av. Union #3201")).isEqualTo("1188 Av. Union");
	}

	private GraphQlTester.Response groups(Map<String, Object> filter, String sort) {
		return graphQl.document(GROUPS).variable("filter", filter).variable("sort", sort).execute();
	}

	private static Map<String, Object> unit(String id, String address, double price, double roomsQc) {
		return with(listing("centris", id, "Montréal", price), "address", address, "roomsQc", roomsQc, "bedrooms",
				roomsQc - 2);
	}

	private static Map<String, Object> located(String id, String precision) {
		return with(listing("kijiji", id, "Montréal", 1200.0), "latitude", 45.5, "longitude", -73.6, "locationPrecision",
				precision);
	}

}
