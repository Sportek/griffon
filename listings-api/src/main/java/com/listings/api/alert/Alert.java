package com.listings.api.alert;

import java.time.Instant;

import org.springframework.data.annotation.Id;
import org.springframework.data.mongodb.core.mapping.Document;

@Document(Alert.COLLECTION)
public record Alert(
		@Id String id,
		String savedSearchId,
		String listingId,
		Reason reason,
		Double previousPrice,
		Double price,
		Instant createdAt,
		Delivery delivery,
		String deliveryError) {

	public static final String COLLECTION = "alerts";

	public enum Reason {
		NEW_LISTING, PRICE_DROP
	}

	public enum Delivery {
		NONE, PENDING, SENT, FAILED
	}

}
