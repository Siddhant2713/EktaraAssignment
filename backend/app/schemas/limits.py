"""Helpers for bounding text that comes back from the LLM.

Input from API clients is REJECTED when too long (Field(max_length=...)). Output from the model is CUT instead:
refusing a whole request because Gemini wrote a 400-character sentence would be worse than trimming it.
"""

from pydantic import BeforeValidator


def clip(limit: int) -> BeforeValidator:
    """Cut a string to `limit` characters. Anything that is not a string (None, ...) passes through."""
    return BeforeValidator(lambda v: v[:limit] if isinstance(v, str) else v)


def first(limit: int) -> BeforeValidator:
    """Keep only the first `limit` items of a list."""
    return BeforeValidator(lambda v: v[:limit] if isinstance(v, list) else v)
