import re

from app import config
from app.schemas.scrape import ScrapedPage

MIN_USEFUL_CHARS = 500  # a page with less room than this is not worth including


def neutralize(text: str) -> str:
    """Make untrusted text unable to write a tag of its own: < and > become entities."""
    return text.replace("<", "&lt;").replace(">", "&gt;")


def fence(tag: str, text: str) -> str:
    """Wrap untrusted text in <tag>...</tag>. It cannot close the tag early, because its own < and > are escaped."""
    return f"<{tag}>\n{neutralize(text)}\n</{tag}>"


def inline(text: str, limit: int = 300) -> str:
    """Make untrusted text safe for a one-line slot in a prompt: a single line, with no tag or code characters.

    Used for company and person names, and for text the model itself wrote from a web page, because that text
    is copied into later prompts (including system prompts), where an injected instruction would carry more weight.
    """
    return re.sub(r"[<>`]", "", " ".join(text.split()))[:limit]


def pages_block(pages: list[ScrapedPage], label: str, budget: int | None = None) -> tuple[str, list[ScrapedPage]]:
    """Join pages into prompt text of at most `budget` characters (default config.MAX_PROMPT_CHARS).

    Earlier pages have priority: a page that does not fit is cut to the room left, and once little room remains
    the rest are dropped. Returns the text AND the pages as the model actually saw them, so that a quote can be
    verified only against text that was really sent.
    """
    remaining = budget or config.MAX_PROMPT_CHARS
    parts: list[str] = []
    used: list[ScrapedPage] = []
    for page in pages:
        header = f"### {label}: {page.url}\n(title: {page.title})\n"
        room = remaining - len(header)
        if room < MIN_USEFUL_CHARS:
            break
        # "###" would let page text forge the header of another page; the model and the quote check see the same text
        text = page.text.replace("###", "# # #")[:room]
        used.append(page if text == page.text else page.model_copy(update={"text": text}))
        parts.append(header + text)
        remaining -= len(header) + len(text) + 2  # 2 for the blank line between pages
    return "\n\n".join(parts), used
