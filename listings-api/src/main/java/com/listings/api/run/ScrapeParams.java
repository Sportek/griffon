package com.listings.api.run;

import java.util.List;

/**
 * Scraper options a worker passes to the source, mirroring the CLI flags
 * ({@code --max-pages}, {@code --areas}, {@code --limit}, {@code --enrich}, {@code --mark-unseen-inactive}).
 */
public record ScrapeParams(Integer maxPages, List<String> areas, Integer limit, Boolean enrich,
		Boolean markUnseenInactive) {

	public static final ScrapeParams DEFAULTS = new ScrapeParams(null, null, null, false, false);

	public ScrapeParams {
		areas = (areas == null || areas.isEmpty()) ? null : List.copyOf(areas);
		enrich = Boolean.TRUE.equals(enrich);
		markUnseenInactive = Boolean.TRUE.equals(markUnseenInactive);
	}

	static ScrapeParams orDefaults(ScrapeParams params) {
		return (params != null) ? params : DEFAULTS;
	}

	/** Same rule as the CLI: deactivating what was not seen needs a complete scrape. */
	void validate() {
		if (markUnseenInactive && (limit != null || maxPages != null)) {
			throw new IllegalArgumentException("markUnseenInactive needs a complete scrape (no limit / maxPages)");
		}
		if ((limit != null && limit < 1) || (maxPages != null && maxPages < 1)) {
			throw new IllegalArgumentException("limit and maxPages must be >= 1");
		}
	}

}
