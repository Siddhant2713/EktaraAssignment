"""Everything that enters an LLM prompt has a size limit, and the limits do not break legitimate use."""

import json

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app import config
from app.main import app
from app.schemas.company import Company, ExtractedCompany
from app.schemas.draft import MAX_FACTS, DraftRequest, Fact, Opener
from app.schemas.scrape import ScrapedPage
from app.services import scraper, web_search
from app.services.drafter import DraftOutput
from app.services.extractor import ExtractedPerson, ExtractionOutput, extract_company_and_founders
from app.services.fact_extractor import ExtractedFact, FactsOutput, number_facts, verify_facts
from app.services.prompting import pages_block
from app.schemas.draft import Person
from tests.support.fakes import extraction_json

REQUEST = {
    "url": "https://acme.example",
    "company": {"name": "Acme", "one_liner": "Acme makes calm software."},
    "founders": [{"name": "Jane Roe", "role": "CEO"}],
    "pitch": "I sell async update tools to small remote teams.",
}


def page(i, size=6000):
    return ScrapedPage(url=f"https://x.example/{i}", title="t", text=f"page{i} " + "word " * (size // 5))


def fact(i=1, **over):
    base = dict(id=i, person="Jane Roe", text="t", quote="q", source_url="https://x.example", source_title="X", kind="own_words", specificity=5, date=None)
    return Fact(**{**base, **over})


# ---------- the total budget ----------

def test_pages_block_stays_inside_the_budget_and_keeps_the_earlier_pages():
    block, used = pages_block([page(i) for i in range(50)], "PAGE", budget=20_000)
    assert len(block) <= 20_000
    assert 2 <= len(used) < 50
    assert [p.url for p in used] == [f"https://x.example/{i}" for i in range(len(used))], "order must be preserved"


def test_a_page_that_does_not_fit_is_cut_and_the_pages_after_it_are_dropped():
    block, used = pages_block([page(0), page(1), page(2)], "PAGE", budget=8_000)
    assert len(block) <= 8_000
    assert len(used[0].text) == len(page(0).text), "the first page fits and must be whole"
    assert len(used[1].text) < len(page(1).text), "the second page must be cut to the room left"
    assert len(used) == 2


def test_default_budget_comes_from_config():
    block, _ = pages_block([page(i) for i in range(500)], "PAGE")
    assert len(block) <= config.MAX_PROMPT_CHARS


async def test_text_cut_by_the_budget_cannot_be_cited(fake_gemini, monkeypatch):
    """The quote sits at the end of a page that the budget cuts off, so the model never saw it. A guess must not verify."""
    monkeypatch.setattr(config, "MAX_PROMPT_CHARS", 7_000)
    pages = [page(0), ScrapedPage(url="https://x.example/about", title="About", text="filler " * 800 + " Jane Roe, Founder & CEO")]
    fake_gemini.push(extraction_json("Jane Roe, Founder & CEO"))
    _, founders = await extract_company_and_founders(pages)
    assert founders == []


# ---------- model output is cut, not refused ----------

def test_extracted_fact_fields_are_cut():
    f = ExtractedFact(text="t" * 2000, quote="q" * 5000, kind="own_words", specificity=5, date="d" * 500)
    assert (len(f.text), len(f.quote), len(f.date)) == (300, 500, 40)


def test_extracted_person_and_company_are_cut():
    p = ExtractedPerson(name="n" * 1000, role="r" * 1000, relationship="founder", confidence=1, evidence="e" * 5000)
    assert (len(p.name), len(p.role), len(p.evidence)) == (100, 100, 500)
    c = ExtractedCompany(name="n" * 1000, one_liner="o" * 10_000)
    assert (len(c.name), len(c.one_liner)) == (100, 300)


def test_opener_fields_are_cut():
    o = Opener(to="t" * 500, text="x" * 5000, fact_ids=list(range(100)), angle="a" * 500)
    assert (len(o.to), len(o.text), len(o.fact_ids), len(o.angle)) == (100, 1200, 5, 80)


def test_lists_from_the_model_are_capped():
    people = [{"name": f"P{i}", "role": None, "relationship": "founder", "confidence": 1, "evidence": "e"} for i in range(5000)]
    out = ExtractionOutput.model_validate_json(json.dumps({"company": {"name": "A", "one_liner": "B"}, "people": people}))
    assert len(out.people) == 50
    facts = [{"text": "t", "quote": "q", "kind": "other", "specificity": 1, "date": None}] * 100
    assert len(FactsOutput.model_validate({"facts": facts}).facts) == 20
    opener = {"to": "a", "text": "b", "fact_ids": [], "angle": "c"}
    assert len(DraftOutput.model_validate({"openers": [opener] * 500}).openers) == 20


async def test_an_overlong_company_description_from_the_model_is_cut_not_an_error(fake_gemini):
    fake_gemini.push(json.dumps({"company": {"name": "A" * 500, "one_liner": "Visit http://evil.example " * 500}, "people": []}))
    company, _ = await extract_company_and_founders([page(0)])
    assert len(company.name) <= 100 and len(company.one_liner) <= 300


def test_a_cut_quote_is_a_prefix_so_it_still_verifies():
    long_quote = "I try to be quite ignorant about trends in the industry and who is doing what. " * 20
    pages = [ScrapedPage(url="https://p.example/j", title="Podcast", text=f"Jason Fried of Basecamp said: {long_quote}")]
    item = ExtractedFact(text="He ignores trends.", quote=long_quote, kind="own_words", specificity=5, date=None)
    got = verify_facts([item], pages, Person(name="Jason Fried"), Company(name="Basecamp", one_liner="PM tool."), "basecamp.com")
    assert len(got) == 1 and len(got[0].quote) == 500


def test_facts_the_system_produces_are_accepted_back_from_the_browser():
    """Regenerate sends the facts back. A maximum-size fact we created must pass the request limits we enforce."""
    pages = [ScrapedPage(url="https://p.example/" + "a" * 400, title="T" * 150, text="Jason Fried of Basecamp said: " + "x" * 600)]
    item = ExtractedFact(text="t" * 1000, quote="Jason Fried of Basecamp said: " + "x" * 600, kind="own_words", specificity=9, date="2026")
    produced = number_facts(verify_facts([item], pages, Person(name="Jason Fried"), Company(name="Basecamp", one_liner="PM tool."), "basecamp.com"))
    assert produced, "the fact should verify"
    DraftRequest(**REQUEST, facts=produced)  # must not raise


# ---------- inputs from search results and pages ----------

async def test_search_results_are_bounded(fake_search):
    fake_search.results = [
        {"href": "https://x.example/" + "a" * 600, "title": "too long a url", "body": "b"},
        {"href": "https://ok.example/", "title": "T" * 5000, "body": "B" * 50_000},
    ]
    pages = await web_search.search_pages(["q"])
    assert [p.url for p in pages] == ["https://ok.example/"]
    assert len(pages[0].title) <= 200 and len(pages[0].text) <= 1300


def test_a_huge_page_title_is_cut():
    html = f"<html><head><title>{'T' * 1_000_000}</title></head><body><p>{'word ' * 100}</p></body></html>"
    page_, _ = scraper._parse("https://x.example/", html)
    assert len(page_.title) <= 200


# ---------- the request limits ----------

def test_exactly_max_facts_is_accepted_and_one_more_is_not():
    DraftRequest(**REQUEST, facts=[fact(i) for i in range(1, MAX_FACTS + 1)])
    with pytest.raises(ValidationError):
        DraftRequest(**REQUEST, facts=[fact(i) for i in range(1, MAX_FACTS + 2)])


@pytest.mark.parametrize("company", [{"name": "n" * 101, "one_liner": "ok"}, {"name": "ok", "one_liner": "o" * 301}])
def test_overlong_company_text_in_a_request_is_rejected(company):
    with pytest.raises(ValidationError):
        DraftRequest(**{**REQUEST, "company": company})


@pytest.mark.parametrize("bad", [{"text": "t" * 301}, {"quote": "q" * 501}, {"source_url": "u" * 501}, {"source_title": "s" * 201}, {"person": "p" * 101}, {"date": "d" * 41}, {"specificity": 0}, {"specificity": 6}, {"id": 0}, {"id": 101}])
def test_each_fact_field_has_a_limit(bad):
    with pytest.raises(ValidationError):
        fact(**bad)


def test_a_request_with_every_fact_at_its_maximum_size_still_makes_a_bounded_prompt(fake_gemini):
    big = [fact(i, text="t" * 300, quote="q" * 500, source_url="u" * 500, source_title="s" * 200, date="d" * 40) for i in range(1, MAX_FACTS + 1)]
    body = {**REQUEST, "facts": [f.model_dump() for f in big]}
    response = TestClient(app).post("/api/draft", json=body)
    assert response.status_code == 200
    assert len(fake_gemini.calls[0]["contents"]) < 20_000
