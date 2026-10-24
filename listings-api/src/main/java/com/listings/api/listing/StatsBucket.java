package com.listings.api.listing;

public record StatsBucket(String key, int count, Double avgPrice, Double minPrice, Double maxPrice) {
}
