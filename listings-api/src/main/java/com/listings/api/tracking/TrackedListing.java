package com.listings.api.tracking;

import com.listings.api.listing.Listing;

/** A tracking with its listing, which is null once the listing has been deleted. */
public record TrackedListing(Tracking tracking, Listing listing) {
}
