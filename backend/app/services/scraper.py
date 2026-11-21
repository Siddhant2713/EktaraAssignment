import asyncio
import ipaddress
import json
import re
import socket
from urllib.parse import urldefrag, urljoin, urlparse

import httpx
import trafilatura
from lxml import html as lxml_html
from lxml.etree import ParserError

from app import config
from app.schemas.events import ErrorCode
from app.schemas.scrape import ScrapedPage
from app.services.errors import PipelineError

STEP = "scrape"

# A link is worth following when its LAST path segment is one of these (earlier = more likely to name
# the founder). Whole-segment matching keeps product pages like /sales-teams or /features/teams out.
PAGE_SLUGS = [
    "founders", "founder", "team", "our-team", "the-team", "meet-the-team", "leadership",
    "about", "about-us", "aboutus", "who-we-are", "our-story", "story", "people", "company",
]
# Paths we try even when the homepage doesn't link to them (JS menus, footers we couldn't parse)
GUESS_PATHS = ["/about", "/team", "/about-us", "/founders", "/our-story", "/company"]
SKIP_FIRST_SEGMENTS = {"blog", "news", "press", "careers", "jobs", "docs", "help", "support"}
MAX_PATH_DEPTH = 2

HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}
MAX_REDIRECTS = 5
BLOCKED_STATUSES = {401, 403, 429, 503}
MIN_EXTRACTED_CHARS = 200  # below this, trafilatura probably missed the content
MAX_PROFILE_LINKS = 8
LINKEDIN_PERSON = re.compile(r"^https?://([a-z]{2,3}\.)?linkedin\.com/in/[^/?#]+", re.I)


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(headers=HEADERS, timeout=config.FETCH_TIMEOUT, follow_redirects=False)


async def scrape_site(url: str) -> list[ScrapedPage]:
    """Fetch the homepage plus a few about/team pages and return their readable text."""
    async with _client() as client:
        home_url, home_html = await _fetch(client, url)  # failure here is fatal
        home_page, links = await asyncio.to_thread(_parse, home_url, home_html)

        candidates = _with_guesses(links, home_url)[: config.MAX_FETCH_ATTEMPTS]
        extra = await _collect(
            client,
            candidates,
            room=config.MAX_PAGES - 1,
            seen_urls={_key(url), _key(home_url)},
            seen_text={home_page.text[:300]},
        )

    pages = [p for p in [home_page, *extra] if p.text]
    if not pages:
        raise PipelineError(
            STEP, ErrorCode.NO_CONTENT, "no readable text found; the site may render its content with JavaScript"
        )
    return pages


async def fetch_pages(urls: list[str], limit: int) -> list[ScrapedPage]:
    """Fetch arbitrary URLs (e.g. search results) and return up to `limit` readable, distinct pages.

    Pages that fail to load are skipped, so the result may be shorter than `limit`, or empty.
    """
    async with _client() as client:
        return await _collect(client, urls, room=limit, seen_urls=set(), seen_text=set())


async def _collect(
    client: httpx.AsyncClient, urls: list[str], room: int, seen_urls: set[str], seen_text: set[str]
) -> list[ScrapedPage]:
    """Fetch `urls` concurrently; keep up to `room` readable pages we don't already have, in input order."""
    results = await asyncio.gather(*(_fetch(client, u) for u in urls), return_exceptions=True)
    pages: list[ScrapedPage] = []
    for result in results:  # results are in input order, so earlier (better) URLs win the slots
        if len(pages) >= room:
            break
        if isinstance(result, PipelineError):
            continue  # one missing or blocked page shouldn't kill the run
        if isinstance(result, BaseException):
            raise result
        final_url, html = result
        if _key(final_url) in seen_urls:
            continue  # redirected to a page we already have
        page, _ = await asyncio.to_thread(_parse, final_url, html)
        if not page.text or page.text[:300] in seen_text:
            continue  # empty, or a "soft 404" that serves the same text for every path
        seen_urls.add(_key(final_url))
        seen_text.add(page.text[:300])
        pages.append(page)
    return pages


async def _ensure_public(url: str) -> None:
    """Reject non-http URLs and hosts that resolve to private/loopback addresses (SSRF guard)."""
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise PipelineError(STEP, ErrorCode.INVALID_URL, "only http(s) URLs are supported")
    try:
        infos = await asyncio.to_thread(socket.getaddrinfo, parsed.hostname, None)
    except socket.gaierror:
        raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, f"could not resolve {parsed.hostname}")
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split("%")[0])
        if not ip.is_global:
            raise PipelineError(STEP, ErrorCode.INVALID_URL, "private or local addresses are not allowed")


async def _fetch(client: httpx.AsyncClient, url: str) -> tuple[str, str]:
    """GET a page, following redirects by hand so every hop is checked. Returns (final_url, html)."""
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        await _ensure_public(current)
        try:
            resp = await client.get(current)
        except httpx.TimeoutException:
            raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, f"{current} timed out")
        except httpx.HTTPError as e:
            raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, f"could not connect to {current} ({type(e).__name__})")

        if resp.is_redirect:
            location = resp.headers.get("location")
            if not location:
                raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, f"{current} sent a bad redirect")
            current = urljoin(current, location)
            continue
        if resp.status_code in BLOCKED_STATUSES:
            raise PipelineError(STEP, ErrorCode.SITE_BLOCKED, f"{current} refused the request (HTTP {resp.status_code})")
        if resp.status_code >= 400:
            raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, f"{current} returned HTTP {resp.status_code}")
        if "html" not in resp.headers.get("content-type", ""):
            raise PipelineError(STEP, ErrorCode.NO_CONTENT, f"{current} is not an HTML page")
        return current, resp.text
    raise PipelineError(STEP, ErrorCode.SITE_UNREACHABLE, "too many redirects")


