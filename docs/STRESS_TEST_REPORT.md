# Stress Test Report: Ektara

**Date:** 2026-11-21
**System under test:** `POST /api/analyze` and `POST /api/draft` (FastAPI backend)
**Status of this report:** baseline measured **before** any hardening, followed by the results after each of the six fixes. **All six fixes are complete**; the offline suite has no failures.

## 1. Summary

The core logic is sound. The failures are not in what the system decides, but in what it **does not limit**.

| | Baseline | After fix 1 (scraper) | After fix 2 (prompts) | After fix 3 (resilience) | After fixes 4 to 6 (final) |
|---|---|---|---|---|---|
| Offline suite | **134 passed, 35 failed**, 11 skipped | 151 / 27 | 183 / 22 | 212 / 19 | **265 passed, 0 failed**, 11 skipped, 46 s |
| Scraper hostile tests | 16 passed, 8 failed | 33 / 0 | 33 / 0 | 33 / 0 | 33 / 0 |
| SSRF tests | 24 passed, 6 failed | 24 / 6 | 24 / 6 | 24 / 6 | **30 / 0** |
| Injection guardrail tests | 2 passed, 12 failed | 2 / 12 | 3 / 11 | 3 / 11 | **14 / 0** |
| Load tests | 1 passed, 2 failed | 1 / 2 | 1 / 2 | 1 / 2 | **3 / 0** |
| API validation tests | 16 passed, 3 failed | 16 / 3 | **all passing** | all passing | all passing |
| Prompt-bound, resilience and limit tests (added during fixes 2 to 6) | n/a | n/a | 27 / 0 | 50 / 0 | **84 / 0** |
| Live suite (real Gemini, real web) | **11 passed**, 0 failed | 9 / 2 | inconclusive (Gemini 503s) | inconclusive | **8 passed, 0 failed, 3 skipped** (Gemini overloaded) |
| Total tests | 180 | 189 | 216 | 242 | 276 |

The 35 failures are tests that state the behaviour we want. They fail on purpose until the guardrail exists. They reduce to **seven distinct problems**, and every one of them is a missing limit or a missing check, not a logic error:

| # | Problem | Severity | Measured |
|---|---|---|---|
| 1 | The scraper has no resource limits (**fixed**, see 3.1) | **High** | 40 MB page fully downloaded; a few-KB gzip bomb used **326 MB** of memory; a slow server held a request open **26 s** |
| 2 | Nothing bounds what is sent into LLM prompts (**fixed**, see 3.2) | **High** | one page injected **409,431** characters into a prompt (limit 8,000); 500 pages built a **3,022,388**-character prompt |
| 3 | No overall deadline, no retry, verbose errors (**fixed**, see 3.3) | **High** | a hung Gemini call blocks forever; one transient 503 fails the request; a 429 shows a **1,354**-character provider dump |
| 4 | No concurrency limits (**fixed**, see 3.4) | Medium | 60 requests made **60** simultaneous Gemini calls; 40 made **40** simultaneous searches |
| 5 | Prompt-injection guardrails are thin (**fixed**, see 3.5) | Medium | links, emails and phone numbers pass the opener lint; untrusted text is not fenced; `font-size:0` text is read |
| 6 | Any network port is allowed (**fixed**, see 3.6) | Low | `:22`, `:6379`, `:9200` accepted |
| 7 | Client-supplied fact fields have no ranges (**fixed**, see 3.2) | Low | an out-of-range value (`specificity: 99` or `id: -5`) is accepted |

**All seven problems are now fixed** (sections 3.1 to 3.7, results in section 8). Severity assumes the service could be hosted publicly. For a single-user local run, problems 1 to 3 are robustness issues and 4 to 7 are hardening.

## 2. Scope and method

**Faked on purpose (offline suite).** Gemini, the web search and the target websites are replaced with a scripted fake Gemini client and a local **hostile web server**. This measures our code (parsing, limits, error handling, concurrency) and not Google's or DuckDuckGo's behaviour, and it makes every run deterministic and free.

