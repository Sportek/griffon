package com.listings.api.alert;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.TimeUnit;

import com.listings.api.IntegrationTest;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.graphql.execution.ErrorType;
import org.springframework.graphql.test.tester.GraphQlTester;

import static org.assertj.core.api.Assertions.assertThat;

class AlertGraphQlTests extends IntegrationTest {

	private static final String CREATE = """
			mutation($input: SavedSearchInput!) { createSavedSearch(input: $input) { id } }""";

	private HttpServer webhook;

	private final BlockingQueue<String> received = new LinkedBlockingQueue<>();

	@BeforeEach
	void startWebhook() throws IOException {
		webhook = HttpServer.create(new InetSocketAddress("localhost", 0), 0);
		webhook.createContext("/hook", exchange -> {
			received.add(new String(exchange.getRequestBody().readAllBytes(), StandardCharsets.UTF_8));
			exchange.sendResponseHeaders(204, -1);
			exchange.close();
		});
		webhook.start();
	}

	@AfterEach
	void stopWebhook() {
		webhook.stop(0);
	}

	@Test
	void newListingsAndPriceDropsRaiseAlertsAndHitTheWebhook() throws InterruptedException {
		upsert(duproprio("c", "Montréal", 2000.0), duproprio("b", "Laval", 1500.0));
		String id = createSearch("""
				{ "name": "Montréal pas cher", "filter": { "cities": ["montreal"], "maxPrice": 1600 },
				  "webhookUrl": "%s", "webhookFormat": "DISCORD", "notifyOnPriceDrop": true }"""
			.formatted(webhookUrl()));

		clock.advance(Duration.ofMinutes(1));
		upsert(duproprio("a", "Montréal", 1500.0), duproprio("z", "Montréal", 2500.0));
		String body = received.poll(5, TimeUnit.SECONDS);
		assertThat(body).contains("\"content\"").contains("Montréal pas cher").contains("Logement a");

		clock.advance(Duration.ofMinutes(1));
		// c drops into the filter; b drops but is in Laval; a is re-seen unchanged.
		upsert(duproprio("c", "Montréal", 1550.0), duproprio("b", "Laval", 1400.0),
				duproprio("a", "Montréal", 1500.0));
		assertThat(received.poll(5, TimeUnit.SECONDS)).contains("Baisse").contains("2000 $ -> 1550 $");

		GraphQlTester.Response alerts = graphQl.document("""
				query($id: ID) { alerts(savedSearchId: $id) {
				    reason previousPrice price delivery listing { externalId } savedSearch { name } } }""")
			.variable("id", id)
			.execute();
		alerts.path("alerts[*].reason").entityList(String.class).containsExactly("PRICE_DROP", "NEW_LISTING");
		alerts.path("alerts[*].listing.externalId").entityList(String.class).containsExactly("c", "a");
		alerts.path("alerts[0].previousPrice").entity(Double.class).isEqualTo(2000.0);
		alerts.path("alerts[0].savedSearch.name").entity(String.class).isEqualTo("Montréal pas cher");
		awaitDelivery(id);
	}

	@Test
	void savedSearchEchoesItsFilterAndCurrentMatches() {
		upsert(duproprio("a", "Montréal", 1500.0), duproprio("b", "Laval", 1500.0));
		String id = createSearch("""
				{ "name": "Montréal", "filter": { "cities": ["Montréal"], "near": { "latitude": 45.5, "longitude": -73.6, "radiusKm": 50 } } }""");

		GraphQlTester.Response search = graphQl.document("""
				query($id: ID!) { savedSearch(id: $id) {
				    enabled webhookFormat filter { cities near { radiusKm } } matches { totalElements } } }""")
			.variable("id", id)
			.execute();
		search.path("savedSearch.enabled").entity(Boolean.class).isEqualTo(true);
		search.path("savedSearch.webhookFormat").entity(String.class).isEqualTo("JSON");
		search.path("savedSearch.filter.cities[0]").entity(String.class).isEqualTo("Montréal");
		search.path("savedSearch.filter.near.radiusKm").entity(Double.class).isEqualTo(50.0);
		// No coordinates on the test listings, so the radius matches nothing.
		search.path("savedSearch.matches.totalElements").entity(Integer.class).isEqualTo(0);
	}

	@Test
	void disabledSearchesStaySilentAndWithoutWebhookAlertsAreStillRecorded() {
		createSearch("{ \"name\": \"off\", \"filter\": {}, \"enabled\": false }");
		String polled = createSearch("{ \"name\": \"poll\", \"filter\": { \"sources\": [\"duproprio\"] } }");
		upsert(duproprio("a", "Laval", 1000.0));

		graphQl.document("{ alerts { delivery savedSearch { name } } }")
			.execute()
			.path("alerts[*].savedSearch.name")
			.entityList(String.class)
			.containsExactly("poll");
		graphQl.document("query($id: ID!) { savedSearch(id: $id) { lastAlertAt } }")
			.variable("id", polled)
			.execute()
			.path("savedSearch.lastAlertAt")
			.hasValue();
	}

	@Test
	void rejectsNonHttpWebhooks() {
		graphQl.document(CREATE)
			.variable("input", java.util.Map.of("name", "x", "filter", java.util.Map.of(), "webhookUrl", "file:///etc/passwd"))
			.execute()
			.errors()
			.satisfy(errors -> assertThat(errors).singleElement()
				.satisfies(e -> assertThat(e.getErrorType()).isEqualTo(ErrorType.BAD_REQUEST)));
	}

	private String createSearch(String inputJson) {
		return graphQl.document("mutation { createSavedSearch(input: " + toGraphQlLiteral(inputJson) + ") { id } }")
			.execute()
			.path("createSavedSearch.id")
			.entity(String.class)
			.get();
	}

	/** JSON object to GraphQL input literal: unquote keys, and the enum value. */
	private static String toGraphQlLiteral(String json) {
		return json.replaceAll("\"(\\w+)\"\\s*:", "$1:").replace("\"DISCORD\"", "DISCORD");
	}

	private void awaitDelivery(String savedSearchId) throws InterruptedException {
		Instant deadline = Instant.now().plusSeconds(5);
		while (Instant.now().isBefore(deadline)) {
			java.util.List<String> statuses = graphQl.document("query($id: ID) { alerts(savedSearchId: $id) { delivery } }")
				.variable("id", savedSearchId)
				.execute()
				.path("alerts[*].delivery")
				.entityList(String.class)
				.get();
			if (statuses.stream().allMatch("SENT"::equals)) {
				return;
			}
			Thread.sleep(100);
		}
		throw new AssertionError("Alerts were not all marked SENT");
	}

	private String webhookUrl() {
		return "http://localhost:" + webhook.getAddress().getPort() + "/hook";
	}

}
