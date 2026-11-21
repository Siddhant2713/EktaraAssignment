from collections.abc import AsyncIterator

from fastapi.responses import StreamingResponse

from app.schemas.events import Event


def sse_response(events: AsyncIterator[Event]) -> StreamingResponse:
    """Stream pipeline events to the browser as server-sent events (one `data: {json}` message each)."""

    async def stream():
        async for event in events:
            yield f"data: {event.model_dump_json()}\n\n"

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
