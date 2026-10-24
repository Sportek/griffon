# Scrape worker: polls listings-api for queued runs (python -m scraper.worker).
# The Playwright image ships Chromium for this exact Playwright version, so pin it.
FROM mcr.microsoft.com/playwright/python:v1.64.1-noble

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt "playwright==1.64.1"
COPY scraper scraper

# Geocoding / POI cache (.cache/geo.sqlite) lives in a volume so enrichment stays cheap.
RUN mkdir -p /app/.cache && chown -R pwuser /app
USER pwuser
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "scraper.worker"]
