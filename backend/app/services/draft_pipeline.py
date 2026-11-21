import logging
from collections.abc import AsyncIterator

from app import config
from app.schemas.draft import DraftRequest, DraftResult, Fact
from app.schemas.events import ErrorCode, ErrorEvent, Event, ProgressEvent, ResultEvent
from app.services.deadline import with_deadline
from app.services.drafter import draft_openers
from app.services.errors import PipelineError
from app.services.fact_extractor import number_facts, research_facts

log = logging.getLogger(__name__)


async def _draft(request: DraftRequest) -> AsyncIterator[Event]:
    """research -> write openers. Cached facts in the request skip the research (that is what regenerate sends)."""
    try:
        if not config.GEMINI_API_KEY:
            raise PipelineError("config", ErrorCode.CONFIG_MISSING, "GEMINI_API_KEY is not set in backend/.env")

        site = request.url.host or ""
        company = request.company

        if request.facts is None:
            collected: list[Fact] = []
            for person in request.founders:
                yield ProgressEvent(step="research", message=f"researching {person.name}")
                try:
                    found = await research_facts(person, company, site.removeprefix("www."))
                except PipelineError as e:  # one founder failing should not sink the whole draft
                    yield ProgressEvent(step="research", message=f"research failed for {person.name}: {e.message}")
                    continue
                yield ProgressEvent(step="research", message=f"found {len(found)} usable fact(s) about {person.name}")
                collected.extend(found)
            facts = number_facts(collected)
        else:
            facts = request.facts
            yield ProgressEvent(step="research", message=f"reusing {len(facts)} fact(s) from the earlier run")

        if not facts:
            yield ProgressEvent(step="draft", message="no personal facts found, writing from the company description only")

        yield ProgressEvent(step="draft", message=f"writing openers ({request.tone.value})")
        openers = await draft_openers(
            company=company, founders=request.founders, pitch=request.pitch.strip(), tone=request.tone, facts=facts
        )

        result = DraftResult(openers=openers, facts=facts, used_fallback=not facts)
        yield ResultEvent(data=result.model_dump(mode="json"))

    except PipelineError as e:
        yield ErrorEvent(step=e.step, code=e.code, message=e.message)
    except Exception:
        log.exception("unexpected failure while drafting for %s", request.url)
        yield ErrorEvent(step="unknown", code=ErrorCode.INTERNAL_ERROR, message="something went wrong on the server")


def draft(request: DraftRequest) -> AsyncIterator[Event]:
    """The drafting pipeline, stopped with a TIMEOUT error if it takes longer than config.DRAFT_TIMEOUT."""
    return with_deadline(_draft(request), config.DRAFT_TIMEOUT)
