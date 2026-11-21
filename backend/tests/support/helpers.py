import json


def parse_sse(body: str) -> list[dict]:
    """Turn an SSE response body into the list of event dicts the browser would see."""
    return [json.loads(line[len("data: ") :]) for line in body.splitlines() if line.startswith("data: ")]


async def collect(agen) -> list:
    """Drain a pipeline's async generator into a list of event objects."""
    return [event async for event in agen]


def terminal(events) -> list:
    """The events that end a run (a result or an error). A healthy run has exactly one, and it is last."""
    return [e for e in events if e.type in ("result", "error")]
