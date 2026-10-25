package com.listings.api.listing;

import java.util.List;

public record ListingGroupPage(List<ListingGroup> content, int page, int size, long totalGroups, long totalListings) {

	public boolean hasNext() {
		return (long) (page + 1) * size < totalGroups;
	}

	public int totalPages() {
		return (int) ((totalGroups + size - 1) / size);
	}

}
