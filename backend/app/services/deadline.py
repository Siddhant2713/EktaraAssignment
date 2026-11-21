import asyncio
from collections.abc import AsyncIterator

from app.schemas.events import ErrorCode, ErrorEvent, Event


async def with_deadline(events: AsyncIterator[Event], seconds: float) -> AsyncIterator[Event]:
    """Pass events through, but stop the whole run (with an error event) once `seconds` have passed in total.

    The limit is applied to each wait for the next event, not held open across the yields, which avoids the
    problems of keeping a timeout scope alive while the consumer does its own work between events.
    """
    loop = asyncio.get_running_loop()
    deadline = loop.time() + seconds
    iterator = events.__aiter__()
    try:
        while True:
            try:
                event = await asyncio.wait_for(iterator.__anext__(), max(deadline - loop.time(), 0))
            except StopAsyncIteration:
                return
            except TimeoutError:
                yield ErrorEvent(
                    step="timeout",
                    code=ErrorCode.TIMEOUT,
                    message=f"This took longer than {seconds:.0f} seconds, so it was stopped. Try again.",
                )
                return
            yield event
    finally:
        await iterator.aclose()  # make sure the pipeline underneath is shut down, whichever way we left
