import logging
import re
from html import unescape
from typing import Literal

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field, ValidationError

from app import config
from app.schemas.company import Company, Founder, UnescapedModel
from app.schemas.events import ErrorCode
from app.schemas.scrape import ScrapedPage
from app.services.errors import PipelineError

log = logging.getLogger(__name__)
STEP = "extract"

SYSTEM_PROMPT = """You extract facts about a company from the text of its website pages.

Rules:
- Use ONLY what the pages say. Never use outside knowledge and never guess.
- company.one_liner: one plain sentence on what the company does.
- people: list every person the pages name in connection with a founder/CEO title, and label each one
  with a relationship:
    "founder"       explicitly described as the founder of THIS company
    "cofounder"     explicitly described as a co-founder of THIS company
    "ceo"           described as CEO of THIS company but not called a founder
    "other_company" a customer, testimonial author, investor or partner who is a founder/CEO of a
                    DIFFERENT company (e.g. "Jane Doe, Co-founder at Acme" in a testimonial)
    "other"         anyone else
- Testimonials and customer quotes are a trap: a founder title next to another company's name does NOT
  make that person a founder of this company.
- name: exactly as written on the pages. If only first names are given (e.g. a signature such as
  "Uku and Marko, Co-founders"), use what is written, one entry per person.
- evidence: copy, character for character, the shortest passage that contains the person's name and
  their role. Do not paraphrase or fix typos.
- Lines in [square brackets] at the end of a page are machine-extracted hints (structured data,
  LinkedIn links). You may use them as evidence.
- confidence: 0.9+ if a page explicitly calls them founder/co-founder/CEO of this company, about 0.5 if
  it is implied, below 0.4 if unsure.
- If nobody is named, return an empty people list."""

WEB_ADDENDUM = """

IMPORTANT: this text is NOT the company's own website. It is a list of web search results, each with a
title and a snippet. They may be about other companies that share a similar name.
- Only count people clearly tied to the company that operates {domain}{about}.
- A person tied to a different company with a similar name gets the relationship "other_company".
- Treat the snippets as pages for the evidence rule: copy the passage exactly as written."""

Relationship = Literal["founder", "cofounder", "ceo", "other_company", "other"]
KEEP = ("founder", "cofounder", "ceo")  # relationships that become Founder results


class ExtractedPerson(UnescapedModel):
    name: str
    role: str | None
    relationship: Relationship
    confidence: float
    evidence: str


class ExtractionOutput(BaseModel):
    """The JSON shape Gemini must return."""

    company: Company
    people: list[ExtractedPerson] = Field(description="Everyone named with a founder/CEO title, tagged by relationship")


async def extract_company_and_founders(
    pages: list[ScrapedPage],
    *,
    source: Literal["site", "web"] = "site",
    domain: str = "",
    company_hint: str | None = None,
) -> tuple[Company, list[Founder]]:
    """Ask Gemini who founded the company, then keep only the founders backed by a quote in `pages`.

    source="site": `pages` are the company's own pages. source="web": they are search results, and
    `domain` / `company_hint` (what the company does) help reject namesake companies.
    """
    label = "RESULT" if source == "web" else "PAGE"
    prompt = "\n\n".join(f"### {label}: {p.url}\n(title: {p.title})\n{p.text}" for p in pages)
    system_prompt = SYSTEM_PROMPT
    if source == "web":
        about = f" (which {company_hint.rstrip('.')})" if company_hint else ""
        system_prompt += WEB_ADDENDUM.format(domain=domain, about=about)
    client = genai.Client(api_key=config.GEMINI_API_KEY)

    try:
        response = await client.aio.models.generate_content(
            model=config.GEMINI_MODEL,
            contents=prompt,
            config={
                "system_instruction": system_prompt,
                "response_mime_type": "application/json",
                "response_json_schema": ExtractionOutput.model_json_schema(),
                "temperature": 0,
            },
        )
    except genai_errors.APIError as e:
        log.warning("Gemini call failed: %s", e)
        raise PipelineError(STEP, ErrorCode.LLM_FAILED, f"Gemini request failed (HTTP {e.code}): {e.message}")

    if not response.text:
        raise PipelineError(STEP, ErrorCode.LLM_FAILED, "Gemini returned an empty response")
    try:
        result = ExtractionOutput.model_validate_json(response.text)
    except ValidationError:
        log.warning("Unparseable Gemini output: %s", response.text)
        raise PipelineError(STEP, ErrorCode.LLM_FAILED, "Gemini returned a response in an unexpected format")

    return result.company, verified_founders(result.people, pages, source)


_PUNCTUATION = str.maketrans(
    {"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-", " ": " "}
)


def _norm(text: str) -> str:
    """Make text comparable: decode entities, straighten quotes, ignore case and whitespace."""
    return " ".join(unescape(text).translate(_PUNCTUATION).casefold().split())


def _has_word(text: str, word: str) -> bool:
    """Whole-word match, so 'sam' does not match inside 'samuel'. (?<!\\w) also copes with names like 'j.b.'."""
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", text) is not None


def verified_founders(
    people: list[ExtractedPerson], pages: list[ScrapedPage], source: Literal["site", "web"] = "site"
) -> list[Founder]:
    """Keep only founder/CEO candidates whose quoted evidence really appears on a scraped page."""
    page_texts = [(p.url, _norm(p.text)) for p in pages]
    corpus = " ".join(text for _, text in page_texts)
    founders: list[Founder] = []
    ceos: list[Founder] = []  # listed after real founders

    for person in people:
        if person.relationship not in KEEP:
            continue
        evidence = _norm(person.evidence)
        name_parts = _norm(person.name).split()
        # The quote must mention the person (first or last name is enough: "Hello, I'm Marie, co-founder")
        # and their full name must appear somewhere in the material we read.
        mentioned = any(_has_word(evidence, part) for part in name_parts)
        known = all(_has_word(corpus, part) for part in name_parts)
        if not evidence or not name_parts or not (mentioned and known):
            log.info("Dropping %r: quote does not mention them, or their name is not in the text", person.name)
            continue
        source_url = next((url for url, text in page_texts if evidence in text), None)
        if source_url is None:
            log.info("Dropping %r: evidence quote not found in any page", person.name)
            continue
        founder = Founder(
            name=person.name.strip(),
            role=person.role,
            confidence=min(max(person.confidence, 0.0), 1.0),
            source=source,
            source_url=source_url,
            evidence=person.evidence.strip(),
        )
        (ceos if person.relationship == "ceo" else founders).append(founder)

    return _dedupe(founders + ceos)


def _dedupe(founders: list[Founder]) -> list[Founder]:
    """Drop repeats, including a bare first name when the full name is also listed."""
    tokens = [set(_norm(f.name).split()) for f in founders]
    result = []
    for i, founder in enumerate(founders):
        redundant = any(
            j != i and (tokens[i] < tokens[j] or (tokens[i] == tokens[j] and j < i)) for j in range(len(founders))
        )
        if not redundant:
            result.append(founder)
    return result
