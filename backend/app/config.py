import os

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"
# the model that writes the openers; extraction can stay on a cheap model, but the writing benefits from a better one
GEMINI_DRAFT_MODEL = os.getenv("GEMINI_DRAFT_MODEL") or GEMINI_MODEL

# scraping limits
MAX_PAGES = 5  # homepage + up to 4 extra pages (about, team, ...)
MAX_FETCH_ATTEMPTS = 7  # extra pages we try to fetch to fill those slots (some will 404)
MAX_CHARS_PER_PAGE = 6000
FETCH_TIMEOUT = 10.0  # seconds

# when the site yields less text than this, treat it as unreadable and use web search instead
MIN_SITE_CHARS = 300

# web search fallback
SEARCH_RESULTS_PER_QUERY = 6
