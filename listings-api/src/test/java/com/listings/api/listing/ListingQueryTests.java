package com.listings.api.listing;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.assertj.core.api.Assertions.fail;

import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.regex.Pattern;

import org.bson.Document;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;

/** The cases shared with the web app's parser (web/src/lib/query-language.test.ts). */
class ListingQueryTests {

	private static final Instant NOW = Instant.parse("2026-11-07T12:00:00Z");

	@TestFactory
	List<DynamicTest> sharedCases() throws Exception {
		List<Document> cases;
		try (InputStream in = getClass().getResourceAsStream("/query-cases.json")) {
			String json = new String(in.readAllBytes(), StandardCharsets.UTF_8);
			cases = Document.parse("{\"cases\": " + json + "}").getList("cases", Document.class);
		}
		return cases.stream().map(c -> DynamicTest.dynamicTest("«" + c.get("q") + "»", () -> {
			String q = (String) c.get("q");
			if (c.containsKey("error")) {
				try {
					ListingQuery.toMongo(q, NOW);
					fail("expected an error for " + q);
				}
				catch (ListingQuery.QueryException e) {
					assertThat(e.getMessage()).contains((String) c.get("error"));
					assertThat(List.of(e.start(), e.end())).as("span of the error")
						.containsExactly((Integer) c.get("start"), (Integer) c.get("end"));
				}
				return;
			}
			Document mongo = ListingQuery.toMongo(q, NOW);
			if (c.containsKey("mongo")) {
				assertThat(mongo.toJson()).isEqualTo(c.get("mongo", Document.class).toJson());
			}
		})).toList();
	}

	@Test
	void ageComparesTheFirstSeenDate() {
		Document young = ListingQuery.toMongo("age < 3j", NOW);
		assertThat(young).isEqualTo(new Document("firstSeenAt",
				new Document("$gt", Date.from(Instant.parse("2026-11-04T12:00:00Z")))));
		Document old = ListingQuery.toMongo("age >= 24h", NOW);
		assertThat(old).isEqualTo(new Document("firstSeenAt",
				new Document("$lte", Date.from(Instant.parse("2026-11-06T12:00:00Z")))));
	}

	@Test
	void textSearchIgnoresCaseAndAccents() {
		Document doc = ListingQuery.toMongo("texte ~ Terrassé", NOW);
		List<?> places = (List<?>) doc.get("$or");
		Pattern pattern = (Pattern) ((Document) places.get(1)).get("description");
		assertThat(pattern.matcher("Grande TERRASSE au soleil").find()).isTrue();
		assertThat(pattern.matcher("terrassé").find()).isTrue();
		assertThat(pattern.matcher("terrain").find()).isFalse();
	}

	@Test
	void keyContainsMatchesTheNormalizedKey() {
		Pattern pattern = (Pattern) ListingQuery.toMongo("quartier ~ Plateau-Mont", NOW).get("neighborhoodKey");
		assertThat(pattern.matcher("le plateau mont royal").find()).isTrue();
	}

	@Test
	void longQueriesAreRefused() {
		assertThatThrownBy(() -> ListingQuery.toMongo("animaux ".repeat(400), NOW))
			.isInstanceOf(IllegalArgumentException.class)
			.hasMessageContaining("trop longue");
	}

	@Test
	void numbers() {
		assertThat(ListingQuery.number("1800$")).isEqualTo(1800.0);
		assertThat(ListingQuery.number("4½")).isEqualTo(4.5);
		assertThat(ListingQuery.number("½")).isEqualTo(0.5);
		assertThat(ListingQuery.number("2k")).isEqualTo(2000.0);
		assertThat(ListingQuery.number("800pi2")).isEqualTo(800.0);
		assertThat(ListingQuery.number("abc")).isNull();
	}

}
