package com.listings.api.listing;

import java.util.List;

public record IngestReport(int received, List<IngestResult> results) {

	public int created() {
		return count(IngestStatus.CREATED);
	}

	public int updated() {
		return count(IngestStatus.UPDATED);
	}

	public int unchanged() {
		return count(IngestStatus.UNCHANGED);
	}

	public int rejected() {
		return count(IngestStatus.REJECTED);
	}

	private int count(IngestStatus status) {
		return (int) results.stream().filter(r -> r.status() == status).count();
	}

}
