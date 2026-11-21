import logging
from urllib.parse import urlparse

from app.schemas.draft import Person
from app.schemas.scrape import ScrapedPage
from app.services.errors import PipelineError
from app.services.scraper import fetch_pages
from app.services.textmatch import has_word, norm
from app.services.web_search import search_pages

log = logging.getLogger(__name__)

# Login walls and bot blocks make these useless to fetch. Their search snippets are still used.
SOCIAL_HOSTS = {"linkedin.com", "x.com", "twitter.com", "facebook.com", "instagram.com", "tiktok.com"}
MAX_FULL_PAGES = 4  # pages fetched in full per person
FETCH_CANDIDATES = 8  # URLs tried to fill those slots, since some will block or fail


async def research_person(person: Person, company_name: str) -> list[ScrapedPage]:
    """Find pages about one founder: full text where we can fetch it, search snippets otherwise."""
    queries = [
        f'"{person.name}" {company_name} interview',
        f'"{person.name}" {company_name} podcast OR talk OR essay',
        f"{person.name} {company_name}",
    ]
    try:
        results = await search_pages(queries)
    except PipelineError:
        log.info("no search results for %s", person.name)
        return []

    relevant = [r for r in results if _mentions(r.text, person.name)]
    urls = [r.url for r in relevant if _host(r.url) not in SOCIAL_HOSTS][:FETCH_CANDIDATES]
    full = [p for p in await fetch_pages(urls, limit=MAX_FULL_PAGES) if _mentions(p.text, person.name)]

    fetched = {p.url for p in full}
    snippets = [r for r in relevant if r.url not in fetched]
    return full + snippets


def _mentions(text: str, name: str) -> bool:
    """True when the text contains the person's last name (a cheap guard against off-topic results)."""
    parts = norm(name).split()
    return bool(parts) and has_word(norm(text), parts[-1])


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")
