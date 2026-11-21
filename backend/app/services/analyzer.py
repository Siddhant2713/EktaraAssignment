import logging
from collections.abc import AsyncIterator

from app import config
from app.schemas.analyze import AnalyzeResult
from app.schemas.events import ErrorCode, ErrorEvent, ProgressEvent, ResultEvent
from app.services.errors import PipelineError
from app.services.extractor import extract_company_and_founders
from app.services.scraper import scrape_site

log = logging.getLogger(__name__)

Event = ProgressEvent | ResultEvent | ErrorEvent


async def analyze(url: str) -> AsyncIterator[Event]:
    """Run scrape -> extract, yielding a progress event before each step and a final result or error."""
    try:
        if not config.GEMINI_API_KEY:
            raise PipelineError("config", ErrorCode.CONFIG_MISSING, "GEMINI_API_KEY is not set in backend/.env")

        yield ProgressEvent(step="scrape", message=f"scraping the website {url}")
        pages = await scrape_site(url)
        yield ProgressEvent(step="scrape", message=f"found {len(pages)} page(s): " + ", ".join(p.url for p in pages))

        yield ProgressEvent(step="extract", message="extracting company and founder details")
        company, founders = await extract_company_and_founders(pages)

        names = ", ".join(f.name for f in founders) or "none named on the site"
        yield ProgressEvent(step="extract", message=f"found {len(founders)} founder(s): {names}")

        result = AnalyzeResult(company=company, founders=founders, pages_scraped=[p.url for p in pages])
        yield ResultEvent(data=result.model_dump(mode="json"))

    except PipelineError as e:
        yield ErrorEvent(step=e.step, code=e.code, message=e.message)
    except Exception:
        log.exception("unexpected failure while analyzing %s", url)
        yield ErrorEvent(step="unknown", code=ErrorCode.INTERNAL_ERROR, message="something went wrong on the server")
