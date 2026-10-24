package com.listings.api.alert;

import java.time.Instant;

import com.listings.api.listing.ListingFilter;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

/**
 * A stored filter that raises alerts when newly ingested listings match it (and,
 * optionally, when a matching listing gets cheaper).
 */
@Document(SavedSearch.COLLECTION)
public record SavedSearch(
		@Id String id,
		String name,
		ListingFilter filter,
		String webhookUrl,
		WebhookFormat webhookFormat,
		boolean notifyOnPriceDrop,
		boolean enabled,
		Instant createdAt,
		Instant lastAlertAt) {

	public static final String COLLECTION = "savedSearches";

}
