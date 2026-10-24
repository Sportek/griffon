package com.listings.api.listing;

import java.util.List;

public record ListingStats(int count, Double avgPrice, Double minPrice, Double maxPrice,
		List<StatsBucket> bySource, List<StatsBucket> byCity, List<StatsBucket> byRoomsQc) {
}
