import asyncio
import logging

from ddgs import DDGS

from app import config
from app.schemas.events import ErrorCode
from app.schemas.scrape import ScrapedPage
from app.services.errors import PipelineError
from app.services.limiter import search_slots

log = logging.getLogger(__name__)
STEP = "search"

ATTEMPTS = 2  # the search library fails intermittently; differently worded queries act as extra retries
QUERY_GAP = 1.0  # seconds between queries; firing them back to back gets rate limited
ENOUGH_RESULTS = 8  # stop querying once we have this many distinct results
MAX_URL_CHARS = 500  # longer URLs cannot be cited as a source
MAX_SNIPPET_CHARS = 1000


async def search_pages(queries: list[str]) -> list[ScrapedPage]:
    """Run web searches and return each result as a 'page' (title + snippet) for the extractor."""
    pages: dict[str, ScrapedPage] = {}
    for i, query in enumerate(queries):
        if len(pages) >= ENOUGH_RESULTS:
            break
        if i:
            await asyncio.sleep(QUERY_GAP)
        async with search_slots.slot():  # shared by all requests: the backend throttles quickly
            results = await _search(query)
        for result in results:
            url, body, title = result.get("href"), result.get("body"), (result.get("title") or "")[:200]
            if url and body and len(url) <= MAX_URL_CHARS and url not in pages:
                pages[url] = ScrapedPage(url=url, title=title, text=f"{title}. {body[:MAX_SNIPPET_CHARS]}")

    if not pages:
        raise PipelineError(STEP, ErrorCode.SEARCH_FAILED, "the web search returned nothing (it may be rate limited)")
    return list(pages.values())


async def _search(query: str) -> list[dict]:
    for attempt in range(ATTEMPTS):
        try:
            return await asyncio.to_thread(lambda: DDGS().text(query, max_results=config.SEARCH_RESULTS_PER_QUERY))
        except Exception as e:  # the library raises its own error types, "no results" and rate limits included
            log.info("search %r failed (attempt %d/%d): %s", query, attempt + 1, ATTEMPTS, type(e).__name__)
            if attempt < ATTEMPTS - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    return []
