package com.listings.api.listing;

import java.time.Duration;
import java.util.List;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

/** Properties for sale next to rentals: separate runs, filters, and never a mixed price. */
class SaleListingGraphQlTests extends IntegrationTest {

	private static Map<String, Object> forSale(String source, String id, String city, double price) {
		return with(listing(source, id, city, price), "listingType", "SALE", "roomsQc", null);
	}

	private String startRun(String source) {
		return graphQl.document("mutation($s: String!) { startIngestionRun(source: $s) { id } }")
			.variable("s", source)
			.execute()
			.path("startIngestionRun.id")
			.entity(String.class)
			.get();
	}

	private GraphQlTester.Response sendInRun(String runId, List<Map<String, Object>> listings) {
		return graphQl.document(UPSERT).variable("listings", listings).variable("runId", runId).execute();
	}

	private int finish(String runId) {
		return graphQl.document("""
				mutation($id: ID!) { finishIngestionRun(id: $id, status: SUCCEEDED, markUnseenInactive: true) { deactivated } }""")
			.variable("id", runId)
			.execute()
			.path("finishIngestionRun.deactivated")
			.entity(Integer.class)
			.get();
	}

	private boolean active(String source, String externalId) {
		return graphQl.document("query($s: String!, $e: String!) { listingByKey(source: $s, externalId: $e) { active } }")
			.variable("s", source)
			.variable("e", externalId)
			.execute()
			.path("listingByKey.active")
			.entity(Boolean.class)
			.get();
	}

	@Test
	void aRunOnlyTakesAndDeactivatesListingsOfItsOwnKind() {
		upsert(duproprio("rent-gone", "Laval", 1500.0), forSale("duproprio", "sale-gone", "Laval", 450000.0),
				forSale("duproprio", "sale-stays", "Laval", 500000.0));
		clock.advance(Duration.ofHours(1));

		// A complete rental run that saw none of the properties for sale leaves them alone.
		String rentRun = startRun("duproprio");
		GraphQlTester.Response batch = sendInRun(rentRun,
				List.of(duproprio("rent-new", "Laval", 1400.0), forSale("duproprio", "intruder", "Laval", 1.0)));
		batch.path("upsertListings.rejected").entity(Integer.class).isEqualTo(1);
		assertThat(batch.path("upsertListings.results[1].error").entity(String.class).get()).contains("duproprio_sale");
		assertThat(finish(rentRun)).isEqualTo(1);
		assertThat(active("duproprio", "rent-gone")).isFalse();
		assertThat(active("duproprio", "sale-gone")).isTrue();

		clock.advance(Duration.ofHours(1));
		String saleRun = startRun("duproprio_sale");
		GraphQlTester.Response saleBatch = sendInRun(saleRun,
				List.of(forSale("duproprio", "sale-stays", "Laval", 500000.0), duproprio("rent-in-sale-run", "Laval", 1.0),
						forSale("centris", "other-source", "Laval", 1.0)));
		saleBatch.path("upsertListings.rejected").entity(Integer.class).isEqualTo(2);
		assertThat(finish(saleRun)).isEqualTo(1);
		assertThat(active("duproprio", "sale-gone")).isFalse();
		assertThat(active("duproprio", "sale-stays")).isTrue();
		assertThat(active("duproprio", "rent-new")).isTrue();
	}

	@Test
	void theSweepGivesPropertiesForSaleLonger() {
		upsert(duproprio("rent", "Laval", 1500.0), forSale("duproprio", "sale", "Laval", 450000.0));
		clock.advance(Duration.ofDays(4));
		graphQl.document("mutation { sweepInactiveListings }").execute();
		assertThat(active("duproprio", "rent")).isFalse();
		assertThat(active("duproprio", "sale")).isTrue();

		clock.advance(Duration.ofDays(7));
		graphQl.document("mutation { sweepInactiveListings }").execute();
		assertThat(active("duproprio", "sale")).isFalse();
	}

