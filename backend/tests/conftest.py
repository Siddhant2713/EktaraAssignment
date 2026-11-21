import asyncio
from types import SimpleNamespace
from urllib.parse import urlparse

import pytest

from app import config as app_config
from app.services import llm, scraper, web_search
from tests.support.fakes import SEARCH_RESULTS, FakeGemini
from tests.support.hostile_server import HostileServer


def pytest_addoption(parser):
    parser.addoption("--live", action="store_true", help="also run tests that call the real Gemini API and the web")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--live"):
        return
    skip = pytest.mark.skip(reason="live test: run with --live (uses your Gemini key and the network)")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def hostile():
    server = HostileServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def allow_local(monkeypatch, hostile):
    """Let the scraper reach the local hostile server, and nothing else private.

    The real SSRF guard refuses 127.0.0.1, so tests that need to fetch from the hostile server punch exactly
    one hole in it (that host and port); every other address still goes through the real check.
    """
    real_guard = scraper._ensure_public

    async def guard(url: str) -> None:
        parsed = urlparse(url)
        if parsed.hostname == "127.0.0.1" and parsed.port == hostile.port:
            return
        await real_guard(url)

    monkeypatch.setattr(scraper, "_ensure_public", guard)


@pytest.fixture
def fake_gemini(monkeypatch):
    fake = FakeGemini()
    monkeypatch.setattr(app_config, "GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm.genai, "Client", lambda api_key=None: SimpleNamespace(aio=SimpleNamespace(models=fake)))
    return fake


@pytest.fixture
def fake_search(monkeypatch):
    """Replace the real web search with a canned, instant one that also records how many ran at once."""
    state = SimpleNamespace(results=list(SEARCH_RESULTS), calls=0, in_flight=0, max_in_flight=0, latency=0.0)

    async def fake(query: str):
        state.calls += 1
        state.in_flight += 1
        state.max_in_flight = max(state.max_in_flight, state.in_flight)
        try:
            if state.latency:
                await asyncio.sleep(state.latency)
            return list(state.results)
        finally:
            state.in_flight -= 1

    monkeypatch.setattr(web_search, "_search", fake)
    monkeypatch.setattr(web_search, "QUERY_GAP", 0)
    return state


@pytest.fixture(autouse=True)
def fast_retries(monkeypatch):
    """The real retry pause is ~1.5s; tests do not need to wait for it."""
    monkeypatch.setattr(app_config, "LLM_RETRY_DELAY", 0)