**Real (live suite, `--live`).** The real Gemini API and the open web, used for prompt-injection probes and a founder-accuracy set. Live tests skip, rather than fail, when the upstream service is unavailable.

| Area | File | Cases |
|---|---|---|
| Verification and lint logic | `test_logic_verification.py`, `test_logic_lint.py` | quote checks, namesakes, sensitive-topic filter, opener quality gate |
| SSRF | `test_ssrf.py` | 30 cases: 17 private or local address forms, 5 non-HTTP schemes, 2 public addresses (must be allowed), 6 unusual ports |
| Hostile scraping | `test_scraper_hostile.py` | huge page, gzip bomb, slow loris, redirect loop, redirect to metadata address, binary, 100,000 nested tags, 30,000 links, empty page, status codes, hidden text (6 variants), poisoned and deeply nested structured data, and (after fix 1) honest gzip, deflate and non-UTF-8 pages |
| Prompt injection (offline) | `test_injection.py` | output lint for links and contact details, prompt fencing, length bounds, invented founders |
| Fault injection | `test_faults.py` | Gemini 429, 503, garbage JSON, empty answers, 5,000 invented founders, a hung model, prompt size, dead search, draft failure modes |
| API contract | `test_api.py` | input validation, event-stream format, happy paths |
| Load | `test_load.py` | 60 concurrent requests (site path), 40 concurrent (web-fallback path), leaked tasks |
| Live injection | `tests/live/test_live_injection.py` | injected page, poisoned fact, hostile pitch |
| Live accuracy | `tests/live/test_live_evals.py` | 8 real companies with required and forbidden founder names |

## 3. Findings

### 3.1 The scraper has no resource limits (High)

**Tested:** a local server serving a 40 MB page, a gzip bomb (about 40 MB decompressed), and a server trickling one byte every 0.4 s.

| Test | Measured | Wanted |
|---|---|---|
| 40 MB page | server allowed to send **40 of 40 MB** | stop after a few MB |
| Gzip bomb | **326 MB** peak Python memory (about 8x the 40 MB payload) | under 25 MB |
| Slow loris | scrape took **26 s** | under 18 s |

**Why:** the response body is read in full with no size cap, decompression is unbounded, and the timeout applies to each network read, not to the whole fetch. A server that sends a byte every few hundred milliseconds never trips it.

**Fix:** read the response as a stream, stop after a decoded-size cap (about 2 MB), and add a total time limit per scrape.

**Status: fixed.** The same three attacks, re-measured:

| Attack | Before | After |
|---|---|---|
| 40 MB page: bytes the server managed to send | 40 MB (all of it) | **2.5 MB**; the page is still parsed from what was read (6,713 characters of text) |
| Gzip bomb: peak Python memory | 326 MB | **18.3 MB** |
| Slow loris: time until we give up | 26 s | **12.0 s**, ending in a clean `SITE_UNREACHABLE` error |

What changed, in `backend/app/services/scraper.py`:
- Pages are streamed, and reading stops at `MAX_RESPONSE_BYTES` (2 MB of **decoded** bytes). Reaching the cap is not an error: only the start of a page is used, so we keep what we read.
- A total deadline (`FETCH_DEADLINE`, 12 s) wraps each whole fetch, redirects included, on top of the existing 10 s per-read timeout that a trickling server never trips.
- We decompress by hand, asking zlib for at most the room left. This was the non-obvious part: httpx's own decoder expands each network chunk in one go, so a bomb a few KB long still inflates to tens of MB before any size check could run. A cap that only counted downloaded bytes would also have missed it.
- Unsupported content encodings (for example brotli) and corrupt compressed bodies end in a clean `NO_CONTENT` error. We now send `Accept-Encoding: gzip, deflate` so honest servers rarely use anything else.

Regression tests confirm honest sites are unaffected: gzip and deflate pages, and a page in ISO-8859-1, are read correctly, and 8 real company sites still work in the live suite.

