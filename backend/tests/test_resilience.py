"""Retries, the model fallback, short error messages and the whole-request deadlines."""

import asyncio

import pytest
from google.genai import errors as genai_errors

from app import config as app_config
from app.schemas.draft import DraftRequest, Fact
from app.schemas.events import ErrorCode
from app.services import llm
from app.services.analyzer import analyze
from app.services.draft_pipeline import draft
from app.services.errors import PipelineError
from app.services.extractor import ExtractionOutput
from tests.support.fakes import extraction_json
from tests.support.helpers import collect, terminal


def api_error(kind, code, message="boom"):
    return kind(code, {"error": {"code": code, "message": message, "status": "X"}})


def overloaded():
    return api_error(genai_errors.ServerError, 503, "This model is currently experiencing high demand.")


def rate_limited():
    return api_error(genai_errors.ClientError, 429, "Quota exceeded for metric requests per minute")


def daily_quota_gone():
    return api_error(genai_errors.ClientError, 429, "Quota exceeded: GenerateRequestsPerDayPerProjectPerModel-FreeTier, limit: 0")


async def ask(**over):
    """One structured call through the real llm wrapper, against the fake Gemini."""
    return await llm.generate_json(step="extract", system_prompt="s", prompt="p", schema=ExtractionOutput, **over)


def models_called(fake):
    return [call["model"] for call in fake.calls]


@pytest.fixture
def two_models(monkeypatch):
    monkeypatch.setattr(app_config, "GEMINI_MODEL", "main-model")
    monkeypatch.setattr(app_config, "GEMINI_FALLBACK_MODEL", "backup-model")


# ---------- retry on the same model ----------

@pytest.mark.parametrize("make_error", [overloaded, rate_limited])
async def test_one_transient_error_is_retried_and_then_succeeds(fake_gemini, make_error):
    fake_gemini.push(make_error(), extraction_json())
    assert (await ask()).company.name == "Acme"
    assert len(fake_gemini.calls) == 2


async def test_only_one_retry_is_made(fake_gemini):
    fake_gemini.push(overloaded(), overloaded(), extraction_json())
    with pytest.raises(PipelineError):
        await ask()
    assert len(fake_gemini.calls) == 2, "a third call would have succeeded; retries must stop at one"


async def test_a_gone_daily_quota_is_not_retried(fake_gemini):
    fake_gemini.push(daily_quota_gone(), extraction_json())
    with pytest.raises(PipelineError):
        await ask()
    assert len(fake_gemini.calls) == 1, "retrying cannot fix a daily quota"


@pytest.mark.parametrize("error", [api_error(genai_errors.ClientError, 400, "Bad request"), api_error(genai_errors.ClientError, 404, "no such model")])
async def test_client_errors_are_not_retried(fake_gemini, error):
    fake_gemini.push(error, extraction_json())
    with pytest.raises(PipelineError):
        await ask()
    assert len(fake_gemini.calls) == 1


# ---------- short, safe messages ----------

@pytest.mark.parametrize(
    "error, expected",
    [
        (rate_limited(), "rate limit"),
        (overloaded(), "overloaded"),
        (api_error(genai_errors.ClientError, 400, "API key not valid. Please pass a valid API key."), "GEMINI_API_KEY"),
        (api_error(genai_errors.ClientError, 403, "forbidden"), "GEMINI_API_KEY"),
        (api_error(genai_errors.ClientError, 418, "teapot"), "HTTP 418"),
    ],
)
async def test_errors_become_short_messages_without_provider_text(fake_gemini, error, expected):
    fake_gemini.default = lambda c, cfg: error
    with pytest.raises(PipelineError) as e:
        await ask()
    assert e.value.code == ErrorCode.LLM_FAILED and expected in e.value.message
    assert len(e.value.message) < 120 and "{" not in e.value.message, "provider JSON leaked into the message"


# ---------- fallback model ----------

async def test_fallback_answers_when_the_main_model_stays_overloaded(fake_gemini, two_models):
    fake_gemini.push(overloaded(), overloaded(), extraction_json())
    assert (await ask()).company.name == "Acme"
    assert models_called(fake_gemini) == ["main-model", "main-model", "backup-model"]


async def test_fallback_is_tried_when_the_main_models_daily_quota_is_gone(fake_gemini, two_models):
    fake_gemini.push(daily_quota_gone(), extraction_json())
    await ask()
    assert models_called(fake_gemini) == ["main-model", "backup-model"], "no retry on the quota-less model, straight to the backup"


async def test_fallback_is_not_used_when_the_main_model_works(fake_gemini, two_models):
    await ask()
    assert models_called(fake_gemini) == ["main-model"]


