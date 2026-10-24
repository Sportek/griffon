package com.listings.api.listing;

import java.util.List;

public record ListingPage(List<Listing> content, int page, int size, long totalElements) {

	public int totalPages() {
		return (int) ((totalElements + size - 1) / size);
	}

	public boolean hasNext() {
		return (long) (page + 1) * size < totalElements;
	}

}
