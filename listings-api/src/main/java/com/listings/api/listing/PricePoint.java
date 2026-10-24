package com.listings.api.listing;

import java.time.Instant;

public record PricePoint(Double price, Instant observedAt) {
}
