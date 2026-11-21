import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import analyze, draft, health

logging.basicConfig(level=logging.INFO)
logging.getLogger("trafilatura").setLevel(logging.ERROR)  # warns about every JS-only page
for noisy in ("httpx", "httpx2", "primp", "ddgs", "google_genai"):
    logging.getLogger(noisy).setLevel(logging.WARNING)  # one INFO line per request is noise

app = FastAPI(title="Ektara")

# the Vite dev server, plus any deployed frontend listed in CORS_ORIGINS (comma separated)
_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_origins += [o.strip().rstrip("/") for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(analyze.router)
app.include_router(draft.router)
