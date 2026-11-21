import logging
import re

from pydantic import BaseModel, Field

from app.schemas.company import Company, UnescapedModel
from app.schemas.draft import Fact, FactKind, Person
from app.schemas.scrape import ScrapedPage
from app.services.llm import generate_json
from app.services.researcher import research_person
from app.services.textmatch import has_word, norm

log = logging.getLogger(__name__)
STEP = "research"

FACTS_PER_PERSON = 4
# Personal topics we never use as a hook. Checked in code because the prompt rule alone gets ignored.
# Over-matching is fine here (it only drops a fact); a missed match would be creepy.
SENSITIVE = re.compile(
    r"\b(wife|husband|spouse|girlfriend|boyfriend|married|marriage|divorce\w*|kids?|child|children|daughter|son|baby"
    r"|pregnan\w*|family|mother|father|cancer|surgery|diagnos\w*|depress\w*|religio\w*|church|republican|democrat\w*)\b"
)
KIND_PRIORITY = {"own_words": 0, "decision": 1, "launch": 2, "career": 3, "other": 4, "milestone": 5}

SYSTEM_PROMPT = """You find facts about one person from web pages, so that someone can write a genuinely \
personal opening line to them.

The person: {name}{role}, founder of {company} ({one_liner}).

Rules:
- Use ONLY what the pages say. Never use outside knowledge.
- Only facts about THIS person. Pages may also mention other people, or other people with the same name; ignore them.
- Professional and public only: their work, products, decisions, opinions, writing, talks. Never family, health,
  relationships, personal finances, politics, religion, or where they live.
- Prefer, in this order: (1) their own words (a quote, a post, an interview answer), (2) a specific decision
  they made and why, (3) something specific they built or shipped, (4) background. Avoid generic facts that every
  article repeats (founded the company, raised money, valuation, "serial entrepreneur").
- text: one plain sentence (at most 25 words) saying what the fact is, in your own words. Write "he said" or
  "he describes" only when the quote really is their own words; otherwise state the fact neutrally.
- quote: copy, character for character, the passage that supports it (at most 300 characters). Never paraphrase.
- specificity: 5 = a detail only they would recognise as theirs (a quoted opinion, a decision with its reason);
  3 = a concrete thing they built or did; 1 = a generic fact repeated everywhere.
- date: the date or year the page gives for it, or null.
- Return at most 8 facts, best first. If the pages hold nothing usable about this person, return an empty list."""


class ExtractedFact(UnescapedModel):
    text: str
    quote: str
    kind: FactKind
    specificity: int = Field(description="1 to 5")
    date: str | None


class FactsOutput(BaseModel):
    facts: list[ExtractedFact]


async def research_facts(person: Person, company: Company, company_site: str) -> list[Fact]:
    """Research one founder and return up to FACTS_PER_PERSON verified facts, best first (ids not yet set).

    Raises PipelineError if the LLM call fails. A founder with no findable material returns an empty list.
    """
    pages = await research_person(person, company.name)
    if not pages:
        return []
    extracted = await _extract(person, company, pages)
    verified = verify_facts(extracted, pages, person, company, company_site)
    return select_facts(verified, FACTS_PER_PERSON)


def number_facts(facts: list[Fact]) -> list[Fact]:
    """Give the facts ids 1..n, in order."""
    return [fact.model_copy(update={"id": i}) for i, fact in enumerate(facts, start=1)]


async def _extract(person: Person, company: Company, pages: list[ScrapedPage]) -> list[ExtractedFact]:
    system_prompt = SYSTEM_PROMPT.format(
        name=person.name,
        role=f" ({person.role})" if person.role else "",
        company=company.name,
        one_liner=company.one_liner.rstrip("."),
    )
    prompt = "\n\n".join(f"### PAGE: {p.url}\n(title: {p.title})\n{p.text}" for p in pages)
    result = await generate_json(step=STEP, system_prompt=system_prompt, prompt=prompt, schema=FactsOutput)
    return result.facts


def verify_facts(
    extracted: list[ExtractedFact],
    pages: list[ScrapedPage],
    person: Person,
    company: Company,
    company_site: str,
) -> list[Fact]:
    """Keep facts whose quote appears word for word on a page that is about this person AND this company."""
    page_texts = [(p, norm(p.text)) for p in pages]
    last_name = norm(person.name).split()[-1]
    company_terms = [norm(company.name), norm(company_site)]
    seen_quotes: set[str] = set()
    kept: list[Fact] = []

    for item in extracted:
        quote = norm(item.quote)
        if len(quote) < 20 or quote in seen_quotes:
            continue
        if SENSITIVE.search(norm(item.text)) or SENSITIVE.search(quote):
            log.info("Dropping sensitive fact for %s: %r", person.name, item.text)
            continue
        source = next(
            (
                page
                for page, text in page_texts
                if quote in text and has_word(text, last_name) and any(term and term in text for term in company_terms)
            ),
            None,
        )
        if source is None:
            log.info("Dropping fact for %s: quote not on a page about them and the company: %r", person.name, item.text)
            continue
        seen_quotes.add(quote)
        kept.append(
            Fact(
                id=0,  # numbered once all founders are processed
                person=person.name,
                text=item.text.strip(),
                quote=item.quote.strip(),
                source_url=source.url,
                source_title=source.title or source.url,
                kind=item.kind,
                specificity=min(max(item.specificity, 1), 5),
                date=item.date,
            )
        )
    return kept


def select_facts(facts: list[Fact], limit: int) -> list[Fact]:
    """Best hooks first: specific beats generic, their own words beat press facts, newer beats older."""
    return sorted(facts, key=lambda f: (-f.specificity, KIND_PRIORITY[f.kind], -_year(f)))[:limit]


def _year(fact: Fact) -> int:
    years = re.findall(r"\b(?:19|20)\d{2}\b", f"{fact.date or ''} {fact.quote}")
    return max(map(int, years), default=0)
