from pydantic import BaseModel


class ScrapedPage(BaseModel):
    url: str
    title: str
    text: str
