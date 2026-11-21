"""Telling "our code is wrong" apart from "Gemini or the search engine is having a bad day"."""

import re

UPSTREAM_TROUBLE = re.compile(r"Gemini (is overloaded|'s rate limit|could not process|rejected)|web search (failed|also failed)|returned nothing", re.I)


def upstream_trouble(events) -> str | None:
    """A reason string when the run ended (or quietly degraded) because an upstream service failed, else None."""
    for event in events:
        if event.type == "error" and UPSTREAM_TROUBLE.search(event.message):
            return event.message
        if event.type == "progress" and UPSTREAM_TROUBLE.search(event.message):
            return event.message  # e.g. "web search failed: ..." followed by a result with no founders
    return None
