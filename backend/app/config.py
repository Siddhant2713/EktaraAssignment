import os

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"
# the model that writes the openers; extraction can stay on a cheap model, but the writing benefits from a better one
GEMINI_DRAFT_MODEL = os.getenv("GEMINI_DRAFT_MODEL") or GEMINI_MODEL
# tried when the main model is overloaded or out of quota, after one retry. Empty means no fallback.
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL") or ""

# scraping limits
MAX_PAGES = 5  # homepage + up to 4 extra pages (about, team, ...)
MAX_FETCH_ATTEMPTS = 7  # extra pages we try to fetch to fill those slots (some will 404)
MAX_CHARS_PER_PAGE = 6000
FETCH_TIMEOUT = 10.0  # seconds of silence tolerated on one network read
FETCH_DEADLINE = 12.0  # seconds allowed for one whole page fetch, redirects included (slow-loris guard)
MAX_RESPONSE_BYTES = 2 * 1024 * 1024  # decoded bytes read from one page; we only use the first few thousand characters

# whole-request time limits, in seconds (a hung model call must not hold a request open forever)
PIPELINE_TIMEOUT = 90.0  # /api/analyze
DRAFT_TIMEOUT = 120.0  # /api/draft: researches and then writes
LLM_RETRY_DELAY = 1.5  # pause before the one retry of a transient Gemini error (jittered)

# the most text we put into one LLM prompt; later (lower-priority) pages are dropped first
MAX_PROMPT_CHARS = 60_000

# when the site yields less text than this, treat it as unreadable and use web search instead
MIN_SITE_CHARS = 300

# web search fallback
SEARCH_RESULTS_PER_QUERY = 6
