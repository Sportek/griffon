"""Facebook groups source: rental posts from groups the scraping account is a member of.

Pipeline (see scraper/sources/facebook.py):

    session.py   Playwright storage_state (cookies) on the worker volume, logged-out detection
    extract.py   everything that knows Facebook's DOM: group/permalink parsing, post extraction
    prefilter.py cheap keyword rules (no LLM): drops colocs, "je cherche", for-sale, off-topic
    llm.py       batched OpenRouter classification + field extraction, cached by text hash
    mapping.py   post (+ classification) -> Listing
    store.py     small JSON state on the volume: seen post ids, text hashes, LLM cache

Facebook's markup is obfuscated and changes often: when the source starts returning nothing,
extract.py is the one file to update (tests/fixtures/facebook/ holds the reference markup).
"""