### 3.2 Nothing bounds what is sent into LLM prompts (High)

**Tested:** pages with huge structured data, 500 pages at once, and oversized client-sent facts.

| Test | Measured | Wanted |
|---|---|---|
| Structured data listing 20,000 "founders" | page text **409,431** chars | under 8,000 |
| 500 scraped pages | prompt **3,022,388** chars | under 120,000 |
| `facts` sent to `/api/draft` | a **2 MB** quote accepted; **1,000** facts accepted | rejected with 422 |
| `company.one_liner` from the model | **52,000** chars kept | at most 300 |
| Structured-data "founder names" | whole sentences, line breaks and brackets accepted | name-shaped values only |
| Fact fields | an out-of-range `specificity` or `id` accepted | range-checked |

**Why:** the per-page cap is applied to page text, but hints appended after truncation, the total across pages, and client-supplied fields were never capped. Every token is cost, long inputs can exceed the model's context window, and unbounded attacker-controlled text is also the channel for prompt injection.

**Fix:** a total prompt cap; validated, capped hints (a few short name-shaped entries); length and range limits on `Company`, `Fact` and the `facts` list.

**Status: fixed.** The same inputs, re-measured:

| Input | Before | After |
|---|---|---|
| 500 scraped pages | 3,022,388-character prompt | **60,000** (the `MAX_PROMPT_CHARS` budget) |
| 2 MB `quote` in `facts` | accepted | **HTTP 422** |
| 1,000 entries in `facts` | accepted | **HTTP 422** (limit 12) |
| `specificity: 99`, `id: -5` | accepted | **HTTP 422** |
| 52,000-character `one_liner` in a request | accepted | **HTTP 422** (limit 300) |
| 20,000-name structured data | 409,431 characters | 499 (fix 1) |
| 12 facts, every field at its maximum | n/a | HTTP 200, drafting prompt under 20,000 characters |

What changed:
- **Inputs are rejected when too long.** `Company`, `Fact` and the `facts` list now have length and range limits (`schemas/company.py`, `schemas/draft.py`). The limits match what we already ask the model for, for example the fact prompt says "at most 300 characters" and the cap is 500.
- **Model output is cut, not refused** (`schemas/limits.py`). If Gemini writes a 400-character description, trimming it beats failing the request. A cut quote is still a verbatim prefix of the original, so it still verifies, and there is a test for that. Lists from the model are capped too (50 people, 20 facts, 20 openers).
- **A total prompt budget** (`services/prompting.py`). Earlier pages have priority, a page that does not fit is cut, and the rest are dropped. Quotes are verified only against text the model actually received, so a quote from cut-off text cannot be cited even if the model guesses it (tested).
- **Round trip.** Facts the system produces are accepted back when the browser sends them for a regenerate (tested at maximum size).
- Search results (title 200, snippet 1,000, URL 500 characters) and page titles (200) are capped too.

An honest note on severity: the 3,022,388-character case cannot happen through today's callers, which pass at most about a dozen pages (roughly 40,000 characters). The total budget is a safety net. The exposure that was real is the client-supplied `facts` and `Company` fields, which were completely open.

**Live re-check:** once Gemini recovered, `tally.so` returned Marie Martens and Filip Minev from web search, and fact research for Jason Fried returned 4 verified facts, both through the new budgeted prompts.

### 3.3 No overall deadline, no retry, verbose errors (High)

**Tested:** scripted Gemini failures.

| Test | Measured | Wanted |
|---|---|---|
| Model never answers | still running after 6 s, no deadline | clean error after about 90 s |
| One transient 503 | whole request failed | retried once, then succeeds |
| 429 quota error | user would see a **1,354**-character provider dump | short, clear message |

**Why:** Gemini errors are passed through verbatim, nothing retries, and no timer covers the pipeline. In real use the Gemini SDK retries internally for a long time (a real 503 took about 46 s to surface), so a hung call would look like a frozen app.

