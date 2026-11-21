"""Fault injection: Gemini and the search backend misbehave. Every run must still end in exactly one result or error."""

import asyncio
import json

import pytest
from google.genai import errors as genai_errors

from app import config as app_config
from app.schemas.draft import DraftRequest, Fact
from app.schemas.events import ErrorCode
from app.schemas.scrape import ScrapedPage
from app.services.analyzer import analyze
from app.services.draft_pipeline import draft
from app.services.extractor import extract_company_and_founders
from tests.support.fakes import extraction_json, openers_json
from tests.support.helpers import collect, terminal


def api_error(kind, code, message="boom"):
    return kind(code, {"error": {"code": code, "message": message, "status": "X"}})


def rate_limited(message="quota exceeded"):
    return api_error(genai_errors.ClientError, 429, message)


def unavailable():
    return api_error(genai_errors.ServerError, 503, "This model is currently experiencing high demand.")


@pytest.fixture
def site(hostile, allow_local):
    return hostile.base + "/"


def one_terminal(events):
    ends = terminal(events)
    assert len(ends) == 1 and events[-1] is ends[0], "a run must end with exactly one result or error event"
    return ends[0]


# ---------- analyze ----------

async def test_a_rate_limit_that_does_not_clear_ends_in_one_clean_error(site, fake_gemini, fake_search):
    fake_gemini.default = lambda c, cfg: rate_limited("You exceeded your current quota. " * 40)  # every call, so the retry fails too
    end = one_terminal(await collect(analyze(site)))
    assert end.type == "error" and end.code == ErrorCode.LLM_FAILED
    assert len(end.message) <= 300, f"the user would see a {len(end.message)}-character provider error dump"
    assert "quota" not in end.message.lower() or len(end.message) < 120


async def test_a_single_transient_503_is_retried(site, fake_gemini, fake_search):
    """'High demand' errors are usually gone a moment later; one retry should rescue the request."""
    fake_gemini.push(unavailable())
    end = one_terminal(await collect(analyze(site)))
    assert end.type == "result", f"one 503 failed the whole request: {getattr(end, 'message', '')}"


@pytest.mark.parametrize("answer", ["this is not json", "", "{}", '{"company": 5, "people": "no"}', '{"unexpected": true}', "[]", "null"])
async def test_garbage_from_gemini_is_a_clean_llm_error(site, fake_gemini, fake_search, answer):
    fake_gemini.push(answer)
    end = one_terminal(await collect(analyze(site)))
    assert end.type == "error" and end.code == ErrorCode.LLM_FAILED


async def test_an_enormous_answer_from_gemini_is_survived(site, fake_gemini, fake_search):
    people = [{"name": f"Person {i}", "role": "Founder", "relationship": "founder", "confidence": 1, "evidence": f"Person {i}, Founder"} for i in range(5000)]
    fake_gemini.push(json.dumps({"company": {"name": "Acme", "one_liner": "Acme."}, "people": people}))
    end = one_terminal(await asyncio.wait_for(collect(analyze(site)), 15))
    assert end.type == "result"
    invented = [f["name"] for f in end.data["founders"] if f["name"].startswith("Person ")]
    assert invented == [], "5000 invented founders must all fail the quote check"


async def test_a_hung_llm_hits_an_overall_deadline(site, fake_gemini, fake_search, monkeypatch):
    fake_gemini.latency = 3600
    monkeypatch.setattr(app_config, "PIPELINE_TIMEOUT", 2, raising=False)
    try:
        events = await asyncio.wait_for(collect(analyze(site)), 6)
    except asyncio.TimeoutError:
        pytest.fail("still running 6s after the LLM hung: the pipeline has no overall deadline")
    assert one_terminal(events).type == "error"


async def test_prompt_size_is_bounded(fake_gemini):
    """500 pages of 6000 characters each: the prompt sent to Gemini must have a ceiling (cost and context limit)."""
    pages = [ScrapedPage(url=f"https://x.example/{i}", title="t", text="word " * 1200) for i in range(500)]
    fake_gemini.push(extraction_json(people=False))
    await extract_company_and_founders(pages)
    size = len(fake_gemini.calls[0]["contents"])
    assert size <= 120_000, f"prompt was {size:,} characters: no total cap on what is sent to the model"


