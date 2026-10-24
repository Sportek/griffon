package com.listings.api.listing;

import java.time.Duration;
import java.util.Map;

import com.listings.api.IntegrationTest;
import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;

class DuplicateDetectorTests extends IntegrationTest {

	@Test
	void keyIgnoresUnitStreetTypeAccentsAndLanguage() {
		assertThat(DuplicateDetector.key("401-962 rue Antoine-du-Verdier", 2.0))
			.isEqualTo(DuplicateDetector.key("962 Antoine du Verdier Street", 2.0))
			.isEqualTo("962 antoine verdier|2");
		assertThat(DuplicateDetector.key("962 boul. René-Lévesque Ouest, app. 5", 1.0))
			.isEqualTo(DuplicateDetector.key("962 Rene Levesque Blvd W", 1.0));
		assertThat(DuplicateDetector.key("962 rue Antoine-du-Verdier", 2.0))
			.isNotEqualTo(DuplicateDetector.key("962 rue Antoine-du-Verdier", 3.0));
	}

	@Test
	void keyKeepsOnlyNumberAndStreetOfRealSourceAddresses() {
		// Kijiji appends city/province/postal code, Centris puts a comma after the number,
		// realtor.ca uses "#unit": all must reduce to the same street key.
		assertThat(DuplicateDetector.key("36 rue de l'Aqueduc, Varennes, QC, J3X 1P4", 2.0))
			.isEqualTo(DuplicateDetector.key("36, Rue de l'Aqueduc, app. 3", 2.0))
			.isEqualTo(DuplicateDetector.key("36 Aqueduc Street", 2.0))
			.isEqualTo("36 aqueduc|2");
		assertThat(DuplicateDetector.key("1188 Av. Union #3201", 1.0))
			.isEqualTo(DuplicateDetector.key("1188, Avenue Union, app. 3201", 1.0))
			.isEqualTo("1188 union|1");
	}

	@Test
	void unitNumberIsExtractedFromEveryAddressStyle() {
		assertThat(DuplicateDetector.unit("401-962 rue Antoine-du-Verdier")).isEqualTo("401");
		assertThat(DuplicateDetector.unit("1245, Rue De Bleury, app. 5516")).isEqualTo("5516");
		assertThat(DuplicateDetector.unit("1188 Av. Union #3201")).isEqualTo("3201");
		assertThat(DuplicateDetector.unit("36 rue de l'Aqueduc, Varennes, QC, J3X 1P4")).isNull();
	}

	@Test
	void differentKnownUnitsOfOneBuildingAreNotDuplicates() {
		// Real case: same building, same bedrooms, close prices, but two different apartments.
		upsert(unit("centris", "c1", "1188, Avenue Union, app. 1804", 1790.0));
		upsert(unit("realtor_ca", "r1", "1188 Av. Union #3201", 1800.0),
				unit("kijiji", "k1", "1188 avenue Union, Montréal, QC", 1800.0));

		assertThat(duplicateOf("realtor_ca", "r1")).isNull();
		// No unit on the Kijiji ad: it may be either, so it is still grouped with the reference.
		assertThat(duplicateOf("kijiji", "k1")).isEqualTo("c1");
	}

	@Test
	void extraKeysAreMadeSafeForMongo() {
		upsert(with(duproprio("1", "Laval", 900.0), "extra",
				Map.of("Superficie (pi.ca.)", 700, "$weird", Map.of("a.b", true))));

		Map<String, Object> extra = graphQl.document("{ listingByKey(source: \"duproprio\", externalId: \"1\") { extra } }")
			.execute()
			.path("listingByKey.extra")
			.entity(Map.class)
			.get();
		assertThat(extra).containsEntry("Superficie (pi_ca_)", 700).containsEntry("_weird", Map.of("a_b", true));
	}

	@Test
	void keyNeedsACivicAddressAndBedrooms() {
		assertThat(DuplicateDetector.key("Le Rouge Condos", 1.0)).isNull();
		assertThat(DuplicateDetector.key(". 36e avenue Ouest", 1.0)).isNull();
		assertThat(DuplicateDetector.key("962 rue Verdier", null)).isNull();
	}

	@Test
	void groupsSameUnitAcrossSources() {
		upsert(unit("duproprio", "d1", "401-962 rue Antoine-du-Verdier", 1000.0));
		clock.advance(Duration.ofMinutes(1));
		upsert(unit("rentals_ca", "r1", "962 Antoine du Verdier Street", 1050.0));
		clock.advance(Duration.ofMinutes(1));
		// Too expensive to be the same unit, and another same-source unit.
		upsert(unit("rentals_ca", "r2", "962 Antoine du Verdier Street", 1600.0),
				unit("kijiji", "k1", "962, rue Antoine-du-Verdier", 990.0));

		assertThat(duplicateOf("rentals_ca", "r1")).isEqualTo("d1");
		assertThat(duplicateOf("kijiji", "k1")).isEqualTo("d1");
		assertThat(duplicateOf("rentals_ca", "r2")).isNull();
		assertThat(duplicateOf("duproprio", "d1")).isNull();

		graphQl.document("{ listingByKey(source: \"duproprio\", externalId: \"d1\") { duplicates { externalId } } }")
			.execute()
			.path("listingByKey.duplicates[*].externalId")
			.entityList(String.class)
			.hasSize(2)
			.contains("r1", "k1");
		graphQl.document("{ listings(filter: { excludeDuplicates: true }) { content { externalId } } }")
			.execute()
			.path("listings.content[*].externalId")
			.entityList(String.class)
			.hasSize(2)
			.contains("d1", "r2");
	}

	@Test
	void inactiveCanonicalHandsOverToActiveDuplicate() {
		upsert(unit("duproprio", "d1", "962 rue Antoine-du-Verdier", 1000.0));
		clock.advance(Duration.ofMinutes(1));
		upsert(unit("rentals_ca", "r1", "962 Antoine du Verdier Street", 1050.0));
		assertThat(duplicateOf("rentals_ca", "r1")).isEqualTo("d1");

		clock.advance(Duration.ofDays(4));
		upsert(unit("rentals_ca", "r1", "962 Antoine du Verdier Street", 1050.0));
		graphQl.document("mutation { sweepInactiveListings }").execute();

		assertThat(duplicateOf("rentals_ca", "r1")).isNull();
		assertThat(duplicateOf("duproprio", "d1")).isEqualTo("r1");
	}

	private String duplicateOf(String source, String externalId) {
		Map<?, ?> listing = graphQl
			.document("query($s: String!, $e: String!) { listingByKey(source: $s, externalId: $e) { duplicateOf { externalId } } }")
			.variable("s", source)
			.variable("e", externalId)
			.execute()
			.path("listingByKey")
			.entity(Map.class)
			.get();
		return (listing.get("duplicateOf") instanceof Map<?, ?> canonical) ? (String) canonical.get("externalId") : null;
	}

	private static Map<String, Object> unit(String source, String id, String address, double price) {
		return with(listing(source, id, "Québec", price), "address", address, "bedrooms", 2.0);
	}

}
