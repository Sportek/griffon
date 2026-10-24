package com.listings.api.alert;

import java.time.Instant;
import java.util.List;

import com.listings.api.listing.Listing;
import com.listings.api.listing.ListingPage;
import com.listings.api.listing.ListingQueryService;
import com.listings.api.listing.ListingSort;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.graphql.data.method.annotation.SchemaMapping;
import org.springframework.stereotype.Controller;

@Controller
class AlertController {

	private final AlertService alerts;

	private final ListingQueryService listings;

	AlertController(AlertService alerts, ListingQueryService listings) {
		this.alerts = alerts;
		this.listings = listings;
	}

	@QueryMapping
	SavedSearch savedSearch(@Argument String id) {
		return alerts.find(id);
	}

	@QueryMapping
	List<SavedSearch> savedSearches() {
		return alerts.findAll();
	}

	@QueryMapping
	List<Alert> alerts(@Argument String savedSearchId, @Argument Instant since, @Argument Integer limit) {
		return alerts.alerts(savedSearchId, since, (limit != null) ? limit : 50);
	}

	@MutationMapping
	SavedSearch createSavedSearch(@Argument SavedSearchInput input) {
		return alerts.create(input);
	}

	@MutationMapping
	SavedSearch updateSavedSearch(@Argument String id, @Argument SavedSearchInput input) {
		return alerts.update(id, input);
	}

	@MutationMapping
	boolean deleteSavedSearch(@Argument String id) {
		return alerts.delete(id);
	}

	@SchemaMapping
	ListingPage matches(SavedSearch search, @Argument Integer page, @Argument Integer size) {
		return listings.search(search.filter(), ListingSort.NEWEST, (page != null) ? page : 0,
				(size != null) ? size : 20);
	}

	@SchemaMapping
	SavedSearch savedSearch(Alert alert) {
		return alerts.find(alert.savedSearchId());
	}

	@SchemaMapping
	Listing listing(Alert alert) {
		return listings.findById(alert.listingId()).orElse(null);
	}

}
