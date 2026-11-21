import os

from dotenv import load_dotenv

load_dotenv()  # reads backend/.env if it exists

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.1-flash-lite"

# scraping limits
MAX_PAGES = 5  # homepage + up to 4 extra pages (about, team, ...)
MAX_FETCH_ATTEMPTS = 7  # extra pages we try to fetch to fill those slots (some will 404)
MAX_CHARS_PER_PAGE = 6000
FETCH_TIMEOUT = 10.0  # seconds