**Fix:** a pipeline deadline (about 90 s), one retry with a short backoff on 429 and 503, and sanitised error messages.

**Seen in the wild:** during the live re-run, one Gemini call stalled and the Plausible test ran past its 150 s limit, even though the same request takes 3.6 s normally and the scraper takes 0.6 s. Nothing in our code stopped the stalled call, which is exactly this finding. A second live test failed on a real Gemini 503 ("high demand") that a single retry might have survived. The live tests now skip, instead of fail, when the error message shows a Gemini outage. The outage returned during the fix-2 runs: most live calls got 503 for several minutes, then recovered. A real user would have seen failures for that whole window, which is the case for the retry.

**Status: fixed.** What changed:

| Before | After |
|---|---|
| A hung Gemini call blocks the request forever | The whole request stops with a `TIMEOUT` error after **90 s** (`/api/analyze`) or **120 s** (`/api/draft`). Events already sent are kept, and the stalled call is cancelled (tested: no task is left running). |
| One transient 503 or 429 fails the request | **One retry** with a short jittered pause. Not retried when retrying cannot help: a bad key or bad request (fails identically every time), or a **daily** quota that is gone. |
| A 429 shows the user a 1,354-character provider dump | A short message, for example "Gemini is overloaded or unavailable right now. Try again shortly" (under 120 characters, no provider JSON). The full text goes to the log only. A rejected key says so and names `GEMINI_API_KEY`. |
| No way around an overloaded model | Optional **fallback model** (`GEMINI_FALLBACK_MODEL`, off by default): after the retry fails, or immediately when the main model's quota is gone, the fallback gets one attempt. It is not tried for a bad key. Drafting keeps its own model and falls back the same way. |

**Tested on the real key:**

| Model | Result |
|---|---|
| `gemini-3.5-flash-lite` | works for structured output, so it is the recommended fallback |
| `gemini-3.1-flash-lite` (main) | worked, but returned 503 for long stretches during testing |
| `gemini-2.5-flash-lite` | 404, listed but not available to this key |
| `gemini-2.5-flash` | 400, does not accept system instructions, so unusable here |
| `gemini-4-carbon` | quota of 0 on the free tier, which makes it a good way to trigger the "quota gone" path on purpose |

**Live demonstration.** With `gemini-4-carbon` (no quota) as the main model and `gemini-3.5-flash-lite` as the fallback, every call had to use the fallback. The log shows a single attempt on the main model (no wasted retry), then "answered by the fallback model". A full analyze and a full draft then completed through the fallback; the first attempts were also hit by 503s on the fallback itself and returned the short message, as designed.

**A bug the live run found.** Through the fallback the founder list came back as `Uku Täht`, `Marko Saric`, `Uku Taht`: the site spells his name both ways and de-duplication did not treat `ä` and `a` as the same letter. Name comparison now ignores accents (and a quote written without accents still verifies the accented name). Covered by three new tests.

**Trade-offs.** Retries and a fallback make a failing request slower before it gives up, bounded by the deadline. A fallback model can write a little differently from the main one, so the quote check and the opener lint stay on for every model, and the log records which model answered.

### 3.4 No concurrency limits (Medium)

**Tested:** 60 concurrent requests (site path) and 40 concurrent requests (web-fallback path) with a fast fake backend.

| Metric | Site path (60 requests) | Web-fallback path (40 requests) |
|---|---|---|
| Succeeded | 60 / 60 | 40 / 40 |
| Wall time | 1.7 s | 2.2 s |
| Latency p50 / p95 / max | 1.3 / 1.4 / 1.4 s | 1.9 / 2.0 / 2.0 s |
| Peak concurrent Gemini calls | **60** | **40** |
| Peak concurrent searches | 0 | **40** |
| Worst event-loop lag | 678 ms | 408 ms |
| Memory growth | 30 MB | 8 MB |

