import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field

from app.schemas.company import Company, ExtractedCompany, Founder, UnescapedModel
from app.schemas.limits import clip, first
from app.schemas.scrape import ScrapedPage
from app.services.llm import generate_json
from app.services.prompting import pages_block
from app.services.textmatch import has_word, norm

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
    name: Annotated[str, clip(100)]
    role: Annotated[str | None, clip(100)]
    relationship: Relationship
    confidence: float
    evidence: Annotated[str, clip(500)]


class ExtractionOutput(BaseModel):
    """The JSON shape Gemini must return."""

    company: ExtractedCompany
    people: Annotated[list[ExtractedPerson], first(50)] = Field(
        description="Everyone named with a founder/CEO title, tagged by relationship"
    )


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
    prompt, sent = pages_block(pages, label)  # capped; `sent` is exactly what the model gets to see
    system_prompt = SYSTEM_PROMPT
    if source == "web":
        about = f" (which {company_hint.rstrip('.')})" if company_hint else ""
        system_prompt += WEB_ADDENDUM.format(domain=domain, about=about)
    result = await generate_json(step=STEP, system_prompt=system_prompt, prompt=prompt, schema=ExtractionOutput)
    company = Company(name=result.company.name.strip(), one_liner=result.company.one_liner.strip())
    return company, verified_founders(result.people, sent, source)


def verified_founders(
    people: list[ExtractedPerson], pages: list[ScrapedPage], source: Literal["site", "web"] = "site"
) -> list[Founder]:
    """Keep only founder/CEO candidates whose quoted evidence really appears on a scraped page."""
    page_texts = [(p.url, norm(p.text)) for p in pages]
    corpus = " ".join(text for _, text in page_texts)
    founders: list[Founder] = []
    ceos: list[Founder] = []  # listed after real founders

    for person in people:
        if person.relationship not in KEEP:
            continue
        evidence = norm(person.evidence)
        name_parts = norm(person.name).split()
        # The quote must mention the person (first or last name is enough: "Hello, I'm Marie, co-founder")
        # and their full name must appear somewhere in the material we read.
        mentioned = any(has_word(evidence, part) for part in name_parts)
        known = all(has_word(corpus, part) for part in name_parts)
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
    tokens = [set(norm(f.name).split()) for f in founders]
    result = []
    for i, founder in enumerate(founders):
        redundant = any(
            j != i and (tokens[i] < tokens[j] or (tokens[i] == tokens[j] and j < i)) for j in range(len(founders))
        )
        if not redundant:
            result.append(founder)
    return result