async def test_site_without_founder_and_a_dead_search_still_returns_a_result(site, fake_gemini, fake_search):
    fake_gemini.push(extraction_json(people=False))
    fake_search.results = []
    events = await collect(analyze(site))
    end = one_terminal(events)
    assert end.type == "result" and end.data["founders"] == []
    assert any("web search failed" in e.message for e in events if e.type == "progress")


async def test_blocked_site_and_dead_search_give_one_clear_error(hostile, allow_local, fake_gemini, fake_search):
    fake_search.results = []
    end = one_terminal(await collect(analyze(hostile.base + "/status/403")))
    assert end.type == "error" and end.code == ErrorCode.SITE_BLOCKED and "web search" in end.message


async def test_site_without_founder_falls_back_to_the_web(site, fake_gemini, fake_search):
    fake_gemini.push(extraction_json(people=False))
    end = one_terminal(await collect(analyze(site)))
    assert end.type == "result" and [f["source"] for f in end.data["founders"]] == ["web"]


# ---------- draft ----------

def request(**over):
    fact = Fact(id=1, person="Jane Roe", text="She keeps Acme calm.", quote="Acme stays calm.", source_url="https://x.example", source_title="X", kind="own_words", specificity=5, date=None)
    body = dict(
        url="https://acme.example",
        company={"name": "Acme", "one_liner": "Acme makes calm software."},
        founders=[{"name": "Jane Roe", "role": "CEO"}],
        pitch="I sell async update tools to small remote teams.",
        facts=[fact],
    )
    body.update(over)
    return DraftRequest(**body)


async def test_a_model_that_only_writes_cliches_costs_two_calls_and_one_error(fake_gemini):
    fake_gemini.default = lambda c, cfg: openers_json(text="I hope this finds you well. We build async tools. Why not?")
    end = one_terminal(await collect(draft(request())))
    assert end.type == "error" and end.code == ErrorCode.LLM_FAILED
    assert len(fake_gemini.calls) == 2, "retries must be bounded: each draft may cost at most one retry"


async def test_at_most_three_openers_are_returned(fake_gemini):
    fake_gemini.default = lambda c, cfg: openers_json(count=50)
    end = one_terminal(await collect(draft(request())))
    assert end.type == "result" and len(end.data["openers"]) == 3


async def test_openers_addressed_to_strangers_are_dropped(fake_gemini):
    fake_gemini.default = lambda c, cfg: openers_json(to="Somebody Else")
    end = one_terminal(await collect(draft(request())))
    assert end.type == "error"


@pytest.mark.parametrize("answer", ["not json", "", "{}", '{"openers": "x"}'])
async def test_draft_garbage_from_gemini_is_a_clean_error(fake_gemini, answer):
    fake_gemini.default = lambda c, cfg: answer
    end = one_terminal(await collect(draft(request())))
    assert end.type == "error" and end.code == ErrorCode.LLM_FAILED


async def test_draft_gemini_outage_is_a_clean_error(fake_gemini):
    fake_gemini.default = lambda c, cfg: unavailable()
    end = one_terminal(await collect(draft(request())))
    assert end.type == "error" and end.code == ErrorCode.LLM_FAILED


async def test_draft_reuses_cached_facts_without_researching(fake_gemini, fake_search):
    end = one_terminal(await collect(draft(request())))
    assert end.type == "result" and not end.data["used_fallback"]
    assert fake_search.calls == 0, "cached facts were sent, so no web search should run"
    assert len(fake_gemini.calls) == 1


async def test_draft_with_empty_cached_facts_uses_the_fallback(fake_gemini, fake_search):
    end = one_terminal(await collect(draft(request(facts=[]))))
    assert end.type == "result" and end.data["used_fallback"] is True
