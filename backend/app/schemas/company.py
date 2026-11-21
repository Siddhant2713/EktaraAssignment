from html import unescape
from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator

from app.schemas.limits import clip

MAX_NAME_CHARS = 100
MAX_ONE_LINER_CHARS = 300


class UnescapedModel(BaseModel):
    """Gemini sometimes returns HTML entities ('&amp;'); decode them on the way in."""

    @field_validator("*", mode="before")
    @classmethod
    def _unescape(cls, v):
        return unescape(v) if isinstance(v, str) else v


class Company(UnescapedModel):
    """A company as the API sees it. Too-long text is rejected (this class is also used for request bodies)."""

    name: str = Field(max_length=MAX_NAME_CHARS, description="Company or product name")
    one_liner: str = Field(max_length=MAX_ONE_LINER_CHARS, description="One plain sentence on what the company does")


class ExtractedCompany(UnescapedModel):
    """What the LLM returns for the company. Too-long text is cut, not refused."""

    name: Annotated[str, clip(MAX_NAME_CHARS)] = Field(description="Company or product name")
    one_liner: Annotated[str, clip(MAX_ONE_LINER_CHARS)] = Field(description="One plain sentence on what the company does")


class Founder(UnescapedModel):
    name: str
    role: str | None
    confidence: float  # 0 to 1, as reported by the model
    source: Literal["site", "web"]  # the company's own pages, or a web search result
    source_url: str  # page where the evidence was found (set by us, not the model)
    evidence: str  # exact passage from that page naming this person and their role
