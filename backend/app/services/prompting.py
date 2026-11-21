from app import config
from app.schemas.scrape import ScrapedPage

MIN_USEFUL_CHARS = 500  # a page with less room than this is not worth including


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
        text = page.text[:room]
        used.append(page if len(text) == len(page.text) else page.model_copy(update={"text": text}))
        parts.append(header + text)
        remaining -= len(header) + len(text) + 2  # 2 for the blank line between pages
    return "\n\n".join(parts), used
