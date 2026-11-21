from enum import Enum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.company import Company
from app.schemas.limits import clip, first

MAX_FACTS = 12  # 2 founders x 4 facts each, plus headroom
MAX_FACT_TEXT = 300
MAX_FACT_QUOTE = 500
MAX_URL_CHARS = 500
MAX_TITLE_CHARS = 200
MAX_DATE_CHARS = 40


class Tone(str, Enum):
    CASUAL = "casual"
    FORMAL = "formal"
    SHORT = "short"


# what kind of thing a fact is; own words beat everything else when picking a hook
FactKind = Literal["own_words", "decision", "launch", "career", "milestone", "other"]


class Person(BaseModel):
    """A founder the user confirmed (names may have been edited or added by hand)."""

    name: str = Field(min_length=1, max_length=100)
    role: str | None = Field(default=None, max_length=100)


class Fact(BaseModel):
    """A claim about a founder, with the exact quote that backs it. Sent to the browser and back, so it is bounded."""

    id: int = Field(ge=1, le=100)  # what an Opener points at
    person: str = Field(max_length=100)  # which founder it is about
    text: str = Field(max_length=MAX_FACT_TEXT)  # one plain sentence
    quote: str = Field(max_length=MAX_FACT_QUOTE)  # exact passage from the source page that backs it up
    source_url: str = Field(max_length=MAX_URL_CHARS)
    source_title: str = Field(max_length=MAX_TITLE_CHARS)
    kind: FactKind
    specificity: int = Field(ge=1, le=5)  # 1 (repeated everywhere) to 5 (only they would recognise it)
    date: str | None = Field(max_length=MAX_DATE_CHARS)


class Opener(BaseModel):
    """Written by the LLM, so over-long values are cut (see schemas/limits.py)."""

    to: Annotated[str, clip(100)]  # which founder it is written to
    text: Annotated[str, clip(1200)]
    fact_ids: Annotated[list[int], first(5)]  # the facts this opener is built on; empty for a fallback opener
    angle: Annotated[str, clip(80)]  # a few words naming the hook, e.g. "their post on pricing"


class DraftRequest(BaseModel):
    url: HttpUrl
    company: Company
    founders: list[Person] = Field(min_length=1, max_length=2)  # one email goes to one person
    pitch: str = Field(min_length=10, max_length=600)  # what the sender sells or asks for
    tone: Tone = Tone.CASUAL
    facts: list[Fact] | None = Field(default=None, max_length=MAX_FACTS)  # cached; skips the research when present


class DraftResult(BaseModel):
    openers: list[Opener]
    facts: list[Fact]
    used_fallback: bool  # True when no verified facts were found and the openers use only the company site
