package com.listings.api.listing;

/**
 * How a listing's price compares with similar active listings: same size, in the same
 * neighbourhood when it has enough of them, otherwise in the same city.
 *
 * @param scope NEIGHBORHOOD or CITY
 * @param area the neighbourhood or city name, as the listing spells it
 * @param deltaPercent how far the listing sits from the median (negative = cheaper)
 */
public record PriceBenchmark(
		String scope,
		String area,
		Double roomsQc,
		Double bedrooms,
		double median,
		int sampleSize,
		double deltaPercent) {
}