def _parse(url: str, html: str) -> tuple[ScrapedPage, list[str]]:
    """Turn raw HTML into clean text (plus structured hints), and find links worth fetching next."""
    try:
        tree = lxml_html.fromstring(html)
    except (ParserError, ValueError):
        return ScrapedPage(url=url, title="", text=""), []

    title = " ".join((tree.findtext(".//title") or "").split())
    links = _candidate_links(tree, url)
    hints = _structured_hints(tree, url)  # read before scripts get stripped below

    text = trafilatura.extract(html, url=url, favor_recall=True) or ""
    if len(text) < MIN_EXTRACTED_CHARS:
        for el in tree.xpath("//script|//style|//noscript"):
            el.drop_tree()
        text = " ".join(tree.text_content().split())

    text = text[: config.MAX_CHARS_PER_PAGE]
    if text:  # hints are added after truncation so a long page can't push them out
        text = "\n".join([text, *hints])
    return ScrapedPage(url=url, title=title, text=text), links


def _key(url: str) -> str:
    """URL identity for de-duplication: ignores fragment, query and trailing slash."""
    parsed = urlparse(urldefrag(url)[0])
    return parsed._replace(query="", path=parsed.path.rstrip("/")).geturl().lower()


def _host(url: str) -> str:
    return (urlparse(url).hostname or "").removeprefix("www.")


def _segments(path: str) -> list[str]:
    return [s for s in path.lower().split("/") if s]


def _candidate_links(tree, base_url: str) -> list[str]:
    """Same-site links that look like an about/team page, best matches first."""
    ranked: dict[str, tuple[int, int]] = {}
    for href in tree.xpath("//a/@href"):
        absolute, _ = urldefrag(urljoin(base_url, href))
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https") or _host(absolute) != _host(base_url):
            continue
        segments = _segments(parsed.path)
        if not segments or len(segments) > MAX_PATH_DEPTH or segments[0] in SKIP_FIRST_SEGMENTS:
            continue
        if segments[-1] not in PAGE_SLUGS:
            continue
        clean = parsed._replace(query="").geturl()
        if _key(clean) == _key(base_url):
            continue
        rank = (PAGE_SLUGS.index(segments[-1]), len(parsed.path))
        ranked[clean] = min(rank, ranked.get(clean, rank))
    return sorted(ranked, key=ranked.get)


def _with_guesses(links: list[str], home_url: str) -> list[str]:
    """Linked pages first, then common paths the homepage didn't link to."""
    parsed = urlparse(home_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = list(links)
    known = {_key(c) for c in candidates} | {_key(home_url)}
    for path in GUESS_PATHS:
        guess = origin + path
        if _key(guess) not in known:
            candidates.append(guess)
    return candidates


def _structured_hints(tree, base_url: str) -> list[str]:
    """Machine-readable founder clues that never show up in the visible text."""
    hints = []
    names = _json_ld_founders(tree)
    if names:
        hints.append(f"[Structured data lists the founder(s) as: {', '.join(names)}]")
    profiles = _linkedin_links(tree, base_url)
    if profiles:
        hints.append("[LinkedIn profile links on this page: " + "; ".join(profiles) + "]")
    return hints


def _json_ld_founders(tree) -> list[str]:
    """Names from schema.org JSON-LD blocks ({"@type": "Organization", "founder": ...})."""
    names: list[str] = []
    for script in tree.xpath('//script[@type="application/ld+json"]'):
        try:
            data = json.loads(script.text or "")
        except ValueError:
            continue
        _collect_founders(data, names)
    return list(dict.fromkeys(n for n in names if n))


def _collect_founders(node, names: list[str]) -> None:
    if isinstance(node, list):
        for item in node:
            _collect_founders(item, names)
    elif isinstance(node, dict):
        for key in ("founder", "founders"):
            _add_names(node.get(key), names)
        for value in node.values():  # JSON-LD often nests objects, e.g. under "@graph"
            if isinstance(value, (list, dict)):
                _collect_founders(value, names)


def _add_names(value, names: list[str]) -> None:
    if isinstance(value, str):
        names.append(value.strip())
    elif isinstance(value, dict) and isinstance(value.get("name"), str):
        names.append(value["name"].strip())
    elif isinstance(value, list):
        for item in value:
            _add_names(item, names)


def _linkedin_links(tree, base_url: str) -> list[str]:
    """Links to personal LinkedIn profiles, with their visible label (often the person's name)."""
    found: dict[str, str] = {}
    for a in tree.xpath("//a[@href]"):
        url = urldefrag(urljoin(base_url, a.get("href")))[0].split("?")[0]
        if LINKEDIN_PERSON.match(url) and url not in found:
            label = " ".join(a.text_content().split())[:40]
            found[url] = label or "link"
    return [f"{label} -> {url}" for url, label in list(found.items())[:MAX_PROFILE_LINKS]]
