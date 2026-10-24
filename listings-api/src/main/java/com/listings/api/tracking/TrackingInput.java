package com.listings.api.tracking;

import java.time.Instant;

/**
 * A partial update: a null field is left as it is. {@code clearStatus} and
 * {@code clearVisitAt} reset those fields, and a blank {@code notes} erases the note.
 */
public record TrackingInput(
		Boolean favorite,
		TrackingStatus status,
		Boolean clearStatus,
		String notes,
		Instant visitAt,
		Boolean clearVisitAt,
		Boolean hidden) {
}
