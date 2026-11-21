from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field, HttpUrl

from app.schemas.company import Company


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
    id: int  # what an Opener points at
    person: str  # which founder it is about
    text: str  # one plain sentence
    quote: str  # exact passage from the source page that backs it up
    source_url: str
    source_title: str
    kind: FactKind
    specificity: int  # 1 (repeated everywhere) to 5 (only they would recognise it)
    date: str | None


class Opener(BaseModel):
    to: str  # which founder it is written to
    text: str
    fact_ids: list[int]  # the facts this opener is built on; empty for a fallback opener
    angle: str  # a few words naming the hook, e.g. "their post on pricing"


class DraftRequest(BaseModel):
    url: HttpUrl
    company: Company
    founders: list[Person] = Field(min_length=1, max_length=2)  # one email goes to one person
    pitch: str = Field(min_length=10, max_length=600)  # what the sender sells or asks for
    tone: Tone = Tone.CASUAL
    facts: list[Fact] | None = None  # cached from an earlier run; skips the research when present


class DraftResult(BaseModel):
    openers: list[Opener]
    facts: list[Fact]
    used_fallback: bool  # True when no verified facts were found and the openers use only the company site