**Reading this:** our own code is fast and correct under this load. The problem is that nothing limits how many calls reach upstream services at once. With real Gemini this produces rate-limit storms. The keyless search backend already rate-limits when queried sequentially, so it would fail first. The event-loop lag (up to 678 ms) suggests CPU-heavy parsing briefly starves other requests.

**Fix:** shared limits across all requests (about 8 Gemini calls and 3 searches at once), and optionally a "busy, try again" response when the queue is long.

**Status: fixed.** Every Gemini call, search query and page download now goes through a shared limiter (`services/limiter.py`). The extra calls wait for a free slot instead of all running at once. The same load tests, before and after:

| Metric | Before (60 / 40 requests) | After |
|---|---|---|
| Peak concurrent Gemini calls | **60** (site path), **40** (fallback path) | **6** |
| Peak concurrent searches | **40** | **2** |
| Requests that succeeded | 60 / 60 and 40 / 40 | 60 / 60 and 40 / 40: nobody fails because of waiting |
| Wall time, site path | 1.7 s | 4.1 s (p95 latency 1.4 s to 3.5 s) |
| Wall time, web-fallback path (fake 0.2 s search) | 2.2 s | 13.4 s |
| Worst event-loop lag | 678 ms | 686 ms (unchanged, see below) |
| Memory growth | 30 MB | 24 MB |

Defaults are 6 Gemini calls, 2 searches and 24 page downloads at once, set with `MAX_CONCURRENT_GEMINI`, `MAX_CONCURRENT_SEARCHES` and `MAX_CONCURRENT_FETCHES`.

Design details that are tested:
- The slot is held only during the call itself. A retry pause does not hold it, so another request can run while a failed one waits to retry.
- Time spent waiting for a slot counts toward the request's overall deadline, so nothing can wait forever. A request that times out gives its slot back (a later request can still get it).
- The page-download wait sits outside each page's own 12 s deadline, so a busy server does not make healthy pages look slow.
- One limiter is kept per event loop, because a semaphore that has made someone wait is tied to the loop it ran on.

**Trade-offs, stated plainly.**
- A burst gets slower instead of failing. That is the point, but it is real latency.
- With real search latency (about 3 s per query) and 2 search slots, a burst of 40 fallback requests would need about 3 minutes of search time, so the last of them would hit the 90 s deadline and end in a clear `TIMEOUT` error. That is far better than a storm of empty results reported as "no founder found", but it means real capacity for fallback-heavy traffic is low. The proper answer is caching analysis results by domain, which is not built.
- This caps concurrency, not rate per minute. A free Gemini key can still hit its per-minute limit; the retry, the fallback model and the short error messages from fix 3 handle that case.
- The event-loop lag (up to about 690 ms) is CPU-heavy page parsing briefly starving other work. It stays under the 1 s limit the test enforces, and this fix does not address it.

### 3.5 Prompt-injection guardrails are thin (Medium)

**Tested:** offline guardrail checks, then the real model with attacks.

| Test | Measured | Wanted |
|---|---|---|
| Opener containing a link, email or phone number | **6 of 6** payloads passed the lint | rejected |
| System prompts | none says that supplied text is data, not instructions | each says so |
| Untrusted text in prompts | not fenced; a fact can close the block and speak as the prompt author | fenced, closing tags escaped |
| Text hidden with `font-size:0` | reached the page text | stripped |

**Why:** the quote check proves that text exists on a page, not that it is true or harmless, and the attacker controls the page. Today the defence against an injected instruction is the model choosing not to follow it.

**Live result:** against the real model, all three attacks failed to take effect: a page telling it to rewrite the company description and add a fake founder, a poisoned fact telling it to end every opener with a link, and a pitch telling it to break the style rules. Each attack ran **once** against a non-deterministic model, so this is encouraging but not proof. The offline guardrails above are what turn "usually resists" into "cannot".

**Fix:** reject URLs, emails and phone numbers in openers; fence untrusted text in tags and escape closers; add a "data, not instructions" line to the system prompts; strip `font-size:0` text.

