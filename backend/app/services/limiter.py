import asyncio
import weakref
from collections.abc import Callable

from app import config


class Limiter:
    """A cap on how many callers may be inside a section at once, shared by every request.

        async with gemini_slots.slot():
            await call_gemini()      # at most N of these run at the same time; the rest wait here

    A separate semaphore is kept per event loop (the app has one; the test suite has one per test), because a
    semaphore that has had to make someone wait is tied to the loop it was used on.
    """

    def __init__(self, limit: Callable[[], int]):
        self._limit = limit
        self._slots: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()

    def slot(self) -> asyncio.Semaphore:
        loop = asyncio.get_running_loop()
        limit = max(1, self._limit())
        current = self._slots.get(loop)
        if current is None or current[0] != limit:  # first use on this loop, or the setting changed
            current = (limit, asyncio.Semaphore(limit))
            self._slots[loop] = current
        return current[1]


gemini_slots = Limiter(lambda: config.MAX_CONCURRENT_GEMINI)
search_slots = Limiter(lambda: config.MAX_CONCURRENT_SEARCHES)
fetch_slots = Limiter(lambda: config.MAX_CONCURRENT_FETCHES)
