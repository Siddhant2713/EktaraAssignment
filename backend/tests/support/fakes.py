"""A scripted stand-in for the Gemini client, plus canned answers for each pipeline step."""

import asyncio
import json
from types import SimpleNamespace

SITE_QUOTE = "Jane Roe, Founder & CEO"  # appears on the hostile server's /about page
WEB_QUOTE = "Jane Roe founded Acme in 2020"  # appears in the canned search result below

SEARCH_RESULTS = [
    {
        "href": "https://news.example.com/acme",
        "title": "Acme founder",
        "body": f"{WEB_QUOTE} and still runs the company today.",
    }
]


def extraction_json(quote: str = SITE_QUOTE, relationship: str = "founder", people: bool = True) -> str:
    return json.dumps(
        {
            "company": {"name": "Acme", "one_liner": "Acme makes calm software for small teams."},
            "people": (
                [
                    {
                        "name": "Jane Roe",
                        "role": "Founder & CEO",
                        "relationship": relationship,
                        "confidence": 0.95,
                        "evidence": quote,
                    }
                ]
                if people
                else []
            ),
        }
    )


def openers_json(count: int = 3, to: str = "Jane Roe", text: str | None = None, fact_ids=(1,)) -> str:
    base = text or "You keep Acme calm on purpose. We write async updates so teams stop talking about status. Why calm?"
    return json.dumps(
        {
            "openers": [
                {"to": to, "text": f"{base} #{i}", "fact_ids": list(fact_ids), "angle": f"angle {i}"}
                for i in range(count)
            ]
        }
    )


def smart_default(contents: str, config: dict) -> str:
    """Answer each pipeline step with something valid, chosen by the schema the caller asked for."""
    title = config["response_json_schema"]["title"]
    if title == "ExtractionOutput":
        if "### RESULT:" in contents:  # web search results, not the company's own pages
            return extraction_json(WEB_QUOTE)
        return extraction_json(SITE_QUOTE)
    if title == "DraftOutput":
        return openers_json(fact_ids=() if "(none found)" in contents else (1,))  # fallback mode must not cite facts
    if title == "FactsOutput":
        return json.dumps({"facts": []})
    raise AssertionError(f"unexpected schema {title}")


class FakeGemini:
    """Plays the part of `client.aio.models`. Push items to script answers; an Exception item is raised."""

    def __init__(self):
        self.script: list = []
        self.default = smart_default
        self.latency = 0.0
        self.calls: list[dict] = []
        self.in_flight = 0
        self.max_in_flight = 0

    def push(self, *items):
        self.script.extend(items)

    async def generate_content(self, *, model, contents, config=None):
        self.calls.append({"model": model, "contents": contents, "config": config})
        self.in_flight += 1
        self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            if self.latency:
                await asyncio.sleep(self.latency)
            item = self.script.pop(0) if self.script else self.default
            if callable(item):
                item = item(contents, config)
            if isinstance(item, BaseException):
                raise item
            return SimpleNamespace(text=item)
        finally:
            self.in_flight -= 1
