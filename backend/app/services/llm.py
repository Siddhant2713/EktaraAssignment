import logging
from typing import TypeVar

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, ValidationError

from app import config
from app.schemas.events import ErrorCode
from app.services.errors import PipelineError

log = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


async def generate_json(
    *, step: str, system_prompt: str, prompt: str, schema: type[T], temperature: float = 0.0, model: str | None = None
) -> T:
    """Call Gemini and parse its answer into `schema`. Every failure becomes a PipelineError tagged with `step`."""
    client = genai.Client(api_key=config.GEMINI_API_KEY)
    try:
        response = await client.aio.models.generate_content(
            model=model or config.GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_json_schema": schema.model_json_schema(),
                "temperature": temperature,
            },
        )
    except genai_errors.APIError as e:
        log.warning("Gemini call failed: %s", e)
        raise PipelineError(step, ErrorCode.LLM_FAILED, f"Gemini request failed (HTTP {e.code}): {e.message}")

    if not response.text:
        raise PipelineError(step, ErrorCode.LLM_FAILED, "Gemini returned an empty response")
    try:
        return schema.model_validate_json(response.text)
    except ValidationError:
        log.warning("Unparseable Gemini output: %s", response.text)
        raise PipelineError(step, ErrorCode.LLM_FAILED, "Gemini returned a response in an unexpected format")
