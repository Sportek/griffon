package com.listings.api.listing;

import java.time.Instant;
import java.util.List;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class ListingController {

	private final ListingQueryService queries;

	ListingController(ListingQueryService queries) {
		this.queries = queries;
	}

	@QueryMapping
	Listing listing(@Argument String id) {
		return queries.findById(id).orElse(null);
	}

	@QueryMapping
	Listing listingByKey(@Argument String source, @Argument String externalId) {
		return queries.findByKey(source, externalId).orElse(null);
	}

	@QueryMapping
	ListingPage listings(@Argument ListingFilter filter, @Argument ListingSort sort, @Argument Integer page,
			@Argument Integer size) {
		return queries.search(filter, (sort != null) ? sort : ListingSort.NEWEST, (page != null) ? page : 0,
				(size != null) ? size : 20);
	}

	@QueryMapping
	List<Listing> latestListings(@Argument Integer limit, @Argument Instant since, @Argument ListingFilter filter) {
		return queries.latest((limit != null) ? limit : 20, since, filter);
	}

	@QueryMapping
	ListingStats listingStats(@Argument ListingFilter filter) {
		return queries.stats(filter);
	}

	@QueryMapping
	FilterOptions filterOptions() {
		return queries.filterOptions();
	}

	@MutationMapping
	boolean deleteListing(@Argument String id) {
		return queries.delete(id);
	}

	@SchemaMapping
	Listing duplicateOf(Listing listing) {
		return (listing.duplicateOf() != null) ? queries.findById(listing.duplicateOf()).orElse(null) : null;
	}

	@SchemaMapping
	List<Listing> duplicates(Listing listing) {
		return queries.duplicateGroup(listing);
	}

}
