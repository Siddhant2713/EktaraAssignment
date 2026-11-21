from pydantic import BaseModel, HttpUrl

from app.schemas.company import Company, Founder


class AnalyzeRequest(BaseModel):
    url: HttpUrl


class AnalyzeResult(BaseModel):
    company: Company
    founders: list[Founder]  # empty when the site doesn't name anyone
    pages_scraped: list[str]
