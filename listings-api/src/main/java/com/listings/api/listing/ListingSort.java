package com.listings.api.listing;

import org.springframework.data.domain.Sort;

public enum ListingSort {

	NEWEST(Sort.by(Sort.Direction.DESC, "firstSeenAt")),
	OLDEST(Sort.by(Sort.Direction.ASC, "firstSeenAt")),
	PRICE_ASC(Sort.by(Sort.Direction.ASC, "price")),
	PRICE_DESC(Sort.by(Sort.Direction.DESC, "price")),
	AREA_DESC(Sort.by(Sort.Direction.DESC, "areaSqft")),
	RECENTLY_UPDATED(Sort.by(Sort.Direction.DESC, "updatedAt")),
	RECENTLY_SEEN(Sort.by(Sort.Direction.DESC, "lastSeenAt"));

	private final Sort sort;

	ListingSort(Sort sort) {
		this.sort = sort;
	}

	/** The sort plus an _id tiebreaker so pagination is stable. */
	public Sort toSort() {
		return sort.and(Sort.by(Sort.Direction.DESC, "_id"));
	}

}
