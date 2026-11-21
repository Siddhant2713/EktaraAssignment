import logging
from collections.abc import AsyncIterator
from urllib.parse import urlparse

from app import config
from app.schemas.analyze import AnalyzeResult
from app.schemas.company import Company, Founder
from app.schemas.events import ErrorCode, ErrorEvent, Event, ProgressEvent, ResultEvent
from app.services.deadline import with_deadline
from app.services.errors import PipelineError
from app.services.extractor import extract_company_and_founders
from app.services.scraper import scrape_site
from app.services.web_search import search_pages

log = logging.getLogger(__name__)

# Scrape failures where the company may still be findable on the web (INVALID_URL is not one of them)
SITE_UNUSABLE = {ErrorCode.SITE_BLOCKED, ErrorCode.NO_CONTENT, ErrorCode.SITE_UNREACHABLE}


async def _analyze(url: str) -> AsyncIterator[Event]:
    """scrape -> extract, then fall back to web search when the site can't tell us the founders."""
    try:
        if not config.GEMINI_API_KEY:
            raise PipelineError("config", ErrorCode.CONFIG_MISSING, "GEMINI_API_KEY is not set in backend/.env")

        domain = (urlparse(url).hostname or "").removeprefix("www.")
        company: Company | None = None
        founders: list[Founder] = []
        pages_scraped: list[str] = []

        # 1. the company's own site
        yield ProgressEvent(step="scrape", message=f"scraping the website {url}")
        site_problem: PipelineError | None = None
        try:
            pages = await scrape_site(url)
            if sum(len(p.text) for p in pages) < config.MIN_SITE_CHARS:
                raise PipelineError(
                    "scrape", ErrorCode.NO_CONTENT, "the site returned almost no readable text (it may need JavaScript)"
                )
        except PipelineError as e:
            if e.code not in SITE_UNUSABLE:
                raise
            site_problem = e

        if site_problem is None:
            pages_scraped = [p.url for p in pages]
            yield ProgressEvent(step="scrape", message=f"found {len(pages)} page(s): " + ", ".join(pages_scraped))
            yield ProgressEvent(step="extract", message="extracting company and founder details")
            company, founders = await extract_company_and_founders(pages)
        else:
            yield ProgressEvent(step="scrape", message=f"could not read the site: {site_problem.message}")

        # 2. web search, when the site gave us no founders
        if not founders:
            name = company.name if company else domain
            yield ProgressEvent(step="search", message=f"searching the web for the founders of {name}")
            try:
                # worded differently on purpose: the search backend drops some phrasings at random
                queries = list(dict.fromkeys([f"who founded {domain}", f"{domain} founders", f"{name} founders"]))
                results = await search_pages(queries)
                yield ProgressEvent(step="search", message=f"found {len(results)} search result(s)")
                yield ProgressEvent(step="extract", message="reading the search results")
                web_company, founders = await extract_company_and_founders(
                    results,
                    source="web",
                    domain=domain,
                    company_hint=company.one_liner if company else None,
                )
                company = company or web_company  # the site's own description wins when we have it
            except PipelineError as e:
                if company is None:  # site unreadable AND search failed: nothing to show
                    raise PipelineError(
                        site_problem.step if site_problem else e.step,
                        site_problem.code if site_problem else e.code,
                        f"{site_problem.message if site_problem else 'no founder on the site'}; "
                        f"the web search also failed: {e.message}",
                    )
                yield ProgressEvent(step="search", message=f"web search failed: {e.message}")

        assert company is not None
        names = ", ".join(f.name for f in founders) or "none found"
        yield ProgressEvent(step="extract", message=f"found {len(founders)} founder(s): {names}")

        result = AnalyzeResult(company=company, founders=founders, pages_scraped=pages_scraped)
        yield ResultEvent(data=result.model_dump(mode="json"))

    except PipelineError as e:
        yield ErrorEvent(step=e.step, code=e.code, message=e.message)
    except Exception:
        log.exception("unexpected failure while analyzing %s", url)
        yield ErrorEvent(step="unknown", code=ErrorCode.INTERNAL_ERROR, message="something went wrong on the server")


def analyze(url: str) -> AsyncIterator[Event]:
    """The analysis pipeline, stopped with a TIMEOUT error if it takes longer than config.PIPELINE_TIMEOUT."""
    return with_deadline(_analyze(url), config.PIPELINE_TIMEOUT)
