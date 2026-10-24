package com.listings.api.listing;

import java.util.List;

public record FilterOptions(List<String> sources, List<String> cities, List<String> neighborhoods,
		List<String> regions, List<String> propertyTypes, List<String> amenities, List<String> utilitiesIncluded) {
}
