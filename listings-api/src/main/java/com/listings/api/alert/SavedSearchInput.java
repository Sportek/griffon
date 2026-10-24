package com.listings.api.alert;

import com.listings.api.listing.ListingFilter;

public record SavedSearchInput(String name, ListingFilter filter, String webhookUrl, WebhookFormat webhookFormat,
		Boolean notifyOnPriceDrop, Boolean enabled) {
}
