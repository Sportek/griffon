package com.listings.api.run;

public record ScrapeScheduleInput(String source, String cron, String timeZone, Boolean enabled, ScrapeParams params) {
}
