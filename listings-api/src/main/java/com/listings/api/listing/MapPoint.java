package com.listings.api.listing;

import java.time.Instant;

import org.springframework.data.annotation.Id;

/** The few fields a map marker needs, so thousands of them stay cheap to send. */
public record MapPoint(
		@Id String id,
		Double latitude,
		Double longitude,
		Double price,
		Double roomsQc,
		Double bedrooms,
		String locationPrecision,
		Instant firstSeenAt,
		String buildingKey) {
}
