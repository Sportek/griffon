package com.listings.api.alert;

import java.time.Duration;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;

import com.listings.api.listing.Listing;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.http.MediaType;
import org.springframework.http.client.SimpleClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClient;
import tools.jackson.databind.json.JsonMapper;

/** Posts alerts to a saved search's webhook in the background and records the outcome. */
@Component
class WebhookNotifier {

	private static final Logger log = LoggerFactory.getLogger(WebhookNotifier.class);

	/** Discord rejects messages over 2000 characters. */
	private static final int DISCORD_MAX_LENGTH = 2000;

	private final MongoTemplate mongo;

	private final Executor executor;

	private final RestClient http;

	private final JsonMapper json;

	WebhookNotifier(MongoTemplate mongo, @Qualifier("applicationTaskExecutor") Executor executor, JsonMapper json) {
		this.mongo = mongo;
		this.json = json;
		this.executor = executor;
		SimpleClientHttpRequestFactory requestFactory = new SimpleClientHttpRequestFactory();
		requestFactory.setConnectTimeout(Duration.ofSeconds(5));
		requestFactory.setReadTimeout(Duration.ofSeconds(10));
		this.http = RestClient.builder().requestFactory(requestFactory).build();
	}

	void send(SavedSearch search, List<Alert> alerts, Map<String, Listing> listings) {
		executor.execute(() -> deliver(search, alerts, listings));
	}

	private void deliver(SavedSearch search, List<Alert> alerts, Map<String, Listing> listings) {
		Alert.Delivery outcome;
		String error = null;
		try {
			http.post()
				.uri(search.webhookUrl())
				.contentType(MediaType.APPLICATION_JSON)
				// Serialized up front so the request carries a Content-Length (some endpoints reject chunked bodies).
				.body(json.writeValueAsBytes(payload(search, alerts, listings)))
				.retrieve()
				.toBodilessEntity();
			outcome = Alert.Delivery.SENT;
		}
		catch (RuntimeException ex) {
			log.warn("Webhook delivery failed for saved search {}: {}", search.id(), ex.getMessage());
			outcome = Alert.Delivery.FAILED;
			error = ex.getMessage();
		}
		List<String> ids = alerts.stream().map(Alert::id).toList();
		mongo.updateMulti(Query.query(Criteria.where("_id").in(ids)),
				new Update().set("delivery", outcome).set("deliveryError", error), Alert.class);
	}

	static Object payload(SavedSearch search, List<Alert> alerts, Map<String, Listing> listings) {
		return switch (search.webhookFormat()) {
			case SLACK -> Map.of("text", text(search, alerts, listings, Integer.MAX_VALUE));
			case DISCORD -> Map.of("content", text(search, alerts, listings, DISCORD_MAX_LENGTH));
			case JSON -> json(search, alerts, listings);
		};
	}

	private static Map<String, Object> json(SavedSearch search, List<Alert> alerts, Map<String, Listing> listings) {
		List<Map<String, Object>> items = new ArrayList<>();
		for (Alert alert : alerts) {
			Map<String, Object> item = new LinkedHashMap<>();
			item.put("reason", alert.reason());
			item.put("previousPrice", alert.previousPrice());
			item.put("price", alert.price());
			Listing l = listings.get(alert.listingId());
			if (l != null) {
				Map<String, Object> listing = new LinkedHashMap<>();
				listing.put("id", l.id());
				listing.put("source", l.source());
				listing.put("title", l.title());
				listing.put("price", l.price());
				listing.put("address", l.address());
				listing.put("neighborhood", l.neighborhood());
				listing.put("city", l.city());
				listing.put("roomsQc", l.roomsQc());
				listing.put("bedrooms", l.bedrooms());
				listing.put("url", l.url());
				item.put("listing", listing);
			}
			items.add(item);
		}
		return Map.of("savedSearch", Map.of("id", search.id(), "name", search.name()), "alerts", items);
	}

	private static String text(SavedSearch search, List<Alert> alerts, Map<String, Listing> listings,
			int maxLength) {
		StringBuilder text = new StringBuilder("Recherche « ").append(search.name()).append(" »\n");
		int written = 0;
		for (Alert alert : alerts) {
			Listing l = listings.get(alert.listingId());
			if (l == null) {
				continue;
			}
			String where = (l.neighborhood() != null) ? l.neighborhood() : l.city();
			String line = switch (alert.reason()) {
				case NEW_LISTING -> "Nouveau : %s, %s $, %s %s".formatted(l.title(), price(alert.price()), where,
						l.url());
				case PRICE_DROP -> "Baisse : %s, %s $ -> %s $, %s %s".formatted(l.title(), price(alert.previousPrice()),
						price(alert.price()), where, l.url());
			};
			String more = "\n... et " + (alerts.size() - written) + " autres";
			if (text.length() + line.length() + 1 + more.length() > maxLength) {
				return text.append(more.substring(1)).toString();
			}
			text.append(line).append('\n');
			written++;
		}
		return text.toString();
	}

	private static String price(Double price) {
		return (price == null) ? "?" : String.valueOf(Math.round(price));
	}

}