**Status: fixed.** What changed:

| Before | After |
|---|---|
| Links, emails and phone numbers pass the opener lint | The lint rejects `http(s)://` and `www.` links, domain names (`evil.example/win`, `bit.ly/...`), email addresses and phone numbers, and the drafting prompt forbids them. All 6 attack payloads are now rejected. Ordinary prose is not (`Node.js`, `e.g.`, `5.5 million`, `$6M`, and a missing space after a full stop as in `works.So` are all accepted, tested). |
| Untrusted text is mixed into prompts as plain text | The sender's pitch and the facts sit in `<pitch>` and `<facts>` blocks. Any `<` or `>` inside them becomes an entity, so a fact cannot close its block and speak as the prompt author (tested with a fake `</facts>` and `</pitch>`). |
| System prompts never mention the issue | Every system prompt (extractor, fact extractor, drafter) says that supplied text is data, not instructions. |
| Company text copied into system prompts | The company description is written by the model from a web page, then pasted into the **next call's system prompt**, where an injected instruction would carry more weight. It is now flattened to one line without tag or code characters, as are names and roles (tested with a poisoned description). |
| Page text can forge another page's header | `###` inside page text is defanged, and the quote check sees exactly the text the model saw (tested). |
| `font-size:0` text is read; structured-data "names" can be sentences | Fixed in fix 1. |

**Residual risk, honestly.** Prompt injection cannot be fully eliminated. These guardrails limit what a successful injection can do: the output is structured text with no tools or actions, a founder still needs a word-for-word quote on a page, and an opener can no longer carry a link, email or phone number. The live injection tests (a poisoned page, a poisoned fact, a hostile pitch) all passed against the real model, but each ran once against a non-deterministic model, so treat that as encouraging, not proof.

**Trade-off.** An opener that mentions a domain name on purpose (for example "dub.co") is rejected and regenerated. A false rejection costs a retry, which is cheaper than letting a link through.

### 3.6 Any network port is allowed (Low)

**Measured:** `:22`, `:25`, `:3306`, `:5432`, `:6379` and `:9200` on a public address were all accepted. The error text differs between "timed out", "refused" and "HTTP 200", which lets someone probe which ports are open on a third party.
**Fix:** allow only ports 80, 443, 8080 and 8443.

**Status: fixed.** `_ensure_public` now refuses any other port and any invalid one (`:99999`, `:0`, `:abc`) with a clean `INVALID_URL` error, before any DNS lookup or connection. The check runs on every redirect hop. All 6 port tests pass, and the four allowed ports and URLs with no explicit port still work. Trade-off: a legitimate site served on an unusual port can no longer be analysed.

### 3.7 Client-supplied fact fields have no ranges (Low)

Covered by 3.2. Listed separately because the fix is small: `specificity` 1 to 5, `id` at least 1. **Fixed together with 3.2.**

## 4. What held up

- **SSRF guard.** Blocked every address form tried: decimal, hex and octal IPv4, `127.1`, IPv4 inside IPv6, cloud metadata addresses (IPv4 and IPv6), private and CGNAT ranges, credentials in the URL, and non-HTTP schemes. It also allowed public addresses, so it does not over-block. One case (`127.0.0.1.nip.io`) depends on DNS being available in the test environment.
- **Redirects.** A redirect loop ends in an error within 5 s, and a redirect to the cloud metadata address is blocked.
- **Malformed pages.** Binary data labelled as HTML, 100,000 nested tags, 30,000 links and empty responses all fail cleanly or succeed; none crash the scraper.
- **Hidden text.** `display:none`, `visibility:hidden`, the `hidden` attribute, `aria-hidden` and HTML comments are all excluded from page text.
- **Founder verification.** 5,000 founders invented by a faked Gemini answer were all rejected by the quote check. Testimonial authors, namesake companies, partial-name quotes and whole-word matching behave correctly in 22 logic tests.
- **Cost bounds already in place.** A model that only writes cliches costs exactly 2 calls and one error. Cached facts skip research and search entirely. At most 3 openers are ever returned.
- **Event-stream contract.** Every run, success or failure, ends with exactly one result or error event.
- **Accuracy (live).** 8 of 8 real companies passed, including the Tally namesake trap (Tally Solutions founders correctly excluded), the Dub testimonial trap, a JavaScript-only site (SpaceX), a blocked site (Tesla), and sites that never name their founder (Paytm).

