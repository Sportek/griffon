package com.listings.api.listing;

public record IngestResult(String source, String externalId, IngestStatus status, String error) {
}