async def test_fallback_is_not_used_for_a_rejected_key(fake_gemini, two_models):
    fake_gemini.push(api_error(genai_errors.ClientError, 400, "API key not valid"), extraction_json())
    with pytest.raises(PipelineError):
        await ask()
    assert models_called(fake_gemini) == ["main-model"], "a bad key fails identically on any model"


async def test_when_both_models_fail_the_error_is_still_short(fake_gemini, two_models):
    fake_gemini.default = lambda c, cfg: overloaded()
    with pytest.raises(PipelineError) as e:
        await ask()
    assert models_called(fake_gemini) == ["main-model", "main-model", "backup-model"]
    assert len(e.value.message) < 120


async def test_a_fallback_equal_to_the_main_model_is_ignored(fake_gemini, monkeypatch):
    monkeypatch.setattr(app_config, "GEMINI_MODEL", "same")
    monkeypatch.setattr(app_config, "GEMINI_FALLBACK_MODEL", "same")
    fake_gemini.default = lambda c, cfg: overloaded()
    with pytest.raises(PipelineError):
        await ask()
    assert len(fake_gemini.calls) == 2


async def test_drafting_uses_its_own_model_and_still_falls_back(fake_gemini, monkeypatch):
    monkeypatch.setattr(app_config, "GEMINI_DRAFT_MODEL", "writer-model")
    monkeypatch.setattr(app_config, "GEMINI_FALLBACK_MODEL", "backup-model")
    fake_gemini.push(overloaded(), overloaded())  # both attempts on the writer model fail, the fallback gets the default answer
    fact = Fact(id=1, person="Jane Roe", text="She keeps Acme calm.", quote="Acme stays calm.", source_url="https://x.example", source_title="X", kind="own_words", specificity=5, date=None)
    request = DraftRequest(url="https://acme.example", company={"name": "Acme", "one_liner": "Acme makes calm software."}, founders=[{"name": "Jane Roe"}], pitch="I sell async update tools to small remote teams.", facts=[fact])
    end = terminal(await collect(draft(request)))[0]
    assert end.type == "result"
    assert models_called(fake_gemini) == ["writer-model", "writer-model", "backup-model"]


# ---------- deadlines ----------

async def test_a_hung_model_ends_in_a_timeout_error_in_the_analyze_pipeline(hostile, allow_local, fake_gemini, fake_search, monkeypatch):
    fake_gemini.latency = 3600
    monkeypatch.setattr(app_config, "PIPELINE_TIMEOUT", 1.5)
    started = asyncio.get_running_loop().time()
    events = await asyncio.wait_for(collect(analyze(hostile.base + "/")), 8)
    end = terminal(events)
    assert len(end) == 1 and end[0].type == "error" and end[0].code == ErrorCode.TIMEOUT
    assert asyncio.get_running_loop().time() - started < 5


async def test_a_hung_model_ends_in_a_timeout_error_in_the_draft_pipeline(fake_gemini, monkeypatch):
    fake_gemini.latency = 3600
    monkeypatch.setattr(app_config, "DRAFT_TIMEOUT", 1.5)
    fact = Fact(id=1, person="Jane Roe", text="t", quote="q", source_url="https://x.example", source_title="X", kind="own_words", specificity=5, date=None)
    request = DraftRequest(url="https://acme.example", company={"name": "Acme", "one_liner": "Acme."}, founders=[{"name": "Jane Roe"}], pitch="I sell async update tools to small remote teams.", facts=[fact])
    end = terminal(await asyncio.wait_for(collect(draft(request)), 8))
    assert len(end) == 1 and end[0].code == ErrorCode.TIMEOUT


async def test_events_before_the_deadline_are_still_delivered(hostile, allow_local, fake_gemini, fake_search, monkeypatch):
    fake_gemini.latency = 3600
    monkeypatch.setattr(app_config, "PIPELINE_TIMEOUT", 1.5)
    events = await collect(analyze(hostile.base + "/"))
    messages = [e.message for e in events if e.type == "progress"]
    assert any("scraping the website" in m for m in messages), "progress made before the timeout must not be lost"


async def test_a_healthy_run_is_not_affected_by_the_deadline(hostile, allow_local, fake_gemini, fake_search):
    end = terminal(await collect(analyze(hostile.base + "/")))
    assert len(end) == 1 and end[0].type == "result"


async def test_the_timeout_leaves_no_task_running(hostile, allow_local, fake_gemini, fake_search, monkeypatch):
    fake_gemini.latency = 3600
    monkeypatch.setattr(app_config, "PIPELINE_TIMEOUT", 1.0)
    before = set(asyncio.all_tasks())
    await collect(analyze(hostile.base + "/"))
    await asyncio.sleep(0.2)
    assert not (set(asyncio.all_tasks()) - before), "a task from the timed-out run is still alive"
    assert fake_gemini.in_flight == 0, "the hung model call was not cancelled"
