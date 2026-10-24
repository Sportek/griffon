package com.listings.api.tracking;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * The owner's follow-up on one listing. Keyed by the listing id: Griffon has a single
 * user for now, so there is no user dimension yet.
 */
@Document(Tracking.COLLECTION)
public record Tracking(
		@Id String listingId,
		Boolean favorite,
		TrackingStatus status,
		String notes,
		Instant visitAt,
		Boolean hidden,
		Double priceWhenTracked,
		Instant createdAt,
		Instant updatedAt) {

	public static final String COLLECTION = "trackings";

	public Tracking {
		favorite = Boolean.TRUE.equals(favorite);
		hidden = Boolean.TRUE.equals(hidden);
	}

	/** No favorite, status, note, visit or hide left: nothing worth keeping. */
	boolean isEmpty() {
		return !favorite && !hidden && status == null && notes == null && visitAt == null;
	}

}
