package com.listings.api.tracking;

import java.time.Clock;
import java.time.Instant;
import java.util.Collection;
import java.util.List;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;

import com.listings.api.listing.Listing;
import com.listings.api.listing.ListingQueryService;

import org.springframework.data.domain.Sort;
import org.springframework.data.mongodb.core.MongoTemplate;
import org.springframework.data.mongodb.core.query.Criteria;
import org.springframework.data.mongodb.core.query.Query;
import org.springframework.stereotype.Service;

@Service
public class TrackingService {

	private final MongoTemplate mongo;

	private final ListingQueryService listings;

	private final Clock clock;

	TrackingService(MongoTemplate mongo, ListingQueryService listings, Clock clock) {
		this.mongo = mongo;
		this.listings = listings;
		this.clock = clock;
	}

	public Map<String, Tracking> findByListingIds(Collection<String> listingIds) {
		Query query = Query.query(Criteria.where("_id").in(listingIds));
		return mongo.find(query, Tracking.class)
			.stream()
			.collect(Collectors.toMap(Tracking::listingId, Function.identity()));
	}

	/** Tracked listings, most recently touched first. Hidden ones only when asked for. */
	public List<TrackedListing> tracked(Boolean favorite, List<TrackingStatus> statuses, boolean hidden) {
		Query query = Query.query(Criteria.where("hidden").is(hidden));
		if (favorite != null) {
			query.addCriteria(Criteria.where("favorite").is(favorite));
		}
		if (statuses != null && !statuses.isEmpty()) {
			query.addCriteria(Criteria.where("status").in(statuses));
		}
		List<Tracking> found = mongo.find(query.with(Sort.by(Sort.Direction.DESC, "updatedAt")), Tracking.class);
		Map<String, Listing> byId = listings.findByIds(found.stream().map(Tracking::listingId).toList());
		return found.stream().map(t -> new TrackedListing(t, byId.get(t.listingId()))).toList();
	}

	/**
	 * Applies a partial update. A tracking left with nothing in it is deleted, so
	 * un-favoriting a listing leaves no trace; the returned value still describes it.
	 */
	public Tracking update(String listingId, TrackingInput input) {
		Listing listing = listings.findById(listingId)
			.orElseThrow(() -> new IllegalArgumentException("unknown listing " + listingId));
		Tracking current = mongo.findById(listingId, Tracking.class);
		Instant now = clock.instant();
		Tracking next = new Tracking(listingId, merge(input.favorite(), (current != null) && current.favorite()),
				Boolean.TRUE.equals(input.clearStatus()) ? null
						: merge(input.status(), (current != null) ? current.status() : null),
				(input.notes() != null) ? (input.notes().isBlank() ? null : input.notes().strip())
						: (current != null) ? current.notes() : null,
				Boolean.TRUE.equals(input.clearVisitAt()) ? null
						: merge(input.visitAt(), (current != null) ? current.visitAt() : null),
				merge(input.hidden(), (current != null) && current.hidden()),
				(current != null) ? current.priceWhenTracked() : listing.price(),
				(current != null) ? current.createdAt() : now, now);
		if (next.isEmpty()) {
			mongo.remove(Query.query(Criteria.where("_id").is(listingId)), Tracking.class);
		}
		else {
			mongo.save(next);
		}
		return next;
	}

	private static <T> T merge(T requested, T current) {
		return (requested != null) ? requested : current;
	}

}
