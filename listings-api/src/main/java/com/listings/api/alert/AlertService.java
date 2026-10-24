package com.listings.api.alert;

import java.net.URI;
import java.time.Clock;
import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.function.Function;
import java.util.stream.Collectors;

import com.listings.api.listing.Listing;
import com.listings.api.listing.ListingFilter;
import com.listings.api.listing.ListingFilterMapper;
import com.listings.api.listing.ListingIngestionService.ListingsIngested;
import com.listings.api.listing.ListingIngestionService.PriceDrop;
import org.bson.Document;
import org.bson.types.ObjectId;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import org.springframework.context.event.EventListener;
import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.BasicQuery;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.data.mongodb.core.query.Update;
import org.springframework.stereotype.Service;

@Service
public class AlertService {

	private static final Logger log = LoggerFactory.getLogger(AlertService.class);

	static final int MAX_LIMIT = 200;

	private final MongoTemplate mongo;

	private final WebhookNotifier notifier;

	private final Clock clock;

	AlertService(MongoTemplate mongo, WebhookNotifier notifier, Clock clock) {
		this.mongo = mongo;
		this.notifier = notifier;
		this.clock = clock;
	}

	public SavedSearch create(SavedSearchInput input) {
		return mongo.insert(toSavedSearch(null, input, clock.instant(), null));
	}

	public SavedSearch update(String id, SavedSearchInput input) {
		SavedSearch existing = find(id);
		if (existing == null) {
			throw new IllegalArgumentException("Unknown saved search: " + id);
		}
		return mongo.save(toSavedSearch(id, input, existing.createdAt(), existing.lastAlertAt()));
	}

	public boolean delete(String id) {
		mongo.remove(Query.query(Criteria.where("savedSearchId").is(id)), Alert.class);
		return mongo.remove(Query.query(Criteria.where("_id").is(id)), SavedSearch.class).getDeletedCount() > 0;
	}

	public SavedSearch find(String id) {
		return mongo.findById(id, SavedSearch.class);
	}

	public List<SavedSearch> findAll() {
		return mongo.find(new Query().with(Sort.by("createdAt")), SavedSearch.class);
	}

	public List<Alert> alerts(String savedSearchId, Instant since, int limit) {
		if (limit < 1 || limit > MAX_LIMIT) {
			throw new IllegalArgumentException("limit must be between 1 and " + MAX_LIMIT);
		}
		Criteria criteria = new Criteria();
		if (savedSearchId != null) {
			criteria = criteria.and("savedSearchId").is(savedSearchId);
		}
		if (since != null) {
			criteria = criteria.and("createdAt").gte(since);
		}
		Query query = Query.query(criteria).with(Sort.by(Sort.Direction.DESC, "createdAt", "_id")).limit(limit);
		return mongo.find(query, Alert.class);
	}

	/**
	 * Matches every enabled saved search against what was just ingested. Runs inside the
	 * ingestion request (one indexed query per search); webhook delivery is asynchronous.
	 */
	@EventListener
	void onIngested(ListingsIngested event) {
		for (SavedSearch search : mongo.find(Query.query(Criteria.where("enabled").is(true)), SavedSearch.class)) {
			try {
				raiseAlerts(search, event);
			}
			catch (RuntimeException ex) {
				// A broken saved search must not fail the scraper's batch.
				log.warn("Saved search {} could not be evaluated", search.id(), ex);
			}
		}
	}

	private void raiseAlerts(SavedSearch search, ListingsIngested event) {
		Instant now = clock.instant();
		Alert.Delivery delivery = (search.webhookUrl() != null) ? Alert.Delivery.PENDING : Alert.Delivery.NONE;
		List<Alert> alerts = new ArrayList<>();

		Map<String, Listing> created = matching(search.filter(), event.createdIds());
		created.values()
			.forEach(l -> alerts.add(new Alert(null, search.id(), l.id(), Alert.Reason.NEW_LISTING, null, l.price(), now,
					delivery, null)));

		if (search.notifyOnPriceDrop() && !event.priceDrops().isEmpty()) {
			Map<String, Listing> dropped = matching(search.filter(),
					event.priceDrops().stream().map(PriceDrop::listingId).toList());
			for (PriceDrop drop : event.priceDrops()) {
				if (dropped.containsKey(drop.listingId())) {
					alerts.add(new Alert(null, search.id(), drop.listingId(), Alert.Reason.PRICE_DROP,
							drop.previousPrice(), drop.price(), now, delivery, null));
				}
			}
		}
		if (alerts.isEmpty()) {
			return;
		}

		List<Alert> saved = new ArrayList<>(mongo.insertAll(alerts));
		mongo.updateFirst(Query.query(Criteria.where("_id").is(search.id())), Update.update("lastAlertAt", now),
				SavedSearch.class);
		if (search.webhookUrl() != null) {
			Map<String, Listing> listings = new HashMap<>(created);
			Set<String> missing = new HashSet<>();
			saved.stream().map(Alert::listingId).filter(id -> !listings.containsKey(id)).forEach(missing::add);
			listings.putAll(byId(missing));
			notifier.send(search, saved, listings);
		}
	}

	/** The listings among {@code ids} that the filter matches, by id. */
	private Map<String, Listing> matching(ListingFilter filter, List<String> ids) {
		if (ids.isEmpty()) {
			return Map.of();
		}
		Document query = ListingFilterMapper.toQuery(filter);
		query.append("_id", new Document("$in", ids.stream().map(ObjectId::new).toList()));
		return mongo.find(new BasicQuery(query), Listing.class)
			.stream()
			.collect(Collectors.toMap(Listing::id, Function.identity()));
	}

	private Map<String, Listing> byId(Set<String> ids) {
		if (ids.isEmpty()) {
			return Map.of();
		}
		return mongo.find(Query.query(Criteria.where("_id").in(ids)), Listing.class)
			.stream()
			.collect(Collectors.toMap(Listing::id, Function.identity()));
	}

	private static SavedSearch toSavedSearch(String id, SavedSearchInput input, Instant createdAt,
			Instant lastAlertAt) {
		if (input.name() == null || input.name().isBlank()) {
			throw new IllegalArgumentException("name must not be blank");
		}
		if (input.filter() == null) {
			throw new IllegalArgumentException("filter is required");
		}
		// Compiling the filter once up front rejects invalid ones (e.g. a negative radius).
		ListingFilterMapper.toQuery(input.filter());
		String webhookUrl = (input.webhookUrl() == null || input.webhookUrl().isBlank()) ? null : input.webhookUrl();
		if (webhookUrl != null) {
			validateWebhookUrl(webhookUrl);
		}
		return new SavedSearch(id, input.name(), input.filter(), webhookUrl,
				(input.webhookFormat() != null) ? input.webhookFormat() : WebhookFormat.JSON,
				Boolean.TRUE.equals(input.notifyOnPriceDrop()), !Boolean.FALSE.equals(input.enabled()), createdAt,
				lastAlertAt);
	}

	private static void validateWebhookUrl(String url) {
		try {
			URI uri = URI.create(url);
			if (!("http".equals(uri.getScheme()) || "https".equals(uri.getScheme())) || uri.getHost() == null) {
				throw new IllegalArgumentException("webhookUrl must be an http(s) URL");
			}
		}
		catch (IllegalArgumentException ex) {
			throw new IllegalArgumentException("Invalid webhookUrl: " + url, ex);
		}
	}

}
