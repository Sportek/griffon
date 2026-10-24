package com.listings.api.listing;

/** A map viewport, in decimal degrees. */
public record BoundingBox(double south, double west, double north, double east) {
}