	@Test
	void saleFieldsAreStoredAndFiltered() {
		Map<String, Object> condo = with(forSale("centris", "sale-1", "Montréal", 420000.0), "propertyType", "condo",
				"yearBuilt", 2009, "condoFeesMonthly", 399.0, "municipalAssessment", 390300.0,
				"municipalAssessmentYear", 2024, "municipalTaxesYearly", 2445.0, "schoolTaxesYearly", 276.0);
		Map<String, Object> triplex = with(forSale("centris", "sale-2", "Montréal", 899000.0), "propertyType",
				"duplex-triplex", "yearBuilt", 1924, "units", 3, "lotAreaSqft", 2305.0, "grossRevenueYearly", 62400.0);
		Map<String, Object> pricyCondo = with(forSale("centris", "sale-3", "Montréal", 380000.0), "propertyType",
				"condo", "condoFeesMonthly", 650.0);
		upsert(condo, triplex, pricyCondo, duproprio("rent", "Montréal", 1500.0));

		GraphQlTester.Response stored = graphQl.document("""
				{ listingByKey(source: "centris", externalId: "sale-1") {
				    listingType pricePeriod condoFeesMonthly municipalAssessment municipalAssessmentYear
				    municipalTaxesYearly schoolTaxesYearly lotAreaSqft units } }""").execute();
		stored.path("listingByKey.listingType").entity(String.class).isEqualTo("SALE");
		stored.path("listingByKey.pricePeriod").entity(String.class).isEqualTo("TOTAL");
		stored.path("listingByKey.municipalAssessment").entity(Double.class).isEqualTo(390300.0);
		stored.path("listingByKey.schoolTaxesYearly").entity(Double.class).isEqualTo(276.0);
		stored.path("listingByKey.lotAreaSqft").valueIsNull();

		assertThat(externalIds("{ listingType: SALE }")).containsExactlyInAnyOrder("sale-1", "sale-2", "sale-3");
		assertThat(externalIds("{ listingType: RENT }")).containsExactly("rent");
		// A house or a plex has no condo fees: it is not filtered out by a maximum.
		assertThat(externalIds("{ listingType: SALE, maxCondoFeesMonthly: 500 }")).containsExactlyInAnyOrder("sale-1",
				"sale-2");
		assertThat(externalIds("{ listingType: SALE, minUnits: 2 }")).containsExactly("sale-2");
		assertThat(externalIds("{ listingType: SALE, minLotAreaSqft: 2000 }")).containsExactly("sale-2");
		assertThat(externalIds("{ listingType: SALE, maxYearBuilt: 2000 }")).containsExactly("sale-2");
		assertThat(externalIds("{ listingType: SALE, maxPrice: 500000 }")).containsExactlyInAnyOrder("sale-1", "sale-3");
	}

	@Test
	void rentsAndAskingPricesAreNeverMixed() {
		// The same unit offered for rent (kijiji) and for sale (centris): two offers, not duplicates.
		upsert(with(listing("kijiji", "k", "Montréal", 2000.0), "address", "100 rue Principale, app. 3", "bedrooms", 2.0),
				with(forSale("centris", "sale-c", "Montréal", 500000.0), "address", "100 rue Principale, app. 3",
						"bedrooms", 2.0),
				with(listing("duproprio", "d", "Montréal", 1800.0), "address", "100 rue Principale, app. 4", "bedrooms",
						1.0));
		GraphQlTester.Response rental = graphQl.document(
				"{ listingByKey(source: \"kijiji\", externalId: \"k\") { duplicateOf { id } duplicates { id } sameBuilding { externalId } } }")
			.execute();
		rental.path("listingByKey.duplicateOf").valueIsNull();
		rental.path("listingByKey.duplicates").entityList(Object.class).hasSize(0);
		rental.path("listingByKey.sameBuilding[*].externalId").entityList(String.class).containsExactly("d");
		GraphQlTester.Response groups = graphQl
			.document("{ listingGroups(filter: { listingType: RENT }) { content { count totalInBuilding minPrice maxPrice } } }")
			.execute();
		groups.path("listingGroups.content[0].totalInBuilding").entity(Integer.class).isEqualTo(2);
		groups.path("listingGroups.content[0].maxPrice").entity(Double.class).isEqualTo(2000.0);

		// Stats without a type average the rents only, and give each type its own prices.
		GraphQlTester.Response stats = graphQl
			.document("{ listingStats { count avgPrice maxPrice byListingType { key count maxPrice } } }")
			.execute();
		stats.path("listingStats.count").entity(Integer.class).isEqualTo(3);
		stats.path("listingStats.maxPrice").entity(Double.class).isEqualTo(2000.0);
		stats.path("listingStats.byListingType[*].key").entityList(String.class).containsExactly("RENT", "SALE");
		stats.path("listingStats.byListingType[1].maxPrice").entity(Double.class).isEqualTo(500000.0);
	}

	@Test
	void aListingThatChangesTypeStartsAFreshPriceHistory() {
		upsert(listing("centris", "1", "Montréal", 2000.0));
		clock.advance(Duration.ofHours(1));
		upsert(forSale("centris", "1", "Montréal", 450000.0));
		upsert(forSale("centris", "1", "Montréal", 440000.0));
		graphQl.document("{ listingByKey(source: \"centris\", externalId: \"1\") { listingType priceHistory { price } } }")
			.execute()
			.path("listingByKey.priceHistory[*].price")
			.entityList(Double.class)
			.containsExactly(450000.0, 440000.0);
	}

	@Test
	void aSavedSearchWithoutTypeStaysARentalSearch() {
		graphQl.document("mutation($input: SavedSearchInput!) { createSavedSearch(input: $input) { id } }")
			.variable("input", Map.of("name", "Laval", "filter", Map.of("cities", List.of("laval"))))
			.execute();
		clock.advance(Duration.ofMinutes(1));
		upsert(duproprio("rent", "Laval", 1500.0), forSale("duproprio", "sale", "Laval", 450000.0));

		GraphQlTester.Response alerts = graphQl
			.document("{ alerts { listing { externalId } } savedSearches { matches { totalElements } } }")
			.execute();
		alerts.path("alerts[*].listing.externalId").entityList(String.class).containsExactly("rent");
		alerts.path("savedSearches[0].matches.totalElements").entity(Integer.class).isEqualTo(1);
	}

	private List<String> externalIds(String filter) {
		return graphQl.document("{ listings(filter: " + filter + ") { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.get();
	}

}
