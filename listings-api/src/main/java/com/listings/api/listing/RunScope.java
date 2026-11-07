package com.listings.api.listing;

import org.bson.Document;

/**
 * The listings an ingestion run (and its schedule) is about. A run source is a listing source,
 * optionally suffixed with {@value #SALE_SUFFIX}: {@code centris} scrapes Centris rentals,
 * {@code centris_sale} its properties for sale. Both write listings of source {@code centris};
 * the listing type tells them apart, so a rental run never deactivates a property for sale of
 * the same site, nor the other way round.
 *
 * @param source the listing source ({@code centris})
 * @param sale whether the run covers properties for sale rather than rentals
 */
public record RunScope(String source, boolean sale) {

	public static final String SALE_SUFFIX = "_sale";

	public static RunScope of(String runSource) {
		if (runSource.endsWith(SALE_SUFFIX) && runSource.length() > SALE_SUFFIX.length()) {
			return new RunScope(runSource.substring(0, runSource.length() - SALE_SUFFIX.length()), true);
		}
		return new RunScope(runSource, false);
	}

	/** The name of the run that covers these listings: {@code centris_sale}. */
	public String runSource() {
		return sale ? source + SALE_SUFFIX : source;
	}

	/** Rejection reason when the listing does not belong to a run of this scope, else null. */
	String rejection(ListingInput input) {
		if (!source.equals(input.source())) {
			return "source " + input.source() + " does not match the ingestion run source " + runSource();
		}
		if (sale != (input.listingType() == ListingType.SALE)) {
			return "listing type " + input.listingType() + " does not match the ingestion run source " + runSource()
					+ (sale ? " (SALE expected)" : " (use " + source + SALE_SUFFIX + " for SALE listings)");
		}
		return null;
	}

	/**
	 * Query matching the listings of this scope. Rentals are "not SALE" rather than "RENT", so
	 * listings of type UNKNOWN stay with the rental runs that have always owned them.
	 */
	Document criteria() {
		return new Document("source", source).append("listingType",
				sale ? ListingType.SALE.name() : new Document("$ne", ListingType.SALE.name()));
	}

}
