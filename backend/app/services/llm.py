import asyncio
import logging
import random
import re
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, ValidationError

from app import config
from app.schemas.events import ErrorCode
from app.services.errors import PipelineError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

# Errors that are about Google's side being busy, not about our request: worth another try.
TRANSIENT = {429, 500, 502, 503, 504}
# A 429 that says the DAILY quota is gone will not clear in a second, so retrying the same model is pointless.
QUOTA_GONE = re.compile(r"PerDay|limit: 0|per day", re.IGNORECASE)


async def generate_json(
    *, step: str, system_prompt: str, prompt: str, schema: type[T], temperature: float = 0.0, model: str | None = None
) -> T:
    """Call Gemini and parse its answer into `schema`.

    A transient error (overloaded, rate limited) is retried once on the same model; if it keeps failing and
    GEMINI_FALLBACK_MODEL is set, that model gets one attempt. Every failure becomes a PipelineError tagged
    with `step` and carrying a short message (the provider's full error is only logged).
    """
    primary = model or config.GEMINI_MODEL
    models = [primary]
    if config.GEMINI_FALLBACK_MODEL and config.GEMINI_FALLBACK_MODEL != primary:
        models.append(config.GEMINI_FALLBACK_MODEL)

    client = genai.Client(api_key=config.GEMINI_API_KEY)
    error: genai_errors.APIError | None = None

    for index, name in enumerate(models):
        attempts = 2 if index == 0 else 1  # one retry on the main model, a single try on the fallback
        for attempt in range(attempts):
            try:
                response = await client.aio.models.generate_content(
                    model=name,
                    contents=prompt,
                    config={
                        "system_instruction": system_prompt,
                        "response_mime_type": "application/json",
                        "response_json_schema": schema.model_json_schema(),
                        "temperature": temperature,
                    },
                )
            except genai_errors.APIError as e:
                error = e
                log.warning("Gemini call failed (model %s, attempt %d/%d): %s", name, attempt + 1, attempts, e)
                if e.code not in TRANSIENT:
                    raise _friendly_error(step, e)  # a bad key or bad request fails the same way on any model
                if QUOTA_GONE.search(str(e)) or attempt + 1 == attempts:
                    break  # give up on this model; the fallback, if any, is next
                await asyncio.sleep(config.LLM_RETRY_DELAY * random.uniform(0.7, 1.3))
            else:
                if index:
                    log.warning("answered by the fallback model %s", name)
                return _parse(step, response.text, schema)

    raise _friendly_error(step, error)


def _parse(step: str, text: str | None, schema: type[T]) -> T:
    if not text:
        raise PipelineError(step, ErrorCode.LLM_FAILED, "Gemini returned an empty response")
    try:
        return schema.model_validate_json(text)
    except ValidationError:
        log.warning("Unparseable Gemini output: %s", text[:2000])
        raise PipelineError(step, ErrorCode.LLM_FAILED, "Gemini returned a response in an unexpected format")


def _friendly_error(step: str, e: genai_errors.APIError | None) -> PipelineError:
    """A short message for the user. The provider's own text can be over a thousand characters of JSON."""
    code = e.code if e else None
    if code in (401, 403) or (code == 400 and "API key" in str(e)):
        message = "Gemini rejected the API key. Check GEMINI_API_KEY in backend/.env"
    elif code == 429:
        message = "Gemini's rate limit or quota has been reached. Wait a minute and try again"
    elif code in (500, 502, 503, 504):
        message = "Gemini is overloaded or unavailable right now. Try again shortly"
    else:
        message = f"Gemini could not process the request (HTTP {code})"
    return PipelineError(step, ErrorCode.LLM_FAILED, message)
