# Ektara

**Paste a company's website. Get three cold-email openers written to its founder, each built on a fact we found and can prove.**

Founders get a lot of cold email, and most openers sound the same ("I came across your company and was impressed..."). Ektara reads the company's site, finds who founded it, researches that person's public work (interviews, podcasts, posts), and writes openers that start from something specific they actually said or did. Every fact is shown with the quote and the page it came from, so you can check it before you send.

- **Backend:** Python 3.11+, FastAPI, Gemini API, `httpx` + `trafilatura` for scraping
- **Frontend:** React + TypeScript (Vite)
- **Status:** works locally end to end. Not deployed. 276 automated tests, with the offline suite fully green (see [Testing](#testing)).

---

## Contents

1. [How it works](#how-it-works)
2. [Setup and running it](#setup-and-running-it)
3. [API reference](#api-reference)
4. [Project structure](#project-structure)
5. [Testing](#testing)
6. [Stress test report](#stress-test-report)
7. [Problems we faced](#problems-we-faced)
8. [Cost breakdown](#cost-breakdown)
9. [The journey in brief](#the-journey-in-brief)
10. [Known limits and next steps](#known-limits-and-next-steps)

---

## How it works

```
 URL ──► POST /api/analyze ───────────────────────────────┐
          1. scrape the site (home, /about, /team ...)    │  live progress
          2. Gemini: who are the founders?                │  streamed to the
          3. no founder / blocked / JS-only site?         │  browser (SSE)
             └─► web search, same extractor, same checks  │
                                                          ▼
                     you confirm or edit the founders (pick up to 2)
                                                          │
 pitch + tone ──► POST /api/draft ────────────────────────┤
          1. search and read pages about each founder     │
          2. Gemini: extract facts, each with a quote     │
          3. keep only facts whose quote is on the page   │
          4. Gemini: write 3 openers from those facts     │
          5. lint (clichés, links, length ...), retry once│
                                                          ▼
                   3 openers, each with the facts and sources behind it
```

Ideas the design rests on:

- **Nothing is believed without a quote.** A founder or fact is only kept if the model's quoted passage appears word for word on a page that mentions both the person and the company. Invented names fail this check.
- **Namesakes are rejected.** "Tally" the form builder is not "Tally Solutions". The extractor is told what the company does and which domain it runs, and facts must come from pages that mention the company.
- **Personal topics are filtered in code.** Family, health, politics and similar never become a hook, even if the model offers them.
- **The opener is linted, not just prompted.** Prompts get ignored, so code rejects clichés ("hope this finds you well"), exclamation marks, links, emails, phone numbers, wrong length, and facts the opener does not legitimately cite. It retries once with the problems listed.
- **No facts? It says so.** If nothing verifiable is found, the openers use only the company description and the UI flags that.
- **Regenerate is cheap.** The facts are sent back by the browser, so changing the tone skips the research (about 4 seconds).

---

## Setup and running it

**You need:** Python 3.11 or newer (developed on 3.12), Node 20 or newer, and a [Gemini API key](https://aistudio.google.com/apikey) (the free tier works, with limits, see [Cost breakdown](#cost-breakdown)).

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then put your key in GEMINI_API_KEY=
uvicorn app.main:app --reload --port 8000
```

Check it: `curl http://localhost:8000/health` returns `{"status":"ok"}`.

`--reload` only watches `.py` files, so restart the server after editing `.env`.

### 2. Frontend

```bash
cd frontend
npm install
npm run dev                 # http://localhost:5173
```

### 3. Use it

1. Paste a company URL, for example `https://basecamp.com`, and press **Go**. Progress lines appear as it works.
2. Check the detected founders (each shows the quote and source), edit names if needed, and tick up to two.
3. Describe what you sell or ask for, pick a tone, and press **Write openers**.
4. Copy the opener you like. **Regenerate** reuses the research; **Research again** starts fresh.

### Configuration (`backend/.env`)

| Variable | Default | What it does |
|---|---|---|
| `GEMINI_API_KEY` | none, required | Your Gemini API key |
| `GEMINI_MODEL` | `gemini-3.1-flash-lite` | Model used for extraction |
| `GEMINI_DRAFT_MODEL` | same as `GEMINI_MODEL` | Model that writes the openers (a stronger one may write better) |
| `GEMINI_FALLBACK_MODEL` | empty (off) | Tried when the main model is overloaded or out of quota. `gemini-3.5-flash-lite` worked in testing |
| `MAX_CONCURRENT_GEMINI` | 6 | Gemini calls in flight at once, across all requests |
| `MAX_CONCURRENT_SEARCHES` | 2 | Web searches in flight at once |
| `MAX_CONCURRENT_FETCHES` | 24 | Page downloads in flight at once |

The frontend reads `VITE_API_URL` (default `http://localhost:8000`).

---

## API reference

Both endpoints stream **server-sent events**: a series of `data: {json}` messages that always ends with exactly one `result` or one `error`.

| Endpoint | Purpose |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /api/analyze` | Body `{"url": "https://..."}`. Scrapes the site and returns the company and its founders. |
| `POST /api/draft` | Researches the chosen founders and writes the openers. |

**`/api/draft` body**

```json
{
  "url": "https://basecamp.com",
  "company": {"name": "Basecamp", "one_liner": "A project management platform."},
  "founders": [{"name": "Jason Fried", "role": "Co-founder & CEO"}],
  "pitch": "I run a small studio that builds internal tools for remote teams.",
  "tone": "casual",
  "facts": null
}
```

`founders`: 1 or 2. `pitch`: 10 to 600 characters. `tone`: `casual`, `formal` or `short`. `facts`: optional, at most 12, the facts from an earlier result; when present the research is skipped.

**Events**

```
{"type": "progress", "step": "scrape", "message": "scraping the website https://basecamp.com/"}
{"type": "result",   "data": { ... }}
{"type": "error",    "step": "extract", "code": "LLM_FAILED", "message": "Gemini is overloaded ..."}
```

Error codes: `CONFIG_MISSING`, `INVALID_URL`, `SITE_UNREACHABLE`, `SITE_BLOCKED`, `NO_CONTENT`, `LLM_FAILED`, `SEARCH_FAILED`, `TIMEOUT`, `INTERNAL_ERROR`.

---

## Project structure

```
backend/
  app/
    main.py                 app, CORS, routers
    config.py               settings and limits
    routers/                thin HTTP layer: health, analyze, draft, sse
    schemas/                data shapes and their size limits
    services/
      scraper.py            fetch pages safely (size cap, deadline, SSRF guard, hidden-text removal)
      web_search.py         keyless web search with retries
      analyzer.py           analyze pipeline (scrape, extract, search fallback)
      extractor.py          Gemini: company and founders, quote verification
      researcher.py         find pages about a founder
      fact_extractor.py     Gemini: facts, verification, ranking, personal-topic filter
      drafter.py            Gemini: openers, prompt, lint
      draft_pipeline.py     draft pipeline
      llm.py                every Gemini call: retry, fallback, short errors
      limiter.py            shared concurrency limits
      deadline.py           whole-request time limit
      prompting.py          prompt budget, fencing, flattening untrusted text
  tests/                    offline suite, hostile web server, fake Gemini; live/ needs --live
frontend/src/
  App.tsx                   the flow
  components/               FounderConfirm, DraftPanel, OpenerCard, ProgressLog, ErrorBanner
  hooks/useStreamTask.ts    reads a streaming response
  api/                      stream, analyze, draft
docs/STRESS_TEST_REPORT.md  full test report with before/after numbers
```

The backend follows an MVC-style split: routers are the controllers, `schemas/` holds the models, the React app is the view, and `services/` is the extra layer where the logic lives.

---

## Testing

```bash
cd backend
pip install -r requirements-dev.txt
pytest                      # offline suite, about 45 seconds, free
pytest -s                   # also prints the load-test numbers
pytest -m "not slow"        # skip the slowest tests
pytest --live               # also runs tests against the real Gemini API and the web
```

The offline tests use a **local hostile web server** (huge pages, gzip bombs, slow servers, redirect loops, poisoned content) and a **scripted fake Gemini**, so they are deterministic and cost nothing. The `--live` tests probe the real model with prompt injections and check founder accuracy on 8 real companies; they skip, rather than fail, when Gemini is overloaded.

**Current result:** 265 passed, 0 failed offline (11 live tests skipped by default); live suite 8 passed, 0 failed, 3 skipped for Gemini overload.

---

## Stress test report

We deliberately tried to break the system: hostile websites, prompt injection, SSRF, API failures and bursts of traffic. The full report, with measured before/after numbers, is in **[docs/STRESS_TEST_REPORT.md](docs/STRESS_TEST_REPORT.md)**. The baseline run had 35 failing tests that reduced to seven problems, all now fixed:

| # | Problem found | Measured at baseline | After the fix |
|---|---|---|---|
| 1 | Scraper had no resource limits | 40 MB page fully downloaded; a few-KB gzip bomb used 326 MB; slow server held a request 26 s | 2.5 MB read; 18 MB peak; gave up at 12 s |
| 2 | Nothing bounded prompts | one page put 409,431 characters into a prompt; a 2 MB `quote` was accepted | 499 characters; 60,000 character budget; oversized input rejected (422) |
| 3 | No deadline, retry or clean errors | a hung model blocked forever; one 503 failed the request; a 429 showed a 1,354-character dump | TIMEOUT at 90 s; one retry; optional fallback model; messages under 120 characters |
| 4 | No concurrency limits | 60 simultaneous Gemini calls, 40 simultaneous searches | 6 and 2, with every request still succeeding |
| 5 | Thin injection guardrails | links, emails and phone numbers passed the opener lint | rejected; untrusted text fenced; "data, not instructions" in every system prompt |
| 6 | Any port allowed | `:22`, `:6379` accepted (a port scanner) | only 80, 443, 8080, 8443 |
| 7 | Fact fields had no ranges | `specificity: 99` accepted | range-checked |

What held up from the start: the SSRF guard blocked every address trick tried (decimal, hex, octal, IPv4-in-IPv6, cloud metadata addresses, redirects to them), malformed pages never crashed the scraper, and 5,000 founders invented by a faked model answer were all rejected by the quote check.

---

## Problems we faced

These are the real problems met while building it, and what solved each.

1. **It only found founders for famous companies.** The scraper chose pages by substring (`"team"` matched `/sales-teams`) and many small companies do not name founders in visible text. *Fix:* match whole path segments, try common paths like `/about` even when unlinked, read the hidden structured data (JSON-LD) and LinkedIn links, and fall back to web search.
2. **Companies with several founders returned one.** The data model allowed a single founder. *Fix:* a list of founders, each with its own evidence, and a confirm card where you tick who to write to.
3. **A testimonial author was almost taken for a founder.** Dub's homepage quotes "Johnny Ho, Co-founder at Perplexity". *Fix:* every candidate is tagged with a relationship (founder, CEO, "founder of another company"), and the prompt names this trap.
4. **Hallucination risk.** A model will happily name a plausible founder. *Fix:* the word-for-word quote rule. It first rejected valid people ("Hello, I'm Marie, co-founder" mentions only a first name), so it was relaxed to "the quote mentions the person and their full name appears in the material".
5. **Sites that cannot be read.** SpaceX returns 6 characters (JavaScript only), Tesla returns HTTP 403, Paytm never names its founder. *Fix:* any of these triggers a web search whose results go through the same extractor and checks.
6. **Namesake companies.** Searching "Tally founders" returns Tally Solutions, a different company. *Fix:* pass the domain and the site's own description, and let the model label look-alikes as "other company".
7. **Gemini's built-in Google Search failed with HTTP 429.** The pricing page later confirmed search grounding is not available on the free tier. *Fix:* a separate keyless search library, with retries, varied query wording, early stopping and a pause between queries, because it throttles quickly and drops some phrasings at random.
8. **Openers were generic and stiff.** Early drafts all followed "You said X. I build Y. How do you Z?", invented claims about the sender ("I follow the same principle") and ended questions with a full stop. *Fix:* a stricter prompt, a shape-variety rule, and a code-level lint. The writing is still limited by the cheapest model: stronger Gemini models were out of quota or overloaded on a free key, so `GEMINI_DRAFT_MODEL` is left as a setting.
9. **Personal facts leaked in.** One fact was about a founder's wife, despite a prompt rule. *Fix:* a filter in code.
10. **Small data bugs.** The model returned `&amp;` inside text, and "Täht" and "Taht" appeared as two founders. *Fix:* decode entities, and compare names ignoring accents.
11. **Gemini kept returning 503 "high demand".** This happened for long stretches during testing and drove the retry, fallback model, deadline and short-error work.
12. **Stress testing found what ordinary use never would** (the table above): the gzip bomb needed hand-written decompression, because the HTTP library inflates a whole network chunk at once, so a size cap on downloaded bytes would not have helped.

---

## Cost breakdown

The only paid component is the Gemini API. Web search uses a keyless library (free), and there is no hosting yet.

**Measured token use** of a full run (analyze + draft for one founder), averaged over two real companies (Basecamp and Plausible) using the real API:

| | Calls | Input tokens | Output tokens | Time |
|---|---|---|---|---|
| Average full run | 3.5 | about 7,300 | about 1,200 | 34 to 52 s |

Typical calls: site extraction about 2,300 in and 150 out; fact extraction 2,500 to 4,300 in and 500 to 600 out; drafting about 1,000 in and 300 out (twice when the first attempt fails the lint).

**Price per full run** (Google's published paid-tier prices, per 1M tokens):

| Model | Input | Output | Cost per run |
|---|---|---|---|
| `gemini-3.1-flash-lite` (default) | $0.25 | $1.50 | **about $0.0036** |
| `gemini-3.5-flash-lite` (fallback) | $0.30 | $2.50 | about $0.0051 |
| Heavy case: web fallback, two founders, a drafting retry (estimated, not measured) | | | about $0.007 |

**At volume** (default model, average run):

| Runs per month | Cost |
|---|---|
| 100 | about $0.36 |
| 1,000 | about $3.57 |
| 10,000 | about $35.70 |

**Other costs and trade-offs**

- **Free tier:** tokens are free, but with low rate limits and frequent overload errors, and Google states that free-tier data is used to improve its products. Pages, pitches and founder names are sent to the API, so use the paid tier for anything confidential.
- **Web search:** free but unofficial and fragile. The alternative we avoided is Gemini's Google Search grounding: paid tier only, 5,000 free requests a month and then $14 per 1,000 (charged per query). At one query per run that is about $0.014, roughly four times the token cost of everything else.
- **Retries and the fallback model** cost extra only when something fails: a retry repeats that call, and the fallback model is about 40% dearer per run.
- **Hosting:** none so far, so $0 (it runs on a laptop).
- **Testing:** the offline suite costs nothing (fake Gemini). A live run makes roughly 20 to 30 calls, a few cents (estimate).

---

## The journey in brief

1. **Decided the stack first.** Python and FastAPI for the backend, React and TypeScript for the UI, Gemini for the AI, `httpx` and `trafilatura` for scraping. Challenged the plan before building: scope the scrape to the pages that matter, split the work into a pipeline instead of one prompt, and never trust the model without a source.
2. **Scaffolded** a health endpoint and a URL form, then built features one at a time.
3. **Built `/api/analyze`**: scrape, extract, stream progress, and a founder confirm step.
4. **Fixed accuracy** after real failures: smarter page selection, structured data, multiple founders, the testimonial trap, the quote rule.
5. **Added the web search fallback** for sites that are blocked, unreadable or silent, with namesake protection.
6. **Built `/api/draft`**: research, sourced facts, openers with a lint, a regenerate that reuses research, and the UI to match.
7. **Wrote a test suite designed to break it**: a hostile server, a fake Gemini, injection and SSRF cases, fault injection and load.
8. **Ran the stress test**, wrote the report, then fixed all seven problems one by one, re-measuring each with the same attack until the offline suite went from 134 passed and 35 failed to 265 passed and 0 failed.

---

## Known limits and next steps

- **Writing quality is bounded by the model.** Openers are specific and sourced, but a stronger model (set `GEMINI_DRAFT_MODEL`) would probably write better. Founders with little public writing get a generic, flagged opener.
- **Burst capacity is low for fallback-heavy traffic.** With real search latency and 2 search slots, a burst of 40 requests would take minutes and the tail would time out. Caching analysis results by domain is the real fix and is not built.
- **No authentication or per-user rate limiting.** Anyone who can reach the API can spend the Gemini quota. Add both before hosting it publicly.
- **The keyless search can break.** It is unofficial and rate-limited. A paid search API is a drop-in replacement (one function, `search_pages`).
- **Not covered by tests:** a client disconnecting mid-stream, DNS rebinding, non-English sites (the filters are English only), and live throughput under load.
- **JavaScript-only sites** rely on web search, not a headless browser.
- **Responsible use:** it reads only public, professional information, filters personal topics, and sends no email itself. It does not honour `robots.txt`, so respect each site's terms.
- **To deploy:** set `VITE_API_URL` and the CORS origins in `backend/app/main.py`, and add authentication and rate limiting first.
