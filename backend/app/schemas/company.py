from html import unescape

from pydantic import BaseModel, Field, field_validator


class UnescapedModel(BaseModel):
    """Gemini sometimes returns HTML entities ('&amp;'); decode them on the way in."""

    @field_validator("*", mode="before")
    @classmethod
    def _unescape(cls, v):
        return unescape(v) if isinstance(v, str) else v


class Company(UnescapedModel):
    name: str = Field(description="Company or product name")
    one_liner: str = Field(description="One plain sentence on what the company does")


class Founder(UnescapedModel):
    name: str
    role: str | None
    confidence: float  # 0 to 1, as reported by the model
    source_url: str  # page where the evidence was found (set by us, not the model)
    evidence: str  # exact passage from that page naming this person and their role
