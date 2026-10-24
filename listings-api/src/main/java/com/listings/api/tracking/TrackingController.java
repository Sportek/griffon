package com.listings.api.tracking;

import java.util.HashMap;
import java.util.List;
import java.util.Map;

import com.listings.api.listing.Listing;

import org.springframework.graphql.data.method.annotation.Argument;
import org.springframework.graphql.data.method.annotation.BatchMapping;
import org.springframework.graphql.data.method.annotation.MutationMapping;
import org.springframework.graphql.data.method.annotation.QueryMapping;
import org.springframework.stereotype.Controller;

@Controller
class TrackingController {

	private final TrackingService trackings;

	TrackingController(TrackingService trackings) {
		this.trackings = trackings;
	}

	@QueryMapping
	List<TrackedListing> trackedListings(@Argument Boolean favorite, @Argument List<TrackingStatus> statuses,
			@Argument Boolean hidden) {
		return trackings.tracked(favorite, statuses, Boolean.TRUE.equals(hidden));
	}

	@MutationMapping
	Tracking updateTracking(@Argument String listingId, @Argument TrackingInput input) {
		return trackings.update(listingId, input);
	}

	@BatchMapping
	Map<Listing, Tracking> tracking(List<Listing> listings) {
		Map<String, Tracking> byId = trackings.findByListingIds(listings.stream().map(Listing::id).toList());
		Map<Listing, Tracking> out = new HashMap<>();
		for (Listing listing : listings) {
			Tracking tracking = byId.get(listing.id());
			if (tracking != null) {
				out.put(listing, tracking);
			}
		}
		return out;
	}

}
