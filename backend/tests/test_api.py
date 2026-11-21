"""The HTTP surface: validation, the SSE contract the frontend relies on, and the happy paths."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from tests.support.helpers import parse_sse

FACT = {"id": 1, "person": "Jane Roe", "text": "She keeps Acme calm.", "quote": "Acme stays calm.", "source_url": "https://x.example", "source_title": "X", "kind": "own_words", "specificity": 5, "date": None}
DRAFT = {
    "url": "https://acme.example",
    "company": {"name": "Acme", "one_liner": "Acme makes calm software."},
    "founders": [{"name": "Jane Roe", "role": "CEO"}],
    "pitch": "I sell async update tools to small remote teams.",
    "facts": [FACT],
}


@pytest.fixture
def client():
    return TestClient(app)


def draft_body(**over):
    return {**DRAFT, **over}


def assert_sse_contract(response):
    """What the browser depends on: an event stream of JSON events ending in exactly one result or error."""
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = parse_sse(response.text)
    assert events and all(e["type"] in ("progress", "result", "error") for e in events)
    ends = [e for e in events if e["type"] in ("result", "error")]
    assert len(ends) == 1 and events[-1] is ends[0]
    return events


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# ---------- /api/analyze ----------

def test_analyze_happy_path(client, hostile, allow_local, fake_gemini):
    events = assert_sse_contract(client.post("/api/analyze", json={"url": hostile.base + "/"}))
    end = events[-1]
    assert end["type"] == "result"
    assert [f["name"] for f in end["data"]["founders"]] == ["Jane Roe"]
    assert end["data"]["founders"][0]["source"] == "site"


@pytest.mark.parametrize(
    "body",
    [{}, {"url": ""}, {"url": "not a url"}, {"url": "javascript:alert(1)"}, {"url": "ftp://example.com"}, {"url": 123}, {"url": None}, {"url": "http://" + "a" * 5000 + ".com"}, ["http://example.com"]],
)
def test_analyze_rejects_bad_input(client, body):
    assert client.post("/api/analyze", json=body).status_code == 422


@pytest.mark.parametrize("url", ["http://169.254.169.254/", "http://127.0.0.1:9/", "http://2130706433/", "http://[::1]/", "http://localhost:8000/health"])
def test_analyze_never_fetches_private_addresses(client, fake_gemini, url):
    events = assert_sse_contract(client.post("/api/analyze", json={"url": url}))
    assert events[-1]["type"] == "error" and events[-1]["code"] == "INVALID_URL"
    assert not fake_gemini.calls, "no LLM call should happen for a refused URL"


def test_analyze_without_a_gemini_key_says_so(client, monkeypatch):
    from app import config

    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    events = assert_sse_contract(client.post("/api/analyze", json={"url": "https://example.com"}))
    assert events[-1]["code"] == "CONFIG_MISSING"


# ---------- /api/draft ----------

def test_draft_happy_path_with_cached_facts(client, fake_gemini):
    events = assert_sse_contract(client.post("/api/draft", json=DRAFT))
    result = events[-1]["data"]
    assert events[-1]["type"] == "result" and len(result["openers"]) == 3 and not result["used_fallback"]
    assert all(o["to"] == "Jane Roe" and o["fact_ids"] == [1] for o in result["openers"])


@pytest.mark.parametrize(
    "over",
    [
        {"founders": []},
        {"founders": [{"name": "A"}, {"name": "B"}, {"name": "C"}]},
        {"founders": [{"name": ""}]},
        {"founders": [{"name": "x" * 101}]},
        {"founders": [{"name": "A", "role": "x" * 101}]},
        {"pitch": "short"},
        {"pitch": "x" * 601},
        {"tone": "angry"},
        {"company": None},
        {"url": "not a url"},
    ],
)
def test_draft_rejects_bad_input(client, over):
    assert client.post("/api/draft", json=draft_body(**over)).status_code == 422


def test_draft_rejects_oversized_client_supplied_facts(client, fake_gemini):
    """`facts` comes straight from the browser and is pasted into the prompt, so it needs size limits."""
    huge = {**FACT, "quote": "x" * 2_000_000}
    response = client.post("/api/draft", json=draft_body(facts=[huge]))
    assert response.status_code == 422, "a 2 MB 'quote' was accepted and would be sent to the model"


def test_draft_rejects_an_absurd_number_of_facts(client, fake_gemini):
    response = client.post("/api/draft", json=draft_body(facts=[{**FACT, "id": i} for i in range(1000)]))
    assert response.status_code == 422, "1000 facts were accepted"


def test_draft_rejects_fact_with_invalid_fields(client, fake_gemini):
    for bad in [{**FACT, "kind": "gossip"}, {**FACT, "specificity": 99}, {**FACT, "id": -5}]:
        assert client.post("/api/draft", json=draft_body(facts=[bad])).status_code == 422, bad