## 5. Not covered

- A client disconnecting mid-stream, and whether the scraping and search threads stop.
- DNS rebinding (a hostname that resolves to a public address at check time and a private one at fetch time).
- Real-service load. Against live Gemini and DuckDuckGo this would mostly measure their limits and could get the key or IP throttled.
- Non-English sites. The sensitive-topic filter and the banned-phrase list are English only, and name matching likely fails for names written without spaces.
- `robots.txt` and the honesty of the Chrome user-agent string, which is an ethics and terms-of-service question and not a crash.
- Request body size limits, authentication and per-IP rate limiting.
- The frontend, which is checked only by typecheck and lint.
- Real throughput of a burst against the live search backend. The load tests use fakes, and section 3.4 gives the arithmetic instead.
- Caching results by domain, per-user rate limiting and authentication, none of which are built.

## 6. Remediation plan

| Order | Fix | Closes | Status |
|---|---|---|---|
| 1 | Scraper limits: streamed size cap, total time cap, validated and capped hints, strip `font-size:0` | 3.1, part of 3.2, part of 3.5 | **done** |
| 2 | Bound everything entering prompts: total cap, field limits and ranges | 3.2, 3.7 | **done** |
| 3 | Pipeline deadline, one retry on 429 and 503, optional fallback model, short error messages | 3.3 | **done** |
| 4 | Shared concurrency limits for Gemini, search and page downloads | 3.4 | **done** |
| 5 | Injection guardrails: lint for links and contact details, fenced prompts, "data, not instructions", flattened company text | 3.5 | **done** |
| 6 | Port allowlist | 3.6 | **done** |

## 7. How to reproduce

```bash
cd backend
pip install -r requirements.txt -r requirements-dev.txt
pytest                      # offline suite, about 45 s
pytest -s                   # also prints the load numbers
pytest -m "not slow"        # skip the slowest tests
pytest --live               # also run the real-Gemini and real-web tests
```

## 8. Results after fixes

| | Baseline | After all six fixes |
|---|---|---|
| Offline suite: passed / failed | 134 / 35 | **265 / 0** |
| Live suite | 11 passed | 8 passed, 3 skipped (Gemini overloaded) |
| 40 MB page: bytes read | 40 MB | 2.5 MB |
| Peak memory on gzip bomb | 326 MB | 18.3 MB |
| Time to give up on a slow-loris server | 26 s | 12.0 s |
| Page text from a 20,000-name structured-data block | 409,431 chars | 499 chars |
| Text hidden with `font-size:0` reaches the page text | yes | no |
| Largest prompt from one request | 3,022,388 chars | 60,000 chars |
| 2 MB `quote` / 1,000 `facts` sent to `/api/draft` | accepted | rejected (422) |
| Pipeline with a hung model | never ends | stops with TIMEOUT at 90 s / 120 s |
| One transient 503 | request fails | retried, succeeds |
| Error text shown for a Gemini 429 | 1,354 chars | under 120 chars |
| Overloaded main model | request fails | optional fallback model |
| Founder listed twice when a name has accents (`Täht` / `Taht`) | yes | no |
| Peak concurrent Gemini calls (60 requests) | 60 | 6 |
| Peak concurrent searches (40 requests) | 40 | 2 |
| Opener containing a link, email or phone number passes the lint | yes (6 of 6) | no (0 of 6) |
| Untrusted text fenced in prompts | no | yes |
| Ports `:22`, `:6379`, `:9200` accepted | yes | refused |
